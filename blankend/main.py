#!/usr/bin/env python3
"""Unified judge: fetch → judge → report in one process, sharing one session."""

import os
import sys
import json
import base64
import argparse
import hashlib
import re
import time
import requests
from urllib.parse import urlparse
from Crypto.Cipher import AES

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


def solve_challenge(html_text):
    numbers = re.findall(r'toNumbers\("([a-f0-9]{32})"\)', html_text)
    if len(numbers) < 3:
        return None
    a, b, c = bytes.fromhex(numbers[0]), bytes.fromhex(numbers[1]), bytes.fromhex(numbers[2])
    for factory in [
        lambda: AES.new(a, AES.MODE_CBC, iv=b),
        lambda: AES.new(a, AES.MODE_ECB),
        lambda: AES.new(a, AES.MODE_OFB, iv=b),
        lambda: AES.new(a, AES.MODE_CFB, iv=b),
    ]:
        try:
            v = factory().decrypt(c).hex()
            if v and len(v) == 32:
                return v
        except Exception:
            continue
    try:
        return AES.new(a, AES.MODE_CBC, iv=b).decrypt(c).hex()
    except Exception:
        return None


def create_session(host, api_key):
    """Create session and solve InfinityFree challenge once."""
    session = requests.Session()
    session.headers.update({
        'X-API-Key': api_key,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
    })
    domain = urlparse(host).hostname or host

    # Solve challenge by hitting the API endpoint directly
    url = f"{host}/api/judge_fetch.php"
    for attempt in range(8):
        resp = session.get(url, params={'batch': 1, 'inline_testcases': 1}, timeout=15, allow_redirects=True)
        ct = resp.headers.get('content-type', '')
        if 'text/html' not in ct and not resp.text.strip().startswith('<html'):
            return session, resp  # Already got real data

        cookie = solve_challenge(resp.text)
        if not cookie:
            continue
        session.cookies.set('__test', cookie, domain=domain, path='/')
        session.headers['Cookie'] = f'__test={cookie}'

        redirect = re.search(r'location\.href="([^"]+)"', resp.text)
        if redirect:
            redirect_url = redirect.group(1).replace('***', host)
            if redirect_url.startswith('/'):
                redirect_url = host + redirect_url
            url = redirect_url

        print(f"  Challenge attempt {attempt+1}: solved, retrying...", file=sys.stderr)

    return session, None


def download_testcase(url, session, cache_dir):
    cache_path = os.path.join(cache_dir, hashlib.md5(url.encode()).hexdigest())
    if os.path.exists(cache_path):
        return cache_path
    for _ in range(2):
        try:
            resp = session.get(url, timeout=10, allow_redirects=True)
            if 'text/html' in resp.headers.get('content-type', '') or resp.text.strip().startswith('<html'):
                cookie = solve_challenge(resp.text)
                if cookie:
                    domain = urlparse(url).hostname or ''
                    session.cookies.set('__test', cookie, domain=domain)
                    session.headers['Cookie'] = f'__test={cookie}'
                    continue
            if resp.status_code == 200:
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache_path, 'wb') as f:
                    f.write(resp.content)
                return cache_path
        except Exception:
            continue
    return None


def prepare_testcase(tc, sub_dir, session, cache_dir):
    in_path = os.path.join(sub_dir, f"test_{tc.get('id', 0)}.in")
    out_path = os.path.join(sub_dir, f"test_{tc.get('id', 0)}.out")

    if tc.get('inlined') and tc.get('input_data') and tc.get('output_data'):
        try:
            with open(in_path, 'wb') as f:
                f.write(base64.b64decode(tc['input_data']))
            with open(out_path, 'wb') as f:
                f.write(base64.b64decode(tc['output_data']))
            return in_path, out_path
        except Exception:
            pass

    if tc.get('input_url') and tc.get('output_url'):
        din = download_testcase(tc['input_url'], session, cache_dir)
        dout = download_testcase(tc['output_url'], session, cache_dir)
        if din and dout:
            import shutil
            shutil.copy(din, in_path)
            shutil.copy(dout, out_path)
            return in_path, out_path
    return None, None


def compare_output(user_out_path, expected_out_path):
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


