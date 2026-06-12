from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import base64

from freecad_client import FreeCADClient
import headless_freecad as hl
import freecad_executor as fe
from freecad_window import (
    cancel_background_minimize,
    focus_freecad_window,
    launch_freecad_gui,
    minimize_freecad_window,
)
from preview_capture import capture_multiview_images, capture_preview_image
import vision_capture as vision_cap
from grok_image import resolve_grok_config
from image_context import (
    GLOBAL_CONTEXT_HINT,
    bootstrap_context_images,
    bootstrap_view_defaults,
    context_pool_from_entries,
    expand_from_critique,
    generate_context_previews,
)
from llm import (
    critique_model,
    extract_required_features,
    fix_freecad_code,
    fix_from_critique,
    generate_freecad_code,
    is_vision_model,
    lessons_prompt_suffix,
    list_ai_models,
    resolve_ai_config,
)
import secrets_store as secrets
from settings_api import apply_settings_update, public_settings
import model_memory
import jobs as job_store
from presets import BOAT_FCSTD, PRINT_DIR, boat_code, export_stl_code
from creality_preflight import preflight_send, wait_for_catalog_entry_sync
from creality_status import live_status
from creality_camera import camera_info, fetch_snapshot, webrtc_exchange
from creality_send import (
    find_gcode_file,
    prepare_k2_upload,
    start_print,
    upload_gcode,
    _gcode_storage_path,
)
from feature_tree import build_feature_tree, features_from_code_comment, patch_parameter
from gcode_meta import extract_gcode_thumbnail, gcode_matches_stls, parse_gcode_meta, read_gcode_preview_text
from orca_slice import resolve_print_bed, slice_stls
from printer_network import printer_status

