import asyncio
import argparse
import time
import sys
import logging
import multiprocessing as mp
from pathlib import Path
from typing import List
from config import load_config
from parser import M3UParser
from checker import StreamChecker
from utils import setup_logging, print_summary
from progress import MultiProcessProgressManager, ProcessProgressTracker
from resume import ResumeManager

def process_single_file_sync(args_tuple) -> dict:
    file_path, config, working_dir, broken_dir, process_id, shared_status = args_tuple
    return asyncio.run(process_single_file_async(file_path, config, working_dir, broken_dir, process_id, shared_status))

async def process_single_file_async(file_path: Path, config: dict, working_dir: Path = None, broken_dir: Path = None, process_id: int = None, shared_status = None) -> dict:
    try:
        channels = M3UParser.parse(str(file_path), config)
        if not channels:
            if shared_status and process_id is not None:
                tracker = ProcessProgressTracker(process_id, shared_status, 0)
                tracker.complete(False)
            return {"file": file_path.name, "error": "No channels found", "working": 0, "broken": 0}
        start_time = time.time()
        tracker = None
        if shared_status and process_id is not None:
            tracker = ProcessProgressTracker(process_id, shared_status, len(channels))
        async with StreamChecker(config) as checker:
            if tracker:
                checker.progress_tracker = tracker
            working_channels, broken_channels = await checker.check_all_streams(channels)
        if tracker:
            tracker.complete(True)
        elapsed_time = time.time() - start_time
        base_name = file_path.stem
        extension = file_path.suffix
        output_prefix = config.get('output_prefix', 'checked')
        working_file = None
        broken_file = None
        if working_channels:
            working_file = (working_dir or file_path.parent) / f"{output_prefix}_{base_name}_working{extension}"
            M3UParser.save_playlist(working_channels, str(working_file))
        if broken_channels:
            broken_file = (broken_dir or file_path.parent) / f"{output_prefix}_{base_name}_broken{extension}"
            M3UParser.save_playlist(broken_channels, str(broken_file))
        return {
            "file": file_path.name,
            "working": len(working_channels),
            "broken": len(broken_channels),
            "elapsed": elapsed_time,
            "working_file": str(working_file) if working_file else None,
            "broken_file": str(broken_file) if broken_file else None
        }
    except Exception as e:
        if shared_status and process_id is not None:
            tracker = ProcessProgressTracker(process_id, shared_status, 0)
            tracker.complete(False)
        return {"file": file_path.name, "error": str(e), "working": 0, "broken": 0}

def find_m3u_files(directory: Path) -> List[Path]:
    m3u_files = []
    for pattern in ['*.m3u', '*.m3u8']:
        m3u_files.extend(directory.glob(pattern))
    return sorted(m3u_files)

