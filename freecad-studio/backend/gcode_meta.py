"""Parse metadata and embedded thumbnails from slicer G-code and 3MF files."""
from __future__ import annotations

import base64
import re
import zipfile
from pathlib import Path

_TIME_PATTERNS = [
    re.compile(r";\s*estimated printing time[^=]*=\s*(.+)", re.I),
    re.compile(r";\s*total estimated time:\s*(.+)", re.I),
    re.compile(r";\s*model printing time:\s*(.+)", re.I),
    re.compile(r";\s*TIME:\s*([\d.]+)", re.I),
]
_FILAMENT_MM = re.compile(r";\s*filament used \[mm\]\s*=\s*([\d.]+)", re.I)
_FILAMENT_M = re.compile(r";\s*Filament used:\s*([\d.]+)m", re.I)
_FILAMENT_G = re.compile(r";\s*filament used \[g\]\s*=\s*([\d.]+)", re.I)
_LAYER_HEIGHT = re.compile(r";\s*layer_height\s*=\s*([\d.]+)", re.I)
_LAYER_HEIGHT_ORCA = re.compile(r";\s*Layer height:\s*([\d.]+)", re.I)
_LAYER_COUNT = re.compile(r";\s*total layer number:\s*(\d+)", re.I)


_FILAMENT_WEIGHT = re.compile(r";\s*Filament Weight:([\d.]+)", re.I)
_FILAMENT_CM3 = re.compile(r";\s*filament used \[cm3\]\s*=\s*([\d.]+)", re.I)
_TOTAL_LAYERS = re.compile(r";\s*total layers count\s*=\s*(\d+)", re.I)
_TIME_ORCA = re.compile(r";\s*estimated printing time \(normal mode\)\s*=\s*(.+)", re.I)
_GCODE_OBJECT = re.compile(r";\s*EXCLUDE_OBJECT_DEFINE NAME=(\S+)", re.I)


def _read_head(path: Path, limit: int = 512_000) -> str:
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(limit)


def _read_tail(path: Path, limit: int = 512_000) -> str:
    size = path.stat().st_size
    if size <= limit:
        return path.read_text(encoding="utf-8", errors="replace")
    with path.open("rb") as handle:
        handle.seek(max(0, size - limit))
        return handle.read().decode("utf-8", errors="replace")


def _parse_thumbnail_block(text: str) -> tuple[bytes, str] | None:
    match = re.search(
        r";\s*THUMBNAIL_BLOCK_START\s*(.*?)\s*;\s*THUMBNAIL_BLOCK_END",
        text,
        re.S | re.I,
    )
    if not match:
        return None

    block = match.group(1)
    header = re.search(
        r";\s*(PNG|JPG|JPEG|QOI)\s+begin\s+(\d+)x(\d+)\s+(\d+)",
        block,
        re.I,
    )
    if not header:
        return None

    fmt = header.group(1).upper()
    payload = "".join(
        line[1:].strip()
        for line in block.splitlines()
        if line.startswith(";") and " begin " not in line and " end" not in line.lower()
    )
    payload = re.sub(r"\s+", "", payload)
    if not payload:
        return None

    try:
        raw = base64.b64decode(payload, validate=False)
    except Exception:
        return None

    mime = "image/png" if fmt == "PNG" else "image/jpeg"
    return raw, mime


def _parse_prusa_thumbnail(text: str) -> tuple[bytes, str] | None:
    match = re.search(
        r";\s*thumbnail begin\s+\d+x\d+\s+\d+\s*(.*?)\s*;\s*thumbnail end",
        text,
        re.S | re.I,
    )
    if not match:
        return None
    payload = re.sub(r"\s+", "", match.group(1))
    if not payload.startswith(";"):
        payload = "".join(
            line[1:].strip()
            for line in match.group(1).splitlines()
            if line.startswith(";")
        )
    payload = re.sub(r"\s+", "", payload)
    if not payload:
        return None
    try:
        return base64.b64decode(payload, validate=False), "image/png"
    except Exception:
        return None


def is_3mf_package(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".3mf") or name.endswith(".gcode.3mf")


def read_gcode_preview_text(path: Path, limit: int | None = None) -> str:
    """Return plain G-code text suitable for toolpath preview."""
    if is_3mf_package(path):
        text = embedded_gcode_text(path)
        if not text:
            raise ValueError(f"No embedded G-code found in {path.name}")
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
    if limit is not None and len(text) > limit:
        return text[:limit]
    return text


def embedded_gcode_text(path: Path) -> str | None:
    if not is_3mf_package(path):
        return None
    try:
        with zipfile.ZipFile(path, "r") as archive:
            plate_names = sorted(
                name
                for name in archive.namelist()
                if name.startswith("Metadata/plate_") and name.endswith(".gcode")
            )
            for name in ("Metadata/plate_1.gcode", "Metadata/plate_0.gcode"):
                if name in archive.namelist():
                    return archive.read(name).decode("utf-8", errors="replace")
            if plate_names:
                return archive.read(plate_names[0]).decode("utf-8", errors="replace")
    except (OSError, zipfile.BadZipFile, KeyError):
        return None
    return None


