#!/usr/bin/env python3
"""
Writes the language-neutral artifacts under `shared/` that the ports consume -
see hoermoles_ble.interop for what they contain and why they exist.

    cd python && uv run python scripts/generate_shared.py

Run this after changing protocol.py or menu_settings.py. `test_interop.py`
fails if the files on disk no longer match what this script would write, so
forgetting is a red CI run rather than a silently stale port.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hoermoles_ble.interop import build_menu_tables, build_test_vectors

SHARED_DIR = Path(__file__).resolve().parents[2] / "shared"

ARTIFACTS = {
    "test-vectors.json": build_test_vectors,
    "menu-tables.json": build_menu_tables,
}


def render(builder) -> str:
    """ensure_ascii=False keeps the German menu texts readable in the file and
    in diffs; the trailing newline keeps pre-commit's end-of-file-fixer happy."""
    return json.dumps(builder(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    SHARED_DIR.mkdir(parents=True, exist_ok=True)
    for filename, builder in ARTIFACTS.items():
        target = SHARED_DIR / filename
        target.write_text(render(builder), encoding="utf-8")
        print(f"wrote {target} ({target.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
