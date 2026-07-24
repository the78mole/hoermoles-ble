"""
Guards the generated `shared/` artifacts (see hoermoles_ble.interop).

The point is not to test JSON serialization - it is that the TypeScript port
runs its own suite against `shared/test-vectors.json`. If protocol.py changes
and nobody regenerates, the port keeps passing against stale expectations and
the two implementations drift apart unnoticed. Here that becomes a failing
test with an explicit "run this command" message instead.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from hoermoles_ble.interop import build_device_log, build_menu_tables, build_test_vectors

SHARED_DIR = Path(__file__).resolve().parents[3].parent / "shared"
REGENERATE_HINT = "cd python && uv run python scripts/generate_shared.py"


def _load(filename: str) -> dict:
    path = SHARED_DIR / filename
    if not path.exists():
        pytest.fail(f"{path} is missing - generate it with: {REGENERATE_HINT}")
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    "filename, builder",
    [
        ("test-vectors.json", build_test_vectors),
        ("menu-tables.json", build_menu_tables),
        ("device-log.json", build_device_log),
    ],
)
def test_shared_artifact_is_up_to_date(filename, builder):
    assert _load(filename) == builder(), (
        f"shared/{filename} is out of date with the Python implementation. Regenerate it: {REGENERATE_HINT}"
    )


def test_test_vectors_cover_every_frame_builder():
    """A new build_*_frame function without a vector means the port can add an
    untested equivalent - so require the coverage explicitly."""
    from hoermoles_ble import protocol

    builders = {name for name in dir(protocol) if name.startswith("build_") and name.endswith("_frame")}
    covered = {vector["function"] for vector in build_test_vectors()["frames"]}
    assert builders <= covered, f"No shared test vector for: {sorted(builders - covered)}"


def test_menu_tables_carry_every_product():
    from hoermoles_ble.menu_settings import DRIVE_MENU_TABLES

    tables = build_menu_tables()["tables"]
    assert len(tables) == len(DRIVE_MENU_TABLES)
    assert {(t["product_class"], t["product_id"]) for t in tables} == {
        (t.product_class, t.product_id) for t in DRIVE_MENU_TABLES
    }


def test_menu_tables_are_internally_consistent():
    """Wire bytes must be unique per product - the web app looks settings up by
    menu_group, and a duplicate would silently shadow one of them."""
    for table in build_menu_tables()["tables"]:
        groups = [setting["menu_group"] for setting in table["settings"]]
        numbers = [setting["menu_number"] for setting in table["settings"]]
        label = f"{table['product_name']} (class={table['product_class']}, id={table['product_id']})"
        assert len(groups) == len(set(groups)), f"duplicate menu_group in {label}"
        assert len(numbers) == len(set(numbers)), f"duplicate menu_number in {label}"
