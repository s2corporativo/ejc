"""#1466 (P0): falha da memória institucional não pode quebrar o encerramento.

O passo RAG do `POST /cases/{id}/encerrar` é ACESSÓRIO: dossiê/embedding/upsert
podem falhar (provedor fora, categoria restrita, savepoint) sem transformar um
encerramento juridicamente válido em HTTP 500. O upsert recebe escopo explícito
do caso canônico (client_id/case_id) e roda em SAVEPOINT; qualquer exceção é
contida e a transação principal (status + movimento + auditoria) commita.

Padrão dos vizinhos: aiosqlite em memória + fakes para o que é Postgres-only
(advisory lock, AuditLog/JSONB). Handler real, sem mock de `encerrar_caso`.
"""
from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.background import BackgroundTasks

from app.core.database import Base
from app.models.case import Case, CaseArea, CaseMovimento, CaseStatus
from app.models.client import Client, ClientTipo
from app.models.user import User, UserRole
from app.routers import cases as cases_router
from app.services import case_closure_service

_TABELAS = [
    User.__table__, Client.__table__, Case.__table__, CaseMovimento.__table__,
]


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABELAS))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def fakes(monkeypatch):
    async def _fake_audit(db, user_id, user_role, acao, entidade, registro_id=None,
                          detalhes=None, **kw):
        return None

    async def _sem_lock(db, case_id):
        return None

    async def _dossie_ok(db, case_id, incluir_pecas=True, sanitizar=True):
        return {"texto": "DOSSIÊ SANITIZADO DE TESTE"}

    async def _diagnostico_limpo(db, case, somente_leitura=False):
        del db, somente_leitura
        return {
            "bloqueios": [],
            "alertas": [],
            "processo": None,
            "resumo": {"case_id": case.id, "apto": True},
        }

    monkeypatch.setattr(cases_router, "criar_audit_log", _fake_audit)
    monkeypatch.setattr(case_closure_service, "serializar_mutacao_caso", _sem_lock)
    monkeypatch.setattr(case_closure_service, "diagnosticar_fechamento", _diagnostico_limpo)

    from app.services import case_context
    monkeypatch.setattr(case_context, "montar_dossie", _dossie_ok)


def _socio() -> User:
    return User(id="u-socio-1466", email="socio1466@teste.adv.br",
                hashed_password="h", full_name="Sócio Teste",
                role=UserRole.socio, is_active=True)


def _cliente(responsavel_id: str) -> Client:
    return Client(id=str(uuid4()), tipo=ClientTipo.PF, nome="Cliente Teste",
                  profissao="professora", logradouro="Rua A", numero="10",
                  bairro="Centro", cidade="Betim", estado="MG", cep="32600-000",
                  area_interesse="civil", responsavel_id=responsavel_id)


def _caso(client_id: str, responsavel_id: str) -> Case:
    return Case(id="caso-1466", numero_interno="DPT-2026-1466", titulo="Cobrança",
                area=CaseArea.civil, status=CaseStatus.em_instrucao,
                client_id=client_id, advogado_responsavel_id=responsavel_id)


def _payload(**extra) -> cases_router.EncerrarCasoReq:
    base = dict(
        resultado="acordo",
        motivo_resultado="Acordo homologado com quitação integral das partes",
        provas_determinantes="Contrato e comprovantes de pagamento",
        licoes_aprendidas="Documentar cedo a negociação evita retrabalho",
        alimentar_rag=True,
        confirmar_alertas=True,
    )
    base.update(extra)
    return cases_router.EncerrarCasoReq(**base)


@pytest.mark.asyncio
async def test_encerramento_sobrevive_a_falha_do_rag(db, fakes, monkeypatch):
    """upsert explode (ex.: embedding fora) → sem 500; caso encerra e commita."""
    from app.services import ingestion_service

    socio = _socio()
    cli = _cliente(socio.id)
    caso = _caso(cli.id, socio.id)
    db.add_all([socio, cli, caso])
    await db.commit()

    async def _upsert_quebrado(db, **kwargs):
        raise RuntimeError("provedor de embedding indisponível")

    monkeypatch.setattr(ingestion_service, "upsert_documento", _upsert_quebrado)

    resp = await cases_router.encerrar_caso(
        caso.id, _payload(), BackgroundTasks(), None, db, socio,
    )
    assert "encerrado" in resp["detail"].lower()
    assert resp["memoria_institucional"]["precedente_rag"] == "falha_acessoria"
    assert resp["memoria_institucional"]["aprendizado_assincrono"] == "enfileirado"
    await db.refresh(caso)
    assert caso.status == CaseStatus.encerrado


@pytest.mark.asyncio
async def test_encerramento_passa_escopo_explicito_ao_rag(db, fakes, monkeypatch):
    """Caminho feliz: precedente nasce escopado ao cliente/caso (sem global)."""
    from app.services import ingestion_service

    socio = _socio()
    cli = _cliente(socio.id)
    caso = _caso(cli.id, socio.id)
    db.add_all([socio, cli, caso])
    await db.commit()

    chamadas: list[dict] = []

    async def _upsert_ok(db, **kwargs):
        chamadas.append(kwargs)
        return "novo"

    monkeypatch.setattr(ingestion_service, "upsert_documento", _upsert_ok)

    resp = await cases_router.encerrar_caso(
        caso.id, _payload(), BackgroundTasks(), None, db, socio,
    )
    assert "encerrado" in resp["detail"].lower()
    assert resp["memoria_institucional"]["precedente_rag"] == "registrado"
    assert resp["memoria_institucional"]["aprendizado_assincrono"] == "enfileirado"
    assert len(chamadas) == 1
    kwargs = chamadas[0]
    assert kwargs["categoria"] == "precedente_interno"
    assert kwargs["client_id"] == cli.id
    assert kwargs["case_id"] == caso.id
    assert kwargs["chave_origem"] == f"caso:{caso.id}"


@pytest.mark.asyncio
async def test_encerramento_sobrevive_a_falha_do_dossie(db, fakes, monkeypatch, caplog):
    """Falha no dossiê também fica contida pelo SAVEPOINT acessório."""
    from app.services import case_context

    socio = _socio()
    cli = _cliente(socio.id)
    caso = _caso(cli.id, socio.id)
    db.add_all([socio, cli, caso])
    await db.commit()

    marcador = "PII-SINTETICA-NAO-DEVE-IR-AO-LOG"

    async def _dossie_quebrado(*args, **kwargs):
        del args, kwargs
        raise RuntimeError(marcador)

    monkeypatch.setattr(case_context, "montar_dossie", _dossie_quebrado)

    with caplog.at_level("WARNING"):
        resp = await cases_router.encerrar_caso(
            caso.id, _payload(), BackgroundTasks(), None, db, socio
        )

    assert "encerrado" in resp["detail"].lower()
    assert resp["memoria_institucional"]["precedente_rag"] == "falha_acessoria"
    await db.refresh(caso)
    assert caso.status == CaseStatus.encerrado
    assert "RuntimeError" in caplog.text
    assert marcador not in caplog.text
    assert caso.id not in caplog.text


def test_dossie_e_upsert_compartilham_um_unico_savepoint():
    """Evita dupla contenção e garante que leitura do dossiê também é isolada."""
    import inspect

    fonte = inspect.getsource(cases_router.encerrar_caso)
    inicio = fonte.index("async with db.begin_nested():")
    pos_dossie = fonte.index("dossie = await montar_dossie")
    pos_upsert = fonte.index("await upsert_documento")

    assert fonte.count("async with db.begin_nested():") == 1
    assert inicio < pos_dossie < pos_upsert
