"""Headless slicing via OrcaSlicer CLI."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from gcode_3mf_k2 import export_k2_flat_gcode, patch_gcode_3mf_for_k2

ORCA_EXE = Path(r"C:\Program Files\OrcaSlicer\orca-slicer.exe")
ORCA_SYSTEM = Path.home() / "AppData" / "Roaming" / "OrcaSlicer" / "system" / "Creality"


def _filament_suffix(model: str) -> str:
    normalized = model.upper().replace("-", " ").replace("_", " ")
    if "K2" in normalized:
        return "K2-all"
    if "K1" in normalized:
        return "K1-all"
    if "HI" in normalized:
        return "Hi-all"
    if "V3" in normalized or "V2" in normalized:
        return "Ender-3V3-all"
    if "5 MAX" in normalized or "5MAX" in normalized:
        return "Ender-5Max-all"
    return "K2-all"


def _resolve_profiles(cfg: dict[str, str]) -> tuple[Path, Path, Path]:
    model = cfg.get("printer_model", "K2").strip()
    nozzle = cfg.get("printer_nozzle", "0.4").strip()
    process_quality = cfg.get("slice_quality", "0.20mm Standard").strip()

    machine = ORCA_SYSTEM / "machine" / f"Creality {model} {nozzle} nozzle.json"
    if not machine.exists():
        candidates = sorted((ORCA_SYSTEM / "machine").glob(f"Creality {model}*.json"))
        candidates = [p for p in candidates if "nozzle" in p.name.lower()]
        if not candidates:
            raise FileNotFoundError(f"No OrcaSlicer machine profile for Creality {model}")
        machine = candidates[0]

    process_candidates = [
        ORCA_SYSTEM / "process" / f"{process_quality} @Creality {model} {nozzle} nozzle.json",
        ORCA_SYSTEM / "process" / f"{process_quality} @Creality {model.replace('-', '')} {nozzle} nozzle.json",
    ]
    process = next((p for p in process_candidates if p.exists()), None)
    if process is None:
        matches = sorted((ORCA_SYSTEM / "process").glob(f"{process_quality}*Creality*{model}*{nozzle}*.json"))
        if not matches:
            matches = sorted((ORCA_SYSTEM / "process").glob(f"*Standard*Creality*{model}*{nozzle}*.json"))
        if not matches:
            raise FileNotFoundError(f"No OrcaSlicer process profile for Creality {model}")
        process = matches[0]

    filament_name = cfg.get("filament_profile", "").strip()
    if filament_name:
        filament = ORCA_SYSTEM / "filament" / (
            filament_name if filament_name.endswith(".json") else f"{filament_name}.json"
        )
    else:
        suffix = _filament_suffix(model)
        filament = ORCA_SYSTEM / "filament" / f"Creality Generic PLA @{suffix}.json"
    if not filament.exists():
        matches = sorted((ORCA_SYSTEM / "filament").glob(f"*Generic PLA*@{_filament_suffix(model)}*.json"))
        if not matches:
            matches = sorted((ORCA_SYSTEM / "filament").glob("*Generic PLA*.json"))
        if not matches:
            raise FileNotFoundError("No OrcaSlicer filament profile found")
        filament = matches[0]

    return machine, process, filament


def resolve_print_bed(cfg: dict[str, str]) -> dict:
    """Read printable bed size from the OrcaSlicer machine profile (mm)."""
    overrides = {
        k: float(cfg[k])
        for k in ("bed_width_mm", "bed_depth_mm", "bed_height_mm")
        if cfg.get(k) not in (None, "")
    }
    try:
        machine_path, _, _ = _resolve_profiles(cfg)
        data = json.loads(machine_path.read_text(encoding="utf-8"))
        area = data.get("printable_area") or []
        xs: list[float] = []
        ys: list[float] = []
        for pt in area:
            raw = str(pt).lower().replace(" ", "")
            if "x" not in raw:
                continue
            x_s, y_s = raw.split("x", 1)
            xs.append(float(x_s))
            ys.append(float(y_s))
        width = max(xs) - min(xs) if xs else float(overrides.get("bed_width_mm", 260))
        depth = max(ys) - min(ys) if ys else float(overrides.get("bed_depth_mm", 260))
        height = float(data.get("printable_height") or overrides.get("bed_height_mm", 260))
        return {
            "bed_width_mm": overrides.get("bed_width_mm", width),
            "bed_depth_mm": overrides.get("bed_depth_mm", depth),
            "bed_height_mm": overrides.get("bed_height_mm", height),
            "printable_area": area,
            "bed_source": machine_path.name,
        }
    except Exception as exc:
        return {
            "bed_width_mm": overrides.get("bed_width_mm", 260.0),
            "bed_depth_mm": overrides.get("bed_depth_mm", 260.0),
            "bed_height_mm": overrides.get("bed_height_mm", 260.0),
            "printable_area": [],
            "bed_source": f"default ({exc.__class__.__name__})",
        }


def _patch_profile_for_cli(src: Path, dst: Path) -> None:
    data = json.loads(src.read_text(encoding="utf-8"))
    flavor = str(data.get("gcode_flavor", "")).lower()
    is_klipper = flavor == "klipper"

    layer = str(data.get("layer_gcode", "") or "")
    if "G92 E0" not in layer:
        data["layer_gcode"] = f"{layer}\nG92 E0".strip() if layer else "G92 E0"

    if not is_klipper:
        start = str(data.get("machine_start_gcode", "") or "")
        if "M83" in start:
            data["machine_start_gcode"] = start.replace("M83", "M82")
        if data.get("type") == "machine":
            data["use_relative_e_distances"] = "0"

    dst.write_text(json.dumps(data, indent=4), encoding="utf-8")


def _patch_filament_for_cli(src: Path, dst: Path) -> None:
    """Ensure filament density is explicit so Orca emits weight/volume metadata."""
    data = json.loads(src.read_text(encoding="utf-8"))
    densities = data.get("filament_density")
    if not densities or str(densities[0]).strip() in ("", "0", "0.0"):
        data["filament_density"] = ["1.24"]
    dst.write_text(json.dumps(data, indent=4), encoding="utf-8")


def _k2_printer(cfg: dict[str, str]) -> bool:
    return "K2" in cfg.get("printer_model", "K2").upper()


def _prefer_3mf_export(cfg: dict[str, str]) -> bool:
    fmt = cfg.get("slice_format", "auto").strip().lower()
    if fmt == "3mf":
        return True
    if fmt == "gcode":
        return False
    model = cfg.get("printer_model", "").upper()
    return "K2" in model


def _cfg_bool(cfg: dict[str, str], key: str, default: bool = True) -> bool:
    raw = cfg.get(key)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _placement_args(cfg: dict[str, str]) -> list[str]:
    """Creality Print-style auto orient + center on bed before slicing."""
    args: list[str] = []
    if _cfg_bool(cfg, "slice_auto_orient", True):
        args.extend(["--orient", "1"])
    if _cfg_bool(cfg, "slice_auto_arrange", True):
        args.extend(["--arrange", "1"])
    if _cfg_bool(cfg, "slice_ensure_on_bed", True):
        args.append("--ensure-on-bed")
    if _cfg_bool(cfg, "slice_allow_rotations", True):
        args.append("--allow-rotations")
    return args


def slice_stls(
    stl_paths: list[Path],
    output_dir: Path,
    cfg: dict[str, str] | None = None,
    timeout_sec: int = 300,
) -> Path:
    if not ORCA_EXE.exists():
        raise FileNotFoundError(f"OrcaSlicer not found at {ORCA_EXE}")
    if not stl_paths:
        raise ValueError("No STL files to slice")

    cfg = cfg or {}
    output_dir.mkdir(parents=True, exist_ok=True)
    machine, process, filament = _resolve_profiles(cfg)

    with tempfile.TemporaryDirectory(prefix="orca_slice_") as tmp:
        patched_machine = Path(tmp) / "machine.json"
        patched_process = Path(tmp) / "process.json"
        patched_filament = Path(tmp) / "filament.json"
        _patch_profile_for_cli(machine, patched_machine)
        _patch_profile_for_cli(process, patched_process)
        _patch_filament_for_cli(filament, patched_filament)
        settings = f"{patched_machine};{patched_process}"
        export_3mf = _prefer_3mf_export(cfg)
        stem = stl_paths[0].stem
        output_3mf = output_dir / f"{stem}.gcode.3mf"
        cmd = [
            str(ORCA_EXE),
            *_placement_args(cfg),
            "--load-settings",
            settings,
            "--load-filaments",
            str(patched_filament),
            "--slice",
            "0",
            *[str(p) for p in stl_paths],
        ]
        if export_3mf:
            cmd.extend(["--export-3mf", str(output_3mf)])
            if _cfg_bool(cfg, "slice_min_save", False):
                cmd.append("--min-save")
        else:
            cmd.extend(["--outputdir", str(output_dir)])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "OrcaSlicer slice failed").strip()
            raise RuntimeError(detail[-800:])

    if export_3mf:
        if not output_3mf.exists():
            matches = sorted(
                output_dir.glob("*.gcode.3mf"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not matches:
                raise RuntimeError("OrcaSlicer finished but no .gcode.3mf file was created")
            output_3mf = matches[0]
        if _k2_printer(cfg):
            patch_gcode_3mf_for_k2(output_3mf)
            export_k2_flat_gcode(output_3mf)
        return output_3mf

    gcode_files = sorted(output_dir.glob("*.gcode"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not gcode_files:
        raise RuntimeError("OrcaSlicer finished but no .gcode file was created")
    return gcode_files[0]
