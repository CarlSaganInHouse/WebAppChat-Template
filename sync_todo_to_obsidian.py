#!/usr/bin/env python3
"""Stub: moved to scripts/sync_todo_to_obsidian.py"""
import subprocess
import sys
from pathlib import Path

script = Path(__file__).parent / "scripts" / "sync_todo_to_obsidian.py"
sys.exit(subprocess.call([sys.executable, str(script)] + sys.argv[1:]))
