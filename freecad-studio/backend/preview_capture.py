"""Reliable FreeCAD 3D view screenshots for the UI preview."""
from __future__ import annotations

import time

from freecad_client import FreeCADClient
from freecad_window import freecad_visible_for_capture

_SETTLE_SECONDS = 0.5


def prepare_view_code(doc_name: str | None = None) -> str:
    doc_lookup = (
        f'''try:
    doc = App.getDocument("{doc_name}")
except Exception:
    doc = None
if doc is None:
    doc = App.newDocument("{doc_name}")
try:
    gui_doc = Gui.getDocument(doc.Name)
except Exception:
    gui_doc = None
if gui_doc is None:
    Gui.addDocument(doc)
'''
        if doc_name
        else """doc = App.activeDocument()
if doc is None:
    docs = list(App.listDocuments().values())
    if docs:
        doc = docs[-1]"""
    )
    return f"""
import FreeCAD as App
import FreeCADGui as Gui
import time

{doc_lookup}

if doc is None:
    print("No document for preview")
else:
    try:
        doc.recompute()
    except Exception:
        pass

    try:
        gui_doc = Gui.getDocument(doc.Name)
    except Exception:
        gui_doc = None
    if gui_doc is None:
        Gui.addDocument(doc)

    Gui.setActiveDocument(doc.Name)
    Gui.ActiveDocument = Gui.getDocument(doc.Name)

    for wb in ("PartWorkbench", "PartDesignWorkbench", "SketcherWorkbench"):
        try:
            Gui.activateWorkbench(wb)
            break
        except Exception:
            continue

    adoc = Gui.ActiveDocument
    view = adoc.ActiveView if adoc else None
    if view is None and adoc is not None:
        try:
            Gui.activateView("View3DInventor", True)
        except Exception:
            pass
        view = adoc.ActiveView if adoc else None

    if view and hasattr(view, "viewIsometric"):
        view.viewIsometric()
    if view and hasattr(view, "fitAll"):
        view.fitAll()
    elif adoc is not None:
        try:
            Gui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    time.sleep(0.4)
    solids = sum(
        1 for o in doc.Objects
        if getattr(o, "Shape", None) and not o.Shape.isNull()
    )
    print(
        "Preview view ready:",
        doc.Name,
        "solids=" + str(solids),
        "view=" + (type(view).__name__ if view else "none"),
    )
"""


from vision_capture import SPATIAL_VIEWS

DEFAULT_VIEWS = ("Isometric",)


def _prepare_view(fc: FreeCADClient, doc_name: str | None) -> str | None:
    result = fc.execute_code(prepare_view_code(doc_name))
    if not result.get("success"):
        return result.get("error") or result.get("message") or "Could not prepare FreeCAD view"
    time.sleep(_SETTLE_SECONDS)
    return None


def _capture_shot(
    fc: FreeCADClient,
    views: tuple[str, ...],
    *,
    doc_name: str | None,
    prepare: bool,
) -> dict:
    if prepare:
        prep_err = _prepare_view(fc, doc_name)
        if prep_err:
            return {"success": False, "error": prep_err}

    last_error = "Screenshot failed — ensure FreeCAD 3D view is available"
    for view in views:
        shot = fc.get_active_screenshot(view)
        if shot.get("success") and shot.get("image"):
            img = shot["image"].strip()
            if len(img) > 100:
                return shot
            last_error = "FreeCAD returned an empty screenshot"
        else:
            last_error = shot.get("error") or last_error
    return {"success": False, "error": last_error}


def capture_multiview_images(
    fc: FreeCADClient,
    views: tuple[str, ...] = SPATIAL_VIEWS,
    *,
    prepare: bool = True,
    doc_name: str | None = None,
    restore_after: bool = False,
) -> dict:
    with freecad_visible_for_capture(restore_after=restore_after):
        captured: list[dict[str, str]] = []
        last_error = "Screenshot failed"

        for view in views:
            if prepare and view == views[0]:
                prep_err = _prepare_view(fc, doc_name)
                if prep_err:
                    return {"success": False, "error": prep_err, "views": [], "images": []}
            elif prepare:
                time.sleep(0.2)

            shot_view = view
            if view.startswith("Section"):
                shot_view = {"SectionFront": "Front", "SectionTop": "Top", "SectionRight": "Right"}.get(
                    view, view
                )
            shot = fc.get_active_screenshot(shot_view)
            if shot.get("success") and shot.get("image") and len(shot["image"].strip()) > 100:
                captured.append({"view": view, "image": shot["image"]})
            else:
                last_error = shot.get("error") or last_error

        if not captured:
            return {"success": False, "error": last_error, "views": [], "images": []}

        return {
            "success": True,
            "views": [c["view"] for c in captured],
            "images": [c["image"] for c in captured],
            "image": captured[0]["image"],
            "primary_view": captured[0]["view"],
        }


def capture_preview_image(
    fc: FreeCADClient,
    view_name: str | None = None,
    *,
    prepare: bool = True,
    doc_name: str | None = None,
    restore_after: bool = False,
) -> dict:
    """Return {success, image?, error?} with base64 PNG payload."""
    views = (view_name,) if view_name else DEFAULT_VIEWS

    with freecad_visible_for_capture(restore_after=restore_after):
        shot = _capture_shot(fc, views, doc_name=doc_name, prepare=prepare)
        if shot.get("success"):
            return shot

        shot = _capture_shot(fc, views, doc_name=doc_name, prepare=True)
        if shot.get("success"):
            return shot

        return {
            "success": False,
            "error": (
                f"{shot.get('error', 'Screenshot failed')}. "
                "Click Show FreeCAD, confirm the 3D view is visible, then Refresh."
            ),
        }