def extract_gcode_thumbnail(path: Path) -> tuple[bytes, str] | None:
    if is_3mf_package(path):
        text = embedded_gcode_text(path) or ""
        if not text:
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    for name in archive.namelist():
                        if name.lower().endswith((".png", ".jpg", ".jpeg")):
                            raw = archive.read(name)
                            mime = "image/jpeg" if name.lower().endswith((".jpg", ".jpeg")) else "image/png"
                            return raw, mime
            except (OSError, zipfile.BadZipFile):
                return None
    else:
        text = _read_head(path)
    return _parse_thumbnail_block(text) or _parse_prusa_thumbnail(text)


def gcode_stl_names(path: Path) -> set[str]:
    if is_3mf_package(path):
        text = (embedded_gcode_text(path) or "")[:200_000]
    else:
        text = _read_head(path, limit=200_000)
    names: set[str] = set()
    for raw in _GCODE_OBJECT.findall(text):
        if "_id_" in raw:
            names.add(raw.split("_id_", 1)[0])
        elif raw.endswith(".stl"):
            names.add(raw)
        else:
            names.add(f"{raw}.stl")
    return names


def gcode_matches_stls(gcode_path: Path, stl_paths: list[Path]) -> bool:
    if not stl_paths:
        return False
    expected = {path.name for path in stl_paths}
    found = gcode_stl_names(gcode_path)
    if not found:
        return True
    return found == expected


def parse_gcode_meta(path: Path) -> dict:
    if is_3mf_package(path):
        embedded = embedded_gcode_text(path)
        if not embedded:
            return {
                "print_time": None,
                "filament_mm": None,
                "filament_g": None,
                "filament_cm3": None,
                "layer_height": None,
                "layer_count": None,
                "has_thumbnail": extract_gcode_thumbnail(path) is not None,
                "format": "3mf",
            }
        lines = embedded.splitlines()
        head = "\n".join(lines[:4000])
        tail = "\n".join(lines[-4000:])
        text = f"{head}\n{tail}"
    else:
        head = _read_head(path)
        tail = _read_tail(path)
        text = f"{head}\n{tail}"
    meta: dict[str, str | float | int | None] = {
        "print_time": None,
        "filament_mm": None,
        "filament_g": None,
        "filament_cm3": None,
        "layer_height": None,
        "layer_count": None,
        "has_thumbnail": False,
    }

    for pattern in (_TIME_ORCA, *_TIME_PATTERNS):
        hit = pattern.search(text)
        if hit:
            raw = hit.group(1).strip()
            try:
                seconds = float(raw)
                hours = int(seconds // 3600)
                minutes = int((seconds % 3600) // 60)
                meta["print_time"] = f"{hours}h {minutes}m" if hours else f"{minutes}m"
            except ValueError:
                meta["print_time"] = raw
            break

    hit = _FILAMENT_M.search(text)
    if hit:
        meta["filament_mm"] = float(hit.group(1)) * 1000

    hit = _FILAMENT_WEIGHT.search(text)
    if hit:
        meta["filament_g"] = float(hit.group(1))

    for key, pattern, cast in (
        ("filament_mm", _FILAMENT_MM, float),
        ("filament_g", _FILAMENT_G, float),
        ("filament_cm3", _FILAMENT_CM3, float),
        ("layer_height", _LAYER_HEIGHT, float),
        ("layer_count", _LAYER_COUNT, int),
    ):
        if key == "filament_mm" and meta["filament_mm"] is not None:
            continue
        if key == "filament_g" and meta["filament_g"] is not None:
            continue
        if key == "layer_count" and meta["layer_count"] is not None:
            continue
        hit = pattern.search(text)
        if hit:
            meta[key] = cast(hit.group(1))

    if meta["layer_count"] is None:
        hit = _TOTAL_LAYERS.search(text)
        if hit:
            meta["layer_count"] = int(hit.group(1))

    if meta["layer_height"] is None:
        hit = _LAYER_HEIGHT_ORCA.search(text)
        if hit:
            meta["layer_height"] = float(hit.group(1))

    meta["has_thumbnail"] = (
        _parse_thumbnail_block(head) is not None
        or _parse_prusa_thumbnail(head) is not None
    )
    if is_3mf_package(path):
        meta["has_thumbnail"] = bool(
            meta["has_thumbnail"] or extract_gcode_thumbnail(path) is not None
        )
    if is_3mf_package(path):
        meta["format"] = "3mf"
    else:
        meta["format"] = "gcode"
    return meta
