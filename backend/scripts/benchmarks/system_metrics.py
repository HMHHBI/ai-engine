import os
import psutil
from typing import Tuple, Optional


class ProcessSampler:
    """
    Samples process telemetry.
    Defaults to the benchmark runner process unless TARGET_PID / pid is explicitly passed.
    Note: Client-side sampling measures the benchmark runner overhead. For container/host
    backend measurements, pass the backend server PID or use container stats.
    """
    def __init__(self, pid: Optional[int] = None):
        target_pid = pid or (int(os.environ["TARGET_PID"]) if os.getenv("TARGET_PID") else os.getpid())
        self.process = psutil.Process(target_pid)

    def sample(self) -> Tuple[float, float]:
        """Returns (cpu_percent, rss_mb)."""
        try:
            cpu = self.process.cpu_percent(interval=None)
            rss = self.process.memory_info().rss / (1024 * 1024)
            return cpu, rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return 0.0, 0.0
