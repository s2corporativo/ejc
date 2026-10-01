import json
from pathlib import Path
import scripts.check_release_freeze as gate


def _cfg(tmp_path: Path, **overrides):
    data = {
        "schema_version": 1,
        "release": "rc",
        "require_full_ci": True,
        "purpose": "test",
        "freeze_main": True,
        "allowed_source_branch": "release/rc",
    }
    data.update(overrides)
    p = tmp_path / "release_candidate.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_release_branch_autorizada(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "CONFIG", _cfg(tmp_path))
    ok, _ = gate.validate({
        "CI_PIPELINE_EVENT": "pull_request",
        "CI_COMMIT_SOURCE_BRANCH": "release/rc",
    })
    assert ok


def test_outro_pr_bloqueado_durante_freeze(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "CONFIG", _cfg(tmp_path))
    ok, msg = gate.validate({
        "CI_PIPELINE_EVENT": "pull_request",
        "CI_COMMIT_SOURCE_BRANCH": "feature/outra",
    })
    assert not ok
    assert "bloqueada" in msg


def test_freeze_exige_ci_integral(monkeypatch, tmp_path):
    monkeypatch.setattr(gate, "CONFIG", _cfg(tmp_path, require_full_ci=False))
    ok, msg = gate.validate({})
    assert not ok
    assert "require_full_ci" in msg
