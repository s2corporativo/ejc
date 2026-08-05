# ── app/core/logging_config.py ────────────────────────────────────────────────
# Logging estruturado (JSON) opcional para o EJC. Sem dependencia externa:
# um logging.Formatter que serializa cada registro em UMA linha JSON, pronto
# para agregadores (Loki/ELK/CloudWatch). Gated por settings.LOG_JSON — com a
# flag desligada (default) o formato texto legivel de sempre e preservado.
from __future__ import annotations

import datetime as _dt
import json
import logging

# Atributos padrao de LogRecord — tudo que NAO estiver aqui e tratado como
# "extra" estruturado (logger.info(msg, extra={...})) e vai para o JSON.
_RESERVADOS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Formata o LogRecord como um objeto JSON de uma linha.

    Campos fixos: ts (ISO 8601 UTC), level, logger, msg. A excecao (quando ha
    exc_info) entra em `exc` ja renderizada. `extra={...}` do call vira campos
    de topo — util para correlacao (request_id, user_id, etc.)."""

    def format(self, record: logging.LogRecord) -> str:
        ts = _dt.datetime.fromtimestamp(
            record.created, tz=_dt.timezone.utc
        ).isoformat()
        payload: dict = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Preferir exc_text sanitizado, que foi preenchido pelo filtro SanitizadorDeLog
        if record.exc_text:
            payload["exc"] = record.exc_text
        elif record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Campos estruturados passados via extra={...}.
        for chave, valor in record.__dict__.items():
            if chave not in _RESERVADOS and not chave.startswith("_"):
                payload.setdefault(chave, valor)
        # default=str: nunca quebra o log por um valor nao-serializavel.
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(*, json_logs: bool, level: str = "INFO") -> None:
    """Configura o logger raiz uma unica vez (idempotente: substitui handlers).

    json_logs=True → JsonFormatter; caso contrario o formato texto de sempre.
    Chamado do main.py no lugar do logging.basicConfig."""
    from app.core.log_sanitizer import SanitizadorDeLog

    nivel = getattr(logging, str(level).upper(), logging.INFO)
    handler = logging.StreamHandler()
    # Mascaramento de PII/credencial no ÚNICO handler raiz. No handler, e não
    # em cada logger, para alcançar também o que bibliotecas de terceiros
    # emitem — que é justamente o que ninguém revisa. Sem isto, o
    # `log_sanitizer` só protegia as chamadas em que alguém lembrou de usá-lo.
    sanitizador = SanitizadorDeLog()
    handler.addFilter(sanitizador)
    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
    root = logging.getLogger()
    root.setLevel(nivel)
    root.handlers[:] = [handler]  # substitui (evita handler duplicado no reload)

    # Aplicar sanitizador também aos handlers uvicorn.access e uvicorn.error,
    # que podem emitir URLs com tokens sem passar pelo handler raiz.
    for logger_name in ("uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        logger.propagate = True  # propagar para raiz (que já tem sanitizador)
        logger.handlers[:] = []  # remover handlers locais, usar a cadeia da raiz
