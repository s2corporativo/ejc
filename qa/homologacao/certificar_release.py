#!/usr/bin/env python3
"""Certifica uma release do EJC a partir de evidências sanitizadas.

Este comando NÃO executa deploy, backup ou homologação. Ele valida que as
evidências obrigatórias já foram produzidas e que o commit implantado coincide
com o commit aprovado. Nenhum segredo, token ou corpo de documento deve entrar
no manifesto ou no relatório.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

EXPECTED_SCENARIOS = [f"H{number:02d}" for number in range(1, 16)]
MANUAL_OVERRIDE_SCENARIOS = {"H13", "H14"}
REQUIRED_CONTROLS = {
    "ci",
    "branch_protection",
    "backup",
    "restore",
    "rollback",
    "rpo_rto",
    "security_audit",
}
REQUIRED_APPROVAL_ROLES = {
    "responsavel_tecnico",
    "responsavel_juridico_lgpd",
    "titular_produto",
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SENSITIVE_KEY_RE = re.compile(
    r"(password|senha|secret|token|api[_-]?key|private[_-]?key|refresh[_-]?token)",
    re.IGNORECASE,
)


class CertificationError(ValueError):
    """Manifesto ou relatório não satisfaz o contrato de certificação."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CertificationError(f"arquivo não encontrado: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CertificationError(
            f"JSON inválido em {path}: linha {exc.lineno}, coluna {exc.colno}"
        ) from exc
    if not isinstance(payload, dict):
        raise CertificationError(f"{path} deve conter um objeto JSON")
    return payload


