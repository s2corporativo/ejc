"""Regressões do fechamento inteligente do módulo Casos.

O diagnóstico é determinístico e não persiste dados: prazos ativos bloqueiam o
encerramento; tarefas, financeiro, peças não protocoladas e próxima ação viram
alertas que exigem confirmação humana no endpoint de encerramento.
"""
from __future__ import annotations

from types import SimpleNamespace

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
    """Entrega, em ordem, resultados para prazo, tarefa, fee e peça."""

    def __init__(self, *batches):
        self._batches = list(batches)
        self.execute_calls = 0

    async def execute(self, _stmt):
        self.execute_calls += 1
        return _Result(self._batches.pop(0))


def _caso(**overrides):
    base = {
        "id": "case-1",
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
    assert db.execute_calls == 4


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
    }
