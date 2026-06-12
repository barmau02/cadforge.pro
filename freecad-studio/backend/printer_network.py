from __future__ import annotations

import concurrent.futures
import re
import socket
import subprocess
from typing import Callable

CREALITY_WS_PORT = 9999
CREALITY_CAMERA_PORT = 8000
MOONRAKER_PORT = 7125
HTTP_PORT = 80


def _tcp_open(host: str, port: int, timeout: float = 0.8) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _local_subnet() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
        parts = ip.split(".")
        if len(parts) == 4:
            return ".".join(parts[:3])
    except OSError:
        pass
    return "192.168.1"


def _arp_neighbors() -> list[str]:
    try:
        result = subprocess.run(["arp", "-a"], capture_output=True, text=True, timeout=5, check=False)
    except Exception:
        return []

    ips: list[str] = []
    for line in result.stdout.splitlines():
        match = re.search(r"(\d{1,3}(?:\.\d{1,3}){3})", line)
        if not match:
            continue
        ip = match.group(1)
        if ip.endswith(".255") or ip.endswith(".1"):
            continue
        if ip not in ips:
            ips.append(ip)
    return ips


def _probe_host(ip: str) -> dict | None:
    if _tcp_open(ip, CREALITY_WS_PORT):
        return {"ip": ip, "port": CREALITY_WS_PORT, "protocol": "creality_ws"}
    if _tcp_open(ip, MOONRAKER_PORT):
        return {"ip": ip, "port": MOONRAKER_PORT, "protocol": "moonraker"}
    return None


def discover_printer(full_scan: bool = False) -> dict | None:
    candidates = _arp_neighbors()
    for ip in candidates:
        hit = _probe_host(ip)
        if hit:
            return hit

    if not full_scan:
        return None

    subnet = _local_subnet()
    scan_ips = [f"{subnet}.{n}" for n in range(2, 255)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as pool:
        for hit in pool.map(_probe_host, scan_ips, chunksize=16):
            if hit:
                return hit
    return None


def printer_status(
    printer_ip: str = "",
    load_config: Callable[[], dict[str, str]] | None = None,
    full_scan: bool = False,
) -> dict:
    cfg = load_config() if load_config else {}
    ip = (printer_ip or cfg.get("printer_ip", "")).strip()
    brand = cfg.get("printer_brand", "Creality")
    model = cfg.get("printer_model", "")
    label = f"{brand} {model}".strip()

    discovered: dict | None = None
    if ip:
        hit = _probe_host(ip)
        if hit:
            discovered = hit
    else:
        discovered = discover_printer(full_scan=full_scan)
        if discovered:
            ip = discovered["ip"]

    online = discovered is not None
    protocol = discovered["protocol"] if discovered else None
    port = discovered["port"] if discovered else CREALITY_WS_PORT
    camera_available = bool(ip and online and protocol == "creality_ws" and _tcp_open(ip, CREALITY_CAMERA_PORT))

    if online:
        detail = f"{ip}:{port} on WiFi ({protocol})"
    elif ip:
        detail = f"{ip} configured but offline — check power & WiFi"
    else:
        detail = "Not found on WiFi — set printer_ip in config.toml or click Find Printer"

    return {
        "printer_online": online,
        "printer_ip": ip or None,
        "printer_port": port if online else None,
        "printer_protocol": protocol,
        "printer_label": label,
        "printer_detail": detail,
        "local_subnet": _local_subnet(),
        "camera_available": camera_available,
        "camera_port": CREALITY_CAMERA_PORT if camera_available else None,
        "camera_type": "webrtc" if camera_available else None,
    }