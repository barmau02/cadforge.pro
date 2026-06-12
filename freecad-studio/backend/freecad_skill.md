# FreeCAD Modeling Skill

## Workflow — ALWAYS follow this order
1. Start with a comment block: list every feature the user asked for and its dimensions.
   Example: `# Features: base plate 80x60x5, 4x M4 holes at corners (inset 8), center boss d20 h10`
2. Define ALL dimensions as named variables at the top (parametric). Never hardcode numbers inline.
3. Build geometry feature by feature. After each boolean, reassign the result to one running solid.
4. Verify your own work in code: count the features you created vs. the comment block from step 1.
5. End with `doc.recompute()` and a `print()` listing every feature with its dimensions.

## Geometry quality rules
- Build ONE final fused solid per part (printable). Multiple separate solids only if the user asks for an assembly.
- Booleans: prefer `shape_a.cut(shape_b)`, `shape_a.fuse(shape_b)`, `shape_a.common(shape_b)` on `Part.Shape`
  objects, then add ONE result: `obj = doc.addObject("Part::Feature", "PartName"); obj.Shape = final_shape`.
  This is more reliable than `Part::Cut`/`Part::Fuse` document objects and leaves a clean tree.
- After fusing coplanar pieces call `final_shape = final_shape.removeSplitter()` to clean faces.
- Fillets/chamfers: `shape = shape.makeFillet(radius, edges)` on the **final fused solid** (after all booleans).
  Select edges by **vertex position + tangent**, not by index:
  ```python
  bb = solid.BoundBox
  def edges_near(solid, *, z=None, y=None, x=None, tol=0.6):
      out = []
      for e in solid.Edges:
          for v in e.Vertexes:
              p = v.Point
              if z is not None and abs(p.z - z) > tol: continue
              if y is not None and abs(p.y - y) > tol: continue
              if x is not None and abs(p.x - x) > tol: continue
              out.append(e)
              break
      return out
  # Top-front outer corner of an L-bracket arm (high Z, front Y):
  top_front = edges_near(solid, z=bb.ZMax, y=bb.YMin)
  # Inner L-corner (where arm meets base — vertical edge at inner junction):
  inner_corner = [e for e in solid.Edges
      if abs(e.tangentAt(e.FirstParameter).z) > 0.9
      and any(abs(v.Point.z - BASE_H) < 1 for v in e.Vertexes)]
  ```
  If `makeFillet` fails, retry at **half radius** — never silently skip a user-requested fillet.
  Print `FILLET upper: ok` or `FILLET upper: FAILED` for each fillet so inspection can verify.
  Optional cosmetic fillets may use try/except; **required** fillets (listed in # Features) must not.
- Position with `Part.makeBox(l, w, h, App.Vector(x, y, z))` style base points or `shape.translate(App.Vector(...))`.
  Think about where the origin is: makeBox grows +X+Y+Z from its base point; makeCylinder grows +Z from center of base circle.
- Holes must fully pierce: make the cutting cylinder LONGER than the wall (start 1 mm below, end 1 mm above).
- Curved/organic shapes: use `Part.makeLoft` over wire profiles, `Part.makeRevolution`, or `extrude` of arcs —
  not hundreds of tiny boxes.
- Check validity before finishing: `assert final_shape.isValid()` and `assert final_shape.Volume > 0`.

## 3D-printability rules (apply when the part will be printed)
- Minimum wall thickness 1.6 mm; minimum feature size 1 mm; minimum hole diameter 2 mm.
- Give the part one large flat face to sit on the print bed (orient it bottom = z=0).
- Avoid unsupported horizontal spans > 30 mm and floating geometry.
- Holes for screws: M3 -> 3.4 mm, M4 -> 4.5 mm, M5 -> 5.5 mm clearance diameter.
- Overall size sanity: a handheld object is 30-200 mm. Never produce micron or kilometer scale.

## Rotation and placement — get this RIGHT
- Coordinate convention: X = width (left-right), Y = depth (front = low Y, back = high Y), Z = up.
  The print bed is the z=0 plane. "Front lip" = at low Y; "back support" = at high Y.
- `shape.rotate(center_point, axis, angle_degrees)` rotates IN PLACE about `center_point`.
  To lean a back panel backwards: build it vertical at its final XY location, then rotate about its own
  BOTTOM BACK edge with axis App.Vector(1, 0, 0) and a NEGATIVE angle (right-hand rule: positive X-axis
  rotation tips +Z toward +Y; check which direction you need and say so in a comment).
- After EVERY rotate/translate, re-anchor to the bed and verify overlap:
  `bb = part.BoundBox` — if `bb.ZMin < 0`, translate up by `-bb.ZMin`.
  Before fusing, require real overlap: `assert part.common(body).Volume > 0.01, "part does not touch body"`.
- After all booleans the result must be ONE connected solid: `assert len(solid.Solids) == 1`.
  A pile of disconnected pieces is a failed model.
- Mentally trace one vertex through every transform before writing it. State the expected final
  bounding box in a comment and assert it roughly: e.g. `assert abs(solid.BoundBox.ZLength - 45) < 5`.

## Common failures to avoid
- `App.ActiveDocument` may be None — always `doc = App.getDocument(NAME) or App.newDocument(NAME)` pattern.
- Names with spaces/special chars break `addObject` — use CamelCase ASCII names.
- `doc.removeObject` while iterating `doc.Objects` directly — iterate over `list(doc.Objects)`.
- Forgetting `doc.recompute()` — nothing shows up.
- Boolean on touching-but-not-overlapping solids can produce invalid shapes — overlap cutting tools by >= 0.5 mm.
- Do NOT import PartDesign / Sketcher for simple solids — raw `Part` API is more robust headless.

## Reference example — quality bar
```python
import FreeCAD as App
import Part

# Features: base 80x60x6, 4x M4 clearance holes inset 8 from corners,
#           center boss d24 h14 with d12 through-hole, vertical edges filleted r3
DOC = "PF_example"
doc = App.getDocument(DOC) if DOC in App.listDocuments() else App.newDocument(DOC)

L, W, T = 80.0, 60.0, 6.0          # base plate
HOLE_D, INSET = 4.5, 8.0           # M4 clearance
BOSS_D, BOSS_H, BORE_D = 24.0, 14.0, 12.0

base = Part.makeBox(L, W, T)

# fillet vertical edges before boolean ops (simpler edge selection)
vert = [e for e in base.Edges if abs(e.tangentAt(e.FirstParameter).z) > 0.99]
try:
    base = base.makeFillet(3.0, vert)
except Exception:
    pass  # keep going without fillet

boss = Part.makeCylinder(BOSS_D / 2, BOSS_H, App.Vector(L / 2, W / 2, T))
solid = base.fuse(boss).removeSplitter()

# through-holes: start 1mm below, extend 1mm past the top
for x, y in [(INSET, INSET), (L - INSET, INSET), (INSET, W - INSET), (L - INSET, W - INSET)]:
    cutter = Part.makeCylinder(HOLE_D / 2, T + 2, App.Vector(x, y, -1))
    solid = solid.cut(cutter)
bore = Part.makeCylinder(BORE_D / 2, T + BOSS_H + 2, App.Vector(L / 2, W / 2, -1))
solid = solid.cut(bore)

assert solid.isValid() and solid.Volume > 0
obj = doc.addObject("Part::Feature", "MountingPlate")
obj.Shape = solid
doc.recompute()
print(f"MountingPlate: base {L}x{W}x{T}mm, 4x M4 holes (d{HOLE_D}, inset {INSET}), "
      f"boss d{BOSS_D}xh{BOSS_H} with d{BORE_D} bore, r3 edge fillets")
```
