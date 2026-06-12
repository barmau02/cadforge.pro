"""Multiview capture for the AI vision loop — no GUI or Qt required.

Primary path: FreeCADCmd + Coin SoOffscreenRenderer (OfflineRenderingUtils.buildScene)
writes PNGs via renderer.getBuffer() + PIL. Works on Windows without simage or Qt offscreen.

Fallback: orthographic renders from merged viewer STL using matplotlib.
"""
from __future__ import annotations

import base64
import os
import tempfile
from pathlib import Path
from typing import Any

import headless_freecad as hl
import jobs as job_store

ROOT = Path(__file__).resolve().parent.parent
RENDER_WIDTH = 1280
RENDER_HEIGHT = 960
RENDER_TIMEOUT = 180

EXTERIOR_VIEWS = ("Isometric", "Front", "Top", "Right", "Back")
SECTION_VIEWS = ("SectionFront", "SectionTop", "SectionRight")
SPATIAL_VIEWS = EXTERIOR_VIEWS + SECTION_VIEWS

# Coin orthographic camera rotations matching FreeCAD standard views (axis xyz, angle rad).
_VIEW_CAMERA_ROTATIONS: dict[str, list[tuple[float, float, float, float]]] = {
    "Isometric": [(1, 0, 0, -0.785398), (0, 0, 1, 0.615479)],
    "Front": [(1, 0, 0, -1.570796)],
    "Top": [(1, 0, 0, -1.570796), (0, 0, 1, -1.570796)],
    "Right": [(1, 0, 0, -1.570796), (0, 0, 1, 1.570796)],
    "Back": [(1, 0, 0, -1.570796), (0, 0, 1, 3.141593)],
    "Left": [(1, 0, 0, -1.570796), (0, 0, 1, -1.570796)],
    "Bottom": [(1, 0, 0, 3.141593)],
}

# Section views reuse the exterior camera but clip at bbox mid-plane (internal cut).
_VIEW_SECTION_AXIS: dict[str, tuple[str, str]] = {
    "SectionFront": ("Front", "y"),
    "SectionTop": ("Top", "z"),
    "SectionRight": ("Right", "x"),
}


def _view_camera_name(view_name: str) -> str:
    if view_name in _VIEW_SECTION_AXIS:
        return _VIEW_SECTION_AXIS[view_name][0]
    return view_name


def _view_section_axis(view_name: str) -> str | None:
    if view_name in _VIEW_SECTION_AXIS:
        return _VIEW_SECTION_AXIS[view_name][1]
    return None


def _render_dir(job_id: str) -> Path:
    return job_store.job_fcstd_dir(job_id) / "renders"


