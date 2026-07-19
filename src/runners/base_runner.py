# -*- coding: utf-8 -*-
"""
BaseRunner v3: 精确资源测量 + 测试点并行运行 + 兼容性回退
============================================================
v3 优化（修复 v2 的 /usr/bin/time 不存在导致全 WA 的 bug）：
  1. 类初始化时检测 /usr/bin/time 是否存在且支持 -v（只检测一次，缓存结果）
  2. 两条运行路径：
     - 有 GNU time：用 `setsid /usr/bin/time -v cmd` 精确测量内存峰值
     - 无 GNU time：用 subprocess 直接执行 + Python resource 模块在子进程
       退出后读 RUSAGE_CHILDREN 测量峰值内存（粗略但可用）
  3. 内存限制统一用 ulimit -v（虚拟内存），CPU 秒数用 ulimit -t
  4. 进程隔离：setsid + 进程组 SIGKILL，超时子进程不残留
  5. 输出捕获：stdout 全量 + stderr 截断（错误信息只用于 RE 提示）
  6. run_batch 并行运行同一提交的多个测试点，每个线程独立 err 文件

返回格式：
  {
    'status': 'ok'|'tle'|'mle'|'re',
    'time_ms': int,        # wall-clock 时间（ms）
    'memory_kb': int,      # 峰值内存（KB）
    'output': bytes,       # 标准输出
    'error': str,          # 错误信息（仅 re 时）
  }
"""
import os
import shutil
import signal
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor

try:
    import resource
    _HAS_RESOURCE = True
except ImportError:
    _HAS_RESOURCE = False


