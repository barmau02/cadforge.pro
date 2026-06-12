"""Live Creality printer status from WebSocket snapshot (port 9999)."""
from __future__ import annotations

import asyncio
import json

import websockets

from creality_preflight import _snapshot_issues


def _run(coro):
    try:
        asyncio.get_running_loop()
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


def _state_label(state: int) -> str:
    labels = {
        0: "Idle",
        1: "Printing",
        2: "Paused",
        3: "Finished",
        4: "Stopped",
    }
    return labels.get(state, f"State {state}")


def _filament_label(material: int, cfs: int) -> str:
    if material == 1:
        return "Detected"
    if cfs == 1:
        return "Sensor empty (check CFS spool)"
    return "Not reported (no sensor?)"


def format_live_status(snapshot: dict) -> dict:
    material = int(snapshot.get("materialStatus") or 0)
    cfs = int(snapshot.get("cfsConnect") or 0)
    state = int(snapshot.get("state") or 0)
    progress = int(snapshot.get("printProgress") or 0)
    total_layers = int(snapshot.get("TotalLayer") or 0)
    target_nozzle = snapshot.get("targetNozzleTemp")
    nozzle = snapshot.get("nozzleTemp")
    bed = snapshot.get("bedTemp0")
    target_bed = snapshot.get("targetBedTemp0") or snapshot.get("targetBedTemp")

    blockers, warnings = _snapshot_issues(snapshot)

    return {
        "filament_loaded": material == 1,
        "filament_status": material,
        "filament_label": _filament_label(material, cfs),
        "cfs_connected": cfs == 1,
        "print_state": state,
        "print_state_label": _state_label(state),
        "print_file": (snapshot.get("printFileName") or "").strip() or None,
        "print_progress": progress,
        "total_layers": total_layers,
        "nozzle_temp": nozzle,
        "target_nozzle_temp": target_nozzle,
        "bed_temp": bed,
        "target_bed_temp": target_bed,
        "material_detect": snapshot.get("materialDetect"),
        "feed_state": snapshot.get("feedState"),
        "enable_self_test": snapshot.get("enableSelfTest"),
        "blockers": blockers,
        "warnings": warnings,
        "printer_ready": len(blockers) == 0 and state not in (1,),
    }


async def live_status_async(printer_ip: str) -> dict:
    snapshot = await _fetch_snapshot(printer_ip)
    return format_live_status(snapshot)


def live_status(printer_ip: str) -> dict:
    return _run(live_status_async(printer_ip))
