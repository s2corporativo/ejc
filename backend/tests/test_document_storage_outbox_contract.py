from __future__ import annotations

import pytest

from app.services.document_storage_outbox_contract import (
    CodigoErroStorage,
    ComandoStorage,
    EstadoOperacaoStorage,
    ResultadoExecucaoStorage,
    StatusOperacaoStorage,
    StorageBackend,
    TipoOperacaoStorage,
    TransicaoOutboxInvalidaError,
)


def _comando(alvo: str = "casos/uuid/documento.pdf") -> ComandoStorage:
    return ComandoStorage(
        document_id="00000000-0000-0000-0000-000000000001",
        backend=StorageBackend.DRIVE,
        operacao=TipoOperacaoStorage.EXCLUIR_OBJETO,
        alvo_opaco=alvo,
    )


def test_chave_idempotencia_e_deterministica_e_sensivel_ao_alvo():
    a = _comando("alvo-a")
    b = _comando("alvo-a")
    c = _comando("alvo-b")

    assert a.chave_idempotencia == b.chave_idempotencia
    assert a.chave_idempotencia != c.chave_idempotencia
    assert len(a.chave_idempotencia) == 64


def test_contexto_seguro_nao_expoe_documento_ou_alvo():
    comando = _comando("path-sensivel-sentinela")
    contexto = comando.contexto_seguro()
    serializado = repr(contexto)

    assert contexto["backend"] == "drive"
    assert contexto["operacao"] == "delete_object"
    assert "chave_idempotencia" in contexto
    assert comando.document_id not in serializado
    assert comando.alvo_opaco not in serializado
    assert "sentinela" not in serializado


def test_comando_rejeita_identificadores_invalidos():
    with pytest.raises(ValueError):
        ComandoStorage(
            document_id="",
            backend=StorageBackend.DRIVE,
            operacao=TipoOperacaoStorage.EXCLUIR_OBJETO,
            alvo_opaco="alvo",
        )
    with pytest.raises(ValueError):
        ComandoStorage(
            document_id="doc",
            backend=StorageBackend.DRIVE,
            operacao=TipoOperacaoStorage.EXCLUIR_OBJETO,
            alvo_opaco="",
        )


def test_claim_incrementa_tentativa_e_limpa_erro_anterior():
    estado = EstadoOperacaoStorage(
        status=StatusOperacaoStorage.AGUARDANDO_RETRY,
        tentativas=2,
        erro_codigo=CodigoErroStorage.TIMEOUT,
    )

    processando = estado.iniciar_tentativa()

    assert processando.status is StatusOperacaoStorage.PROCESSANDO
    assert processando.tentativas == 3
    assert processando.erro_codigo is None


@pytest.mark.parametrize(
    "resultado",
    [ResultadoExecucaoStorage.SUCESSO, ResultadoExecucaoStorage.JA_AUSENTE],
)
def test_sucesso_e_objeto_ja_ausente_concluem_idempotentemente(resultado):
    processando = EstadoOperacaoStorage().iniciar_tentativa()

    final = processando.aplicar_resultado(
        resultado,
        max_tentativas=5,
    )

    assert final.status is StatusOperacaoStorage.CONCLUIDA
    assert final.tentativas == 1
    assert final.erro_codigo is None


def test_falha_transitoria_agenda_retry_antes_do_limite():
    processando = EstadoOperacaoStorage().iniciar_tentativa()

    retry = processando.aplicar_resultado(
        ResultadoExecucaoStorage.FALHA_TRANSITORIA,
        erro_codigo=CodigoErroStorage.INDISPONIVEL,
        max_tentativas=3,
    )

    assert retry.status is StatusOperacaoStorage.AGUARDANDO_RETRY
    assert retry.tentativas == 1
    assert retry.erro_codigo is CodigoErroStorage.INDISPONIVEL


def test_falha_transitoria_vira_terminal_ao_atingir_limite():
    estado = EstadoOperacaoStorage(
        status=StatusOperacaoStorage.AGUARDANDO_RETRY,
        tentativas=2,
        erro_codigo=CodigoErroStorage.TIMEOUT,
    ).iniciar_tentativa()

    final = estado.aplicar_resultado(
        ResultadoExecucaoStorage.FALHA_TRANSITORIA,
        erro_codigo=CodigoErroStorage.TIMEOUT,
        max_tentativas=3,
    )

    assert final.status is StatusOperacaoStorage.FALHA_TERMINAL
    assert final.tentativas == 3
    assert final.erro_codigo is CodigoErroStorage.TIMEOUT


def test_falha_terminal_nao_e_retentada():
    processando = EstadoOperacaoStorage().iniciar_tentativa()
    final = processando.aplicar_resultado(
        ResultadoExecucaoStorage.FALHA_TERMINAL,
        erro_codigo=CodigoErroStorage.PERMISSAO,
        max_tentativas=5,
    )

    assert final.status is StatusOperacaoStorage.FALHA_TERMINAL
    with pytest.raises(TransicaoOutboxInvalidaError):
        final.iniciar_tentativa()


def test_resultado_so_pode_ser_aplicado_durante_processamento():
    with pytest.raises(TransicaoOutboxInvalidaError):
        EstadoOperacaoStorage().aplicar_resultado(
            ResultadoExecucaoStorage.SUCESSO,
            max_tentativas=3,
        )


def test_falha_exige_codigo_e_sucesso_rejeita_codigo():
    processando = EstadoOperacaoStorage().iniciar_tentativa()

    with pytest.raises(ValueError):
        processando.aplicar_resultado(
            ResultadoExecucaoStorage.FALHA_TRANSITORIA,
            max_tentativas=3,
        )
    with pytest.raises(ValueError):
        processando.aplicar_resultado(
            ResultadoExecucaoStorage.SUCESSO,
            erro_codigo=CodigoErroStorage.ERRO_DESCONHECIDO,
            max_tentativas=3,
        )


def test_estado_invalido_rejeita_erro_em_sucesso_e_exige_erro_em_retry():
    with pytest.raises(ValueError):
        EstadoOperacaoStorage(
            status=StatusOperacaoStorage.CONCLUIDA,
            erro_codigo=CodigoErroStorage.TIMEOUT,
        )
    with pytest.raises(ValueError):
        EstadoOperacaoStorage(status=StatusOperacaoStorage.AGUARDANDO_RETRY)


def test_max_tentativas_precisa_ser_positivo():
    processando = EstadoOperacaoStorage().iniciar_tentativa()
    with pytest.raises(ValueError):
        processando.aplicar_resultado(
            ResultadoExecucaoStorage.FALHA_TRANSITORIA,
            erro_codigo=CodigoErroStorage.TIMEOUT,
            max_tentativas=0,
        )
