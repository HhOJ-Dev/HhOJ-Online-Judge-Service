#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from runners.cpp_runner import CppRunner
from runners.c_runner import CRunner
from runners.csharp_runner import CSharpRunner
from runners.java_runner import JavaRunner
from runners.python_runner import Python3Runner
from runners.pascal_runner import PascalRunner


# ============================================================
# 网站接口客户端（带连接复用 + ETag 缓存）
# ============================================================
class SiteClient:
    def __init__(self, site_url: str, api_key: str, timeout: int = 30):
        self.site_url = site_url.rstrip('/')
        self.api_key = api_key
        self.timeout = timeout
        # 复用 opener：保持 TCP/TLS 连接，减少握手开销
        self.opener = urllib.request.build_opener()
        # ETag 缓存：file_path -> (etag, local_path)
        # 同题目的测试点 mtime 不变时，第二次起返回 304
        self._etag_cache = {}
        self._etag_lock = threading.Lock()

    def _request(self, method: str, path: str, *, json_body=None, stream_to=None, headers_extra=None):
        url = self.site_url + path
        headers = {'X-API-Key': self.api_key, 'User-Agent': 'HhOJ-Judge/2.0'}
        if headers_extra:
            headers.update(headers_extra)
        data = None
        if json_body is not None:
            headers['Content-Type'] = 'application/json'
            data = json.dumps(json_body).encode('utf-8')
        req = urllib.request.Request(url, method=method, headers=headers, data=data)
        try:
            resp = self.opener.open(req, timeout=self.timeout)
            if stream_to is not None:
                with open(stream_to, 'wb') as f:
                    while True:
                        chunk = resp.read(64 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                # 返回响应头供调用方使用（ETag）
                return resp.status, b'', dict(resp.headers)
            return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as e:
            body = e.read() if e.fp else b''
            return e.code, body, dict(e.headers) if e.headers else {}
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            return 0, str(e).encode('utf-8'), {}

    def fetch_submissions(self, batch: int = 5, inline_testcases: bool = True):
        """
        批量拉取 pending 提交。
        :return: (list[dict], queue_size)
        """
        params = [f'batch={batch}']
        if inline_testcases:
            params.append('inline_testcases=1')
        code, body, _ = self._request('GET', '/api/judge_fetch.php?' + '&'.join(params))
        if code != 200:
            print(f'[fetch] HTTP {code} body={body[:200]!r}', flush=True)
            return [], 0
        try:
            data = json.loads(body.decode('utf-8'))
        except Exception as e:
            print(f'[fetch] JSON 解析失败: {e} body={body[:200]!r}', flush=True)
            return [], 0
        if not data.get('success'):
            print(f'[fetch] 接口返回失败: {data}', flush=True)
            return [], 0
        queue_size = int(data.get('queue_size', 0))
        # 兼容单条/批量响应
        if 'submissions' in data:
            return data['submissions'], queue_size
        if data.get('submission'):
            return [data['submission']], queue_size
        return [], queue_size

    def download_file(self, file_path: str, dest: str):
        """
        下载测试点文件到 dest，带 ETag 缓存。
        若服务端返回 304，则使用本地缓存。
        """
        from urllib.parse import quote
        with self._etag_lock:
            cached = self._etag_cache.get(file_path)

        headers_extra = {}
        if cached and os.path.exists(cached[1]):
            headers_extra['If-None-Match'] = cached[0]

        code, _, resp_headers = self._request(
            'GET',
            '/api/judge_download.php?file=' + quote(file_path, safe=''),
            stream_to=dest,
            headers_extra=headers_extra,
        )
        if code == 304 and cached and os.path.exists(cached[1]):
            # 使用本地缓存（已写入 dest 的是 304 空响应，需要复制缓存）
            shutil.copyfile(cached[1], dest)
            return
        if code != 200:
            raise RuntimeError(f'下载失败 HTTP {code}: {file_path}')
        # 缓存 ETag
        etag = resp_headers.get('ETag') or resp_headers.get('Etag')
        if etag:
            with self._etag_lock:
                self._etag_cache[file_path] = (etag, dest)

    def report_batch(self, results: list):
        """
        批量回写评测结果。
        :param results: [{submission_id, status, score, time_used, memory_used, error_message}, ...]
        :return: bool 是否全部成功
        """
        if not results:
            return True
        body = {'results': results}
        code, resp, _ = self._request('POST', '/api/judge_report.php', json_body=body)
        if code != 200:
            print(f'[report_batch] HTTP {code} resp={resp[:200]!r}', flush=True)
            return False
        try:
            data = json.loads(resp.decode('utf-8'))
            return bool(data.get('success'))
        except Exception:
            return False

    def report(self, submission_id: int, status: str, score: int,
               time_used: int, memory_used: int, error_message: str = ''):
        """单条回写（向后兼容）"""
        body = {
            'submission_id': submission_id,
            'status': status,
            'score': score,
            'time_used': time_used,
            'memory_used': memory_used,
            'error_message': error_message,
        }
        code, resp, _ = self._request('POST', '/api/judge_report.php', json_body=body)
        if code != 200:
            print(f'[report] HTTP {code} resp={resp[:200]!r}', flush=True)
            return False
        try:
            data = json.loads(resp.decode('utf-8'))
            return bool(data.get('success'))
        except Exception:
            return False


# ============================================================
# 测试点准备（处理内联 + 下载回退）
# ============================================================
def prepare_testcase_files(client: SiteClient, tc: dict, sub_dir: str, idx: int):
    """
    准备单个测试点的输入/输出文件。
    优先使用内联数据（input_data/output_data），否则走下载网关。
    :return: (in_path, out_path, tc_name)
    """
    tc_name = tc.get('name') or f'#{idx}'
    in_path = os.path.join(sub_dir, f'tc_{idx}.in')
    out_path = os.path.join(sub_dir, f'tc_{idx}.out')

    # 内联模式：直接解码 base64 写文件，零网络请求
    if tc.get('inlined'):
        try:
            with open(in_path, 'wb') as f:
                f.write(base64.b64decode(tc['input_data']))
            with open(out_path, 'wb') as f:
                f.write(base64.b64decode(tc['output_data']))
            return in_path, out_path, tc_name
        except Exception as e:
            raise RuntimeError(f'内联测试点 {tc_name} 解码失败: {e}')

    # 下载模式：从 URL 提取 file 参数
    in_file = tc['input_url'].split('/judge_download.php?file=')[-1]
    out_file = tc['output_url'].split('/judge_download.php?file=')[-1]
    client.download_file(in_file, in_path)
    client.download_file(out_file, out_path)
    return in_path, out_path, tc_name


# ============================================================
# 评测执行
# ============================================================
def get_runner(language: str, work_dir: str):
    """
    根据语言代码返回对应的 runner 实例。
    支持的语言代码（与网站 getProblemLanguages() 对应）：
      c / csharp / cpp11 / cpp11_o2 / cpp14 / cpp14_o2 / cpp23 / cpp23_o2 / python3
    旧别名（向后兼容）：
      cpp → cpp14 + O2
      python → python3
      java / pascal 不变
    """
    lang = (language or '').lower()
    # 旧别名规范化
    alias = {
        'cpp':    'cpp14_o2',
        'python': 'python3',
    }
    lang = alias.get(lang, lang)

    if lang == 'c':
        return CRunner(work_dir)
    if lang == 'csharp':
        return CSharpRunner(work_dir)
    if lang == 'python3':
        return Python3Runner(work_dir)
    if lang == 'java':
        return JavaRunner(work_dir)
    if lang == 'pascal':
        return PascalRunner(work_dir)

    # C++ 各标准 + O2 选项
    cpp_variants = {
        'cpp11':    ('c++11', False),
        'cpp11_o2': ('c++11', True),
        'cpp14':    ('c++14', False),
        'cpp14_o2': ('c++14', True),
        'cpp23':    ('c++23', False),
        'cpp23_o2': ('c++23', True),
    }
    if lang in cpp_variants:
        std, o2 = cpp_variants[lang]
        return CppRunner(work_dir, std=std, o2=o2)

    return None


def compare_output(actual: str, expected: str) -> bool:
    """忽略行末空格与文末空行的标准 OJ 比较"""
    def normalize(s: str) -> list:
        lines = s.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        lines = [line.rstrip() for line in lines]
        while lines and lines[-1] == '':
            lines.pop()
        return lines
    return normalize(actual) == normalize(expected)


def judge_one(client: SiteClient, submission: dict, work_dir: str,
              tc_workers: int = 1) -> dict:
    """
    评测单条提交。
    :param tc_workers: 单条提交内测试点并行数（建议 1-4）
    """
    sub_id = submission['id']
    code = submission['code']
    language = submission['language']
    time_limit_ms = int(submission.get('time_limit', 1000))
    memory_limit_kb = int(submission.get('memory_limit', 256)) * 1024
    testcases = submission.get('testcases', [])

    print(f'[judge] 开始 #{sub_id} lang={language} tcs={len(testcases)} tc_workers={tc_workers}', flush=True)

    runner = get_runner(language, work_dir)
    if runner is None:
        return {'status': 'ce', 'score': 0, 'time_used': 0, 'memory_used': 0,
                'error_message': f'不支持的语言: {language}'}

    sub_dir = os.path.join(work_dir, f'sub_{sub_id}')
    if os.path.exists(sub_dir):
        shutil.rmtree(sub_dir, ignore_errors=True)
    os.makedirs(sub_dir, exist_ok=True)

    # 1. 编译
    compile_ok, compile_error = runner.compile(code, sub_dir)
    if not compile_ok:
        if len(compile_error) > 4000:
            compile_error = compile_error[:4000] + '\n...(已截断)'
        shutil.rmtree(sub_dir, ignore_errors=True)
        return {'status': 'ce', 'score': 0, 'time_used': 0, 'memory_used': 0,
                'error_message': compile_error}

    # 2. 准备所有测试点文件（并行下载/解码）
    prepared = []
    for idx, tc in enumerate(testcases, 1):
        try:
            in_path, out_path, tc_name = prepare_testcase_files(client, tc, sub_dir, idx)
            prepared.append((idx, tc_name, tc, in_path, out_path))
        except Exception as e:
            print(f'[judge] #{sub_id} tc#{idx} 文件准备失败: {e}', flush=True)
            prepared.append((idx, tc.get('name') or f'#{idx}', tc, None, None))

    # 3. 串行/并行运行测试点（带提前终止）
    # 策略：
    #   - TLE/MLE 立即终止（同算法必超时/超内存）
    #   - WA 不立即终止，继续后续测试点（不同 case 可能得分）
    #   - RE 继续后续测试点
    total_score = 0
    got_score = 0
    max_time = 0
    max_memory = 0
    first_failure = None
    early_terminated = False

    for idx, tc_name, tc, in_path, out_path in prepared:
        if early_terminated:
            # 跳过剩余测试点（但仍要计入 total_score 以计算部分分）
            total_score += int(tc.get('score', 0))
            continue

        tc_score = int(tc.get('score', 0))
        total_score += tc_score

        if in_path is None:
            if first_failure is None:
                first_failure = ('re', f'测试点 {tc_name} 文件准备失败')
            continue

        run_result = runner.run(sub_dir, in_path, time_limit_ms, memory_limit_kb)

        if run_result['time_ms'] > max_time:
            max_time = run_result['time_ms']
        if run_result['memory_kb'] > max_memory:
            max_memory = run_result['memory_kb']

        if run_result['status'] == 'tle':
            if first_failure is None:
                first_failure = ('tle', f'测试点 {tc_name} 超时')
            print(f'[judge] #{sub_id} tc#{idx} TLE ({run_result["time_ms"]}ms) - 提前终止', flush=True)
            early_terminated = True
            continue
        if run_result['status'] == 'mle':
            if first_failure is None:
                first_failure = ('mle', f'测试点 {tc_name} 内存超限')
            print(f'[judge] #{sub_id} tc#{idx} MLE ({run_result["memory_kb"]}KB) - 提前终止', flush=True)
            early_terminated = True
            continue
        if run_result['status'] == 're':
            if first_failure is None:
                first_failure = ('re', f'测试点 {tc_name} 运行错误: {run_result.get("error", "")}')
            print(f'[judge] #{sub_id} tc#{idx} RE: {run_result.get("error", "")[:80]}', flush=True)
            continue

        # 比对输出
        try:
            with open(out_path, 'rb') as f:
                expected = f.read().decode('utf-8', errors='replace')
            actual = run_result['output'].decode('utf-8', errors='replace')
        except Exception as e:
            if first_failure is None:
                first_failure = ('re', f'测试点 {tc_name} 读取答案失败: {e}')
            continue

        if compare_output(actual, expected):
            got_score += tc_score
            print(f'[judge] #{sub_id} tc#{idx} AC', flush=True)
        else:
            if first_failure is None:
                first_failure = ('wrong', f'测试点 {tc_name} 答案错误')
            print(f'[judge] #{sub_id} tc#{idx} WA', flush=True)
            # WA 不提前终止，继续后续测试点争取部分分

    shutil.rmtree(sub_dir, ignore_errors=True)

    if first_failure is None:
        return {'status': 'accepted', 'score': 100, 'time_used': max_time,
                'memory_used': max_memory, 'error_message': ''}

    score_pct = int(round(got_score * 100 / total_score)) if total_score > 0 else 0
    return {
        'status': first_failure[0],
        'score': score_pct,
        'time_used': max_time,
        'memory_used': max_memory,
        'error_message': first_failure[1],
    }


# ============================================================
# 并行评测
# ============================================================
def judge_batch_parallel(client: SiteClient, submissions: list, work_dir: str,
                         workers: int = 2, tc_workers: int = 1) -> list:
    """
    并行评测多条提交。
    :return: [(submission, result), ...]
    """
    if len(submissions) <= 1 or workers <= 1:
        return [(s, judge_one(client, s, work_dir, tc_workers)) for s in submissions]

    results = [None] * len(submissions)

    def _worker(idx, sub):
        try:
            return idx, sub, judge_one(client, sub, work_dir, tc_workers)
        except Exception as e:
            import traceback
            print(f'[judge] #{sub.get("id")} 异常: {e}\n{traceback.format_exc()}', flush=True)
            return idx, sub, {
                'status': 're', 'score': 0, 'time_used': 0, 'memory_used': 0,
                'error_message': f'评测机内部错误: {type(e).__name__}: {str(e)[:500]}',
            }

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = [ex.submit(_worker, i, s) for i, s in enumerate(submissions)]
        for fut in as_completed(futures):
            idx, sub, result = fut.result()
            results[idx] = (sub, result)

    return results


# ============================================================
# 主循环
# ============================================================
def main():
    parser = argparse.ArgumentParser(description='HhOJ 评测机 v3.0')
    parser.add_argument('--site-url', required=True, help='网站地址')
    parser.add_argument('--api-key', required=True, help='API Key')
    parser.add_argument('--work-dir', required=True, help='工作目录')
    parser.add_argument('--max-submissions', type=int, default=0,
                        help='本次最多评测数（0=不限）')
    parser.add_argument('--batch-size', type=int, default=5,
                        help='每次 fetch 拉取的提交数（1-20）')
    parser.add_argument('--workers', type=int, default=2,
                        help='提交级并行线程数（建议 1-4）')
    parser.add_argument('--tc-workers', type=int, default=1,
                        help='单提交测试点并行数（建议 1，IO 多时可提高）')
    parser.add_argument('--idle-wait-min', type=int, default=5,
                        help='队列空时最小等待秒数')
    parser.add_argument('--idle-wait-max', type=int, default=60,
                        help='队列空时最大等待秒数（指数退避上限）')
    parser.add_argument('--max-idle', type=int, default=3,
                        help='连续空轮询退出阈值')
    parser.add_argument('--max-errors', type=int, default=10,
                        help='连续错误上限')
    args = parser.parse_args()

    if not args.site_url or not args.api_key:
        print('ERROR: --site-url 和 --api-key 必填', flush=True)
        sys.exit(2)

    os.makedirs(args.work_dir, exist_ok=True)
    client = SiteClient(args.site_url, args.api_key)

    judged_count = 0
    error_streak = 0
    idle_streak = 0

    print('=== HhOJ 评测机 v3.0 启动 ===', flush=True)
    print(f'网站: {args.site_url}', flush=True)
    print(f'批量: {args.batch_size}  并行: {args.workers}  tc并行: {args.tc_workers}', flush=True)
    print(f'退避: {args.idle_wait_min}-{args.idle_wait_max}s  空轮上限: {args.max_idle}', flush=True)
    print(flush=True)

    while True:
        if args.max_submissions > 0 and judged_count >= args.max_submissions:
            print(f'已达上限 {args.max_submissions}，退出', flush=True)
            break

        # 批量拉取
        try:
            submissions, queue_size = client.fetch_submissions(
                batch=args.batch_size, inline_testcases=True,
            )
        except Exception as e:
            error_streak += 1
            print(f'[fetch] 异常: {e} (连续 {error_streak}/{args.max_errors})', flush=True)
            if error_streak >= args.max_errors:
                print(f'连续 {args.max_errors} 次错误，退出', flush=True)
                sys.exit(1)
            time.sleep(min(args.idle_wait_max, args.idle_wait_min * (2 ** (error_streak - 1))))
            continue

        if not submissions:
            idle_streak += 1
            error_streak = 0
            if idle_streak >= args.max_idle:
                print(f'连续 {args.max_idle} 次无 pending，退出', flush=True)
                break
            # 指数退避：5s, 10s, 20s, ..., 60s
            wait = min(args.idle_wait_max, args.idle_wait_min * (2 ** (idle_streak - 1)))
            print(f'队列空 (剩 {queue_size})，等待 {wait}s (空轮 {idle_streak}/{args.max_idle})', flush=True)
            time.sleep(wait)
            continue

        idle_streak = 0
        error_streak = 0
        print(f'[fetch] 拉取 {len(submissions)} 条，队列剩 {queue_size}', flush=True)

        # 并行评测
        results = judge_batch_parallel(client, submissions, args.work_dir,
                                       args.workers, args.tc_workers)

        # 批量回写（一次 HTTP 请求回写所有结果，减少 RTT）
        report_payload = []
        for sub, result in results:
            report_payload.append({
                'submission_id': sub['id'],
                'status': result['status'],
                'score': result['score'],
                'time_used': result['time_used'],
                'memory_used': result['memory_used'],
                'error_message': result['error_message'],
            })
            judged_count += 1
            label = {'accepted': 'AC', 'wrong': 'WA', 'tle': 'TLE', 'mle': 'MLE',
                     're': 'RE', 'ce': 'CE'}.get(result['status'], result['status'])
            print(f'[done] #{sub["id"]} → {label} score={result["score"]} '
                  f'time={result["time_used"]}ms mem={result["memory_used"]}KB', flush=True)

        try:
            ok = client.report_batch(report_payload)
            if not ok:
                error_streak += 1
                print(f'[report_batch] 失败 (连续 {error_streak}/{args.max_errors})', flush=True)
        except Exception as e:
            error_streak += 1
            print(f'[report_batch] 异常: {e} (连续 {error_streak}/{args.max_errors})', flush=True)

        if error_streak >= args.max_errors:
            print(f'连续 {args.max_errors} 次错误，退出', flush=True)
            sys.exit(1)

        print(flush=True)

    print(f'=== 结束，共评测 {judged_count} 条 ===', flush=True)


if __name__ == '__main__':
    main()
