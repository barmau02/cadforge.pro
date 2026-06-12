"""Parse Python model code and slicer profiles into an Inventor-style feature tree."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from gcode_meta import parse_gcode_meta
from orca_slice import _resolve_profiles, resolve_print_bed

TreeNode = dict[str, Any]

_PARAM_SINGLE = re.compile(
    r"^([A-Z][A-Z0-9_]*)\s*=\s*(.+?)\s*(?:#.*)?$",
)
_PARAM_MULTI = re.compile(
    r"^([A-Z][A-Z0-9_]*(?:\s*,\s*[A-Z][A-Z0-9_]*)+)\s*=\s*(.+?)\s*(?:#.*)?$",
)
_OP_PART = re.compile(
    r"^(\w+)\s*=\s*Part\.(make\w+)\(",
)
_OP_BOOL = re.compile(
    r"^(\w+)\s*=\s*(\w+)\.(fuse|cut|common|removeSplitter|makeFillet)\(",
)
_OP_ASSIGN = re.compile(
    r"^(\w+)\s*=\s*(\w+)\.(fuse|cut|common|removeSplitter|makeFillet)\(",
)
_SECTION = re.compile(r"^#\s*(.+)$")
_FEATURES = re.compile(r"^#\s*Features:\s*(.+)$", re.I)

_SLICER_EDITABLE_KEYS = {
    "slice_quality",
    "printer_nozzle",
    "filament_profile",
    "printer_model",
}

_MACHINE_KEYS = (
    "printer_model",
    "nozzle_diameter",
    "printable_height",
    "gcode_flavor",
    "default_print_profile",
)
_PROCESS_KEYS = (
    "layer_height",
    "sparse_infill_density",
    "wall_loops",
    "top_shell_layers",
    "bottom_shell_layers",
    "brim_type",
    "support_type",
)
_FILAMENT_KEYS = (
    "filament_type",
    "nozzle_temperature",
    "nozzle_temperature_initial_layer",
    "bed_temperature",
    "bed_temperature_initial_layer_single",
)


def _format_value(value: float | int | str) -> str:
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value == int(value):
            return f"{int(value)}.0"
        return f"{value:g}"
    return str(value)


def _literal_value(raw: str) -> float | int | str | None:
    raw = raw.strip().rstrip(",")
    try:
        node = ast.literal_eval(raw)
    except (SyntaxError, ValueError):
        return raw if raw else None
    if isinstance(node, (int, float, str, bool)):
        return node
    return raw


def _split_rhs_values(raw: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in raw:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def extract_parameters(code: str) -> list[dict[str, Any]]:
    params: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_no, line in enumerate(code.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        multi = _PARAM_MULTI.match(stripped)
        if multi:
            names = [n.strip() for n in multi.group(1).split(",")]
            values = _split_rhs_values(multi.group(2))
            if len(names) != len(values):
                continue
            for name, raw in zip(names, values):
                if name in seen:
                    continue
                seen.add(name)
                params.append({
                    "id": f"param:{name}",
                    "kind": "parameter",
                    "name": name,
                    "value": _literal_value(raw),
                    "raw": raw,
                    "line": line_no,
                    "editable": isinstance(_literal_value(raw), (int, float)),
                })
            continue
        single = _PARAM_SINGLE.match(stripped)
        if single:
            name = single.group(1)
            if name in seen:
                continue
            seen.add(name)
            raw = single.group(2).strip()
            params.append({
                "id": f"param:{name}",
                "kind": "parameter",
                "name": name,
                "value": _literal_value(raw),
                "raw": raw,
                "line": line_no,
                "editable": isinstance(_literal_value(raw), (int, float)),
            })
    return params


def extract_design_intent(code: str) -> list[TreeNode]:
    nodes: list[TreeNode] = []
    for line in code.splitlines():
        match = _FEATURES.match(line.strip())
        if not match:
            continue
        chunks = re.split(r",\s*(?=[a-z_]+(?:\s|$))", match.group(1))
        for chunk in chunks:
            text = chunk.strip()
            if not text:
                continue
            nodes.append({
                "id": f"intent:{len(nodes)}",
                "kind": "intent",
                "name": text.split()[0] if text.split() else f"feature_{len(nodes)}",
                "label": text,
                "editable": False,
            })
        break
    return nodes


def features_from_code_comment(code: str) -> dict[str, Any]:
    """Rebuild a feature checklist from the # Features: comment in generated Python."""
    intent = extract_design_intent(code)
    if not intent:
        return {"summary": "", "features": []}
    return {
        "summary": "Features declared in the current Python script",
        "features": [
            {
                "name": str(item.get("name") or f"feature_{i}"),
                "description": str(item.get("label") or item.get("name") or ""),
                "priority": "required",
            }
            for i, item in enumerate(intent)
        ],
    }


