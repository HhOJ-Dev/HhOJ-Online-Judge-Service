#!/bin/bash
# Unified judge: single Python process, shared session (challenge solved once)
set -euo pipefail

HOST="${1%/}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Install missing compilers only if needed (gcc/g++ preinstalled on ubuntu)
LANGS=$(python3 -c "
import json, sys
try:
    with open('submissions.json') as f:
        data = json.load(f)
    for s in data.get('submissions', []):
        print(s.get('language', ''))
except: pass
" 2>/dev/null || echo "")

# Run unified judge (fetch + judge + report in one process)
python3 "$SCRIPT_DIR/main.py" --host "$HOST"
