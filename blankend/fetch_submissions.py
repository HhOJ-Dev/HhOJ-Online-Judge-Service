#!/usr/bin/env python3
"""
Fetch submissions from HhOJ API, handling InfinityFree's JavaScript anti-bot challenge.
"""

import sys
import re
import requests
from Crypto.Cipher import AES


def solve_infinitree_challenge(html_text):
    """Parse and solve InfinityFree's JavaScript AES challenge."""
    numbers = re.findall(r'toNumbers\("([a-f0-9]{32})"\)', html_text)
    if len(numbers) < 3:
        return None

    a = bytes.fromhex(numbers[0])  # key
    b = bytes.fromhex(numbers[1])  # IV
    c = bytes.fromhex(numbers[2])  # ciphertext

    # InfinityFree uses AES-ECB (slowAES mode 2 in some versions, CBC in others)
    # Try ECB first (most common for InfinityFree)
    try:
        cipher = AES.new(a, AES.MODE_ECB)
        decrypted = cipher.decrypt(c)
        return decrypted.hex()
    except Exception:
        pass

    # Try CBC as fallback
    try:
        cipher = AES.new(a, AES.MODE_CBC, b)
        decrypted = cipher.decrypt(c)
        return decrypted.hex()
    except Exception:
        pass

    return None


def fetch_submissions(host, api_key, batch=1, inline_testcases=1):
    """Fetch submissions with InfinityFree challenge handling."""
    url = f"{host}/api/judge_fetch.php"
    params = {
        'batch': batch,
        'inline_testcases': inline_testcases
    }
    headers = {
        'X-API-Key': api_key,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    }

    session = requests.Session()
    session.headers.update(headers)

    # First request - may get JavaScript challenge
    response = session.get(url, params=params, timeout=30, allow_redirects=True)

    # Check if we got the InfinityFree JavaScript challenge
    content_type = response.headers.get('content-type', '')
    if 'text/html' in content_type or response.text.startswith('<html'):
        cookie_value = solve_infinitree_challenge(response.text)
        if cookie_value:
            # Set the cookie and retry
            session.cookies.set('__test', cookie_value, domain=response.url.split('/')[2])
            response = session.get(url, params=params, timeout=30, allow_redirects=True)

    return response


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fetch submissions from HhOJ API')
    parser.add_argument('--host', required=True, help='HhOJ site URL')
    parser.add_argument('--api-key', required=True, help='API key')
    parser.add_argument('--output', default='submissions.json', help='Output file path')
    parser.add_argument('--batch', type=int, default=1, help='Batch size')
    parser.add_argument('--inline-testcases', type=int, default=1, help='Inline testcases')
    parser.add_argument('--max-retries', type=int, default=5, help='Max retries for challenge')

    args = parser.parse_args()
    host = args.host.rstrip('/')

    response = None
    for attempt in range(args.max_retries):
        response = fetch_submissions(host, args.api_key, args.batch, args.inline_testcases)

        # Check if still getting HTML challenge
        content_type = response.headers.get('content-type', '')
        if 'text/html' not in content_type and not response.text.startswith('<html'):
            break

        print(f"Attempt {attempt + 1}: Still getting JavaScript challenge, retrying...", file=sys.stderr)

        # Try to solve and set cookie for next attempt
        cookie_value = solve_infinitree_challenge(response.text)
        if not cookie_value:
            print("Failed to solve JavaScript challenge", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"Failed after {args.max_retries} attempts", file=sys.stderr)
        sys.exit(1)

    # Write response to output file
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(response.text)

    # Try to parse as JSON and print summary
    try:
        data = response.json()
        if data.get('success'):
            count = len(data.get('submissions', []))
            print(f"Successfully fetched {count} submissions")
        else:
            print(f"API error: {data.get('message', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Failed to parse response as JSON: {e}", file=sys.stderr)
        print(f"Response preview: {response.text[:500]}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