def _png_to_b64(path: Path) -> str | None:
    if not path.is_file() or path.stat().st_size < 100:
        return None
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _generate_coin_render_script(
    fcstd_path: Path,
    outputs: list[tuple[str, Path]],
    *,
    width: int,
    height: int,
) -> str:
    fcstd_esc = str(fcstd_path).replace("\\", "\\\\")
    out_map = {name: str(path).replace("\\", "\\\\") for name, path in outputs}
    rots_repr = repr(_VIEW_CAMERA_ROTATIONS)
    section_repr = repr(_VIEW_SECTION_AXIS)

    return f'''
import os
import FreeCAD as App
import Part
import OfflineRenderingUtils as ORU
from pivy import coin
from PIL import Image

FCSTD = r"{fcstd_esc}"
OUTPUTS = {repr(out_map)}
VIEW_ROTS = {rots_repr}
VIEW_SECTIONS = {section_repr}
WIDTH = {int(width)}
HEIGHT = {int(height)}

if not os.path.isfile(FCSTD):
    raise RuntimeError("FCStd missing: " + FCSTD)

doc = App.openDocument(FCSTD)
objects = []
for obj in doc.Objects:
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull() or shape.Volume <= 1e-6:
        continue
    objects.append(obj)
if not objects:
    raise RuntimeError("No solids to render in " + doc.Name)

bb = objects[0].Shape.BoundBox
for obj in objects[1:]:
    bb.add(obj.Shape.BoundBox)
CENTER = App.Vector((bb.XMin + bb.XMax) * 0.5, (bb.YMin + bb.YMax) * 0.5, (bb.ZMin + bb.ZMax) * 0.5)

def _half_shape(shape, axis, center):
    b = shape.BoundBox
    if axis == "x":
        w = max(center.x - b.XMin, 1e-6)
        box = Part.makeBox(w, b.YLength, b.ZLength)
        box.translate(App.Vector(b.XMin, b.YMin, b.ZMin))
    elif axis == "y":
        h = max(center.y - b.YMin, 1e-6)
        box = Part.makeBox(b.XLength, h, b.ZLength)
        box.translate(App.Vector(b.XMin, b.YMin, b.ZMin))
    elif axis == "z":
        h = max(center.z - b.ZMin, 1e-6)
        box = Part.makeBox(b.XLength, b.YLength, h)
        box.translate(App.Vector(b.XMin, b.YMin, b.ZMin))
    else:
        return shape
    try:
        cut = shape.common(box)
        return cut if not cut.isNull() and cut.Volume > 1e-6 else shape
    except Exception:
        return shape

def _camera(view_name):
    cam = coin.SoOrthographicCamera()
    rot = coin.SbRotation.identity()
    for axis in VIEW_ROTS.get(view_name, VIEW_ROTS.get("Isometric", [])):
        rot *= coin.SbRotation(coin.SbVec3f(axis[0], axis[1], axis[2]), axis[3])
    cam.orientation = rot
    return cam

def _build_scene(view_name):
    section_axis = None
    if view_name in VIEW_SECTIONS:
        _, section_axis = VIEW_SECTIONS[view_name]
    camera_name = VIEW_SECTIONS.get(view_name, (view_name,))[0] if view_name in VIEW_SECTIONS else view_name
    render_objs = []
    for obj in objects:
        shape = obj.Shape
        if section_axis:
            shape = _half_shape(shape, section_axis, CENTER)
        feat = doc.addObject("Part::Feature", "PFClip_" + obj.Name + "_" + view_name)
        feat.Shape = shape
        render_objs.append(feat)
    try:
        scene = ORU.buildScene(render_objs)
    finally:
        for feat in render_objs:
            try:
                doc.removeObject(feat.Name)
            except Exception:
                pass
    return scene, camera_name

def _render_view(view_name, out_path):
    scene, camera_name = _build_scene(view_name)
    if scene is None:
        raise RuntimeError("Could not build Coin scene for " + view_name)
    cam = _camera(camera_name)
    root = coin.SoSeparator()
    root.addChild(coin.SoDirectionalLight())
    root.addChild(cam)
    root.addChild(scene)
    vp = coin.SbViewportRegion(WIDTH, HEIGHT)
    cam.viewAll(root, vp)
    renderer = coin.SoOffscreenRenderer(vp)
    renderer.setBackgroundColor(coin.SbColor(1.0, 1.0, 1.0))
    root.ref()
    ok = renderer.render(root)
    root.unref()
    if not ok:
        raise RuntimeError("Coin render failed for " + view_name)
    buf = renderer.getBuffer()
    if not buf:
        raise RuntimeError("Empty render buffer for " + view_name)
    img = Image.frombytes("RGB", (WIDTH, HEIGHT), bytes(buf))
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    img.save(out_path)
    print("PF_RENDER_OK:", view_name, out_path, os.path.getsize(out_path))

for _view, _path in OUTPUTS.items():
    _render_view(_view, _path)

try:
    App.closeDocument(doc.Name)
except Exception:
    pass
'''


