"""Development mode: backend with reload + Vite dev server (proxying /api to the backend)."""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import webbrowser

from launcher import BACKEND, FRONTEND, free_port, server_env, stop, wait_for_health

VITE_PORT = 5173


def main() -> None:
    npm = shutil.which("npm")
    if not npm:
        sys.exit("npm was not found. Install Node.js.")
    if not (FRONTEND / "node_modules").exists():
        subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)

    port = int(os.environ.get("LNB_HOST_PORT") or free_port())
    token = secrets.token_urlsafe(32)
    origins = f"http://127.0.0.1:{VITE_PORT},http://localhost:{VITE_PORT}"
    backend = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:create_app",
            "--factory",
            "--reload",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=BACKEND,
        env=server_env(port, token, LNB_ALLOWED_ORIGINS=origins),
    )
    vite = None
    try:
        wait_for_health(port, token, backend)
        vite = subprocess.Popen(
            [npm, "run", "dev", "--", "--strictPort"],
            cwd=FRONTEND,
            env={**os.environ, "LNB_BACKEND_PORT": str(port)},
        )
        url = f"http://127.0.0.1:{VITE_PORT}/#token={token}"
        print(f"Dev UI: {url}")
        webbrowser.open(url)
        vite.wait()
    except KeyboardInterrupt:
        pass
    finally:
        if vite:
            stop(vite)
        stop(backend)


if __name__ == "__main__":
    main()
