from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import Select
from sqlalchemy.dialects import postgresql

import app.routers.case_timeline as roteador_timeline
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.atendimento import Atendimento
from app.models.deadline import Deadline
from app.models.legal_doc import LegalDoc
from app.models.task import Task
from app.services import case_timeline_service
from app.services.case_timeline_service import (
    _as_utc,
    _attendance_query,
    _deadline_query,
    _document_query,
    _event,
    _legal_doc_query,
    _task_query,
)


def _usuario(papel: str):
    return SimpleNamespace(role=SimpleNamespace(value=papel))


class _ResultadoEscalarFalso:
    def __init__(self, linhas: list[Any]):
        self._linhas = linhas

    def scalars(self):
        return self

    def all(self) -> list[Any]:
        return self._linhas


class _SessaoSomenteLeituraFalsa:
    """Sessão mínima que aceita somente SELECT e aplica o limite da consulta."""

    def __init__(self, linhas_por_modelo: dict[type[Any], list[Any]] | None = None):
        self.linhas_por_modelo = linhas_por_modelo or {}
        self.consultas: list[Select[Any]] = []

    async def execute(self, consulta: Select[Any]) -> _ResultadoEscalarFalso:
        assert isinstance(consulta, Select), "a fachada deve emitir somente SELECT"
        self.consultas.append(consulta)
        modelo = consulta.column_descriptions[0].get("entity")
        linhas = list(self.linhas_por_modelo.get(modelo, []))
        clausula_limite = getattr(consulta, "_limit_clause", None)
        limite = getattr(clausula_limite, "value", None)
        if isinstance(limite, int):
            linhas = linhas[:limite]
        return _ResultadoEscalarFalso(linhas)


def _ordem_sql(consulta: Select[Any]) -> str:
    """Retorna somente o trecho ORDER BY compilado no dialeto de produção."""
    sql = str(
        consulta.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).lower()
    assert " order by " in sql
    return sql.split(" order by ", 1)[1].split(" limit ", 1)[0]


def _prazo(
    identificador: str,
    *,
    data_prazo: date,
    data_conclusao: datetime | None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=identificador,
        titulo=f"Prazo {identificador}",
        descricao=None,
        data_conclusao=data_conclusao,
        data_prazo=data_prazo,
        status="pendente",
        tipo="processual",
        prioridade="alta",
        confirmado=True,
        ciencia_confirmada=False,
        origem="manual",
        responsavel_id=None,
    )


def _tarefa(
    identificador: str,
    *,
    concluida_em: datetime | None,
    atualizada_em: datetime,
    criada_em: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=identificador,
        titulo=f"Tarefa {identificador}",
        descricao=None,
        concluida_em=concluida_em,
        updated_at=atualizada_em,
        created_at=criada_em,
        status="a_fazer",
        prioridade="media",
        data_limite=None,
        responsavel_id=None,
    )


def _peca(
    identificador: str,
    *,
    protocolado_em: datetime | None,
    revisado_em: datetime | None,
    atualizada_em: datetime,
    criada_em: datetime,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=identificador,
        titulo=f"Peça {identificador}",
        versao=1,
        protocolado_em=protocolado_em,
        revisado_em=revisado_em,
        updated_at=atualizada_em,
        created_at=criada_em,
        status="rascunho",
        tipo_peca="outro",
        codigo_peca=None,
        ai_generated=False,
        human_reviewed=False,
        numero_protocolo=None,
    )


def _aplicacao_teste() -> FastAPI:
    aplicacao = FastAPI()
    aplicacao.include_router(roteador_timeline.router, prefix="/cases")

    async def banco_falso():
        yield object()

    async def usuario_falso():
        return _usuario("advogado")

    aplicacao.dependency_overrides[get_db] = banco_falso
    aplicacao.dependency_overrides[get_current_user] = usuario_falso
    return aplicacao


def test_evento_tem_contrato_estavel_e_data_utc():
    evento = _event(
        entity_id="abc",
        kind="task",
        title="Revisar peça",
        description="Conferir pedidos",
        occurred_at=date(2026, 8, 5),
        status="a_fazer",
        source="tasks",
        metadata={"prioridade": "alta"},
    )
    assert evento["id"] == "tasks:abc"
    assert evento["occurred_at"] == "2026-08-05T00:00:00+00:00"
    assert evento["metadata"] == {"prioridade": "alta"}
    assert evento["_sort_at"].tzinfo is not None


def test_data_sem_fuso_e_normalizada_para_utc():
    resultado = _as_utc(datetime(2026, 8, 5, 10, 30))
    assert resultado.tzinfo == timezone.utc


def test_data_com_offset_e_convertida_para_utc():
    horario_brasilia = timezone(timedelta(hours=-3))
    resultado = _as_utc(datetime(2026, 8, 5, 10, 30, tzinfo=horario_brasilia))
    assert resultado == datetime(2026, 8, 5, 13, 30, tzinfo=timezone.utc)
    assert resultado.tzinfo == timezone.utc