def _require_mapping(parent: dict[str, Any], key: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise CertificationError(f"{key} deve ser objeto")
    return value


def _require_nonempty_text(parent: dict[str, Any], key: str, context: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise CertificationError(f"{context}.{key} deve ser texto não vazio")
    return value.strip()


def _validate_timestamp(value: str, context: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CertificationError(f"{context} deve usar timestamp ISO-8601") from exc
    if parsed.tzinfo is None:
        raise CertificationError(f"{context} deve conter fuso horário")


def _validate_no_sensitive_keys(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if SENSITIVE_KEY_RE.search(str(key)):
                raise CertificationError(
                    f"campo sensível proibido no manifesto/relatório: {path}.{key}"
                )
            _validate_no_sensitive_keys(nested, f"{path}.{key}")
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            _validate_no_sensitive_keys(nested, f"{path}[{index}]")


def _validate_evidence_reference(control: dict[str, Any], context: str) -> None:
    evidence = _require_nonempty_text(control, "evidence", context)
    lowered = evidence.casefold()
    if any(marker in lowered for marker in ("bearer ", "password=", "senha=", "token=")):
        raise CertificationError(f"{context}.evidence aparenta conter segredo")
    if "\n" in evidence or "\r" in evidence:
        raise CertificationError(f"{context}.evidence deve ser referência de uma linha")


def _validate_release(manifest: dict[str, Any]) -> tuple[str, str]:
    release = _require_mapping(manifest, "release")
    approved_sha = _require_nonempty_text(release, "approved_commit_sha", "release")
    deployed_sha = _require_nonempty_text(release, "deployed_commit_sha", "release")
    if not SHA_RE.fullmatch(approved_sha):
        raise CertificationError("release.approved_commit_sha deve ser SHA-1 de 40 hex")
    if not SHA_RE.fullmatch(deployed_sha):
        raise CertificationError("release.deployed_commit_sha deve ser SHA-1 de 40 hex")
    if approved_sha != deployed_sha:
        raise CertificationError(
            "commit implantado diverge do commit aprovado; certificar é proibido"
        )

    environment = _require_nonempty_text(release, "environment", "release")
    if environment not in {"homologacao", "producao"}:
        raise CertificationError(
            "release.environment deve ser 'homologacao' ou 'producao'"
        )
    deployed_at = _require_nonempty_text(release, "deployed_at", "release")
    _validate_timestamp(deployed_at, "release.deployed_at")
    return approved_sha, environment


def _validate_report_commit_sha(report: dict[str, Any], approved_sha: str) -> None:
    """Vincula o relatório H01–H15 ao SHA aprovado — sem isso, o relatório é só
    "H01–H15 passaram em algum commit, algum dia", não uma prova ligada à
    release. `run_homologacao.py` grava `commit_sha` via `git rev-parse HEAD`
    no momento da execução; aqui é onde essa amarração é COBRADA."""
    report_sha = report.get("commit_sha")
    if not isinstance(report_sha, str) or not report_sha.strip():
        raise CertificationError(
            "relatório não contém 'commit_sha' — gere com run_homologacao.py "
            "atualizado (grava o commit_sha automaticamente) para vincular "
            "H01–H15 ao SHA da release"
        )
    report_sha = report_sha.strip()
    if not SHA_RE.fullmatch(report_sha):
        raise CertificationError("relatório.commit_sha deve ser SHA-1 de 40 hex")
    if report_sha != approved_sha:
        raise CertificationError(
            "relatório de homologação (H01–H15) foi gerado em um commit "
            f"diferente do aprovado: relatório={report_sha} "
            f"aprovado={approved_sha}. H01–H15 não provam nada sobre o SHA "
            "que está sendo certificado — rode run_homologacao.py de novo no "
            "SHA candidato."
        )


def _validate_expected_sha(approved_sha: str, expected_sha: str | None) -> None:
    """Vincula a certificação ao commit que ESTÁ SENDO CERTIFICADO nesta
    execução — não apenas ao que o manifesto AFIRMA. Sem isso, qualquer
    manifesto internamente consistente (approved == deployed == relatório)
    passa mesmo rodando num checkout de outro commit: nada no processo
    obrigava o SHA declarado a ser o SHA real sob teste.

    `expected_sha` normalmente vem de `git rev-parse HEAD` do checkout que o
    workflow de CI fez para este job — é o SHA real, não um campo que alguém
    preencheu à mão. Opcional na CLI para não quebrar uso local/manual (onde
    conferir o SHA é responsabilidade humana, como já documentado no runbook),
    mas o workflow de release SEMPRE o passa — é o que fecha o gate de verdade
    (Issue #715)."""
    if expected_sha is None:
        return
    expected_sha = expected_sha.strip()
    if not SHA_RE.fullmatch(expected_sha):
        raise CertificationError(
            "--expected-sha deve ser SHA-1 de 40 hex (recebido do checkout "
            "real do workflow; se isto falhar, o checkout está errado, não o "
            "manifesto)"
        )
    if expected_sha != approved_sha:
        raise CertificationError(
            "SHA do checkout real desta execução diverge do manifesto: "
            f"checkout={expected_sha} manifesto.approved_commit_sha="
            f"{approved_sha}. Certificar é proibido — o manifesto certifica "
            "um commit que não é o que está rodando agora."
        )


def _report_scenarios(report: dict[str, Any]) -> dict[str, str]:
    scenarios = report.get("cenarios")
    if not isinstance(scenarios, list):
        raise CertificationError("relatório deve conter lista 'cenarios'")
    result: dict[str, str] = {}
    for scenario in scenarios:
        if not isinstance(scenario, dict):
            raise CertificationError("cada cenário do relatório deve ser objeto")
        scenario_id = scenario.get("id")
        status = scenario.get("status")
        if scenario_id in result:
            raise CertificationError(f"cenário duplicado no relatório: {scenario_id}")
        if scenario_id not in EXPECTED_SCENARIOS:
            raise CertificationError(f"cenário desconhecido no relatório: {scenario_id}")
        if status not in {"PASS", "FALHA", "BLOQUEADO"}:
            raise CertificationError(
                f"{scenario_id}: status inválido {status!r} no relatório"
            )
        result[str(scenario_id)] = str(status)
    missing = [scenario_id for scenario_id in EXPECTED_SCENARIOS if scenario_id not in result]
    if missing:
        raise CertificationError(f"relatório não contém todos H01–H15: {missing}")
    return result


def _manual_scenarios(manifest: dict[str, Any]) -> dict[str, str]:
    manual = manifest.get("manual_scenarios", {})
    if not isinstance(manual, dict):
        raise CertificationError("manual_scenarios deve ser objeto")
    result: dict[str, str] = {}
    for scenario_id, proof in manual.items():
        if scenario_id not in MANUAL_OVERRIDE_SCENARIOS:
            raise CertificationError(
                f"override manual permitido apenas para H13/H14; obtido {scenario_id}"
            )
        if not isinstance(proof, dict):
            raise CertificationError(f"manual_scenarios.{scenario_id} deve ser objeto")
        status = proof.get("status")
        if status != "PASS":
            raise CertificationError(
                f"manual_scenarios.{scenario_id}.status deve ser PASS"
            )
        _validate_evidence_reference(proof, f"manual_scenarios.{scenario_id}")
        executor = _require_nonempty_text(
            proof, "executed_by", f"manual_scenarios.{scenario_id}"
        )
        if len(executor) > 200:
            raise CertificationError(
                f"manual_scenarios.{scenario_id}.executed_by excede 200 caracteres"
            )
        executed_at = _require_nonempty_text(
            proof, "executed_at", f"manual_scenarios.{scenario_id}"
        )
        _validate_timestamp(
            executed_at, f"manual_scenarios.{scenario_id}.executed_at"
        )
        result[scenario_id] = "PASS"
    return result


def _validate_homologation(manifest: dict[str, Any], report: dict[str, Any]) -> None:
    statuses = _report_scenarios(report)
    statuses.update(_manual_scenarios(manifest))
    failures = {
        scenario_id: status
        for scenario_id, status in statuses.items()
        if status != "PASS"
    }
    if failures:
        formatted = ", ".join(
            f"{scenario_id}={status}" for scenario_id, status in sorted(failures.items())
        )
        raise CertificationError(f"homologação incompleta: {formatted}")


def _validate_controls(manifest: dict[str, Any]) -> None:
    controls = _require_mapping(manifest, "controls")
    missing = sorted(REQUIRED_CONTROLS - set(controls))
    if missing:
        raise CertificationError(f"controles obrigatórios ausentes: {missing}")

    for name in sorted(REQUIRED_CONTROLS - {"rpo_rto"}):
        control = controls.get(name)
        if not isinstance(control, dict):
            raise CertificationError(f"controls.{name} deve ser objeto")
        if control.get("status") != "PASS":
            raise CertificationError(f"controls.{name}.status deve ser PASS")
        _validate_evidence_reference(control, f"controls.{name}")

    backup = controls["backup"]
    for field in ("database_encrypted", "uploads_encrypted", "offsite_copy"):
        if backup.get(field) is not True:
            raise CertificationError(f"controls.backup.{field} deve ser true")

    restore = controls["restore"]
    for field in ("database_restored", "uploads_restored", "application_started"):
        if restore.get(field) is not True:
            raise CertificationError(f"controls.restore.{field} deve ser true")

    rollback = controls["rollback"]
    if rollback.get("tested") is not True:
        raise CertificationError("controls.rollback.tested deve ser true")

    security = controls["security_audit"]
    for field in ("rbac", "idor", "lgpd", "ai_rag"):
        if security.get(field) is not True:
            raise CertificationError(f"controls.security_audit.{field} deve ser true")

    rpo_rto = controls["rpo_rto"]
    if not isinstance(rpo_rto, dict):
        raise CertificationError("controls.rpo_rto deve ser objeto")
    if rpo_rto.get("status") != "APPROVED":
        raise CertificationError("controls.rpo_rto.status deve ser APPROVED")
    for field in ("rpo_hours", "rto_hours"):
        value = rpo_rto.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            raise CertificationError(
                f"controls.rpo_rto.{field} deve ser número positivo"
            )
    _validate_evidence_reference(rpo_rto, "controls.rpo_rto")
    approved_at = _require_nonempty_text(
        rpo_rto, "approved_at", "controls.rpo_rto"
    )
    _validate_timestamp(approved_at, "controls.rpo_rto.approved_at")


def _validate_approvals(manifest: dict[str, Any]) -> None:
    approvals = manifest.get("approvals")
    if not isinstance(approvals, list):
        raise CertificationError("approvals deve ser lista")
    found: set[str] = set()
    for approval in approvals:
        if not isinstance(approval, dict):
            raise CertificationError("cada aprovação deve ser objeto")
        role = _require_nonempty_text(approval, "role", "approvals")
        if role in found:
            raise CertificationError(f"papel de aprovação duplicado: {role}")
        found.add(role)
        if approval.get("status") != "APPROVED":
            raise CertificationError(f"aprovação {role} deve ter status APPROVED")
        _require_nonempty_text(approval, "approved_by", f"approvals.{role}")
        approved_at = _require_nonempty_text(
            approval, "approved_at", f"approvals.{role}"
        )
        _validate_timestamp(approved_at, f"approvals.{role}.approved_at")
        _validate_evidence_reference(approval, f"approvals.{role}")
    missing = sorted(REQUIRED_APPROVAL_ROLES - found)
    if missing:
        raise CertificationError(f"aprovações obrigatórias ausentes: {missing}")


def _validate_decision(manifest: dict[str, Any], environment: str) -> str:
    decision = _require_mapping(manifest, "decision")
    status = _require_nonempty_text(decision, "status", "decision")
    if status not in {"piloto_controlado", "producao"}:
        raise CertificationError(
            "decision.status deve ser 'piloto_controlado' ou 'producao'"
        )
    restrictions = decision.get("restrictions", [])
    if not isinstance(restrictions, list) or not all(
        isinstance(item, str) and item.strip() for item in restrictions
    ):
        raise CertificationError("decision.restrictions deve ser lista de textos")
    if status == "producao" and restrictions:
        raise CertificationError(
            "decisão de produção não pode manter restrições pendentes; use piloto_controlado"
        )
    if status == "producao" and environment != "producao":
        raise CertificationError(
            "decisão de produção exige release.environment='producao'"
        )
    return status


def certify(
    manifest: dict[str, Any],
    report: dict[str, Any],
    *,
    expected_sha: str | None = None,
) -> dict[str, Any]:
    _validate_no_sensitive_keys(manifest)
    _validate_no_sensitive_keys(report)
    approved_sha, environment = _validate_release(manifest)
    _validate_expected_sha(approved_sha, expected_sha)
    _validate_report_commit_sha(report, approved_sha)
    _validate_homologation(manifest, report)
    _validate_controls(manifest)
    _validate_approvals(manifest)
    decision = _validate_decision(manifest, environment)
    return {
        "schema_version": 1,
        "status": (
            "CERTIFICADO_PRODUCAO"
            if decision == "producao"
            else "CERTIFICADO_PILOTO_CONTROLADO"
        ),
        "commit_sha": approved_sha,
        "environment": environment,
        "decision": decision,
        "h01_h15": "PASS",
        "production_ready": decision == "producao",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Valida o pacote de certificação da release EJC"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("qa/homologacao/reports/release_certification.json"),
    )
    parser.add_argument(
        "--expected-sha",
        default=None,
        help=(
            "SHA-1 do commit que está REALMENTE sob certificação nesta "
            "execução (ex.: 'git rev-parse HEAD' do checkout do workflow). "
            "Quando informado, precisa bater com release.approved_commit_sha "
            "do manifesto — é o que impede certificar um manifesto "
            "internamente consistente rodando sobre outro commit. O "
            "workflow de release SEMPRE passa este argumento; uso manual "
            "local pode omiti-lo (nesse caso a conferência é humana, como "
            "já documentado no runbook)."
        ),
    )
    args = parser.parse_args()

    try:
        result = certify(
            _load_json(args.manifest),
            _load_json(args.report),
            expected_sha=args.expected_sha,
        )
    except CertificationError as exc:
        failure = {
            "schema_version": 1,
            "status": "NAO_CERTIFICADO",
            "reason": str(exc),
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(failure, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[EJC] NÃO CERTIFICADO: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[EJC] {result['status']} — commit {result['commit_sha']}")
    print(f"[EJC] relatório: {args.output}")


if __name__ == "__main__":
    main()
