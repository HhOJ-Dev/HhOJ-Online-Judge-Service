#!/usr/bin/env python3

import sys
import os
import re
import requests
from Crypto.Cipher import AES
from urllib.parse import urlparse


def solve_infinitree_challenge(html_text):
    numbers = re.findall(r'toNumbers\("([a-f0-9]{32})"\)', html_text)
    if len(numbers) < 3:
        return None
    a = bytes.fromhex(numbers[0])
    b = bytes.fromhex(numbers[1])
    c = bytes.fromhex(numbers[2])
    try:
        cipher = AES.new(a, AES.MODE_CBC, iv=b)
        decrypted = cipher.decrypt(c)
        return decrypted.hex()
    except Exception:
        pass
    try:
        cipher = AES.new(a, AES.MODE_ECB)
        decrypted = cipher.decrypt(c)
        return decrypted.hex()
    except Exception:
        pass
    return None


def fetch_submissions(host, api_key, batch=1, inline_testcases=1, max_retries=3):
    url = f"{host}/api/judge_fetch.php"
    params = {'batch': batch, 'inline_testcases': inline_testcases}
    headers = {
        'X-API-Key': api_key,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36',
    }

    session = requests.Session()
    session.headers.update(headers)
    parsed = urlparse(host)
    domain = parsed.hostname or host

    cookie_value = None
    for attempt in range(max_retries):
        if cookie_value:
            session.headers['Cookie'] = f'__test={cookie_value}'

        response = session.get(url, params=params, timeout=10, allow_redirects=True)
        content_type = response.headers.get('content-type', '')
        is_html = 'text/html' in content_type or response.text.strip().startswith('<html') or response.text.strip().startswith('<!DOCTYPE')

        if not is_html:
            return response

        cookie_value = solve_infinitree_challenge(response.text)
        if not cookie_value:
            continue

        session.cookies.set('__test', cookie_value, domain=domain, path='/')
        redirect_match = re.search(r'location\.href="([^"]+)"', response.text)
        if redirect_match:
            redirect_url = redirect_match.group(1)
            if '***' in redirect_url:
                redirect_url = redirect_url.replace('***', host)
            if redirect_url.startswith('/'):
                redirect_url = host + redirect_url
            url = redirect_url
            params = None

    return response


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fetch submissions from HhOJ API')
    parser.add_argument('--host', required=True, help='HhOJ site URL')
    parser.add_argument('--api-key', default=os.environ.get('HHOJ_API_KEY', ''), help='API key')
    parser.add_argument('--output', default='submissions.json', help='Output file path')
    parser.add_argument('--batch', type=int, default=1, help='Batch size')
    parser.add_argument('--inline-testcases', type=int, default=1, help='Inline testcases')
    parser.add_argument('--max-retries', type=int, default=3, help='Max retries')

    args = parser.parse_args()
    host = args.host.rstrip('/')

    response = fetch_submissions(host, args.api_key, args.batch, args.inline_testcases, args.max_retries)

    if response is None:
        print("Failed: no response", file=sys.stderr)
        sys.exit(1)

    content_type = response.headers.get('content-type', '')
    if 'text/html' in content_type or response.text.strip().startswith('<html'):
        print("Failed: challenge not solved", file=sys.stderr)
        sys.exit(1)

    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(response.text)

    try:
        data = response.json()
        if data.get('success'):
            count = len(data.get('submissions', []))
            print(f"count={count}")
            for idx, sub in enumerate(data.get('submissions', [])):
                code = sub.get('code', '')
                if not code or len(code) < 10:
                    print(f"WARNING: Submission #{sub.get('id', idx)} suspicious code", file=sys.stderr)
        else:
            print(f"API error: {data.get('message', 'Unknown')}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
