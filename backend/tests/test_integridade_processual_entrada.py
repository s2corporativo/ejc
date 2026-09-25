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


def test_extracao_cnj_colado_na_data_de_lista_exportada():
    texto = (
        "1018284-13.2026.8.13.002714/08/202615/09/2026"
        "Procedimento do Juizado Especial Cível "
        "BETIM BATERIAS AUTOMOTIVAS LTDA X FACEBOOK SERVICOS ONLINE DO BRASIL LTDA."
        "1015352-52.2026.8.13.002718/07/202610/09/2026"
        "Procedimento Comum Cível "
        "EDNALDO CLEMENTE DA SILVA JUNIOR X AFFARE AUTO LTDA"
        "0709938-44.2026.8.07.001803/08/202601/09/2026"
        "Procedimento Comum Cível "
        "BETIM BATERIAS AUTOMOTIVAS LTDA X "
        "DEPARTAMENTO DE ESTRADA DE RODAGEM DO DISTRITO FEDERAL - DER"
    )
    assert entrada_service._extrair_cnjs_texto(texto) == [
        "10182841320268130027",
        "10153525220268130027",
        "07099384420268070018",
    ]


def test_radar_integridade_respeita_escopo_de_carteira(monkeypatch):
    from sqlalchemy import select

    from app.models.case import Case
    from app.routers import saneamento

    monkeypatch.setattr(saneamento, "pode_ver_todos", lambda _user: False)
    stmt = saneamento._escopo_cases_integridade(
        select(Case.id),
        SimpleNamespace(id="adv-1"),
    )
    sql = str(stmt)

    # Usuário sem visão global só pode ver casos em que é responsável ou
    # auxiliar. Não pode existir exceção que exponha casos sem responsável.
    assert "cases.advogado_responsavel_id IS NULL" not in sql
    assert "cases.advogado_auxiliar_id IS NULL" not in sql
    assert "cases.advogado_responsavel_id =" in sql
    assert "cases.advogado_auxiliar_id =" in sql


@pytest.mark.anyio
async def test_update_cnj_mantem_ordem_global_de_locks(monkeypatch):
    from app.services import case_integrity_service

    eventos: list[str] = []

    async def _lock_case(_db, case_id):
        assert case_id == "case-1"
        eventos.append("case")

    async def _lock_cnj(_db, numero):
        assert numero == "10182841320268130027"
        eventos.append("cnj")

    async def _ids(_db, _numero):
        return ["case-1"]

    monkeypatch.setattr(process_repository, "lock_case", _lock_case)
    monkeypatch.setattr(process_repository, "lock_cnj", _lock_cnj)
    monkeypatch.setattr(process_repository, "case_ids_for_cnj", _ids)

    await case_integrity_service.garantir_numero_processo_unico(
        SimpleNamespace(),
        client_id="client-1",
        numero_processo="1018284-13.2026.8.13.0027",
        excluir_case_id="case-1",
    )

    assert eventos == ["case", "cnj"]
