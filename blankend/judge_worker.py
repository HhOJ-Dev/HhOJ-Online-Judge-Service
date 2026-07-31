#!/usr/bin/env python3
"""
Persistent Judge Worker — continuously polls backend for pending submissions,
judges them immediately, and reports results back.

This eliminates the GitHub Actions cold-start overhead (~15-20s), reducing
total latency from ~30s to ~2-3s.

Usage:
    python3 judge_worker.py --host http://localhost:3000 --api-key YOUR_KEY
    python3 judge_worker.py --host http://localhost:3000 --api-key YOUR_KEY --poll-interval 100
"""

import os
import sys
import json
import time
import signal
import argparse
import hashlib
import base64
import requests
from urllib.parse import urlparse

# Reuse existing judge infrastructure
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from runners import get_runner

RESULT_AC = 'AC'
RESULT_WA = 'WA'
RESULT_TLE = 'TLE'
RESULT_MLE = 'MLE'
RESULT_RE = 'RE'
RESULT_CE = 'CE'
RESULT_UKE = 'UKE'

STATUS_TO_HHOJ = {
    RESULT_AC: 'accepted',
    RESULT_WA: 'wrong',
    RESULT_TLE: 'tle',
    RESULT_MLE: 'mle',
    RESULT_RE: 're',
    RESULT_CE: 'ce',
    RESULT_UKE: 're',
}


