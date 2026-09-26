from __future__ import annotations

import pytest

from app.services.process_reconciliation import (
    extrair_cnjs,
    normalizar_cnj,
    reconciliar_entrada,
)


def test_extrair_cnjs_remove_repeticao_e_preserva_formato():
    texto = (
        "Processo 1018284-13.2026.8.13.0027; "
        "repetido 1018284-13.2026.8.13.0027; "
        "e 0709938-44.2026.8.07.0018."
    )
    assert extrair_cnjs(texto) == [
        "1018284-13.2026.8.13.0027",
        "0709938-44.2026.8.07.0018",
    ]


def test_extrair_cnjs_aceita_numero_sem_mascara_e_rejeita_dv_invalido():
    assert extrair_cnjs("CNJ 10182841320268130027") == [
        "1018284-13.2026.8.13.0027"
    ]
    assert extrair_cnjs("CNJ 12345678920268130027") == []


def test_normalizar_cnj_recusa_numero_incompleto():
    assert normalizar_cnj("1018284-13.2026.8.13.0027") == "10182841320268130027"
    assert normalizar_cnj("1018284-13") is None


@pytest.mark.anyio
async def test_reconciliacao_sem_banco_nao_inventa_correspondencia():
    resultado = await reconciliar_entrada(
        None,
        object(),
        texto="Relato sem número de processo.",
        cliente_id=None,
        cliente_nome="Fulano",
        parte_contraria="Empresa X",
        assunto="Dano moral",
    )
    assert resultado["status"] == "informacoes_insuficientes"
    assert resultado["correspondencias"] == []
    assert resultado["bloquear_criacao"] is False
