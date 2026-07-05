# ── tests/test_logging_config.py ──────────────────────────────────────────────
# Logging estruturado (JSON) — o JsonFormatter serializa cada LogRecord numa
# linha JSON; setup_logging troca o formato sem duplicar handlers.
import json
import logging

from app.core.logging_config import JsonFormatter, setup_logging


def _record(**kw):
    base = dict(
        name="ejc.teste", level=logging.INFO, pathname=__file__, lineno=10,
        msg="ola %s", args=("mundo",), exc_info=None,
    )
    base.update(kw)
    return logging.LogRecord(**base)


def test_formata_json_valido_com_campos_fixos():
    linha = JsonFormatter().format(_record())
    obj = json.loads(linha)  # linha unica, JSON valido
    assert obj["level"] == "INFO"
    assert obj["logger"] == "ejc.teste"
    assert obj["msg"] == "ola mundo"          # args interpolados
    assert "ts" in obj and obj["ts"].endswith("+00:00")  # ISO UTC


def test_excecao_renderizada_em_exc():
    try:
        raise ValueError("falha proposital")
    except ValueError:
        import sys
        rec = _record(exc_info=sys.exc_info())
    obj = json.loads(JsonFormatter().format(rec))
    assert "exc" in obj
    assert "ValueError: falha proposital" in obj["exc"]


def test_extra_vira_campo_de_topo():
    rec = _record()
    rec.request_id = "abc-123"      # simula logger.info(..., extra={"request_id": ...})
    obj = json.loads(JsonFormatter().format(rec))
    assert obj["request_id"] == "abc-123"


def test_valor_nao_serializavel_nao_quebra():
    rec = _record()
    rec.obj = object()             # nao serializavel por padrao → default=str
    obj = json.loads(JsonFormatter().format(rec))
    assert isinstance(obj["obj"], str)


def test_setup_logging_json_e_idempotente():
    root = logging.getLogger()
    try:
        setup_logging(json_logs=True, level="WARNING")
        assert root.level == logging.WARNING
        assert len(root.handlers) == 1
        assert isinstance(root.handlers[0].formatter, JsonFormatter)
        # Rechamar NAO deve empilhar handlers (evita log duplicado no reload).
        setup_logging(json_logs=True, level="WARNING")
        assert len(root.handlers) == 1
    finally:
        # Restaura formato texto p/ nao afetar outros testes.
        setup_logging(json_logs=False, level="INFO")


def test_setup_logging_texto_nao_usa_json_formatter():
    root = logging.getLogger()
    setup_logging(json_logs=False, level="INFO")
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)
