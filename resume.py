import logging
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from models import IPTVChannel
from parser import M3UParser

class ResumeManager:
    def __init__(self, config: Dict):
        self.config = config
        self.output_prefix = config.get('output_prefix', 'checked')
    
    def should_skip_file(self, file_path: Path, working_dir: Path = None, broken_dir: Path = None) -> Tuple[bool, Optional[str]]:
        """Проверяет, нужно ли пропустить файл на основе существующих выходных файлов"""
        base_name = file_path.stem
        extension = file_path.suffix
        
        working_file = self._get_output_file_path(file_path, working_dir, "working", base_name, extension)
        broken_file = self._get_output_file_path(file_path, broken_dir, "broken", base_name, extension)
        
        working_exists = working_file and working_file.exists()
        broken_exists = broken_file and broken_file.exists()
        
        if not working_exists and not broken_exists:
            return False, None
        
        try:
            original_channels = M3UParser.parse(str(file_path), self.config)
            original_count = len(original_channels)
            
            if original_count == 0:
                return False, "Original file has no channels"
            
            total_output_channels = 0
            output_files = []
            
            if working_exists:
                working_channels = M3UParser.parse(str(working_file), self.config)
                total_output_channels += len(working_channels)
                output_files.append(f"working({len(working_channels)})")
            
            if broken_exists:
                broken_channels = M3UParser.parse(str(broken_file), self.config)
                total_output_channels += len(broken_channels)
                output_files.append(f"broken({len(broken_channels)})")
            
            if total_output_channels == original_count:
                reason = f"Complete: {' + '.join(output_files)} = {total_output_channels}/{original_count}"
                return True, reason
            else:
                reason = f"Incomplete: {' + '.join(output_files)} = {total_output_channels}/{original_count}"
                return False, reason
                
        except Exception as e:
            logging.warning(f"Error checking resume status for {file_path.name}: {e}")
            return False, f"Error checking: {e}"
    
    def _get_output_file_path(self, original_file: Path, output_dir: Path, suffix: str, base_name: str, extension: str) -> Optional[Path]:
        """Получает путь к выходному файлу"""
        if output_dir:
            return output_dir / f"{self.output_prefix}_{base_name}_{suffix}{extension}"
        else:
            return original_file.parent / f"{self.output_prefix}_{base_name}_{suffix}{extension}"
    
    def filter_files_for_processing(self, files: List[Path], working_dir: Path = None, broken_dir: Path = None, force: bool = False) -> Tuple[List[Path], List[Dict]]:
        """Фильтрует файлы для обработки, исключая уже обработанные"""
        if force:
            return files, []
        
        files_to_process = []
        skipped_files = []
        
        for file_path in files:
            should_skip, reason = self.should_skip_file(file_path, working_dir, broken_dir)
            
            if should_skip:
                skipped_files.append({
                    'file': file_path.name,
                    'reason': reason,
                    'path': str(file_path)
                })
                logging.info(f"Skipping {file_path.name}: {reason}")
            else:
                files_to_process.append(file_path)
                if reason:
                    logging.info(f"Processing {file_path.name}: {reason}")
        
        return files_to_process, skipped_files
    
    def get_resume_info(self, files: List[Path], working_dir: Path = None, broken_dir: Path = None) -> Dict:
        """Получает информацию о состоянии resume для списка файлов"""
        total_files = len(files)
        completed_files = 0
        incomplete_files = 0
        new_files = 0
        
        completed_details = []
        incomplete_details = []
        
        for file_path in files:
            should_skip, reason = self.should_skip_file(file_path, working_dir, broken_dir)
            
            if should_skip:
                completed_files += 1
                completed_details.append({
                    'file': file_path.name,
                    'reason': reason
                })
            elif reason and "Incomplete" in reason:
                incomplete_files += 1
                incomplete_details.append({
                    'file': file_path.name,
                    'reason': reason
                })
            else:
                new_files += 1
        
        return {
            'total_files': total_files,
            'completed_files': completed_files,
            'incomplete_files': incomplete_files,
            'new_files': new_files,
            'completed_details': completed_details,
            'incomplete_details': incomplete_details
        }
    
    def cleanup_incomplete_files(self, files: List[Path], working_dir: Path = None, broken_dir: Path = None) -> List[str]:
        """Удаляет неполные выходные файлы"""
        cleaned_files = []
        
        for file_path in files:
            should_skip, reason = self.should_skip_file(file_path, working_dir, broken_dir)
            
            if not should_skip and reason and "Incomplete" in reason:
                base_name = file_path.stem
                extension = file_path.suffix
                
                working_file = self._get_output_file_path(file_path, working_dir, "working", base_name, extension)
                broken_file = self._get_output_file_path(file_path, broken_dir, "broken", base_name, extension)
                
                for output_file in [working_file, broken_file]:
                    if output_file and output_file.exists():
                        try:
                            output_file.unlink()
                            cleaned_files.append(str(output_file))
                            logging.info(f"Removed incomplete file: {output_file}")
                        except Exception as e:
                            logging.error(f"Error removing {output_file}: {e}")
        
        return cleaned_files
    
    def print_resume_summary(self, resume_info: Dict, skipped_files: List[Dict]):
        """Выводит сводку о состоянии resume"""
        if resume_info['completed_files'] == 0 and resume_info['incomplete_files'] == 0:
            return
        
        print(f"\n{'='*60}")
        print(f"RESUME STATUS")
        print(f"{'='*60}")
        print(f"Total files: {resume_info['total_files']}")
        print(f"Already completed: {resume_info['completed_files']}")
        print(f"Incomplete: {resume_info['incomplete_files']}")
        print(f"New files: {resume_info['new_files']}")
        
        if resume_info['completed_files'] > 0:
            print(f"\nCompleted files (skipped):")
            for item in resume_info['completed_details']:
                print(f"  ✅ {item['file']} - {item['reason']}")
        
        if resume_info['incomplete_files'] > 0:
            print(f"\nIncomplete files (will be reprocessed):")
            for item in resume_info['incomplete_details']:
                print(f"  ⚠️  {item['file']} - {item['reason']}")
        
        print(f"{'='*60}")