def extract_operations(code: str) -> list[TreeNode]:
    roots: list[TreeNode] = []
    current_section: TreeNode | None = None
    op_index = 0

    def add_op(node: TreeNode) -> None:
        nonlocal op_index
        op_index += 1
        node["id"] = f"op:{op_index}"
        if current_section is not None:
            current_section.setdefault("children", []).append(node)
        else:
            roots.append(node)

    for line in code.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            section_match = _SECTION.match(stripped)
            if section_match and not _FEATURES.match(stripped):
                title = section_match.group(1).strip()
                if title.lower().startswith("features:"):
                    continue
                if title.lower().startswith("parametric"):
                    continue
                current_section = {
                    "id": f"section:{len(roots)}",
                    "kind": "section",
                    "name": title,
                    "label": title,
                    "editable": False,
                    "children": [],
                }
                roots.append(current_section)
            continue

        part = _OP_PART.match(stripped)
        if part:
            add_op({
                "kind": "operation",
                "name": part.group(1),
                "label": f"{part.group(1)} = Part.{part.group(2)}(...)",
                "operation": part.group(2),
                "editable": False,
            })
            continue

        op = _OP_ASSIGN.match(stripped)
        if op:
            add_op({
                "kind": "operation",
                "name": op.group(1),
                "label": f"{op.group(1)} = {op.group(2)}.{op.group(3)}(...)",
                "operation": op.group(3),
                "editable": False,
            })
            continue

        if ".makeFillet(" in stripped or ".fillet(" in stripped.lower():
            add_op({
                "kind": "operation",
                "name": "fillet",
                "label": stripped.split("#", 1)[0].strip(),
                "operation": "makeFillet",
                "editable": False,
            })

    return roots


def patch_parameter(code: str, name: str, new_value: float | int | str) -> str:
    target = name.strip().upper()
    formatted = _format_value(new_value)
    lines = code.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(rf"^{re.escape(target)}\s*=", stripped):
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f"{indent}{target} = {formatted}"
            return "\n".join(lines)
        multi = _PARAM_MULTI.match(stripped)
        if multi and target in [n.strip() for n in multi.group(1).split(",")]:
            names = [n.strip() for n in multi.group(1).split(",")]
            values = _split_rhs_values(multi.group(2))
            if len(names) != len(values):
                continue
            idx = names.index(target)
            values[idx] = formatted
            indent = line[: len(line) - len(line.lstrip())]
            lines[i] = f"{indent}{', '.join(names)} = {', '.join(values)}"
            return "\n".join(lines)
    raise ValueError(f"Parameter '{name}' not found in Python code")


def _profile_fields(data: dict[str, Any], keys: tuple[str, ...]) -> list[TreeNode]:
    nodes: list[TreeNode] = []
    for key in keys:
        if key not in data:
            continue
        val = data[key]
        if isinstance(val, list):
            val = val[0] if len(val) == 1 else val
        nodes.append({
            "id": f"slicer:{key}",
            "kind": "slicer_meta",
            "name": key,
            "label": key.replace("_", " "),
            "value": val,
            "editable": key in _SLICER_EDITABLE_KEYS,
        })
    return nodes


def resolve_slicer_tree(cfg: dict[str, str], gcode_path: Path | None = None) -> list[TreeNode]:
    bed = resolve_print_bed(cfg)
    roots: list[TreeNode] = [
        {
            "id": "slicer:bed",
            "kind": "group",
            "name": "Print bed",
            "label": "Print bed",
            "editable": False,
            "children": [
                {
                    "id": "slicer:bed_size",
                    "kind": "slicer_meta",
                    "name": "bed_size_mm",
                    "label": "Bed size (mm)",
                    "value": f"{bed['bed_width_mm']:.0f} × {bed['bed_depth_mm']:.0f} × {bed['bed_height_mm']:.0f}",
                    "editable": False,
                },
                {
                    "id": "slicer:bed_source",
                    "kind": "slicer_meta",
                    "name": "bed_source",
                    "label": "Profile source",
                    "value": bed.get("bed_source"),
                    "editable": False,
                },
            ],
        }
    ]

    config_nodes: list[TreeNode] = []
    for key in sorted(_SLICER_EDITABLE_KEYS):
        if cfg.get(key):
            config_nodes.append({
                "id": f"config:{key}",
                "kind": "slicer_meta",
                "name": key,
                "label": key.replace("_", " "),
                "value": cfg[key],
                "editable": True,
                "source": "config.toml",
            })
    if config_nodes:
        roots.append({
            "id": "slicer:config",
            "kind": "group",
            "name": "Studio config",
            "label": "Studio config (config.toml)",
            "editable": False,
            "children": config_nodes,
        })

    try:
        machine_path, process_path, filament_path = _resolve_profiles(cfg)
        machine = json.loads(machine_path.read_text(encoding="utf-8"))
        process = json.loads(process_path.read_text(encoding="utf-8"))
        filament = json.loads(filament_path.read_text(encoding="utf-8"))
        roots.extend([
            {
                "id": "slicer:machine",
                "kind": "group",
                "name": "Machine profile",
                "label": machine_path.name,
                "editable": False,
                "children": _profile_fields(machine, _MACHINE_KEYS),
            },
            {
                "id": "slicer:process",
                "kind": "group",
                "name": "Process profile",
                "label": process_path.name,
                "editable": False,
                "children": _profile_fields(process, _PROCESS_KEYS),
            },
            {
                "id": "slicer:filament",
                "kind": "group",
                "name": "Filament profile",
                "label": filament_path.name,
                "editable": False,
                "children": _profile_fields(filament, _FILAMENT_KEYS),
            },
        ])
    except Exception as exc:
        roots.append({
            "id": "slicer:error",
            "kind": "meta",
            "name": "slicer_profiles",
            "label": "Slicer profiles unavailable",
            "value": str(exc),
            "editable": False,
        })

    if gcode_path and gcode_path.exists():
        meta = parse_gcode_meta(gcode_path)
        gcode_nodes = [
            {
                "id": f"gcode:{key}",
                "kind": "gcode_meta",
                "name": key,
                "label": key.replace("_", " "),
                "value": meta.get(key),
                "editable": False,
            }
            for key in (
                "print_time",
                "layer_height",
                "layer_count",
                "filament_g",
                "filament_mm",
                "filament_cm3",
                "format",
            )
            if meta.get(key) is not None
        ]
        if gcode_nodes:
            roots.append({
                "id": "slicer:gcode",
                "kind": "group",
                "name": "G-code output",
                "label": gcode_path.name,
                "editable": False,
                "children": gcode_nodes,
            })

    return roots


