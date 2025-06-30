import time
import threading
import multiprocessing as mp
from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path
try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False

@dataclass
class ProcessStatus:
    file_name: str
    total_channels: int = 0
    completed: int = 0
    working: int = 0
    broken: int = 0
    elapsed: float = 0
    status: str = "waiting"

class ProgressTracker:
    def __init__(self, total: int, show_progress: bool = True):
        self.total = total
        self.completed = 0
        self.working = 0
        self.broken = 0
        self.start_time = time.time()
        self.show_progress = show_progress and TQDM_AVAILABLE
        self.pbar = None
        if self.show_progress:
            self.pbar = tqdm(total=total, desc="Checking channels", unit="ch")
    
    def update(self, is_working: bool):
        self.completed += 1
        if is_working:
            self.working += 1
        else:
            self.broken += 1
        if self.pbar:
            self.pbar.update(1)
            self.pbar.set_postfix(working=self.working, broken=self.broken)
    
    def close(self):
        if self.pbar:
            self.pbar.close()
    
    def get_elapsed_time(self) -> float:
        return time.time() - self.start_time

class MultiProcessProgressManager:
    def __init__(self, file_paths: List[Path], show_progress: bool = True):
        self.file_paths = file_paths
        self.show_progress = show_progress and TQDM_AVAILABLE
        self.manager = mp.Manager()
        self.shared_status = self.manager.dict()
        self.lock = threading.Lock()
        self.progress_bars = {}
        self.main_bar = None
        self.total_files = len(file_paths)
        self.completed_files = 0
        self.display_thread = None
        self.should_stop = False
        for i, file_path in enumerate(file_paths):
            self.shared_status[i] = {
                'file_name': file_path.name,
                'total_channels': 0,
                'completed': 0,
                'working': 0,
                'broken': 0,
                'elapsed': 0,
                'status': 'waiting'
            }

    def start_display(self):
        if not self.show_progress:
            return
        self.main_bar = tqdm(
            total=self.total_files,
            desc="Overall Progress",
            position=0,
            leave=True,
            bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} files [{elapsed}<{remaining}]"
        )
        for i in range(len(self.file_paths)):
            file_name = self.file_paths[i].name
            display_name = file_name[:25] + "..." if len(file_name) > 25 else file_name
            self.progress_bars[i] = tqdm(
                total=100,
                desc=f"File {i+1}: {display_name}",
                position=i+1,
                leave=False,
                bar_format="{l_bar}{bar}| {postfix}"
            )
        self.display_thread = threading.Thread(target=self._update_display, daemon=True)
        self.display_thread.start()

    def _update_display(self):
        while not self.should_stop and self.completed_files < self.total_files:
            completed_count = 0
            for process_id in range(len(self.file_paths)):
                if process_id not in self.shared_status:
                    continue
                status = self.shared_status.get(process_id, {})
                if process_id not in self.progress_bars:
                    continue
                bar = self.progress_bars[process_id]
                if status.get('status') == 'completed':
                    if bar.n < bar.total:
                        bar.n = bar.total
                        bar.set_postfix_str(f"✅ {status.get('working', 0)}W/{status.get('broken', 0)}B ({status.get('elapsed', 0):.1f}s)")
                        bar.refresh()
                    completed_count += 1
                elif status.get('status') == 'processing':
                    total_channels = status.get('total_channels', 0)
                    if total_channels > 0:
                        progress = min(100, int((status.get('completed', 0) / total_channels) * 100))
                        bar.n = progress
                        bar.set_postfix_str(f"⚡ {status.get('completed', 0)}/{total_channels} ({status.get('working', 0)}W/{status.get('broken', 0)}B)")
                        bar.refresh()
                elif status.get('status') == 'error':
                    if bar.n < bar.total:
                        bar.n = bar.total
                        bar.set_postfix_str("❌ Error")
                        bar.refresh()
                    completed_count += 1
                elif status.get('status') == 'waiting':
                    bar.set_postfix_str("⏳ Waiting")
                    bar.refresh()
            if completed_count != self.completed_files:
                self.completed_files = completed_count
                if self.main_bar:
                    self.main_bar.n = completed_count
                    self.main_bar.refresh()
            time.sleep(0.1)

    def update_process_status(self, process_id: int, **kwargs):
        if process_id in self.shared_status:
            status = dict(self.shared_status[process_id])
            status.update(kwargs)
            self.shared_status[process_id] = status

    def close(self):
        if not self.show_progress:
            return
        self.should_stop = True
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.join(timeout=1.0)
        time.sleep(0.2)
        for bar in self.progress_bars.values():
            if bar:
                bar.close()
        if self.main_bar:
            self.main_bar.close()

class ProcessProgressTracker:
    def __init__(self, process_id: int, shared_status: Dict, total: int):
        self.process_id = process_id
        self.shared_status = shared_status
        self.total = total
        self.completed = 0
        self.working = 0
        self.broken = 0
        self.start_time = time.time()
        self._update_status(
            total_channels=total,
            status='processing'
        )

    def update(self, is_working: bool):
        self.completed += 1
        if is_working:
            self.working += 1
        else:
            self.broken += 1
        self._update_status(
            completed=self.completed,
            working=self.working,
            broken=self.broken,
            elapsed=time.time() - self.start_time
        )

    def complete(self, success: bool = True):
        self._update_status(
            completed=self.total,
            working=self.working,
            broken=self.broken,
            elapsed=time.time() - self.start_time,
            status='completed' if success else 'error'
        )

    def get_elapsed_time(self) -> float:
        return time.time() - self.start_time

    def _update_status(self, **kwargs):
        if self.process_id in self.shared_status:
            status = dict(self.shared_status[self.process_id])
            status.update(kwargs)
            self.shared_status[self.process_id] = status

def create_process_tracker(process_id: int, shared_status: Dict, total: int) -> ProcessProgressTracker:
    return ProcessProgressTracker(process_id, shared_status, total)