from __future__ import annotations

import sys
import unittest
from pathlib import Path

from agents import Agent
from agents.items import HandoffOutputItem


DIRETORIO_AGENTES = Path(__file__).resolve().parents[1]
if str(DIRETORIO_AGENTES) not in sys.path:
    sys.path.insert(0, str(DIRETORIO_AGENTES))

from runner import (  # noqa: E402
    NOME_REVISOR_SEGURANCA,
    construir_agente,
    criar_opcoes_docker,
    resultado_tem_handoff_seguranca,
)


class TestesRunner(unittest.TestCase):
    def test_docker_fica_sem_rede_e_sem_portas_publicadas(self) -> None:
        opcoes = criar_opcoes_docker("ejc-agents-sandbox:test")
        self.assertEqual(opcoes.network_mode, "none")
        self.assertEqual(opcoes.exposed_ports, ())

    def test_manifesto_materializa_apenas_repo_sem_grants_externos(self) -> None:
        agente = construir_agente(Path("snapshot-isolado"), "gpt-5.6-sol")
        manifesto = agente.default_manifest
        self.assertIsNotNone(manifesto)
        assert manifesto is not None
        self.assertEqual(set(manifesto.entries), {"repo"})
        self.assertEqual(manifesto.extra_path_grants, ())

    def test_reconhece_handoff_real_para_revisor_de_seguranca(self) -> None:
        origem = Agent(name="Orquestrador")
        destino = Agent(name=NOME_REVISOR_SEGURANCA)
        item = HandoffOutputItem(
            agent=destino,
            raw_item={"type": "function_call_output", "call_id": "teste", "output": "ok"},
            source_agent=origem,
            target_agent=destino,
        )
        self.assertTrue(resultado_tem_handoff_seguranca([item]))

    def test_rejeita_lista_sem_handoff_de_seguranca(self) -> None:
        self.assertFalse(resultado_tem_handoff_seguranca([]))

    def test_handoff_para_outro_agente_nao_satisfaz_gate(self) -> None:
        origem = Agent(name="Orquestrador")
        destino = Agent(name="Outro Revisor")
        item = HandoffOutputItem(
            agent=destino,
            raw_item={"type": "function_call_output", "call_id": "teste", "output": "ok"},
            source_agent=origem,
            target_agent=destino,
        )
        self.assertFalse(resultado_tem_handoff_seguranca([item]))


if __name__ == "__main__":
    unittest.main()