def freecad_object_nodes(objects: list[dict[str, Any]]) -> list[TreeNode]:
    nodes: list[TreeNode] = []
    for obj in objects:
        shape = obj.get("Shape") or {}
        children: list[TreeNode] = []
        if shape.get("Volume"):
            children.append({
                "id": f"fc:{obj.get('Name')}:volume",
                "kind": "meta",
                "name": "volume_mm3",
                "label": "Volume (mm³)",
                "value": round(shape["Volume"], 2),
                "editable": False,
            })
        if shape.get("BoundBox"):
            bb = shape["BoundBox"]
            children.append({
                "id": f"fc:{obj.get('Name')}:bbox",
                "kind": "meta",
                "name": "bound_box",
                "label": "Bound box (mm)",
                "value": (
                    f"{bb.get('XLength', 0):.1f} × {bb.get('YLength', 0):.1f} × {bb.get('ZLength', 0):.1f}"
                    if isinstance(bb, dict)
                    else str(bb)
                ),
                "editable": False,
            })
        props = obj.get("Properties") or {}
        if isinstance(props, dict):
            for key, val in list(props.items())[:8]:
                if isinstance(val, (int, float, str, bool)):
                    children.append({
                        "id": f"fc:{obj.get('Name')}:{key}",
                        "kind": "meta",
                        "name": key,
                        "label": key,
                        "value": val,
                        "editable": False,
                    })
        nodes.append({
            "id": f"fc:{obj.get('Name')}",
            "kind": "freecad_object",
            "name": obj.get("Name", "?"),
            "label": obj.get("Label") or obj.get("Name", "?"),
            "type": obj.get("TypeId", ""),
            "editable": False,
            "children": children,
        })
    return nodes


def _count_operations(nodes: list[TreeNode]) -> int:
    total = 0
    for node in nodes:
        if node.get("kind") == "operation":
            total += 1
        total += _count_operations(node.get("children") or [])
    return total


def build_feature_tree(
    code: str,
    cfg: dict[str, str],
    *,
    freecad_objects: list[dict[str, Any]] | None = None,
    gcode_path: Path | None = None,
    doc_name: str | None = None,
) -> dict[str, Any]:
    parameters = extract_parameters(code)
    operations = extract_operations(code)
    intent = extract_design_intent(code)
    slicer = resolve_slicer_tree(cfg, gcode_path)
    fc_nodes = freecad_object_nodes(freecad_objects or [])

    tree: list[TreeNode] = [
        {
            "id": "group:parameters",
            "kind": "group",
            "name": "Parameters",
            "label": "Parameters",
            "editable": False,
            "children": [
                {
                    "id": p["id"],
                    "kind": "parameter",
                    "name": p["name"],
                    "label": p["name"],
                    "value": p["value"],
                    "line": p["line"],
                    "editable": p["editable"],
                }
                for p in parameters
            ],
        },
    ]

    if intent:
        tree.append({
            "id": "group:intent",
            "kind": "group",
            "name": "Design intent",
            "label": "Design intent",
            "editable": False,
            "children": intent,
        })

    if operations:
        tree.append({
            "id": "group:operations",
            "kind": "group",
            "name": "Build history",
            "label": "Build history",
            "editable": False,
            "children": operations,
        })

    if fc_nodes:
        tree.append({
            "id": "group:freecad",
            "kind": "group",
            "name": "FreeCAD objects",
            "label": doc_name or "FreeCAD document",
            "editable": False,
            "children": fc_nodes,
        })

    tree.append({
        "id": "group:slicer",
        "kind": "group",
        "name": "Slicer metadata",
        "label": "Slicer & print metadata",
        "editable": False,
        "children": slicer,
    })

    return {
        "tree": tree,
        "parameters": parameters,
        "parameter_count": len(parameters),
        "operation_count": _count_operations(operations),
        "doc_name": doc_name,
    }
