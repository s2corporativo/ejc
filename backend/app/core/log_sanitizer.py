# ── app/core/log_sanitizer.py ────────────────────────────────────────────────
# Sanitização defensiva para logs operacionais do EJC.
# Objetivo: preservar diagnóstico técnico sem registrar dados pessoais,
# credenciais ou identificadores sensíveis em logs de aplicação/containers.
from __future__ import annotations

import logging
import re
from typing import Any

_MASK = "***"

_PATTERNS = (
    # CPF com ou sem pontuação
    (re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"), "***CPF***"),
    # CNPJ com ou sem pontuação
    (re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"), "***CNPJ***"),
    # E-mail
    (re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I), "***EMAIL***"),
    # Bearer/API tokens em mensagens acidentais
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer ***"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|senha)\s*[:=]\s*[^\s,;]+"), r"\1=***"),
)


def sanitize_log_value(value: Any, *, max_len: int = 500) -> str:
    """Converte e mascara valor para uso em log operacional.

    Não é anonimização jurídica completa; é uma barreira de engenharia para
    evitar vazamento acidental de dado pessoal/credencial em `docker logs`,
    agregadores e observabilidade.
    """
    text = str(value or "")
    for pattern, repl in _PATTERNS:
        text = pattern.sub(repl, text)
    if len(text) > max_len:
        return text[:max_len] + "…"
    return text


def safe_exception_log(exc: Exception) -> dict[str, str]:
    """Metadados mínimos para exceção não tratada em produção."""
    return {
        "exception_type": type(exc).__name__,
        "exception_message_masked": sanitize_log_value(exc, max_len=240) or _MASK,
    }


#: Campos que o próprio `logging` cria no LogRecord. Tudo fora daqui veio de
#: `extra={...}` do chamador e passa pelo mascaramento.
_RESERVADOS_LOGRECORD = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
})

#: Teto por campo de `extra`. Alto o bastante para não estropiar diagnóstico e
#: baixo o bastante para um payload inteiro não vazar por um `extra` solto.
_MAX_EXTRA = 2000


class SanitizadorDeLog(logging.Filter):
    """Mascara PII e credenciais em TODO registro, antes de ele ser formatado.

    Por que existir: `sanitize_log_value` e `safe_exception_log` só protegem
    onde alguém lembrou de chamá-los. Um `logger.info(f"... {user.email} ...")`
    — ou uma biblioteca de terceiros logando URL com token, ou o asyncpg
    despejando `[parameters: (...)]` num erro — ia inteiro para `docker logs`
    e para o agregador. Como filtro no handler raiz, a barreira deixa de
    depender de disciplina e passa a valer por padrão.

    O que é mascarado:
      • a mensagem já interpolada (`record.getMessage()`);
      • a EXCEÇÃO renderizada — é onde mais vaza dado, porque o traceback
        carrega valores de parâmetro sem ninguém decidir por isso;
      • os campos string vindos de `extra={...}`.

    Não substitui sanitização jurídica: é barreira de engenharia contra
    vazamento acidental, e o padrão continua sendo não logar dado pessoal.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            # A mensagem é consolidada AQUI: guardar o texto já interpolado e
            # zerar `args` impede que a interpolação aconteça depois do
            # mascaramento e reintroduza o valor cru.
            record.msg = sanitize_log_value(record.getMessage(), max_len=_MAX_EXTRA)
            record.args = ()

            # Pré-renderiza a exceção mascarada. Tanto o Formatter padrão
            # quanto o JsonFormatter reaproveitam `exc_text` quando já existe,
            # então o traceback cru nunca chega à saída.
            if record.exc_info and not record.exc_text:
                record.exc_text = sanitize_log_value(
                    logging.Formatter().formatException(record.exc_info),
                    max_len=8000,
                )
            elif record.exc_text:
                record.exc_text = sanitize_log_value(record.exc_text, max_len=8000)

            for chave, valor in list(record.__dict__.items()):
                if chave in _RESERVADOS_LOGRECORD or chave.startswith("_"):
                    continue
                if isinstance(valor, str):
                    record.__dict__[chave] = sanitize_log_value(valor, max_len=_MAX_EXTRA)
        except Exception:  # pragma: no cover - defensivo
            # Um filtro de log NUNCA pode derrubar a aplicação nem engolir o
            # registro: na dúvida, deixa passar (o registro segue, ainda que
            # sem mascaramento) em vez de perder observabilidade.
            return True
        return True
