"""Pre-send validation for Creality K-series printers (K2 WebSocket protocol)."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import websockets

from gcode_meta import embedded_gcode_text, gcode_matches_stls, is_3mf_package, parse_gcode_meta


def _run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _connect_ws(uri: str):
    try:
        return await websockets.connect(uri, subprotocols=["wsslicer"], open_timeout=8)
    except TypeError:
        return await websockets.connect(uri, open_timeout=8)


async def _fetch_snapshot(printer_ip: str) -> dict:
    uri = f"ws://{printer_ip}:9999/"
    async with await _connect_ws(uri) as ws:
        payload = await asyncio.wait_for(ws.recv(), timeout=8)
        data = json.loads(payload)
        return data if isinstance(data, dict) else {}


async def _fetch_gcode_catalog(printer_ip: str) -> list[dict]:
    uri = f"ws://{printer_ip}:9999/"
    async with await _connect_ws(uri) as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)
        await ws.send(json.dumps({"method": "get", "params": {"reqGcodeFile": 1}}))
        chunks: list[str] = []
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            try:
                chunks.append(await asyncio.wait_for(ws.recv(), timeout=1))
            except asyncio.TimeoutError:
                break

    entries: list[dict] = []
    for chunk in chunks:
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for key in ("retGcodeFileInfo2", "retGcodeFileInfo"):
            block = data.get(key)
            if isinstance(block, list):
                entries.extend(block)
    return entries


def _flatten_catalog(entries: list[dict]) -> list[dict]:
    flat: list[dict] = []
    for entry in entries:
        nested = entry.get("file")
        if isinstance(nested, list):
            flat.extend(nested)
        else:
            flat.append(entry)
    return flat


def _catalog_lookup_names(filename: str) -> tuple[str, ...]:
    """Return upload filename plus K2 indexer aliases for .gcode.3mf packages."""
    names = [filename]
    lower = filename.lower()
    if lower.endswith(".gcode.3mf"):
        # K2 extracts embedded plate gcode as e.g. model.gcode.3mf -> model.gcode_plate_1.gcode
        names.append(f"{filename[:-4]}_plate_1.gcode")
    elif lower.endswith(".3mf"):
        names.append(f"{Path(filename).stem}_plate_1.gcode")
    return tuple(dict.fromkeys(names))


def _catalog_entry_for_name(entries: list[dict], filename: str) -> dict | None:
    aliases = set(_catalog_lookup_names(filename))
    for entry in _flatten_catalog(entries):
        if entry.get("name") in aliases:
            return entry
    return None


def _local_gcode_issues(path: Path, stl_paths: list[Path] | None = None) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return ["Print file not found on this PC"], warnings
    if path.stat().st_size < 1024:
        blockers.append("Print file is suspiciously small")
    meta = parse_gcode_meta(path)
    if not meta.get("layer_count"):
        blockers.append("Sliced file has no layer count metadata")
    if is_3mf_package(path):
        embedded = embedded_gcode_text(path)
        if not embedded:
            blockers.append("3MF package has no embedded G-code")
        elif " G1 " in embedded[:400_000] and " E" not in embedded[:400_000] and " E-" not in embedded[:400_000]:
            blockers.append("Embedded G-code appears to contain no extrusion moves")
    else:
        text_head = path.read_text(encoding="utf-8", errors="replace")[:400_000]
        if " G1 " in text_head and " E" not in text_head and " E-" not in text_head:
            blockers.append("G-code appears to contain no extrusion moves")
    if stl_paths and not gcode_matches_stls(path, stl_paths):
        blockers.append("Sliced file was built from different STL files than the current export")
    return blockers, warnings


def _catalog_issues(entry: dict | None, filename: str) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []

    if entry is None:
        warnings.append(
            f"{filename} is not indexed on the printer yet — upload may still be processing"
        )
        return blockers, warnings

    model_x = int(entry.get("modelX") or 0)
    model_y = int(entry.get("modelY") or 0)
    model_z = int(entry.get("modelZ") or 0)
    if model_x <= 0 and model_y <= 0 and model_z <= 0:
        warnings.append(
            "K2 reports zero model size for this file — preview on the printer may be blank, "
            "but the job can still print if the slice file has valid layer data."
        )

    check = entry.get("fileCheckResult")
    if check not in (None, 1, "1"):
        blockers.append(f"K2 file validation failed (fileCheckResult={check})")

    validated = entry.get("validation_completed")
    if validated is False:
        blockers.append("K2 has not finished validating this file")

    software = str(entry.get("software") or "")
    if software == "OrcaSlicer" and model_x <= 0:
        warnings.append(
            "OrcaSlicer G-code may lack K2 preview metadata — printing can still work via WiFi send"
        )
    return blockers, warnings


def _snapshot_issues(snapshot: dict) -> tuple[list[str], list[str]]:
    """Return (blockers, warnings) from live printer WebSocket snapshot."""
    blockers: list[str] = []
    warnings: list[str] = []

    err = snapshot.get("err") or {}
    if isinstance(err, dict) and int(err.get("errcode") or 0) != 0:
        blockers.append(
            f"Printer error {err.get('errcode')}: {err.get('value') or 'see printer screen'}"
        )

    material = int(snapshot.get("materialStatus") or 0)
    cfs = int(snapshot.get("cfsConnect") or 0)
    state = int(snapshot.get("state") or 0)
    total_layers = int(snapshot.get("TotalLayer") or 0)
    print_file = (snapshot.get("printFileName") or "").strip()

    # K2 often reports materialStatus=0 when no runout sensor is fitted — warn, don't block.
    if material == 0:
        if cfs == 1:
            warnings.append(
                "CFS connected — confirm a spool is selected/loaded on the printer before printing"
            )
        else:
            warnings.append(
                "Filament sensor not triggered (common on K2 without sensor) — confirm filament is loaded"
            )

    # Idle K2 often reports TotalLayer=0 even when a file path is shown — not a send blocker.
    if print_file and total_layers == 0 and state not in (1, 2):
        name = print_file.rsplit("/", 1)[-1] or print_file
        warnings.append(
            f"Printer is idle (screen may show {name!r} with 0 layers — normal until a print starts). "
            "Send uploads and starts your current slice from CadForge."
        )

    return blockers, warnings


async def preflight_async(
    printer_ip: str,
    gcode_path: Path,
    stl_paths: list[Path] | None = None,
    *,
    catalog_entry: dict | None = None,
) -> dict:
    filename = gcode_path.name
    snapshot = await _fetch_snapshot(printer_ip)
    entry = catalog_entry
    if entry is None:
        catalog = await _fetch_gcode_catalog(printer_ip)
        entry = _catalog_entry_for_name(catalog, filename)

    blockers: list[str] = []
    warnings: list[str] = []

    local_blockers, local_warnings = _local_gcode_issues(gcode_path, stl_paths)
    blockers.extend(local_blockers)
    warnings.extend(local_warnings)

    snap_blockers, snap_warnings = _snapshot_issues(snapshot)
    blockers.extend(snap_blockers)
    warnings.extend(snap_warnings)

    cat_blockers, cat_warnings = _catalog_issues(entry, filename)
    blockers.extend(cat_blockers)
    warnings.extend(cat_warnings)

    ok = len(blockers) == 0
    return {
        "ok": ok,
        "ready_to_send": ok,
        "blockers": blockers,
        "warnings": warnings,
        "printer_ip": printer_ip,
        "gcode_file": filename,
        "printer_snapshot": {
            "state": snapshot.get("state"),
            "printFileName": snapshot.get("printFileName"),
            "TotalLayer": snapshot.get("TotalLayer"),
            "printProgress": snapshot.get("printProgress"),
            "materialStatus": snapshot.get("materialStatus"),
            "cfsConnect": snapshot.get("cfsConnect"),
            "nozzleTemp": snapshot.get("nozzleTemp"),
            "targetNozzleTemp": snapshot.get("targetNozzleTemp"),
            "bedTemp0": snapshot.get("bedTemp0"),
        },
        "printer_file": {
            "name": entry.get("name") if entry else None,
            "modelX": entry.get("modelX") if entry else None,
            "modelY": entry.get("modelY") if entry else None,
            "modelZ": entry.get("modelZ") if entry else None,
            "fileCheckResult": entry.get("fileCheckResult") if entry else None,
            "validation_completed": entry.get("validation_completed") if entry else None,
            "software": entry.get("software") if entry else None,
            "timeCost": entry.get("timeCost") if entry else None,
        },
        "local_gcode": parse_gcode_meta(gcode_path),
    }


async def wait_for_catalog_entry(
    printer_ip: str,
    filename: str,
    *,
    max_attempts: int = 5,
    delay_sec: float = 1.5,
) -> dict | None:
    """Poll printer file catalog until *filename* appears (post-upload indexing lag)."""
    entry: dict | None = None
    for attempt in range(max_attempts):
        catalog = await _fetch_gcode_catalog(printer_ip)
        entry = _catalog_entry_for_name(catalog, filename)
        if entry is not None:
            return entry
        if attempt < max_attempts - 1:
            await asyncio.sleep(delay_sec)
    return None


def wait_for_catalog_entry_sync(
    printer_ip: str,
    filename: str,
    *,
    max_attempts: int = 5,
    delay_sec: float = 1.5,
) -> dict | None:
    return _run(
        wait_for_catalog_entry(
            printer_ip,
            filename,
            max_attempts=max_attempts,
            delay_sec=delay_sec,
        )
    )


def preflight_send(
    printer_ip: str,
    gcode_path: Path,
    stl_paths: list[Path] | None = None,
    *,
    catalog_entry: dict | None = None,
) -> dict:
    return _run(
        preflight_async(
            printer_ip,
            gcode_path,
            stl_paths,
            catalog_entry=catalog_entry,
        )
    )
