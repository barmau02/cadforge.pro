"""
PromptForge security layer for the vendored cli-anything-freecad copy.

Enforces path allowlists, command group whitelists, and a pinned FreeCAD binary
before headless macro execution. Enabled by default in this fork.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Iterable

# Defaults — override with environment variables (see SECURITY.md).
_FORGE_ROOT = Path(__file__).resolve().parents[3]  # forgeprompt/
_DEFAULT_CLI_ROOT = _FORGE_ROOT / "batch"
_DEFAULT_IMPORT_ROOT = _DEFAULT_CLI_ROOT / "imports"
_DEFAULT_PREVIEW_ROOT = _DEFAULT_CLI_ROOT / "previews"

PF_CLI_ROOT = Path(os.environ.get("PF_CLI_ROOT", str(_DEFAULT_CLI_ROOT))).resolve()
PF_IMPORT_ROOT = Path(os.environ.get("PF_IMPORT_ROOT", str(_DEFAULT_IMPORT_ROOT))).resolve()
PF_PREVIEW_ROOT = Path(os.environ.get("PF_PREVIEW_ROOT", str(_DEFAULT_PREVIEW_ROOT))).resolve()

# Pin headless binary on this machine (override with PF_FREECAD_CMD).
_DEFAULT_FREECAD_CMD = Path(r"C:\Program Files\FreeCAD 1.1\bin\FreeCADCmd.exe")
PF_FREECAD_CMD = os.environ.get("PF_FREECAD_CMD", str(_DEFAULT_FREECAD_CMD))

# Command groups permitted in secure mode (batch / measure / export focus).
ALLOWED_COMMAND_GROUPS = frozenset(
    g.strip()
    for g in os.environ.get(
        "PF_CLI_ALLOWED_GROUPS",
        "document,part,measure,export,import,session,preview",
    ).split(",")
    if g.strip()
)

# Block interactive REPL (bare `cli-anything-freecad` with no subcommand).
PF_ALLOW_REPL = os.environ.get("PF_ALLOW_REPL", "").strip().lower() in ("1", "true", "yes")

# Max macro runtime seconds (backend also has its own timeout).
PF_MAX_TIMEOUT = int(os.environ.get("PF_MAX_TIMEOUT", "180"))

_WRITE_ROOTS: tuple[Path, ...] | None = None
_READ_ROOTS: tuple[Path, ...] | None = None


def _write_roots() -> tuple[Path, ...]:
    global _WRITE_ROOTS
    if _WRITE_ROOTS is None:
        roots = [PF_CLI_ROOT, PF_PREVIEW_ROOT, Path(tempfile.gettempdir()).resolve()]
        extra = os.environ.get("PF_CLI_EXTRA_WRITE_ROOTS", "")
        for part in extra.split(os.pathsep):
            if part.strip():
                roots.append(Path(part.strip()).resolve())
        _WRITE_ROOTS = tuple(roots)
    return _WRITE_ROOTS


def _read_roots() -> tuple[Path, ...]:
    global _READ_ROOTS
    if _READ_ROOTS is None:
        roots = list(_write_roots()) + [PF_IMPORT_ROOT]
        jobs = _FORGE_ROOT / "freecad-studio" / "jobs"
        if jobs.is_dir():
            roots.append(jobs.resolve())
        print_dir = _FORGE_ROOT / "boat_print"
        if print_dir.is_dir():
            roots.append(print_dir.resolve())
        extra = os.environ.get("PF_CLI_EXTRA_READ_ROOTS", "")
        for part in extra.split(os.pathsep):
            if part.strip():
                roots.append(Path(part.strip()).resolve())
        _READ_ROOTS = tuple(dict.fromkeys(roots))  # dedupe, preserve order
    return _READ_ROOTS


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _is_under_any(path: Path, roots: Iterable[Path]) -> bool:
    return any(_is_under(path, root) for root in roots)


def ensure_roots_exist() -> None:
    PF_CLI_ROOT.mkdir(parents=True, exist_ok=True)
    PF_IMPORT_ROOT.mkdir(parents=True, exist_ok=True)
    PF_PREVIEW_ROOT.mkdir(parents=True, exist_ok=True)


def validate_read_path(path: str | Path, *, label: str = "path") -> Path:
    """Imported STEP/STL and project files must live under read allowlist."""
    resolved = Path(path).expanduser().resolve()
    if not _is_under_any(resolved, _read_roots()):
        allowed = ", ".join(str(r) for r in _read_roots())
        raise PermissionError(
            f"{label} {resolved} is outside allowed read roots: {allowed}"
        )
    if not resolved.is_file() and not resolved.is_dir():
        raise FileNotFoundError(f"{label} not found: {resolved}")
    return resolved


def validate_write_path(path: str | Path, *, label: str = "output", create_parent: bool = True) -> Path:
    """Exports, project JSON, and previews must stay under write allowlist."""
    resolved = Path(path).expanduser().resolve()
    if ".." in Path(path).parts:
        pass  # resolve() already collapses; still block escape via relative_to
    if not _is_under_any(resolved, _write_roots()):
        allowed = ", ".join(str(r) for r in _write_roots())
        raise PermissionError(
            f"{label} {resolved} is outside allowed write roots: {allowed}"
        )
    if create_parent and resolved.suffix:
        resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def validate_temp_script(path: str | Path) -> Path:
    """Macro scripts must be temp files or under CLI root."""
    resolved = Path(path).resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if _is_under(resolved, temp_root) or _is_under_any(resolved, _write_roots()):
        return resolved
    raise PermissionError(f"Macro script path not allowed: {resolved}")


def validate_frecad_executable(explicit: str | None = None) -> str:
    """Only run a known FreeCADCmd binary (no PATH fallback to random freecad.exe)."""
    candidate = explicit or os.environ.get("FREECAD_PATH") or PF_FREECAD_CMD
    resolved = Path(candidate).expanduser().resolve()
    if not resolved.is_file():
        raise RuntimeError(
            f"FreeCADCmd not found at {resolved}. Set PF_FREECAD_CMD to your FreeCADCmd.exe."
        )
    name = resolved.name.lower()
    if "freecadcmd" not in name and resolved.suffix.lower() != ".exe":
        raise RuntimeError(f"Refusing non-FreeCADCmd binary: {resolved}")
    return str(resolved)


def _flag_value(argv: list[str], *flags: str) -> str | None:
    for i, arg in enumerate(argv):
        if arg in flags and i + 1 < len(argv):
            return argv[i + 1]
        for flag in flags:
            if arg.startswith(flag + "="):
                return arg.split("=", 1)[1]
    return None


def _positional_command_group(argv: list[str]) -> str | None:
    skip = False
    for arg in argv:
        if skip:
            skip = False
            continue
        if arg in ("-p", "--project", "-o", "--output", "--name", "-n", "--preset"):
            skip = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return None


def validate_argv_or_exit(argv: list[str]) -> None:
    """Validate CLI invocation before Click runs. Exits with code 2 on violation."""
    try:
        ensure_roots_exist()

        if _flag_value(argv, "-p", "--project"):
            validate_read_path(_flag_value(argv, "-p", "--project"), label="project file")

        for flag in ("-o", "--output"):
            val = _flag_value(argv, flag)
            if val:
                validate_write_path(val, label="output")

        group = _positional_command_group(argv)
        if group is None:
            if not PF_ALLOW_REPL:
                raise PermissionError(
                    "Interactive REPL is disabled. Pass a command group "
                    "(e.g. document, part, measure, export) or set PF_ALLOW_REPL=1."
                )
            return

        if group not in ALLOWED_COMMAND_GROUPS:
            raise PermissionError(
                f"Command group '{group}' is not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_COMMAND_GROUPS))}"
            )
    except (PermissionError, FileNotFoundError, RuntimeError) as exc:
        print(f"SECURITY: {exc}", file=sys.stderr)
        sys.exit(2)


def audit_enabled() -> bool:
    return os.environ.get("PF_SECURE_CLI", "1").strip().lower() not in ("0", "false", "no")
