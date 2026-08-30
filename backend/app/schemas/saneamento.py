# ── app/schemas/saneamento.py ─────────────────────────────────────────────────
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AplicarDedupIn(BaseModel):
    """Confirmação explícita de quem aplica o plano de deduplicação."""

    confirmar: bool = Field(
        ...,
        description="Deve ser true — barreira contra aplicação acidental via automação.",
    )


class DecidirIndicativoIn(BaseModel):
    """Decisão de advogado sobre um indicativo de encerramento.

    A coluna `decisao` só é escrita por esta rota (autenticada, RBAC
    'advogado' ou superior) — nenhum job grava aqui. O banco reforça a
    metade que dá para reforçar via CHECK (decisao exige decidido_por e
    decidido_em, ver migration 154).
    """

    decisao: Literal["encerrar", "manter_ativo"]
    justificativa: str = Field(..., min_length=3, max_length=2000)