ROOT = Path(__file__).resolve().parent.parent
CONFIG_FILE = ROOT / "config.toml"
FRONTEND = ROOT / "frontend"
FREECAD_EXE = Path(r"C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe")
FREECAD_CMD = Path(r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe")
ORCA_EXE = Path(r"C:\Program Files\OrcaSlicer\orca-slicer.exe")
CREALITY_PRINT_CANDIDATES = [
    Path(r"C:\Program Files\Creality Print\CrealityPrint.exe"),
    Path(r"C:\Program Files\Creality Print 6\CrealityPrint.exe"),
    Path(r"C:\Program Files\Creality Print 7\CrealityPrint.exe"),
    Path(r"C:\Program Files\Creality\Creality Print\CrealityPrint.exe"),
    Path(r"C:\Program Files (x86)\Creality Print\CrealityPrint.exe"),
    Path(r"C:\Program Files\CrealityPrint\CrealityPrint.exe"),
]
CREALITY_PRINT_DOWNLOAD = "https://github.com/CrealityOfficial/CrealityPrint/releases/latest"
START_RPC_MACRO = Path(os.environ.get("APPDATA", "")) / "FreeCAD" / "v1-1" / "Macro" / "StartMCPOnly.FCMacro"

app = FastAPI(title="CadForge", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = FreeCADClient()


def _check_rpc() -> bool:
    return client.ping_health()


@app.on_event("startup")
def _startup_reconnect_rpc() -> None:
    cfg = _load_config()
    secrets.migrate_from_config(cfg)
    from settings_api import _remove_config_keys as _strip_config_secrets

    _strip_config_secrets(CONFIG_FILE, ("ollama_api_key", "api_key", "grok_api_key"))
    if _use_headless():
        return
    if _check_rpc():
        return
    if _freecad_running():
        _wait_for_rpc(20)
        return
    if FREECAD_EXE.exists() and START_RPC_MACRO.exists():
        launch_freecad_gui(
            str(FREECAD_EXE),
            str(START_RPC_MACRO),
            focus=not _background_freecad(),
            minimize=_background_freecad(),
        )
        _wait_for_rpc(45)


class ExecuteRequest(BaseModel):
    code: str
    capture_preview: bool = True
    job_id: str | None = None
    focus_window: bool | None = None
    auto_fix: bool = True


class ExportRequest(BaseModel):
    doc_name: str = "Boat"
    target_length_mm: float = Field(default=200.0, ge=10, le=500)


class ActionResult(BaseModel):
    ok: bool
    message: str
    data: dict | None = None


class PromptRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    execute: bool = True
    image_base64: str | None = Field(default=None, max_length=12_000_000)
    image_mime: str | None = None
    existing_code: str | None = Field(default=None, max_length=200_000)
    edit_mode: bool = False
    use_scene_preview: bool = True
    job_id: str | None = None
    global_image_context: str = Field(default="", max_length=2000)
    context_view_specs: list[dict[str, Any]] | None = None
    context_images: list[dict[str, Any]] | None = None


class ContextViewInput(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    prompt: str = Field(min_length=1, max_length=4000)
    enabled: bool = True
    title: str | None = None


class ContextGenerateRequest(BaseModel):
    image_base64: str = Field(min_length=100, max_length=12_000_000)
    image_mime: str | None = None
    global_context: str = Field(default="", max_length=2000)
    views: list[ContextViewInput] | None = None
    only_label: str | None = Field(default=None, max_length=80)
    chain_anchor_base64: str | None = Field(default=None, max_length=12_000_000)
    chain_anchor_mime: str | None = None


class JobCreateRequest(BaseModel):
    title: str = Field(default="Untitled part", max_length=120)
    prompt: str = ""


class JobUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    prompt: str | None = None
    code: str | None = Field(default=None, max_length=200_000)
    status: str | None = None


class AiModelRequest(BaseModel):
    model: str = Field(min_length=1, max_length=120)


class SendPrintRequest(BaseModel):
    gcode_file: str | None = None


class WebRtcOfferRequest(BaseModel):
    offer: str = Field(min_length=8, max_length=500_000)


class SliceRequest(BaseModel):
    refresh_cad: bool = False
    wipe_slice: bool = False


class BuildLoopRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=4000)
    job_id: str | None = None
    max_iterations: int = Field(default=6, ge=1, le=8)
    target_score: int = Field(default=80, ge=50, le=100)
    image_base64: str | None = Field(default=None, max_length=12_000_000)
    image_mime: str | None = None
    edit_mode: bool = False
    existing_code: str | None = Field(default=None, max_length=200_000)
    global_image_context: str = Field(default="", max_length=2000)
    context_view_specs: list[dict[str, Any]] | None = None
    context_images: list[dict[str, Any]] | None = None


class FeatureParamPatchRequest(BaseModel):
    job_id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    value: float | int | str
    rerun: bool = True


class FeatureConfigPatchRequest(BaseModel):
    key: str = Field(min_length=1, max_length=80)
    value: str = Field(min_length=1, max_length=200)


class SettingsUpdateRequest(BaseModel):
    ollama_api_key: str | None = Field(default=None, max_length=500)
    grok_api_key: str | None = Field(default=None, max_length=500)
    ai_provider: str | None = Field(default=None, max_length=40)
    api_url: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=120)
    grok_image_model: str | None = Field(default=None, max_length=80)
    grok_api_url: str | None = Field(default=None, max_length=200)
    image_gen_enabled: bool | None = None


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def _background_freecad() -> bool:
    return _truthy(_load_config().get("background_freecad", "true"))


def _freecad_mode() -> str:
    return (_load_config().get("freecad_mode") or "headless").strip().lower()


def _use_headless() -> bool:
    return _freecad_mode() != "rpc"


def _vision_capture_mode() -> str:
    return (_load_config().get("vision_capture") or "auto").strip().lower()


def _cad_ready() -> bool:
    if _use_headless():
        return hl.is_ready()
    return _check_rpc()


def _should_focus_window(override: bool | None = None) -> bool:
    if override is not None:
        return override
    return not _background_freecad()


def _maybe_focus_freecad(override: bool | None = None) -> None:
    if _should_focus_window(override):
        focus_freecad_window()


def _job_stl_info(job: dict | None) -> dict:
    if not job:
        return {
            "job_stl_dir": None,
            "job_stl_files": [],
            "job_stl_ready": False,
            "job_stl_count": 0,
        }
    job_dir = job_store.job_stl_dir(PRINT_DIR, job["id"])
    files = job_store.list_job_stl_files(PRINT_DIR, job["id"])
    return {
        "job_stl_dir": str(job_dir),
        "job_stl_files": files,
        "job_stl_ready": len(files) > 0,
        "job_stl_count": len(files),
    }


def _load_config() -> dict[str, str]:
    cfg: dict[str, str] = {}
    if not CONFIG_FILE.exists():
        return cfg
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        raw = value.strip().strip('"').strip("'")
        if "#" in raw:
            raw = raw.split("#", 1)[0].strip()
        cfg[key.strip()] = raw
    return cfg


def _save_config_value(key: str, value: str) -> None:
    lines = CONFIG_FILE.read_text(encoding="utf-8").splitlines() if CONFIG_FILE.exists() else []
    out: list[str] = []
    found = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#") or "=" not in stripped:
            out.append(line)
            continue
        k, _, _ = stripped.partition("=")
        if k.strip() == key:
            out.append(f'{key} = "{value}"')
            found = True
        else:
            out.append(line)
    if not found:
        out.append(f'{key} = "{value}"')
    CONFIG_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")


def _normalize_image_b64(raw: str | None) -> str | None:
    if not raw:
        return None
    data = raw.strip()
    if data.startswith("data:") and "," in data:
        data = data.split(",", 1)[1]
    return data or None


def _ai_info() -> dict:
    return resolve_ai_config(_load_config())


def _slicer_info() -> dict:
    cfg = _load_config()
    pref = cfg.get("slicer_preference", "auto").lower()
    creality = next((p for p in CREALITY_PRINT_CANDIDATES if p.exists()), None)
    orca = ORCA_EXE if ORCA_EXE.exists() else None

    if pref == "creality_print":
        chosen, name = creality, "Creality Print"
    elif pref == "orcaslicer":
        chosen, name = orca, "OrcaSlicer"
    elif creality:
        chosen, name = creality, "Creality Print"
    elif orca:
        chosen, name = orca, "OrcaSlicer"
    else:
        chosen, name = None, None

    brand = cfg.get("printer_brand", "Creality")
    model = cfg.get("printer_model", "")
    printer_label = f"{brand} {model}".strip()

    return {
        "exe": chosen,
        "name": name,
        "creality_print_installed": creality is not None,
        "orca_installed": orca is not None,
        "slicer_installed": chosen is not None,
        "slicer_path": str(chosen) if chosen else None,
        "slicer_download": CREALITY_PRINT_DOWNLOAD,
        "printer_brand": brand,
        "printer_model": model,
        "printer_label": printer_label,
    }


def _freecad_running() -> bool:
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq freecad.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return "freecad.exe" in result.stdout.lower()
    except Exception:
        return False


def _printer_info(full_scan: bool = False) -> dict:
    return printer_status(load_config=_load_config, full_scan=full_scan)


def _job_output_dir(job: dict | None) -> Path:
    if job:
        return job_store.job_stl_dir(PRINT_DIR, job["id"])
    return PRINT_DIR


def _resolve_stl_paths(job: dict | None) -> list[Path]:
    if job:
        job_dir = job_store.job_stl_dir(PRINT_DIR, job["id"])
        return job_store.exportable_stl_paths(job_dir)
    if not PRINT_DIR.exists():
        return []
    return sorted(
        p for p in PRINT_DIR.glob("*.stl") if job_store.is_export_stl_name(p.name)
    )


def _cad_export_stale(job: dict | None) -> tuple[bool, str | None]:
    if not job:
        return False, None
    job_dir = job_store.job_stl_dir(PRINT_DIR, job["id"])
    stls = job_store.exportable_stl_paths(job_dir)
    if not stls:
        return True, "CAD not exported yet — export STL or Re-slice from latest model"
    newest_stl = max(stl.stat().st_mtime for stl in stls)
    if float(job.get("updated_at") or 0) > newest_stl + 1:
        return True, "FreeCAD model changed since last STL export — Re-slice to refresh"
    return False, None


def _gcode_info(job: dict | None = None) -> dict:
    cfg = _load_config()
    job_id = job["id"] if job else None
    output_dir = _job_output_dir(job) if job else PRINT_DIR
    path = find_gcode_file(cfg, PRINT_DIR, job_id=job_id)
    stls = _resolve_stl_paths(job) if job else []
    cad_stale, cad_stale_reason = _cad_export_stale(job)
    stale = False
    stale_reason: str | None = None
    if cad_stale:
        stale = True
        stale_reason = cad_stale_reason
    if path and stls and not stale:
        if not gcode_matches_stls(path, stls):
            stale = True
            stale_reason = (
                "G-code includes old parts that are no longer in the export — click Auto-Slice again"
            )
        else:
            newest_stl = max(stl.stat().st_mtime for stl in stls)
            if newest_stl > path.stat().st_mtime + 1:
                stale = True
                stale_reason = "STLs were updated after the last slice — click Auto-Slice again"
    ready = path is not None and not stale
    meta = parse_gcode_meta(path) if ready and path else {}
    return {
        "gcode_ready": ready,
        "gcode_stale": stale,
        "gcode_stale_reason": stale_reason,
        "cad_stale": cad_stale,
        "cad_stale_reason": cad_stale_reason,
        "gcode_file": path.name if path else None,
        "gcode_path": str(path) if path else None,
        "gcode_dir": str(output_dir),
        "gcode_print_time": meta.get("print_time"),
        "gcode_filament_g": meta.get("filament_g"),
        "gcode_filament_mm": meta.get("filament_mm"),
        "gcode_filament_cm3": meta.get("filament_cm3"),
        "gcode_layer_height": meta.get("layer_height"),
        "gcode_layer_count": meta.get("layer_count"),
        "gcode_has_thumbnail": bool(meta.get("has_thumbnail")),
    }


def _services_snapshot() -> dict:
    rpc = _check_rpc()
    headless = _use_headless()
    cad_ready = _cad_ready()
    slicer = _slicer_info()
    printer = _printer_info()
    return {
        "studio_api": True,
        "freecad_installed": FREECAD_EXE.exists() or hl.is_ready(),
        "freecad_running": _freecad_running() if not headless else hl.is_ready(),
        "freecad_mode": _freecad_mode(),
        "headless_ready": hl.is_ready(),
        "freecad_cmd_path": hl.cmd_path_display(),
        "rpc_bridge": rpc,
        "cad_ready": cad_ready,
        "orca_installed": slicer["orca_installed"],
        "creality_print_installed": slicer["creality_print_installed"],
        "slicer_installed": slicer["slicer_installed"],
        "slicer_name": slicer["name"],
        "printer_label": slicer["printer_label"],
        "printer_online": printer["printer_online"],
        "printer_ip": printer["printer_ip"],
        "printer_detail": printer["printer_detail"],
        "all_ready": cad_ready,
    }


def _wait_for_rpc(timeout_sec: int = 60) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if _check_rpc():
            return True
        time.sleep(2)
    return False


def _connect_freecad_rpc() -> str:
    """Connect RPC without spawning a duplicate FreeCAD GUI process."""
    if _check_rpc():
        return "RPC bridge already connected."

    if not FREECAD_EXE.exists():
        raise HTTPException(status_code=404, detail="FreeCAD not found")
    if not START_RPC_MACRO.exists():
        raise HTTPException(status_code=404, detail=f"RPC macro not found: {START_RPC_MACRO}")

    background = _background_freecad()

    if not _freecad_running():
        launch_freecad_gui(
            str(FREECAD_EXE),
            str(START_RPC_MACRO),
            focus=not background,
            minimize=background,
        )
        if _wait_for_rpc(60):
            if background:
                minimize_freecad_window()
            else:
                focus_freecad_window()
            return "Launched FreeCAD GUI with RPC auto-start."
        raise HTTPException(
            status_code=503,
            detail="FreeCAD started but RPC not ready. In FreeCAD: MCP Addon → Start RPC Server.",
        )

    # FreeCAD is already running — never launch a second instance (causes open/close flicker).
    if _wait_for_rpc(20):
        if background:
            minimize_freecad_window()
        return "Connected to RPC on the existing FreeCAD instance."

    if not background:
        focus_freecad_window()
    raise HTTPException(
        status_code=503,
        detail=(
            "FreeCAD is running but RPC is not connected. "
            "In FreeCAD: FreeCADMCP addon → Start RPC Server (or run the StartMCPOnly macro once)."
        ),
    )


def _require_rpc() -> FreeCADClient:
    if not _check_rpc():
        raise HTTPException(
            status_code=503,
            detail="FreeCAD RPC not running. Open FreeCAD → MCP Addon → Start RPC Server.",
        )
    return client


def _require_cad(job_id: str | None = None) -> FreeCADClient | fe.HeadlessCad:
    if _use_headless():
        if not hl.is_ready():
            raise HTTPException(
                status_code=503,
                detail=(
                    "FreeCADCmd not found. Install FreeCAD or set freecad_cmd_path in config.toml "
                    f"(expected near {FREECAD_CMD})."
                ),
            )
        return fe.headless_cad(job_id)
    return _require_rpc()


_FEATURE_PROPS = (
    "Length",
    "Width",
    "Height",
    "Radius",
    "Radius1",
    "Radius2",
    "Angle",
    "Thickness",
    "Size",
    "Diameter",
    "Depth",
    "Offset",
    "Placement",
    "Base",
    "Profile",
    "FacesNumber",
    "EdgesNumber",
)


def _format_feature_props(props: dict) -> str:
    parts: list[str] = []
    for key in _FEATURE_PROPS:
        if key not in props:
            continue
        val = props[key]
        if isinstance(val, (int, float, str, bool)):
            parts.append(f"{key}={val}")
        elif isinstance(val, dict) and key == "Base" and all(k in val for k in ("x", "y", "z")):
            parts.append(f"base=({val['x']:.1f},{val['y']:.1f},{val['z']:.1f})")
    return ", ".join(parts[:8])


def _resolve_job(job_id: str | None = None) -> dict | None:
    if job_id:
        job = job_store.load_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
        return job
    return job_store.get_active_job()


def _object_structured_entry(obj: dict) -> dict:
    entry: dict = {
        "name": obj.get("Name", "?"),
        "type": obj.get("TypeId", ""),
    }
    label = obj.get("Label", "")
    if label and label != entry["name"]:
        entry["label"] = label
    shape = obj.get("Shape") or {}
    if shape.get("Volume"):
        entry["volume_mm3"] = round(shape["Volume"], 2)
    if shape.get("FaceCount"):
        entry["face_count"] = shape["FaceCount"]
    if shape.get("EdgeCount"):
        entry["edge_count"] = shape["EdgeCount"]
    placement = obj.get("Placement") or {}
    base = placement.get("Base") if isinstance(placement, dict) else None
    if isinstance(base, dict) and all(k in base for k in ("x", "y", "z")):
        entry["position_mm"] = {
            "x": round(base["x"], 2),
            "y": round(base["y"], 2),
            "z": round(base["z"], 2),
        }
    props = obj.get("Properties") or {}
    if isinstance(props, dict):
        features = _format_feature_props(props)
        if features:
            entry["features"] = features
    return entry


def _scene_structured_for_llm(
    fc: FreeCADClient | fe.HeadlessCad,
    doc_name: str | None = None,
) -> dict:
    docs = fc.list_documents()
    if not docs:
        return {"documents": [], "note": "No open FreeCAD documents."}
    if doc_name and doc_name in docs:
        docs = [doc_name]
    elif doc_name:
        return {"documents": [], "note": f"Document '{doc_name}' is not open in FreeCAD yet."}

    documents: list[dict] = []
    for scan_doc in docs[:3]:
        doc_entry: dict = {"name": scan_doc, "objects": []}
        try:
            objs = fc.get_objects(scan_doc)
        except Exception:
            doc_entry["error"] = "could not read objects"
            documents.append(doc_entry)
            continue
        doc_entry["objects"] = [_object_structured_entry(obj) for obj in objs[:20]]
        documents.append(doc_entry)
    return {"documents": documents}


def _scene_context_for_llm(
    fc: FreeCADClient | fe.HeadlessCad,
    doc_name: str | None = None,
) -> str:
    return json.dumps(_scene_structured_for_llm(fc, doc_name), indent=2)


def _model_info(cad_ready: bool, focus_doc: str | None = None, job_id: str | None = None) -> dict:
    if not cad_ready:
        return {"has_model": False, "object_count": 0, "active_document": None, "objects": []}

    if _use_headless():
        if not job_id or not focus_doc:
            active_job = job_store.get_active_job()
            job_id = job_id or (active_job["id"] if active_job else None)
            focus_doc = focus_doc or (active_job["freecad_doc"] if active_job else None)
        if not job_id or not focus_doc:
            return {"has_model": False, "object_count": 0, "active_document": None, "objects": []}
        fc = fe.headless_cad(job_id)
        try:
            objs = fc.get_objects(focus_doc)
            names = [o.get("Name", "?") for o in objs if o.get("Name")]
            return {
                "has_model": len(names) > 0,
                "object_count": len(names),
                "active_document": focus_doc,
                "objects": names[:20],
            }
        except Exception:
            fcstd = job_store.job_fcstd_path(job_id, focus_doc)
            has_file = fcstd.is_file() and fcstd.stat().st_size > 0
            return {
                "has_model": has_file,
                "object_count": 0 if not has_file else 1,
                "active_document": focus_doc,
                "objects": [],
            }

    documents = client.list_documents()
    total_objects = 0
    all_objects: list[str] = []
    active_job = job_store.get_active_job()
    active_doc = focus_doc or (active_job["freecad_doc"] if active_job else None) or (documents[0] if documents else None)
    scan_docs = [active_doc] if active_doc and active_doc in documents else documents

    for doc_name in scan_docs:
        try:
            objs = client.get_objects(doc_name)
            names = [o.get("Name", "?") for o in objs if o.get("Name")]
            total_objects += len(names)
            all_objects.extend(names)
        except Exception:
            continue

    return {
        "has_model": total_objects > 0,
        "object_count": total_objects,
        "active_document": active_doc,
        "objects": all_objects[:20],
    }


@app.get("/api/status")
def status() -> dict:
    rpc = _check_rpc()
    headless = _use_headless()
    cad_ready = _cad_ready()
    documents = client.list_documents() if rpc and not headless else []
    stl_files = sorted(p.name for p in PRINT_DIR.glob("*.stl")) if PRINT_DIR.exists() else []
    slicer = _slicer_info()
    printer = _printer_info()
    ai = _ai_info()
    active_job = job_store.get_active_job()
    job_model = _model_info(
        cad_ready,
        active_job["freecad_doc"] if active_job else None,
        active_job["id"] if active_job else None,
    )
    if headless and active_job and cad_ready:
        documents = [active_job["freecad_doc"]] if job_model.get("has_model") else []
    job_stl = _job_stl_info(active_job)
    gcode = _gcode_info(active_job)
    stl_ready = job_stl["job_stl_ready"] if active_job else len(stl_files) > 0
    stl_count = job_stl["job_stl_count"] if active_job else len(stl_files)
    job_output_dir = str(_job_output_dir(active_job))
    cfg = _load_config()
    bed = resolve_print_bed(cfg)
    return {
        "rpc_connected": cad_ready,
        "rpc_bridge_live": rpc,
        "cad_ready": cad_ready,
        "freecad_mode": _freecad_mode(),
        "headless_ready": hl.is_ready(),
        "freecad_cmd_path": hl.cmd_path_display(),
        "freecad_path": str(FREECAD_EXE),
        "orca_path": str(ORCA_EXE),
        "orca_installed": slicer["orca_installed"],
        "creality_print_installed": slicer["creality_print_installed"],
        "slicer_installed": slicer["slicer_installed"],
        "slicer_name": slicer["name"],
        "slicer_path": slicer["slicer_path"],
        "slicer_download": slicer["slicer_download"],
        "printer_brand": slicer["printer_brand"],
        "printer_model": slicer["printer_model"],
        "printer_label": slicer["printer_label"],
        "bed_width_mm": bed["bed_width_mm"],
        "bed_depth_mm": bed["bed_depth_mm"],
        "bed_height_mm": bed["bed_height_mm"],
        "bed_source": bed["bed_source"],
        "printer_online": printer["printer_online"],
        "printer_ip": printer["printer_ip"],
        "printer_port": printer["printer_port"],
        "printer_protocol": printer["printer_protocol"],
        "printer_detail": printer["printer_detail"],
        "local_subnet": printer["local_subnet"],
        "camera_available": printer.get("camera_available", False),
        "camera_port": printer.get("camera_port"),
        "camera_type": printer.get("camera_type"),
        "gcode_ready": gcode["gcode_ready"],
        "gcode_stale": gcode["gcode_stale"],
        "gcode_stale_reason": gcode["gcode_stale_reason"],
        "cad_stale": gcode["cad_stale"],
        "cad_stale_reason": gcode["cad_stale_reason"],
        "gcode_file": gcode["gcode_file"],
        "gcode_path": gcode["gcode_path"],
        "gcode_dir": gcode["gcode_dir"],
        "gcode_print_time": gcode["gcode_print_time"],
        "gcode_filament_g": gcode["gcode_filament_g"],
        "gcode_filament_mm": gcode["gcode_filament_mm"],
        "gcode_filament_cm3": gcode["gcode_filament_cm3"],
        "gcode_layer_height": gcode["gcode_layer_height"],
        "gcode_layer_count": gcode["gcode_layer_count"],
        "gcode_has_thumbnail": gcode["gcode_has_thumbnail"],
        "job_output_dir": job_output_dir,
        "boat_fcstd": str(BOAT_FCSTD),
        "boat_exists": BOAT_FCSTD.exists(),
        "boat_in_freecad": "Boat" in documents,
        "print_dir": str(PRINT_DIR),
        "stl_files": job_stl["job_stl_files"] if active_job else stl_files,
        "stl_ready": stl_ready,
        "stl_count": stl_count,
        "background_freecad": _background_freecad(),
        **job_stl,
        "documents": documents,
        "ai_configured": ai["configured"],
        "ai_provider": ai["provider"],
        "ai_model": ai["model"],
        "ai_vision": is_vision_model(ai["model"]),
        "ai_label": ai["label"],
        "grok_configured": resolve_grok_config(cfg)["configured"],
        "image_gen_enabled": resolve_grok_config(cfg)["enabled"],
        "grok_image_model": resolve_grok_config(cfg)["model"],
        "studio_url": "http://127.0.0.1:8787",
        "active_job_id": active_job["id"] if active_job else None,
        "active_job_title": active_job["title"] if active_job else None,
        "active_job_doc": active_job["freecad_doc"] if active_job else None,
        **job_model,
    }


@app.get("/api/workflow")
def workflow() -> dict:
    s = status()
    steps = [
        {
            "id": "studio",
            "title": "CadForge running",
            "description": "CadForge server is online",
            "status": "done",
            "detail": s["studio_url"],
            "action": None,
            "optional": False,
        },
        {
            "id": "rpc",
            "title": "Connect FreeCAD" if not s.get("freecad_mode") == "headless" else "CAD engine",
            "description": (
                "Start FreeCAD MCP RPC bridge"
                if s.get("freecad_mode") != "headless"
                else "Headless FreeCADCmd (no GUI required)"
            ),
            "status": "done" if s["rpc_connected"] else "active",
            "detail": (
                "Headless engine ready"
                if s.get("freecad_mode") == "headless" and s["rpc_connected"]
                else ("Connected" if s["rpc_connected"] else "Click Start All Services to launch FreeCAD + RPC")
            ),
            "action": None if s.get("freecad_mode") == "headless" else "start-all",
            "optional": s.get("freecad_mode") == "headless",
        },
        {
            "id": "ai",
            "title": "AI key (optional)",
            "description": "Enable natural-language prompts",
            "status": "done" if s["ai_configured"] else "pending",
            "detail": (
                f"{s['ai_label']} ({s['ai_model']}) ready"
                if s["ai_configured"]
                else "Open Settings — add Ollama API key (vision + code) and optional Grok key (image expansion)"
            ),
            "action": None,
            "optional": True,
        },
        {
            "id": "design",
            "title": "Design your model",
            "description": "Prompt or run Python in FreeCAD",
            "status": (
                "done"
                if s["has_model"]
                else ("active" if s["rpc_connected"] else "pending")
            ),
            "detail": (
                f"{s['object_count']} objects in {s['documents']}"
                if s["has_model"]
                else "Type a prompt and click Build"
            ),
            "action": "prompt-build",
            "optional": False,
        },
        {
            "id": "preview",
            "title": "Preview model",
            "description": "Check the 3D view looks correct",
            "status": "done" if s["has_model"] else "pending",
            "detail": "Refresh preview after building",
            "action": "screenshot",
            "optional": False,
        },
        {
            "id": "export",
            "title": "Export STL",
            "description": "Prepare files for 3D printing",
            "status": (
                "done"
                if s["stl_ready"]
                else ("active" if s["has_model"] else "pending")
            ),
            "detail": (
                f"{s['stl_count']} files in {s['print_dir']}"
                if s["stl_ready"]
                else "Export scaled STLs"
            ),
            "action": "export-stl",
            "optional": False,
        },
        {
            "id": "slice",
            "title": "Slice G-code",
            "description": f"Slice STLs in {s['slicer_name'] or 'Creality Print'}",
            "status": (
                "done"
                if s["gcode_ready"]
                else ("active" if s["stl_ready"] else "pending")
            ),
            "detail": (
                (
                    f"G-code ready: {s['gcode_file']}"
                    + (
                        f" — {s['gcode_print_time']}, {s['gcode_filament_cm3']} cm³"
                        if s.get("gcode_print_time") and s.get("gcode_filament_cm3")
                        else ""
                    )
                )
                if s["gcode_ready"]
                else (
                    s.get("gcode_stale_reason")
                    or (
                        f"Auto-slice or open {s['slicer_name']} for {s.get('job_output_dir') or s['print_dir']}"
                        if s["slicer_installed"]
                        else "Install Creality Print from github.com/CrealityOfficial/CrealityPrint"
                    )
                )
            ),
            "action": "slice-gcode" if s.get("orca_installed") else "open-slicer",
            "optional": False,
        },
        {
            "id": "reslice",
            "title": "Re-slice from latest CAD",
            "description": "Export fresh STL, wipe old slice, slice again",
            "status": (
                "active"
                if s.get("cad_stale") or s.get("gcode_stale")
                else ("done" if s["gcode_ready"] and not s.get("cad_stale") else "pending")
            ),
            "detail": (
                s.get("cad_stale_reason")
                or s.get("gcode_stale_reason")
                or (
                    f"Current slice: {s['gcode_file']}"
                    if s["gcode_ready"]
                    else "Use after changing the model in FreeCAD"
                )
            ),
            "action": "reslice-gcode" if s.get("orca_installed") else None,
            "optional": True,
        },
        {
            "id": "send",
            "title": "Send to WiFi printer",
            "description": f"Upload G-code to {s['printer_label'] or 'Creality'} over WiFi",
            "status": "active" if s["gcode_ready"] and s["printer_online"] else "pending",
            "detail": (
                f"Click Send to Printer — uploads to {s['printer_ip']} and starts print"
                if s["gcode_ready"] and s["printer_online"]
                else (
                    f"Slice first, then send to {s['printer_ip'] or 'printer on WiFi'}"
                    if s["printer_online"]
                    else "Connect printer to WiFi first"
                )
            ),
            "action": "send-print",
            "optional": False,
        },
    ]

    required = [x for x in steps if not x["optional"]]
    done_count = sum(1 for x in required if x["status"] == "done")
    current = next((x for x in steps if x["status"] == "active"), None)
    if current is None:
        current = next((x for x in steps if x["status"] == "pending"), steps[-1])

    return {
        "steps": steps,
        "progress_percent": round(100 * done_count / len(required)),
        "done_count": done_count,
        "total_count": len(required),
        "current_step_id": current["id"] if current else None,
        "current_step_title": current["title"] if current else None,
        "current_step_detail": current["detail"] if current else None,
        "current_action": current.get("action") if current else None,
    }


@app.get("/api/ai/models")
def ai_models() -> dict:
    return list_ai_models(_load_config())


@app.get("/api/settings")
def get_settings() -> dict:
    return public_settings(_load_config())


@app.post("/api/settings", response_model=ActionResult)
def update_settings(req: SettingsUpdateRequest) -> ActionResult:
    payload = req.model_dump(exclude_unset=True)
    if not payload:
        raise HTTPException(status_code=400, detail="No settings provided")
    result = apply_settings_update(
        payload,
        load_config=_load_config,
        save_config_value=_save_config_value,
        config_file=CONFIG_FILE,
    )
    return ActionResult(ok=True, message="Settings saved", data=result)


@app.post("/api/ai/model", response_model=ActionResult)
def set_ai_model(req: AiModelRequest) -> ActionResult:
    catalog = list_ai_models(_load_config())
    known = {m["id"] for m in catalog.get("models", [])}
    if known and req.model not in known:
        raise HTTPException(status_code=400, detail=f"Unknown model: {req.model}")

    _save_config_value("model", req.model)
    vision = is_vision_model(req.model)
    return ActionResult(
        ok=True,
        message=f"AI model set to {req.model}",
        data={"model": req.model, "vision": vision},
    )


@app.get("/api/jobs")
def list_jobs() -> dict:
    return job_store.list_jobs()


@app.post("/api/jobs", response_model=ActionResult)
def create_job(req: JobCreateRequest) -> ActionResult:
    job = job_store.create_job(title=req.title, prompt=req.prompt)
    if _cad_ready():
        fc = _require_cad(job["id"])
        fe.activate_job(fc, job, use_headless=_use_headless())
    return ActionResult(
        ok=True,
        message=f"Job created: {job['title']}",
        data={"job": job},
    )


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = job_store.load_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/api/features/tree")
def features_tree(job_id: str | None = None) -> dict:
    job = _resolve_job(job_id)
    cfg = _load_config()
    code = (job or {}).get("code") or ""
    doc_name = (job or {}).get("freecad_doc")
    fc_objects: list[dict] = []
    if _cad_ready() and doc_name and job:
        try:
            fc_objects = _require_cad(job["id"]).get_objects(doc_name)
        except Exception:
            fc_objects = []
    gcode_path = find_gcode_file(cfg, PRINT_DIR, job_id=job["id"]) if job else None
    return build_feature_tree(
        code,
        cfg,
        freecad_objects=fc_objects,
        gcode_path=gcode_path,
        doc_name=doc_name,
    )


@app.post("/api/features/param", response_model=ActionResult)
def patch_feature_param(req: FeatureParamPatchRequest) -> ActionResult:
    job = _resolve_job(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="No active job")
    code = job.get("code") or ""
    if not code.strip():
        raise HTTPException(status_code=400, detail="Job has no Python code yet")
    try:
        new_code = patch_parameter(code, req.name, req.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    job_store.update_job_fields(job["id"], code=new_code, status="draft")
    job_store.append_prompt_history(
        job["id"],
        f"Set parameter {req.name} = {req.value}",
        kind="param",
    )
    data: dict = {"code": new_code, "job_id": job["id"], "parameter": req.name, "value": req.value}

    if req.rerun:
        fc = _require_cad(job["id"])
        if not _use_headless():
            _maybe_focus_freecad()
        fe.activate_job(fc, job, use_headless=_use_headless())
        final_code, result, fix_attempts = _execute_with_autofix(
            fc, new_code, job, job["freecad_doc"], auto_fix=True
        )
        if final_code != new_code:
            job_store.update_job_fields(job["id"], code=final_code)
            new_code = final_code
        job_store.update_job_fields(job["id"], status="built")
        data.update({
            "code": new_code,
            "execution_output": result.get("message"),
            "auto_fixed": fix_attempts > 0,
            "fix_attempts": fix_attempts,
        })
        try:
            stls = _export_active_job_stl(fc, job)
            data["stl_files"] = [p.name for p in stls]
        except HTTPException as exc:
            data["stl_export_warning"] = str(exc.detail)

    tree = build_feature_tree(
        new_code,
        _load_config(),
        freecad_objects=_require_cad(job["id"]).get_objects(job["freecad_doc"]) if _cad_ready() else [],
        gcode_path=find_gcode_file(_load_config(), PRINT_DIR, job_id=job["id"]),
        doc_name=job["freecad_doc"],
    )
    data["tree"] = tree
    return ActionResult(
        ok=True,
        message=f"Updated {req.name} → {req.value}"
        + (" and rebuilt in FreeCAD" if req.rerun else "")
        + (f" — exported {len(data['stl_files'])} STL(s)" if data.get("stl_files") else "")
        + (f" ({data['stl_export_warning']})" if data.get("stl_export_warning") else ""),
        data=data,
    )


@app.post("/api/features/config", response_model=ActionResult)
def patch_feature_config(req: FeatureConfigPatchRequest) -> ActionResult:
    allowed = {"slice_quality", "printer_nozzle", "filament_profile", "printer_model", "bed_width_mm", "bed_depth_mm", "bed_height_mm"}
    if req.key not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported config key: {req.key}")
    _save_config_value(req.key, req.value)
    cfg = _load_config()
    job = job_store.get_active_job()
    code = (job or {}).get("code") or ""
    tree = build_feature_tree(
        code,
        cfg,
        gcode_path=find_gcode_file(cfg, PRINT_DIR, job_id=job["id"]) if job else None,
        doc_name=(job or {}).get("freecad_doc"),
    )
    return ActionResult(
        ok=True,
        message=f"Updated config.toml: {req.key} = {req.value}",
        data={"key": req.key, "value": req.value, "tree": tree},
    )


@app.patch("/api/jobs/{job_id}", response_model=ActionResult)
def update_job(job_id: str, req: JobUpdateRequest) -> ActionResult:
    try:
        job = job_store.update_job_fields(
            job_id,
            title=req.title,
            prompt=req.prompt,
            code=req.code,
            status=req.status,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ActionResult(ok=True, message="Job updated", data={"job": job})


@app.post("/api/jobs/{job_id}/activate", response_model=ActionResult)
def activate_job(job_id: str) -> ActionResult:
    try:
        job = job_store.set_active_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if _cad_ready():
        fc = _require_cad(job["id"])
        if not _use_headless():
            _maybe_focus_freecad()
        fe.activate_job(fc, job, use_headless=_use_headless())
    return ActionResult(ok=True, message=f"Active job: {job['title']}", data={"job": job})


@app.delete("/api/jobs/{job_id}", response_model=ActionResult)
def remove_job(job_id: str) -> ActionResult:
    job = job_store.delete_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if _check_rpc() and not _use_headless():
        try:
            fc = _require_rpc()
            fc.execute_code(job_store.close_document_code(job["freecad_doc"]))
        except Exception:
            pass
    return ActionResult(ok=True, message=f"Deleted job: {job['title']}", data={"job_id": job_id})


@app.post("/api/prompt", response_model=ActionResult)
def build_from_prompt(req: PromptRequest) -> ActionResult:
    cfg = _load_config()
    ai = resolve_ai_config(cfg)
    image_b64 = _normalize_image_b64(req.image_base64)
    images = [image_b64] if image_b64 else None
    context_b64s: list[str] = []
    if req.context_images:
        context_b64s = [str(e["base64"]) for e in req.context_images if e.get("base64")]
    elif image_b64:
        _, context_b64s, _ = _prepare_reference_context(
            image_b64,
            cfg,
            pregenerated=None,
            view_specs=req.context_view_specs,
            global_context=req.global_image_context or "",
            mime=req.image_mime,
        )
    if context_b64s:
        images = (images or []) + context_b64s

    job = _resolve_job(req.job_id)
    if job is None:
        job = job_store.create_job(title=job_store._slug_title(req.prompt), prompt=req.prompt)
    elif not req.job_id:
        job_store.set_active_job(job["id"])

    job_code = (job.get("code") or "").strip()
    has_job_code = job_code and job_code != job_store.INITIAL_CODE.strip()
    editing = req.edit_mode or bool((req.existing_code or "").strip()) or has_job_code
    existing_code = (req.existing_code or "").strip() or (job_code if has_job_code else None)

    job = job_store.append_prompt_history(
        job["id"],
        req.prompt,
        kind="edit" if editing else "build",
    )
    design_context = job_store.design_conversation_context(job)
    scene_context: str | None = None
    scene_preview = False
    scene_view_names: list[str] | None = None
    doc_name = job["freecad_doc"]

    if _check_rpc() and not _use_headless():
        fc_ctx = _require_rpc()
        fe.activate_job(fc_ctx, job, use_headless=False)
        if editing:
            scene_context = _scene_context_for_llm(fc_ctx, doc_name)
            if req.use_scene_preview and is_vision_model(ai["model"]):
                user_ref_count = len(images) if images else 0
                multiview = capture_multiview_images(
                    fc_ctx, doc_name=doc_name, restore_after=_background_freecad()
                )
                if multiview.get("success") and multiview.get("images"):
                    view_labels = (
                        (["User reference"] * user_ref_count)
                        + list(multiview.get("views") or [])
                    )
                    images = (images or []) + multiview["images"]
                    scene_view_names = view_labels
                    scene_preview = True
    elif editing and _cad_ready():
        fc_ctx = _require_cad(job["id"])
        scene_context = _scene_context_for_llm(fc_ctx, doc_name)
        if req.use_scene_preview and is_vision_model(ai["model"]):
            user_ref_count = len(images) if images else 0
            multiview = _capture_for_critique(fc_ctx, doc_name, job)
            if multiview.get("success") and multiview.get("images"):
                view_labels = (
                    (["User reference"] * user_ref_count)
                    + list(multiview.get("views") or [])
                )
                images = (images or []) + multiview["images"]
                scene_view_names = view_labels
                scene_preview = True

    try:
        code = generate_freecad_code(
            design_context if editing else req.prompt,
            cfg=cfg,
            images=images,
            existing_code=existing_code if editing else None,
            scene_context=scene_context,
            scene_preview=scene_preview,
            scene_view_names=scene_view_names,
            job_doc_name=doc_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not req.execute:
        job_store.update_job_fields(job["id"], code=code, status="draft")
        return ActionResult(
            ok=True,
            message="Edit code generated" if editing else "Code generated",
            data={
                "code": code,
                "prompt": req.prompt,
                "used_image": bool(image_b64),
                "edit_mode": editing,
                "used_scene_preview": scene_preview,
                "spatial_views": scene_view_names or [],
                "job_id": job["id"],
                "job": job_store.load_job(job["id"]),
            },
        )

    fc = _require_cad(job["id"])
    if not _use_headless():
        _maybe_focus_freecad()
    fe.activate_job(fc, job, use_headless=_use_headless())
    code, result, _ = _execute_with_autofix(fc, code, job, doc_name, auto_fix=False)
    job_store.update_job_fields(job["id"], code=code, status="built")
    data: dict = {
        "code": code,
        "prompt": req.prompt,
        "used_image": bool(image_b64),
        "edit_mode": editing,
        "used_scene_preview": scene_preview,
        "spatial_views": scene_view_names or [],
        "preview_url": "/api/preview/stl",
        "job_id": job["id"],
        "job": job_store.load_job(job["id"]),
    }
    if not _use_headless() and _check_rpc():
        preview = capture_preview_image(
            fc, doc_name=doc_name, restore_after=_background_freecad()  # type: ignore[arg-type]
        )
        if preview.get("success") and preview.get("image"):
            data["preview_image"] = preview["image"]
            data["preview_mime"] = "image/png"
            data["preview_url"] = "/api/screenshot.png"

    return ActionResult(
        ok=True,
        message=result.get("message", "Updated model" if editing else "Built from prompt"),
        data=data,
    )


def _count_solids(
    fc: FreeCADClient | fe.HeadlessCad,
    doc_name: str,
    job: dict | None = None,
) -> int | None:
    return fe.count_solids(fc, doc_name, job, use_headless=_use_headless())


def _execute_with_autofix(
    fc: FreeCADClient | fe.HeadlessCad,
    code: str,
    job: dict | None,
    doc_name: str | None,
    *,
    auto_fix: bool = True,
    max_fixes: int = 2,
) -> tuple[str, dict, int]:
    """Run code, auto-repairing with the LLM on failure. Returns (final_code, result, fix_attempts).

    Raises HTTPException when the code still fails after max_fixes repairs.
    """
    fix_attempts = 0
    while True:
        result = fe.run_wrapped_code(fc, code, doc_name, job, use_headless=_use_headless())
        error: str | None = None
        if not result.get("success"):
            error = result.get("error") or result.get("message") or "Execution failed"
        elif job and doc_name:
            solids = _count_solids(fc, doc_name, job)
            if solids == 0:
                error = "Script executed but produced no solid geometry — the document is empty."
        if not error:
            return code, result, fix_attempts
        if not auto_fix or fix_attempts >= max_fixes:
            raise HTTPException(status_code=400, detail=error)
        fix_attempts += 1
        try:
            code = fix_freecad_code(
                code,
                error,
                user_prompt=(job or {}).get("prompt") or None,
                cfg=_load_config(),
                job_doc_name=doc_name,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"{error} (auto-fix failed: {exc})"
            ) from exc


@app.post("/api/execute", response_model=ActionResult)
def execute(req: ExecuteRequest) -> ActionResult:
    job = _resolve_job(req.job_id)
    fc = _require_cad(job["id"] if job else None)
    if not _use_headless():
        _maybe_focus_freecad(req.focus_window)
    doc_name = job["freecad_doc"] if job else None
    if job:
        fe.activate_job(fc, job, use_headless=_use_headless())

    code, result, fix_attempts = _execute_with_autofix(
        fc, req.code, job, doc_name, auto_fix=req.auto_fix
    )

    if job:
        job_store.update_job_fields(job["id"], code=code, status="built")
    output = (result.get("message") or "").split("Output:", 1)[-1].strip()
    data: dict | None = {
        **({"job_id": job["id"], "job": job} if job else {}),
        "code": code,
        "auto_fixed": fix_attempts > 0,
        "execution_output": output or None,
        "progress": "Python executed in FreeCAD",
    }
    if req.capture_preview and not _use_headless() and _check_rpc():
        preview = capture_preview_image(
            fc,  # type: ignore[arg-type]
            doc_name=doc_name,
            restore_after=_background_freecad(),
        )
        if preview.get("success") and preview.get("image"):
            preview_data = {
                "preview_image": preview["image"],
                "preview_mime": "image/png",
                "preview_url": "/api/screenshot.png",
                "progress": "Preview captured",
            }
            data = {**(data or {}), **preview_data}
    return ActionResult(ok=True, message=result.get("message", "OK"), data=data)


# Live progress per job for the AI build loop (UI polls /api/build/loop/status).
_loop_progress: dict[str, dict] = {}
_loop_results: dict[str, dict] = {}


def _calc_loop_pct(
    iteration: int,
    max_iterations: int,
    *,
    stage: str = "running",
) -> int:
    """Map loop stage to 0–100 for UI progress bar."""
    stage_frac = {
        "starting": 0.03,
        "plan": 0.1,
        "generate": 0.3,
        "execute": 0.55,
        "inspect": 0.78,
        "done": 1.0,
    }
    if iteration <= 0:
        return min(12, int(stage_frac.get(stage, 0.03) * 100))
    span = 88 / max(max_iterations, 1)
    base = 12 + (iteration - 1) * span
    return min(99, int(base + stage_frac.get(stage, 0.5) * span))


def _set_loop_progress(job_id: str, **fields) -> None:
    cur = dict(_loop_progress.get(job_id) or {})
    thinking = list(cur.get("thinking_log") or [])
    phase = fields.get("phase")
    if phase:
        thinking.append(str(phase))
    reasoning = fields.get("reasoning")
    if reasoning:
        thinking.append(f"Reasoning: {reasoning}")
    for issue in fields.get("issues") or []:
        thinking.append(f"Issue: {issue}")
    for item in fields.get("feature_audit") or []:
        if isinstance(item, dict) and item.get("status") != "ok":
            thinking.append(
                f"Feature {item.get('feature')}: {item.get('status')} — {item.get('fix') or item.get('observed')}"
            )
    fields["thinking_log"] = thinking[-50:]
    if "progress_percent" not in fields:
        stage = fields.pop("stage", None)
        if fields.get("state") == "done":
            fields["progress_percent"] = 100
        elif fields.get("state") == "error":
            fields["progress_percent"] = cur.get("progress_percent", 0)
        elif stage:
            iteration = int(fields.get("iteration") or cur.get("iteration") or 0)
            max_iterations = int(fields.get("max_iterations") or cur.get("max_iterations") or 6)
            fields["progress_percent"] = _calc_loop_pct(iteration, max_iterations, stage=stage)
    cur.update(fields)
    cur["updated_at"] = time.time()
    if "state" not in fields and "state" not in cur:
        cur["state"] = "running"
    _loop_progress[job_id] = cur


def _audit_missing(critique: dict | None) -> list[str]:
    if not critique:
        return []
    return [
        str(a.get("feature") or "")
        for a in (critique.get("feature_audit") or [])
        if a.get("status") in ("missing", "wrong") and a.get("feature")
    ]


def _export_viewer_stl_path(job: dict, doc_name: str) -> Path:
    """Write merged viewer STL for a job; returns output path."""
    out_path = PRINT_DIR / f"_viewer_{doc_name}.stl"
    PRINT_DIR.mkdir(parents=True, exist_ok=True)
    fc = _require_cad(job["id"])
    fe.activate_job(fc, job, use_headless=_use_headless())
    body = hl.export_viewer_stl_script(doc_name, out_path)
    if _use_headless():
        script = job_store.headless_open_document_code(doc_name, job["id"]).strip() + "\n\n" + body
        result = hl.run_script(script)
    else:
        result = fc.execute_code(body)
    if not result.get("success"):
        raise RuntimeError(result.get("error") or result.get("message") or "STL export failed")
    if not out_path.exists():
        raise RuntimeError("STL file was not written")
    return out_path


def _capture_for_critique(
    fc: FreeCADClient | fe.HeadlessCad,
    doc_name: str,
    job: dict,
) -> dict:
    """Multiview renders for inspection — RPC, subprocess FCStd, or STL fallback."""
    mode = _vision_capture_mode()

    if mode == "rpc" or (_check_rpc() and not _use_headless() and mode != "subprocess"):
        multiview = capture_multiview_images(
            fc,  # type: ignore[arg-type]
            doc_name=doc_name,
            restore_after=_background_freecad(),
        )
        if multiview.get("success") and multiview.get("images"):
            multiview["method"] = "rpc"
            return multiview
        single = capture_preview_image(
            fc,  # type: ignore[arg-type]
            view_name="Isometric",
            doc_name=doc_name,
            restore_after=_background_freecad(),
        )
        if single.get("success") and single.get("image"):
            return {
                "success": True,
                "images": [single["image"]],
                "views": ["Isometric"],
                "method": "rpc",
            }
        if mode == "rpc":
            return multiview

    _ensure_viewer_stl(job, doc_name)
    headless = vision_cap.capture_multiview_for_critique(
        job["id"],
        doc_name,
        print_dir=PRINT_DIR,
        mode=mode if mode in ("auto", "subprocess", "stl", "fcstd") else "auto",
    )
    if headless.get("success"):
        return headless

    if _check_rpc() and not _use_headless():
        return capture_multiview_images(
            fc,  # type: ignore[arg-type]
            doc_name=doc_name,
            restore_after=_background_freecad(),
        )
    return headless


def _ensure_viewer_stl(job: dict, doc_name: str) -> None:
    """Export merged viewer STL if missing (used by STL vision fallback)."""
    out_path = PRINT_DIR / f"_viewer_{doc_name}.stl"
    if out_path.is_file() and out_path.stat().st_size > 100:
        return
    try:
        _export_viewer_stl_path(job, doc_name)
    except Exception:
        pass


def _prepare_reference_context(
    image_b64: str | None,
    cfg: dict[str, str],
    *,
    pregenerated: list[dict[str, Any]] | None,
    view_specs: list[dict[str, Any]] | None,
    global_context: str,
    mime: str | None,
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Resolve Grok context images for vision + code generation."""
    if pregenerated:
        valid = [e for e in pregenerated if e.get("base64")]
        context_b64s = [str(e["base64"]) for e in valid]
        context_labels = [
            f"Generated context — {e.get('label', 'view')} (approximate, not measured)"
            for e in valid
        ]
        return valid, context_b64s, context_labels

    if not image_b64:
        return [], [], []

    grok = resolve_grok_config(cfg)
    if not grok["configured"] or not grok["enabled"]:
        return [], [], []

    generated = bootstrap_context_images(
        image_b64,
        cfg,
        mime=mime or "image/png",
        view_specs=view_specs,
        global_context=global_context or "",
    )
    context_b64s = [e["base64"] for e in generated]
    context_labels = [
        f"Generated context — {e.get('label', 'view')} (approximate, not measured)"
        for e in generated
    ]
    return generated, context_b64s, context_labels


@app.get("/api/image/context/defaults")
def image_context_defaults() -> dict:
    grok = resolve_grok_config(_load_config())
    return {
        "views": bootstrap_view_defaults(),
        "global_context_hint": GLOBAL_CONTEXT_HINT,
        "grok_configured": grok["configured"],
        "image_gen_enabled": grok["enabled"],
    }


@app.post("/api/image/context/generate", response_model=ActionResult)
def image_context_generate(req: ContextGenerateRequest) -> ActionResult:
    image_b64 = _normalize_image_b64(req.image_base64)
    if not image_b64:
        raise HTTPException(status_code=400, detail="Invalid image data")

    cfg = _load_config()
    view_specs = [v.model_dump() for v in req.views] if req.views else None
    results = generate_context_previews(
        image_b64,
        cfg,
        mime=req.image_mime or "image/png",
        view_specs=view_specs,
        global_context=req.global_context or "",
        only_label=req.only_label,
        chain_anchor_b64=_normalize_image_b64(req.chain_anchor_base64)
        if req.chain_anchor_base64
        else None,
        chain_anchor_mime=req.chain_anchor_mime,
    )
    ok_count = sum(1 for r in results if r.get("base64"))
    err_count = len(results) - ok_count
    msg = f"Generated {ok_count} synthetic view(s)"
    if err_count:
        msg += f" ({err_count} failed)"
    if req.only_label:
        msg = f"Regenerated {req.only_label}" if ok_count else f"Failed to regenerate {req.only_label}"
    return ActionResult(
        ok=ok_count > 0,
        message=msg,
        data={
            "images": results,
            "generated_count": ok_count,
            "failed_count": err_count,
        },
    )


@app.get("/api/build/loop/status")
def build_loop_status(job_id: str) -> dict:
    progress = dict(_loop_progress.get(job_id) or {"state": "idle"})
    if progress.get("state") in ("done", "error") and job_id in _loop_results:
        progress["result"] = _loop_results[job_id]
    return progress


@app.get("/api/build/history")
def build_history(job_id: str | None = None) -> dict:
    runs = model_memory.run_history(job_id)
    return {"runs": runs}


def _execute_build_loop(req: BuildLoopRequest) -> ActionResult:
    """Run the full vision loop (blocking). Called from a background thread."""
    cfg = _load_config()
    ai = resolve_ai_config(cfg)
    can_critique = is_vision_model(ai["model"])

    job = _resolve_job(req.job_id)
    if job is None:
        job = job_store.create_job(title=job_store._slug_title(req.prompt), prompt=req.prompt)
    doc_name = job["freecad_doc"]
    job_id = job["id"]

    job_code = (job.get("code") or "").strip()
    has_job_code = bool(job_code) and job_code != job_store.INITIAL_CODE.strip()
    editing = req.edit_mode or bool((req.existing_code or "").strip()) or has_job_code
    existing_code = (req.existing_code or "").strip() or (job_code if has_job_code else None)

    job = job_store.append_prompt_history(
        job_id,
        req.prompt,
        kind="edit" if editing else "build",
    )
    design_context = job_store.design_conversation_context(job)

    fc = _require_cad(job_id)
    if not _use_headless():
        _maybe_focus_freecad()
    fe.activate_job(fc, job, use_headless=_use_headless())

    run_id = model_memory.start_run(job_id, design_context, ai["model"])
    lessons = model_memory.past_lessons(design_context, job_id=job_id)
    lessons_suffix = lessons_prompt_suffix(lessons)

    image_b64 = _normalize_image_b64(req.image_base64)
    user_images = [image_b64] if image_b64 else None
    generated_context: list[dict] = []
    context_b64s: list[str] = []
    context_labels: list[str] = []

    if image_b64 or req.context_images:
        _set_loop_progress(
            job_id,
            state="running",
            stage="context",
            phase="Preparing reference images for CAD generation…",
        )
        try:
            generated_context, context_b64s, context_labels = _prepare_reference_context(
                image_b64,
                cfg,
                pregenerated=req.context_images,
                view_specs=req.context_view_specs,
                global_context=req.global_image_context or "",
                mime=req.image_mime,
            )
            if context_b64s:
                _set_loop_progress(
                    job_id,
                    stage="context",
                    phase=f"Reference context ready — {len(context_b64s)} synthetic view(s)",
                    context_images=[
                        {"label": e.get("label"), "prompt": e.get("prompt")}
                        for e in generated_context
                    ],
                )
            elif image_b64 and resolve_grok_config(cfg)["configured"]:
                _set_loop_progress(job_id, stage="context", phase="Grok context skipped (none generated)")
        except Exception as exc:
            _set_loop_progress(job_id, stage="context", phase=f"Grok context skipped: {exc}")

    code: str | None = None
    critique: dict | None = None
    score: int | None = None
    history: list[dict] = []
    required_features: dict | None = None
    last_multiview: dict | None = None
    prev_missing: list[str] | None = None
    best: dict = {"score": -1, "code": None, "missing": 999}

    # Step 0: feature checklist — new builds extract from prompt; edits keep prior plan
    if can_critique:
        _set_loop_progress(
            job_id,
            state="running",
            stage="plan",
            phase=(
                "Edit mode — reusing existing feature plan…"
                if editing
                else "Analyzing request — extracting required features…"
            ),
        )
        try:
            if editing:
                required_features = job.get("required_features") or features_from_code_comment(existing_code or "")
                if not (required_features.get("features") or []):
                    required_features = {
                        "summary": design_context[:240],
                        "features": [],
                    }
            else:
                required_features = extract_required_features(
                    design_context,
                    cfg=cfg,
                    reference_image=image_b64,
                    context_images=context_b64s or None,
                    context_labels=context_labels or None,
                )
            feat_names = [f.get("name", "?") for f in (required_features.get("features") or [])]
            model_memory.log_iteration(
                run_id, 0, "plan",
                critique={"required_features": required_features},
            )
            _set_loop_progress(
                job_id,
                stage="plan",
                required_features=feat_names,
                phase=(
                    f"Edit: {len(feat_names)} known features — applying latest change"
                    if editing
                    else f"Plan: {len(feat_names)} features — {required_features.get('summary', '')[:80]}"
                ),
            )
        except Exception as exc:
            required_features = {"summary": design_context, "features": []}
            _set_loop_progress(job_id, phase=f"Feature plan skipped: {exc}")

    try:
        for iteration in range(1, req.max_iterations + 1):
            # --- generate / fix ---
            phase = "generate" if iteration == 1 else "fix"
            _set_loop_progress(
                job_id,
                state="running",
                run_id=run_id,
                iteration=iteration,
                max_iterations=req.max_iterations,
                stage="generate",
                phase="Generating Python…" if iteration == 1 else f"Fixing issues (iteration {iteration})…",
                score=score,
                issues=(critique or {}).get("issues", []),
                lessons_used=len(lessons),
            )
            t0 = time.time()
            if iteration == 1:
                gen_prompt = design_context
                if editing:
                    gen_prompt += (
                        "\n\nIMPORTANT: This is an EDIT of an existing model. "
                        "Apply ONLY the latest change request. Keep all other geometry, "
                        "dimensions, and features from the current script unless the user "
                        "explicitly asked to change them."
                    )
                if required_features and required_features.get("features"):
                    checklist = json.dumps(required_features, indent=2)
                    gen_prompt += (
                        "\n\nYou MUST implement EVERY feature in this checklist:\n" + checklist
                    )
                gen_prompt += lessons_suffix or ""
                existing = existing_code if editing else None
                scene_context: str | None = None
                gen_images = list(user_images) if user_images else []
                if context_b64s:
                    gen_images.extend(context_b64s)
                scene_view_names: list[str] | None = None
                scene_preview = False
                if existing and can_critique:
                    scene_context = _scene_context_for_llm(fc, doc_name)
                    mv = _capture_for_critique(fc, doc_name, job)
                    if mv.get("success") and mv.get("images"):
                        gen_images.extend(mv["images"])
                        scene_view_names = list(mv.get("views") or [])
                        scene_preview = True
                code = generate_freecad_code(
                    gen_prompt,
                    cfg=cfg,
                    images=gen_images or None,
                    existing_code=existing,
                    scene_context=scene_context,
                    scene_preview=scene_preview,
                    scene_view_names=scene_view_names,
                    job_doc_name=doc_name,
                )
            else:
                assert code is not None and critique is not None
                built_imgs = (last_multiview or {}).get("images") or []
                built_views = (last_multiview or {}).get("views") or []
                missing_now = _audit_missing(critique)
                stagnation = (
                    prev_missing is not None
                    and set(missing_now) == set(prev_missing)
                    and len(missing_now) > 0
                )
                if stagnation:
                    _set_loop_progress(
                        job_id,
                        phase=f"Escalating fix for stuck features: {', '.join(missing_now[:3])}",
                    )
                code = fix_from_critique(
                    code,
                    critique,
                    design_context,
                    cfg=cfg,
                    job_doc_name=doc_name,
                    built_images=built_imgs,
                    built_view_names=built_views,
                    reference_image=image_b64,
                    required_features=required_features,
                    stagnation=stagnation,
                )
            model_memory.log_iteration(
                run_id, iteration, phase, code=code, duration_sec=time.time() - t0
            )
            _set_loop_progress(
                job_id,
                code=code,
                stage="generate",
                iteration=iteration,
                max_iterations=req.max_iterations,
                phase=f"Python ready (iteration {iteration}) — running in FreeCAD…",
            )

            # --- execute (with its own error auto-fix) ---
            _set_loop_progress(
                job_id,
                stage="execute",
                iteration=iteration,
                max_iterations=req.max_iterations,
                phase=f"Running in FreeCAD (iteration {iteration})…",
            )
            t0 = time.time()
            try:
                code, exec_result, fixes = _execute_with_autofix(fc, code, job, doc_name)
            except HTTPException as exc:
                model_memory.log_iteration(
                    run_id, iteration, "execute", code=code,
                    error=str(exc.detail), duration_sec=time.time() - t0,
                )
                model_memory.finish_run(run_id, "error", iteration, score, code)
                _set_loop_progress(job_id, state="error", phase=f"Execution failed: {exc.detail}")
                raise
            solids = _count_solids(fc, doc_name, job)
            model_memory.log_iteration(
                run_id, iteration, "execute", code=code, solids=solids,
                duration_sec=time.time() - t0,
            )
            job_store.update_job_fields(
                job_id,
                code=code,
                status="built",
                required_features=required_features,
            )
            _set_loop_progress(
                job_id,
                code=code,
                stage="execute",
                iteration=iteration,
                max_iterations=req.max_iterations,
                phase=f"FreeCAD run complete (iteration {iteration})",
            )

            if not can_critique:
                # Text-only model: one pass, no visual inspection possible.
                model_memory.finish_run(run_id, "approved", iteration, None, code)
                _set_loop_progress(job_id, state="done", phase="Built (no vision model for inspection)")
                break

            # --- render + critique ---
            _set_loop_progress(
                job_id,
                stage="inspect",
                iteration=iteration,
                max_iterations=req.max_iterations,
                phase=f"Inspecting model (iteration {iteration})…",
            )
            t0 = time.time()
            multiview = _capture_for_critique(fc, doc_name, job)
            last_multiview = multiview
            if not multiview.get("success"):
                method = multiview.get("method") or "unknown"
                _set_loop_progress(
                    job_id,
                    phase=f"Vision capture failed ({method}) — inspecting from scene data and code",
                    reasoning=multiview.get("error") or "Could not capture multiview renders.",
                )
                multiview = {"success": False, "images": [], "views": []}
            else:
                method = multiview.get("method") or "capture"
                _set_loop_progress(
                    job_id,
                    phase=f"Captured {len(multiview.get('images') or [])} views via {method}",
                )
            scene_context = _scene_context_for_llm(fc, doc_name)
            critique = critique_model(
                design_context,
                multiview.get("images") or [],
                list(multiview.get("views") or []),
                scene_context=scene_context,
                cfg=cfg,
                reference_image=image_b64,
                context_images=context_b64s or None,
                context_labels=context_labels or None,
                required_features=required_features,
                current_code=code,
            )
            if image_b64:
                extra = expand_from_critique(
                    image_b64,
                    critique,
                    cfg,
                    mime=req.image_mime or "image/png",
                    existing_labels={e.get("label", "") for e in generated_context},
                )
                added = [e for e in extra if e.get("base64")]
                if added:
                    generated_context.extend(added)
                    context_b64s.extend([e["base64"] for e in added])
                    context_labels.extend(
                        [
                            f"Generated context — {e.get('label', 'view')} (approximate, not measured)"
                            for e in added
                        ]
                    )
                    _set_loop_progress(
                        job_id,
                        phase=f"Agent requested {len(added)} extra context image(s) from Grok",
                    )
            score = critique["score"]
            missing = _audit_missing(critique)
            model_memory.log_iteration(
                run_id, iteration, "critique", critique=critique, score=score,
                solids=solids, duration_sec=time.time() - t0,
            )
            missing_count = len(missing)
            if (
                code
                and (score > best["score"] or (score == best["score"] and missing_count < best["missing"]))
            ):
                best = {"score": score, "code": code, "missing": missing_count}

            audit_summary = [f"{f}: {next((a.get('status') for a in (critique.get('feature_audit') or []) if a.get('feature') == f), '?')}" for f in missing]
            history.append({
                "iteration": iteration,
                "score": score,
                "issues": critique["issues"],
                "reasoning": critique.get("reasoning", ""),
                "feature_audit": critique.get("feature_audit", []),
                "reference_match": critique.get("reference_match"),
                "missing_features": missing,
            })
            still_fixing = iteration < req.max_iterations and missing
            _set_loop_progress(
                job_id,
                stage="inspect",
                iteration=iteration,
                max_iterations=req.max_iterations,
                score=score,
                issues=critique["issues"],
                feature_audit=critique.get("feature_audit"),
                reasoning=critique.get("reasoning"),
                reference_score=(critique.get("reference_match") or {}).get("score"),
                phase=(
                    f"Iteration {iteration}: score {score}/100"
                    + (f" — still missing: {', '.join(missing[:3])}" if missing else " — all features ok")
                    + (f" — rerunning fix ({iteration + 1}/{req.max_iterations})" if still_fixing else "")
                ),
            )

            prev_missing = missing
            if not missing and critique.get("approved"):
                model_memory.finish_run(run_id, "approved", iteration, score, code)
                _set_loop_progress(job_id, state="done", phase=f"Approved — score {score}/100, all features present")
                break
        else:
            final_missing = _audit_missing(critique)
            if best["code"]:
                code = best["code"]
                job_store.update_job_fields(job_id, code=code, status="built")
            status = "incomplete" if final_missing else "max_iters"
            model_memory.finish_run(run_id, status, req.max_iterations, score, code)
            if final_missing:
                _set_loop_progress(
                    job_id, state="done",
                    phase=(
                        f"Incomplete after {req.max_iterations} iterations — "
                        f"score {score}/100 — still missing: {', '.join(final_missing)}"
                    ),
                    feature_audit=(critique or {}).get("feature_audit"),
                )
            else:
                _set_loop_progress(
                    job_id, state="done",
                    phase=f"Stopped at {req.max_iterations} iterations — best score {score}/100",
                )
    except HTTPException:
        raise
    except Exception as exc:
        model_memory.finish_run(run_id, "error", len(history) + 1, score, code)
        _set_loop_progress(job_id, state="error", phase=str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if best["code"] and code != best["code"]:
        code = best["code"]
        try:
            code, _, _ = _execute_with_autofix(fc, code, job, doc_name, auto_fix=False)
            job_store.update_job_fields(job_id, code=code, status="built")
            _set_loop_progress(job_id, phase=f"Restored best revision (score {best['score']}/100)")
        except HTTPException:
            pass

    data: dict = {
        "code": code,
        "job_id": job_id,
        "job": job_store.load_job(job_id),
        "run_id": run_id,
        "iterations": history or [{"iteration": 1, "score": None, "issues": []}],
        "final_score": score,
        "lessons_used": len(lessons),
        "required_features": required_features,
        "preview_url": "/api/preview/stl",
    }
    if not _use_headless() and _check_rpc():
        preview = capture_preview_image(
            fc, doc_name=doc_name, restore_after=_background_freecad()  # type: ignore[arg-type]
        )
        if preview.get("success") and preview.get("image"):
            data["preview_image"] = preview["image"]
            data["preview_mime"] = "image/png"
            data["preview_url"] = "/api/screenshot.png"

    final_missing = _audit_missing(critique)
    if final_missing:
        msg = (
            f"Build incomplete — score {score}/100 — still missing: {', '.join(final_missing)}. "
            f"Try 'Apply changes' with more detail or edit the Python fillet section."
        )
        data["incomplete"] = True
        data["missing_features"] = final_missing
    elif score is not None:
        msg = f"Build approved — score {score}/100 after {len(history)} inspection(s)"
    else:
        msg = "Build complete"
    return ActionResult(ok=True, message=msg, data=data)


def _run_build_loop_thread(req: BuildLoopRequest, job_id: str) -> None:
    try:
        result = _execute_build_loop(req)
        _loop_results[job_id] = {
            "ok": True,
            "message": result.message,
            "data": result.data,
        }
        _set_loop_progress(job_id, state="done", phase=result.message)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        _loop_results[job_id] = {"ok": False, "error": detail}
        _set_loop_progress(job_id, state="error", phase=detail)
    except Exception as exc:
        _loop_results[job_id] = {"ok": False, "error": str(exc)}
        _set_loop_progress(job_id, state="error", phase=str(exc))


@app.post("/api/build/loop", response_model=ActionResult)
def build_loop(req: BuildLoopRequest) -> ActionResult:
    """Start agentic vision loop in background; poll /api/build/loop/status for live reasoning."""
    cfg = _load_config()
    ai = resolve_ai_config(cfg)
    job = _resolve_job(req.job_id)
    if job is None:
        job = job_store.create_job(title=job_store._slug_title(req.prompt), prompt=req.prompt)
    job_id = job["id"]

    _loop_results.pop(job_id, None)
    _set_loop_progress(
        job_id,
        state="running",
        iteration=0,
        max_iterations=req.max_iterations,
        stage="starting",
        progress_percent=2,
        phase="Starting AI vision loop…",
        reasoning="",
        feature_audit=[],
        issues=[],
        thinking_log=["AI vision loop started"],
    )

    req = req.model_copy(update={"job_id": job_id})
    thread = threading.Thread(
        target=_run_build_loop_thread,
        args=(req, job_id),
        daemon=True,
        name=f"build-loop-{job_id[:8]}",
    )
    thread.start()

    return ActionResult(
        ok=True,
        message="AI vision loop started — poll status for live reasoning",
        data={"job_id": job_id, "async": True, "vision": is_vision_model(ai["model"])},
    )


@app.post("/api/build/boat", response_model=ActionResult)
def build_boat() -> ActionResult:
    fc = _require_rpc()
    result = fc.execute_code(boat_code(BOAT_FCSTD))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Boat build failed"))
    objects = fc.get_objects("Boat")
    return ActionResult(
        ok=True,
        message=result.get("message", "Boat built"),
        data={"parts": [o.get("Name") for o in objects], "file": str(BOAT_FCSTD)},
    )


@app.post("/api/export/stl", response_model=ActionResult)
def export_stl(req: ExportRequest) -> ActionResult:
    active_job = job_store.get_active_job()
    if active_job:
        fc = _require_cad(active_job["id"])
        doc_name = active_job["freecad_doc"]
        fe.activate_job(fc, active_job, use_headless=_use_headless())
        job_store.clear_job_slice_dir(PRINT_DIR, active_job["id"])
        export_code = job_store.export_job_stl_code(doc_name, PRINT_DIR, active_job["id"])
        if _use_headless():
            script = (
                job_store.headless_open_document_code(doc_name, active_job["id"]).strip()
                + "\n\n"
                + export_code
            )
            result = hl.run_script(script)
        else:
            result = fc.execute_code(export_code)
    else:
        fc = _require_cad()
        doc_name = req.doc_name
        result = fc.execute_code(export_stl_code(doc_name, PRINT_DIR, req.target_length_mm))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Export failed"))
    if active_job:
        files = job_store.list_job_stl_files(PRINT_DIR, active_job["id"])
        out_dir = job_store.job_stl_dir(PRINT_DIR, active_job["id"])
    else:
        files = sorted(p.name for p in PRINT_DIR.glob("*.stl")) if PRINT_DIR.exists() else []
        out_dir = PRINT_DIR
    return ActionResult(
        ok=True,
        message=result.get("message", "Exported"),
        data={
            "files": files,
            "dir": str(out_dir),
            "job_id": active_job["id"] if active_job else None,
        },
    )


def _preview_doc_name(job_id: str | None = None) -> tuple[str | None, dict | None]:
    job = _resolve_job(job_id) if job_id else job_store.get_active_job()
    if job:
        return job["freecad_doc"], job
    return None, None


@app.get("/api/screenshot")
def screenshot(view: str = "Isometric", job_id: str | None = None) -> dict:
    fc = _require_rpc()
    doc_name, job = _preview_doc_name(job_id)
    if job:
        job_store.activate_job_in_freecad(fc, job)
    shot = capture_preview_image(
        fc, view_name=view, doc_name=doc_name, restore_after=_background_freecad()
    )
    if not shot.get("success"):
        raise HTTPException(status_code=400, detail=shot.get("error", "Screenshot failed"))
    return {"image": shot.get("image"), "mime": "image/png", "preview_url": "/api/screenshot.png"}


@app.get("/api/screenshot.png")
def screenshot_png(view: str = "Isometric", job_id: str | None = None) -> Response:
    fc = _require_rpc()
    doc_name, job = _preview_doc_name(job_id)
    if job:
        job_store.activate_job_in_freecad(fc, job)
    shot = capture_preview_image(
        fc, view_name=view, doc_name=doc_name, restore_after=_background_freecad()
    )
    if not shot.get("success") or not shot.get("image"):
        raise HTTPException(status_code=400, detail=shot.get("error", "Screenshot failed"))
    try:
        raw = base64.b64decode(shot["image"])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Invalid screenshot data: {exc}") from exc
    return Response(
        content=raw,
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/preview/stl")
def preview_stl(job_id: str | None = None) -> Response:
    """Export the job's document as one binary STL for the interactive viewer."""
    doc_name, job = _preview_doc_name(job_id)
    if not doc_name:
        raise HTTPException(status_code=404, detail="No active job/document to preview.")
    if not job:
        raise HTTPException(status_code=404, detail="No active job for STL preview.")
    try:
        out_path = _export_viewer_stl_path(job, doc_name)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=out_path.read_bytes(),
        media_type="model/stl",
        headers={"Cache-Control": "no-store"},
    )


def _ensure_freecad_gui() -> None:
    if not _freecad_running():
        if not FREECAD_EXE.exists():
            raise HTTPException(status_code=404, detail="FreeCAD not found")
        macro = str(START_RPC_MACRO) if START_RPC_MACRO.exists() else None
        launch_freecad_gui(
            str(FREECAD_EXE),
            macro,
            focus=not _background_freecad(),
            minimize=_background_freecad(),
        )
        _wait_for_rpc(45)
    if _background_freecad():
        minimize_freecad_window()
    else:
        focus_freecad_window()


@app.post("/api/freecad/focus", response_model=ActionResult)
def freecad_focus() -> ActionResult:
    cancel_background_minimize()
    if not _freecad_running():
        _ensure_freecad_gui()
    elif not _check_rpc():
        raise HTTPException(status_code=503, detail="FreeCAD is open but RPC is not connected.")
    else:
        focus_freecad_window()
    return ActionResult(ok=True, message="FreeCAD window brought to front")


@app.post("/api/open/freecad", response_model=ActionResult)
def open_freecad() -> ActionResult:
    _ensure_freecad_gui()
    return ActionResult(ok=True, message="FreeCAD opened — watch the 3D view while building")


@app.get("/api/services")
def services() -> dict:
    snap = _services_snapshot()
    return {
        **snap,
        "items": [
            {"id": "studio", "name": "CadForge API", "ok": snap["studio_api"], "detail": "Port 8787"},
            {
                "id": "freecad",
                "name": "FreeCAD",
                "ok": snap["cad_ready"],
                "detail": (
                    f"Headless ({snap.get('freecad_cmd_path') or 'FreeCADCmd'})"
                    if snap.get("freecad_mode") == "headless"
                    else "GUI process"
                ),
            },
            {
                "id": "rpc",
                "name": "MCP RPC Bridge" if snap.get("freecad_mode") != "headless" else "CAD engine",
                "ok": snap["cad_ready"],
                "detail": (
                    "Headless — no RPC"
                    if snap.get("freecad_mode") == "headless"
                    else ("Port 9875" if snap["rpc_bridge"] else "Not connected")
                ),
            },
            {
                "id": "slicer",
                "name": snap["slicer_name"] or "Slicer",
                "ok": snap["slicer_installed"],
                "detail": snap["printer_label"] or "Not installed",
            },
            {
                "id": "printer",
                "name": "Printer WiFi",
                "ok": snap["printer_online"],
                "detail": snap["printer_detail"],
            },
        ],
    }


@app.get("/api/printer")
def printer() -> dict:
    return _printer_info()


@app.get("/api/printer/camera")
def printer_camera() -> dict:
    printer = _printer_info()
    ip = printer.get("printer_ip")
    if not printer.get("printer_online") or not ip:
        return {
            "available": False,
            "printer_online": False,
            "message": "Printer offline — turn it on and connect to WiFi",
        }
    info = camera_info(ip)
    return {
        "printer_online": True,
        "printer_ip": ip,
        **info,
    }


@app.post("/api/printer/camera/webrtc")
def printer_camera_webrtc(req: WebRtcOfferRequest) -> dict:
    printer = _printer_info()
    ip = printer.get("printer_ip")
    if not printer.get("printer_online") or not ip:
        raise HTTPException(status_code=503, detail="Printer offline")
    try:
        answer = webrtc_exchange(ip, req.offer)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"answer": answer}


@app.get("/api/printer/camera/snapshot")
def printer_camera_snapshot() -> Response:
    printer = _printer_info()
    ip = printer.get("printer_ip")
    if not printer.get("printer_online") or not ip:
        raise HTTPException(status_code=503, detail="Printer offline")
    try:
        data, mime = fetch_snapshot(ip)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return Response(content=data, media_type=mime, headers={"Cache-Control": "no-store"})


@app.get("/api/printer/status")
def printer_status_live() -> dict:
    printer = _printer_info()
    active_job = job_store.get_active_job()
    gcode = _gcode_info(active_job)
    cad_stale, cad_stale_reason = _cad_export_stale(active_job)

    if not printer.get("printer_online") or not printer.get("printer_ip"):
        blockers = ["Printer offline — check power and WiFi"]
        if cad_stale and cad_stale_reason:
            blockers.append(cad_stale_reason)
        elif gcode.get("gcode_stale") and gcode.get("gcode_stale_reason"):
            blockers.append(gcode["gcode_stale_reason"])
        elif not gcode.get("gcode_ready"):
            blockers.append("No slice file ready — export and slice first")
        return {
            "online": False,
            "ready_to_print": False,
            "blockers": blockers,
            "warnings": [],
            "local": {
                "gcode_ready": gcode.get("gcode_ready", False),
                "gcode_stale": gcode.get("gcode_stale", False),
                "cad_stale": cad_stale,
                "gcode_file": gcode.get("gcode_file"),
                "gcode_print_time": gcode.get("gcode_print_time"),
                "gcode_filament_cm3": gcode.get("gcode_filament_cm3"),
            },
            "printer": None,
        }

    ip = printer["printer_ip"]
    try:
        live = live_status(ip)
    except Exception as exc:
        live = {
            "filament_loaded": False,
            "filament_label": "Could not read printer",
            "blockers": [str(exc)],
            "printer_ready": False,
        }

    blockers: list[str] = list(live.get("blockers") or [])
    warnings: list[str] = list(live.get("warnings") or [])
    if cad_stale and cad_stale_reason:
        blockers.append(cad_stale_reason)
    if gcode.get("gcode_stale") and gcode.get("gcode_stale_reason"):
        if gcode["gcode_stale_reason"] not in blockers:
            blockers.append(gcode["gcode_stale_reason"])
    if not gcode.get("gcode_ready"):
        blockers.append("No slice file on this PC — export STL and slice")

    ready = gcode.get("gcode_ready") and not gcode.get("gcode_stale") and not cad_stale and live.get("printer_ready")

    return {
        "online": True,
        "ready_to_print": ready,
        "blockers": blockers,
        "warnings": warnings,
        "local": {
            "gcode_ready": gcode.get("gcode_ready", False),
            "gcode_stale": gcode.get("gcode_stale", False),
            "cad_stale": cad_stale,
            "cad_stale_reason": cad_stale_reason,
            "gcode_file": gcode.get("gcode_file"),
            "gcode_print_time": gcode.get("gcode_print_time"),
            "gcode_filament_cm3": gcode.get("gcode_filament_cm3"),
            "gcode_layer_count": gcode.get("gcode_layer_count"),
        },
        "printer": {
            **live,
            "ip": ip,
            "label": printer.get("printer_label"),
        },
    }


@app.post("/api/printer/discover", response_model=ActionResult)
def discover_printer_endpoint() -> ActionResult:
    found = _printer_info(full_scan=True)
    if found["printer_online"]:
        return ActionResult(
            ok=True,
            message=f"Found {found['printer_label']} at {found['printer_ip']} on WiFi",
            data=found,
        )
    return ActionResult(
        ok=False,
        message=(
            f"No Creality printer found on {found['local_subnet']}.x — "
            "turn printer on, connect to same WiFi, then set printer_ip in config.toml"
        ),
        data=found,
    )


@app.post("/api/start-all", response_model=ActionResult)
def start_all() -> ActionResult:
    if _use_headless():
        if not hl.is_ready():
            raise HTTPException(
                status_code=503,
                detail=f"FreeCADCmd not found. Install FreeCAD or set freecad_cmd_path (expected near {FREECAD_CMD}).",
            )
        snap = _services_snapshot()
        return ActionResult(
            ok=True,
            message="Headless CAD engine ready — no GUI required.",
            data={"services": snap},
        )
    message = _connect_freecad_rpc()
    snap = _services_snapshot()
    return ActionResult(
        ok=True,
        message=message,
        data={"services": snap},
    )


@app.post("/api/open/rpc", response_model=ActionResult)
def open_rpc() -> ActionResult:
    return start_all()


def _open_slicer_impl() -> ActionResult:
    slicer = _slicer_info()
    exe = slicer["exe"]
    name = slicer["name"] or "slicer"
    if not exe:
        raise HTTPException(
            status_code=404,
            detail=f"No slicer found. Install Creality Print: {CREALITY_PRINT_DOWNLOAD}",
        )
    active_job = job_store.get_active_job()
    stls = _resolve_stl_paths(active_job)
    if not stls:
        raise HTTPException(status_code=404, detail="No STL files. Export first.")
    out_dir = _job_output_dir(active_job)
    subprocess.Popen([str(exe), *[str(p) for p in stls]], shell=False)
    net = _printer_info()
    label = slicer["printer_label"]
    wifi = ""
    if net["printer_online"] and net["printer_ip"]:
        wifi = f" — send to {net['printer_ip']} via WiFi in {name}"
    elif label:
        wifi = f" for {label}"
    return ActionResult(
        ok=True,
        message=(
            f"Opened {len(stls)} STL file(s) in {name}{wifi}. "
            f"Save G-code to {out_dir}"
        ),
        data={
            "slicer": name,
            "printer": label,
            "printer_ip": net["printer_ip"],
            "output_dir": str(out_dir),
            "stl_files": [p.name for p in stls],
        },
    )


@app.post("/api/open/slicer", response_model=ActionResult)
def open_slicer() -> ActionResult:
    return _open_slicer_impl()


@app.post("/api/open/orcaslicer", response_model=ActionResult)
def open_orcaslicer() -> ActionResult:
    return _open_slicer_impl()


def _resolve_gcode_path(job_id: str | None = None, name: str | None = None) -> Path:
    cfg = _load_config()
    job = job_store.load_job(job_id) if job_id else job_store.get_active_job()
    resolved_job_id = job["id"] if job else None
    path = find_gcode_file(cfg, PRINT_DIR, name, job_id=resolved_job_id)
    if not path:
        out_dir = _job_output_dir(job)
        raise HTTPException(status_code=404, detail=f"No G-code found in {out_dir}")
    return path


@app.get("/api/preview/gcode")
def preview_gcode(job_id: str | None = None, file: str | None = None) -> Response:
    path = _resolve_gcode_path(job_id, file)
    try:
        text = read_gcode_preview_text(path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=text,
        media_type="text/plain; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/preview/gcode/thumbnail")
def preview_gcode_thumbnail(job_id: str | None = None, file: str | None = None) -> Response:
    path = _resolve_gcode_path(job_id, file)
    thumb = extract_gcode_thumbnail(path)
    if not thumb:
        raise HTTPException(status_code=404, detail="No embedded thumbnail in this G-code file")
    data, mime = thumb
    return Response(content=data, media_type=mime)


def _export_active_job_stl(fc: FreeCADClient | fe.HeadlessCad, active_job: dict) -> list[Path]:
    fe.activate_job(fc, active_job, use_headless=_use_headless())
    job_store.clear_job_stl_dir(PRINT_DIR, active_job["id"])
    export_code = job_store.export_job_stl_code(
        active_job["freecad_doc"], PRINT_DIR, active_job["id"]
    )
    if _use_headless():
        script = (
            job_store.headless_open_document_code(active_job["freecad_doc"], active_job["id"]).strip()
            + "\n\n"
            + export_code
        )
        result = hl.run_script(script)
    else:
        result = fc.execute_code(export_code)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "STL export failed"))
    job_dir = job_store.job_stl_dir(PRINT_DIR, active_job["id"])
    stls = job_store.exportable_stl_paths(job_dir)
    if not stls:
        raise HTTPException(status_code=400, detail="No exportable solids in FreeCAD document")
    return stls


def _slice_active_job(req: SliceRequest) -> ActionResult:
    slicer = _slicer_info()
    if not slicer["orca_installed"]:
        raise HTTPException(status_code=404, detail="OrcaSlicer is required for auto-slice")
    active_job = job_store.get_active_job()
    if not active_job:
        raise HTTPException(status_code=404, detail="No active job")

    if req.wipe_slice:
        job_store.clear_job_slice_dir(PRINT_DIR, active_job["id"])

    cad_stale, _cad_reason = _cad_export_stale(active_job)
    refresh_cad = req.refresh_cad or cad_stale

    if refresh_cad:
        fc = _require_cad(active_job["id"])
        stls = _export_active_job_stl(fc, active_job)
    else:
        stls = _resolve_stl_paths(active_job)
        if not stls:
            raise HTTPException(
                status_code=404,
                detail="No STL files. Export first or use Re-slice to refresh from FreeCAD.",
            )

    out_dir = _job_output_dir(active_job)
    cfg = _load_config()
    try:
        gcode_path = slice_stls(stls, out_dir, cfg)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    meta = parse_gcode_meta(gcode_path)
    parts = [f"Sliced to {gcode_path.name} (auto-oriented and centered on bed)"]
    if refresh_cad:
        parts.append(f"exported {len(stls)} STL(s) from latest CAD")
    if req.wipe_slice:
        parts.append("cleared previous slice files")
    return ActionResult(
        ok=True,
        message=" — ".join(parts),
        data={
            "gcode_file": gcode_path.name,
            "gcode_path": str(gcode_path),
            "output_dir": str(out_dir),
            "stl_files": [p.name for p in stls],
            "refresh_cad": refresh_cad,
            "wipe_slice": req.wipe_slice,
            **meta,
        },
    )


@app.post("/api/slice/gcode", response_model=ActionResult)
def slice_gcode_endpoint(req: SliceRequest | None = None) -> ActionResult:
    return _slice_active_job(req or SliceRequest())


@app.post("/api/slice/reslice", response_model=ActionResult)
def reslice_gcode_endpoint() -> ActionResult:
    return _slice_active_job(SliceRequest(refresh_cad=True, wipe_slice=True))


@app.get("/api/printer/preflight")
def printer_preflight(job_id: str | None = None, file: str | None = None) -> dict:
    cfg = _load_config()
    printer = _printer_info()
    if not printer["printer_online"] or not printer["printer_ip"]:
        raise HTTPException(
            status_code=503,
            detail="Printer offline. Turn it on, connect to WiFi, then click Find Printer.",
        )
    job = _resolve_job(job_id) if job_id else job_store.get_active_job()
    gcode_path = find_gcode_file(cfg, PRINT_DIR, file, job_id=job["id"] if job else None)
    if not gcode_path:
        raise HTTPException(status_code=404, detail="No G-code file found for this job")
    gcode_info = _gcode_info(job)
    if gcode_info.get("gcode_stale"):
        return {
            "ok": False,
            "ready_to_send": False,
            "blockers": [gcode_info.get("gcode_stale_reason") or "G-code is out of date — re-slice first"],
            "warnings": [],
        }
    stls = _resolve_stl_paths(job)
    return preflight_send(printer["printer_ip"], gcode_path, stls)


@app.post("/api/send/print", response_model=ActionResult)
def send_print_job(req: SendPrintRequest | None = None) -> ActionResult:
    cfg = _load_config()
    printer = _printer_info()
    if not printer["printer_online"] or not printer["printer_ip"]:
        raise HTTPException(
            status_code=503,
            detail="Printer offline. Turn it on, connect to WiFi, then click Find Printer.",
        )
    if printer["printer_protocol"] == "moonraker":
        raise HTTPException(
            status_code=501,
            detail="Moonraker printers need Fluidd/Mainsail to send prints.",
        )

    name = req.gcode_file if req else None
    active_job = job_store.get_active_job()
    job_id = active_job["id"] if active_job else None
    gcode_path = find_gcode_file(cfg, PRINT_DIR, name, job_id=job_id)
    if not gcode_path:
        out_dir = _job_output_dir(active_job)
        raise HTTPException(
            status_code=404,
            detail=(
                "No sliced print file found. Click Auto-Slice (K2 uses .gcode.3mf), "
                f"or slice in OrcaSlicer, export to {out_dir}, then try again."
            ),
        )
    gcode_info = _gcode_info(active_job)
    if gcode_info.get("gcode_stale"):
        raise HTTPException(
            status_code=409,
            detail=gcode_info.get("gcode_stale_reason") or "G-code is out of date — re-slice first",
        )

    stls = _resolve_stl_paths(active_job)
    printer_ip = printer["printer_ip"]
    try:
        gcode_path = prepare_k2_upload(gcode_path, cfg)
        filename = upload_gcode(printer_ip, gcode_path)
        storage = _gcode_storage_path(cfg, filename)
        catalog_entry = wait_for_catalog_entry_sync(
            printer_ip,
            filename,
            max_attempts=5,
            delay_sec=2.0,
        )
        check = preflight_send(
            printer_ip,
            gcode_path,
            stls,
            catalog_entry=catalog_entry,
        )
        if catalog_entry is None:
            note = (
                f"{filename} is not indexed on the printer yet — upload succeeded; starting print anyway"
            )
            if note not in check["warnings"]:
                check["warnings"].append(note)
            check["ok"] = len(check["blockers"]) == 0
            check["ready_to_send"] = check["ok"]
        if not check["ok"]:
            raise HTTPException(
                status_code=409,
                detail="K2 is not ready to print:\n- " + "\n- ".join(check["blockers"]),
            )
        enable_self_test = (cfg.get("printer_enable_self_test") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        start_info = start_print(
            printer_ip,
            storage,
            print_path=gcode_path,
            cfg=cfg,
            enable_self_test=enable_self_test,
        )
        result = {
            "filename": filename,
            "local_path": str(gcode_path),
            "printer_path": storage,
            "printer_ip": printer_ip,
            "enable_self_test": enable_self_test,
            "preflight": check,
            "catalog_indexed": catalog_entry is not None,
            **start_info,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    if result.get("enable_self_test"):
        detail = "calibration/self-test running — wait for the nozzle to heat before plastic appears"
    else:
        detail = "print job confirmed on printer"

    return ActionResult(
        ok=True,
        message=(
            f"Sent {result['filename']} to {result['printer_ip']} over WiFi — {detail}"
        ),
        data=result,
    )


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")