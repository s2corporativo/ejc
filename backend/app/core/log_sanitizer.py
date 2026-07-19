# ── app/core/log_sanitizer.py ────────────────────────────────────────────────
# Sanitização defensiva para logs operacionais do EJC.
# Objetivo: preservar diagnóstico técnico sem registrar dados pessoais,
# credenciais ou identificadores sensíveis em logs de aplicação/containers.
from __future__ import annotations

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
