# ── app/schemas/ai.py ────────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List

# Teto de 200.000 chars replica o de VerificarCitacoesRequest (já validado em
# produção) — protege o gateway/provedor de payload sem limite (auditoria de
# segurança, 18/08: nada em ai_gateway.py valida tamanho de mensagem antes de
# _chamar_provedor; quem chama o gateway direto, sem passar por
# ai_skill_service, ignorava AI_LONG_DOCUMENT_MAX_CHARS).
_MAX_TEXTO_IA = 200_000

class AnalisarCasoRequest(BaseModel):
    descricao_fatos: str = Field(..., max_length=_MAX_TEXTO_IA)
    area: str
    case_id: Optional[str] = None
    nomes_proteger: Optional[List[str]] = None   # cliente, parte contrária

class ResumirDocRequest(BaseModel):
    texto: str = Field(..., max_length=_MAX_TEXTO_IA)
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
