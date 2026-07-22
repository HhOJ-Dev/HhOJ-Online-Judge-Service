#!/bin/bash
# Single-step judge script: fetch → install compilers → judge → report → summary
set -euo pipefail

HOST="${1%/}"
WORK_DIR="${2:-.}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$WORK_DIR"

START_MS=$(($(date +%s%N) / 1000000))

# --- Fetch ---
python3 "$SCRIPT_DIR/fetch_submissions.py" \
  --host "$HOST" \
  --output submissions.json \
  --batch 1 \
  --inline-testcases 1

if [ ! -f submissions.json ]; then
  echo "::error::Failed to fetch submissions"
  exit 1
fi

SUCCESS=$(jq -r '.success' submissions.json 2>/dev/null || echo "false")
if [ "$SUCCESS" != "true" ]; then
  MSG=$(jq -r '.message' submissions.json 2>/dev/null || echo "Unknown error")
  echo "::error::API error: $MSG"
  exit 1
fi

COUNT=$(jq '.submissions | length' submissions.json 2>/dev/null || echo "0")
echo "count=$COUNT"

FETCH_MS=$(($(date +%s%N) / 1000000))
echo "Fetch: $((FETCH_MS - START_MS))ms"

# --- Install missing compilers (S1 fix) ---
if [ "$COUNT" -gt 0 ]; then
  NEED_INSTALL=""

  # Check which languages are in the submissions
  LANGS=$(python3 -c "
import json
with open('submissions.json') as f:
    data = json.load(f)
langs = set()
for s in data.get('submissions', []):
    l = s.get('language', '')
    if l.startswith('java'): langs.add('java')
    elif l == 'csharp': langs.add('csharp')
    elif l == 'pascal': langs.add('pascal')
print(' '.join(sorted(langs)))
" 2>/dev/null || echo "")

  for lang in $LANGS; do
    case $lang in
      java)
        command -v javac >/dev/null 2>&1 || NEED_INSTALL="$NEED_INSTALL default-jdk"
        ;;
      csharp)
        command -v mcs >/dev/null 2>&1 || NEED_INSTALL="$NEED_INSTALL mono-mcs"
        ;;
      pascal)
        command -v fpc >/dev/null 2>&1 || NEED_INSTALL="$NEED_INSTALL fp-compiler"
        ;;
    esac
  done

  if [ -n "$NEED_INSTALL" ]; then
    echo "Installing compilers:$NEED_INSTALL"
    sudo apt-get update -qq 2>/dev/null
    sudo apt-get install -y -qq --no-install-recommends $NEED_INSTALL 2>/dev/null
  fi
fi

# --- Judge ---
if [ "$COUNT" -gt 0 ]; then
  python3 "$SCRIPT_DIR/judge.py" \
    --site-url "$HOST" \
    --submissions submissions.json \
    --work-dir judge_work
else
  echo "No pending submissions to judge"
  echo '{"status":"skip","message":"No pending submissions"}' > judge_result.json
  echo "SKIP" > status.txt
  echo "## HhOJ Judge Result" > summary.md
  echo "" >> summary.md
  echo "**Status**: No pending submissions" >> summary.md
fi

END_MS=$(($(date +%s%N) / 1000000))
echo "Judge: $((END_MS - FETCH_MS))ms"
echo "Total: $((END_MS - START_MS))ms"
