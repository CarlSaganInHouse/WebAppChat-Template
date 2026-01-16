#!/usr/bin/env python3
"""Stub: moved to scripts/manage.py"""
import subprocess
import sys
from pathlib import Path

script = Path(__file__).parent / "scripts" / "manage.py"
sys.exit(subprocess.call([sys.executable, str(script)] + sys.argv[1:]))
