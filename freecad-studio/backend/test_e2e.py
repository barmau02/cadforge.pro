"""CadForge end-to-end API tests."""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

API = "http://127.0.0.1:8787"


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(f"{API}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            return resp.status, payload
    except urllib.error.HTTPError as exc:
        payload = json.loads(exc.read().decode("utf-8", errors="replace") or "{}")
        return exc.code, payload


def wait_for_api(seconds: int = 30) -> bool:
    for _ in range(seconds):
        try:
            with urllib.request.urlopen(f"{API}/api/status", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False


def ok(name: str, passed: bool, detail: str = "") -> bool:
    mark = "PASS" if passed else "FAIL"
    line = f"[{mark}] {name}"
    if detail:
        line += f" — {detail}"
    print(line)
    return passed


def fail_detail(code: int, payload: dict) -> str:
    return f"HTTP {code}: {payload.get('detail') or payload.get('message') or payload}"


def main() -> int:
    print("CadForge E2E tests")
    print("=" * 50)

    if not wait_for_api(5):
        print("Backend not running at", API)
        print("Start with: cd freecad-studio/backend && python -m uvicorn main:app --host 127.0.0.1 --port 8787")
        return 1

    results: list[bool] = []

    code, status = call("GET", "/api/status")
    results.append(ok("status endpoint", code == 200, f"rpc={status.get('rpc_connected')}"))
    results.append(ok("background_freecad flag", "background_freecad" in status))
    results.append(ok("job stl fields", all(k in status for k in ("job_stl_dir", "job_stl_count"))))

    code, jobs = call("GET", "/api/jobs")
    results.append(ok("list jobs", code == 200))

    code, created = call("POST", "/api/jobs", {"title": "E2E Test Bracket", "prompt": "test"})
    job = created.get("data", {}).get("job", {})
    job_id = job.get("id")
    results.append(ok("create job", code == 200 and bool(job_id), job_id or ""))

    if job_id:
        code, renamed = call("PATCH", f"/api/jobs/{job_id}", {"title": "E2E Renamed Part"})
        results.append(ok("rename job", code == 200, renamed.get("message", "")))

        code, activated = call("POST", f"/api/jobs/{job_id}/activate")
        results.append(ok("activate job", code == 200))

        if status.get("rpc_connected"):
            box_code = """
import FreeCAD as App
import Part
doc = App.activeDocument()
for obj in list(doc.Objects):
    if getattr(obj, "Shape", None) and not obj.Shape.isNull():
        doc.removeObject(obj.Name)
box = doc.addObject("Part::Box", "E2EBox")
box.Length = 40
box.Width = 20
box.Height = 10
doc.recompute()
print("E2E box created")
"""
            code, executed = call(
                "POST",
                "/api/execute",
                {"code": box_code, "job_id": job_id, "capture_preview": True, "focus_window": False},
            )
            data = executed.get("data") or {}
            exec_ok = code == 200
            results.append(
                ok(
                    "execute python",
                    exec_ok,
                    executed.get("message", "")[:80] if exec_ok else fail_detail(code, executed),
                )
            )
            results.append(
                ok(
                    "preview image returned",
                    bool(data.get("preview_image")),
                    data.get("progress", "") if data.get("preview_image") else fail_detail(code, executed),
                )
            )

            code, shot = call("GET", f"/api/screenshot?job_id={job_id}")
            results.append(
                ok(
                    "screenshot api",
                    code == 200 and bool(shot.get("image")),
                    "" if code == 200 else fail_detail(code, shot),
                )
            )

            code, exported = call("POST", "/api/export/stl", {})
            exp = exported.get("data") or {}
            results.append(
                ok(
                    "export stl per job",
                    code == 200 and job_id in str(exp.get("dir", "")),
                    exp.get("dir", "") if code == 200 else fail_detail(code, exported),
                )
            )

            code, status2 = call("GET", "/api/status")
            results.append(
                ok(
                    "status reflects job stl",
                    status2.get("job_stl_count", 0) > 0,
                    f"count={status2.get('job_stl_count')}",
                )
            )
        else:
            print("[SKIP] FreeCAD RPC offline — execute/screenshot/export tests skipped")

        code, deleted = call("DELETE", f"/api/jobs/{job_id}")
        results.append(ok("delete job", code == 200, deleted.get("message", "")))

    passed = sum(results)
    total = len(results)
    print("=" * 50)
    print(f"Results: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())