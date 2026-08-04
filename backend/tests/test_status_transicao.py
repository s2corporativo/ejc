"""Transições automáticas de estado do caso (Bloco 3 — unitário puro).

Decisão do titular (docs/DESENHO_BLOCO3_TELAS.md): as transições MOVEM
SOZINHAS, sempre para frente, nunca regridem, jamais tocam terminais, e cada
avanço registra CaseMovimento tipo "nota" na mesma transação do evento.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.case import Case, CaseMovimento, CaseStatus
from app.services.status_transicao import (
    STATUS_TERMINAIS,
    TRANSICOES_POR_EVENTO,
    avancar_status_por_evento,
)


class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)


def _caso(status) -> Case:
    return Case(id="k1", titulo="t", area="civil", status=status, client_id="c1")


# ── avanços válidos ──────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_documento_vinculado_avanca_aberto_para_em_instrucao():
    db, caso = _FakeDB(), _caso(CaseStatus.aberto)
    assert await avancar_status_por_evento(db, caso, "documento_vinculado", user_id="u1")
    assert caso.status == CaseStatus.em_instrucao
    movs = [o for o in db.added if isinstance(o, CaseMovimento)]
    assert len(movs) == 1
    assert movs[0].tipo == "nota"
    assert movs[0].case_id == "k1"
    assert movs[0].created_by == "u1"
    assert "em_instrucao" in movs[0].descricao
    assert "ajuste manual" in movs[0].descricao


@pytest.mark.anyio
async def test_peca_criada_avanca_aberto_e_em_instrucao():
    for origem in (CaseStatus.aberto, CaseStatus.em_instrucao):
        db, caso = _FakeDB(), _caso(origem)
        assert await avancar_status_por_evento(db, caso, "peca_criada")
        assert caso.status == CaseStatus.em_producao


@pytest.mark.anyio
async def test_peca_protocolada_avanca_os_tres_estados_de_trabalho():
    for origem in (CaseStatus.aberto, CaseStatus.em_instrucao, CaseStatus.em_producao):
        db, caso = _FakeDB(), _caso(origem)
        assert await avancar_status_por_evento(db, caso, "peca_protocolada")
        assert caso.status == CaseStatus.protocolado


@pytest.mark.anyio
async def test_status_string_tambem_avanca():
    # Fakes/dados antigos podem trazer o status como string crua.
    db, caso = _FakeDB(), _caso("aberto")
    assert await avancar_status_por_evento(db, caso, "documento_vinculado")
    assert caso.status == CaseStatus.em_instrucao


# ── nunca regride, nunca toca terminais ──────────────────────────────────────

@pytest.mark.anyio
async def test_nunca_regride():
    db, caso = _FakeDB(), _caso(CaseStatus.protocolado)
    assert not await avancar_status_por_evento(db, caso, "documento_vinculado")
    assert not await avancar_status_por_evento(db, caso, "peca_criada")
    assert caso.status == CaseStatus.protocolado
    assert db.added == []  # sem movimento espúrio

    db2, caso2 = _FakeDB(), _caso(CaseStatus.em_producao)
    assert not await avancar_status_por_evento(db2, caso2, "documento_vinculado")
    assert caso2.status == CaseStatus.em_producao


@pytest.mark.anyio
async def test_terminais_jamais_sao_tocados():
    for terminal in STATUS_TERMINAIS:
        for evento in TRANSICOES_POR_EVENTO:
            db, caso = _FakeDB(), _caso(terminal)
            assert not await avancar_status_por_evento(db, caso, evento)
            assert caso.status == terminal
            assert db.added == []


# ── entradas inválidas são inofensivas ───────────────────────────────────────

@pytest.mark.anyio
async def test_evento_desconhecido_caso_ausente_e_caso_excluido():
    db = _FakeDB()
    assert not await avancar_status_por_evento(db, _caso(CaseStatus.aberto), "evento_inexistente")
    assert not await avancar_status_por_evento(db, None, "documento_vinculado")
    excluido = _caso(CaseStatus.aberto)
    excluido.deleted_at = datetime.now(timezone.utc)
    assert not await avancar_status_por_evento(db, excluido, "documento_vinculado")
    assert excluido.status == CaseStatus.aberto
    assert db.added == []


@pytest.mark.anyio
async def test_status_invalido_nao_explode():
    db, caso = _FakeDB(), _caso("status_que_nao_existe")
    assert not await avancar_status_por_evento(db, caso, "documento_vinculado")
    assert db.added == []


def test_mapa_de_transicoes_cobre_o_desenho():
    # Guarda de regressão do contrato da seção 6 do desenho aprovado.
    assert set(TRANSICOES_POR_EVENTO) == {
        "documento_vinculado", "peca_criada", "peca_protocolada",
    }
    assert TRANSICOES_POR_EVENTO["documento_vinculado"][1] == CaseStatus.em_instrucao
    assert TRANSICOES_POR_EVENTO["peca_criada"][1] == CaseStatus.em_producao
    assert TRANSICOES_POR_EVENTO["peca_protocolada"][1] == CaseStatus.protocolado
    assert STATUS_TERMINAIS == frozenset({CaseStatus.encerrado, CaseStatus.arquivado})


def test_pontos_de_chamada_registrados():
    """Os três fluxos existentes chamam a variante fail-safe APÓS o commit da
    operação principal (falha na transição nunca desfaz a operação)."""
    import inspect

    from app.routers import documents, legal_docs

    assert "avancar_status_pos_commit" in inspect.getsource(documents.upload)
    assert "peca_criada" in inspect.getsource(legal_docs.criar)
    assert "peca_protocolada" in inspect.getsource(legal_docs.registrar_protocolo)
