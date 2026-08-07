#!/usr/bin/env python3
"""Wrapper script for Judge Worker 2.
Provides a direct entry point to run the persistent judge worker.
"""

import sys
from judge_worker import main

if __name__ == "__main__":
    sys.argv[0] = "judge-2.py"
    main()
