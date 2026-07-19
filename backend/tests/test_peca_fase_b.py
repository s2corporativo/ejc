"""Fase B do gerador de peças: (#3) versões por complexidade e (#2) blocos
condicionais de teses.

Padrão dos testes de IA do projeto (sem Postgres/IA real): dicionários/funções
puras testados diretamente; handler REAL exercitado com dependências
monkeypatched e a IA (gerar_peca_pipeline) substituída por um recorder que
captura os kwargs — assim validamos a derivação de flags e a propagação do nível
SEM chamar modelo.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.models.user import UserRole
from app.routers import peca_geracao as pg
from app.routers.peca_geracao import GerarPecaRequest
from app.services.peca_service import NIVEIS_COMPLEXIDADE, PERFIL_COMPLEXIDADE
from app.services.system_prompts.blocos_condicionais import (
    BLOCOS,
    FLAGS_VALIDAS,
    REGRA_ANTI_FRANKENSTEIN,
    detectar_conflitos,
    montar_instrucao_blocos,
)


# ── #3 — PERFIL_COMPLEXIDADE (dict puro, sem IA) ──────────────────────────────

def test_perfil_cobre_exatamente_os_niveis():
    assert set(PERFIL_COMPLEXIDADE) == set(NIVEIS_COMPLEXIDADE)


def test_perfil_cada_nivel_tem_contrato_completo():
    for nivel, perfil in PERFIL_COMPLEXIDADE.items():
        assert perfil["instrucao"].strip(), nivel
        assert isinstance(perfil["max_tokens"], int) and perfil["max_tokens"] > 0
        assert 0.0 <= perfil["temperature"] <= 1.0


def test_perfil_ritos_curtos_usam_menos_tokens_que_comum():
    comum = PERFIL_COMPLEXIDADE["comum"]["max_tokens"]
    assert PERFIL_COMPLEXIDADE["simples"]["max_tokens"] < comum
    assert PERFIL_COMPLEXIDADE["juizado_especial"]["max_tokens"] < comum
    # Estratégica acomoda teses subsidiárias + análise de risco → teto >= comum.
    assert PERFIL_COMPLEXIDADE["estrategica"]["max_tokens"] >= comum


def test_perfil_instrucoes_sao_distintas_por_nivel():
    instrucoes = {p["instrucao"] for p in PERFIL_COMPLEXIDADE.values()}
    # comum e completa podem ter teto igual, mas cada nível carrega texto próprio.
    assert len(instrucoes) == len(PERFIL_COMPLEXIDADE)


def test_juizado_menciona_lei_9099():
    assert "9.099" in PERFIL_COMPLEXIDADE["juizado_especial"]["instrucao"]


# ── #2 — montar_instrucao_blocos / catálogo (funções puras) ───────────────────

def test_flags_validas_bate_com_catalogo():
    assert FLAGS_VALIDAS == frozenset(BLOCOS)
    assert FLAGS_VALIDAS == {
        "dano_moral", "relacao_consumo", "hipossuficiencia",
        "prova_documental_suficiente", "pedido_tutela",
    }


def test_blocos_flags_conhecidas_geram_texto_e_anti_frankenstein():
    txt = montar_instrucao_blocos({"dano_moral", "pedido_tutela"})
    assert "Dano moral" in txt
    assert "Tutela de urgência" in txt
    assert REGRA_ANTI_FRANKENSTEIN in txt


def test_blocos_flags_desconhecidas_sao_ignoradas():
    # Só a conhecida entra; a desconhecida não gera linha nem quebra.
    txt = montar_instrucao_blocos({"relacao_consumo", "flag_inexistente"})
    assert "Relação de consumo" in txt
    assert "flag_inexistente" not in txt


def test_blocos_sem_flag_conhecida_retorna_vazio():
    assert montar_instrucao_blocos(set()) == ""
    assert montar_instrucao_blocos({"xpto", "nada"}) == ""


def test_blocos_anti_frankenstein_sempre_presente_com_qualquer_tese():
    for flag in FLAGS_VALIDAS:
        assert REGRA_ANTI_FRANKENSTEIN in montar_instrucao_blocos({flag})


def test_blocos_ordem_estavel_independe_da_ordem_de_entrada():
    a = montar_instrucao_blocos(["pedido_tutela", "dano_moral"])
    b = montar_instrucao_blocos(["dano_moral", "pedido_tutela"])
    assert a == b


def test_incompatibilidade_sinalizada():
    # Mecanismo de conflito exercitado com catálogo custom (o catálogo real desta
    # fase declara listas vazias — não há impedimento rígido entre as 5 flags).
    catalogo = {
        "a": {"rotulo": "Tese A", "instrucao": "...", "incompativel_com": ["b"]},
        "b": {"rotulo": "Tese B", "instrucao": "...", "incompativel_com": ["a"]},
        "c": {"rotulo": "Tese C", "instrucao": "...", "incompativel_com": []},
    }
    assert detectar_conflitos({"a", "b"}, catalogo) == [("a", "b")]
    assert detectar_conflitos({"a", "c"}, catalogo) == []
    txt = montar_instrucao_blocos({"a", "b"}, catalogo)
    assert "incompatíveis" in txt
    assert "Tese A" in txt and "Tese B" in txt


def test_conflito_unilateral_tambem_detectado():
    catalogo = {
        "a": {"rotulo": "A", "instrucao": "...", "incompativel_com": ["b"]},
        "b": {"rotulo": "B", "instrucao": "...", "incompativel_com": []},
    }
    assert detectar_conflitos({"a", "b"}, catalogo) == [("a", "b")]


# ── #2 — derivação determinística de flags no handler REAL ────────────────────

def _user(role: UserRole = UserRole.advogado):
    return SimpleNamespace(id="u1", role=role, full_name="Adv Teste")


def _req(**over):
    base = dict(
        tipo_peca="peticao_inicial",
        area_direito="civil",
        descricao_fatos="F" * 60,
        pedidos="P" * 20,
    )
    base.update(over)
    return GerarPecaRequest(**base)


@pytest.fixture
def recorder(monkeypatch):
    """Substitui a IA e as dependências de caso; captura os kwargs do pipeline."""
    captured: dict = {}

    async def fake_pipeline(**kwargs):
        captured.update(kwargs)
        yield "event: fim\ndata: {}\n\n"

    async def fake_estilo(db, uid):
        return ""

    monkeypatch.setattr(pg, "gerar_peca_pipeline", fake_pipeline)
    monkeypatch.setattr(pg, "montar_instrucoes_estilo_para_prompt", fake_estilo)
    return captured


async def _rodar(handler_req, recorder, db=None):
    """Executa o handler e consome o StreamingResponse (dispara o stream())."""
    resp = await pg.gerar_peca(handler_req, db=db, cu=_user())
    async for _ in resp.body_iterator:
        pass
    return recorder


async def test_area_consumidor_deriva_relacao_consumo(recorder):
    # Avulsa (sem case_id): só área + manuais valem — não quebra.
    await _rodar(_req(area_direito="consumidor"), recorder)
    instr = recorder["instrucoes_adicionais"]
    assert "Relação de consumo" in instr
    assert REGRA_ANTI_FRANKENSTEIN in instr


async def test_area_nao_consumidor_nao_deriva_relacao_consumo(recorder):
    await _rodar(_req(area_direito="civil"), recorder)
    assert "Relação de consumo" not in recorder["instrucoes_adicionais"]


async def test_flags_manuais_unem_com_deterministicas(recorder):
    # consumidor (determinística) + dano_moral (manual) + desconhecida (ignorada).
    await _rodar(
        _req(area_direito="consumidor", flags_teses=["dano_moral", "zzz_nao_existe"]),
        recorder,
    )
    instr = recorder["instrucoes_adicionais"]
    assert "Relação de consumo" in instr
    assert "Dano moral" in instr
    assert "zzz_nao_existe" not in instr


async def test_ficha_com_tutela_e_provas_deriva_flags(monkeypatch, recorder):
    ficha = SimpleNamespace(
        status="confirmada", tutela_urgencia=True,
        provas_disponiveis="Contrato assinado; e-mails",
    )

    async def fake_acesso(db, cu, cid):
        return None

    async def fake_escopo(db, cid):
        return None

    async def fake_confirmada(db, cid):
        return ficha

    monkeypatch.setattr(pg, "verificar_acesso_caso", fake_acesso)
    monkeypatch.setattr(
        "app.services.ai_service._escopo_cliente_do_caso", fake_escopo
    )
    monkeypatch.setattr(
        "app.services.ficha_triagem_service.ficha_confirmada", fake_confirmada
    )
    monkeypatch.setattr(
        "app.services.ficha_triagem_service.resumo_para_prompt", lambda f: ""
    )

    await _rodar(_req(area_direito="civil", case_id="c1"), recorder)
    instr = recorder["instrucoes_adicionais"]
    assert "Tutela de urgência" in instr           # de ficha.tutela_urgencia
    assert "Prova documental suficiente" in instr  # de ficha.provas_disponiveis


async def test_ficha_sem_tutela_nem_provas_nao_deriva(monkeypatch, recorder):
    ficha = SimpleNamespace(
        status="confirmada", tutela_urgencia=False, provas_disponiveis="",
    )
    monkeypatch.setattr(pg, "verificar_acesso_caso", lambda *a, **k: _noop())
    monkeypatch.setattr(
        "app.services.ai_service._escopo_cliente_do_caso", lambda *a, **k: _noop()
    )
    monkeypatch.setattr(
        "app.services.ficha_triagem_service.ficha_confirmada",
        lambda *a, **k: _noret(ficha),
    )
    monkeypatch.setattr(
        "app.services.ficha_triagem_service.resumo_para_prompt", lambda f: ""
    )
    await _rodar(_req(area_direito="civil", case_id="c1"), recorder)
    instr = recorder["instrucoes_adicionais"] or ""
    assert "Tutela de urgência" not in instr
    assert "Prova documental suficiente" not in instr


async def _noop():
    return None


async def _noret(v):
    return v


# ── #3 — nível de complexidade no handler ─────────────────────────────────────

async def test_nivel_invalido_retorna_422(recorder):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        await pg.gerar_peca(_req(nivel_complexidade="turbo"), db=None, cu=_user())
    assert ei.value.status_code == 422


async def test_nivel_valido_propaga_ao_pipeline(recorder):
    await _rodar(_req(nivel_complexidade="estrategica"), recorder)
    assert recorder["nivel_complexidade"] == "estrategica"


async def test_nivel_default_comum(recorder):
    await _rodar(_req(), recorder)
    assert recorder["nivel_complexidade"] == "comum"