def test_documento_restrito_e_filtrado_no_sql_antes_do_limit():
    consulta = _document_query(_usuario("advogado"), "case-1", 50)
    comando_sql = str(consulta.compile(compile_kwargs={"literal_binds": True}))
    assert "documents.confidencialidade NOT IN" in comando_sql
    assert "LIMIT 50" in comando_sql
    assert comando_sql.index("documents.confidencialidade NOT IN") < comando_sql.index(
        "LIMIT 50"
    )


def test_socio_preserva_acesso_documental_conforme_politica_interna():
    consulta = _document_query(_usuario("socio"), "case-1", 50)
    comando_sql = str(consulta.compile(compile_kwargs={"literal_binds": True}))
    assert "documents.confidencialidade NOT IN" not in comando_sql


def test_fontes_ordenam_pela_mesma_precedencia_exposta_em_occurred_at():
    ordem_prazos = _ordem_sql(_deadline_query("case-1", 2))
    assert ordem_prazos.startswith("coalesce(deadlines.data_conclusao, timezone(")
    assert "'utc'" in ordem_prazos
    assert "deadlines.data_prazo" in ordem_prazos
    assert ordem_prazos.split(", deadlines.created_at", 1)[0].endswith(" desc")
    assert "deadlines.created_at desc" in ordem_prazos

    ordem_tarefas = _ordem_sql(_task_query("case-1", 2))
    assert ordem_tarefas.startswith(
        "coalesce(tasks.concluida_em, tasks.updated_at, tasks.created_at) desc"
    )
    assert "tasks.created_at desc" in ordem_tarefas

    ordem_pecas = _ordem_sql(_legal_doc_query("case-1", 2))
    assert ordem_pecas.startswith(
        "coalesce(legal_docs.protocolado_em, legal_docs.revisado_em, "
        "legal_docs.updated_at, legal_docs.created_at) desc"
    )
    assert "legal_docs.created_at desc" in ordem_pecas

    ordem_atendimentos = _ordem_sql(_attendance_query("case-1", 2))
    assert ordem_atendimentos.startswith("atendimentos.data_atendimento desc")
    assert "atendimentos.created_at desc" in ordem_atendimentos


@pytest.mark.asyncio
async def test_source_limit_preserva_eventos_mais_recentes_de_prazos_tarefas_e_pecas():
    utc = timezone.utc
    linhas_por_modelo = {
        Deadline: [
            _prazo(
                "prazo-recente",
                data_prazo=date(2026, 7, 1),
                data_conclusao=datetime(2026, 8, 10, 12, tzinfo=utc),
            ),
            _prazo(
                "prazo-pendente",
                data_prazo=date(2026, 8, 9),
                data_conclusao=None,
            ),
            _prazo(
                "prazo-antigo",
                data_prazo=date(2026, 12, 1),
                data_conclusao=datetime(2026, 8, 8, 12, tzinfo=utc),
            ),
        ],
        Task: [
            _tarefa(
                "tarefa-recente",
                concluida_em=datetime(2026, 8, 10, 11, tzinfo=utc),
                atualizada_em=datetime(2026, 7, 1, tzinfo=utc),
                criada_em=datetime(2026, 6, 1, tzinfo=utc),
            ),
            _tarefa(
                "tarefa-atualizada",
                concluida_em=None,
                atualizada_em=datetime(2026, 8, 9, 11, tzinfo=utc),
                criada_em=datetime(2026, 8, 1, tzinfo=utc),
            ),
            _tarefa(
                "tarefa-antiga",
                concluida_em=datetime(2026, 8, 8, 11, tzinfo=utc),
                atualizada_em=datetime(2026, 12, 1, tzinfo=utc),
                criada_em=datetime(2026, 5, 1, tzinfo=utc),
            ),
        ],
        LegalDoc: [
            _peca(
                "peca-recente",
                protocolado_em=datetime(2026, 8, 10, 10, tzinfo=utc),
                revisado_em=None,
                atualizada_em=datetime(2026, 7, 1, tzinfo=utc),
                criada_em=datetime(2026, 6, 1, tzinfo=utc),
            ),
            _peca(
                "peca-revisada",
                protocolado_em=None,
                revisado_em=datetime(2026, 8, 9, 10, tzinfo=utc),
                atualizada_em=datetime(2026, 8, 1, tzinfo=utc),
                criada_em=datetime(2026, 7, 1, tzinfo=utc),
            ),
            _peca(
                "peca-antiga",
                protocolado_em=datetime(2026, 8, 8, 10, tzinfo=utc),
                revisado_em=None,
                atualizada_em=datetime(2026, 12, 1, tzinfo=utc),
                criada_em=datetime(2026, 5, 1, tzinfo=utc),
            ),
        ],
    }
    sessao = _SessaoSomenteLeituraFalsa(linhas_por_modelo)

    resultado = await case_timeline_service.timeline(
        sessao,
        _usuario("socio"),
        "case-1",
        source_limit=2,
        per_page=20,
    )

    identificadores = {evento["entity_id"] for evento in resultado["items"]}
    assert {
        "prazo-recente",
        "prazo-pendente",
        "tarefa-recente",
        "tarefa-atualizada",
        "peca-recente",
        "peca-revisada",
    } <= identificadores
    assert {
        "prazo-antigo",
        "tarefa-antiga",
        "peca-antiga",
    }.isdisjoint(identificadores)
    assert {"deadlines", "tasks", "legal_docs"} <= set(
        resultado["saturated_sources"]
    )


