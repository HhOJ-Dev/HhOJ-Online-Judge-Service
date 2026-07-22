import os
import subprocess
from runners._common import run_sandboxed

class CRunner:
    def __init__(self):
        pass

    def compile(self, code, sub_dir):
        src_path = os.path.join(sub_dir, 'main.c')
        exe_path = os.path.join(sub_dir, 'main')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        cmd = ['gcc', '-O2', '-std=c11', src_path, '-o', exe_path]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                return False, result.stderr
            os.chmod(exe_path, 0o755)
            return True, ''
        except subprocess.TimeoutExpired:
            return False, 'Compilation timed out'
        except Exception as e:
            return False, str(e)

    def run(self, sub_dir, in_path, time_limit_ms, memory_limit_kb):
        exe_path = os.path.join(sub_dir, 'main')
        out_path = os.path.join(sub_dir, 'user.out')
        err_path = os.path.join(sub_dir, 'user.err')
        return run_sandboxed([exe_path], in_path, out_path, err_path,
                             time_limit_ms, memory_limit_kb, use_rlimit_as=True)
