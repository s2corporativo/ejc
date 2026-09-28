"""Contrato temporal de proveniência compartilhado pelo RAG e Legal Brain.

ISO com segundos (fração até microssegundos) ou data civil; sem fuso = UTC.
Não aceita datas relativas, calendário inválido ou verificações futuras.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

ISO_VERIFICATION_PATTERN = (
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"([T ][0-2][0-9]:[0-5][0-9]:[0-5][0-9]"
    r"([.][0-9]{1,6})?(Z|[+-](0[0-9]|1[0-4]):[0-5][0-9])?)?"
)
# Restringir horas a 00..23 também no PostgreSQL (que aceita 24:00).
ISO_VERIFICATION_PATTERN = ISO_VERIFICATION_PATTERN.replace(
    "[0-2][0-9]", "(0[0-9]|1[0-9]|2[0-3])"
)


def verificacao_temporal_valida(value: object, *, now: datetime | None = None) -> bool:
    if not isinstance(value, str):
        return False
    value = value.strip(" ")
    if not re.fullmatch(ISO_VERIFICATION_PATTERN, value):
        return False
    try:
        verified = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if verified.tzinfo is None:
            verified = verified.replace(tzinfo=timezone.utc)
        reference = now if now is not None else datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        return verified <= reference
    except (ValueError, OverflowError):
        return False


# Alias fixo kd, sem interpolação de entrada do usuário. PostgreSQL >= 16.
# CASE protege o cast de datas impossíveis; COALESCE fecha metadados ausentes.
_RAW = "btrim(kd.extra->>'legal_status_verificado_em')"
_UTC = (
    f"(CASE WHEN length({_RAW}) = 10 THEN {_RAW} || 'T00:00:00+00:00' "
    f"WHEN {_RAW} ~ '(Z|[+-][0-9]{{2}}:[0-9]{{2}})$' THEN {_RAW} "
    f"ELSE {_RAW} || '+00:00' END)"
)
SQL_VERIFICACAO_TEMPORAL_VALIDA = (
    "COALESCE((CASE WHEN "
    "jsonb_typeof(kd.extra->'legal_status_verificado_em') = 'string' "
    f"AND {_RAW} ~ '^{ISO_VERIFICATION_PATTERN}$' "
    f"AND pg_input_is_valid({_UTC}, 'timestamp with time zone') "
    f"THEN {_UTC}::timestamptz <= CURRENT_TIMESTAMP "
    "ELSE false END), false)"
)
