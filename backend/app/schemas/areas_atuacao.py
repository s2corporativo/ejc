# ── app/schemas/areas_atuacao.py ──────────────────────────────────────────────
# Schemas de ATUALIZAÇÃO (PATCH) dos 6 ramos especializados (routers/ramos.py).
# Onda 1 da auditoria de Áreas de Atuação — bloqueio de mass assignment:
#   • extra="forbid": qualquer campo fora da whitelist (deleted_at, case_id,
#     created_at, updated_at, id, campo desconhecido) → 422.
#   • Todos os campos opcionais; o handler usa model_dump(exclude_unset=True),
#     preservando o comportamento de patch parcial de _crud_atualizar.
# Whitelist espelha as colunas EDITÁVEIS de app/models/especializado.py,
# EXCLUINDO campos de controle (id, case_id, created_at, updated_at, deleted_at).
from __future__ import annotations
from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

from app.models.especializado import (
    EmpresarialTipo, EmpresarialStatus,
    CivelTipo, CivelStatus,
    PenalTipo, PenalFase,
    TrabalhistaTipo, TrabalhistaFase,
    AdminTipo, AdminStatus,
    BancarioTipo, BancarioStatus,
)

MENSAGEM_EIRELI = ("EIRELI foi extinta — registros novos devem usar SLU/LTDA; "
                   "registros históricos são preservados")


def validar_tipo_societario(v: Optional[str]) -> Optional[str]:
    """Rejeita EIRELI em registros novos/atualizados (Lei 14.195/2021 extinguiu
    a figura; empresas existentes foram convertidas em SLU). Dados históricos
    já gravados NÃO são alterados — o bloqueio vale só para entrada nova."""
    if v and v.strip().upper() == "EIRELI":
        raise ValueError(MENSAGEM_EIRELI)
    return v


class _AreaUpdateBase(BaseModel):
    """Base dos PATCHes por área: whitelist explícita + extra proibido."""
    model_config = ConfigDict(extra="forbid")


class EmpresarialUpdate(_AreaUpdateBase):
    tipo: Optional[EmpresarialTipo] = None
    status: Optional[EmpresarialStatus] = None
    cnpj_empresa: Optional[str] = None
    tipo_societario: Optional[str] = None
    capital_social: Optional[float] = None
    nire: Optional[str] = None
    data_distribuicao_rj: Optional[date] = None
    data_aprovacao_plano: Optional[date] = None
    valor_passivo_total: Optional[float] = None
    numero_credores: Optional[int] = None
    ato_concentracao_notificado: Optional[bool] = None
    data_notificacao_cade: Optional[date] = None
    valor_operacao: Optional[float] = None
    numero_processo_inpi: Optional[str] = None
    tipo_pi: Optional[str] = None
    num_reclamacoes_trabalhistas: Optional[int] = None
    valor_passivo_trabalhista: Optional[float] = None
    regime_tributario: Optional[str] = None
    debito_fiscal_total: Optional[float] = None
    em_parcelamento: Optional[bool] = None
    data_encerramento_estimado: Optional[date] = None
    honorarios_tipo: Optional[str] = None
    observacoes: Optional[str] = None

    _valida_tipo_societario = field_validator("tipo_societario")(validar_tipo_societario)


class CivelUpdate(_AreaUpdateBase):
    tipo: Optional[CivelTipo] = None
    status: Optional[CivelStatus] = None
    valor_causa: Optional[float] = None
    competencia: Optional[str] = None
    polo_ativo: Optional[str] = None
    tutela_urgencia: Optional[bool] = None
    data_tutela: Optional[date] = None
    regime_bens: Optional[str] = None
    filhos_menores: Optional[int] = None
    guarda_tipo: Optional[str] = None
    alimentos_valor: Optional[float] = None
    alimentos_percentual: Optional[float] = None
    data_separacao: Optional[date] = None
    tipo_imovel: Optional[str] = None
    matricula_imovel: Optional[str] = None
    area_m2: Optional[float] = None
    valor_imovel: Optional[float] = None
    data_posse: Optional[date] = None
    anos_posse: Optional[float] = None
    fornecedor: Optional[str] = None
    numero_contrato: Optional[str] = None
    valor_pedido: Optional[float] = None
    dano_moral_pedido: Optional[float] = None
    data_fato: Optional[date] = None
    protocolo_procon: Optional[str] = None
    data_citacao: Optional[date] = None
    data_contestacao: Optional[date] = None
    data_audiencia: Optional[date] = None
    resultado: Optional[str] = None
    observacoes: Optional[str] = None


