#!/usr/bin/env python3
"""Stub: moved to scripts/generate_webdav_credentials.py"""
import subprocess
import sys
from pathlib import Path

script = Path(__file__).parent / "scripts" / "generate_webdav_credentials.py"
sys.exit(subprocess.call([sys.executable, str(script)] + sys.argv[1:]))
