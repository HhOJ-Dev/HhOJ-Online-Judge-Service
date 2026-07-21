#!/usr/bin/env python3

import os
import sys
import json
import base64
import argparse
import tempfile
import hashlib
import time
import re
import requests

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
        with open(user_out_path, 'r', encoding='utf-8', errors='ignore') as f:
            user_lines = f.read().splitlines()
        with open(expected_out_path, 'r', encoding='utf-8', errors='ignore') as f:
            expected_lines = f.read().splitlines()

        while user_lines and user_lines[-1].rstrip() == '':
            user_lines.pop()
        while expected_lines and expected_lines[-1].rstrip() == '':
            expected_lines.pop()

        if len(user_lines) != len(expected_lines):
            return False

        for u, e in zip(user_lines, expected_lines):
            if u.rstrip() != e.rstrip():
                return False

        return True
    except Exception:
        return False


def solve_infinitree_challenge(html_text):
    """Parse and solve InfinityFree's JavaScript AES challenge."""
    from Crypto.Cipher import AES
    numbers = re.findall(r'toNumbers\("([a-f0-9]{32})"\)', html_text)
    if len(numbers) < 3:
        return None

    a = bytes.fromhex(numbers[0])  # key
    b = bytes.fromhex(numbers[1])  # IV
    c = bytes.fromhex(numbers[2])  # ciphertext

    # Try CBC first (most common for InfinityFree)
    try:
        cipher = AES.new(a, AES.MODE_CBC, b)
        decrypted = cipher.decrypt(c)
        return decrypted.hex()
    except Exception:
        pass

    # Try ECB as fallback
    try:
        cipher = AES.new(a, AES.MODE_ECB)
        decrypted = cipher.decrypt(c)
        return decrypted.hex()
    except Exception:
        pass

    return None


def create_api_session(host, api_key):
    """Create a requests session with InfinityFree challenge handling."""
    session = requests.Session()
    session.headers.update({
        'X-API-Key': api_key,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    })

    # Pre-fetch to solve InfinityFree JavaScript challenge
    try:
        response = session.get(host, timeout=30, allow_redirects=True)
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

    try:
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            # Handle InfinityFree challenge
            if 'text/html' in response.headers.get('content-type', '') or response.text.startswith('<html'):
                cookie_value = solve_infinitree_challenge(response.text)
                if cookie_value:
                    domain = url.split('/')[2] if '://' in url else ''
                    session.cookies.set('__test', cookie_value, domain=domain)
                    response = session.get(url, timeout=30)

            if response.status_code == 200 and not response.text.startswith('<html'):
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache_path, 'wb') as f:
                    f.write(response.content)
                return cache_path
    except Exception:
        pass

    return None


