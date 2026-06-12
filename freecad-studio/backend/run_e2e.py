"""Start backend (if needed) and run E2E tests."""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = Path(r"C:\Program Files\FreeCAD 1.1\bin\python.exe")
API = "http://127.0.0.1:8787/api/status"


def api_up() -> bool:
    try:
        with urllib.request.urlopen(API, timeout=2) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> int:
    proc = None
    if not api_up():
        print("Starting backend…")
        proc = subprocess.Popen(
            [str(PY), "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8787"],
            cwd=str(ROOT),
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for _ in range(30):
            if api_up():
                break
            time.sleep(1)
        if not api_up():
            print("Backend failed to start")
            if proc:
                proc.terminate()
            return 1

    result = subprocess.call([str(PY), str(ROOT / "test_e2e.py")])
    if proc:
        proc.terminate()
    return result


if __name__ == "__main__":
    sys.exit(main())