@pytest.mark.asyncio
async def test_timeline_executa_somente_select_e_nao_expoe_observacao_privada():
    sentinela = "NAO-EXPOR-OBSERVACAO-PRIVADA"
    atendimento = SimpleNamespace(
        id="atendimento-1",
        tipo="telefone",
        resumo="Contato com cliente",
        data_atendimento=datetime(2026, 8, 6, 12, tzinfo=timezone.utc),
        solicitacao_atendida=True,
        solicitacao="Enviar documento",
        proximo_passo="Revisar documento",
        solicitacao_prazo=None,
        contato_status="concluido",
        solicitacao_responsavel_id=None,
        task_id=None,
        observacoes_privadas=sentinela,
    )
    sessao = _SessaoSomenteLeituraFalsa({Atendimento: [atendimento]})

    resultado = await case_timeline_service.timeline(
        sessao,
        _usuario("advogado"),
        "case-1",
        source_limit=50,
    )

    assert len(sessao.consultas) == 7
    assert all(isinstance(consulta, Select) for consulta in sessao.consultas)
    assert sentinela not in json.dumps(resultado, ensure_ascii=False, default=str)
    assert resultado["items"][0]["source"] == "atendimentos"


def test_handlers_rejeitam_sem_ownership_e_expoem_saude_deterministica(monkeypatch):
    aplicacao = _aplicacao_teste()

    async def negar_acesso(_banco, _usuario_atual, _caso_id):
        raise HTTPException(status_code=403, detail="Acesso negado")

    monkeypatch.setattr(roteador_timeline, "verificar_acesso_caso", negar_acesso)
    with TestClient(aplicacao) as cliente:
        resposta_timeline = cliente.get("/cases/case-1/timeline")
        resposta_saude = cliente.get("/cases/case-1/operational-health")
    assert resposta_timeline.status_code == 403
    assert resposta_saude.status_code == 403

    caso = SimpleNamespace(id="case-1")
    chamadas: list[str] = []

    async def permitir_acesso(_banco, _usuario_atual, caso_id):
        chamadas.append(f"ownership:{caso_id}")
        return caso

    async def timeline_falsa(_banco, _usuario_atual, caso_id, **_parametros):
        chamadas.append(f"timeline:{caso_id}")
        return {"case_id": caso_id, "items": [], "total_loaded": 0}

    async def saude_falsa(_banco, caso_recebido):
        assert caso_recebido is caso
        chamadas.append("saude")
        return {"case_id": caso_recebido.id, "score": 87, "nivel": "saudavel"}

    monkeypatch.setattr(roteador_timeline, "verificar_acesso_caso", permitir_acesso)
    monkeypatch.setattr(
        roteador_timeline.case_timeline_service, "timeline", timeline_falsa
    )
    monkeypatch.setattr(
        roteador_timeline.case_health, "calcular_score_caso", saude_falsa
    )

    with TestClient(aplicacao) as cliente:
        resposta_timeline = cliente.get("/cases/case-1/timeline")
        resposta_saude = cliente.get("/cases/case-1/operational-health")

    assert resposta_timeline.status_code == 200
    assert resposta_timeline.json()["case_id"] == "case-1"
    assert resposta_saude.status_code == 200
    assert resposta_saude.json() == {
        "case_id": "case-1",
        "score": 87,
        "nivel": "saudavel",
    }
    assert chamadas == [
        "ownership:case-1",
        "timeline:case-1",
        "ownership:case-1",
        "saude",
    ]


def test_router_e_anexado_uma_unica_vez_ao_dominio_cases():
    from app.main import app

    caminhos = [
        rota.path
        for rota in app.routes
        if getattr(rota, "path", "")
        in {
            "/api/cases/{case_id}/timeline",
            "/api/cases/{case_id}/operational-health",
        }
    ]
    assert sorted(caminhos) == [
        "/api/cases/{case_id}/operational-health",
        "/api/cases/{case_id}/timeline",
    ]
