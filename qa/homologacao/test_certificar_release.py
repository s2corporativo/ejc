from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("certificar_release.py")
SHA = "a" * 40


def report(*, blocked: str | None = None, commit_sha: str = SHA) -> dict:
    scenarios = []
    for number in range(1, 16):
        scenario_id = f"H{number:02d}"
        status = "BLOQUEADO" if scenario_id == blocked else "PASS"
        scenarios.append({"id": scenario_id, "status": status, "passos": []})
    payload = {"cenarios": scenarios}
    if commit_sha is not None:
        payload["commit_sha"] = commit_sha
    return payload


def manifest(*, deployed_sha: str = SHA, include_approvals: bool = True) -> dict:
    payload = {
        "schema_version": 1,
        "release": {
            "approved_commit_sha": SHA,
            "deployed_commit_sha": deployed_sha,
            "environment": "homologacao",
            "deployed_at": "2026-08-05T12:00:00-03:00",
        },
        "manual_scenarios": {
            "H13": {
                "status": "PASS",
                "evidence": "evidencias/H13-backup-restauracao.md",
                "executed_by": "Executor homologação",
                "executed_at": "2026-08-05T12:30:00-03:00",
            },
            "H14": {
                "status": "PASS",
                "evidence": "evidencias/H14-deploy-rollback.md",
                "executed_by": "Executor homologação",
                "executed_at": "2026-08-05T13:00:00-03:00",
            },
        },
        "controls": {
            "ci": {
                "status": "PASS",
                "evidence": "GitHub Actions/run-123",
            },
            "branch_protection": {
                "status": "PASS",
                "evidence": "evidencias/branch-protection.md",
            },
            "backup": {
                "status": "PASS",
                "database_encrypted": True,
                "uploads_encrypted": True,
                "offsite_copy": True,
                "evidence": "evidencias/backup.md",
            },
            "restore": {
                "status": "PASS",
                "database_restored": True,
                "uploads_restored": True,
                "application_started": True,
                "evidence": "evidencias/restore.md",
            },
            "rollback": {
                "status": "PASS",
                "tested": True,
                "evidence": "evidencias/rollback.md",
            },
            "rpo_rto": {
                "status": "APPROVED",
                "rpo_hours": 24,
                "rto_hours": 4,
                "approved_at": "2026-08-05T13:10:00-03:00",
                "evidence": "evidencias/rpo-rto.md",
            },
            "security_audit": {
                "status": "PASS",
                "rbac": True,
                "idor": True,
                "lgpd": True,
                "ai_rag": True,
                "evidence": "evidencias/auditoria-seguranca.md",
            },
        },
        "approvals": [
            {
                "role": "responsavel_tecnico",
                "status": "APPROVED",
                "approved_by": "Responsável técnico",
                "approved_at": "2026-08-05T14:00:00-03:00",
                "evidence": "evidencias/ata.md#tecnico",
            },
            {
                "role": "responsavel_juridico_lgpd",
                "status": "APPROVED",
                "approved_by": "Responsável jurídico/LGPD",
                "approved_at": "2026-08-05T14:05:00-03:00",
                "evidence": "evidencias/ata.md#juridico",
            },
            {
                "role": "titular_produto",
                "status": "APPROVED",
                "approved_by": "Titular do produto",
                "approved_at": "2026-08-05T14:10:00-03:00",
                "evidence": "evidencias/ata.md#titular",
            },
        ],
        "decision": {
            "status": "piloto_controlado",
            "restrictions": ["dados fictícios e casos selecionados"],
        },
    }
    if not include_approvals:
        payload["approvals"] = []
    return payload


class CertificationCliTest(unittest.TestCase):
    def run_cli(
        self,
        manifest_payload: dict,
        report_payload: dict,
        *,
        expected_sha: str | None = None,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest_path = root / "manifest.json"
            report_path = root / "report.json"
            output_path = root / "certification.json"
            manifest_path.write_text(json.dumps(manifest_payload), encoding="utf-8")
            report_path.write_text(json.dumps(report_payload), encoding="utf-8")
            argv = [
                sys.executable,
                str(SCRIPT),
                "--manifest",
                str(manifest_path),
                "--report",
                str(report_path),
                "--output",
                str(output_path),
            ]
            if expected_sha is not None:
                argv += ["--expected-sha", expected_sha]
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
            )
            output = json.loads(output_path.read_text(encoding="utf-8"))
            return completed, output

    def test_certifica_piloto_com_h13_h14_manuais(self):
        completed, output = self.run_cli(
            manifest(),
            report(blocked="H13"),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["status"], "CERTIFICADO_PILOTO_CONTROLADO")
        self.assertFalse(output["production_ready"])

    def test_bloqueia_cenario_sem_override(self):
        completed, output = self.run_cli(manifest(), report(blocked="H12"))
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(output["status"], "NAO_CERTIFICADO")
        self.assertIn("H12=BLOQUEADO", output["reason"])

    def test_bloqueia_commit_implantado_divergente(self):
        completed, output = self.run_cli(
            manifest(deployed_sha="b" * 40),
            report(),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("diverge", output["reason"])

    def test_bloqueia_sem_tres_aprovacoes(self):
        completed, output = self.run_cli(
            manifest(include_approvals=False),
            report(),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("aprovações obrigatórias ausentes", output["reason"])

    def test_bloqueia_chave_sensivel(self):
        payload = manifest()
        payload["api_key"] = "proibido"
        completed, output = self.run_cli(payload, report())
        self.assertEqual(completed.returncode, 2)
        self.assertIn("campo sensível proibido", output["reason"])

    # ── Issue #715: vincular H01–H15 e a execução real ao SHA da release ────

    def test_bloqueia_relatorio_sem_commit_sha(self):
        """H01–H15 verdes sem dizer de QUAL commit não provam nada sobre a
        release — run_homologacao.py desatualizado (sem o campo) não passa."""
        payload = report()
        del payload["commit_sha"]
        completed, output = self.run_cli(manifest(), payload)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("commit_sha", output["reason"])

    def test_bloqueia_relatorio_de_outro_commit(self):
        """H01–H15 rodaram de verdade, mas em outro commit — não podem
        certificar ESTA release, mesmo com manifesto internamente consistente
        (approved == deployed)."""
        completed, output = self.run_cli(manifest(), report(commit_sha="c" * 40))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("relatório", output["reason"])
        self.assertIn("commit", output["reason"])

    def test_certifica_quando_expected_sha_bate_com_manifesto(self):
        """Controle positivo: --expected-sha (o SHA real do checkout do
        workflow) igual ao aprovado não bloqueia a certificação normal."""
        completed, output = self.run_cli(
            manifest(), report(blocked="H13"), expected_sha=SHA
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(output["status"], "CERTIFICADO_PILOTO_CONTROLADO")

    def test_bloqueia_quando_expected_sha_diverge_do_manifesto(self):
        """O gate central da Issue #715: mesmo um manifesto 100% consistente
        internamente (aprovado == implantado == relatório) é reprovado se o
        checkout REAL desta execução (--expected-sha, vindo de
        'git rev-parse HEAD' no workflow) for outro commit — impede
        certificar um manifesto que não corresponde ao código sob teste."""
        completed, output = self.run_cli(
            manifest(), report(), expected_sha="d" * 40
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("checkout", output["reason"])

    def test_bloqueia_expected_sha_mal_formado(self):
        completed, output = self.run_cli(
            manifest(), report(), expected_sha="nao-e-um-sha"
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("--expected-sha", output["reason"])


if __name__ == "__main__":
    unittest.main()
