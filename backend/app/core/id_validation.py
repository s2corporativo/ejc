# ── app/core/id_validation.py ─────────────────────────────────────────────────
# Validação de formato de identificador de path (Issue #581).
#
# `Case.id` (e a maioria das PKs do EJC) é `Column(String(36))` — VARCHAR, não
# o tipo UUID nativo do Postgres. Um path param malformado ("abc", "' OR 1=1")
# não quebra a query (compara string com string), mas devolve 404 igual a um
# UUID válido inexistente — os dois casos ficam indistinguíveis pela resposta,
# e o cliente não sabe se errou o FORMATO ou se o recurso não existe.
#
# Validar aqui, ANTES da consulta, separa os dois: formato errado → 422
# (defeito do chamador); formato certo e ausente → 404 (recurso inexistente).
# Mantém `case_id: str` na assinatura da rota — não usar `uuid.UUID` como tipo
# do path param, que mudaria o valor que chega ao handler (viraria objeto UUID,
# não string) e quebraria qualquer comparação/log que espera string.
from __future__ import annotations

import re

from fastapi import HTTPException

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def validar_uuid_path(valor: str, *, rotulo: str = "Identificador") -> str:
    """Levanta 422 se `valor` não tem forma de UUID; devolve o próprio valor.

    Não confere existência (isso é 404, na consulta) — só formato. `rotulo`
    entra na mensagem para o erro apontar o campo, não um "id inválido" genérico
    quando a rota tem mais de um path param de identificador.
    """
    if not _UUID_RE.fullmatch(valor or ""):
        raise HTTPException(
            status_code=422,
            detail=f"{rotulo} inválido: {valor!r} não tem formato de UUID.",
        )
    return valor
