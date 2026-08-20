# ── app/routers/ramos_empresarial.py ────────────────────────────────────────────────────
# Sub-router do domínio empresarial — extraído de ramos.py no fatiamento P5
# (20/08/2026). Caminhos ABSOLUTOS: a montagem final é feita pelo agregador
# ramos.py sem prefixo adicional, preservando a paridade do snapshot de rotas.
# HITL: todas as saídas de cálculo são minutas — revisão humana obrigatória.

from __future__ import annotations  # noqa: F401 (reexport p/ compat)
import logging  # noqa: F401 (reexport p/ compat)
import re  # noqa: F401 (reexport p/ compat)
from calendar import monthrange  # noqa: F401 (reexport p/ compat)
from datetime import date, timedelta  # noqa: F401 (reexport p/ compat)
from decimal import Decimal  # noqa: F401 (reexport p/ compat)
from typing import Optional, Literal  # noqa: F401 (reexport p/ compat)
from uuid import uuid4  # noqa: F401 (reexport p/ compat)

from fastapi import APIRouter, Depends, HTTPException, Query, Response  # noqa: F401 (reexport p/ compat)
from pydantic import BaseModel, field_validator  # noqa: F401 (reexport p/ compat)
from sqlalchemy import select  # noqa: F401 (reexport p/ compat)
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401 (reexport p/ compat)

from app.core.config import get_settings  # noqa: F401 (reexport p/ compat)
from app.core.database import get_db  # noqa: F401 (reexport p/ compat)
from app.core.security import get_current_user, require_roles  # noqa: F401 (reexport p/ compat)
from app.models.user import User  # noqa: F401 (reexport p/ compat)
from app.models.case import Case  # noqa: F401 (reexport p/ compat)
from app.models.audit_log import criar_audit_log  # noqa: F401 (reexport p/ compat)
from app.core.ownership import verificar_acesso_caso, is_gestao  # noqa: F401 (reexport p/ compat)
from app.models.especializado import (  # noqa: F401 (reexport p/ compat)
    EmpresarialCase, EmpresarialTipo, EmpresarialStatus,
    CivelCase, CivelTipo, CivelStatus,
    PenalCase, PenalTipo, PenalFase,
    TrabalhistaCase, TrabalhistaTipo, TrabalhistaFase,
    AdminCase, AdminTipo, AdminStatus,
    BancarioCase, BancarioTipo, BancarioStatus,
)
from app.services.deadline_calculator import (  # noqa: F401 (reexport p/ compat)
    prazo_dias_uteis, prazo_dias_corridos, prazo_defesa_ambiental, proximo_dia_util,
)
from app.schemas.areas_atuacao import (  # noqa: F401 (reexport p/ compat)
    EmpresarialUpdate, CivelUpdate, PenalUpdate,
    TrabalhistaUpdate, AdminUpdate, BancarioUpdate,
    validar_tipo_societario,
)
from app.routers.ramos_comum import (  # noqa: F401 (reexport p/ compat)
    logger,  # logger de módulo; handlers o usam diretamente
    _EQUIPE, _ADM, _CENT, TETOS_DEPOSITO_RECURSAL, _teto_deposito_para,
    _SIM_NAO, _parse_sim_nao, _VERSAO_REGRA, VERSAO_REGRA_ATUAL,
    _SUNSET_DUPLICATAS, _DUPLICATAS_DEPRECIADAS, _marcar_depreciada,
    _REGRAS_FERRAMENTAS, _com_regra,
    _get_case, _serialize, _casos_visiveis_subq,
    _crud_listar, _crud_atualizar, _crud_remover,
    _add_anos_data,
    _SUSPENSAO_LEGAL, _atravessa_recesso, _info_suspensao,
    _prazo_util_com_recesso, _prazo_corrido_com_recesso,
    _ultimo_dia_do_mes, _add_meses_data,
    _prescricao_prazo_anos, _prescricao_penal_consolidada,
    _classificar_taxa_vs_media, _sm_vigente,
    _LIMIARES_TAXA_MEDIA,
)
from app.services.homologacao_ferramentas import (  # noqa: F401 (reexport p/ compat)
    FERRAMENTAS_BLOQUEADAS,
    FERRAMENTAS_NAO_HOMOLOGADAS,
    normalizar_caminho_ferramenta,
    selo_homologacao as _selo_homologacao,
)
# `bloquear_nao_homologada` NÃO é importado aqui: nenhuma ferramenta está
# bloqueada hoje (FERRAMENTAS_BLOQUEADAS vazio). O mecanismo continua vivo no
# módulo de homologação — para bloquear uma ferramenta, importe a função no
# handler e adicione o caminho ao frozenset.

