"""CadForge job manager — one FreeCAD document per design job."""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from freecad_client import FreeCADClient

ROOT = Path(__file__).resolve().parent.parent
JOBS_DIR = ROOT / "jobs"
REGISTRY_FILE = JOBS_DIR / "registry.json"

INITIAL_CODE = "# Python appears here after you prompt\n"


def _now() -> float:
    return time.time()


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def activate_document_code(doc_name: str) -> str:
    safe = doc_name.replace('"', "")
    return f'''
import FreeCAD as App
import FreeCADGui as Gui

DOC_NAME = "{safe}"
try:
    doc = App.getDocument(DOC_NAME)
except Exception:
    doc = None
if doc is None:
    doc = App.newDocument(DOC_NAME)
try:
    gui_doc = Gui.getDocument(doc.Name)
except Exception:
    gui_doc = None
if gui_doc is None:
    Gui.addDocument(doc)
Gui.setActiveDocument(doc.Name)
Gui.ActiveDocument = Gui.getDocument(doc.Name)
print("Active document:", doc.Name)
'''


def wrap_code_for_job(code: str, doc_name: str) -> str:
    return activate_document_code(doc_name).strip() + "\n\n" + code.strip()


def job_fcstd_dir(job_id: str) -> Path:
    return JOBS_DIR / job_id


def job_fcstd_path(job_id: str, doc_name: str | None = None) -> Path:
    stem = doc_name or "model"
    safe = re.sub(r'[<>:"/\\|?*]', "_", stem)
    return job_fcstd_dir(job_id) / f"{safe}.FCStd"


def headless_open_document_code(doc_name: str, job_id: str) -> str:
    safe_doc = doc_name.replace('"', "")
    fcstd = job_fcstd_path(job_id, doc_name)
    fcstd_esc = str(fcstd).replace("\\", "\\\\")
    return f'''
import os
import FreeCAD as App

DOC_NAME = "{safe_doc}"
FCSTD = r"{fcstd_esc}"
os.makedirs(os.path.dirname(FCSTD), exist_ok=True)

try:
    doc = App.getDocument(DOC_NAME)
except Exception:
    doc = None
if doc is None:
    if os.path.isfile(FCSTD):
        doc = App.openDocument(FCSTD)
    else:
        doc = App.newDocument(DOC_NAME)
'''


def headless_wrap_code_for_job(code: str, doc_name: str, job_id: str) -> str:
    """Run user code in FreeCADCmd with document load/save via FCStd on disk."""
    fcstd = job_fcstd_path(job_id, doc_name)
    fcstd_esc = str(fcstd).replace("\\", "\\\\")
    return (
        headless_open_document_code(doc_name, job_id).strip()
        + "\n\n"
        + code.strip()
        + f'''

doc.recompute()
doc.saveAs(r"{fcstd_esc}")
print("Saved:", r"{fcstd_esc}")
'''
    )


def _default_registry() -> dict[str, Any]:
    return {"active_job_id": None, "jobs": []}


def _load_registry() -> dict[str, Any]:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    if not REGISTRY_FILE.exists():
        return _default_registry()
    try:
        data = json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("jobs"), list):
            return data
    except Exception:
        pass
    return _default_registry()


def _save_registry(data: dict[str, Any]) -> None:
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _freecad_doc_name(job_id: str) -> str:
    return f"PF_{job_id[:8]}"


def _slug_title(text: str, max_len: int = 48) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text).strip()
    if not cleaned:
        return "Untitled part"
    return cleaned[:max_len]


