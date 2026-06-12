"""Send sliced jobs to a Creality printer over WiFi (HTTP upload + WebSocket start)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import requests
import websockets

from gcode_meta import is_3mf_package
from gcode_3mf_k2 import export_k2_flat_gcode, patch_gcode_3mf_for_k2

K1_GCODE_DIR = "/usr/data/printer_data/gcodes"
K2_GCODE_DIR = "/mnt/UDISK/printer_data/gcodes"


def _default_gcode_storage(cfg: dict[str, str]) -> str:
    explicit = cfg.get("printer_gcode_storage", "").strip()
    if explicit:
        return explicit.rstrip("/")
    model = cfg.get("printer_model", "").upper()
    if "K2" in model or "K1" in model or "HI" in model:
        return K2_GCODE_DIR
    return K1_GCODE_DIR


def _gcode_storage_path(cfg: dict[str, str], filename: str) -> str:
    base = _default_gcode_storage(cfg)
    return f"{base}/{filename}"


def _print_file_patterns(cfg: dict[str, str] | None = None) -> tuple[str, ...]:
    """Prefer plain .gcode for K2 — printer UI reads metadata reliably from flat gcode only."""
    if cfg and "K2" in cfg.get("printer_model", "").upper():
        return ("*.gcode", "*.gcode.3mf", "*.3mf")
    return ("*.gcode.3mf", "*.3mf", "*.gcode")


def find_gcode_file(
    cfg: dict[str, str],
    print_dir: Path,
    name: str | None = None,
    job_id: str | None = None,
) -> Path | None:
    if name:
        for base in _gcode_search_dirs(cfg, print_dir, job_id):
            candidate = base / name
            if candidate.exists():
                return candidate
        return None

    newest: Path | None = None
    newest_mtime = -1.0
    for base in _gcode_search_dirs(cfg, print_dir, job_id):
        if not base.exists():
            continue
        for pattern in _print_file_patterns(cfg):
            for path in base.glob(pattern):
                lower = path.name.lower()
                if path.suffix.lower() == ".gcode" and lower.endswith(".gcode.3mf"):
                    continue
                if lower.startswith("_viewer") or lower.startswith("_preview"):
                    continue
                mtime = path.stat().st_mtime
                if mtime > newest_mtime:
                    newest = path
                    newest_mtime = mtime
    return newest


def _gcode_search_dirs(cfg: dict[str, str], print_dir: Path, job_id: str | None = None) -> list[Path]:
    ordered: list[Path] = []
    extra = cfg.get("gcode_dir", "").strip()
    if extra:
        ordered.append(Path(extra))
    if job_id:
        ordered.append(print_dir / job_id)
    ordered.append(print_dir)

    seen: set[str] = set()
    dirs: list[Path] = []
    for base in ordered:
        key = str(base.resolve()) if base.exists() else str(base)
        if key in seen:
            continue
        seen.add(key)
        dirs.append(base)
    return dirs


def upload_gcode(printer_ip: str, gcode_path: Path, timeout: int = 180) -> str:
    filename = gcode_path.name
    url = f"http://{printer_ip}/upload/{filename}"
    with gcode_path.open("rb") as handle:
        response = requests.post(
            url,
            files={"file": (filename, handle, "application/octet-stream")},
            timeout=timeout,
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Upload failed ({response.status_code}): {response.text[:300]}")
    return filename


def _use_multicolor_start(print_path: Path, cfg: dict[str, str]) -> bool:
    """Use CFS multiColorPrint only when explicitly enabled.

    Default spool-holder path (opGcodeFile + printprt:) works for plain .gcode and
    .gcode.3mf on K2 without requiring colorMatch / CFS slot mapping first.
    """
    if cfg.get("printer_multicolor_print", "").strip().lower() in ("1", "true", "yes", "on"):
        return is_3mf_package(print_path)
    return False


def _build_start_command(
    printer_path: str,
    print_path: Path,
    cfg: dict[str, str],
    enable_self_test: bool,
) -> dict:
    params: dict = {"enableSelfTest": 1 if enable_self_test else 0}
    if _use_multicolor_start(print_path, cfg):
        params = {
            "multiColorPrint": {
                "gcode": printer_path,
                "enableSelfTest": 1 if enable_self_test else 0,
            }
        }
    else:
        params = {
            "opGcodeFile": f"printprt:{printer_path}",
            "enableSelfTest": 1 if enable_self_test else 0,
        }
    return {"method": "set", "params": params}


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def _parse_status(payload: str) -> dict | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _file_loaded(status: dict, printer_path: str) -> bool:
    loaded = (status.get("printFileName") or "").strip()
    if not loaded:
        return False
    return loaded.endswith(Path(printer_path).name) or loaded == printer_path


async def _connect_ws(uri: str):
    try:
        return await websockets.connect(uri, subprotocols=["wsslicer"], open_timeout=8)
    except TypeError:
        return await websockets.connect(uri, open_timeout=8)


async def _start_print_ws(
    printer_ip: str,
    printer_path: str,
    print_path: Path,
    cfg: dict[str, str] | None = None,
    enable_self_test: bool = False,
    confirm_timeout: float = 20,
) -> dict:
    cfg = cfg or {}
    uri = f"ws://{printer_ip}:9999/"
    cmd = _build_start_command(printer_path, print_path, cfg, enable_self_test)

    async with await _connect_ws(uri) as ws:
        try:
            await asyncio.wait_for(ws.recv(), timeout=5)
        except asyncio.TimeoutError:
            pass

        await ws.send(json.dumps(cmd, separators=(",", ":")))

        deadline = asyncio.get_running_loop().time() + confirm_timeout
        while asyncio.get_running_loop().time() < deadline:
            remaining = max(0.1, deadline - asyncio.get_running_loop().time())
            try:
                payload = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            status = _parse_status(payload)
            if status and _file_loaded(status, printer_path):
                return {
                    "confirmed": True,
                    "state": status.get("state"),
                    "enableSelfTest": status.get("enableSelfTest"),
                    "printProgress": status.get("printProgress"),
                    "targetNozzleTemp": status.get("targetNozzleTemp"),
                }

    raise RuntimeError(
        "Upload succeeded but the printer did not confirm the print job. "
        "Check the printer screen — it may need confirmation, or stop the current job and try again."
    )


def start_print(
    printer_ip: str,
    printer_path: str,
    print_path: Path | None = None,
    cfg: dict[str, str] | None = None,
    enable_self_test: bool = False,
) -> dict:
    local_path = print_path or Path(printer_path)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            _start_print_ws(
                printer_ip,
                printer_path,
                local_path,
                cfg,
                enable_self_test,
            )
        )
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(
            asyncio.run,
            _start_print_ws(
                printer_ip,
                printer_path,
                local_path,
                cfg,
                enable_self_test,
            ),
        ).result()


def prepare_k2_upload(gcode_path: Path, cfg: dict[str, str] | None = None) -> Path:
    """Patch K2 packages and prefer flat .gcode for printer UI metadata."""
    cfg = cfg or {}
    model = cfg.get("printer_model", "").upper()
    if "K2" not in model:
        return gcode_path
    if gcode_path.name.lower().endswith(".gcode.3mf"):
        patch_gcode_3mf_for_k2(gcode_path)
        flat = export_k2_flat_gcode(gcode_path)
        if flat is not None:
            return flat
    return gcode_path


def send_print(
    printer_ip: str,
    gcode_path: Path,
    cfg: dict[str, str] | None = None,
) -> dict:
    cfg = cfg or {}
    gcode_path = prepare_k2_upload(gcode_path, cfg)
    filename = upload_gcode(printer_ip, gcode_path)
    storage = _gcode_storage_path(cfg, filename)
    enable_self_test = _truthy(cfg.get("printer_enable_self_test"), default=False)
    start_info = start_print(
        printer_ip,
        storage,
        print_path=gcode_path,
        cfg=cfg,
        enable_self_test=enable_self_test,
    )
    return {
        "filename": filename,
        "local_path": str(gcode_path),
        "printer_path": storage,
        "printer_ip": printer_ip,
        "enable_self_test": enable_self_test,
        "print_format": "3mf" if is_3mf_package(gcode_path) else "gcode",
        **start_info,
    }