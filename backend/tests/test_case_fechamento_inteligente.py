"""Regressões do fechamento inteligente do módulo Casos.

O diagnóstico é determinístico e não persiste dados: prazos ativos bloqueiam o
encerramento; tarefas, financeiro, peças não protocoladas e próxima ação viram
alertas que exigem confirmação humana no endpoint de encerramento.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.case import CaseStatus
from app.models.deadline import DeadlineStatus
from app.models.fee import FeeStatus
from app.models.legal_doc import PecaStatus
from app.models.task import TaskStatus
from app.services.case_closure_service import diagnosticar_fechamento


class _Scalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _Scalars(self._rows)


class _DB:
    """Entrega, em ordem, resultados para prazo, tarefa, fee, peça e processo.

    Lote ausente → lista vazia (a consulta de processos ativos é a última e a
    maioria dos cenários não a exercita)."""

    def __init__(self, *batches):
        self._batches = list(batches)
        self.execute_calls = 0
        self.refresh_calls = 0

    async def execute(self, stmt, *_args, **_kwargs):
        self.execute_calls += 1
        if "pg_advisory_xact_lock" in str(stmt):
            return _Result([])
        return _Result(self._batches.pop(0) if self._batches else [])

    async def refresh(self, _obj):
        self.refresh_calls += 1


def _caso(**overrides):
    base = {
        "id": "case-1",
        "status": CaseStatus.aberto,
        "proxima_acao": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


async def test_prazo_ativo_bloqueia_fechamento_mesmo_sem_confirmacao():
    prazo = SimpleNamespace(
        id="prazo-1",
        titulo="Apresentar recurso",
        status=DeadlineStatus.pendente,
        data_prazo="2026-09-10",
        confirmado=False,
    )
    db = _DB([prazo], [], [], [])

    diagnostico = await diagnosticar_fechamento(db, _caso())

    assert diagnostico["pode_encerrar"] is False
    assert diagnostico["resumo"]["prazos_ativos"] == 1
    assert diagnostico["resumo"]["prazos_nao_confirmados"] == 1
    assert diagnostico["bloqueios"][0]["codigo"] == "prazo_ativo"
    assert "a confirmar" in diagnostico["bloqueios"][0]["descricao"]
    assert db.execute_calls == 6  # lock + prazo, tarefa, fee, peça, processo
    assert db.refresh_calls == 1


async def test_pendencias_nao_fatais_exigem_confirmacao_humana():
    tarefa = SimpleNamespace(
        id="task-1",
        titulo="Telefonar ao cliente",
        status=TaskStatus.a_fazer,
    )
    fee = SimpleNamespace(
        id="fee-1",
        descricao="Honorários finais",
        status=FeeStatus.atrasado,
    )
    peca = SimpleNamespace(
        id="peca-1",
        titulo="Razões finais",
        status=PecaStatus.em_revisao,
    )
    db = _DB([], [tarefa], [fee], [peca])

    diagnostico = await diagnosticar_fechamento(
        db,
        _caso(proxima_acao="Aguardar retorno do cliente"),
    )

    assert diagnostico["pode_encerrar"] is True
    assert diagnostico["requer_confirmacao_alertas"] is True
    assert diagnostico["bloqueios"] == []
    assert {item["codigo"] for item in diagnostico["alertas"]} == {
        "tarefa_aberta",
        "financeiro_pendente",
        "peca_nao_protocolada",
        "proxima_acao_pendente",
    }


async def test_caso_sem_pendencias_fica_pronto_para_encerrar():
    db = _DB([], [], [], [])

    diagnostico = await diagnosticar_fechamento(db, _caso())

    assert diagnostico["pode_encerrar"] is True
    assert diagnostico["requer_confirmacao_alertas"] is False
    assert diagnostico["bloqueios"] == []
    assert diagnostico["alertas"] == []
    assert diagnostico["resumo"] == {
        "prazos_ativos": 0,
        "prazos_nao_confirmados": 0,
        "tarefas_abertas": 0,
        "financeiro_pendente": 0,
        "pecas_nao_protocoladas": 0,
        "proxima_acao_pendente": False,
        "processos_ativos": 0,
    }


async def test_caso_terminal_e_rechecado_apos_lock():
    db = _DB()

    with pytest.raises(HTTPException) as exc:
        await diagnosticar_fechamento(db, _caso(status=CaseStatus.encerrado))

    assert exc.value.status_code == 409
    assert db.execute_calls == 1
    assert db.refresh_calls == 1


async def test_processo_ativo_vira_alerta_com_sugestao_de_sincronizar():
    processo = SimpleNamespace(id="proc-1", numero_cnj="0001234-56.2026.8.13.0027")
    db = _DB([], [], [], [], [processo])

    diagnostico = await diagnosticar_fechamento(
        db,
        _caso(numero_processo="0001234-56.2026.8.13.0027", last_synced_at=None,
              sync_error=None),
    )

    assert diagnostico["pode_encerrar"] is True
    assert diagnostico["requer_confirmacao_alertas"] is True
    assert [a["codigo"] for a in diagnostico["alertas"]] == ["processo_ativo"]
    assert diagnostico["processo"]["pode_sincronizar"] is True
    assert diagnostico["processo"]["processos_ativos"] == 1
    assert diagnostico["resumo"]["processos_ativos"] == 1