def load_job(job_id: str) -> dict[str, Any] | None:
    path = _job_path(job_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_job(job: dict[str, Any]) -> dict[str, Any]:
    job["updated_at"] = _now()
    _job_path(job["id"]).write_text(json.dumps(job, indent=2), encoding="utf-8")
    reg = _load_registry()
    summary = {
        "id": job["id"],
        "title": job["title"],
        "freecad_doc": job["freecad_doc"],
        "status": job.get("status", "new"),
        "created_at": job.get("created_at", _now()),
        "updated_at": job["updated_at"],
    }
    jobs = [j for j in reg.get("jobs", []) if j.get("id") != job["id"]]
    jobs.insert(0, summary)
    reg["jobs"] = jobs[:50]
    if reg.get("active_job_id") == job["id"]:
        reg["active_job_id"] = job["id"]
    _save_registry(reg)
    return job


def list_jobs() -> dict[str, Any]:
    reg = _load_registry()
    active_id = reg.get("active_job_id")
    jobs = reg.get("jobs", [])
    active = load_job(active_id) if active_id else None
    return {"active_job_id": active_id, "jobs": jobs, "active_job": active}


def get_active_job() -> dict[str, Any] | None:
    reg = _load_registry()
    active_id = reg.get("active_job_id")
    if not active_id:
        return None
    return load_job(active_id)


def set_active_job(job_id: str) -> dict[str, Any]:
    job = load_job(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")
    reg = _load_registry()
    reg["active_job_id"] = job_id
    _save_registry(reg)
    return job


def create_job(title: str = "Untitled part", prompt: str = "") -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    title = _slug_title(title or prompt or "Untitled part")
    job = {
        "id": job_id,
        "title": title,
        "freecad_doc": _freecad_doc_name(job_id),
        "prompt": prompt,
        "code": INITIAL_CODE,
        "status": "new",
        "created_at": _now(),
        "updated_at": _now(),
    }
    save_job(job)
    reg = _load_registry()
    reg["active_job_id"] = job_id
    _save_registry(reg)
    return job


def ensure_active_job(title: str = "Untitled part", prompt: str = "") -> dict[str, Any]:
    job = get_active_job()
    if job is not None:
        return job
    return create_job(title=title, prompt=prompt)


def update_job_fields(job_id: str, **fields: Any) -> dict[str, Any]:
    job = load_job(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")
    for key, value in fields.items():
        if value is not None:
            job[key] = value
    return save_job(job)


def append_prompt_history(job_id: str, prompt: str, *, kind: str = "build") -> dict[str, Any]:
    """Append a user request to the job conversation (deduped if identical to last entry)."""
    job = load_job(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")
    text = prompt.strip()
    if not text:
        return job

    history: list[dict[str, Any]] = list(job.get("prompt_history") or [])
    if not history and job.get("prompt") and job["prompt"].strip() and job["prompt"].strip() != text:
        history.append({
            "prompt": job["prompt"].strip(),
            "kind": "original",
            "at": job.get("created_at", _now()),
        })

    if history and history[-1].get("prompt") == text and history[-1].get("kind") == kind:
        job["prompt"] = text
        return save_job(job)

    history.append({"prompt": text, "kind": kind, "at": _now()})
    job["prompt_history"] = history[-30:]
    job["prompt"] = text
    return save_job(job)


def design_conversation_context(job: dict[str, Any]) -> str:
    """Full design conversation for the LLM — original request plus follow-up edits."""
    history: list[dict[str, Any]] = list(job.get("prompt_history") or [])
    if not history:
        return (job.get("prompt") or "").strip()

    parts: list[str] = []
    for idx, entry in enumerate(history, start=1):
        text = str(entry.get("prompt") or "").strip()
        if not text:
            continue
        kind = str(entry.get("kind") or "note")
        if kind == "original":
            parts.append(f"Original design request:\n{text}")
        elif kind == "edit":
            parts.append(f"Change request {idx}:\n{text}")
        elif kind == "param":
            parts.append(f"Manual parameter change:\n{text}")
        elif kind == "build":
            parts.append(f"Build request {idx}:\n{text}")
        else:
            parts.append(f"{kind}:\n{text}")

    return "\n\n".join(parts)


def activate_job_in_freecad(fc: FreeCADClient, job: dict[str, Any]) -> dict[str, Any]:
    return fc.execute_code(activate_document_code(job["freecad_doc"]))


def job_stl_dir(output_dir: Path, job_id: str) -> Path:
    return output_dir / job_id


def is_export_stl_name(name: str) -> bool:
    """Exclude preview/viewer meshes — not real print exports."""
    lower = name.lower()
    return not (lower.startswith("_viewer") or lower.startswith("_preview"))


def exportable_stl_paths(job_dir: Path) -> list[Path]:
    if not job_dir.exists():
        return []
    merged = job_dir / f"{EXPORT_STL_BASENAME}.stl"
    if merged.exists():
        return [merged]
    return sorted(p for p in job_dir.glob("*.stl") if is_export_stl_name(p.name))


def list_job_stl_files(output_dir: Path, job_id: str) -> list[str]:
    job_dir = job_stl_dir(output_dir, job_id)
    return [p.name for p in exportable_stl_paths(job_dir)]


def delete_job(job_id: str) -> dict[str, Any] | None:
    job = load_job(job_id)
    if job is None:
        return None

    reg = _load_registry()
    jobs = [j for j in reg.get("jobs", []) if j.get("id") != job_id]
    reg["jobs"] = jobs
    if reg.get("active_job_id") == job_id:
        reg["active_job_id"] = jobs[0]["id"] if jobs else None
    _save_registry(reg)

    path = _job_path(job_id)
    if path.exists():
        path.unlink()
    fcstd_dir = job_fcstd_dir(job_id)
    if fcstd_dir.exists():
        import shutil

        shutil.rmtree(fcstd_dir, ignore_errors=True)
    return job


def close_document_code(doc_name: str) -> str:
    safe = doc_name.replace('"', "")
    return f'''
import FreeCAD as App
if "{safe}" in App.listDocuments():
    App.closeDocument("{safe}")
    print("Closed document:", "{safe}")
else:
    print("Document not open:", "{safe}")
'''


_SLICE_KEEP_NAMES = frozenset({"readme", "readme.md", ".gitkeep"})


def _is_slice_artifact_name(name: str) -> bool:
    lower = name.lower()
    if lower.startswith("_viewer") or lower.startswith("_preview"):
        return True
    return lower.endswith((".stl", ".gcode", ".3mf", ".gcode.3mf"))


def clear_job_gcode_dir(output_dir: Path, job_id: str) -> None:
    job_dir = job_stl_dir(output_dir, job_id)
    if not job_dir.exists():
        return
    for path in job_dir.iterdir():
        if not path.is_file():
            continue
        if _is_slice_artifact_name(path.name) and not path.name.lower().endswith(".stl"):
            path.unlink()


def clear_job_stl_dir(output_dir: Path, job_id: str) -> None:
    job_dir = job_stl_dir(output_dir, job_id)
    if not job_dir.exists():
        return
    for path in job_dir.glob("*.stl"):
        if is_export_stl_name(path.name):
            path.unlink()


def clear_job_slice_dir(output_dir: Path, job_id: str) -> None:
    """Remove all slice/export artifacts from a job folder (keeps README/.gitkeep only)."""
    job_dir = job_stl_dir(output_dir, job_id)
    if not job_dir.exists():
        return
    for path in job_dir.iterdir():
        if not path.is_file():
            continue
        if path.name.lower() in _SLICE_KEEP_NAMES:
            continue
        path.unlink()


# Single merged STL per job — Orca treats each file as a separate bed object.
EXPORT_STL_BASENAME = "model"


def export_job_stl_code(doc_name: str, output_dir: Path, job_id: str) -> str:
    out = str(output_dir / job_id).replace("\\", "\\\\")
    safe_doc = doc_name.replace('"', "")
    stl_name = EXPORT_STL_BASENAME
    return f'''
import os
import re
import FreeCAD as App
import Mesh

DOC = "{safe_doc}"
OUT = r"{out}"
STL_NAME = "{stl_name}"
MIN_VOLUME_MM3 = 1.0
SKIP_PREFIXES = ("PFClip_", "_")

os.makedirs(OUT, exist_ok=True)
for old in os.listdir(OUT):
    if old.lower().endswith(".stl"):
        os.remove(os.path.join(OUT, old))
try:
    doc = App.getDocument(DOC)
except Exception:
    doc = None
if doc is None:
    raise RuntimeError("Document not found: " + DOC)


def _skip_name(name):
    return any(name.startswith(p) for p in SKIP_PREFIXES)


def _part_type(type_id):
    return bool(type_id) and type_id.startswith("Part::")


def _base_stem(name):
    match = re.match(r"^(.+?)(\\d+)$", name)
    return match.group(1) if match else name


def _shape_fingerprint(shape):
    bb = shape.BoundBox
    return (
        round(float(shape.Volume), 1),
        round(float(bb.XLength), 2),
        round(float(bb.YLength), 2),
        round(float(bb.ZLength), 2),
    )


def _name_rank(name):
    suffix = re.search(r"(\\d+)$", name)
    suffix_len = len(suffix.group(1)) if suffix else 0
    return (-suffix_len, len(name), name)


candidates = []
for obj in doc.Objects:
    if _skip_name(obj.Name):
        continue
    if not _part_type(getattr(obj, "TypeId", "")):
        continue
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull():
        continue
    if not shape.isValid():
        continue
    if float(shape.Volume) <= MIN_VOLUME_MM3:
        continue
    if len(shape.Faces) == 0:
        continue
    fp = _shape_fingerprint(shape)
    vol = float(shape.Volume)
    candidates.append((fp, _name_rank(obj.Name), obj.Name, shape, vol))

by_stem = {{}}
for fp, rank, name, shape, vol in candidates:
    stem = _base_stem(name)
    prev = by_stem.get(stem)
    if prev is None or rank > prev[0] or (rank == prev[0] and vol > prev[4]):
        by_stem[stem] = (rank, name, shape, fp, vol)

by_fp = {{}}
for _rank, name, shape, fp, _vol in by_stem.values():
    prev = by_fp.get(fp)
    cur_rank = _name_rank(name)
    if prev is None or cur_rank > prev[0]:
        by_fp[fp] = (cur_rank, name, shape)

unique = list(by_fp.values())
if not unique:
    raise RuntimeError("No exportable solids in " + DOC)

if len(unique) > 1:
    vols = [float(s.Volume) for _, _, s in unique]
    vmax = max(vols)
    if vmax > 0 and (vmax - min(vols)) / vmax < 0.02:
        unique = [max(unique, key=lambda item: _name_rank(item[1]))]

volumes = sorted((float(s.Volume) for _, _, s in unique), reverse=True)
if len(volumes) > 1 and volumes[0] > 2.0 * max(volumes[1], 1.0):
    max_vol = volumes[0]
    unique = [(r, n, s) for r, n, s in unique if float(s.Volume) >= max_vol * 0.98]

mesh = Mesh.Mesh()
included = []
for _rank, name, shape in unique:
    part = Mesh.Mesh()
    part.addFacets(shape.tessellate(0.12))
    if part.CountFacets == 0:
        continue
    mesh.addMesh(part)
    included.append(name)

if mesh.CountFacets == 0:
    raise RuntimeError("No tessellatable solids in " + DOC)

bb = mesh.BoundBox
dx = -(bb.XMin + bb.XMax) / 2.0
dy = -(bb.YMin + bb.YMax) / 2.0
dz = -bb.ZMin
if abs(dx) > 1e-9 or abs(dy) > 1e-9 or abs(dz) > 1e-9:
    mesh.translate(dx, dy, dz)

path = os.path.join(OUT, STL_NAME + ".stl")
mesh.write(path)
print("Included solids:", included)
print("Exported", path)
print("Files:", [path])
'''