#!/usr/bin/env python3
import os
import subprocess
import time
from typing import Tuple

from .base import Runner

class CSharpRunner(Runner):
    def __init__(self, source_file: str = "Answer.cs", time_limit: float = 2.0, memory_limit: int = 262144):
        super().__init__(source_file, time_limit, memory_limit)

    def _get_solution_file(self) -> str:
        return "solution.dll"

    def compile(self) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["csc", "/out:" + self.solution_file, self.source_file],
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                with open(self.compile_error_log, "w") as f:
                    f.write(result.stderr)
                return False, result.stderr
            return True, ""
        except subprocess.TimeoutExpired:
            with open(self.compile_error_log, "w") as f:
                f.write("Compilation timed out")
            return False, "Compilation timed out"
        except FileNotFoundError:
            with open(self.compile_error_log, "w") as f:
                f.write("csc compiler not found. Please install .NET SDK.")
            return False, "csc compiler not found. Please install .NET SDK."
        except Exception as e:
            with open(self.compile_error_log, "w") as f:
                f.write(str(e))
            return False, str(e)

    def run(self, input_file: str, output_file: str) -> Tuple[str, float, int, str]:
        status = "AC"
        run_time = 0.0
        memory_kb = 0
        error_msg = ""

        try:
            with open(input_file, "r") as fin, open(output_file, "w") as fout:
                start_time = time.time()
                proc = subprocess.Popen(
                    ["mono", self.solution_file],
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
                    error_msg = f"Runtime Error (exit code {proc.returncode})"

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