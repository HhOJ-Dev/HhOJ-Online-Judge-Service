#!/usr/bin/env python3
import os
import subprocess
import time
import shutil
from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict

class Runner(ABC):
    def __init__(self, source_file: str, time_limit: float = 2.0, memory_limit: int = 262144):
        self.source_file = source_file
        self.time_limit = time_limit
        self.memory_limit = memory_limit
        self.solution_file = self._get_solution_file()
        self.compile_error_log = "compile_error.log"
        self.run_error_log = "run_error.log"

    @abstractmethod
    def _get_solution_file(self) -> str:
        pass

    @abstractmethod
    def compile(self) -> Tuple[bool, str]:
        pass

    @abstractmethod
    def run(self, input_file: str, output_file: str) -> Tuple[str, float, int, str]:
        pass

    def measure_memory(self, input_file: str) -> Tuple[int, str]:
        time_path = shutil.which("time")
        if not time_path and os.path.exists("/usr/bin/time"):
            time_path = "/usr/bin/time"

        if not time_path:
            return 0, "/usr/bin/time not available"

        try:
            with open(input_file, "r") as fin:
                result = subprocess.run(
                    [time_path, "-v", self.solution_file],
                    stdin=fin,
                    capture_output=True,
                    text=True,
                    timeout=self.time_limit + 5,
                )
                stderr = result.stderr
                match = __import__("re").search(r"Maximum resident set size $kbytes$:\s+(\d+)", stderr)
                if match:
                    return int(match.group(1)), ""
                return 0, "Could not parse memory usage"
        except Exception as e:
            return 0, str(e)

    def cleanup(self):
        if os.path.exists(self.solution_file):
            os.remove(self.solution_file)
        if os.path.exists(self.compile_error_log):
            os.remove(self.compile_error_log)
        if os.path.exists(self.run_error_log):
            os.remove(self.run_error_log)