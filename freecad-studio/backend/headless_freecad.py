"""Headless FreeCAD execution via FreeCADCmd (no GUI / RPC required)."""
from __future__ import annotations

import glob
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CMD = Path(r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe")

_cached_cmd: str | None = None


def _config_cmd_path() -> Path | None:
    cfg = ROOT / "config.toml"
    if not cfg.exists():
        return None
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "freecad_cmd_path":
            path = value.strip().strip('"').strip("'")
            if path:
                return Path(path)
    return None


def find_freecad_cmd() -> str:
    """Locate FreeCADCmd.exe (or equivalent) on this machine."""
    global _cached_cmd
    if _cached_cmd:
        return _cached_cmd

    env_path = os.environ.get("FREECAD_CMD_PATH") or os.environ.get("FREECAD_PATH")
    if env_path and os.path.isfile(env_path):
        _cached_cmd = os.path.abspath(env_path)
        return _cached_cmd

    cfg_path = _config_cmd_path()
    if cfg_path and cfg_path.is_file():
        _cached_cmd = str(cfg_path.resolve())
        return _cached_cmd

    if DEFAULT_CMD.is_file():
        _cached_cmd = str(DEFAULT_CMD)
        return _cached_cmd

    for name in ("FreeCADCmd", "freecadcmd"):
        found = shutil.which(name)
        if found:
            _cached_cmd = os.path.abspath(found)
            return _cached_cmd

    if platform.system() == "Windows":
        patterns = [
            "C:/Program Files/FreeCAD*/bin/FreeCADCmd.exe",
            "C:/Program Files (x86)/FreeCAD*/bin/FreeCADCmd.exe",
        ]
        for pattern in patterns:
            matches = sorted(glob.glob(pattern), reverse=True)
            if matches:
                _cached_cmd = os.path.abspath(matches[0])
                return _cached_cmd

    if platform.system() == "Darwin":
        for mac_path in (
            "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd",
            "/Applications/FreeCAD.app/Contents/MacOS/FreeCAD",
        ):
            if os.path.isfile(mac_path):
                _cached_cmd = mac_path
                return _cached_cmd

    if platform.system() == "Linux":
        for linux_path in ("/usr/bin/freecadcmd", "/usr/bin/freecad", "/snap/bin/freecad"):
            if os.path.isfile(linux_path):
                _cached_cmd = linux_path
                return _cached_cmd

    raise RuntimeError(
        "FreeCADCmd not found. Install FreeCAD or set freecad_cmd_path in config.toml"
    )


def is_ready() -> bool:
    try:
        find_freecad_cmd()
        return True
    except RuntimeError:
        return False


def cmd_path_display() -> str | None:
    try:
        return find_freecad_cmd()
    except RuntimeError:
        return None


def _write_temp_script(content: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".py", prefix="pf_headless_")
    try:
        os.write(fd, content.encode("utf-8"))
    finally:
        os.close(fd)
    return path


def _normalize_result(returncode: int, stdout: str, stderr: str) -> dict[str, Any]:
    out = (stdout or "").strip()
    err = (stderr or "").strip()
    combined = out
    if err:
        combined = f"{out}\n{err}".strip() if out else err

    if returncode != 0:
        detail = err or out or f"FreeCADCmd exited with code {returncode}"
        return {"success": False, "message": combined, "error": detail}

    if "Traceback (most recent call last)" in out or "Traceback (most recent call last)" in err:
        detail = err or out
        return {"success": False, "message": combined, "error": detail}

    return {"success": True, "message": out or "OK", "error": None}


def run_script(content: str, *, timeout: int = 180) -> dict[str, Any]:
    """Execute Python in a fresh FreeCADCmd process."""
    freecad = find_freecad_cmd()
    script_path = _write_temp_script(content)
    try:
        proc = subprocess.run(
            [freecad, script_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(ROOT),
        )
        return _normalize_result(proc.returncode, proc.stdout, proc.stderr)
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": "",
            "error": f"FreeCADCmd timed out after {timeout}s",
        }
    except FileNotFoundError as exc:
        return {"success": False, "message": "", "error": str(exc)}
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def count_solids_script(doc_name: str) -> str:
    safe = doc_name.replace('"', "")
    return f'''
import FreeCAD as App
doc = App.getDocument("{safe}") if "{safe}" in App.listDocuments() else None
count = 0
if doc:
    for o in doc.Objects:
        shape = getattr(o, "Shape", None)
        if shape and not shape.isNull() and shape.Volume > 1e-6:
            count += 1
print("SOLID_COUNT:", count)
'''


def parse_solid_count(result: dict[str, Any]) -> int | None:
    if not result.get("success"):
        return None
    match = re.search(r"SOLID_COUNT:\s*(\d+)", result.get("message") or "")
    return int(match.group(1)) if match else None


def export_viewer_stl_script(doc_name: str, out_path: Path) -> str:
    safe_doc = doc_name.replace('"', "")
    out_escaped = str(out_path).replace("\\", "\\\\")
    return f'''
import FreeCAD as App
import Mesh

DOC = "{safe_doc}"
doc = App.getDocument(DOC) if DOC in App.listDocuments() else None
if doc is None:
    raise RuntimeError("Document not open: " + DOC)
mesh = Mesh.Mesh()
count = 0
for obj in doc.Objects:
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull() or shape.Volume <= 1e-6:
        continue
    mesh.addFacets(shape.tessellate(0.1))
    count += 1
if count == 0:
    raise RuntimeError("No solids to preview in " + DOC)
mesh.write(r"{out_escaped}")
print("Viewer STL:", count, "solids")
'''


def introspect_objects_script(doc_name: str) -> str:
    safe = doc_name.replace('"', "")
    return f'''
import json
import FreeCAD as App

doc = App.getDocument("{safe}") if "{safe}" in App.listDocuments() else None
objects = []
if doc:
    for obj in doc.Objects:
        entry = {{"Name": obj.Name, "TypeId": getattr(obj, "TypeId", ""), "Label": getattr(obj, "Label", obj.Name)}}
        shape = getattr(obj, "Shape", None)
        if shape and not shape.isNull():
            entry["Shape"] = {{
                "Volume": float(shape.Volume),
                "FaceCount": len(shape.Faces),
                "EdgeCount": len(shape.Edges),
            }}
        objects.append(entry)
print("PF_OBJECTS_JSON:", json.dumps(objects))
'''


def parse_objects_json(result: dict[str, Any]) -> list[dict[str, Any]]:
    if not result.get("success"):
        return []
    text = result.get("message") or ""
    for line in text.splitlines():
        if line.startswith("PF_OBJECTS_JSON:"):
            payload = line.split(":", 1)[1].strip()
            try:
                data = json.loads(payload)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                return []
    return []