class JudgeWorker:
    def __init__(self, host, api_key, poll_interval=100, work_dir='./judge_work'):
        self.host = host.rstrip('/')
        self.api_key = api_key
        self.poll_interval = poll_interval / 1000.0  # Convert ms to seconds
        self.work_dir = os.path.abspath(work_dir)
        self.cache_dir = os.path.join(self.work_dir, 'tc_cache')
        self.running = True
        self.session = self._create_session()

        os.makedirs(self.work_dir, exist_ok=True)
        os.makedirs(self.cache_dir, exist_ok=True)

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        print(f"\n[JudgeWorker] Received signal {signum}, shutting down...", file=sys.stderr)
        self.running = False

    def _create_session(self):
        session = requests.Session()
        session.headers.update({
            'X-API-Key': self.api_key,
            'User-Agent': 'HhOJ-JudgeWorker/1.0',
            'Accept': 'application/json',
        })
        # Set reasonable timeouts
        session.timeout = (5, 15)  # (connect, read)
        return session

    def _fetch_submissions(self, batch=1):
        """Fetch pending submissions from backend."""
        try:
            resp = self.session.get(
                f"{self.host}/api/judge_fetch.php",
                params={'batch': batch, 'inline_testcases': 1},
                timeout=5
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
            if not data.get('success'):
                return []
            return data.get('submissions', [])
        except Exception as e:
            print(f"[JudgeWorker] Fetch error: {e}", file=sys.stderr)
            return []

    def _report_results(self, results):
        """Report judge results back to backend."""
        payload = {'results': [{
            'submission_id': r['submission_id'],
            'status': STATUS_TO_HHOJ.get(r['status'], 're'),
            'score': r['score'],
            'time_used': r['time_used'],
            'memory_used': r['memory_used'],
            'error_message': r.get('error_message', '')[:5000]
        } for r in results]}

        try:
            resp = self.session.post(
                f"{self.host}/api/judge_report.php",
                json=payload,
                timeout=5
            )
            return resp.status_code == 200
        except Exception as e:
            print(f"[JudgeWorker] Report error: {e}", file=sys.stderr)
            return False

    def _judge_submission(self, submission):
        """Judge a single submission (adapted from judge.py)."""
        sub_id = submission.get('id', 'unknown')
        language = submission.get('language', '')
        code = submission.get('code', '')
        testcases = submission.get('testcases') or []
        time_limit = submission.get('time_limit', 1000)
        memory_limit = submission.get('memory_limit', 256)

        sub_dir = os.path.join(self.work_dir, f"sub_{sub_id}")
        os.makedirs(sub_dir, exist_ok=True)

        result = {
            'submission_id': sub_id,
            'status': RESULT_UKE,
            'score': 0,
            'time_used': 0,
            'memory_used': 0,
            'error_message': '',
            'testcases': []
        }

        if not code:
            result['status'] = RESULT_CE
            result['error_message'] = 'Empty source code'
            return result

        try:
            runner = get_runner(language)
        except ValueError as e:
            result['status'] = RESULT_CE
            result['error_message'] = str(e)
            return result

        compile_ok, compile_error = runner.compile(code, sub_dir)
        if not compile_ok:
            result['status'] = RESULT_CE
            result['error_message'] = compile_error[:5000]
            return result

        total_score = 0
        max_score = sum(tc.get('score', 10) for tc in testcases) if testcases else 100
        if max_score == 0:
            max_score = 100

        max_time = 0
        max_memory = 0
        stopped_early = False
        final_status = RESULT_AC

        for tc in testcases:
            if stopped_early:
                result['testcases'].append({
                    'id': tc.get('id'), 'status': 'skipped',
                    'time_used': 0, 'memory_used': 0
                })
                continue

            # Prepare testcase files
            in_path = os.path.join(sub_dir, f"test_{tc.get('id', 0)}.in")
            out_path = os.path.join(sub_dir, f"test_{tc.get('id', 0)}.out")

            if not self._prepare_testcase(tc, in_path, out_path):
                result['testcases'].append({
                    'id': tc.get('id'), 'status': RESULT_UKE,
                    'time_used': 0, 'memory_used': 0
                })
                final_status = RESULT_UKE
                result['error_message'] = f'Failed to prepare testcase {tc.get("id")}'
                break

            run_status, time_used, memory_used = runner.run(
                sub_dir, in_path, time_limit, memory_limit * 1024
            )

            tc_result = {
                'id': tc.get('id'), 'status': run_status,
                'time_used': time_used, 'memory_used': memory_used
            }

            if run_status == 'OK':
                user_out = os.path.join(sub_dir, 'user.out')
                if os.path.exists(user_out) and self._compare_output(user_out, out_path):
                    tc_result['status'] = RESULT_AC
                    total_score += tc.get('score', 10)
                else:
                    tc_result['status'] = RESULT_WA
                    final_status = RESULT_WA
            elif run_status in (RESULT_TLE, RESULT_MLE, RESULT_RE):
                final_status = run_status
                if run_status in (RESULT_TLE, RESULT_MLE):
                    stopped_early = True

            max_time = max(max_time, time_used)
            max_memory = max(max_memory, memory_used)
            result['testcases'].append(tc_result)

        if final_status == RESULT_AC and total_score < max_score:
            final_status = RESULT_WA

        result['status'] = final_status
        result['score'] = 100 if final_status == RESULT_AC else (
            int(total_score * 100 / max_score) if max_score > 0 else 0
        )
        result['time_used'] = max_time
        result['memory_used'] = max_memory

        if final_status == RESULT_RE:
            err_path = os.path.join(sub_dir, 'user.err')
            if os.path.exists(err_path):
                with open(err_path, 'r', encoding='utf-8', errors='ignore') as f:
                    result['error_message'] = f.read()[:5000]

        return result

    def _prepare_testcase(self, tc, in_path, out_path):
        """Prepare testcase input/output files."""
        # Inlined testcases (base64 encoded in request)
        # Check for inlined flag, even if input_data/output_data are empty strings
        if tc.get('inlined') and 'input_data' in tc and 'output_data' in tc:
            try:
                with open(in_path, 'wb') as f:
                    f.write(base64.b64decode(tc['input_data']) if tc['input_data'] else b'')
                with open(out_path, 'wb') as f:
                    f.write(base64.b64decode(tc['output_data']) if tc['output_data'] else b'')
                return True
            except Exception:
                return False

        # URL-based testcases
        if tc.get('input_url') and tc.get('output_url'):
            din = self._download_testcase(tc['input_url'])
            dout = self._download_testcase(tc['output_url'])
            if din and dout:
                import shutil
                shutil.copy(din, in_path)
                shutil.copy(dout, out_path)
                return True

        return False

    def _download_testcase(self, url):
        """Download a testcase file with caching."""
        cache_path = os.path.join(self.cache_dir, hashlib.md5(url.encode()).hexdigest())
        if os.path.exists(cache_path):
            return cache_path

        try:
            resp = requests.get(url, timeout=10, allow_redirects=True)
            if resp.status_code == 200:
                os.makedirs(self.cache_dir, exist_ok=True)
                with open(cache_path, 'wb') as f:
                    f.write(resp.content)
                return cache_path
        except Exception:
            pass
        return None

    def _compare_output(self, user_out_path, expected_out_path):
        """Compare user output with expected output."""
        try:
            with open(user_out_path, 'rb') as f:
                u = f.read()
            with open(expected_out_path, 'rb') as f:
                e = f.read()
            ul = u.decode('utf-8', errors='surrogateescape').splitlines()
            el = e.decode('utf-8', errors='surrogateescape').splitlines()
            while ul and ul[-1].rstrip() == '':
                ul.pop()
            while el and el[-1].rstrip() == '':
                el.pop()
            return ul == el
        except Exception:
            return False

    def run(self):
        """Main loop: continuously poll and judge."""
        print(f"[JudgeWorker] Starting: host={self.host}, poll_interval={self.poll_interval*1000:.0f}ms",
              file=sys.stderr)

        consecutive_empty = 0
        while self.running:
            try:
                submissions = self._fetch_submissions(batch=1)

                if not submissions:
                    consecutive_empty += 1
                    # Adaptive sleep: longer when idle, shorter when busy
                    if consecutive_empty > 50:
                        time.sleep(0.5)  # 500ms when idle for a while
                    else:
                        time.sleep(self.poll_interval)
                    continue

                consecutive_empty = 0
                t0 = time.time()

                for sub in submissions:
                    if not self.running:
                        break

                    sub_id = sub.get('id', 'unknown')
                    lang = sub.get('language', '?')
                    t1 = time.time()

                    result = self._judge_submission(sub)
                    judge_ms = int((time.time() - t1) * 1000)

                    verdict = result['status']
                    score = result['score']
                    print(f"[JudgeWorker] [{sub_id}] {lang} → {verdict} ({score}/100, {judge_ms}ms)",
                          file=sys.stderr)
                    if result.get('error_message'):
                        print(f"  err: {result['error_message'][:200]}", file=sys.stderr)

                    self._report_results([result])

                total_ms = int((time.time() - t0) * 1000)
                if len(submissions) > 1:
                    print(f"[JudgeWorker] Batch done: {len(submissions)} subs in {total_ms}ms",
                          file=sys.stderr)

            except Exception as e:
                print(f"[JudgeWorker] Loop error: {e}", file=sys.stderr)
                time.sleep(1)

        print("[JudgeWorker] Stopped", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='HhOJ Persistent Judge Worker')
    parser.add_argument('--host', required=True, help='HhOJ backend URL (e.g. http://localhost:3000)')
    parser.add_argument('--api-key', default=os.environ.get('HHOJ_API_KEY', ''), help='API key')
    parser.add_argument('--poll-interval', type=int, default=100,
                        help='Poll interval in ms (default: 100)')
    parser.add_argument('--work-dir', default='./judge_work', help='Working directory')
    args = parser.parse_args()

    worker = JudgeWorker(
        host=args.host,
        api_key=args.api_key,
        poll_interval=args.poll_interval,
        work_dir=args.work_dir,
    )
    worker.run()


if __name__ == '__main__':
    main()