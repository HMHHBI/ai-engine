import os
import psutil
from typing import Tuple


class ProcessSampler:
    def __init__(self, pid: int = None):
        self.process = psutil.Process(pid or os.getpid())

    def sample(self) -> Tuple[float, float]:
        """Returns (cpu_percent, rss_mb)."""
        try:
            cpu = self.process.cpu_percent(interval=None)
            rss = self.process.memory_info().rss / (1024 * 1024)
            return cpu, rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0, 0.0
