import json
from types import SimpleNamespace

import httpx
import pytest


@pytest.mark.asyncio
async def test_consulta_vazia_legitima_nao_e_falha(monkeypatch):
    from app.services import djen_service

    async def fake_get(_params):
        return {"items": []}

    monkeypatch.setattr(djen_service, "_djen_get", fake_get)

    resultado = await djen_service.consultar_oab("123456", "MG")

    assert resultado.fonte_ok is True
    assert resultado.items == []
    assert resultado.erro is None
    assert resultado.recebidas == 0


@pytest.mark.asyncio
async def test_timeout_nao_vira_lista_vazia_com_sucesso(monkeypatch):
    from app.services import djen_service

    async def fake_get(_params):
        raise httpx.ReadTimeout("segredo-nao-pode-vazar")

    monkeypatch.setattr(djen_service, "_djen_get", fake_get)

    resultado = await djen_service.consultar_oab("123456", "MG")

    assert resultado.fonte_ok is False
    assert resultado.items == []
    assert resultado.erro == "timeout"
    assert "123456" not in json.dumps(resultado.to_dict())
    assert "segredo-nao-pode-vazar" not in json.dumps(resultado.to_dict())


@pytest.mark.asyncio
async def test_payload_invalido_nao_e_interpretado_como_zero_legitimo(monkeypatch):
    from app.services import djen_service

    async def fake_get(_params):
        return "html-ou-payload-invalido"

    monkeypatch.setattr(djen_service, "_djen_get", fake_get)

    resultado = await djen_service.consultar_oab("123456", "MG")

    assert resultado.fonte_ok is False
    assert resultado.erro == "payload_invalido"
    assert resultado.recebidas == 0


def test_resumo_sem_oab_configurada_falha_fechado():
    from app.services.djen_service import resumir_execucao

    resumo = resumir_execucao([])

    assert resumo["heartbeat_status"] == "erro"
    assert resumo["resultado"] == "configuracao_incompleta"
    assert resumo["oabs_elegiveis"] == 0
    assert resumo["novas"] == 0


def test_resumo_parcial_nao_fica_verde():
    from app.services.djen_service import DjenCapturaResultado, resumir_execucao

    resultados = [
        DjenCapturaResultado(
            configurada=True,
            fonte_ok=True,
            recebidas=2,
            novas=1,
            duplicadas=1,
            ignoradas=0,
        ),
        DjenCapturaResultado(
            configurada=True,
            fonte_ok=False,
            recebidas=0,
            novas=0,
            duplicadas=0,
            ignoradas=0,
            erro="http_5xx",
        ),
    ]

    resumo = resumir_execucao(resultados)

    assert resumo["heartbeat_status"] == "erro"
    assert resumo["resultado"] == "parcial"
    assert resumo["oabs_elegiveis"] == 2
    assert resumo["oabs_sucesso"] == 1
    assert resumo["oabs_falha"] == 1
    assert resumo["recebidas"] == 2
    assert resumo["novas"] == 1
    assert resumo["duplicadas"] == 1


def test_resumo_zero_valido_preserva_sucesso_e_produtividade_zero():
    from app.services.djen_service import DjenCapturaResultado, resumir_execucao

    resumo = resumir_execucao([
        DjenCapturaResultado(
            configurada=True,
            fonte_ok=True,
            recebidas=0,
            novas=0,
            duplicadas=0,
            ignoradas=0,
        )
    ])

    assert resumo["heartbeat_status"] == "ok"
    assert resumo["resultado"] == "sucesso_sem_resultados"
    assert resumo["oabs_sucesso"] == 1
    assert resumo["recebidas"] == 0
    assert resumo["novas"] == 0


def test_captura_sem_oab_e_configuracao_incompleta():
    from app.services.djen_service import DjenCapturaResultado

    resultado = DjenCapturaResultado.sem_configuracao()

    assert resultado.configurada is False
    assert resultado.fonte_ok is False
    assert resultado.erro == "oab_nao_configurada"
    assert resultado.to_dict()["configurada"] is False


def test_detalhe_heartbeat_e_json_sanitizado():
    from app.services.djen_service import codificar_resumo_heartbeat

    detalhe = codificar_resumo_heartbeat({
        "heartbeat_status": "erro",
        "resultado": "parcial",
        "oabs_elegiveis": 2,
        "oabs_sucesso": 1,
        "oabs_falha": 1,
        "recebidas": 2,
        "novas": 1,
        "duplicadas": 1,
        "ignoradas": 0,
        "erros": {"http_5xx": 1},
    })

    payload = json.loads(detalhe)
    assert payload["resultado"] == "parcial"
    assert payload["erros"] == {"http_5xx": 1}
    assert "email" not in detalhe.lower()
    assert "oab_numero" not in detalhe.lower()
