#!/usr/bin/env python3
"""Wrapper script for Judge Worker 1.
Provides a direct entry point to run the persistent judge worker.
"""

import sys
from judge_worker import main

if __name__ == "__main__":
    # Forward all command-line arguments to the original main implementation.
    sys.argv[0] = "judge-1.py"
    main()
