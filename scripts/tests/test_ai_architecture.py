"""Contratos estruturais do núcleo canônico de IA/RAG.

Estes testes não fazem chamadas de rede: protegem a topologia do código e
impedem que um novo módulo contorne as políticas centralizadas.
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "backend" / "app"


class AIArchitectureContract(unittest.TestCase):
    def test_providers_only_imported_by_gateway_or_provider_package(self):
        forbidden = []
        for path in APP.rglob("*.py"):
            relative = path.relative_to(APP).as_posix()
            if relative == "services/ai_gateway.py" or relative.startswith("services/providers/"):
                continue
            text = path.read_text(encoding="utf-8")
            if "app.services.providers" in text or "services.providers." in text:
                forbidden.append(relative)
        self.assertEqual(
            forbidden,
            [],
            "providers de IA devem ser acessados exclusivamente pelo ai_gateway: "
            + ", ".join(forbidden),
        )

    def test_gateway_exposes_the_canonical_policy_layers(self):
        gateway = (APP / "services" / "ai_gateway.py").read_text(encoding="utf-8")
        for marker in (
            "_chamar_com_barreira",
            "_resolver_cadeia",
            "_deadline_cadeia",
            "AI_REQUIRE_SANITIZATION_FOR_EXTERNAL",
            "_restringir_cadeia_local_completo",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, gateway)

    def test_rag_retrieval_has_one_scope_and_governance_contract(self):
        service = (APP / "services" / "ai_service.py").read_text(encoding="utf-8")
        for marker in (
            "_FILTRO_ESCOPO_RAG",
            "_FILTRO_GATE_RAG",
            "_FILTRO_REVOGADA_RAG",
            "def filtros_gate_rag(",
            "async def buscar_contexto_rag(",
            "_filtros_gate_rag(incluir_ficticio)",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, service)

    def test_backup_rclone_has_remote_rotation_contract(self):
        service = (APP / "services" / "backup_service.py").read_text(encoding="utf-8")
        for marker in (
            "def selecionar_para_rotacao_rclone(",
            "def _rotacionar_rclone_sync(",
            "rclone lsjson",
            "rclone deletefile",
            "_criar_manifesto_cifrado",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, service)


if __name__ == "__main__":
    unittest.main()
