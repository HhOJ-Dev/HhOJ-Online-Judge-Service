import os
import subprocess
import time

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

        time_limit_s = time_limit_ms / 1000.0

        try:
            with open(in_path, 'r', encoding='utf-8') as fin, \
                 open(out_path, 'w', encoding='utf-8') as fout, \
                 open(err_path, 'w', encoding='utf-8') as ferr:

                start_time = time.time()
                proc = subprocess.Popen(
                    ['mono', exe_path],
                    stdin=fin,
                    stdout=fout,
                    stderr=ferr
                )

                try:
                    proc.wait(timeout=time_limit_s)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                    return 'TLE', 0, 0

                elapsed_ms = int((time.time() - start_time) * 1000)

                if proc.returncode != 0:
                    return 'RE', elapsed_ms, 0

                return 'OK', elapsed_ms, 0

        except Exception as e:
            return 'RE', 0, 0
