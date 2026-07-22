import os
import subprocess
from runners._common import run_sandboxed

class PythonRunner:
    def __init__(self, version='3'):
        self.version = version

    def compile(self, code, sub_dir):
        src_path = os.path.join(sub_dir, 'main.py')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        cmd = ['python3', '-m', 'py_compile', src_path]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                return False, result.stderr
            return True, ''
        except subprocess.TimeoutExpired:
            return False, 'Compilation timed out'
        except Exception as e:
            return False, str(e)

    def run(self, sub_dir, in_path, time_limit_ms, memory_limit_kb):
        src_path = os.path.join(sub_dir, 'main.py')
        out_path = os.path.join(sub_dir, 'user.out')
        err_path = os.path.join(sub_dir, 'user.err')
        # Python interpreter needs more memory; use 2x overhead
        adjusted_limit = memory_limit_kb * 2 if memory_limit_kb > 0 else 0
        return run_sandboxed(['python3', src_path], in_path, out_path, err_path,
                             time_limit_ms, adjusted_limit, use_rlimit_as=True)
