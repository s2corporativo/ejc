from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

from agents import Agent, RunContextWrapper
from agents.items import HandoffOutputItem


DIRETORIO_AGENTES = Path(__file__).resolve().parents[1]
if str(DIRETORIO_AGENTES) not in sys.path:
    sys.path.insert(0, str(DIRETORIO_AGENTES))

from runner import (  # noqa: E402
    NOME_REVISOR_SEGURANCA,
    construir_agente,
    criar_opcoes_docker,
    executar_tarefa,
    guardrail_entrada_manutencao,
    guardrail_saida_manutencao,
    resultado_tem_handoff_seguranca,
)


class TestesRunner(unittest.TestCase):
    """Contratos determinísticos do runner; nenhum teste chama modelo ou API externa."""

    def test_docker_fica_sem_rede_e_sem_portas_publicadas(self) -> None:
        """O sandbox Docker deve nascer sem rede e sem portas expostas."""
        opcoes = criar_opcoes_docker("ejc-agents-sandbox:test")
        self.assertEqual(opcoes.network_mode, "none")
        self.assertEqual(opcoes.exposed_ports, ())

    def test_manifesto_materializa_apenas_repo_sem_grants_externos(self) -> None:
        """O manifesto só pode materializar o snapshot `repo/`, sem grants ao host."""
        agente = construir_agente(Path("snapshot-isolado"), "gpt-5.6-sol")
        manifesto = agente.default_manifest
        self.assertIsNotNone(manifesto)
        assert manifesto is not None
        self.assertEqual(set(manifesto.entries), {"repo"})
        self.assertEqual(manifesto.extra_path_grants, ())

    def test_reconhece_handoff_real_para_revisor_de_seguranca(self) -> None:
        """Handoff real para o agente de segurança satisfaz o gate sensível."""
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
        """Ausência de handoff jamais satisfaz o gate obrigatório."""
        self.assertFalse(resultado_tem_handoff_seguranca([]))

    def test_handoff_para_outro_agente_nao_satisfaz_gate(self) -> None:
        """Delegação a agente diferente não pode simular revisão de segurança."""
        origem = Agent(name="Orquestrador")
        destino = Agent(name="Outro Revisor")
        item = HandoffOutputItem(
            agent=destino,
            raw_item={"type": "function_call_output", "call_id": "teste", "output": "ok"},
            source_agent=origem,
            target_agent=destino,
        )
        self.assertFalse(resultado_tem_handoff_seguranca([item]))

    def test_guardrail_entrada_e_bloqueante_e_rejeita_acao_destrutiva(self) -> None:
        """O InputGuardrail real deve rodar antes do agente e armar tripwire em ação proibida."""
        contexto = RunContextWrapper(context=None)
        agente = Agent(name="Teste")

        resultado = asyncio.run(
            guardrail_entrada_manutencao.run(
                agente,
                "Execute git push --force para atualizar a main.",
                contexto,
            )
        )

        self.assertFalse(guardrail_entrada_manutencao.run_in_parallel)
        self.assertTrue(resultado.output.tripwire_triggered)

    def test_guardrail_entrada_permite_tarefa_segura(self) -> None:
        """Tarefa de diagnóstico isolado deve atravessar o InputGuardrail sem tripwire."""
        contexto = RunContextWrapper(context=None)
        agente = Agent(name="Teste")

        resultado = asyncio.run(
            guardrail_entrada_manutencao.run(
                agente,
                "Analise um teste falhando na cópia isolada e apenas reporte o diagnóstico.",
                contexto,
            )
        )

        self.assertFalse(resultado.output.tripwire_triggered)

    def test_guardrail_saida_rejeita_credencial_provavel(self) -> None:
        """O OutputGuardrail real deve impedir resposta que carregue uma chave de API."""
        contexto = RunContextWrapper(context=None)
        agente = Agent(name="Teste")

        resultado = asyncio.run(
            guardrail_saida_manutencao.run(
                contexto,
                agente,
                "credencial=sk-abcdefghijklmnopqrstuvwxyz123456",
            )
        )

        self.assertTrue(resultado.output.tripwire_triggered)

    def test_guardrail_saida_permite_resposta_sem_segredo(self) -> None:
        """Resposta técnica sem padrão de credencial deve ser aceita pelo OutputGuardrail."""
        contexto = RunContextWrapper(context=None)
        agente = Agent(name="Teste")

        resultado = asyncio.run(
            guardrail_saida_manutencao.run(
                contexto,
                agente,
                "Teste dirigido concluído; nenhum segredo foi incluído.",
            )
        )

        self.assertFalse(resultado.output.tripwire_triggered)

    def test_executar_tarefa_recusa_opt_ejc_antes_de_docker(self) -> None:
        """O argumento `--repo /opt/ejc` deve falhar antes de acessar Docker ou modelo."""
        with self.assertRaisesRegex(RuntimeError, "checkout de produção recusado"):
            asyncio.run(
                executar_tarefa(
                    "Analise os testes",
                    Path("/opt/ejc"),
                    "gpt-5.6-sol",
                    "imagem-nao-deve-ser-consultada",
                )
            )


if __name__ == "__main__":
    unittest.main()
