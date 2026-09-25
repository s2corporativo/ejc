from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.repositories.process_repository import process_repository
from app.services import entrada_service, processo_service


@pytest.mark.anyio
async def test_cnj_nao_pode_ser_vinculado_a_outro_caso(monkeypatch):
    monkeypatch.setattr(process_repository, "lock_cnj", AsyncMock())
    monkeypatch.setattr(
        process_repository,
        "case_ids_for_cnj",
        AsyncMock(return_value=["case-existente"]),
    )

    with pytest.raises(processo_service.ProcessConflict, match="outro caso"):
        await processo_service._garantir_cnj_no_mesmo_caso(
            SimpleNamespace(),
            "case-novo",
            "1018284-13.2026.8.13.0027",
        )

    process_repository.lock_cnj.assert_awaited_once()


@pytest.mark.anyio
async def test_mesmo_cnj_pode_ter_registros_no_mesmo_caso(monkeypatch):
    monkeypatch.setattr(process_repository, "lock_cnj", AsyncMock())
    monkeypatch.setattr(
        process_repository,
        "case_ids_for_cnj",
        AsyncMock(return_value=["case-1"]),
    )

    await processo_service._garantir_cnj_no_mesmo_caso(
        SimpleNamespace(),
        "case-1",
        "1018284-13.2026.8.13.0027",
    )


def test_extracao_cnj_da_entrada_e_deterministica():
    texto = (
        "Processo 1018284-13.2026.8.13.0027 e repetição "
        "1018284-13.2026.8.13.0027."
    )
    assert entrada_service._extrair_cnjs_texto(texto) == [
        "10182841320268130027"
    ]


@pytest.mark.anyio
async def test_entrada_com_varios_cnjs_nao_escolhe_um_silenciosamente():
    resultado = await entrada_service.reconciliar_processo_entrada(
        SimpleNamespace(),
        SimpleNamespace(),
        numeros_detectados=[
            "1018284-13.2026.8.13.0027",
            "1015352-52.2026.8.13.0027",
        ],
        client_id=None,
        parte_contraria=None,
        tribunal=None,
        comarca=None,
        vara=None,
    )
    assert resultado["status"] == "informacoes_insuficientes"
    assert len(resultado["numeros_detectados"]) == 2


@pytest.mark.anyio
async def test_cnj_valido_sem_correspondencia_vira_novo_processo(monkeypatch):
    monkeypatch.setattr(
        process_repository,
        "case_ids_for_cnj",
        AsyncMock(return_value=[]),
    )
    resultado = await entrada_service.reconciliar_processo_entrada(
        SimpleNamespace(),
        SimpleNamespace(),
        numeros_detectados=["1018284-13.2026.8.13.0027"],
        client_id=None,
        parte_contraria="FACEBOOK SERVICOS ONLINE DO BRASIL LTDA.",
        tribunal="TJMG",
        comarca="Betim",
        vara="Juizado Especial",
    )
    assert resultado["status"] == "novo_processo"
    assert resultado["dados_processuais"]["numero_cnj"] == "10182841320268130027"
