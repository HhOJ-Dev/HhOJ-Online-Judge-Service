#!/usr/bin/env python3
"""
Fetch submissions from HhOJ API, handling InfinityFree's JavaScript anti-bot challenge.
"""

import sys
import re
import requests
from Crypto.Cipher import AES
from urllib.parse import urlparse, urlencode


def solve_infinitree_challenge(html_text):
    """Parse and solve InfinityFree's JavaScript AES challenge."""
    numbers = re.findall(r'toNumbers\("([a-f0-9]{32})"\)', html_text)
    if len(numbers) < 3:
        return None

    a = bytes.fromhex(numbers[0])  # key
    b = bytes.fromhex(numbers[1])  # IV
    c = bytes.fromhex(numbers[2])  # ciphertext

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
            # Cookie value is the hex string of the decrypted data
            cookie_value = decrypted.hex()
            # Basic validation: cookie should be non-empty and look reasonable
            if cookie_value and len(cookie_value) == 32:
                return cookie_value
        except Exception:
            continue

    # Last resort: return raw decryption from CBC (most common)
    try:
        cipher = AES.new(a, AES.MODE_CBC, iv=b)
        decrypted = cipher.decrypt(c)
        return decrypted.hex()
    except Exception:
        pass

    return None


def fetch_submissions(host, api_key, batch=1, inline_testcases=1, max_retries=10):
    """Fetch submissions with InfinityFree challenge handling."""
    url = f"{host}/api/judge_fetch.php"
    params = {
        'batch': batch,
        'inline_testcases': inline_testcases
    }
    headers = {
        'X-API-Key': api_key,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/javascript, */*; q=0.01',
        'Accept-Language': 'en-US,en;q=0.9',
        'X-Requested-With': 'XMLHttpRequest',
    }

    session = requests.Session()
    session.headers.update(headers)

    # Parse domain for cookie setting
    parsed = urlparse(host)
    domain = parsed.hostname or host

    cookie_value = None
    response = None
    for attempt in range(max_retries):
        # Set cookie in header directly if we have one
        if cookie_value:
            session.headers['Cookie'] = f'__test={cookie_value}'

        response = session.get(url, params=params, timeout=30, allow_redirects=True)

        # Check if we got the InfinityFree JavaScript challenge
        content_type = response.headers.get('content-type', '')
        is_html = 'text/html' in content_type or response.text.strip().startswith('<html') or response.text.strip().startswith('<!DOCTYPE')

        if not is_html:
            # Got real content
            return response

        # Try to solve the challenge
        cookie_value = solve_infinitree_challenge(response.text)
        if not cookie_value:
            print(f"Attempt {attempt + 1}: Failed to solve JavaScript challenge", file=sys.stderr)
            print(f"Response preview: {response.text[:300]}", file=sys.stderr)
            continue

        # Also set cookie in session cookies
        session.cookies.set('__test', cookie_value, domain=domain, path='/')

        # Check if the challenge HTML contains a redirect URL with &i= parameter
        redirect_match = re.search(r'location\.href="([^"]+)"', response.text)
        if redirect_match:
            redirect_url = redirect_match.group(1)
            # The URL in the HTML may have *** as host mask, replace with actual host
            if '***' in redirect_url:
                redirect_url = redirect_url.replace('***', host)
            # If it's a relative URL, make it absolute
            if redirect_url.startswith('/'):
                redirect_url = host + redirect_url
            # Use the redirect URL for the next request
            url = redirect_url
            # Clear params since they're already in the redirect URL
            params = None

        print(f"Attempt {attempt + 1}: Solved challenge (cookie={cookie_value[:8]}...), retrying...", file=sys.stderr)

    return response


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Fetch submissions from HhOJ API')
    parser.add_argument('--host', required=True, help='HhOJ site URL')
    parser.add_argument('--api-key', required=True, help='API key')
    parser.add_argument('--output', default='submissions.json', help='Output file path')
    parser.add_argument('--batch', type=int, default=1, help='Batch size')
    parser.add_argument('--inline-testcases', type=int, default=1, help='Inline testcases')
    parser.add_argument('--max-retries', type=int, default=10, help='Max retries for challenge')

    args = parser.parse_args()
    host = args.host.rstrip('/')

    response = fetch_submissions(
        host, args.api_key, args.batch, args.inline_testcases, args.max_retries
    )

    if response is None:
        print("Failed to fetch submissions: no response", file=sys.stderr)
        sys.exit(1)

    # Check if we still got HTML (challenge not solved)
    content_type = response.headers.get('content-type', '')
    if 'text/html' in content_type or response.text.strip().startswith('<html'):
        print("Failed to pass InfinityFree JavaScript challenge after all retries", file=sys.stderr)
        print(f"Final response preview: {response.text[:500]}", file=sys.stderr)
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
            
            for idx, sub in enumerate(data.get('submissions', [])):
                code = sub.get('code', '')
                if not code or len(code) < 10:
                    print(f"WARNING: Submission #{sub.get('id', idx)} has suspicious code (length={len(code)}): {repr(code[:50])}", file=sys.stderr)
        else:
            print(f"API error: {data.get('message', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Failed to parse response as JSON: {e}", file=sys.stderr)
        print(f"Response preview: {response.text[:500]}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
