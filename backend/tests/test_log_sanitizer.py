from app.core.log_sanitizer import sanitize_log_value, safe_exception_log


def test_sanitize_log_value_mascara_dados_pessoais_e_credenciais():
    texto = (
        "CPF 123.456.789-00 CNPJ 12.345.678/0001-90 "
        "email pessoa@example.com Authorization Bearer abcdefghijklmnop "
        "token=segredo"
    )

    out = sanitize_log_value(texto)

    assert "123.456.789-00" not in out
    assert "12.345.678/0001-90" not in out
    assert "pessoa@example.com" not in out
    assert "abcdefghijklmnop" not in out
    assert "segredo" not in out
    assert "***CPF***" in out
    assert "***CNPJ***" in out
    assert "***EMAIL***" in out
    assert "Bearer ***" in out
    assert "token=***" in out


def test_sanitize_log_value_trunca_texto_longo():
    out = sanitize_log_value("x" * 50, max_len=10)

    assert out == "x" * 10 + "…"


def test_safe_exception_log_nao_expoe_mensagem_em_claro():
    exc = ValueError("falha CPF 12345678900 token=abc123")

    payload = safe_exception_log(exc)

    assert payload["exception_type"] == "ValueError"
    assert "12345678900" not in payload["exception_message_masked"]
    assert "abc123" not in payload["exception_message_masked"]
    assert "***CPF***" in payload["exception_message_masked"]
    assert "token=***" in payload["exception_message_masked"]


# ── O sanitizador ligado ao pipeline de logging (SEG-006) ────────────────────
# `sanitize_log_value` e `safe_exception_log` só protegiam onde alguém lembrou
# de chamá-los. Um f-string com e-mail do cliente, uma biblioteca de terceiros
# logando URL com token, ou o asyncpg despejando `[parameters: (...)]` num erro
# iam inteiros para `docker logs`. Agora o filtro vive no handler raiz.

import io
import logging as _logging

import pytest

from app.core.log_sanitizer import SanitizadorDeLog
from app.core.logging_config import setup_logging


@pytest.fixture
def _log_capturado():
    """Pipeline REAL (setup_logging), com a saída desviada para um buffer."""
    buf = io.StringIO()
    setup_logging(json_logs=False, level="INFO")
    raiz = _logging.getLogger()
    raiz.handlers[0].stream = buf
    yield _logging.getLogger("ejc.teste_sanitizacao"), buf
    setup_logging(json_logs=False, level="INFO")


def test_setup_logging_instala_o_filtro_no_handler_raiz():
    """Regressão estrutural: sem o filtro no handler, todo o resto é acidente."""
    setup_logging(json_logs=False, level="INFO")
    handler = _logging.getLogger().handlers[0]
    assert any(isinstance(f, SanitizadorDeLog) for f in handler.filters)


def test_mensagem_interpolada_sai_mascarada(_log_capturado):
    """Args do `%s` são interpolados ANTES do mascaramento — senão o valor cru
    voltaria na formatação, depois de o filtro já ter passado."""
    log, buf = _log_capturado
    log.info("Cliente %s com CPF 123.456.789-09", "fulano@escritorio.com.br")
    saida = buf.getvalue()
    assert "fulano@escritorio.com.br" not in saida
    assert "123.456.789-09" not in saida
    assert "***EMAIL***" in saida and "***CPF***" in saida


def test_traceback_de_excecao_sai_mascarado(_log_capturado):
    """O caminho que mais vaza: ninguém escolhe o que entra num traceback, e é
    lá que o driver de banco imprime os parâmetros da query."""
    log, buf = _log_capturado
    try:
        raise ValueError("falhou para vitima@dominio.com e CNPJ 12.345.678/0001-99")
    except ValueError:
        log.exception("erro no processamento")
    saida = buf.getvalue()
    assert "vitima@dominio.com" not in saida
    assert "12.345.678/0001-99" not in saida
    assert "***EMAIL***" in saida


def test_campos_de_extra_sao_mascarados(_log_capturado):
    """`extra={...}` alimenta o log estruturado e escapava inteiro."""
    log, buf = _log_capturado
    log.info("chamada", extra={"detalhe": "Authorization: Bearer abcdefghijklmnop123"})
    assert "abcdefghijklmnop123" not in buf.getvalue()


def test_filtro_nunca_descarta_o_registro():
    """Um filtro de log que engole registro troca vazamento por cegueira. Mesmo
    diante de um record impossível de processar, ele deixa passar."""
    filtro = SanitizadorDeLog()
    quebrado = _logging.LogRecord("x", _logging.INFO, "f", 1, "%s %s", ("só um",), None)
    assert filtro.filter(quebrado) is True
