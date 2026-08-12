# ── app/models/dpt_diagnostico.py ─────────────────────────────────────────────
# Persistência de resultados do Diagnóstico Jurídico Empresarial 360 (DPT360).
#
# Habilita o campo `persistencia` do `DptDiagnosticReadiness` (diagnostic_service)
# com valor "habilitada" e grava cada execução de diagnóstico em estado
# `rascunho` até a revisão humana obrigatória (HITL), em coerência com a
# governança de IA do EJC (revisão OAB antes de qualquer entrega ao cliente).
#
# Padrões seguidos:
#  - PK string(36) UUID, igual aos demais satélites do EJC (empresarial_cases etc.)
#  - Estados VARCHAR com validação de domínio em Pydantic (sem enum nativo PG,
#    como em empresarial_cases / environmental) — evita drift model↔schema.
#  - Auditoria who/when completa (created_by/revised_by FK users).
#  - RBAC: o acesso é feito via client_id, filtrado pelo escopo de
#    company_service (get_company_scope) — não há coluna própria de escopo.

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text

from app.core.database import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class DptDiagnosticEstado(str, enum.Enum):
    rascunho = "rascunho"              # execução da IA concluída, aguarda revisão
    em_revisao = "em_revisao"          # revisor humano assumiu a análise
    revisado = "revisado"              # revisado (requer_revisao=False ou review)
    concluido = "concluido"            # entregue/consolidado pelo escritório
    descartado = "descartado"          # inválido ou gerado por engano (preservação)


class DptDiagnosticRun(Base):
    """Resultado persistido de uma execução de Diagnóstico 360."""

    __tablename__ = "dpt_diagnosticos"

    id = Column(String(36), primary_key=True, default=_new_uuid)
    client_id = Column(
        String(36),
        ForeignKey("clients.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # completo | tributario | ambiental | administrativo | trabalhista |
    # contratual | lgpd | governanca_ia (ver DptDiagnosticKind em schemas.py)
    tipo = Column(String(30), nullable=False, default="completo")

    # JSON serializado de DptDiagnosticReadiness.areas (evidências, lacunas e
    # estado por área) — JSONB não é usado por padrão de portabilidade do EJC.
    areas_json = Column(Text, nullable=True)

    estado = Column(
        String(20), nullable=False, default=DptDiagnosticEstado.rascunho.value
    )
    requer_revisao = Column(Boolean, nullable=False, default=True)
    observacao_revisao = Column(Text, nullable=True)

    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    revised_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    revised_at = Column(DateTime(timezone=True), nullable=True)
