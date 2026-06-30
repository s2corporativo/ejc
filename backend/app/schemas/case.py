# ── app/schemas/case.py ──────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, date
from decimal import Decimal

class CaseCreate(BaseModel):
    titulo: str
    area: str
    client_id: str
    prioridade: str = "media"
    numero_processo: Optional[str] = None
    tribunal: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    parte_contraria: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    descricao_fatos: Optional[str] = None
    advogado_responsavel_id: Optional[str] = None
    tipo_acao_prescricao: Optional[str] = None
    data_fato_prescricao: Optional[date] = None  # p/ cálculo automático
    case_type: Optional[str] = "judicial"
    extrajudicial_type: Optional[str] = None
    has_judicial_process: Optional[bool] = False

class CaseUpdate(BaseModel):
    titulo: Optional[str] = None
    status: Optional[str] = None
    fase: Optional[str] = None
    prioridade: Optional[str] = None
    risco: Optional[str] = None
    numero_processo: Optional[str] = None
    tribunal: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    parte_contraria: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    descricao_fatos: Optional[str] = None
    tese_principal: Optional[str] = None
    pontos_fortes: Optional[str] = None
    pontos_fracos: Optional[str] = None
    observacoes: Optional[str] = None
    advogado_responsavel_id: Optional[str] = None
    case_type: Optional[str] = None
    extrajudicial_type: Optional[str] = None
    has_judicial_process: Optional[bool] = None
    kanban_column: Optional[str] = None
    kanban_position: Optional[int] = None

class ProcessoPrincipalSchema(BaseModel):
    """Snapshot do processo principal (is_principal=True) — fonte canonica."""
    id: str
    numero_cnj: Optional[str] = None
    instancia: Optional[str] = None
    tribunal: Optional[str] = None
    comarca: Optional[str] = None
    vara: Optional[str] = None
    classe: Optional[str] = None
    fase: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    status: Optional[str] = None
    class Config:
        from_attributes = True

class CaseResponse(BaseModel):
    id: str
    numero_interno: Optional[str] = None
    titulo: str
    area: str
    status: str
    fase: str
    prioridade: str
    risco: Optional[str] = None
    numero_processo: Optional[str] = None
    tribunal: Optional[str] = None
    parte_contraria: Optional[str] = None
    valor_causa: Optional[Decimal] = None
    client_id: str
    advogado_responsavel_id: Optional[str] = None
    case_type: Optional[str] = None
    extrajudicial_type: Optional[str] = None
    has_judicial_process: Optional[bool] = None
    kanban_column: Optional[str] = None
    linked_judicial_case_id: Optional[str] = None
    data_prescricao: Optional[datetime] = None
    created_at: datetime
    
    # Sincronização
    last_synced_at: Optional[datetime] = None
    sync_pending: bool = False
    sync_error: Optional[str] = None
    
    processo_principal: Optional[ProcessoPrincipalSchema] = None
    class Config:
        from_attributes = True

class CaseDetail(CaseResponse):
    comarca: Optional[str] = None
    vara: Optional[str] = None
    descricao_fatos: Optional[str] = None
    tese_principal: Optional[str] = None
    pontos_fortes: Optional[str] = None
    pontos_fracos: Optional[str] = None
    observacoes: Optional[str] = None
    tipo_acao_prescricao: Optional[str] = None

class MovimentoCreate(BaseModel):
    tipo: str
    descricao: str
