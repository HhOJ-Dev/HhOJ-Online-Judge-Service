#!/usr/bin/env python3
import os
import subprocess
import time
from typing import Tuple

from .base import Runner

class PythonRunner(Runner):
    def __init__(self, source_file: str = "Answer.py", time_limit: float = 2.0, memory_limit: int = 262144):
        super().__init__(source_file, time_limit, memory_limit)

    def _get_solution_file(self) -> str:
        return self.source_file

    def compile(self) -> Tuple[bool, str]:
        return True, ""

    def run(self, input_file: str, output_file: str) -> Tuple[str, float, int, str]:
        status = "AC"
        run_time = 0.0
        memory_kb = 0
        error_msg = ""

        try:
            with open(input_file, "r") as fin, open(output_file, "w") as fout:
                start_time = time.time()
                proc = subprocess.Popen(
                    ["python3", self.source_file],
                    stdin=fin,
                    stdout=fout,
                    stderr=subprocess.PIPE,
                )

                try:
                    proc.wait(timeout=self.time_limit)
                    run_time = time.time() - start_time
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    return "TLE", self.time_limit, 0, "Time Limit Exceeded"

                if proc.returncode != 0:
                    status = "RE"
                    stderr = proc.stderr.read().decode("utf-8", errors="replace")
                    error_msg = f"Runtime Error: {stderr}"
                    with open(self.run_error_log, "w") as f:
                        f.write(stderr)
                else:
                    stderr = proc.stderr.read().decode("utf-8", errors="replace")
                    if stderr:
                        with open(self.run_error_log, "w") as f:
                            f.write(stderr)

        except FileNotFoundError as e:
            status = "UKE"
            error_msg = f"File not found: {e}"
        except Exception as e:
            status = "UKE"
            error_msg = str(e)

        return status, run_time, memory_kb, error_msg

    def measure_memory(self, input_file: str) -> Tuple[int, str]:
        time_path = None
        for tp in ["/usr/bin/time", "/usr/local/bin/time", "/bin/time"]:
            if os.path.exists(tp):
                time_path = tp
                break

        if not time_path:
            time_path = shutil.which("time")

        if not time_path:
            return 0, "/usr/bin/time not available"

        import shutil
        try:
            with open(input_file, "r") as fin:
                result = subprocess.run(
                    [time_path, "-v", "python3", self.source_file],
                    stdin=fin,
                    capture_output=True,
                    text=True,
                    timeout=self.time_limit + 5,
                )
                stderr = result.stderr
                import re
                match = re.search(r"Maximum resident set size $kbytes$:\s+(\d+)", stderr)
                if match:
                    return int(match.group(1)), ""
                return 0, "Could not parse memory usage"
        except Exception as e:
            return 0, str(e)