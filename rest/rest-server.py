#!/usr/bin/env python3
"""README-compatible entry point; run from any directory."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from rest.rest_server import app

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
