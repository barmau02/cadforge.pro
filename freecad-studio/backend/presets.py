from __future__ import annotations

from pathlib import Path

HOME = Path.home()
BOAT_FCSTD = HOME / "boat.FCStd"
PRINT_DIR = HOME / "boat_print"

BOAT_CODE = r'''
import FreeCAD as App
import FreeCADGui as Gui
import Part

LENGTH = 480.0
BEAM = 140.0
DRAFT = 55.0
FREEBOARD = 35.0
DECK_INSET = 18.0
DECK_THICKNESS = 6.0
CABIN_LENGTH = 130.0
CABIN_WIDTH = 90.0
CABIN_HEIGHT = 55.0
CABIN_OFFSET_X = 95.0
WINDSHIELD_HEIGHT = 32.0
WINDSHIELD_THICKNESS = 4.0
RUDDER_HEIGHT = 70.0
RUDDER_WIDTH = 8.0
RUDDER_DEPTH = 28.0


def hull_section(x, length, beam, draft, freeboard):
    t = x / length
    beam_scale = 0.08 + 1.84 * t if t <= 0.5 else 1.0 - 0.35 * ((t - 0.5) / 0.5)
    half_beam = (beam * beam_scale) / 2.0
    chine_z = draft * 0.30
    bilge_z = draft * 0.78
    gunwale_z = draft + freeboard * 0.15
    depth_scale = 0.85 + 0.15 * (1.0 - abs(2.0 * t - 1.0))
    points = [
        App.Vector(x, 0, 0),
        App.Vector(x, -half_beam * 0.82, chine_z * depth_scale),
        App.Vector(x, -half_beam * 0.96, bilge_z * depth_scale),
        App.Vector(x, -half_beam, gunwale_z),
        App.Vector(x, -half_beam * 0.55, (draft + freeboard) * depth_scale),
        App.Vector(x, 0, (draft + freeboard * 0.92) * depth_scale),
        App.Vector(x, half_beam * 0.55, (draft + freeboard) * depth_scale),
        App.Vector(x, half_beam, gunwale_z),
        App.Vector(x, half_beam * 0.96, bilge_z * depth_scale),
        App.Vector(x, half_beam * 0.82, chine_z * depth_scale),
        App.Vector(x, 0, 0),
    ]
    return Part.Wire(Part.makePolygon(points))


def add_shape(doc, name, shape, color):
    obj = doc.addObject("Part::Feature", name)
    obj.Shape = shape
    if obj.ViewObject:
        obj.ViewObject.ShapeColor = color
    return obj


if "Boat" in App.listDocuments():
    App.closeDocument("Boat")

doc = App.newDocument("Boat")
deck_z = DRAFT + FREEBOARD * 0.92 + DECK_THICKNESS

wires = [hull_section((LENGTH * i) / 13.0, LENGTH, BEAM, DRAFT, FREEBOARD) for i in range(14)]
add_shape(doc, "Hull", Part.makeLoft(wires, True, False), (0.10, 0.45, 0.80))

deck_length = LENGTH - DECK_INSET
deck_width = BEAM - DECK_INSET * 1.4
z = DRAFT + FREEBOARD * 0.92
add_shape(doc, "Deck", Part.makeBox(deck_length, deck_width, DECK_THICKNESS, App.Vector(DECK_INSET * 0.55, -deck_width / 2.0, z)), (0.75, 0.75, 0.75))

cabin = Part.makeBox(CABIN_LENGTH, CABIN_WIDTH, CABIN_HEIGHT, App.Vector(CABIN_OFFSET_X, -CABIN_WIDTH / 2.0, deck_z))
front_round = Part.makeSphere(CABIN_WIDTH * 0.45)
front_round.translate(App.Vector(CABIN_OFFSET_X + CABIN_LENGTH - CABIN_WIDTH * 0.15, 0, deck_z + CABIN_HEIGHT * 0.45))
cabin = cabin.fuse(front_round).cut(Part.makeBox(CABIN_LENGTH - 10, CABIN_WIDTH - 10, CABIN_HEIGHT - 5, App.Vector(CABIN_OFFSET_X + 5, -(CABIN_WIDTH - 10) / 2.0, deck_z + 5)))
add_shape(doc, "Cabin", cabin, (0.90, 0.90, 0.95))

x = CABIN_OFFSET_X + CABIN_LENGTH - 8
face = Part.Face(Part.makePolygon([
    App.Vector(x, -CABIN_WIDTH / 2.0 + 8, deck_z + CABIN_HEIGHT - 6),
    App.Vector(x + WINDSHIELD_THICKNESS, -CABIN_WIDTH / 2.0 + 8, deck_z + CABIN_HEIGHT + WINDSHIELD_HEIGHT - 6),
    App.Vector(x + WINDSHIELD_THICKNESS, CABIN_WIDTH / 2.0 - 8, deck_z + CABIN_HEIGHT + WINDSHIELD_HEIGHT - 6),
    App.Vector(x, CABIN_WIDTH / 2.0 - 8, deck_z + CABIN_HEIGHT - 6),
    App.Vector(x, -CABIN_WIDTH / 2.0 + 8, deck_z + CABIN_HEIGHT - 6),
]))
add_shape(doc, "Windshield", face.extrude(App.Vector(6, 0, 0)), (0.55, 0.80, 0.95))

rx = LENGTH - 6
rz = DRAFT * 0.35
blade = Part.makeBox(RUDDER_WIDTH, RUDDER_DEPTH, RUDDER_HEIGHT, App.Vector(rx, -RUDDER_DEPTH / 2.0, rz))
cutter = Part.makeBox(RUDDER_WIDTH + 2, RUDDER_DEPTH + 2, RUDDER_HEIGHT * 0.45, App.Vector(rx - 1, -RUDDER_DEPTH / 2.0 - 1, rz + RUDDER_HEIGHT * 0.55))
cutter.rotate(App.Vector(rx + RUDDER_WIDTH / 2.0, 0, rz + RUDDER_HEIGHT), App.Vector(0, 1, 0), 18)
add_shape(doc, "Rudder", blade.cut(cutter), (0.20, 0.20, 0.20))

mx = LENGTH - 22
mz = DRAFT + FREEBOARD * 0.25
motor = Part.makeBox(18, 28, 42, App.Vector(mx, -14, mz)).fuse(Part.makeCylinder(10, 14, App.Vector(mx + 9, 0, mz + 42), App.Vector(0, 1, 0)))
add_shape(doc, "Motor", motor, (0.15, 0.15, 0.15))

doc.recompute()
doc.saveAs(r"__BOAT_FCSTD__")
Gui.activeDocument().activeView().viewIsometric()
Gui.SendMsgToActiveView("ViewFit")
print("Boat built:", [o.Name for o in doc.Objects])
'''


