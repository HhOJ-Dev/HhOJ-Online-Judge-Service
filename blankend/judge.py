#!/usr/bin/env python3

import os
import sys
import json
import base64
import argparse
import hashlib
import re
import requests
from urllib.parse import urlparse

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


def compare_output(user_out_path, expected_out_path):
    try:
        with open(user_out_path, 'rb') as f:
            user_data = f.read()
        with open(expected_out_path, 'rb') as f:
            expected_data = f.read()

        user_lines = user_data.decode('utf-8', errors='surrogateescape').splitlines()
        expected_lines = expected_data.decode('utf-8', errors='surrogateescape').splitlines()

        while user_lines and user_lines[-1].rstrip() == '':
            user_lines.pop()
        while expected_lines and expected_lines[-1].rstrip() == '':
            expected_lines.pop()

        return user_lines == expected_lines
    except Exception:
        return False


def solve_infinitree_challenge(html_text):
    from Crypto.Cipher import AES
    numbers = re.findall(r'toNumbers\("([a-f0-9]{32})"\)', html_text)
    if len(numbers) < 3:
        return None
    a = bytes.fromhex(numbers[0])
    b = bytes.fromhex(numbers[1])
    c = bytes.fromhex(numbers[2])
    try:
        return AES.new(a, AES.MODE_CBC, b).decrypt(c).hex()
    except Exception:
        pass
    try:
        return AES.new(a, AES.MODE_ECB).decrypt(c).hex()
    except Exception:
        pass
    return None


def create_api_session(host, api_key):
    session = requests.Session()
    session.headers.update({
        'X-API-Key': api_key,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36'
    })
    try:
        response = session.get(host, timeout=5, allow_redirects=True)
        if 'text/html' in response.headers.get('content-type', '') or response.text.startswith('<html'):
            cookie_value = solve_infinitree_challenge(response.text)
            if cookie_value:
                domain = host.split('/')[2] if '://' in host else host.split('/')[0]
                session.cookies.set('__test', cookie_value, domain=domain)
    except Exception:
        pass
    return session


def download_testcase(url, session, cache_dir):
    url_hash = hashlib.md5(url.encode()).hexdigest()
    cache_path = os.path.join(cache_dir, url_hash)
    if os.path.exists(cache_path):
        return cache_path

    for attempt in range(2):
        try:
            response = session.get(url, timeout=10, allow_redirects=True)
            is_html = 'text/html' in response.headers.get('content-type', '') or response.text.strip().startswith('<html')

            if is_html:
                cookie_value = solve_infinitree_challenge(response.text)
                if cookie_value:
                    domain = urlparse(url).hostname or ''
                    session.cookies.set('__test', cookie_value, domain=domain)
                    session.headers['Cookie'] = f'__test={cookie_value}'
                    continue

            if response.status_code == 200:
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache_path, 'wb') as f:
                    f.write(response.content)
                return cache_path
        except Exception:
            continue

    return None


def prepare_testcase(tc, sub_dir, session, cache_dir):
    in_path = os.path.join(sub_dir, f"test_{tc.get('id', 0)}.in")
    out_path = os.path.join(sub_dir, f"test_{tc.get('id', 0)}.out")

    if tc.get('inlined') and tc.get('input_data') and tc.get('output_data'):
        try:
            input_decoded = base64.b64decode(tc['input_data'])
            output_decoded = base64.b64decode(tc['output_data'])
            with open(in_path, 'wb') as f:
                f.write(input_decoded)
            with open(out_path, 'wb') as f:
                f.write(output_decoded)
            return in_path, out_path
        except Exception:
            pass

    if tc.get('input_url') and tc.get('output_url'):
        downloaded_in = download_testcase(tc['input_url'], session, cache_dir)
        downloaded_out = download_testcase(tc['output_url'], session, cache_dir)
        if downloaded_in and downloaded_out:
            import shutil
            shutil.copy(downloaded_in, in_path)
            shutil.copy(downloaded_out, out_path)
            return in_path, out_path

    return None, None


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
            result['testcases'].append({'id': tc.get('id'), 'status': 'skipped', 'time_used': 0, 'memory_used': 0})
            continue

        in_path, out_path = prepare_testcase(tc, sub_dir, session, cache_dir)
        if not in_path or not out_path:
            result['testcases'].append({'id': tc.get('id'), 'status': RESULT_UKE, 'time_used': 0, 'memory_used': 0})
            final_status = RESULT_UKE
            break

        run_status, time_used, memory_used = runner.run(sub_dir, in_path, time_limit, memory_limit * 1024)

        tc_result = {'id': tc.get('id'), 'status': run_status, 'time_used': time_used, 'memory_used': memory_used}

        if run_status == 'OK':
            user_out = os.path.join(sub_dir, 'user.out')
            if compare_output(user_out, out_path):
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
    result['score'] = 100 if final_status == RESULT_AC else (int(total_score * 100 / max_score) if max_score > 0 else 0)
    result['time_used'] = max_time
    result['memory_used'] = max_memory

    if final_status == RESULT_RE:
        err_path = os.path.join(sub_dir, 'user.err')
        if os.path.exists(err_path):
            with open(err_path, 'r', encoding='utf-8', errors='ignore') as f:
                result['error_message'] = f.read()[:5000]

    return result


