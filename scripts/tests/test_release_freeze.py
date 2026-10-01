import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.check_release_freeze as gate


class ReleaseFreezeTest(unittest.TestCase):
    def _cfg(self, root: Path, **overrides) -> Path:
        data = {
            "schema_version": 1,
            "release": "rc",
            "require_full_ci": True,
            "purpose": "test",
            "freeze_main": True,
            "allowed_source_branch": "release/rc",
        }
        data.update(overrides)
        p = root / "release_candidate.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_release_branch_autorizada(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(gate, "CONFIG", self._cfg(Path(tmp))):
                ok, _ = gate.validate({
                    "CI_PIPELINE_EVENT": "pull_request",
                    "CI_COMMIT_SOURCE_BRANCH": "release/rc",
                })
        self.assertTrue(ok)

    def test_outro_pr_bloqueado_durante_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(gate, "CONFIG", self._cfg(Path(tmp))):
                ok, msg = gate.validate({
                    "CI_PIPELINE_EVENT": "pull_request",
                    "CI_COMMIT_SOURCE_BRANCH": "feature/outra",
                })
        self.assertFalse(ok)
        self.assertIn("bloqueada", msg)

    def test_freeze_exige_ci_integral(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(gate, "CONFIG", self._cfg(Path(tmp), require_full_ci=False)):
                ok, msg = gate.validate({})
        self.assertFalse(ok)
        self.assertIn("require_full_ci", msg)

    def test_freeze_desativado_libera_pr(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(gate, "CONFIG", self._cfg(Path(tmp), freeze_main=False)):
                ok, _ = gate.validate({
                    "CI_PIPELINE_EVENT": "pull_request",
                    "CI_COMMIT_SOURCE_BRANCH": "feature/outra",
                })
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
