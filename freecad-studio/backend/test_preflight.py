"""Unit tests for soft vs hard preflight checks (no printer required)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from creality_preflight import _catalog_entry_for_name, _catalog_issues, _catalog_lookup_names, _snapshot_issues


class PreflightSoftChecksTest(unittest.TestCase):
    def test_material_status_zero_is_warning_not_blocker(self) -> None:
        blockers, warnings = _snapshot_issues({"materialStatus": 0, "cfsConnect": 0})
        self.assertEqual(blockers, [])
        self.assertTrue(any("Filament" in w or "filament" in w for w in warnings))

    def test_cfs_without_material_is_warning(self) -> None:
        blockers, warnings = _snapshot_issues({"materialStatus": 0, "cfsConnect": 1})
        self.assertEqual(blockers, [])
        self.assertTrue(any("CFS" in w for w in warnings))

    def test_idle_total_layer_zero_is_warning(self) -> None:
        blockers, warnings = _snapshot_issues(
            {"printFileName": "CubeBody.gcode.3mf", "TotalLayer": 0}
        )
        self.assertEqual(blockers, [])
        self.assertTrue(any("0 layers" in w for w in warnings))

    def test_missing_catalog_entry_is_warning(self) -> None:
        blockers, warnings = _catalog_issues(None, "CubeBody.gcode.3mf")
        self.assertEqual(blockers, [])
        self.assertTrue(any("not indexed" in w for w in warnings))

    def test_zero_model_size_is_warning(self) -> None:
        blockers, warnings = _catalog_issues(
            {"name": "CubeBody.gcode.3mf", "modelX": 0, "modelY": 0, "modelZ": 0},
            "CubeBody.gcode.3mf",
        )
        self.assertEqual(blockers, [])
        self.assertTrue(any("zero model size" in w.lower() for w in warnings))

    def test_catalog_lookup_resolves_k2_renamed_plate(self) -> None:
        entries = [{"name": "CubeBody.gcode_plate_1.gcode", "modelX": 1000, "timeCost": 586}]
        hit = _catalog_entry_for_name(entries, "CubeBody.gcode.3mf")
        self.assertIsNotNone(hit)
        self.assertEqual(hit["timeCost"], 586)

    def test_catalog_lookup_names(self) -> None:
        self.assertIn(
            "model.gcode_plate_1.gcode",
            _catalog_lookup_names("model.gcode.3mf"),
        )


if __name__ == "__main__":
    unittest.main()