async def main():
    parser = argparse.ArgumentParser(description='IPTV M3U Playlist Checker')
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--file', help='Path to single M3U file')
    input_group.add_argument('--dir', help='Directory with M3U files')
    parser.add_argument('-c', '--config', default='config.json', help='Configuration file path')
    parser.add_argument('-o', '--output-prefix', help='Output files prefix')
    parser.add_argument('-t', '--timeout', type=int, help='Timeout for each stream in seconds')
    parser.add_argument('--concurrent', type=int, help='Max concurrent connections')
    parser.add_argument('--processes', type=int, default=1, help='Number of parallel processes for multiple files')
    parser.add_argument('--working-dir', help='Directory to save working playlists')
    parser.add_argument('--broken-dir', help='Directory to save broken playlists')
    parser.add_argument('--working-only', action='store_true', help='Create only working channels playlist')
    parser.add_argument('--broken-only', action='store_true', help='Create only broken channels playlist')
    parser.add_argument('--no-progress', action='store_true', help='Disable progress bar')
    parser.add_argument('--force', action='store_true', help='Force recheck all files (ignore resume)')
    parser.add_argument('--resume-info', action='store_true', help='Show resume information and exit')
    parser.add_argument('--cleanup-incomplete', action='store_true', help='Remove incomplete output files and exit')
    args = parser.parse_args()
    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)
    if args.output_prefix:
        config['output_prefix'] = args.output_prefix
    if args.timeout:
        config['timeout'] = args.timeout
        config['client_timeout']['total'] = args.timeout
        config['client_timeout']['sock_read'] = args.timeout
    if args.concurrent:
        config['max_concurrent'] = args.concurrent
    if args.no_progress:
        config['show_progress_bar'] = False
    setup_logging(config)
    working_dir = Path(args.working_dir) if args.working_dir else None
    broken_dir = Path(args.broken_dir) if args.broken_dir else None
    try:
        if working_dir:
            working_dir.mkdir(parents=True, exist_ok=True)
        if broken_dir:
            broken_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error creating directories: {e}")
        sys.exit(1)
    files_to_process = []
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"Error: File {args.file} not found!")
            sys.exit(1)
        files_to_process = [file_path]
    else:
        input_dir = Path(args.dir)
        if not input_dir.exists():
            print(f"Error: Directory {args.dir} not found!")
            sys.exit(1)
        files_to_process = find_m3u_files(input_dir)
        if not files_to_process:
            print(f"Error: No M3U files found in {args.dir}")
            sys.exit(1)
    print(f"Found {len(files_to_process)} file(s)")
    for f in files_to_process:
        print(f"  - {f}")
    if args.broken_only:
        working_dir = None
    if args.working_only:
        broken_dir = None
    resume_manager = ResumeManager(config)
    if args.resume_info:
        resume_info = resume_manager.get_resume_info(files_to_process, working_dir, broken_dir)
        resume_manager.print_resume_summary(resume_info, [])
        return
    if args.cleanup_incomplete:
        cleaned_files = resume_manager.cleanup_incomplete_files(files_to_process, working_dir, broken_dir)
        if cleaned_files:
            print(f"Cleaned up {len(cleaned_files)} incomplete files:")
            for file in cleaned_files:
                print(f"  - {file}")
        else:
            print("No incomplete files found to clean up")
        return
    original_files_count = len(files_to_process)
    files_to_process, skipped_files = resume_manager.filter_files_for_processing(
        files_to_process, working_dir, broken_dir, args.force
    )
    if not files_to_process:
        print("All files have been already processed. Use --force to reprocess or --cleanup-incomplete to clean incomplete files.")
        if skipped_files:
            print(f"\nSkipped {len(skipped_files)} completed files:")
            for skipped in skipped_files:
                print(f"  ✅ {skipped['file']} - {skipped['reason']}")
        return
    if skipped_files:
        all_files = files_to_process + [Path(f['path']) for f in skipped_files]
        resume_info = resume_manager.get_resume_info(all_files, working_dir, broken_dir)
        resume_manager.print_resume_summary(resume_info, skipped_files)
    print(f"\nProcessing {len(files_to_process)} file(s):")
    for f in files_to_process:
        print(f"  - {f}")
    if skipped_files:
        print(f"Skipped {len(skipped_files)} already processed file(s)")
    start_time = time.time()
    if len(files_to_process) == 1:
        result = await process_single_file_async(files_to_process[0], config, working_dir, broken_dir)
        results = [result]
    else:
        max_processes = min(args.processes, len(files_to_process), mp.cpu_count())
        progress_manager = MultiProcessProgressManager(
            files_to_process, 
            config.get('show_progress_bar', True) and not args.no_progress
        )
        try:
            progress_manager.start_display()
            print(f"Processing with {max_processes} parallel processes...\n")
            with mp.Pool(max_processes) as pool:
                process_args = [
                    (f, config, working_dir, broken_dir, i, progress_manager.shared_status) 
                    for i, f in enumerate(files_to_process)
                ]
                results = pool.map(process_single_file_sync, process_args)
        finally:
            progress_manager.close()
    total_elapsed = time.time() - start_time
    print(f"\n{'='*80}")
    print(f"BATCH PROCESSING RESULTS")
    print(f"{'='*80}")
    total_working = 0
    total_broken = 0
    successful_files = 0
    for result in results:
        if 'error' in result:
            print(f"❌ {result['file']}: {result['error']}")
        else:
            successful_files += 1
            total_working += result['working']
            total_broken += result['broken']
            print(f"✅ {result['file']}: {result['working']} working, {result['broken']} broken ({result['elapsed']:.1f}s)")
            if result.get('working_file'):
                print(f"   Working → {result['working_file']}")
            if result.get('broken_file'):
                print(f"   Broken → {result['broken_file']}")
    print(f"\n{'='*80}")
    print(f"SUMMARY:")
    print(f"Original files found: {original_files_count}")
    if skipped_files:
        print(f"Already completed: {len(skipped_files)}")
    print(f"Files processed: {successful_files}/{len(files_to_process)}")
    print(f"Total working channels: {total_working}")
    print(f"Total broken channels: {total_broken}")
    print(f"Total processing time: {total_elapsed:.2f}s")
    if successful_files > 0:
        print(f"Average per file: {total_elapsed/successful_files:.2f}s")
    print(f"{'='*80}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)