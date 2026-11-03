#!/usr/bin/env python3
"""README-compatible worker entry point."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worker.worker import main

if __name__ == "__main__":
    main()
