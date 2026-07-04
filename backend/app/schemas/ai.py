# ── app/schemas/ai.py ────────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List

class AnalisarCasoRequest(BaseModel):
    descricao_fatos: str
    area: str
    case_id: Optional[str] = None
    nomes_proteger: Optional[List[str]] = None   # cliente, parte contrária

class ResumirDocRequest(BaseModel):
    texto: str
    case_id: Optional[str] = None

class HITLRevisaoRequest(BaseModel):
    status: str   # revisado | aplicado | descartado
    # Gate de citações (CITACOES_POLITICA="bloquear"): aprovar output com
    # citação bloqueante exige override EXPLÍCITO + justificativa (auditada).
    override_citacoes: bool = False
    justificativa_override: Optional[str] = Field(None, max_length=2000)

class VerificarCitacoesRequest(BaseModel):
    """Verificador rigoroso de jurisprudência (anti-alucinação)."""
    texto: str = Field(..., min_length=1, max_length=200_000)
    consultar_datajud: bool = False   # confirma nº CNJ no DataJud (máx. 5/verificação)
