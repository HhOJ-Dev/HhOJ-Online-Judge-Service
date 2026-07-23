import os
import subprocess
from runners._common import run_sandboxed

class CSharpRunner:
    def __init__(self):
        pass

    def compile(self, code, sub_dir):
        src_path = os.path.join(sub_dir, 'main.cs')
        exe_path = os.path.join(sub_dir, 'main.exe')

        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(code)

        cmd = ['csc', '/out:' + exe_path, src_path]

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
        except FileNotFoundError:
            try:
                cmd2 = ['mcs', '-out:' + exe_path, src_path]
                result = subprocess.run(
                    cmd2,
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    return False, result.stderr
                return True, ''
            except Exception as e:
                return False, str(e)
        except Exception as e:
            return False, str(e)

    def run(self, sub_dir, in_path, time_limit_ms, memory_limit_kb):
        exe_path = os.path.join(sub_dir, 'main.exe')
        out_path = os.path.join(sub_dir, 'user.out')
        err_path = os.path.join(sub_dir, 'user.err')
        # Mono reserves large virtual address space; use RLIMIT_DATA with 2x overhead
        adjusted_limit = memory_limit_kb * 2 if memory_limit_kb > 0 else 0
        return run_sandboxed(['mono', exe_path], in_path, out_path, err_path,
                             time_limit_ms, adjusted_limit, use_rlimit_as=False)
