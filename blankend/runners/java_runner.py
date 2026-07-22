import os
import subprocess
from runners._common import run_sandboxed

class JavaRunner:
    def __init__(self):
        pass

    def compile(self, code, sub_dir):
        src_path = os.path.join(sub_dir, 'Main.java')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        cmd = ['javac', src_path]

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
        out_path = os.path.join(sub_dir, 'user.out')
        err_path = os.path.join(sub_dir, 'user.err')
        # JVM reserves large virtual address space; use RLIMIT_DATA with 3x overhead
        adjusted_limit = memory_limit_kb * 3 if memory_limit_kb > 0 else 0
        return run_sandboxed(['java', '-cp', sub_dir, 'Main'], in_path, out_path, err_path,
                             time_limit_ms, adjusted_limit, use_rlimit_as=False)