def judge_submission(submission, work_dir, session):
    sub_id = submission.get('id', 'unknown')
    language = submission.get('language', '')
    code = submission.get('code', '')
    testcases = submission.get('testcases') or []
    time_limit = submission.get('time_limit', 1000)
    memory_limit = submission.get('memory_limit', 256)

    sub_dir = os.path.join(work_dir, f"sub_{sub_id}")
    cache_dir = os.path.join(work_dir, 'tc_cache')
    os.makedirs(sub_dir, exist_ok=True)
    os.makedirs(cache_dir, exist_ok=True)

    result = {
        'submission_id': sub_id, 'status': RESULT_UKE, 'score': 0,
        'time_used': 0, 'memory_used': 0, 'error_message': '', 'testcases': []
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

    ok, err = runner.compile(code, sub_dir)
    if not ok:
        result['status'] = RESULT_CE
        result['error_message'] = err[:5000]
        return result

    total_score = 0
    max_score = sum(tc.get('score', 10) for tc in testcases) if testcases else 100
    if max_score == 0:
        max_score = 100

    max_time = max_mem = 0
    stopped_early = False
    final = RESULT_AC

    for tc in testcases:
        if stopped_early:
            result['testcases'].append({'id': tc.get('id'), 'status': 'skipped', 'time_used': 0, 'memory_used': 0})
            continue

        in_path, out_path = prepare_testcase(tc, sub_dir, session, cache_dir)
        if not in_path or not out_path:
            result['testcases'].append({'id': tc.get('id'), 'status': RESULT_UKE, 'time_used': 0, 'memory_used': 0})
            final = RESULT_UKE
            result['error_message'] = f'Failed to prepare testcase {tc.get("id")}'
            break

        status, t, m = runner.run(sub_dir, in_path, time_limit, memory_limit * 1024)
        tc_result = {'id': tc.get('id'), 'status': status, 'time_used': t, 'memory_used': m}

        if status == 'OK':
            user_out_path = os.path.join(sub_dir, 'user.out')
            if os.path.exists(user_out_path):
                if compare_output(user_out_path, out_path):
                    tc_result['status'] = RESULT_AC
                    total_score += tc.get('score', 10)
                else:
                    tc_result['status'] = RESULT_WA
                    final = RESULT_WA
            else:
                tc_result['status'] = RESULT_RE
                final = RESULT_RE
                result['error_message'] = f'User output file not found: {user_out_path}'
        elif status in (RESULT_TLE, RESULT_MLE, RESULT_RE):
            final = status
            if status in (RESULT_TLE, RESULT_MLE):
                stopped_early = True

        max_time = max(max_time, t)
        max_mem = max(max_mem, m)
        result['testcases'].append(tc_result)

    if final == RESULT_AC and total_score < max_score:
        final = RESULT_WA

    result['status'] = final
    result['score'] = 100 if final == RESULT_AC else (int(total_score * 100 / max_score) if max_score > 0 else 0)
    result['time_used'] = max_time
    result['memory_used'] = max_mem

    if final == RESULT_RE:
        err_path = os.path.join(sub_dir, 'user.err')
        if os.path.exists(err_path):
            with open(err_path, 'r', errors='ignore') as f:
                result['error_message'] = f.read()[:5000]

    return result


def report_results(session, site_url, results):
    url = f"{site_url}/api/judge_report.php"
    payload = {'results': [{
        'submission_id': r['submission_id'],
        'status': STATUS_TO_HHOJ.get(r['status'], 're'),
        'score': r['score'],
        'time_used': r['time_used'],
        'memory_used': r['memory_used'],
        'error_message': r.get('error_message', '')[:5000]
    } for r in results]}

    try:
        resp = session.post(url, json=payload, timeout=10)
        if 'text/html' in resp.headers.get('content-type', '') or resp.text.startswith('<html'):
            cookie = solve_challenge(resp.text)
            if cookie:
                domain = urlparse(site_url).hostname or ''
                session.cookies.set('__test', cookie, domain=domain)
                session.headers['Cookie'] = f'__test={cookie}'
                resp = session.post(url, json=payload, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description='HhOJ Unified Judge')
    parser.add_argument('--host', required=True)
    parser.add_argument('--api-key', default=os.environ.get('HHOJ_API_KEY', ''))
    parser.add_argument('--work-dir', default='./judge_work')
    args = parser.parse_args()

    host = args.host.rstrip('/')
    work_dir = os.path.abspath(args.work_dir)
    os.makedirs(work_dir, exist_ok=True)

    t0 = time.time()

    # Step 1: Create session + fetch (challenge solved once here)
    session, response = create_session(host, args.api_key)
    if response is None:
        print("Failed: challenge not solved", file=sys.stderr)
        sys.exit(1)

    # Save submissions.json for debugging
    with open('submissions.json', 'w', encoding='utf-8') as f:
        f.write(response.text)

    try:
        data = response.json()
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)

    if not data.get('success'):
        print(f"API error: {data.get('message', 'Unknown')}", file=sys.stderr)
        sys.exit(1)

    submissions = data.get('submissions', [])
    print(f"Fetch: {int((time.time()-t0)*1000)}ms, count={len(submissions)}")

    if not submissions:
        print("No pending submissions")
        with open('status.txt', 'w') as f:
            f.write('SKIP')
        with open('summary.md', 'w') as f:
            f.write('# HhOJ Judge Result\n\n**Status**: No pending submissions\n')
        return

    # Step 2: Judge (reusing same session - no redundant challenge!)
    t1 = time.time()
    results = []
    for sub in submissions:
        sub_id = sub.get('id', 'unknown')
        try:
            r = judge_submission(sub, work_dir, session)
            results.append(r)
            print(f"[{sub_id}] {r['status']} ({r['score']}/100, {r['time_used']}ms)")
            if r['error_message']:
                print(f"  err: {r['error_message'][:200]}", file=sys.stderr)
        except Exception as e:
            print(f"[{sub_id}] Error: {e}", file=sys.stderr)
            results.append({
                'submission_id': sub_id, 'status': RESULT_UKE, 'score': 0,
                'time_used': 0, 'memory_used': 0, 'error_message': str(e)[:5000]
            })
    print(f"Judge: {int((time.time()-t1)*1000)}ms")

    # Step 3: Report (reusing same session)
    t2 = time.time()
    ok = report_results(session, host, results)
    print(f"Report: {'OK' if ok else 'FAILED'} ({int((time.time()-t2)*1000)}ms)")

    # Write output files
    with open('judge_result.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    with open('status.txt', 'w') as f:
        f.write('SUCCESS' if results else 'SKIP')
    with open('summary.md', 'w', encoding='utf-8') as f:
        f.write('# HhOJ Judge Result\n\n')
        for r in results:
            f.write(f"## Submission #{r['submission_id']}\n\n")
            f.write(f"- **Status**: {r['status']}\n- **Score**: {r['score']}/100\n")
            f.write(f"- **Time**: {r['time_used']} ms\n- **Memory**: {r['memory_used']} KB\n")
            if r.get('error_message'):
                f.write(f"- **Error**: {r['error_message'][:200]}\n")
            f.write('\n')

    print(f"Total: {int((time.time()-t0)*1000)}ms")


if __name__ == '__main__':
    main()
