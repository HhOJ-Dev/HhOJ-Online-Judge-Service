#!/bin/bash
# Single-step judge script: fetch → judge → report → summary
# Runs inside hhoj/judge-env container, eliminating all install steps.
set -euo pipefail

HOST="${1%/}"
API_KEY="$2"
WORK_DIR="${3:-.}"

cd "$WORK_DIR"

# --- Fetch ---
python3 blankend/fetch_submissions.py \
  --host "$HOST" \
  --api-key "$API_KEY" \
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
echo "host=$HOST"

# --- Judge ---
if [ "$COUNT" -gt 0 ]; then
  cd blankend
  python3 judge.py \
    --api-key "$API_KEY" \
    --site-url "$HOST" \
    --submissions ../submissions.json \
    --work-dir ../judge_work
else
  echo "No pending submissions to judge"
  echo '{"status":"skip","message":"No pending submissions"}' > ../judge_result.json
  echo "SKIP" > ../status.txt
  echo "## HhOJ Judge Result" > ../summary.md
  echo "" >> ../summary.md
  echo "**Status**: No pending submissions" >> ../summary.md
fi