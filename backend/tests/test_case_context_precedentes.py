# ── tests/test_case_context_precedentes.py ────────────────────────────────────
# Cobertura dos módulos introduzidos nas Camadas 1-3:
#   - montar_dossie (app/services/case_context.py)
#   - ingestão de precedentes internos (app/services/ingestion_service.py)
#   - busca_contexto_rag com filtro de categoria (app/services/ai_service.py)
#
# Rodamos em SQLite in-memory (sem Postgres). Os operadores ILIKE e ANY() são
# incompatíveis com SQLite, por isso validamos a LÓGICA de estrutura e sanitização
# aqui, e o comportamento em Postgres real fica coberto por smoke_rag_producao.py.
from __future__ import annotations
import asyncio
import os
from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/x")
os.environ.setdefault("SECRET_KEY", "devdevdevdevdevdevdevdevdevdevdev")
os.environ.setdefault("EMBEDDINGS_ENABLED", "false")

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

@compiles(JSONB, "sqlite")
def _jsonb_sqlite(type_, compiler, **kw):   # noqa: D401
    """Compat: JSONB → JSON para SQLite."""
    return "JSON"

from app.core.database import Base
from app.models.case import Case, CaseMovimento
from app.models.client import Client
from app.models.deadline import Deadline
from app.models.fee import Fee
from app.models.especializado import BancarioCase, CivelCase
from app.services.pii_crypto import encrypt, hash_documento, normalizar_documento
from app.services.case_context import montar_dossie
from app.services.ingestion_service import upsert_documento