def capture_multiview_from_fcstd(
    job_id: str,
    doc_name: str,
    *,
    views: tuple[str, ...] = SPATIAL_VIEWS,
    width: int = RENDER_WIDTH,
    height: int = RENDER_HEIGHT,
) -> dict[str, Any]:
    """Render multiview PNGs from job FCStd via Coin offscreen (FreeCADCmd, no GUI)."""
    fcstd = job_store.job_fcstd_path(job_id, doc_name)
    if not fcstd.is_file() or fcstd.stat().st_size == 0:
        return {
            "success": False,
            "error": f"No saved model yet ({fcstd.name}). Run build/execute first.",
            "views": [],
            "images": [],
            "method": "coin-offscreen",
        }

    out_dir = _render_dir(job_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[tuple[str, Path]] = []
    for view in views:
        outputs.append((view, out_dir / f"{view.lower()}.png"))

    script = _generate_coin_render_script(fcstd, outputs, width=width, height=height)
    run = hl.run_script(script, timeout=RENDER_TIMEOUT)
    if not run.get("success"):
        detail = run.get("error") or run.get("message") or "Coin render failed"
        return {
            "success": False,
            "error": detail,
            "views": [],
            "images": [],
            "method": "coin-offscreen",
        }

    captured_views: list[str] = []
    captured_images: list[str] = []
    for view, path in outputs:
        b64 = _png_to_b64(path)
        if b64:
            captured_views.append(view)
            captured_images.append(b64)

    if not captured_images:
        msg = run.get("message") or "Coin render completed but no PNG files were written."
        return {
            "success": False,
            "error": msg,
            "views": [],
            "images": [],
            "method": "coin-offscreen",
        }

    return {
        "success": True,
        "views": captured_views,
        "images": captured_images,
        "image": captured_images[0],
        "primary_view": captured_views[0],
        "method": "coin-offscreen",
    }


def _read_binary_stl(path: Path) -> tuple[list[tuple[float, float, float]], list[tuple[int, int, int]]]:
    """Minimal binary STL reader returning vertices and triangle indices."""
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError("STL too small")
    tri_count = int.from_bytes(data[80:84], "little")
    verts: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    index_map: dict[tuple[float, float, float], int] = {}

    def _idx(v: tuple[float, float, float]) -> int:
        key = (round(v[0], 4), round(v[1], 4), round(v[2], 4))
        if key not in index_map:
            index_map[key] = len(verts)
            verts.append(key)
        return index_map[key]

    offset = 84
    for _ in range(tri_count):
        if offset + 50 > len(data):
            break
        offset += 12  # normal
        tri: list[int] = []
        for _v in range(3):
            x = float.from_bytes(data[offset : offset + 4], "little")
            y = float.from_bytes(data[offset + 4 : offset + 8], "little")
            z = float.from_bytes(data[offset + 8 : offset + 12], "little")
            offset += 12
            tri.append(_idx((x, y, z)))
        offset += 2  # attribute
        faces.append((tri[0], tri[1], tri[2]))
    return verts, faces


def capture_multiview_from_stl(
    stl_path: Path,
    *,
    views: tuple[str, ...] = SPATIAL_VIEWS,
    width: int = RENDER_WIDTH,
    height: int = RENDER_HEIGHT,
) -> dict[str, Any]:
    """Fallback orthographic renders from a merged STL (weaker than Coin renders)."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    except ImportError:
        return {
            "success": False,
            "error": "matplotlib not installed for STL vision fallback",
            "views": [],
            "images": [],
            "method": "stl-matplotlib",
        }

    if not stl_path.is_file():
        return {
            "success": False,
            "error": f"STL not found: {stl_path}",
            "views": [],
            "images": [],
            "method": "stl-matplotlib",
        }

    try:
        verts, faces = _read_binary_stl(stl_path)
    except Exception as exc:
        return {
            "success": False,
            "error": f"Could not read STL: {exc}",
            "views": [],
            "images": [],
            "method": "stl-matplotlib",
        }

    if not verts or not faces:
        return {
            "success": False,
            "error": "STL has no geometry",
            "views": [],
            "images": [],
            "method": "stl-matplotlib",
        }

    xs = [v[0] for v in verts]
    ys = [v[1] for v in verts]
    zs = [v[2] for v in verts]
    mid = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
    span = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)

    camera_angles: dict[str, tuple[int, int]] = {
        "Isometric": (25, 45),
        "Front": (0, 0),
        "Top": (90, 0),
        "Right": (0, 90),
        "Back": (0, 180),
    }

    captured_views: list[str] = []
    captured_images: list[str] = []

    for view in views:
        section_axis = _view_section_axis(view)
        camera_name = _view_camera_name(view)
        elev, azim = camera_angles.get(camera_name, (25, 45))

        use_verts = verts
        use_faces = faces
        if section_axis:
            axis_idx = {"x": 0, "y": 1, "z": 2}[section_axis]
            limit = mid[axis_idx]
            filtered_faces: list[tuple[int, int, int]] = []
            for face in faces:
                cx = sum(verts[i][axis_idx] for i in face) / 3.0
                if cx <= limit + 1e-6:
                    filtered_faces.append(face)
            if filtered_faces:
                use_faces = filtered_faces

        fig = plt.figure(figsize=(width / 100, height / 100), dpi=100)
        ax = fig.add_subplot(111, projection="3d")
        tri_vertices = [[verts[i] for i in face] for face in use_faces]
        mesh = Poly3DCollection(tri_vertices, alpha=0.95, edgecolor="0.25", linewidth=0.15)
        mesh.set_facecolor("#6ea8d8")
        ax.add_collection3d(mesh)
        ax.set_xlim(mid[0] - span / 2, mid[0] + span / 2)
        ax.set_ylim(mid[1] - span / 2, mid[1] + span / 2)
        ax.set_zlim(mid[2] - span / 2, mid[2] + span / 2)
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
        ax.set_box_aspect((1, 1, 1))
        fig.patch.set_facecolor("white")
        fig.tight_layout(pad=0)
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        try:
            fig.savefig(tmp.name, facecolor="white", bbox_inches="tight", pad_inches=0.05)
            b64 = _png_to_b64(Path(tmp.name))
            if b64:
                captured_views.append(view)
                captured_images.append(b64)
        finally:
            plt.close(fig)
            try:
                os.unlink(tmp.name)
            except OSError:
                pass

    if not captured_images:
        return {
            "success": False,
            "error": "STL render produced no images",
            "views": [],
            "images": [],
            "method": "stl-matplotlib",
        }

    return {
        "success": True,
        "views": captured_views,
        "images": captured_images,
        "image": captured_images[0],
        "primary_view": captured_views[0],
        "method": "stl-matplotlib",
    }


def capture_multiview_for_critique(
    job_id: str,
    doc_name: str,
    *,
    print_dir: Path | None = None,
    mode: str = "auto",
) -> dict[str, Any]:
    """Best-effort multiview capture for the vision loop."""
    mode = (mode or "auto").strip().lower()
    fcstd_result: dict[str, Any] | None = None
    stl_result: dict[str, Any] | None = None

    if mode in ("auto", "subprocess", "fcstd", "coin"):
        fcstd_result = capture_multiview_from_fcstd(job_id, doc_name)
        if fcstd_result.get("success"):
            return fcstd_result
        if mode in ("subprocess", "fcstd", "coin"):
            return fcstd_result

    if mode in ("auto", "stl"):
        from presets import PRINT_DIR

        out_dir = print_dir or PRINT_DIR
        stl_path = out_dir / f"_viewer_{doc_name}.stl"
        stl_result = capture_multiview_from_stl(stl_path)
        if stl_result.get("success"):
            return stl_result
        if mode == "stl":
            return stl_result

    errors = [
        e
        for e in (
            (fcstd_result or {}).get("error"),
            (stl_result or {}).get("error"),
        )
        if e
    ]
    return {
        "success": False,
        "error": "; ".join(errors) if errors else "Vision capture failed",
        "views": [],
        "images": [],
        "method": "none",
    }
