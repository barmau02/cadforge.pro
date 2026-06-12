"""Unit tests for job output directory cleanup helpers."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import jobs as job_store


class ClearJobSliceDirTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.job_id = "test-job-abc"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _job_dir(self) -> Path:
        d = job_store.job_stl_dir(self.root, self.job_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def test_clear_job_slice_dir_removes_all_artifacts(self) -> None:
        job_dir = self._job_dir()
        for name in (
            "CubeBody.stl",
            "old.stl",
            "CubeBody.gcode.3mf",
            "stale.gcode",
            "bundle.3mf",
            "_viewer_preview.gcode.3mf",
            "_viewer_mesh.stl",
            "partial.tmp",
        ):
            (job_dir / name).write_text("x", encoding="utf-8")
        (job_dir / "README").write_text("notes", encoding="utf-8")

        job_store.clear_job_slice_dir(self.root, self.job_id)

        remaining = sorted(p.name for p in job_dir.iterdir())
        self.assertEqual(remaining, ["README"])

    def test_clear_job_slice_dir_does_not_touch_other_jobs(self) -> None:
        job_a = self._job_dir()
        other = job_store.job_stl_dir(self.root, "other-job")
        other.mkdir(parents=True, exist_ok=True)
        (job_a / "CubeBody.stl").write_text("a", encoding="utf-8")
        (other / "KeepMe.stl").write_text("b", encoding="utf-8")

        job_store.clear_job_slice_dir(self.root, self.job_id)

        self.assertFalse(any(job_a.iterdir()))
        self.assertEqual([p.name for p in other.iterdir()], ["KeepMe.stl"])

    def test_clear_job_gcode_dir_removes_viewer_gcode_artifacts(self) -> None:
        job_dir = self._job_dir()
        (job_dir / "CubeBody.stl").write_text("stl", encoding="utf-8")
        (job_dir / "CubeBody.gcode.3mf").write_text("3mf", encoding="utf-8")
        (job_dir / "_viewer_old.gcode.3mf").write_text("v", encoding="utf-8")

        job_store.clear_job_gcode_dir(self.root, self.job_id)

        remaining = sorted(p.name for p in job_dir.iterdir())
        self.assertEqual(remaining, ["CubeBody.stl"])


if __name__ == "__main__":
    unittest.main()