router = APIRouter(tags=["Áreas de Atuação"])

# 1. EMPRESARIAL (/empresarial)
# ════════════════════════════════════════════════════════════════════════════
class EmpresarialIn(BaseModel):
    case_id: str
    tipo: EmpresarialTipo = EmpresarialTipo.contrato_empresarial
    status: EmpresarialStatus = EmpresarialStatus.diagnostico
    cnpj_empresa: Optional[str] = None
    tipo_societario: Optional[str] = None
    capital_social: Optional[float] = None
    nire: Optional[str] = None
    data_distribuicao_rj: Optional[date] = None
    valor_passivo_total: Optional[float] = None
    numero_credores: Optional[int] = None
    ato_concentracao_notificado: bool = False
    data_notificacao_cade: Optional[date] = None
    valor_operacao: Optional[float] = None
    numero_processo_inpi: Optional[str] = None
    tipo_pi: Optional[str] = None
    regime_tributario: Optional[str] = None
    debito_fiscal_total: Optional[float] = None
    em_parcelamento: bool = False
    num_reclamacoes_trabalhistas: Optional[int] = None
    valor_passivo_trabalhista: Optional[float] = None
    honorarios_tipo: Optional[str] = None
    observacoes: Optional[str] = None

    # EIRELI extinta (Lei 14.195/2021) — rejeitada em registros novos com 422.
    _valida_tipo_societario = field_validator("tipo_societario")(validar_tipo_societario)


@router.get("/empresarial/tipos")
async def emp_tipos(cu: User = Depends(get_current_user)):
    """Tipos disponíveis de matéria empresarial."""
    return {
        "tipos": [
            {"value": t.value, "label": t.value.replace("_", " ").title()}
            for t in EmpresarialTipo
        ]
    }


@router.get("/empresarial")
async def emp_listar(
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
    tipo: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),):
    return await _crud_listar(EmpresarialCase, db, tipo, limit, offset, cu)

@router.post("/empresarial", status_code=201)
async def emp_criar(body: EmpresarialIn, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(require_roles(_EQUIPE))):
    await _get_case(db, body.case_id, cu)
    e = EmpresarialCase(id=str(uuid4()), **body.model_dump())
    db.add(e)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "empresarial_cases", e.id)
    await db.commit()
    return _serialize(e)


