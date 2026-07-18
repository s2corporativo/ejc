# ── app/schemas/case.py ──────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal


_NUMERO_PROCESSO_MAX = 60


def _validar_numero_processo_cnj(v: Optional[str]) -> Optional[str]:
    """Valida `numero_processo` na ENTRADA (create/update).

    Regra: o caso pode ainda NÃO ter número → vazio/None PASSA (retorna None).
    A validação estrita (formato + dígito verificador módulo 97, via
    validators_service.validar_cnj) só se aplica quando o valor PARECE um
    número CNJ — 20 dígitos após remover a pontuação (com ou sem a máscara
    NNNNNNN-DD.AAAA.J.TR.OOOO). Processos ADMINISTRATIVOS (JARI/SEI/PAD etc.)
    têm numeração própria e são aceitos como texto livre, limitado a
    60 caracteres. Só roda em CaseCreate/CaseUpdate — a LEITURA
    (CaseResponse/CaseDetail) não valida, para não quebrar casos legados já
    gravados com número fora do padrão.
    """
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    from app.services.validators_service import normalizar_cnj, validar_cnj
    parece_cnj = len(normalizar_cnj(v)) == 20
    if parece_cnj:
        if not validar_cnj(v):
            raise ValueError(
                "Número CNJ inválido: dígito verificador não confere ou formato "
                "fora do padrão NNNNNNN-DD.AAAA.J.TR.OOOO"
            )
        return v
    if len(v) > _NUMERO_PROCESSO_MAX:
        raise ValueError(
            f"Número de processo muito longo (máximo {_NUMERO_PROCESSO_MAX} caracteres)"
        )
    return v


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

    @field_validator("area")
    @classmethod
    def _area_valida(cls, v: str) -> str:
        # A coluna `area` é ENUM casearea no banco; um valor fora do enum estoura
        # InvalidTextRepresentationError → 500. Validar aqui devolve 422 claro.
        from app.models.case import CaseArea
        validas = {a.value for a in CaseArea}
        if v not in validas:
            raise ValueError(
                f"Área inválida: {v!r}. Válidas: {sorted(validas)}"
            )
        return v

    @field_validator("numero_processo")
    @classmethod
    def _numero_processo_valido(cls, v: Optional[str]) -> Optional[str]:
        return _validar_numero_processo_cnj(v)

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

    @field_validator("numero_processo")
    @classmethod
    def _numero_processo_valido(cls, v: Optional[str]) -> Optional[str]:
        return _validar_numero_processo_cnj(v)

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
    archived_at: Optional[datetime] = None
    archive_reason: Optional[str] = None
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


# ── R2 — Arquivamento e exclusão segura ──────────────────────────────────────
class CaseDeleteRequest(BaseModel):
    """Body do DELETE /cases/{id}: motivo obrigatório (gravado no audit log)."""
    motivo: str = Field(min_length=5, max_length=500,
                        description="Motivo da exclusão (mínimo 5 caracteres)")


class CasePendencia(BaseModel):
    """Pendência que bloqueia a exclusão do caso (retornada no 422)."""
    tipo: str        # prazo | honorario | peca
    id: str
    descricao: str


class CasePendenciasResponse(BaseModel):
    """Corpo do 422 quando a exclusão é bloqueada — usar arquivamento."""
    mensagem: str
    pendencias: List[CasePendencia]
