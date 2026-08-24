"""Extensão do Banco de Teses (migração 148, PR 2 da série de consolidação).

Cobre fundamentações estruturadas, o grafo de relações entre teses (inclui
contratese/distinguishing), o vínculo com jurisprudência interna, a trilha
de evidência jurídica (`legal_evidence`) e o ciclo de validação — com o
gate anti-alucinação de `verificador_jurisprudencia` bloqueando promoção a
status de confiança quando há citação suspeita, conforme
`docs/decisoes/ADR_BANCO_TESES_CANONICO_2026-08-24.md`.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database import Base
from app.models.user import User, UserRole
from app.models.tese import Tese, TeseTipo, TeseStatus
from app.models.tese_extensoes import (
    TeseFundamentacao, TeseRelacao, TeseJurisprudenciaLink,
    TeseAlertaJurisprudencial, LegalEvidence,
)
from app.models.jurisprudencia_interna import JurisprudenciaInterna
from app.routers import teses as teses_router
from app.services.verificador_jurisprudencia import SUMULA_TETO

_TABELAS = [
    User.__table__, Tese.__table__, TeseFundamentacao.__table__,
    TeseRelacao.__table__, TeseJurisprudenciaLink.__table__,
    TeseAlertaJurisprudencial.__table__, LegalEvidence.__table__,
    JurisprudenciaInterna.__table__,
]


@pytest.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def _audit(*args, **kwargs):
        return None

    monkeypatch.setattr(teses_router, "criar_audit_log", _audit)

    async with maker() as session:
        yield session
    await engine.dispose()


def _user(role: UserRole) -> User:
    return User(
        id=str(uuid4()), email=f"{role.value}-{uuid4().hex[:6]}@teste.local",
        hashed_password="x", full_name=f"Usuário {role.value}",
        role=role, is_active=True,
    )


async def _nova_tese(db, **kwargs) -> Tese:
    t = Tese(
        id=str(uuid4()), titulo=kwargs.pop("titulo", "Tese de teste"),
        descricao=kwargs.pop("descricao", "Descrição de teste com mais de dez caracteres"),
        tipo=TeseTipo.escritorio, status=TeseStatus.ativa,
        **kwargs,
    )
    db.add(t)
    await db.commit()
    return t


# ── Fundamentações ────────────────────────────────────────────────────────────

async def test_criar_e_listar_fundamentacao(db):
    advogado = _user(UserRole.advogado)
    t = await _nova_tese(db)
    db.add(advogado)
    await db.commit()

    req = teses_router.FundamentacaoIn(norma="CDC", artigo="3", paragrafo="2",
                                        tipo="lei_federal", texto="...", interpretacao="...")
    criada = await teses_router.criar_fundamentacao(t.id, req, db=db, cu=advogado)
    assert criada["norma"] == "CDC"
    assert criada["artigo"] == "3"

    listadas = await teses_router.listar_fundamentacoes(t.id, db=db, cu=advogado)
    assert len(listadas) == 1
    assert listadas[0]["id"] == criada["id"]


async def test_fundamentacao_exige_permissao_de_edicao(db):
    estagiario = _user(UserRole.estagiario)
    t = await _nova_tese(db)
    db.add(estagiario)
    await db.commit()

    req = teses_router.FundamentacaoIn(norma="CDC")
    with pytest.raises(HTTPException) as exc:
        await teses_router.criar_fundamentacao(t.id, req, db=db, cu=estagiario)
    assert exc.value.status_code == 403


# ── Relações (grafo — inclui contratese) ─────────────────────────────────────

async def test_relacao_contradiz_aparece_em_saida_e_entrada(db):
    advogado = _user(UserRole.advogado)
    a = await _nova_tese(db, titulo="Tese A — ataque")
    b = await _nova_tese(db, titulo="Tese B — contratese")
    db.add(advogado)
    await db.commit()

    req = teses_router.RelacaoIn(tese_destino_id=b.id, tipo_relacao="contradiz",
                                   observacao="B é a contratese natural de A")
    await teses_router.criar_relacao(a.id, req, db=db, cu=advogado)

    saida_a = await teses_router.listar_relacoes(a.id, db=db, cu=advogado)
    assert len(saida_a["saida"]) == 1
    assert saida_a["saida"][0]["tipo_relacao"] == "contradiz"

    entrada_b = await teses_router.listar_relacoes(b.id, db=db, cu=advogado)
    assert len(entrada_b["entrada"]) == 1
    assert entrada_b["entrada"][0]["tese_origem_id"] == a.id


async def test_relacao_consigo_mesma_rejeitada(db):
    advogado = _user(UserRole.advogado)
    a = await _nova_tese(db)
    db.add(advogado)
    await db.commit()

    req = teses_router.RelacaoIn(tese_destino_id=a.id, tipo_relacao="apoia")
    with pytest.raises(HTTPException) as exc:
        await teses_router.criar_relacao(a.id, req, db=db, cu=advogado)
    assert exc.value.status_code == 422


async def test_relacao_duplicada_rejeitada_com_409(db):
    advogado = _user(UserRole.advogado)
    a = await _nova_tese(db)
    b = await _nova_tese(db)
    db.add(advogado)
    await db.commit()

    req = teses_router.RelacaoIn(tese_destino_id=b.id, tipo_relacao="apoia")
    await teses_router.criar_relacao(a.id, req, db=db, cu=advogado)
    with pytest.raises(HTTPException) as exc:
        await teses_router.criar_relacao(a.id, req, db=db, cu=advogado)
    assert exc.value.status_code == 409


async def test_relacao_tipo_invalido_rejeitada(db):
    advogado = _user(UserRole.advogado)
    a = await _nova_tese(db)
    b = await _nova_tese(db)
    db.add(advogado)
    await db.commit()

    req = teses_router.RelacaoIn(tese_destino_id=b.id, tipo_relacao="tipo-inexistente")
    with pytest.raises(HTTPException) as exc:
        await teses_router.criar_relacao(a.id, req, db=db, cu=advogado)
    assert exc.value.status_code == 422


# ── Vínculo com jurisprudência interna ───────────────────────────────────────

async def test_vincular_jurisprudencia_incrementa_vezes_citada(db):
    advogado = _user(UserRole.advogado)
    t = await _nova_tese(db)
    j = JurisprudenciaInterna(
        id=str(uuid4()), titulo="Súmula 297/STJ", ementa="CDC aplica-se a bancos.",
        tribunal="STJ", vezes_citada=0,
    )
    db.add_all([advogado, j])
    await db.commit()

    req = teses_router.JurisprudenciaLinkIn(jurisprudencia_id=j.id, tipo_relacao="favoravel")
    link = await teses_router.vincular_jurisprudencia(t.id, req, db=db, cu=advogado)
    assert link["tipo_relacao"] == "favoravel"

    await db.refresh(j)
    assert j.vezes_citada == 1

    vinculadas = await teses_router.listar_jurisprudencias_vinculadas(t.id, db=db, cu=advogado)
    assert len(vinculadas) == 1


async def test_vincular_jurisprudencia_inexistente_404(db):
    advogado = _user(UserRole.advogado)
    t = await _nova_tese(db)
    db.add(advogado)
    await db.commit()

    req = teses_router.JurisprudenciaLinkIn(jurisprudencia_id=str(uuid4()), tipo_relacao="favoravel")
    with pytest.raises(HTTPException) as exc:
        await teses_router.vincular_jurisprudencia(t.id, req, db=db, cu=advogado)
    assert exc.value.status_code == 404


# ── Evidência jurídica ────────────────────────────────────────────────────────

async def test_registrar_e_revisar_evidencia(db):
    advogado = _user(UserRole.advogado)
    t = await _nova_tese(db)
    db.add(advogado)
    await db.commit()

    req = teses_router.EvidenciaIn(
        tipo_fonte="sumula", tribunal="STJ", numero="297",
        url_oficial="https://scon.stj.jus.br/x", trecho_relevante="...",
    )
    e = await teses_router.registrar_evidencia(t.id, req, db=db, cu=advogado)
    assert e["status"] == "coletada"
    assert e["coletado_por"] == advogado.id

    revisada = await teses_router.revisar_evidencia(
        t.id, e["id"], novo_status="verificada", db=db, cu=advogado,
    )
    assert revisada["status"] == "verificada"
    assert revisada["revisado_por"] == advogado.id


async def test_revisar_evidencia_status_invalido(db):
    advogado = _user(UserRole.advogado)
    t = await _nova_tese(db)
    db.add(advogado)
    await db.commit()

    req = teses_router.EvidenciaIn(tipo_fonte="sumula")
    e = await teses_router.registrar_evidencia(t.id, req, db=db, cu=advogado)
    with pytest.raises(HTTPException) as exc:
        await teses_router.revisar_evidencia(
            t.id, e["id"], novo_status="inexistente", db=db, cu=advogado,
        )
    assert exc.value.status_code == 422


# ── Ciclo de validação ───────────────────────────────────────────────────────

async def test_transicao_valida_avanca_status_e_versao(db):
    advogado = _user(UserRole.advogado)
    t = await _nova_tese(db)
    db.add(advogado)
    await db.commit()
    assert t.status_validacao is None
    assert t.versao == 1

    req = teses_router.ValidacaoIn(novo_status="coletada")
    saida = await teses_router.transicionar_validacao(t.id, req, db=db, cu=advogado)
    assert saida["status_validacao"] == "coletada"
    assert saida["versao"] == 2
    assert saida["validada_por"] == advogado.id


async def test_transicao_pulando_estados_e_rejeitada(db):
    advogado = _user(UserRole.advogado)
    t = await _nova_tese(db, status_validacao="coletada")
    db.add(advogado)
    await db.commit()

    # coletada → validada não está em TRANSICOES_VALIDACAO["coletada"]
    req = teses_router.ValidacaoIn(novo_status="validada")
    with pytest.raises(HTTPException) as exc:
        await teses_router.transicionar_validacao(t.id, req, db=db, cu=advogado)
    assert exc.value.status_code in (403, 422)  # 403 primeiro: exige sócio


async def test_promover_a_validada_exige_socio(db):
    advogado = _user(UserRole.advogado)
    t = await _nova_tese(db, status_validacao="parcialmente_validada")
    db.add(advogado)
    await db.commit()

    req = teses_router.ValidacaoIn(novo_status="validada")
    with pytest.raises(HTTPException) as exc:
        await teses_router.transicionar_validacao(t.id, req, db=db, cu=advogado)
    assert exc.value.status_code == 403


async def test_promover_a_validada_bloqueada_por_citacao_suspeita(db):
    socio = _user(UserRole.socio)
    acima_do_teto = SUMULA_TETO["STJ"] + 100
    t = await _nova_tese(
        db, status_validacao="parcialmente_validada",
        fundamentacao=f"Nos termos da Súmula {acima_do_teto} do STJ.",
    )
    db.add(socio)
    await db.commit()

    req = teses_router.ValidacaoIn(novo_status="validada")
    with pytest.raises(HTTPException) as exc:
        await teses_router.transicionar_validacao(t.id, req, db=db, cu=socio)
    assert exc.value.status_code == 422
    assert "suspeita" in str(exc.value.detail).lower() or isinstance(exc.value.detail, dict)

    await db.refresh(t)
    assert t.status_validacao == "parcialmente_validada"  # não promovida


async def test_promover_a_validada_socio_com_conteudo_limpo(db):
    # Sem citação estruturada (artigo/súmula/processo) o verificador não
    # dispara nenhuma consulta ao RAG — o gate passa trivialmente. Citações
    # estruturadas em faixa válida exigem lookup em `knowledge_docs` com SQL
    # específico de Postgres (regex `~*`, `regexp_replace` com flag `g`),
    # fora do escopo deste teste em aiosqlite; cobertas em
    # tests/test_verificador_jurisprudencia.py.
    socio = _user(UserRole.socio)
    t = await _nova_tese(
        db, status_validacao="parcialmente_validada",
        fundamentacao="Fundamentação doutrinária sobre a aplicação do Código de "
                       "Defesa do Consumidor às relações bancárias.",
    )
    db.add(socio)
    await db.commit()

    req = teses_router.ValidacaoIn(novo_status="validada", observacao="Conferido contra fonte oficial")
    saida = await teses_router.transicionar_validacao(t.id, req, db=db, cu=socio)
    assert saida["status_validacao"] == "validada"
    assert saida["ultima_validacao_em"] is not None
