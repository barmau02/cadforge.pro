# PromptForge — sanitized cli-anything-freecad

Headless FreeCAD batch CLI with security checks. Sidecar to PromptForge (does not replace MCP or the desktop app).

## Install

```powershell
cd c:\Users\mauri\forgeprompt\cli-anything-freecad
python -m pip install -e .
```

Requires: Python 3.10+, FreeCAD 1.1 `FreeCADCmd.exe`.

## Quick start

```powershell
$env:PF_FREECAD_CMD = "C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe"

# New project
pf-freecad-cli --json document new --name BatchTest -o c:\Users\mauri\forgeprompt\batch\test.json

# Add box
pf-freecad-cli --json -p c:\Users\mauri\forgeprompt\batch\test.json part add box -P length=80 -P width=60 -P height=5

# Measure
pf-freecad-cli --json -p c:\Users\mauri\forgeprompt\batch\test.json measure bounding-box 0

# Export STL
pf-freecad-cli --json -p c:\Users\mauri\forgeprompt\batch\test.json export render c:\Users\mauri\forgeprompt\batch\test.stl --preset stl --overwrite
```

Put files to import under `forgeprompt/batch/imports/`.

## Security

Read `SECURITY.md`. Use **`pf-freecad-cli`**, not the upstream command name, in scripts and agent prompts.
