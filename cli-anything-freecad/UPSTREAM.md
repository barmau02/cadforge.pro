# Upstream provenance

- **Project:** [HKUDS/CLI-Anything](https://github.com/HKUDS/CLI-Anything)
- **Path:** `freecad/agent-harness`
- **License:** Apache-2.0
- **Vendored:** 2026-06-10 (main branch, 36 files)

## CadForge changes

1. `cli_anything/freecad/security.py` — path/command allowlists
2. `cli_anything/freecad/utils/freecad_backend.py` — `# PF-SEC` hooks
3. `pf_freecad_cli.py` — secure entry point
4. `SECURITY.md`, `README-PROMPTFORGE.md`

## Refresh upstream files

```powershell
# From forgeprompt — re-fetch blobs listed in GitHub tree freecad/agent-harness/
# Then re-merge security.py and PF-SEC sections in freecad_backend.py
```