class PenalUpdate(_AreaUpdateBase):
    tipo_crime: Optional[PenalTipo] = None
    fase: Optional[PenalFase] = None
    numero_bo: Optional[str] = None
    numero_ip: Optional[str] = None
    delegacia: Optional[str] = None
    data_fato: Optional[date] = None
    local_fato: Optional[str] = None
    polo: Optional[str] = None
    preso: Optional[bool] = None
    tipo_prisao: Optional[str] = None
    data_prisao: Optional[date] = None
    data_alvara: Optional[date] = None
    fianca_valor: Optional[float] = None
    artigo_imputado: Optional[str] = None
    pena_min_anos: Optional[float] = None
    pena_max_anos: Optional[float] = None
    pena_aplicada: Optional[str] = None
    sursis: Optional[bool] = None
    pena_alternativa: Optional[bool] = None
    anpp_proposto: Optional[bool] = None
    anpp_aceito: Optional[bool] = None
    anpp_condicoes: Optional[str] = None
    data_denuncia: Optional[date] = None
    prazo_resposta_acusacao: Optional[date] = None
    data_audiencia: Optional[date] = None
    resultado: Optional[str] = None
    observacoes: Optional[str] = None


class TrabalhistaUpdate(_AreaUpdateBase):
    tipo: Optional[TrabalhistaTipo] = None
    fase: Optional[TrabalhistaFase] = None
    polo: Optional[str] = None
    salario_base: Optional[float] = None
    data_admissao: Optional[date] = None
    data_demissao: Optional[date] = None
    tipo_rescisao: Optional[str] = None
    cargo: Optional[str] = None
    cbo: Optional[str] = None
    regime_contratacao: Optional[str] = None
    valor_causa_estimado: Optional[float] = None
    horas_extras_semana: Optional[float] = None
    adicional_percentual: Optional[float] = None
    data_acidente: Optional[date] = None
    cat_emitida: Optional[bool] = None
    cid: Optional[str] = None
    afastamento_dias: Optional[int] = None
    sequela_permanente: Optional[bool] = None
    dano_moral_pedido: Optional[float] = None
    dano_moral_concedido: Optional[float] = None
    deposito_recursal: Optional[float] = None
    valor_acordo: Optional[float] = None
    valor_condenacao: Optional[float] = None
    prazo_recurso_ordinario: Optional[date] = None
    data_audiencia_inaugural: Optional[date] = None
    resultado: Optional[str] = None
    observacoes: Optional[str] = None


class AdminUpdate(_AreaUpdateBase):
    tipo: Optional[AdminTipo] = None
    status: Optional[AdminStatus] = None
    numero_auto_infracao: Optional[str] = None
    orgao_autuador: Optional[str] = None
    data_infracao: Optional[date] = None
    data_notificacao: Optional[date] = None
    codigo_infracao: Optional[str] = None
    valor_multa_original: Optional[float] = None
    valor_com_desconto: Optional[float] = None
    pontuacao_cnh: Optional[int] = None
    suspensao_cnh: Optional[bool] = None
    prazo_recurso_1a_inst: Optional[date] = None
    prazo_recurso_2a_inst: Optional[date] = None
    protocolo_recurso: Optional[str] = None
    data_ato_coator: Optional[date] = None
    prazo_ms: Optional[date] = None
    autoridade_coatora: Optional[str] = None
    numero_pad: Optional[str] = None
    cargo_servidor: Optional[str] = None
    penalidade_imputada: Optional[str] = None
    resultado: Optional[str] = None
    observacoes: Optional[str] = None


class BancarioUpdate(_AreaUpdateBase):
    tipo: Optional[BancarioTipo] = None
    status: Optional[BancarioStatus] = None
    instituicao_financeira: Optional[str] = None
    numero_contrato: Optional[str] = None
    modalidade_credito: Optional[str] = None
    data_contrato: Optional[date] = None
    valor_contratado: Optional[float] = None
    valor_pago: Optional[float] = None
    taxa_mensal_contratada: Optional[float] = None
    taxa_mensal_legal: Optional[float] = None
    cet_contratado: Optional[float] = None
    spread_excessivo: Optional[bool] = None
    saldo_devedor_declarado: Optional[float] = None
    saldo_devedor_revisado: Optional[float] = None
    valor_cobrado_indevido: Optional[float] = None
    negativado: Optional[bool] = None
    orgao_negativacao: Optional[str] = None
    data_negativacao: Optional[date] = None
    valor_negativado: Optional[float] = None
    dano_moral_pedido: Optional[float] = None
    superendividamento: Optional[bool] = None
    renda_mensal: Optional[float] = None
    total_dividas: Optional[float] = None
    minimo_existencial: Optional[bool] = None
    data_notificacao_ba: Optional[date] = None
    prazo_purga: Optional[date] = None
    bem_garantia: Optional[str] = None
    resultado: Optional[str] = None
    observacoes: Optional[str] = None
