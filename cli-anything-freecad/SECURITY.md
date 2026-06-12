# Security — PromptForge vendored cli-anything-freecad

This directory is a **sanitized private copy** of
[HKUDS/CLI-Anything `freecad/agent-harness`](https://github.com/HKUDS/CLI-Anything)
(Apache-2.0). Upstream is designed for full agent access; this fork adds guardrails.

## Use the secure entry point only

```powershell
pip install -e c:\Users\mauri\forgeprompt\cli-anything-freecad
pf-freecad-cli --json document new -o c:\Users\mauri\forgeprompt\batch\test.json
```

Do **not** call `cli-anything-freecad` directly unless you disable checks (`PF_SECURE_CLI=0`).

## Defaults (override with environment variables)

| Variable | Default | Purpose |
|----------|---------|---------|
| `PF_SECURE_CLI` | `1` | Enable argv/path checks |
| `PF_CLI_ROOT` | `forgeprompt/batch` | All writes (exports, project JSON) |
| `PF_IMPORT_ROOT` | `forgeprompt/batch/imports` | STEP/STL you import |
| `PF_PREVIEW_ROOT` | `forgeprompt/batch/previews` | Preview bundles |
| `PF_FREECAD_CMD` | `C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe` | Pinned headless binary |
| `PF_CLI_ALLOWED_GROUPS` | `document,part,measure,export,import,session,preview` | Command whitelist |
| `PF_ALLOW_REPL` | off | Block bare REPL (no subcommand) |
| `PF_MAX_TIMEOUT` | `180` | Macro timeout hint |

## What is blocked

- Writes outside allowlisted directories
- Reads for project/import outside allowlisted directories (+ jobs, boat_print read-only)
- Interactive REPL without `PF_ALLOW_REPL=1`
- Command groups not in whitelist (e.g. `cam`, `fem`, `techdraw` by default)
- Running arbitrary `freecad.exe` from PATH when `PF_FREECAD_CMD` is set

## What is NOT sandboxed

- Generated FreeCAD Python macros still run with **your user privileges** inside `FreeCADCmd` — same risk class as PromptForge `execute_code`.
- Untrusted STEP files can still contain malicious geometry; only import from `PF_IMPORT_ROOT`.

## Disabling checks (debug only)

```powershell
$env:PF_SECURE_CLI = "0"
cli-anything-freecad --help
```

## Updating upstream

Re-download `freecad/agent-harness` from GitHub, re-apply patches to:

- `cli_anything/freecad/security.py`
- `cli_anything/freecad/utils/freecad_backend.py` (marked `# PF-SEC`)
- `setup.py` entry point `pf-freecad-cli`

See `UPSTREAM.md`.