# ────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session():
    """Sessão SQLite in-memory — banco recriado a cada teste (isolamento total)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        import app.models  # registra todos os modelos no Base.metadata  # noqa
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def caso_bancario(db_session):
    """Caso bancário completo com cliente, satélite, prazo e honorário."""
    cid = str(uuid4())
    caseid = str(uuid4())
    cpf_normalizado = normalizar_documento("987.654.321-00")
    db_session.add(Client(
        id=cid, tipo="PF", nome="Maria Souza",
        cpf_enc=encrypt(cpf_normalizado), cpf_hash=hash_documento(cpf_normalizado),
        cidade="Betim", estado="MG", profissao="Autônoma", status="ativo",
    ))
    db_session.add(Case(
        id=caseid, numero_interno="DPT-TESTE-001",
        titulo="Souza x Banco — Busca e Apreensão",
        area="civil", status="ativo", fase="conhecimento", prioridade="alta",
        client_id=cid, parte_contraria="Banco Teste S.A.",
        valor_causa=25000,
        descricao_fatos="Cliente teve veículo apreendido.",
        tese_principal="Adimplemento substancial",
    ))
    db_session.add(BancarioCase(
        id=str(uuid4()), case_id=caseid, tipo="busca_apreensao",
        status="processual", instituicao_financeira="Banco Teste",
        valor_contratado=60000, bem_garantia="Toyota Corolla 2023",
    ))
    db_session.add(Deadline(
        id=str(uuid4()), titulo="Purga da mora", tipo="processual",
        prioridade="alta", status="pendente",
        data_prazo=date(2026, 7, 15),
        base_legal="Dec.-Lei 911/69 art. 3º §2",
        case_id=caseid,
    ))
    db_session.add(Fee(
        id=str(uuid4()), tipo="fixo", status="pendente",
        descricao="Honorários defesa BA",
        valor=5000, client_id=cid, case_id=caseid,
    ))
    db_session.add(CaseMovimento(
        id=str(uuid4()), case_id=caseid, tipo="intimacao",
        descricao="Cliente notificado da busca e apreensão.", created_by=None,
    ))
    await db_session.commit()
    return {"case_id": caseid, "client_id": cid}


# ────────────────────────────────────────────────────────────────────────────
# Testes: montar_dossie
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dossie_caso_inexistente_retorna_none(db_session):
    """montar_dossie com UUID inexistente → retorna None (não lança exceção)."""
    result = await montar_dossie(db_session, str(uuid4()))
    assert result is None


@pytest.mark.asyncio
async def test_dossie_estrutura_minima(db_session, caso_bancario):
    """Dossiê retorna as 3 chaves obrigatórias."""
    d = await montar_dossie(db_session, caso_bancario["case_id"])
    assert d is not None
    assert "texto" in d
    assert "meta" in d
    assert "nomes_proteger" in d


@pytest.mark.asyncio
async def test_dossie_numero_interno_presente(db_session, caso_bancario):
    """Número interno aparece no texto do dossiê."""
    d = await montar_dossie(db_session, caso_bancario["case_id"])
    assert "DPT-TESTE-001" in d["texto"]


@pytest.mark.asyncio
async def test_dossie_ramo_especializado_detectado(db_session, caso_bancario):
    """O ramo Bancário é detectado mesmo sem área própria no Case."""
    d = await montar_dossie(db_session, caso_bancario["case_id"])
    assert d["meta"]["tem_ramo_especializado"] is True
    assert "Bancário" in d["meta"]["area"]


@pytest.mark.asyncio
async def test_dossie_prazo_ativo_no_texto(db_session, caso_bancario):
    """Prazos ativos aparecem na seção [PRAZOS ATIVOS]."""
    d = await montar_dossie(db_session, caso_bancario["case_id"])
    assert "Purga da mora" in d["texto"]
    assert "PRAZOS ATIVOS" in d["texto"]


@pytest.mark.asyncio
async def test_dossie_honorario_no_texto(db_session, caso_bancario):
    """Honorários aparecem na seção [HONORÁRIOS]."""
    d = await montar_dossie(db_session, caso_bancario["case_id"])
    assert "HONORÁRIOS" in d["texto"]
    assert d["meta"]["qtd_honorarios"] == 1


@pytest.mark.asyncio
async def test_dossie_historico_no_texto(db_session, caso_bancario):
    """Movimentações aparecem na seção [HISTÓRICO RECENTE]."""
    d = await montar_dossie(db_session, caso_bancario["case_id"])
    assert "HISTÓRICO RECENTE" in d["texto"]
    assert "intimacao" in d["texto"]


# ────────────────────────────────────────────────────────────────────────────
# Testes: sanitização LGPD
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cpf_nao_vaza_no_dossie(db_session, caso_bancario):
    """CPF do cliente NÃO deve aparecer no texto sanitizado."""
    d = await montar_dossie(db_session, caso_bancario["case_id"], sanitizar=True)
    assert "987.654.321-00" not in d["texto"]


@pytest.mark.asyncio
async def test_nome_cliente_nao_vaza_no_dossie(db_session, caso_bancario):
    """Nome do cliente NÃO deve aparecer no texto sanitizado."""
    d = await montar_dossie(db_session, caso_bancario["case_id"], sanitizar=True)
    assert "Maria Souza" not in d["texto"]


@pytest.mark.asyncio
async def test_parte_contraria_mascarada(db_session, caso_bancario):
    """Razão social da parte contrária deve estar mascarada."""
    d = await montar_dossie(db_session, caso_bancario["case_id"], sanitizar=True)
    assert "Banco Teste S.A." not in d["texto"]


@pytest.mark.asyncio
async def test_sem_sanitizacao_parte_contraria_aparece(db_session, caso_bancario):
    """Com sanitizar=False, a parte contrária aparece em claro no texto.
    Com sanitizar=True (padrão), ela é mascarada pelo sanitizador."""
    # sanitizar=False → dados brutos
    d_bruto = await montar_dossie(db_session, caso_bancario["case_id"], sanitizar=False)
    assert "Banco Teste S.A." in d_bruto["texto"], "parte contrária deve aparecer no texto bruto"

    # sanitizar=True → parte contrária mascarada
    d_limpo = await montar_dossie(db_session, caso_bancario["case_id"], sanitizar=True)
    assert "Banco Teste S.A." not in d_limpo["texto"], "parte contrária deve ser mascarada"


@pytest_asyncio.fixture(scope="module")
def event_loop_policy():
    """Necessário para fixtures module-scope com pytest-asyncio."""
    import asyncio
    return asyncio.DefaultEventLoopPolicy()


CHAVE_PREC = "caso:case-prec-01"
CLIENTE_PREC = "client-prec-01"
CONTEUDO_V1 = "Adimplemento substancial afasta busca e apreensão. STJ REsp 1622555. " * 5
CONTEUDO_V2 = "NOVA VERSÃO: adimplemento substancial — jurisprudência consolidada. " * 5


# ────────────────────────────────────────────────────────────────────────────
# Testes: precedentes internos (Camada 3)
# Rodados num único teste sequencial para garantir a ordem: novo → inalterado →
# atualizado → verificar meta. Evita conflito de event loop entre fixtures de
# scope diferente no pytest-asyncio STRICT mode.
# ────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ciclo_completo_precedentes():
    """
    Ciclo completo de precedentes internos em banco isolado:
      1. Primeira ingestão → 'novo'
      2. Re-ingestão idêntica → 'inalterado' (dedup por hash)
      3. Conteúdo alterado → 'atualizado' (chunks substituídos)
      4. Campo extra (metadados) gravado corretamente
    """
    from sqlalchemy.dialects.postgresql import JSONB
    from sqlalchemy.ext.compiler import compiles as _compiles
    # Compat JSONB → JSON para este banco de teste
    try:
        @_compiles(JSONB, "sqlite")
        def _j(t, c, **k): return "JSON"
    except Exception:
        pass  # já registrado globalmente

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        import app.models  # noqa
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as db:
        # 1. NOVO
        r1 = await upsert_documento(
            db, titulo="Precedente Teste (exito)",
            categoria="precedente_interno", conteudo=CONTEUDO_V1,
            chave_origem=CHAVE_PREC, fonte=CHAVE_PREC,
            client_id=CLIENTE_PREC,
            embutir_vetores=False,
            extra={"area": "civil", "resultado": "exito"},
        )
        await db.commit()
        assert r1 == "novo", f"esperado 'novo', veio '{r1}'"

        # 2. INALTERADO (mesmo conteúdo = mesmo hash)
        r2 = await upsert_documento(
            db, titulo="Precedente Teste (exito)",
            categoria="precedente_interno", conteudo=CONTEUDO_V1,
            chave_origem=CHAVE_PREC, fonte=CHAVE_PREC,
            client_id=CLIENTE_PREC,
            embutir_vetores=False,
        )
        await db.commit()
        assert r2 == "inalterado", f"esperado 'inalterado', veio '{r2}'"

        # 3. ATUALIZADO (conteúdo diferente → chunks substituídos)
        r3 = await upsert_documento(
            db, titulo="Precedente Teste (exito) v2",
            categoria="precedente_interno", conteudo=CONTEUDO_V2,
            chave_origem=CHAVE_PREC, fonte=CHAVE_PREC,
            client_id=CLIENTE_PREC,
            embutir_vetores=False,
            extra={"area": "civil", "resultado": "exito"},
        )
        await db.commit()
        assert r3 == "atualizado", f"esperado 'atualizado', veio '{r3}'"

        # 4. META gravada
        from sqlalchemy import text
        import json
        row = (await db.execute(
            text("SELECT extra FROM knowledge_docs WHERE chave_origem = :k"),
            {"k": CHAVE_PREC},
        )).fetchone()
        assert row is not None, "knowledge_doc não encontrado após upsert"
        extra = json.loads(row[0]) if isinstance(row[0], str) else row[0]
        assert extra.get("area") == "civil", f"extra.area incorreto: {extra}"

    await engine.dispose()

@pytest.mark.asyncio
async def test_dossie_meta_campos(db_session, caso_bancario):
    """Meta do dossiê reporta contagens corretas."""
    d = await montar_dossie(db_session, caso_bancario["case_id"])
    assert d["meta"]["case_id"] == caso_bancario["case_id"]
    assert d["meta"]["qtd_prazos_ativos"] >= 1
    assert d["meta"]["qtd_honorarios"] >= 1
