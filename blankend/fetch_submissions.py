#!/usr/bin/env python3

import sys
import os
import re
import requests
from Crypto.Cipher import AES
from urllib.parse import urlparse


def solve_infinitree_challenge(html_text):
    """Parse and solve InfinityFree's JavaScript AES challenge."""
    numbers = re.findall(r'toNumbers\("([a-f0-9]{32})"\)', html_text)
    if len(numbers) < 3:
        return None
    a = bytes.fromhex(numbers[0])
    b = bytes.fromhex(numbers[1])
    c = bytes.fromhex(numbers[2])

    # Try all AES modes (InfinityFree uses different modes in different versions)
    modes = [
        ('CBC', lambda: AES.new(a, AES.MODE_CBC, iv=b)),
        ('ECB', lambda: AES.new(a, AES.MODE_ECB)),
        ('OFB', lambda: AES.new(a, AES.MODE_OFB, iv=b)),
        ('CFB', lambda: AES.new(a, AES.MODE_CFB, iv=b)),
    ]

    for mode_name, cipher_factory in modes:
        try:
            cipher = cipher_factory()
            decrypted = cipher.decrypt(c)
            cookie_value = decrypted.hex()
            if cookie_value and len(cookie_value) == 32:
                return cookie_value
        except Exception:
            continue

    # Last resort: return raw decryption from CBC
    try:
        cipher = AES.new(a, AES.MODE_CBC, iv=b)
        decrypted = cipher.decrypt(c)
        return decrypted.hex()
    except Exception:
        pass
    return None


def fetch_submissions(host, api_key, batch=1, inline_testcases=1, max_retries=8):
    """Fetch submissions with InfinityFree challenge handling."""
    url = f"{host}/api/judge_fetch.php"
    params = {'batch': batch, 'inline_testcases': inline_testcases}
    headers = {
        'X-API-Key': api_key,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9',
        'X-Requested-With': 'XMLHttpRequest',
    }

    session = requests.Session()
    session.headers.update(headers)

    parsed = urlparse(host)
    domain = parsed.hostname or host

    cookie_value = None
    response = None
    for attempt in range(max_retries):
        if cookie_value:
            session.headers['Cookie'] = f'__test={cookie_value}'

        response = session.get(url, params=params, timeout=15, allow_redirects=True)

        content_type = response.headers.get('content-type', '')
        is_html = 'text/html' in content_type or response.text.strip().startswith('<html') or response.text.strip().startswith('<!DOCTYPE')

        if not is_html:
            return response

        cookie_value = solve_infinitree_challenge(response.text)
        if not cookie_value:
            print(f"Attempt {attempt + 1}: Failed to solve challenge", file=sys.stderr)
            continue

        session.cookies.set('__test', cookie_value, domain=domain, path='/')

        # Follow redirect URL embedded in challenge HTML
        redirect_match = re.search(r'location\.href="([^"]+)"', response.text)
        if redirect_match:
            redirect_url = redirect_match.group(1)
            if '***' in redirect_url:
                redirect_url = redirect_url.replace('***', host)
            if redirect_url.startswith('/'):
                redirect_url = host + redirect_url
            url = redirect_url
            params = None

        print(f"Attempt {attempt + 1}: Solved challenge, retrying...", file=sys.stderr)

    return response


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fetch submissions from HhOJ API')
    parser.add_argument('--host', required=True, help='HhOJ site URL')
    parser.add_argument('--api-key', default=os.environ.get('HHOJ_API_KEY', ''), help='API key')
    parser.add_argument('--output', default='submissions.json', help='Output file path')
    parser.add_argument('--batch', type=int, default=1, help='Batch size')
    parser.add_argument('--inline-testcases', type=int, default=1, help='Inline testcases')
    parser.add_argument('--max-retries', type=int, default=8, help='Max retries')

    args = parser.parse_args()
    host = args.host.rstrip('/')

    response = fetch_submissions(host, args.api_key, args.batch, args.inline_testcases, args.max_retries)

    if response is None:
        print("Failed: no response", file=sys.stderr)
        sys.exit(1)

    content_type = response.headers.get('content-type', '')
    if 'text/html' in content_type or response.text.strip().startswith('<html'):
        print("Failed: challenge not solved after retries", file=sys.stderr)
        sys.exit(1)

    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(response.text)

    try:
        data = response.json()
        if data.get('success'):
            count = len(data.get('submissions', []))
            print(f"count={count}")
        else:
            print(f"API error: {data.get('message', 'Unknown')}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