def report_results(session, site_url, results):
    url = f"{site_url}/api/judge_report.php"
    hhoj_results = []
    for r in results:
        hhoj_results.append({
            'submission_id': r['submission_id'],
            'status': STATUS_TO_HHOJ.get(r['status'], 're'),
            'score': r['score'],
            'time_used': r['time_used'],
            'memory_used': r['memory_used'],
            'error_message': r.get('error_message', '')[:5000]
        })

    try:
        response = session.post(url, json={'results': hhoj_results}, timeout=10)
        if 'text/html' in response.headers.get('content-type', '') or response.text.startswith('<html'):
            cookie_value = solve_infinitree_challenge(response.text)
            if cookie_value:
                domain = urlparse(site_url).hostname or ''
                session.cookies.set('__test', cookie_value, domain=domain)
                response = session.post(url, json={'results': hhoj_results}, timeout=10)
        return response.status_code == 200, response.text
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description='HhOJ Judge Script')
    parser.add_argument('--api-key', default=os.environ.get('HHOJ_API_KEY', ''), help='API key')
    parser.add_argument('--site-url', required=True, help='HhOJ site URL')
    parser.add_argument('--submissions', required=True, help='Submissions JSON file')
    parser.add_argument('--work-dir', default='./judge_work', help='Working directory')

    args = parser.parse_args()
    site_url = args.site_url.rstrip('/')
    work_dir = os.path.abspath(args.work_dir)
    os.makedirs(work_dir, exist_ok=True)

    with open(args.submissions, 'r', encoding='utf-8') as f:
        data = json.load(f)

    if not data.get('success'):
        print(f"API error: {data.get('message', 'Unknown')}", file=sys.stderr)
        sys.exit(1)

    submissions = data.get('submissions', [])
    print(f"Loaded {len(submissions)} submissions")

    session = create_api_session(site_url, args.api_key)

    results = []
    for submission in submissions:
        sub_id = submission.get('id', 'unknown')
        print(f"[{sub_id}] Judging...")
        try:
            result = judge_submission(submission, work_dir, session)
            results.append(result)
            print(f"[{sub_id}] {result['status']} ({result['score']}/100, {result['time_used']}ms)")
        except Exception as e:
            print(f"[{sub_id}] Error: {e}", file=sys.stderr)
            results.append({
                'submission_id': sub_id,
                'status': RESULT_UKE,
                'score': 0,
                'time_used': 0,
                'memory_used': 0,
                'error_message': str(e)[:5000]
            })

    if results:
        print(f"Reporting {len(results)} results...")
        ok, msg = report_results(session, site_url, results)
        print("Report OK" if ok else f"Report failed: {msg}")

    result_file = os.path.join(os.path.dirname(args.submissions), 'judge_result.json')
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    status_file = os.path.join(os.path.dirname(args.submissions), 'status.txt')
    with open(status_file, 'w') as f:
        f.write('SUCCESS' if results else 'SKIP')

    summary_file = os.path.join(os.path.dirname(args.submissions), 'summary.md')
    with open(summary_file, 'w', encoding='utf-8') as f:
        f.write('# HhOJ Judge Result\n\n')
        if results:
            for r in results:
                f.write(f"## Submission #{r['submission_id']}\n\n")
                f.write(f"- **Status**: {r['status']}\n")
                f.write(f"- **Score**: {r['score']}/100\n")
                f.write(f"- **Time**: {r['time_used']} ms\n")
                f.write(f"- **Memory**: {r['memory_used']} KB\n")
                if r.get('error_message'):
                    f.write(f"- **Error**: {r['error_message'][:200]}\n")
                f.write('\n')
        else:
            f.write("**Status**: No submissions to judge\n")

    print("Done.")


if __name__ == '__main__':
    main()
