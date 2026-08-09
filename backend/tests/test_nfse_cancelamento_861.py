from app.models.nfse import NotaFiscalServico


def test_cancelamento_manual_e_somente_registro_local():
    nota = NotaFiscalServico(provider="manual", status="autorizada")
    nota.status = "cancelada"

    assert nota.cancelamento_tipo == "registro_local"
    assert nota.cancelamento_fiscal_confirmado is False
    assert nota.cancelamento_confirmado_em is None


def test_cancelamento_provider_fica_marcado_como_fiscal_confirmado():
    nota = NotaFiscalServico(provider="nuvemfiscal", status="autorizada")
    nota.status = "cancelada"

    assert nota.cancelamento_tipo == "fiscal_provider"
    assert nota.cancelamento_fiscal_confirmado is True
    assert nota.cancelamento_confirmado_em is not None


def test_retorno_a_status_nao_cancelado_limpa_evidencia_de_cancelamento():
    nota = NotaFiscalServico(provider="nuvemfiscal", status="cancelada")
    assert nota.cancelamento_fiscal_confirmado is True

    nota.status = "autorizada"
    assert nota.cancelamento_tipo is None
    assert nota.cancelamento_fiscal_confirmado is False
    assert nota.cancelamento_confirmado_em is None
