# ── app/schemas/saneamento.py ─────────────────────────────────────────────────
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


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

    @field_validator("justificativa")
    @classmethod
    def _justificativa_nao_pode_ser_so_espaco(cls, v: str) -> str:
        """Pydantic não apara string por padrão — "   " passa no
        min_length=3 sem conter nenhuma justificativa de verdade (achado de
        revisão de código). Esta é a razão registrada de uma decisão
        efetivamente irreversível sobre um processo."""
        limpo = v.strip()
        if len(limpo) < 3:
            raise ValueError("justificativa não pode ser vazia ou só espaços")
        return limpo


class VarreduraIn(BaseModel):
    """Aciona o produtor do módulo (Issue #1319) — sem isso as tabelas de
    saneamento ficam vazias para sempre."""

    tipo: Literal["dedup", "datajud", "completa"] = "dedup"
    limite_datajud: int = Field(
        50, ge=1, le=500,
        description="Máximo de numero_cnj consultados ao DataJud nesta execução (tipo=datajud/completa).",
    )
