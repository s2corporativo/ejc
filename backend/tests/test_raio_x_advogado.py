"""Análise "ADVOGADO SÊNIOR" do Raio-X (services/raio_x_advogado_service.py).

Tudo mockado — nenhum teste toca rede/DB/Redis. Mocka `rodar_agente` e
`verificar_acesso_caso` no nível do módulo do serviço (as bordas externas), e o
bloco de estilo do escritório. Cobre:
  (a) a instrução ao agente traz o método FIRAC + o bloco de estilo;
  (b) o fluxo é SOMENTE LEITURA (apenas_leitura=True) — nenhuma tool de escrita;
  (c) com AI_AGENT_ENABLED=False → status "indisponivel" (não quebra);
  (d) `base_relatorio` é injetado na instrução quando fornecido;
  (e) a resposta marca is_rascunho=True.

Estilo herdado de test_agente_ia.py: settings via monkeypatch na instância
cacheada de get_settings(); dados FICTÍCIOS.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.config import get_settings
from app.services import raio_x_advogado_service as svc

ESTILO_SENTINELA = "[[ESTILO_ESCRITORIO_SENTINELA]]"


def _user():
    return SimpleNamespace(id="u1", role=SimpleNamespace(value="advogado"))


def _caso():
    return SimpleNamespace(
        id="c1", titulo="Ação de cobrança fictícia",
        area=SimpleNamespace(value="civil"), client_id="cli1",
    )


@pytest.fixture
def env(monkeypatch):
    """Baseline: AI_AGENT_ENABLED ligado, Duas IAs desligado (sem rede), e as
    bordas externas do serviço mockadas. `capturado` guarda os kwargs de
    rodar_agente para as asserções sobre a instrução/flags."""
    st = get_settings()
    monkeypatch.setattr(st, "AI_AGENT_ENABLED", True, raising=False)
    monkeypatch.setattr(st, "DUAS_IAS_ENABLED", False, raising=False)

    capturado: dict = {}

    async def fake_acesso(db, user, case_id):
        return _caso()

    async def fake_estilo(db, user_id):
        return ESTILO_SENTINELA

    async def fake_rodar_agente(**kwargs):
        capturado.update(kwargs)
        return {
            "status": "ok",
            "resposta": "Parecer estruturado (rascunho).",
            "is_rascunho": True,
            "passos": [{"passo": 1}],
            "custo_estimado_brl": 0.12,
            "alertas": [],
            "revisao_obrigatoria": False,
        }

    monkeypatch.setattr(svc, "verificar_acesso_caso", fake_acesso)
    monkeypatch.setattr(svc, "montar_instrucoes_estilo_para_prompt", fake_estilo)
    monkeypatch.setattr(svc, "rodar_agente", fake_rodar_agente)

    return SimpleNamespace(st=st, capturado=capturado, monkeypatch=monkeypatch)


class TestAnaliseAdvogado:
    async def test_instrucao_tem_firac_e_estilo(self, env):
        """(a) A mensagem enviada ao agente usa o método FIRAC e inclui o bloco de
        estilo do escritório."""
        r = await svc.analise_advogado_caso(db=None, user=_user(), case_id="c1")
        assert r["status"] == "ok"
        msg = env.capturado["mensagem"]
        assert "FIRAC" in msg
        assert ESTILO_SENTINELA in msg
        # Reforço das vedações OAB na própria instrução.
        assert "REVISÃO HUMANA" in msg.upper()

    async def test_fluxo_somente_leitura(self, env):
        """(b) O agente roda em modo SOMENTE LEITURA — nenhuma tool de escrita
        (não pode pausar em HITL)."""
        await svc.analise_advogado_caso(db=None, user=_user(), case_id="c1")
        assert env.capturado["apenas_leitura"] is True
        # Sanidade: o serviço passa mensagem e case_id ao agente.
        assert env.capturado["case_id"] == "c1"
        assert env.capturado["mensagem"]

    async def test_flag_off_indisponivel(self, env):
        """(c) Com AI_AGENT_ENABLED=False, retorna 'indisponivel' sem chamar o
        agente nem o gate de ownership."""
        env.monkeypatch.setattr(env.st, "AI_AGENT_ENABLED", False, raising=False)

        chamou = {"acesso": 0, "agente": 0}

        async def espia_acesso(db, user, case_id):
            chamou["acesso"] += 1
            return _caso()

        async def espia_agente(**kwargs):
            chamou["agente"] += 1
            return {"status": "ok", "resposta": "x", "is_rascunho": True}

        env.monkeypatch.setattr(svc, "verificar_acesso_caso", espia_acesso)
        env.monkeypatch.setattr(svc, "rodar_agente", espia_agente)

        r = await svc.analise_advogado_caso(db=None, user=_user(), case_id="c1")
        assert r == {"status": "indisponivel",
                     "detalhe": "analise_advogado_requer_AI_AGENT_ENABLED"}
        assert chamou == {"acesso": 0, "agente": 0}  # gate ANTES de qualquer IA

    async def test_base_relatorio_injetado(self, env):
        """(d) Quando `base_relatorio` é fornecido (fluxo por documentos), ele é
        injetado na instrução como contexto; sem ele, não aparece."""
        marcador = "MARCADOR_RELATORIO_XYZ"
        base = {"sintese_executiva": marcador, "risco_nivel": "elevado"}
        await svc.analise_advogado_caso(
            db=None, user=_user(), case_id="c1", base_relatorio=base)
        msg_com = env.capturado["mensagem"]
        assert marcador in msg_com
        assert "RELATÓRIO CONSOLIDADO DO RAIO-X" in msg_com

        # Sem base_relatorio o marcador não aparece.
        env.capturado.clear()
        await svc.analise_advogado_caso(db=None, user=_user(), case_id="c1")
        assert marcador not in env.capturado["mensagem"]

    async def test_resposta_marca_rascunho(self, env):
        """(e) A resposta é sempre rascunho (revisão humana obrigatória)."""
        r = await svc.analise_advogado_caso(db=None, user=_user(), case_id="c1")
        assert r["status"] == "ok"
        assert r["is_rascunho"] is True
        assert r["analise"] == "Parecer estruturado (rascunho)."
        assert r["custo_estimado_brl"] == 0.12
        # Sem Duas IAs, não há crítica anexada.
        assert r["critica_adversarial"] is None

    async def test_status_erro_do_agente_e_propagado(self, env):
        """Fail-safe: se o agente falhar (ex.: caso sigiloso exige IA local), o
        serviço propaga o status sem quebrar."""
        async def agente_erro(**kwargs):
            return {"status": "erro", "detalhe": "caso_sigiloso_exige_ia_local"}

        env.monkeypatch.setattr(svc, "rodar_agente", agente_erro)
        r = await svc.analise_advogado_caso(db=None, user=_user(), case_id="c1")
        assert r["status"] == "erro"
        assert r["detalhe"] == "caso_sigiloso_exige_ia_local"
        assert r["is_rascunho"] is True


class TestCriticaAdversarialOpcional:
    async def test_duas_ias_ligado_anexa_critica(self, env):
        """Com DUAS_IAS_ENABLED, roda a crítica adversarial e ANEXA a nota de
        robustez — sem jamais bloquear a entrega."""
        env.monkeypatch.setattr(env.st, "DUAS_IAS_ENABLED", True, raising=False)

        async def fake_critica(db, **kwargs):
            return SimpleNamespace(
                disponivel=True, nota_robustez=82,
                relatorio="Crítica fictícia.", alertas=[], aviso="rascunho",
            )

        env.monkeypatch.setattr(svc, "criticar_peca", fake_critica)
        r = await svc.analise_advogado_caso(db=None, user=_user(), case_id="c1")
        assert r["status"] == "ok"
        assert r["critica_adversarial"]["disponivel"] is True
        assert r["critica_adversarial"]["nota_robustez"] == 82

    async def test_falha_da_critica_nao_bloqueia(self, env):
        """Exceção na crítica não derruba a análise (crítica é apoio, não gate)."""
        env.monkeypatch.setattr(env.st, "DUAS_IAS_ENABLED", True, raising=False)

        async def critica_boom(db, **kwargs):
            raise RuntimeError("provedor da crítica fora do ar")

        env.monkeypatch.setattr(svc, "criticar_peca", critica_boom)
        r = await svc.analise_advogado_caso(db=None, user=_user(), case_id="c1")
        assert r["status"] == "ok"                 # análise entregue mesmo assim
        assert r["critica_adversarial"] is None
