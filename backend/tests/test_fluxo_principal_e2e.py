"""Fluxo principal do EJC, de ponta a ponta, sem Postgres.

CLIENTE → CONTRATAÇÃO (contrato + procuração pelo kit de admissão, com modelo
por área do módulo Templates) → CASO → FINANCEIRO → PROCESSO → SINCRONIZAR
(idempotente) → ENCERRAR (diagnóstico: bloqueio, alerta, justificativa) →
REABRIR. Padrão dos vizinhos: aiosqlite em memória + fakes para o que é
Postgres-only (advisory lock, AuditLog/JSONB, DataJud).
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.background import BackgroundTasks

from app.core.database import Base
from app.models.case import Case, CaseArea, CaseMovimento, CaseStatus
from app.models.client import Client, ClientTipo
from app.models.deadline import Deadline, DeadlineStatus
from app.models.fee import Fee, FeeStatus
from app.models.legal_doc import LegalDoc, PecaTipo
from app.models.process import Process
from app.models.redesign import TabelaOABHonorario
from app.models.task import Task
from app.models.template import DocTemplate
from app.models.user import User, UserRole
from app.routers import cases as cases_router
from app.services import case_closure_service, datajud_service
from app.services import geracao_documental_cliente as gdc

_TABELAS = [
    User.__table__, Client.__table__, Case.__table__, CaseMovimento.__table__,
    LegalDoc.__table__, DocTemplate.__table__, TabelaOABHonorario.__table__,
    Process.__table__, Deadline.__table__, Task.__table__, Fee.__table__,
]

CNJ = "0001234-56.2026.8.13.0027"


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
def auditoria(monkeypatch):
    """AuditLog é JSONB (Postgres-only): coletor em memória, na mesma transação."""
    registros: list[dict] = []

    async def _fake(db, user_id, user_role, acao, entidade, registro_id=None,
                    detalhes=None, **kw):
        registros.append({"acao": acao, "entidade": entidade, "id": registro_id,
                          "detalhes": detalhes, **kw})

    monkeypatch.setattr(gdc, "criar_audit_log", _fake)
    monkeypatch.setattr(cases_router, "criar_audit_log", _fake)

    async def _sem_lock(db, case_id):  # pg_advisory_xact_lock é Postgres-only
        return None

    monkeypatch.setattr(case_closure_service, "serializar_mutacao_caso", _sem_lock)
    return registros


def _socio() -> User:
    return User(id="u-socio", email="socio@teste.adv.br", hashed_password="h",
                full_name="Dra. Sócia Teste", role=UserRole.socio, is_active=True)


def _cliente(responsavel_id: str) -> Client:
    c = Client(id=str(uuid4()), tipo=ClientTipo.PF, nome="Maria Cliente",
               profissao="professora", logradouro="Rua A", numero="10",
               bairro="Centro", cidade="Betim", estado="MG", cep="32600-000",
               area_interesse="civil", responsavel_id=responsavel_id)
    return c


def _payload_encerrar(**extra) -> cases_router.EncerrarCasoReq:
    base = dict(
        resultado="acordo",
        motivo_resultado="Acordo homologado com quitação integral das partes",
        provas_determinantes="Contrato e comprovantes de pagamento",
        licoes_aprendidas="Documentar cedo a negociação evita retrabalho",
        alimentar_rag=False,
    )
    base.update(extra)
    return cases_router.EncerrarCasoReq(**base)


@pytest.mark.asyncio
async def test_fluxo_principal_ponta_a_ponta(db, auditoria, monkeypatch):
    socio = _socio()
    cli = _cliente(socio.id)
    db.add_all([socio, cli])
    # Modelo de contrato POR ÁREA no módulo Templates: o kit deve usá-lo, com
    # os dados do cliente e do escritório vindo do cadastro/configuração.
    db.add(DocTemplate(
        id="tpl-civil", titulo="Contrato cível padrão", tipo_peca="contrato",
        area="civil", ativo=True,
        conteudo=("CONTRATO — {{escritorio_nome}} (OAB {{escritorio_oab}})\n"
                  "CONTRATANTE: {{cliente_qualificacao}}\nÁrea: {{area}}\n"
                  "Advogado: {{advogado_nome}}\n{{escritorio_cidade}}, {{data_hoje}}"),
    ))
    await db.commit()

    # ── 1) CONTRATAÇÃO: contrato + procuração vinculados ao cliente (FK) ──────
    kit = await gdc.gerar_documentos_cliente(db, cli, socio)
    assert kit["ja_existia"] is False and kit["status"] == "rascunho"
    assert kit["contrato"]["modelo"]["id"] == "tpl-civil"
    assert kit["procuracao"]["modelo"] is None  # sem modelo → texto do escritório
    contrato = kit["contrato"]["conteudo"]
    assert "De Paula Teixeira" in contrato and "251.174" in contrato
    assert "Maria Cliente" in contrato and "Rua A" in contrato
    assert "[cliente_qualificacao?]" not in contrato  # variável nova resolvida
    assert "JOÃO PEDRO RODRIGUES TEIXEIRA" in kit["procuracao"]["conteudo"]
    docs = (await db.execute(select(LegalDoc).where(LegalDoc.client_id == cli.id))).scalars().all()
    assert {d.tipo_peca for d in docs} == {PecaTipo.contrato, PecaTipo.procuracao}
    assert all(d.case_id is None and d.ai_generated is False for d in docs)
    # Idempotente: segunda chamada reaproveita, não recadastra nem duplica.
    assert (await gdc.gerar_documentos_cliente(db, cli, socio))["ja_existia"] is True
    assert auditoria[-1]["acao"] == "GERAR_DOCS_CLIENTE"

    # ── 2) CASO a partir do cliente (FK), com financeiro e processo ──────────
    caso = Case(id="caso-1", numero_interno="DPT-2026-0001", titulo="Cobrança",
                area=CaseArea.civil, status=CaseStatus.em_instrucao,
                client_id=cli.id, advogado_responsavel_id=socio.id,
                numero_processo=CNJ, proxima_acao="Aguardar homologação")
    db.add(caso)
    db.add(Fee(id="fee-1", case_id=caso.id, client_id=cli.id,
               descricao="Honorários iniciais", valor=1500, status=FeeStatus.pendente))
    db.add(Process(id="proc-1", case_id=caso.id, numero_cnj=CNJ, tipo="judicial",
                   status="ativo", is_principal=True))
    await db.commit()

    # ── 3) SINCRONIZAR processo (DataJud): idempotente, com última sync ──────
    async def _datajud(numero):
        return {"movimentos": [
            {"data": "2026-08-01T10:00:00", "descricao": "Juntada de petição"},
            {"data": "2026-08-15T10:00:00", "descricao": "Conclusos para despacho"},
        ]}

    monkeypatch.setattr(datajud_service, "consultar_processo", _datajud)
    r1 = await cases_router.sincronizar_processo(caso.id, db, socio)
    r2 = await cases_router.sincronizar_processo(caso.id, db, socio)
    assert r1["movimentos_novos"] == 2 and r2["movimentos_novos"] == 0
    n_oficiais = (await db.execute(
        select(func.count()).select_from(CaseMovimento).where(
            CaseMovimento.case_id == caso.id,
            CaseMovimento.tipo == "andamento_oficial")
    )).scalar_one()
    assert n_oficiais == 2
    assert caso.last_synced_at is not None and caso.sync_error is None

    # ── 4) ENCERRAR: prazo aberto BLOQUEIA; diagnóstico expõe tudo ───────────
    db.add(Deadline(id="prazo-1", case_id=caso.id, titulo="Contestação",
                    data_prazo=date.today() + timedelta(days=5),
                    status=DeadlineStatus.pendente, responsavel_id=socio.id))
    db.add(Task(id="tarefa-1", case_id=caso.id, titulo="Ligar para o cliente"))
    await db.commit()

    diag = await cases_router.diagnostico_encerramento(caso.id, db, socio)
    assert diag["pode_encerrar"] is False
    assert [b["codigo"] for b in diag["bloqueios"]] == ["prazo_ativo"]
    assert {a["codigo"] for a in diag["alertas"]} == {
        "tarefa_aberta", "financeiro_pendente", "proxima_acao_pendente", "processo_ativo",
    }
    assert diag["processo"]["pode_sincronizar"] is True
    assert diag["processo"]["ultima_sincronizacao"] is not None

    with pytest.raises(HTTPException) as exc:
        await cases_router.encerrar_caso(
            caso.id, _payload_encerrar(confirmar_alertas=True), BackgroundTasks(),
            None, db, socio,
        )
    assert exc.value.status_code == 422
    assert exc.value.detail["bloqueios"][0]["codigo"] == "prazo_ativo"
    assert caso.status == CaseStatus.em_instrucao  # nada persistido

    # Prazo concluído → sem bloqueio; alertas ainda exigem confirmação explícita.
    prazo = await db.get(Deadline, "prazo-1")
    prazo.status = DeadlineStatus.concluido
    await db.commit()
    with pytest.raises(HTTPException) as exc:
        await cases_router.encerrar_caso(
            caso.id, _payload_encerrar(), BackgroundTasks(), None, db, socio,
        )
    assert exc.value.status_code == 422 and exc.value.detail["bloqueios"] == []
    assert exc.value.detail["alertas"]

    # Confirmado: encerra, preserva histórico (movimento + auditoria).
    resp = await cases_router.encerrar_caso(
        caso.id, _payload_encerrar(confirmar_alertas=True), BackgroundTasks(),
        None, db, socio,
    )
    assert resp["sincronizacao_processo_eletronico"]["solicitada"] is False
    assert caso.status == CaseStatus.encerrado
    assert caso.status_anterior == "em_instrucao" and caso.resultado == "acordo"
    trilha = [r for r in auditoria if r["entidade"] == "cases" and r["id"] == caso.id]
    assert trilha[-1]["dados_depois"]["alertas_confirmados"]
    assert n_oficiais == (await db.execute(
        select(func.count()).select_from(CaseMovimento).where(
            CaseMovimento.case_id == caso.id, CaseMovimento.tipo == "andamento_oficial")
    )).scalar_one()

    # ── 5) REABRIR: volta ao estágio anterior e aceita novo encerramento ─────
    reaberto = await cases_router.reabrir_caso(caso.id, BackgroundTasks(), db, socio)
    assert reaberto.status == CaseStatus.em_instrucao
    tipos = (await db.execute(
        select(CaseMovimento.tipo).where(CaseMovimento.case_id == caso.id)
    )).scalars().all()
    assert "encerramento" in tipos and "reabertura" in tipos


@pytest.mark.asyncio
async def test_justificativa_de_gestao_cede_o_bloqueio_e_fica_na_trilha(db, auditoria):
    socio = _socio()
    cli = _cliente(socio.id)
    caso = Case(id="caso-2", numero_interno="DPT-2026-0002", titulo="Urgente",
                area=CaseArea.civil, status=CaseStatus.aberto,
                client_id=cli.id, advogado_responsavel_id=socio.id)
    db.add_all([socio, cli, caso])
    db.add(Deadline(id="prazo-2", case_id=caso.id, titulo="Recurso",
                    data_prazo=date.today(), status=DeadlineStatus.vencido))
    await db.commit()

    curta = _payload_encerrar(justificativa_bloqueio="curta demais")
    with pytest.raises(HTTPException) as exc:
        await cases_router.encerrar_caso(caso.id, curta, BackgroundTasks(), None, db, socio)
    assert exc.value.status_code == 422

    just = "Prazo vencido sem efeito prático: acordo homologado encerra a lide."
    await cases_router.encerrar_caso(
        caso.id, _payload_encerrar(justificativa_bloqueio=just), BackgroundTasks(),
        None, db, socio,
    )
    assert caso.status == CaseStatus.encerrado
    registro = [r for r in auditoria if r["entidade"] == "cases"][-1]
    assert registro["dados_depois"]["justificativa_bloqueio"] == just
    assert registro["dados_depois"]["bloqueios_justificados"] == ["prazo_ativo"]
    mov = (await db.execute(
        select(CaseMovimento).where(CaseMovimento.tipo == "encerramento")
    )).scalar_one()
    assert just in mov.descricao


@pytest.mark.asyncio
async def test_advogado_nao_contorna_bloqueio_com_justificativa(db, auditoria):
    adv = User(id="u-adv", email="adv@teste.adv.br", hashed_password="h",
               full_name="Dr. Advogado", role=UserRole.advogado, is_active=True)
    cli = _cliente(adv.id)
    caso = Case(id="caso-3", numero_interno="DPT-2026-0003", titulo="Comum",
                area=CaseArea.civil, status=CaseStatus.aberto,
                client_id=cli.id, advogado_responsavel_id=adv.id)
    db.add_all([adv, cli, caso])
    db.add(Deadline(id="prazo-3", case_id=caso.id, titulo="Réplica",
                    data_prazo=date.today(), status=DeadlineStatus.pendente))
    await db.commit()

    with pytest.raises(HTTPException) as exc:
        await cases_router.encerrar_caso(
            caso.id,
            _payload_encerrar(justificativa_bloqueio="Justificativa longa o bastante para passar"),
            BackgroundTasks(), None, db, adv,
        )
    assert exc.value.status_code == 422
    assert caso.status == CaseStatus.aberto
