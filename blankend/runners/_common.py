import os
import signal
import time
import resource
import subprocess


def make_preexec(memory_limit_kb, cpu_limit_s=0, use_rlimit_as=True):
    def preexec():
        if cpu_limit_s > 0:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_s, cpu_limit_s + 1))

        if memory_limit_kb and memory_limit_kb > 0:
            limit_bytes = memory_limit_kb * 1024
            if use_rlimit_as:
                resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
            else:
                resource.setrlimit(resource.RLIMIT_DATA, (limit_bytes, limit_bytes))

        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return preexec


def run_sandboxed(cmd, in_path, out_path, err_path, time_limit_ms, memory_limit_kb, use_rlimit_as=True):
    time_limit_s = time_limit_ms / 1000.0
    cpu_limit = int(time_limit_s) + 2
    preexec = make_preexec(memory_limit_kb, cpu_limit, use_rlimit_as)

    try:
        with open(in_path, 'rb') as fin, \
             open(out_path, 'wb') as fout, \
             open(err_path, 'wb') as ferr:

            proc = subprocess.Popen(
                cmd,
                stdin=fin,
                stdout=fout,
                stderr=ferr,
                preexec_fn=preexec,
                start_new_session=True
            )

            start_time = time.time()

            pid, status, rusage = os.wait4(proc.pid, os.WNOHANG)
            while pid == 0:
                elapsed = time.time() - start_time
                if elapsed > time_limit_s:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    return 'TLE', int(elapsed * 1000), 0
                time.sleep(0.005)
                pid, status, rusage = os.wait4(proc.pid, os.WNOHANG)

            elapsed_ms = int((time.time() - start_time) * 1000)

            memory_kb = 0
            if rusage is not None:
                memory_kb = rusage.ru_maxrss
            else:
                memory_kb = int(proc.poll() or 0)

            if os.WIFSIGNALED(status):
                sig = os.WTERMSIG(status)
                if sig == signal.SIGXCPU:
                    return 'TLE', elapsed_ms, memory_kb
                if sig in (signal.SIGKILL, signal.SIGTERM):
                    if elapsed_ms < time_limit_s * 950:
                        return 'MLE', elapsed_ms, memory_kb
                    return 'TLE', elapsed_ms, memory_kb
                return 'RE', elapsed_ms, memory_kb

            if os.WIFEXITED(status):
                exit_code = os.WEXITSTATUS(status)
                if exit_code != 0:
                    return 'RE', elapsed_ms, memory_kb

            return 'OK', elapsed_ms, memory_kb

    except FileNotFoundError:
        return 'RE', 0, 0
    except PermissionError:
        return 'RE', 0, 0
    except Exception:
        return 'RE', 0, 0