def prepare_testcase(tc, sub_dir, session, cache_dir):
    in_path = os.path.join(sub_dir, f"test_{tc.get('id', 0)}.in")
    out_path = os.path.join(sub_dir, f"test_{tc.get('id', 0)}.out")

    print(f"  [TC {tc.get('id')}] inlined={tc.get('inlined')}, has_input_data={bool(tc.get('input_data'))}, has_output_data={bool(tc.get('output_data'))}", file=sys.stderr)

    if tc.get('inlined'):
        if tc.get('input_data') and tc.get('output_data'):
            try:
                input_decoded = base64.b64decode(tc['input_data'])
                output_decoded = base64.b64decode(tc['output_data'])
                print(f"  [TC {tc.get('id')}] Decoded input: {repr(input_decoded[:100])}, output: {repr(output_decoded[:100])}", file=sys.stderr)
                
                with open(in_path, 'wb') as f:
                    f.write(input_decoded)
                with open(out_path, 'wb') as f:
                    f.write(output_decoded)
                return in_path, out_path
            except Exception as e:
                print(f"  [TC {tc.get('id')}] Base64 decode error: {e}", file=sys.stderr)
        else:
            print(f"  [TC {tc.get('id')}] Missing input_data or output_data", file=sys.stderr)

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
        result['error_message'] = 'Empty or missing source code'
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
                'id': tc.get('id'),
                'status': 'skipped',
                'time_used': 0,
                'memory_used': 0
            })
            continue

        in_path, out_path = prepare_testcase(tc, sub_dir, session, cache_dir)
        if not in_path or not out_path:
            tc_result = {
                'id': tc.get('id'),
                'status': RESULT_UKE,
                'time_used': 0,
                'memory_used': 0
            }
            result['testcases'].append(tc_result)
            final_status = RESULT_UKE
            break

        run_status, time_used, memory_used = runner.run(
            sub_dir, in_path, time_limit, memory_limit * 1024
        )

        tc_result = {
            'id': tc.get('id'),
            'status': run_status,
            'time_used': time_used,
            'memory_used': memory_used
        }

        if run_status == 'OK':
            user_out = os.path.join(sub_dir, 'user.out')
            if compare_output(user_out, out_path):
                tc_result['status'] = RESULT_AC
                tc_score = tc.get('score', 10)
                total_score += tc_score
            else:
                tc_result['status'] = RESULT_WA
                final_status = RESULT_WA
        elif run_status == RESULT_TLE:
            final_status = RESULT_TLE
            stopped_early = True
        elif run_status == RESULT_MLE:
            final_status = RESULT_MLE
            stopped_early = True
        elif run_status == RESULT_RE:
            final_status = RESULT_RE

        max_time = max(max_time, time_used)
        max_memory = max(max_memory, memory_used)

        result['testcases'].append(tc_result)

    if final_status == RESULT_AC and total_score < max_score:
        final_status = RESULT_WA

    if final_status == RESULT_AC:
        score = 100
    else:
        score = int(total_score * 100 / max_score) if max_score > 0 else 0

    result['status'] = final_status
    result['score'] = score
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

    payload = {'results': hhoj_results}

    try:
        response = session.post(url, json=payload, timeout=30)
        # Handle InfinityFree challenge on POST too
        if 'text/html' in response.headers.get('content-type', '') or response.text.startswith('<html'):
            cookie_value = solve_infinitree_challenge(response.text)
            if cookie_value:
                domain = site_url.split('/')[2] if '://' in site_url else ''
                session.cookies.set('__test', cookie_value, domain=domain)
                response = session.post(url, json=payload, timeout=30)
        return response.status_code == 200, response.text
    except Exception as e:
        return False, str(e)


def main():
    parser = argparse.ArgumentParser(description='HhOJ Judge Script v3.0')
    parser.add_argument('--api-key', required=True, help='API key')
    parser.add_argument('--site-url', required=True, help='HhOJ site URL')
    parser.add_argument('--submissions', required=True, help='Path to submissions JSON file')
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

    # Create session with InfinityFree challenge handling
    session = create_api_session(site_url, args.api_key)

    results = []
    for submission in submissions:
        sub_id = submission['id']
        print(f"[{sub_id}] Judging {submission.get('language', 'unknown')}...")

        try:
            result = judge_submission(submission, work_dir, session)
            results.append(result)
            print(f"[{sub_id}] Result: {result['status']} (score: {result['score']}, time: {result['time_used']}ms)")
        except Exception as e:
            import traceback
            print(f"[{sub_id}] Error: {e}", file=sys.stderr)
            traceback.print_exc()
            results.append({
                'submission_id': sub_id,
                'status': RESULT_UKE,
                'score': 0,
                'time_used': 0,
                'memory_used': 0,
                'error_message': str(e)[:5000]
            })

    if results:
        print(f"Reporting {len(results)} results to {site_url}...")
        ok, msg = report_results(session, site_url, results)
        if ok:
            print("Report successful")
        else:
            print(f"Report failed: {msg}", file=sys.stderr)

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
