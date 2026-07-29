import json

import pytest

from app.services import djen_service, heartbeat_service


class _ScalarResult:
    def __init__(self, valor):
        self.valor = valor

    def scalar(self):
        return self.valor


class _DBComUsuarios:
    def __init__(self, quantidade_oabs):
        self.quantidade_oabs = quantidade_oabs
        self.params = None

    async def execute(self, _query, params=None):
        if params is None:
            return _ScalarResult(self.quantidade_oabs)
        self.params = params
        return _ScalarResult(None)

    async def commit(self):
        return None

    async def rollback(self):
        return None


@pytest.mark.asyncio
async def test_heartbeat_sem_oab_configurada_nao_fica_verde():
    djen_service.limpar_resultados_execucao()
    db = _DBComUsuarios(quantidade_oabs=0)

    gravou = await heartbeat_service.registrar_heartbeat(
        db, heartbeat_service.JOB_DJEN, "ok"
    )

    assert gravou is True
    assert db.params["status"] == "erro"
    detalhe = json.loads(db.params["detail"])
    assert detalhe["resultado"] == "configuracao_incompleta"
    assert detalhe["oabs_elegiveis"] == 0


@pytest.mark.asyncio
async def test_heartbeat_com_oabs_mas_sem_metricas_indica_falha_do_job():
    djen_service.limpar_resultados_execucao()
    db = _DBComUsuarios(quantidade_oabs=3)

    gravou = await heartbeat_service.registrar_heartbeat(
        db, heartbeat_service.JOB_DJEN, "ok"
    )

    assert gravou is True
    assert db.params["status"] == "erro"
    detalhe = json.loads(db.params["detail"])
    assert detalhe["resultado"] == "falha_job"
    assert detalhe["oabs_elegiveis"] == 3
    assert detalhe["oabs_falha"] == 3
    assert detalhe["erros"] == {"sem_metricas_da_execucao": 1}
