#!/usr/bin/env python3
"""
PromptForge secure entry point for cli-anything-freecad.

Always runs argv and path checks before delegating to the upstream CLI.
Install: pip install -e .  then use: pf-freecad-cli --json ...
"""
from __future__ import annotations

import sys

from cli_anything.freecad.security import audit_enabled, validate_argv_or_exit


def main() -> None:
    if audit_enabled():
        validate_argv_or_exit(sys.argv[1:])
    from cli_anything.freecad.freecad_cli import main as upstream_main

    upstream_main()


if __name__ == "__main__":
    main()