@router.patch("/empresarial/{eid}")
async def emp_atualizar(eid: str, body: EmpresarialUpdate, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(EmpresarialCase, "empresarial_cases", eid,
                                 body.model_dump(exclude_unset=True), db, cu)

@router.delete("/empresarial/{eid}")
async def emp_remover(eid: str, db: AsyncSession = Depends(get_db),
                      cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(EmpresarialCase, "empresarial_cases", eid, db, cu)

# ── Ferramentas Empresariais ──────────────────────────────────────────────────
@router.get("/empresarial/ferramentas/prazos-rj")
async def emp_prazos_rj(
    data_publicacao_deferimento: Optional[date] = None,
    data_deferimento: Optional[date] = None,
    data_concessao: Optional[date] = None,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Marcos temporais da recuperação judicial — Lei 11.101/2005 (red. Lei 14.112/2020).
    NENHUM marco conta da distribuição; cada um tem termo inicial próprio:
      • plano (art. 53): 60 dias da PUBLICAÇÃO da decisão que defere o processamento;
      • stay period (art. 6º §4º): 180 dias do deferimento, prorrogável 1x por igual período;
      • AGC para deliberar o plano, havendo objeção (art. 56 §1º): até 150 dias do deferimento;
      • supervisão judicial (art. 61): até 2 anos da CONCESSÃO da recuperação.
    Informe a(s) data(s) de que dispõe — só os marcos correspondentes são calculados.
    MINUTA — o advogado valida com o juízo e o administrador judicial.
    """
    if not any((data_publicacao_deferimento, data_deferimento, data_concessao)):
        raise HTTPException(422, (
            "Informe ao menos um termo inicial: data_publicacao_deferimento (plano, art. 53), "
            "data_deferimento (stay period art. 6º §4º e AGC art. 56 §1º) ou "
            "data_concessao (supervisão judicial, art. 61)."))
    marcos: list[dict] = []
    marcos_nao_calculados: list[str] = []
    if data_publicacao_deferimento:
        marcos.append({
            "evento": "Apresentação do plano de recuperação",
            "marco_inicial": "publicação da decisão que defere o processamento",
            "data": prazo_dias_corridos(data_publicacao_deferimento, 60, prorrogar_fim=False),
            "prazo": "60 dias corridos, improrrogável — sob pena de convolação em falência (art. 73 II)",
            "base": "Lei 11.101/2005 art. 53",
        })
    else:
        marcos_nao_calculados.append("plano de recuperação (art. 53) — falta data_publicacao_deferimento")
    if data_deferimento:
        marcos.append({
            "evento": "Fim do stay period (suspensão das execuções)",
            "marco_inicial": "decisão que defere o processamento",
            "data": prazo_dias_corridos(data_deferimento, 180, prorrogar_fim=False),
            "data_com_prorrogacao_maxima": prazo_dias_corridos(data_deferimento, 360, prorrogar_fim=False),
            "prazo": "180 dias, prorrogável UMA única vez por igual período (excepcionalmente)",
            "base": "Lei 11.101/2005 art. 6º §4º (red. Lei 14.112/2020)",
        })
        marcos.append({
            "evento": "AGC para deliberar sobre o plano (se houver objeção de credor)",
            "marco_inicial": "decisão que defere o processamento",
            "data": prazo_dias_corridos(data_deferimento, 150, prorrogar_fim=False),
            "prazo": "até 150 dias",
            "base": "Lei 11.101/2005 art. 56 §1º",
        })
    else:
        marcos_nao_calculados.append(
            "stay period (art. 6º §4º) e AGC (art. 56 §1º) — falta data_deferimento")
    if data_concessao:
        marcos.append({
            "evento": "Fim da supervisão judicial",
            "marco_inicial": "decisão que CONCEDE a recuperação judicial (art. 58)",
            "data": _add_anos_data(data_concessao, 2),
            "prazo": "até 2 anos",
            "base": "Lei 11.101/2005 art. 61 (red. Lei 14.112/2020)",
        })
    else:
        marcos_nao_calculados.append("supervisão judicial (art. 61) — falta data_concessao")
    return {
        "marcos": marcos,
        "marcos_nao_calculados": marcos_nao_calculados,
        "fontes": [
            "Lei 11.101/2005 arts. 6º §4º, 53, 56 §1º, 58, 61 e 73 II",
            "Lei 14.112/2020 (reforma da Lei de Recuperação e Falência)",
        ],
        "vigencia_regra": "Lei 11.101/2005 com a redação da Lei 14.112/2020, vigente desde 23/01/2021",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Datas em dias corridos, sem prorrogação "
                  "automática para dia útil: confirme a contagem aplicada pelo juízo da recuperação "
                  "e eventuais suspensões com o administrador judicial."),
    }


@router.get("/empresarial/ferramentas/verificar-cade")
async def emp_cade(valor_faturamento_br: float, valor_operacao: float,
                   valor_faturamento_outro_grupo: Optional[float] = None,
                   cu: User = Depends(require_roles(_EQUIPE))):
    """
    Verifica obrigatoriedade de notificação ao CADE (controle de concentrações).
    Lei 12.529/2011 art. 88, I e II (patamares atualizados pela Portaria Interminis-
    terial MJ/MF 994/2012): a notificação é OBRIGATÓRIA quando, cumulativamente,
    um grupo econômico envolvido faturou ≥ R$ 750 mi E OUTRO grupo ≥ R$ 75 mi no
    Brasil, no ano anterior. São dois limiares CUMULATIVOS — não basta um só grupo.
    Os limiares NÃO são posicionais: basta UM dos grupos atingir R$ 750 mi e o
    OUTRO atingir R$ 75 mi, independentemente de qual valor foi informado em qual
    campo (avaliação por max/min dos dois faturamentos).
    - valor_faturamento_br: faturamento de um dos grupos envolvidos.
    - valor_faturamento_outro_grupo: faturamento do segundo grupo envolvido.
      Retrocompatível: se não informado, não há como confirmar o inciso II. Nesse
      caso NÃO devolvemos um falso "não obrigatória" — sinalizamos pendência de
      dado (pendente_dado=True, notificacao_obrigatoria=None).
    """
    limiar_grupo_maior = 750_000_000.00   # art. 88, I (atualizado p/ R$ 750 mi)
    limiar_grupo_menor = 75_000_000.00    # art. 88, II (atualizado p/ R$ 75 mi)
    segundo_informado = valor_faturamento_outro_grupo is not None

    # Não há "prazo de 30 dias para notificar": o controle é PRÉVIO — a operação
    # não pode ser consumada antes da decisão do CADE (gun jumping, art. 88 §3º).
    controle_previo = ("Controle PRÉVIO (Lei 12.529/2011 art. 88): não há prazo de 30 dias "
                       "para notificar — a operação NÃO pode ser consumada antes da decisão "
                       "do CADE, sob pena de gun jumping (nulidade e multa, art. 88 §3º).")

    fontes_cade = [
        "Lei 12.529/2011 art. 88, I-III e §§2º-3º",
        "Portaria Interministerial MJ/MF nº 994/2012 (atualização dos limiares)",
    ]
    vigencia_cade = "Lei 12.529/2011 · limiares da Portaria 994/2012, vigentes desde 30/05/2012"
    if not segundo_informado:
        # Sem o faturamento do 2º grupo é impossível confirmar o inciso II. Em vez
        # de um falso negativo, devolvemos estado pendente (retrocompat. c/ API).
        return {
            "faturamento_informado": valor_faturamento_br,
            "faturamento_outro_grupo": None,
            "valor_operacao": valor_operacao,
            "grupo_maior_atinge_750mi": valor_faturamento_br >= limiar_grupo_maior,
            "grupo_menor_atinge_75mi": None,
            "segundo_grupo_informado": False,
            "pendente_dado": True,
            "notificacao_obrigatoria": None,
            "controle_previo": controle_previo,
            "taxa_cade_estimada": "N/A",
            "fontes": fontes_cade,
            "vigencia_regra": vigencia_cade,
            "versao_regra": _VERSAO_REGRA,
            "aviso": ("MINUTA. Informe o faturamento do 2º grupo envolvido para avaliar o "
                      "art. 88 (limiar de R$ 75 mi do inciso II). Análise de enquadramento "
                      "deve ser confirmada por especialista antitruste."),
        }

    # Cumulativos mas NÃO posicionais: um grupo ≥ 750 mi E outro ≥ 75 mi (art. 88,
    # I e II), avaliando por max/min dos dois faturamentos informados.
    maior = max(valor_faturamento_br, valor_faturamento_outro_grupo)
    menor = min(valor_faturamento_br, valor_faturamento_outro_grupo)
    grupo_maior_atinge = maior >= limiar_grupo_maior
    grupo_menor_atinge = menor >= limiar_grupo_menor
    obrigatorio = grupo_maior_atinge and grupo_menor_atinge
    return {
        "faturamento_informado": valor_faturamento_br,
        "faturamento_outro_grupo": valor_faturamento_outro_grupo,
        "valor_operacao": valor_operacao,
        "grupo_maior_atinge_750mi": grupo_maior_atinge,
        "grupo_menor_atinge_75mi": grupo_menor_atinge,
        "segundo_grupo_informado": True,
        "pendente_dado": False,
        "notificacao_obrigatoria": obrigatorio,
        "controle_previo": controle_previo,
        # Taxa (TFPP) de referência — NÃO é leitura da tabela CADE vigente; valor
        # fixo de orientação, sujeito a reajuste. Confirmar na tabela CADE atual.
        "taxa_cade_estimada": "~R$ 85.000 (estimativa de referência — confirmar tabela CADE vigente)" if obrigatorio else "N/A",
        "fontes": fontes_cade,
        "vigencia_regra": vigencia_cade,
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA. Análise de enquadramento deve ser confirmada por especialista antitruste.",
    }


# ════════════════════════════════════════════════════════════════════════════
# 2. CÍVEL (/civel)
