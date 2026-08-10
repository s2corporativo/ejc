from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "ci_evidence.py"
SHA = "a" * 40
REQUIRED_LOGS = {
    "backend.log",
    "eval.log",
    "frontend.log",
    "p0.log",
    "governanca.log",
    "architecture.log",
    "continuity.log",
    "ui-extra.log",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("ejc_ci_evidence_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def evidence():
    return _load_module()


def _write_full_logs(attempt: Path) -> None:
    for name in REQUIRED_LOGS:
        (attempt / name).write_text(f"conteudo-{name}\n", encoding="utf-8")


def _finish_success(module, root: Path, attempt: Path) -> Path:
    _write_full_logs(attempt)
    return module.finish_attempt(
        attempt=attempt,
        sha_root=root / SHA,
        sha=SHA,
        ref="feature/test",
        pr=123,
        result="success",
        failed_stage=None,
        exit_code=0,
        promote=True,
    )


def test_nova_tentativa_invalida_sucesso_anterior_imediatamente(tmp_path: Path, evidence):
    attempt_a = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    _finish_success(evidence, tmp_path, attempt_a)
    assert evidence.verify_success(tmp_path / SHA, SHA) is True

    attempt_b = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)

    assert attempt_b != attempt_a
    assert evidence.verify_success(tmp_path / SHA, SHA) is False


def test_falha_posterior_nunca_reutiliza_verde_antigo(tmp_path: Path, evidence):
    attempt_a = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    _finish_success(evidence, tmp_path, attempt_a)
    assert evidence.verify_success(tmp_path / SHA, SHA) is True

    attempt_b = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    (attempt_b / "backend.log").write_text("pytest failed\n", encoding="utf-8")
    evidence.finish_attempt(
        attempt=attempt_b,
        sha_root=tmp_path / SHA,
        sha=SHA,
        ref="feature/test",
        pr=123,
        result="failure",
        failed_stage="backend",
        exit_code=1,
        promote=False,
    )

    assert evidence.verify_success(tmp_path / SHA, SHA) is False
    assert evidence.latest_log(tmp_path / SHA, SHA, 0) == attempt_b / "backend.log"


def test_sucesso_exige_exatamente_os_oito_logs_do_full_gate(tmp_path: Path, evidence):
    attempt = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    for name in REQUIRED_LOGS - {"ui-extra.log"}:
        (attempt / name).write_text("ok\n", encoding="utf-8")

    with pytest.raises(ValueError, match="oito logs"):
        evidence.finish_attempt(
            attempt=attempt,
            sha_root=tmp_path / SHA,
            sha=SHA,
            ref="feature/test",
            pr=123,
            result="success",
            failed_stage=None,
            exit_code=0,
            promote=True,
        )

    assert evidence.verify_success(tmp_path / SHA, SHA) is False


def test_log_adulterado_depois_da_promocao_invalida_evidencia(tmp_path: Path, evidence):
    attempt = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    _finish_success(evidence, tmp_path, attempt)
    assert evidence.verify_success(tmp_path / SHA, SHA) is True

    (attempt / "backend.log").write_text("conteudo adulterado\n", encoding="utf-8")

    assert evidence.verify_success(tmp_path / SHA, SHA) is False


def test_summary_adulterado_depois_da_promocao_invalida_evidencia(tmp_path: Path, evidence):
    attempt = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    summary = _finish_success(evidence, tmp_path, attempt)
    assert evidence.verify_success(tmp_path / SHA, SHA) is True

    data = json.loads(summary.read_text(encoding="utf-8"))
    data["result"] = "failure"
    summary.write_text(json.dumps(data), encoding="utf-8")

    assert evidence.verify_success(tmp_path / SHA, SHA) is False


def test_pointer_com_path_traversal_e_rejeitado(tmp_path: Path, evidence):
    attempt = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    _finish_success(evidence, tmp_path, attempt)
    pointer = tmp_path / SHA / "latest-success.json"
    data = json.loads(pointer.read_text(encoding="utf-8"))
    data["summary"] = "../fora.json"
    pointer.write_text(json.dumps(data), encoding="utf-8")

    assert evidence.verify_success(tmp_path / SHA, SHA) is False


def test_symlink_em_log_e_rejeitado(tmp_path: Path, evidence):
    attempt = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    outside = tmp_path / "outside.log"
    outside.write_text("conteudo externo\n", encoding="utf-8")
    for name in REQUIRED_LOGS - {"backend.log"}:
        (attempt / name).write_text("ok\n", encoding="utf-8")
    (attempt / "backend.log").symlink_to(outside)

    with pytest.raises(ValueError, match="arquivo de evidência inválido"):
        evidence.finish_attempt(
            attempt=attempt,
            sha_root=tmp_path / SHA,
            sha=SHA,
            ref="feature/test",
            pr=123,
            result="success",
            failed_stage=None,
            exit_code=0,
            promote=True,
        )


def test_tentativa_stale_nao_pode_finalizar_apos_nova_tentativa(tmp_path: Path, evidence):
    attempt_a = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    _write_full_logs(attempt_a)
    attempt_b = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    _write_full_logs(attempt_b)

    with pytest.raises(ValueError, match="tentativa stale"):
        evidence.finish_attempt(
            attempt=attempt_a,
            sha_root=tmp_path / SHA,
            sha=SHA,
            ref="feature/test",
            pr=123,
            result="success",
            failed_stage=None,
            exit_code=0,
            promote=True,
        )

    evidence.finish_attempt(
        attempt=attempt_b,
        sha_root=tmp_path / SHA,
        sha=SHA,
        ref="feature/test",
        pr=123,
        result="success",
        failed_stage=None,
        exit_code=0,
        promote=True,
    )
    assert evidence.verify_success(tmp_path / SHA, SHA) is True


def test_sucesso_com_exit_code_nao_zero_e_rejeitado(tmp_path: Path, evidence):
    attempt = evidence.start_attempt(tmp_path, SHA, "feature/test", 123)
    _write_full_logs(attempt)

    with pytest.raises(ValueError, match="exit_code=0"):
        evidence.finish_attempt(
            attempt=attempt,
            sha_root=tmp_path / SHA,
            sha=SHA,
            ref="feature/test",
            pr=123,
            result="success",
            failed_stage=None,
            exit_code=2,
            promote=True,
        )
