"""Start the server on a free local port and open the browser with a per-launch token.

Used by scripts/run.* (production build served by the backend) and scripts/dev.py (reload + Vite).
"""

from __future__ import annotations

import os
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
BACKEND = ROOT / "backend"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def npm(*args: str) -> None:
    exe = shutil.which("npm")
    if not exe:
        sys.exit("npm was not found. Install Node.js to build the frontend.")
    subprocess.run([exe, *args], cwd=FRONTEND, check=True)


def build_frontend_if_needed() -> None:
    if (FRONTEND / "dist" / "index.html").exists():
        return
    print("Building the frontend (first run)...")
    npm("ci")
    npm("run", "build")


def wait_for_health(port: int, token: str, proc: subprocess.Popen, timeout: float = 30) -> None:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/health", headers={"Authorization": f"Bearer {token}"}
    )
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            sys.exit("The server exited during startup.")
        try:
            with urllib.request.urlopen(req, timeout=1):
                return
        except (urllib.error.URLError, OSError):
            time.sleep(0.2)
    sys.exit("The server did not become ready in time.")


def server_env(port: int, token: str, **extra: str) -> dict[str, str]:
    return {**os.environ, "LNB_HOST_PORT": str(port), "LNB_TOKEN": token, **extra}


def stop(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> None:
    build_frontend_if_needed()
    port = int(os.environ.get("LNB_HOST_PORT") or free_port())
    token = secrets.token_urlsafe(32)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=BACKEND,
        env=server_env(port, token),
    )
    try:
        wait_for_health(port, token, proc)
        url = f"http://127.0.0.1:{port}/#token={token}"
        print(f"LocalNotebook is running at http://127.0.0.1:{port}/  (Ctrl+C to stop)")
        webbrowser.open(url)
        proc.wait()
    except KeyboardInterrupt:
        pass
    finally:
        stop(proc)


if __name__ == "__main__":
    main()