def boat_code(fcstd_path: Path) -> str:
    return BOAT_CODE.replace("__BOAT_FCSTD__", str(fcstd_path).replace("\\", "\\\\"))


def export_stl_code(doc_name: str, output_dir: Path, target_length_mm: float = 200.0) -> str:
    out = str(output_dir).replace("\\", "\\\\")
    return f'''
import os
import FreeCAD as App
import Mesh

DOC = "{doc_name}"
OUT = r"{out}"
TARGET = {target_length_mm}
BOAT_LENGTH = 480.0
SCALE = TARGET / BOAT_LENGTH
PARTS = ["Hull", "Deck", "Cabin", "Windshield", "Rudder", "Motor"]

os.makedirs(OUT, exist_ok=True)
doc = App.getDocument(DOC)
if doc is None:
    raise RuntimeError("Document not found: " + DOC)

exported = []
for name in PARTS:
    obj = doc.getObject(name)
    if obj is None:
        continue
    shape = obj.Shape.copy()
    if SCALE != 1.0:
        shape.scale(SCALE)
    mesh = Mesh.Mesh()
    mesh.addFacets(shape.tessellate(0.1))
    path = os.path.join(OUT, name + ".stl")
    mesh.write(path)
    exported.append(path)
    print("Exported", path)

print("Scale:", SCALE)
print("Files:", exported)
'''