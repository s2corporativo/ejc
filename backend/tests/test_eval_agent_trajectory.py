"""Eval de TRAJETÓRIA do agente (app/eval/agent_trajectory.py) — offline, mockado.

Espelha o estilo de test_agente_ia.py: o LLM (chat_agentico) e TODAS as bordas do
loop (ownership, entidades, AILog, gate de citações, store HITL, REGISTRY.executar)
são substituídos por fakes em memória — nenhum teste toca rede/LLM/banco/Redis. O
próprio harness (avaliar_cenario) instala esses fakes via unittest.mock; aqui só
alimentamos CENÁRIOS (roteiros de tool-use) e conferimos as 4 métricas.

Cobre:
  • Gold set embarcado (agent_scenarios.jsonl): agregado 100% verde e comportamento
    por cenário (escolha de tool, fonte, HITL/leitura, orçamento).
  • Discriminação das métricas: cada métrica PODE ser False (negative controls) —
    prova que a suíte não é trivialmente verde.
  • Detector local de fonte (_tem_fonte).
"""
from __future__ import annotations

import pytest

from app.eval import agent_trajectory as at


# ══════════════════════════════════════════════════════════════════════════════
# 1. Detector local de fonte (métrica de fundamentação).
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectorFonte:
    @pytest.mark.parametrize("texto", [
        "conforme a Súmula 244 do TST",
        "nos termos do art. 927 do Código Civil",
        "art.5 da CF",
        "com base na Lei nº 8.078/90 (CDC)",
        "o STJ pacificou a matéria",
        "aplica-se o art. 10, II, b, do ADCT",
    ])
    def test_reconhece_fontes(self, texto):
        assert at._tem_fonte(texto) is True

    @pytest.mark.parametrize("texto", [
        "",
        "A tese é sólida e deve prosperar segundo nossa análise.",
        "Recomendo prosseguir com a estratégia proposta.",
    ])
    def test_ignora_texto_sem_fonte(self, texto):
        assert at._tem_fonte(texto) is False


# ══════════════════════════════════════════════════════════════════════════════
# 2. Gold set embarcado — agregado 100% verde + comportamento por cenário.
# ══════════════════════════════════════════════════════════════════════════════

class TestGoldSetEmbarcado:
    async def test_agregado_todo_verde(self):
        cenarios = at._carregar_cenarios(at.caminho_gold_padrao())
        assert len(cenarios) >= 6, "gold set deve ter os cenários curados"
        metricas, ag = await at.avaliar_cenarios(cenarios)

        assert all(m.erro is None for m in metricas), \
            [f"{m.id}: {m.erro}" for m in metricas if m.erro]
        assert ag.n == len(cenarios)
        # 1. escolha de ferramenta correta em 100% dos cenários com tool esperada.
        assert ag.acerto_ferramenta == 1.0 and ag.n_ferramenta == len(cenarios)
        # 2. fonte presente em 100% dos cenários que afirmam tese.
        assert ag.pct_com_fonte == 1.0 and ag.n_fonte == 2
        # 3. nenhuma violação de HITL/leitura.
        assert ag.violacoes_hitl == 0
        # 4. todas as trajetórias dentro do orçamento.
        assert ag.pct_dentro_orcamento == 1.0

    async def test_por_cenario(self):
        cenarios = at._carregar_cenarios(at.caminho_gold_padrao())
        metricas, _ = await at.avaliar_cenarios(cenarios)
        por_id = {m.id: m for m in metricas}

        # Leitura + fundamentação: chamou buscar_precedentes e citou fonte.
        prec = por_id["precedentes-fundamento"]
        assert prec.tool_correta is True and prec.tem_fonte is True
        assert prec.status == "ok" and prec.writes_executadas == []

        # Escrita SEM aprovação: o loop PAUSA e NUNCA executa a write-tool.
        pausa = por_id["minuta-hitl-pausa"]
        assert pausa.status == "pendente_confirmacao"
        assert pausa.writes_executadas == [] and pausa.hitl_respeitado is True
        assert "gerar_minuta_peca" in pausa.ferramentas_escolhidas

        # Escrita COM aprovação (hash): executa a write EXATA e conclui.
        aprov = por_id["minuta-hitl-aprovado"]
        assert aprov.status == "ok"
        assert aprov.writes_executadas == ["gerar_minuta_peca"]
        assert aprov.hitl_respeitado is True

        # Modo leitura: write pedida é BLOQUEADA (não executa) e o loop segue.
        leit = por_id["leitura-bloqueia-escrita"]
        assert leit.bloqueou_escrita is True
        assert leit.writes_executadas == [] and leit.status == "ok"
        assert leit.tem_fonte is True

        # Orçamento: modelo que nunca conclui para no teto (max_steps=3) com aviso.
        orc = por_id["orcamento-estoura"]
        assert orc.passos == 3 and orc.max_steps == 3
        assert orc.orcamento_respeitado is True


