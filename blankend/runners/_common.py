import os
import signal
import time
import resource
import subprocess


def make_preexec(memory_limit_kb, cpu_limit_s=0, use_rlimit_as=True):
    """Create a preexec_fn that sets resource limits for the child process."""
    def preexec():
        # CPU time limit (seconds)
        if cpu_limit_s > 0:
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit_s, cpu_limit_s + 1))

        # Memory limit
        if memory_limit_kb and memory_limit_kb > 0:
            limit_bytes = memory_limit_kb * 1024
            if use_rlimit_as:
                resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
            else:
                # Java/Mono: RLIMIT_DATA instead of RLIMIT_AS
                # (JVM/Mono reserve large virtual address spaces)
                resource.setrlimit(resource.RLIMIT_DATA, (limit_bytes, limit_bytes))

        # Max file size: 64MB
        resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))

        # Max open file descriptors
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))

        # Disable core dumps
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return preexec


def run_sandboxed(cmd, in_path, out_path, err_path, time_limit_ms, memory_limit_kb, use_rlimit_as=True):
    """Run a command with sandboxing.

    Returns (status_str, time_ms, memory_kb) where status_str is one of:
    'OK', 'TLE', 'MLE', 'RE'

    Security:
    - start_new_session=True + os.killpg: kills entire process group on timeout
    - RLIMIT_CPU: prevents CPU spin bombs
    - RLIMIT_AS/RLIMIT_DATA: memory limit
    - RLIMIT_FSIZE: max output file size
    - RLIMIT_NOFILE: max open file descriptors
    - RLIMIT_CORE: no core dumps
    """
    time_limit_s = time_limit_ms / 1000.0
    cpu_limit = int(time_limit_s) + 2  # CPU seconds = wall time + 2s grace
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
                start_new_session=True  # New process group for killpg
            )

            start_time = time.time()

            # Poll with os.wait4 for per-child rusage (accurate memory)
            pid, status, rusage = os.wait4(proc.pid, os.WNOHANG)
            while pid == 0:
                elapsed = time.time() - start_time
                if elapsed > time_limit_s:
                    # Kill entire process group (catches forked children)
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()
                    return 'TLE', int(elapsed * 1000), 0
                time.sleep(0.005)  # 5ms poll interval
                pid, status, rusage = os.wait4(proc.pid, os.WNOHANG)

            elapsed_ms = int((time.time() - start_time) * 1000)
            memory_kb = rusage.ru_maxrss  # Peak RSS in KB (Linux)

            if os.WIFSIGNALED(status):
                sig = os.WTERMSIG(status)
                if sig == signal.SIGXCPU:
                    return 'TLE', elapsed_ms, memory_kb
                if sig in (signal.SIGKILL, signal.SIGTERM):
                    # MLE (OOM killer) if killed before time limit, TLE otherwise
                    if elapsed_ms < time_limit_s * 950:
                        return 'MLE', elapsed_ms, memory_kb
                    return 'TLE', elapsed_ms, memory_kb
                return 'RE', elapsed_ms, memory_kb

            if os.WIFEXITED(status) and os.WEXITSTATUS(status) != 0:
                return 'RE', elapsed_ms, memory_kb

            return 'OK', elapsed_ms, memory_kb

    except Exception:
        return 'RE', 0, 0
