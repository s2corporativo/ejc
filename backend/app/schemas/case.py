# ── app/schemas/case.py ──────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date
from decimal import Decimal


# Deve casar com Case.numero_processo (String(30) em models/case.py) — um
# limite maior aqui passaria na validação e estouraria no INSERT (500).
_NUMERO_PROCESSO_MAX = 30


def _validar_numero_processo_cnj(v: Optional[str]) -> Optional[str]:
    """Valida `numero_processo` na ENTRADA (create/update).

    Regra: o caso pode ainda NÃO ter número → vazio/None PASSA (retorna None).
    A validação estrita (formato + dígito verificador módulo 97, via
    validators_service.validar_cnj) só se aplica quando o valor PARECE um
    número CNJ — 20 dígitos após remover a pontuação (com ou sem a máscara
    NNNNNNN-DD.AAAA.J.TR.OOOO). Processos ADMINISTRATIVOS (JARI/SEI/PAD etc.)
    têm numeração própria e são aceitos como texto livre, limitado à largura
    da coluna (30 caracteres). Só roda em CaseCreate/CaseUpdate — a LEITURA
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


class HonorariosCreate(BaseModel):
    """FASE 2 — honorários informados na ABERTURA do caso (objeto OPCIONAL).

    Contrato de campos ESTÁVEL com o frontend — NÃO renomear os 4 campos:
      • valor_contratual — honorários contratuais fixos, em R$.
      • percentual_exito — % de êxito sobre o proveito econômico (0 a 100).
      • forma_pagamento  — texto livre (ex.: "à vista", "3x", "conforme cláusula").
      • observacoes      — anotações do advogado sobre os honorários.

    TODOS opcionais: o caso pode abrir sem honorários. Sem este objeto (ou sem
    nenhum valor financeiro), o contrato do kit nasce com placeholders de
    revisão, exatamente como hoje. Quando há dado financeiro, os honorários são
    persistidos como proposta de honorários já vigente e o CONTRATO do kit sai
    preenchido (fee_proposal_service.seed_proposta_honorarios_cadastro).
    """
    valor_contratual: Optional[float] = None
    percentual_exito: Optional[float] = None
    forma_pagamento: Optional[str] = Field(default=None, max_length=500)
    observacoes: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("valor_contratual")
    @classmethod
    def _valor_nao_negativo(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and v < 0:
            raise ValueError("valor_contratual não pode ser negativo")
        return v

    @field_validator("percentual_exito")
    @classmethod
    def _exito_faixa(cls, v: Optional[float]) -> Optional[float]:
        # Percentual de êxito entre 0 e 100 — evita valor absurdo e o overflow
        # da coluna Numeric(5,2) de fee_proposals.exito_percentual (→ 500).
        if v is not None and not (0 <= v <= 100):
            raise ValueError("percentual_exito deve estar entre 0 e 100")
        return v


class CaseCreate(BaseModel):
    titulo: str
    area: str
    client_id: str
    prioridade: str = "media"
    proxima_acao: Optional[str] = None
    proxima_acao_prazo: Optional[datetime] = None
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
    # FASE 2 (opcional): honorários do cadastro → contrato do kit preenchido.
    honorarios: Optional[HonorariosCreate] = None
    # FLX-045 — abertura por documento: True adia triagem e kit documental até
    # o vínculo da fonte (upload/lote), em vez de rodar na criação do caso.
    aguardar_documentos: bool = False

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
    proxima_acao: Optional[str] = None
    proxima_acao_prazo: Optional[datetime] = None
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

    @field_validator("fase")
    @classmethod
    def _fase_valida(cls, v: Optional[str]) -> Optional[str]:
        # Case.fase é SAEnum(CaseFase): valor fora do enum estourava no UPDATE
        # (asyncpg InvalidTextRepresentationError → 500 não tratado; achado do
        # smoke E2E). Validar na ENTRADA devolve 422 claro. Vazio/None PASSA.
        if v is None or str(v).strip() == "":
            return v
        from app.models.case import CaseFase
        validos = {m.value for m in CaseFase}
        if v not in validos:
            raise ValueError(f"fase inválida: use um de {sorted(validos)}")
        return v

    @field_validator("status")
    @classmethod
    def _status_valido(cls, v: Optional[str]) -> Optional[str]:
        # Case.status é SAEnum(CaseStatus) — mesma classe de 500 que fase.
        if v is None or str(v).strip() == "":
            return v
        from app.models.case import CaseStatus
        validos = {m.value for m in CaseStatus}
        if v not in validos:
            raise ValueError(f"status inválido: use um de {sorted(validos)}")
        return v

    @field_validator("prioridade")
    @classmethod
    def _prioridade_valida(cls, v: Optional[str]) -> Optional[str]:
        # Case.prioridade é SAEnum(CasePrioridade) — mesma classe de 500.
        if v is None or str(v).strip() == "":
            return v
        from app.models.case import CasePrioridade
        validos = {m.value for m in CasePrioridade}
        if v not in validos:
            raise ValueError(f"prioridade inválida: use um de {sorted(validos)}")
        return v

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
    proxima_acao: Optional[str] = None
    proxima_acao_prazo: Optional[datetime] = None
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