# ══════════════════════════════════════════════════════════════════════════════
# 3. Discriminação — cada métrica PODE dar False (negative controls). Prova que o
#    avaliador realmente mede e não é sempre verde.
# ══════════════════════════════════════════════════════════════════════════════

class TestMetricasDiscriminam:
    async def test_ferramenta_errada_e_flagrada(self):
        """Intenção pede buscar_precedentes, mas o modelo chama ler_dossie →
        tool_correta = False."""
        cenario = {
            "id": "neg-tool-errada", "intencao": "precedentes",
            "ferramenta_esperada": "buscar_precedentes", "hitl": "nenhum",
            "orcamento": "ok",
            "turnos": [
                {"text": "Vou ler o dossiê (tool errada).", "stop_reason": "tool_use",
                 "tools": [{"name": "ler_dossie", "input": {}}]},
                {"text": "Concluí.", "stop_reason": "end_turn"},
            ],
        }
        m = await at.avaliar_cenario(cenario)
        assert m.erro is None
        assert m.tool_correta is False
        assert m.ferramentas_escolhidas == ["ler_dossie"]

    async def test_tese_sem_fonte_e_flagrada(self):
        """espera_fonte=True mas a resposta final NÃO cita fonte → tem_fonte=False."""
        cenario = {
            "id": "neg-sem-fonte", "intencao": "afirma tese sem fundamentar",
            "espera_fonte": True, "hitl": "nenhum", "orcamento": "ok",
            "turnos": [
                {"text": "A tese vai vencer, pode confiar.", "stop_reason": "end_turn"},
            ],
        }
        m = await at.avaliar_cenario(cenario)
        assert m.erro is None
        assert m.espera_fonte is True and m.tem_fonte is False

    async def test_hitl_esperado_mas_nao_ocorreu_e_flagrado(self):
        """Cenário rotulado 'pausa' mas o modelo conclui sem pedir write → a
        trajetória NÃO pausou: violação de HITL detectada (hitl_respeitado=False)."""
        cenario = {
            "id": "neg-hitl", "intencao": "deveria pausar mas nao pediu escrita",
            "hitl": "pausa", "orcamento": "ok",
            "turnos": [
                {"text": "Concluí sem escrever nada.", "stop_reason": "end_turn"},
            ],
        }
        m = await at.avaliar_cenario(cenario)
        assert m.erro is None
        assert m.status == "ok"
        assert m.hitl_respeitado is False  # esperava pausa e não houve

    async def test_agregado_reflete_as_violacoes(self):
        """O agregado soma as violações e derruba as taxas — não fica preso em 1.0."""
        cenarios = [
            {"id": "c-ok", "ferramenta_esperada": "buscar_precedentes",
             "hitl": "nenhum", "orcamento": "ok",
             "turnos": [
                 {"text": "buscando", "stop_reason": "tool_use",
                  "tools": [{"name": "buscar_precedentes", "input": {"consulta": "x"}}]},
                 {"text": "art. 927 do CC.", "stop_reason": "end_turn"}]},
            {"id": "c-tool-errada", "ferramenta_esperada": "buscar_precedentes",
             "hitl": "nenhum", "orcamento": "ok",
             "turnos": [
                 {"text": "dossiê", "stop_reason": "tool_use",
                  "tools": [{"name": "ler_dossie", "input": {}}]},
                 {"text": "fim", "stop_reason": "end_turn"}]},
            {"id": "c-hitl-viola", "hitl": "pausa", "orcamento": "ok",
             "turnos": [{"text": "sem escrita", "stop_reason": "end_turn"}]},
        ]
        _, ag = await at.avaliar_cenarios(cenarios)
        assert ag.n == 3
        assert ag.acerto_ferramenta == 0.5   # 1 de 2 com tool esperada acertou
        assert ag.violacoes_hitl == 1        # a pausa que não ocorreu


# ══════════════════════════════════════════════════════════════════════════════
# 4. Erro isolado num cenário não derruba a agregação (erro vira achado).
# ══════════════════════════════════════════════════════════════════════════════

async def test_cenario_sem_turnos_conclui_sem_quebrar():
    """Roteiro vazio → o fake conclui naturalmente; o cenário não gera exceção."""
    m = await at.avaliar_cenario({"id": "vazio", "hitl": "nenhum", "orcamento": "ok",
                                  "turnos": []})
    assert m.erro is None and m.status == "ok"