class BaseRunner:
    """runner 基类"""

    # 类级缓存：检测 /usr/bin/time 是否可用，避免每次 run 都 stat
    _time_bin_checked = False
    _time_bin_available = False

    def __init__(self, work_dir: str):
        self.work_dir = work_dir
        # 首次实例化时检测一次 /usr/bin/time
        if not BaseRunner._time_bin_checked:
            BaseRunner._time_bin_available = self._detect_gnu_time()
            BaseRunner._time_bin_checked = True

    @staticmethod
    def _detect_gnu_time() -> bool:
        """
        检测 /usr/bin/time 是否存在且是 GNU time（支持 -v 标志）。
        bash 内建的 time 不支持 -v，会报错，必须排除。
        """
        candidates = ['/usr/bin/time', '/bin/time']
        for cand in candidates:
            if not os.path.exists(cand) or not os.access(cand, os.X_OK):
                continue
            try:
                # 用 --version 探测，GNU time 输出 "GNU time ..."，BSD time 无此选项
                r = subprocess.run(
                    [cand, '--version'],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    timeout=3,
                )
                if r.returncode == 0:
                    return True
                # 某些 GNU time 把版本输出到 stderr
                err = r.stderr.decode('utf-8', errors='replace').lower()
                if 'gnu time' in err or 'freebsd' not in err and 'usage' not in err:
                    # 简单兜底：调用 -v 看是否能跑通（用一个 true 命令）
                    test = subprocess.run(
                        [cand, '-v', 'true'],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        timeout=3,
                    )
                    if test.returncode == 0:
                        return True
            except Exception:
                continue
        return False

    def compile(self, code: str, sub_dir: str):
        """
        编译代码。
        :return: (success: bool, error_message: str)
        """
        raise NotImplementedError

    def _build_run_cmd(self, sub_dir: str):
        """返回运行命令（list）。"""
        raise NotImplementedError

    def run(self, sub_dir: str, input_file: str, time_limit_ms: int, memory_limit_kb: int) -> dict:
        """运行单个测试点（详见模块文档）"""
        try:
            cmd = self._build_run_cmd(sub_dir)
        except Exception as e:
            return {'status': 're', 'time_ms': 0, 'memory_kb': 0,
                    'output': b'', 'error': f'构建运行命令失败: {e}'}

        try:
            with open(input_file, 'rb') as f:
                stdin_data = f.read()
        except Exception as e:
            return {'status': 're', 'time_ms': 0, 'memory_kb': 0,
                    'output': b'', 'error': f'读取输入失败: {e}'}

        # 两条运行路径：有 GNU time 走精确测量，没有走直接执行
        if BaseRunner._time_bin_available:
            return self._run_with_gnu_time(cmd, sub_dir, stdin_data,
                                           time_limit_ms, memory_limit_kb)
        return self._run_plain(cmd, sub_dir, stdin_data,
                               time_limit_ms, memory_limit_kb)

    # ------------------------------------------------------------
    # 路径 A：GNU time 精确测量（推荐）
    # ------------------------------------------------------------
    def _run_with_gnu_time(self, cmd, sub_dir, stdin_data,
                           time_limit_ms: int, memory_limit_kb: int) -> dict:
        """用 /usr/bin/time -v 精确测量内存峰值"""
        time_bin = '/usr/bin/time'
        # 线程 ID 后缀：run_batch 并行时各线程独立 err 文件
        time_err_file = f'/tmp/judge_time_{os.getpid()}_{threading.get_ident()}.err'

        wrapper = [
            'bash', '-c',
            'ulimit -v {mem}; ulimit -t {cpu_sec}; '
            'exec setsid {time_bin} -v {cmd} 2> {err_file}'
            .format(
                mem=int(memory_limit_kb),
                cpu_sec=max(1, int(time_limit_ms / 1000) + 2),
                time_bin=time_bin,
                err_file=time_err_file,
                cmd=' '.join(self._shell_escape(c) for c in cmd),
            )
        ]

        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                wrapper,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=sub_dir,
                start_new_session=True,
            )
        except Exception as e:
            self._cleanup_file(time_err_file)
            return {'status': 're', 'time_ms': 0, 'memory_kb': 0,
                    'output': b'', 'error': f'启动失败: {e}'}

        timeout_sec = time_limit_ms / 1000.0
        kill_after_sec = timeout_sec + 2.0

        try:
            out, err = proc.communicate(input=stdin_data, timeout=kill_after_sec)
        except subprocess.TimeoutExpired:
            self._kill_proc(proc)
            try:
                out, err = proc.communicate(timeout=2)
            except Exception:
                out, err = b'', b''
            elapsed_ms = int((time.monotonic() - start) * 1000)
            self._cleanup_file(time_err_file)
            return {'status': 'tle', 'time_ms': elapsed_ms, 'memory_kb': 0,
                    'output': out or b'', 'error': ''}

        elapsed_ms = int((time.monotonic() - start) * 1000)
        mem_kb = self._read_time_memory(time_err_file)

        return self._build_result(proc.returncode, out, err, elapsed_ms, mem_kb)

    # ------------------------------------------------------------
    # 路径 B：直接执行（GNU time 不可用时回退）
    # ------------------------------------------------------------
    def _run_plain(self, cmd, sub_dir, stdin_data,
                   time_limit_ms: int, memory_limit_kb: int) -> dict:
        """
        直接用 subprocess.Popen 执行，不依赖 /usr/bin/time。
        内存测量：用 Python resource.RUSAGE_CHILDREN 取子进程峰值（粗略），
                  资源限制：ulimit -v / ulimit -t。
        """
        # 在 bash wrapper 里设置 ulimit，确保子进程受限
        wrapper = [
            'bash', '-c',
            'ulimit -v {mem} 2>/dev/null; ulimit -t {cpu_sec}; '
            'exec {cmd}'
            .format(
                mem=int(memory_limit_kb),
                cpu_sec=max(1, int(time_limit_ms / 1000) + 2),
                cmd=' '.join(self._shell_escape(c) for c in cmd),
            )
        ]

        # 记录调用前的 children 内存峰值，差值即本次运行的近似峰值
        prev_max_rss = 0
        if _HAS_RESOURCE:
            try:
                prev_max_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
            except Exception:
                prev_max_rss = 0

        start = time.monotonic()
        try:
            proc = subprocess.Popen(
                wrapper,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=sub_dir,
                start_new_session=True,
            )
        except Exception as e:
            return {'status': 're', 'time_ms': 0, 'memory_kb': 0,
                    'output': b'', 'error': f'启动失败: {e}'}

        timeout_sec = time_limit_ms / 1000.0
        kill_after_sec = timeout_sec + 2.0

        try:
            out, err = proc.communicate(input=stdin_data, timeout=kill_after_sec)
        except subprocess.TimeoutExpired:
            self._kill_proc(proc)
            try:
                out, err = proc.communicate(timeout=2)
            except Exception:
                out, err = b'', b''
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return {'status': 'tle', 'time_ms': elapsed_ms, 'memory_kb': 0,
                    'output': out or b'', 'error': ''}

        elapsed_ms = int((time.monotonic() - start) * 1000)

        # 估算内存：取 RUSAGE_CHILDREN.ru_maxrss 的增量
        # 注意：ru_maxrss 是累积最大值，不是单次进程值，仅作近似
        mem_kb = 0
        if _HAS_RESOURCE:
            try:
                cur_max_rss = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
                # Linux 上单位是 KB，macOS 上是字节；GitHub Actions 是 Linux
                mem_kb = max(0, cur_max_rss - prev_max_rss)
                # 如果本次比之前还小（不可能但保险），就用当前值
                if mem_kb == 0 and cur_max_rss > 0:
                    mem_kb = cur_max_rss
            except Exception:
                mem_kb = 0

        return self._build_result(proc.returncode, out, err, elapsed_ms, mem_kb)

    # ------------------------------------------------------------
    # 共用结果构造
    # ------------------------------------------------------------
    def _build_result(self, ret: int, out: bytes, err: bytes,
                      elapsed_ms: int, mem_kb: int) -> dict:
        """根据返回码构造结果字典"""
        if ret == 0:
            return {'status': 'ok', 'time_ms': elapsed_ms, 'memory_kb': mem_kb,
                    'output': out, 'error': ''}

        # 信号退出
        if ret < 0 or ret > 128:
            sig = -ret if ret < 0 else (ret - 128)
            sig_name = self._signal_name(sig)
            err_text = err.decode('utf-8', errors='replace') if err else ''
            return {'status': 're', 'time_ms': elapsed_ms, 'memory_kb': mem_kb,
                    'output': out, 'error': f'程序异常退出（信号 {sig_name}）' + (f': {err_text[:200]}' if err_text else '')}

        err_text = err.decode('utf-8', errors='replace') if err else ''
        return {'status': 're', 'time_ms': elapsed_ms, 'memory_kb': mem_kb,
                'output': out, 'error': f'退出码 {ret}' + (f': {err_text[:200]}' if err_text else '')}

    def run_batch(self, sub_dir: str, testcases: list, time_limit_ms: int,
                  memory_limit_kb: int, workers: int = 1) -> list:
        """
        并行运行同一提交的多个测试点。
        :param testcases: [(idx, in_path), ...]
        :return: [{'idx': int, 'result': dict}, ...] 保持原顺序
        """
        if workers <= 1 or len(testcases) <= 1:
            return [{'idx': idx, 'result': self.run(sub_dir, in_path, time_limit_ms, memory_limit_kb)}
                    for idx, in_path in testcases]

        results = [None] * len(testcases)

        def _worker(i, idx, in_path):
            return i, {'idx': idx, 'result': self.run(sub_dir, in_path, time_limit_ms, memory_limit_kb)}

        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(_worker, i, idx, in_path) for i, (idx, in_path) in enumerate(testcases)]
            for fut in futures:
                i, r = fut.result()
                results[i] = r
        return results

    def _read_time_memory(self, path: str) -> int:
        """读取 /usr/bin/time -v 输出中的峰值内存（KB）"""
        try:
            with open(path, 'r', errors='replace') as f:
                for line in f:
                    if 'Maximum resident set size' in line:
                        # "Maximum resident set size (kbytes): 1234"
                        parts = line.split(':')
                        if len(parts) >= 2:
                            return int(parts[-1].strip())
        except Exception:
            pass
        finally:
            self._cleanup_file(path)
        return 0

    @staticmethod
    def _cleanup_file(path: str):
        try:
            os.unlink(path)
        except Exception:
            pass

    @staticmethod
    def _kill_proc(proc):
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    @staticmethod
    def _shell_escape(s: str) -> str:
        return "'" + s.replace("'", "'\"'\"'") + "'"

    @staticmethod
    def _signal_name(sig: int) -> str:
        names = {
            1: 'SIGHUP', 2: 'SIGINT', 3: 'SIGQUIT', 4: 'SIGILL', 6: 'SIGABRT',
            8: 'SIGFPE', 9: 'SIGKILL', 11: 'SIGSEGV', 13: 'SIGPIPE',
            14: 'SIGALRM', 15: 'SIGTERM',
        }
        return names.get(sig, f'SIG{sig}')

    @staticmethod
    def write_file(path: str, content: str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
