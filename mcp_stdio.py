import os
import shutil
import subprocess
import threading
import time
from typing import List, Optional


DEFAULT_ALLOWED = os.environ.get("MCP_ALLOWED_DIRS", "/mnt/obsidian-vault")


def _choose_filesystem_cmd(allowed: List[str]) -> List[str]:
    """Pick a command to start the MCP filesystem server.

    Preference order:
      1. `mcp-server-filesystem` if installed (bin from package)
      2. `npx -y @modelcontextprotocol/server-filesystem` (will fetch and run)
    The allowed directories are appended as positional args.
    """
    if shutil.which("mcp-server-filesystem"):
        return ["mcp-server-filesystem"] + allowed

    # fallback to npx (will download the package if not present)
    if shutil.which("npx"):
        return ["npx", "-y", "@modelcontextprotocol/server-filesystem"] + allowed

    # As a last resort, try node + a relative dist path if present in cwd
    # (This is opportunistic; the folder may not exist in the webapp image.)
    if os.path.exists("/app/dist/index.js") and shutil.which("node"):
        return ["node", "/app/dist/index.js"] + allowed

    raise FileNotFoundError("No available way to start the MCP filesystem server (tried mcp-server-filesystem, npx, node)")


def start_filesystem_process(allowed_dirs: Optional[List[str]] = None, timeout: int = 10) -> subprocess.Popen:
    """Start the filesystem server as a subprocess and return the Popen object.

    The process uses pipes for stdin/stdout so callers can bridge io.
    """
    allowed = allowed_dirs or (DEFAULT_ALLOWED.split(":") if DEFAULT_ALLOWED else ["/mnt/obsidian-vault"])
    cmd = _choose_filesystem_cmd(allowed)

    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0
    )

    # Wait a short while to see if it exits immediately with error
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            # process exited
            raise RuntimeError(f"Filesystem server exited early with code {proc.returncode}: {proc.stderr.read().decode(errors='ignore')}")
        # If stdout is available (not a perfect check) assume it's up
        if proc.stdout is not None:
            break
        time.sleep(0.1)

    return proc


def _forward_stream(src, dst, stop_event: threading.Event):
    try:
        while not stop_event.is_set():
            chunk = src.read(4096)
            if not chunk:
                break
            dst.write(chunk)
            dst.flush()
    except Exception:
        # best-effort forwarding; ignore and let caller handle process termination
        pass


def bridge_processes(proc_a: subprocess.Popen, proc_b: subprocess.Popen, timeout: int = 120) -> None:
    """Bridge stdio between proc_a and proc_b until one exits or timeout.

    This sets up two threads:
      proc_a.stdout -> proc_b.stdin
      proc_b.stdout -> proc_a.stdin
    and waits for completion or timeout.
    """
    stop_event = threading.Event()

    t1 = threading.Thread(target=_forward_stream, args=(proc_a.stdout, proc_b.stdin, stop_event), daemon=True)
    t2 = threading.Thread(target=_forward_stream, args=(proc_b.stdout, proc_a.stdin, stop_event), daemon=True)

    t1.start()
    t2.start()

    start = time.time()
    try:
        while time.time() - start < timeout:
            if proc_a.poll() is not None or proc_b.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        stop_event.set()
        # give threads a moment to flush
        time.sleep(0.1)


def stop_process(proc: subprocess.Popen, grace: float = 1.0) -> None:
    try:
        if proc.poll() is None:
            proc.terminate()
            time.sleep(grace)
            if proc.poll() is None:
                proc.kill()
    except Exception:
        pass
