# 3D CAD Skills & Repos for CadForge

Research summary for improving AI → FreeCAD Python generation.

## Recommended skills to adopt

| Repo / skill | URL | Use in CadForge |
|--------------|-----|-------------------|
| **FreeCAD MCP** | https://github.com/neka-nat/freecad-mcp | RPC patterns, `execute_code`, screenshots, object serialization (already integrated) |
| **CadQuery** | https://github.com/CadQuery/cadquery | Alternative parametric API; good LLM examples for boxes, holes, fillets |
| **build123d** | https://github.com/gumyr/build123d | Modern Python CAD; cleaner primitives than raw FreeCAD |
| **PartDesign prompts** | FreeCAD wiki + forum macros | Fillet, pocket, pad patterns for edit-mode prompts |
| **Anthropic frontend-design** | Claude Code skills | UI only — see `UI-SKILLS.md` |

## Spatial understanding (open source)

| Project | Role | Integration status |
|---------|------|-------------------|
| **FreeCAD multiview** | 5-angle renders from live model | **Integrated** (edit pipeline) |
| **Scene JSON** | Volumes, positions, feature dims | **Integrated** |
| **VLM-3R** | Vision-language 3D reasoning | Research — local inference heavy |
| **DUSt3R / CUT3R** | Point clouds from images | Optional future — needs GPU pipeline |
| **Depth Anything V2** | Depth maps from renders | Optional — add as 6th channel to vision prompt |
| **BlenderProc** | Synthetic multiview datasets | Offline training only, not runtime |

## Practical pipeline (current)

```
Edit request
  → multiview PNGs (iso/front/top/right/back)
  → structured JSON scene
  → current Python script
  → user prompt
  → updated Python
```

## Prompt rules to embed in skills

1. Millimeters only; printable sizes (no micron features).
2. One document per job (`PF_xxxxxxxx`).
3. Edits: output **full** script, remove old solids before recreate.
4. End every script with `doc.recompute()` and descriptive `print()`.
5. Name objects clearly (`Body`, `MountHole`, `Deck`).

## Next integrations

1. **CadQuery export path** — generate CQ script, convert to FreeCAD on execute.
2. **Depth map pass** — render depth from FreeCAD view, attach to vision model.
3. **Macro library** — common features (hex nut, bracket, enclosure) as few-shot examples in `llm.py`.