import logging
import sys
import os
from typing import List, Dict
from pathlib import Path
from models import IPTVChannel
def setup_logging(config: Dict, file_prefix: str = None):
    handlers = []
    if config.get("log_to_file", True):
        log_file = config.get("log_file", "iptv_checker.log")
        if file_prefix and config.get("batch_processing", {}).get("log_per_file", False):
            log_path = Path(log_file)
            log_file = log_path.parent / f"{file_prefix}_{log_path.name}"
        handlers.append(logging.FileHandler(log_file, encoding='utf-8'))
    if not config.get("show_progress_bar", True):
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=getattr(logging, config.get("log_level", "INFO")),
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True
    )
def print_summary(working_channels: List[IPTVChannel], broken_channels: List[IPTVChannel], 
                 elapsed_time: float, config: Dict):
    total = len(working_channels) + len(broken_channels)
    working_count = len(working_channels)
    broken_count = len(broken_channels)
    working_percent = (working_count / total) * 100 if total > 0 else 0
    print(f"\n{'='*60}")
    print(f"IPTV CHECKER RESULTS")
    print(f"{'='*60}")
    print(f"Total channels:     {total}")
    print(f"Working channels:   {working_count} ({working_percent:.1f}%)")
    print(f"Broken channels:    {broken_count} ({100-working_percent:.1f}%)")
    print(f"Check duration:     {elapsed_time:.2f} seconds")
    print(f"Average per channel: {elapsed_time/total:.2f} seconds" if total > 0 else "")
    print(f"{'='*60}")
    if config.get("show_errors_in_summary", True) and broken_channels:
        error_stats = {}
        for channel in broken_channels:
            error = channel.error_message or "Unknown error"
            error_stats[error] = error_stats.get(error, 0) + 1
        max_errors = config.get("max_errors_to_show", 5)
        print(f"\nTOP {max_errors} ERRORS:")
        print("-" * 30)
        for error, count in sorted(error_stats.items(), key=lambda x: x[1], reverse=True)[:max_errors]:
            percentage = (count / broken_count) * 100
            print(f"  {error}: {count} channels ({percentage:.1f}%)")
        print()
def ensure_directory(path: str) -> Path:
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path
def get_file_size_mb(file_path: Path) -> float:
    try:
        return file_path.stat().st_size / (1024 * 1024)
    except:
        return 0.0
def format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{seconds//60:.0f}m {seconds%60:.0f}s"
    else:
        return f"{seconds//3600:.0f}h {(seconds%3600)//60:.0f}m {seconds%60:.0f}s"