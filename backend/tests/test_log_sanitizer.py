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
