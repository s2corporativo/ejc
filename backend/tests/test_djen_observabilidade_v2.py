from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import djen_service, heartbeat_service


class _Savepoint:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        self.db.savepoints_abertos += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self.db.savepoints_fechados += 1
        return False


class _DBSavepoint:
    def __init__(self):
        self.savepoints_abertos = 0
        self.savepoints_fechados = 0
        self.commits = 0
        self.rollbacks = 0

    def begin_nested(self):
        return _Savepoint(self)

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


@pytest.fixture(autouse=True)
def _limpar_contexto_djen():
    djen_service.limpar_resultados_execucao()
    yield
    djen_service.limpar_resultados_execucao()


@pytest.mark.asyncio
async def test_metricas_ficam_isoladas_por_task_assincrona():
    async def executar(codigo: str):
        djen_service.registrar_resultado_execucao(
            djen_service.DjenCapturaResultado(
                configurada=True,
                fonte_ok=codigo == "ok",
                recebidas=1 if codigo == "ok" else 0,
                novas=1 if codigo == "ok" else 0,
                duplicadas=0,
                ignoradas=0,
                erro=None if codigo == "ok" else "timeout",
            )
        )
        await asyncio.sleep(0)
        return djen_service.consumir_resultados_execucao()

    manual, agendado = await asyncio.gather(executar("timeout"), executar("ok"))

    assert [resultado.erro for resultado in manual] == ["timeout"]
    assert [resultado.novas for resultado in agendado] == [1]


@pytest.mark.asyncio
async def test_falha_de_um_advogado_reverte_apenas_o_savepoint(monkeypatch):
    async def consulta_ok(_numero, _uf, dias=2):
        return djen_service.DjenConsultaResultado(
            fonte_ok=True,
            items=[{"id": "com-1"}],
        )

    async def processamento_falha(_db, _adv, _consulta):
        raise RuntimeError("falha de banco")

    monkeypatch.setattr(djen_service, "consultar_oab", consulta_ok)
    monkeypatch.setattr(djen_service, "_capturar_configurado", processamento_falha)

    db = _DBSavepoint()
    advogado = SimpleNamespace(
        id="adv-1",
        email="adv@example.com",
        djen_oab_numero="123456",
        djen_oab_uf="MG",
    )

    resultado = await djen_service.capturar_para_advogado(db, advogado)

    assert resultado.fonte_ok is False
    assert resultado.erro == "erro_interno"
    assert db.savepoints_abertos == 1
    assert db.savepoints_fechados == 1
    assert db.rollbacks == 0


@pytest.mark.asyncio
async def test_captura_manual_preserva_novas_numerico_e_envia_pos_commit(monkeypatch):
    from app.routers import intimacoes

    resultado = djen_service.DjenCapturaResultado(
        configurada=True,
        fonte_ok=True,
        recebidas=3,
        novas=2,
        duplicadas=1,
        ignoradas=0,
    )
    capturar = AsyncMock(return_value=resultado)
    enviar = AsyncMock()
    monkeypatch.setattr(intimacoes, "capturar_para_advogado", capturar)
    monkeypatch.setattr(intimacoes, "enviar_emails_pendentes", enviar)

    db = _DBSavepoint()
    usuario = SimpleNamespace(
        djen_oab_numero="123456",
        djen_oab_uf="MG",
    )

    resposta = await intimacoes.capturar_agora(db=db, cu=usuario)

    assert resposta["novas"] == 2
    assert isinstance(resposta["novas"], int)
    assert resposta["duplicadas"] == 1
    assert db.commits == 1
    assert db.rollbacks == 0
    enviar.assert_awaited_once_with(resultado)


@pytest.mark.asyncio
async def test_captura_manual_falha_com_503_e_rollback(monkeypatch):
    from app.routers import intimacoes

    resultado = djen_service.DjenCapturaResultado(
        configurada=True,
        fonte_ok=False,
        recebidas=0,
        novas=0,
        duplicadas=0,
        ignoradas=0,
        erro="timeout",
    )
    monkeypatch.setattr(
        intimacoes,
        "capturar_para_advogado",
        AsyncMock(return_value=resultado),
    )
    enviar = AsyncMock()
    monkeypatch.setattr(intimacoes, "enviar_emails_pendentes", enviar)

    db = _DBSavepoint()
    usuario = SimpleNamespace(
        djen_oab_numero="123456",
        djen_oab_uf="MG",
    )

    with pytest.raises(HTTPException) as exc:
        await intimacoes.capturar_agora(db=db, cu=usuario)

    assert exc.value.status_code == 503
    assert "timeout" in str(exc.value.detail)
    assert db.commits == 0
    assert db.rollbacks == 1
    enviar.assert_not_awaited()


@pytest.mark.asyncio
async def test_heartbeat_consume_somente_resultados_da_task(monkeypatch):
    resultado = djen_service.DjenCapturaResultado(
        configurada=True,
        fonte_ok=True,
        recebidas=2,
        novas=1,
        duplicadas=1,
        ignoradas=0,
    )
    djen_service.registrar_resultado_execucao(resultado)
    enviar = AsyncMock()
    monkeypatch.setattr(djen_service, "enviar_emails_pendentes", enviar)

    status, detalhe = await heartbeat_service._normalizar_resultado_djen(
        db=object(),
        status_nominal="ok",
        detail_nominal=None,
    )

    assert status == "ok"
    payload = json.loads(detalhe)
    assert payload["resultado"] == "sucesso"
    assert payload["novas"] == 1
    assert payload["duplicadas"] == 1
    enviar.assert_awaited_once_with(resultado)
    assert djen_service.consumir_resultados_execucao() == []


class _Scalar:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _DBElegiveis(_DBSavepoint):
    def __init__(self, quantidade):
        super().__init__()
        self.quantidade = quantidade
        self.sql = ""

    async def execute(self, statement):
        self.sql = " ".join(str(statement).split())
        return _Scalar(self.quantidade)


@pytest.mark.asyncio
async def test_probe_elegiveis_espelha_scheduler_e_campos_nao_vazios():
    db = _DBElegiveis(2)

    quantidade = await heartbeat_service._quantidade_oabs_elegiveis(db)

    assert quantidade == 2
    assert "is_active = TRUE" in db.sql
    assert "deleted_at IS NULL" in db.sql
    assert "trim(coalesce(djen_oab_numero" in db.sql
    assert "trim(coalesce(djen_oab_uf" in db.sql
    assert db.savepoints_abertos == 1
    assert db.savepoints_fechados == 1


class _SavepointFalha:
    async def __aenter__(self):
        raise RuntimeError("users ausente")

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DBSchemaMinimo:
    def begin_nested(self):
        return _SavepointFalha()


@pytest.mark.asyncio
async def test_probe_indisponivel_retorna_none_sem_propagar():
    assert (
        await heartbeat_service._quantidade_oabs_elegiveis(_DBSchemaMinimo())
        is None
    )


def test_resumo_parcial_nunca_fica_verde():
    resumo = djen_service.resumir_execucao(
        [
            djen_service.DjenCapturaResultado(
                configurada=True,
                fonte_ok=True,
                recebidas=1,
                novas=1,
                duplicadas=0,
                ignoradas=0,
            ),
            djen_service.DjenCapturaResultado(
                configurada=True,
                fonte_ok=False,
                recebidas=0,
                novas=0,
                duplicadas=0,
                ignoradas=0,
                erro="http_5xx",
            ),
        ]
    )

    assert resumo["heartbeat_status"] == "erro"
    assert resumo["resultado"] == "parcial"
    assert resumo["oabs_sucesso"] == 1
    assert resumo["oabs_falha"] == 1
