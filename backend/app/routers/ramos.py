# ── app/routers/ramos.py ──────────────────────────────────────────────────────
# Routers dos 6 ramos jurídicos especializados (além do Ambiental já existente).
# Padrão: CRUD + calculadoras/ferramentas específicas de cada área.
# Cada ramo tem: listar / criar / atualizar / remover (soft-delete) + ferramentas.
# HITL: todas as saídas de cálculo são minutas — revisão humana obrigatória.
from __future__ import annotations
import re
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import get_current_user, require_roles
from app.models.user import User
from app.models.case import Case
from app.models.audit_log import criar_audit_log
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.models.especializado import (
    EmpresarialCase, EmpresarialTipo, EmpresarialStatus,
    CivelCase, CivelTipo, CivelStatus,
    PenalCase, PenalTipo, PenalFase,
    TrabalhistaCase, TrabalhistaTipo, TrabalhistaFase,
    AdminCase, AdminTipo, AdminStatus,
    BancarioCase, BancarioTipo, BancarioStatus,
)
from app.services.deadline_calculator import (
    prazo_dias_uteis, prazo_dias_corridos, prazo_defesa_ambiental,
)
from app.schemas.areas_atuacao import (
    EmpresarialUpdate, CivelUpdate, PenalUpdate,
    TrabalhistaUpdate, AdminUpdate, BancarioUpdate,
    validar_tipo_societario,
)
from app.services.homologacao_ferramentas import (  # noqa: F401 (reexport p/ compat)
    FERRAMENTAS_BLOQUEADAS,
    FERRAMENTAS_NAO_HOMOLOGADAS,
    bloquear_nao_homologada as _bloquear_nao_homologada,
    selo_homologacao as _selo_homologacao,
)

_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]
_ADM    = ["superadmin", "admin", "socio"]
_CENT   = Decimal("0.01")

# ── Tetos do depósito recursal trabalhista (CLT art. 899 §§1º-4º) ─────────────
# ATENÇÃO — ATUALIZAÇÃO ANUAL OBRIGATÓRIA: o TST reajusta estes tetos pelo IPCA-E
# e publica novo Ato de GP (jan/ago de cada ano). Valores abaixo = 2026
# (Ato TST GP 323/2025 — referência). Conferir a portaria vigente na data do
# recurso antes de usar em produção; NÃO deixar defasar.
TETO_DEPOSITO_RO = 12_127.64   # Recurso Ordinário
TETO_DEPOSITO_RR = 24_255.28   # Recurso de Revista (dobro do RO)

router = APIRouter(tags=["Áreas de Atuação"])

# SELO DE HOMOLOGAÇÃO — Onda 1: matriz e helpers vivem em módulo neutro
# (app/services/homologacao_ferramentas.py), compartilhado com o gate de
# /pecas/demonstrativo sem acoplamento router→router.

# ── Validação sim/não explícita (sem fallback silencioso) ────────────────────
_SIM_NAO = {"sim": True, "true": True, "1": True,
            "nao": False, "não": False, "false": False, "0": False}


def _parse_sim_nao(valor: str, campo: str) -> bool:
    """Converte parâmetro sim/não. Valor fora do domínio → 422 (não cai em default)."""
    v = (valor or "").strip().lower()
    if v not in _SIM_NAO:
        raise HTTPException(422, f"Valor inválido para '{campo}': '{valor}'. Use: sim | nao")
    return _SIM_NAO[v]


# Versão do conjunto de regras jurídicas embarcadas nas ferramentas corrigidas
# na Onda 2 — carimbada em toda resposta (campo `versao_regra`).
_VERSAO_REGRA = "2026-07"


# ════════════════════════════════════════════════════════════════════════════
# HELPERS COMUNS
# ════════════════════════════════════════════════════════════════════════════
async def _get_case(db: AsyncSession, case_id: str, user: User) -> Case:
    """Valida existência + ownership do caso (gate canônico, inclui auxiliar e
    salvaguarda anti-lockout). Fonte única: core.ownership.verificar_acesso_caso."""
    return await verificar_acesso_caso(db, user, case_id)


def _serialize(obj) -> dict:
    """Serializa um modelo ORM em dict SEM vazar `_sa_instance_state`."""
    return {c.key: getattr(obj, c.key) for c in obj.__table__.columns}


def _casos_visiveis_subq(cu: User):
    """Subquery dos IDs de casos visíveis ao usuário (espelha verificar_acesso_caso)."""
    return select(Case.id).where(
        Case.deleted_at.is_(None),
        (
            (Case.advogado_responsavel_id == cu.id)
            | (Case.advogado_auxiliar_id == cu.id)
            | (Case.advogado_responsavel_id.is_(None) & Case.advogado_auxiliar_id.is_(None))
        ),
    )


# ── CRUD compartilhado ────────────────────────────────────────────────────────
# A lógica de listar/atualizar/remover é idêntica entre os 6 ramos. Para evitar
# duplicação mantendo cada rota EXPLÍCITA e auditável, cada handler delega para
# estes helpers. Comportamento preservado: filtro por tipo, soft-delete, audit
# log, whitelist de colunas no patch.
async def _crud_listar(Model, db: AsyncSession, tipo: Optional[str],
                       limit: int, offset: int, cu: User) -> dict:
    q = select(Model).where(Model.deleted_at.is_(None))
    if tipo and hasattr(Model, "tipo"):
        q = q.where(Model.tipo == tipo)
    # Ownership por caso (IDOR): não-gestão só vê registros dos seus casos.
    if not is_gestao(cu):
        q = q.where(Model.case_id.in_(_casos_visiveis_subq(cu)))
    rows = (await db.execute(
        q.order_by(Model.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return {"data": [_serialize(r) for r in rows]}


async def _crud_atualizar(Model, table: str, item_id: str, body: dict,
                          db: AsyncSession, cu: User) -> dict:
    obj = (await db.execute(
        select(Model).where(Model.id == item_id, Model.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Registro não encontrado")
    # Ownership por caso (IDOR): só edita registros de casos a que tem acesso.
    await verificar_acesso_caso(db, cu, obj.case_id)
    # Defesa em profundidade: os schemas de app/schemas/areas_atuacao.py já são
    # a fronteira (extra="forbid"), mas esta exclusão protege callers futuros
    # que passem dict cru — campos de controle jamais são atribuíveis.
    allowed = {c.key for c in Model.__table__.columns
               if c.key not in ("id", "case_id", "created_at", "updated_at", "deleted_at")}
    for k, v in body.items():
        if k in allowed:
            setattr(obj, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", table, item_id)
    await db.commit()
    return _serialize(obj)


async def _crud_remover(Model, table: str, item_id: str,
                        db: AsyncSession, cu: User) -> dict:
    from sqlalchemy import func as sqlfunc
    obj = (await db.execute(
        select(Model).where(Model.id == item_id, Model.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404)
    # Ownership por caso (IDOR): só remove registros de casos a que tem acesso.
    await verificar_acesso_caso(db, cu, obj.case_id)
    obj.deleted_at = sqlfunc.now()
    await criar_audit_log(db, cu.id, cu.role.value, "DELETE", table, item_id)
    await db.commit()
    return {"detail": "Removido"}


# ════════════════════════════════════════════════════════════════════════════
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

    if not segundo_informado:
        # Sem o faturamento do 2º grupo é impossível confirmar o inciso II. Em vez
        # de um falso negativo, devolvemos estado pendente (retrocompat. c/ API).
        return _selo_homologacao("/empresarial/ferramentas/verificar-cade", {
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
            "base": "Lei 12.529/2011 art. 88, I-III c/c Portaria Interm. MJ/MF 994/2012.",
            "aviso": ("MINUTA. Informe o faturamento do 2º grupo envolvido para avaliar o "
                      "art. 88 (limiar de R$ 75 mi do inciso II). Análise de enquadramento "
                      "deve ser confirmada por especialista antitruste."),
        })

    # Cumulativos mas NÃO posicionais: um grupo ≥ 750 mi E outro ≥ 75 mi (art. 88,
    # I e II), avaliando por max/min dos dois faturamentos informados.
    maior = max(valor_faturamento_br, valor_faturamento_outro_grupo)
    menor = min(valor_faturamento_br, valor_faturamento_outro_grupo)
    grupo_maior_atinge = maior >= limiar_grupo_maior
    grupo_menor_atinge = menor >= limiar_grupo_menor
    obrigatorio = grupo_maior_atinge and grupo_menor_atinge
    return _selo_homologacao("/empresarial/ferramentas/verificar-cade", {
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
        "base": "Lei 12.529/2011 art. 88, I-III c/c Portaria Interm. MJ/MF 994/2012.",
        "aviso": "MINUTA. Análise de enquadramento deve ser confirmada por especialista antitruste.",
    })


# ════════════════════════════════════════════════════════════════════════════
# 2. CÍVEL (/civel)
# ════════════════════════════════════════════════════════════════════════════
class CivelIn(BaseModel):
    case_id: str
    tipo: CivelTipo
    status: CivelStatus = CivelStatus.pre_processual
    valor_causa: Optional[float] = None
    competencia: Optional[str] = None
    polo_ativo: Optional[str] = None
    tutela_urgencia: bool = False
    data_tutela: Optional[date] = None
    regime_bens: Optional[str] = None
    filhos_menores: int = 0
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
    valor_pedido: Optional[float] = None
    dano_moral_pedido: Optional[float] = None
    data_fato: Optional[date] = None
    protocolo_procon: Optional[str] = None
    data_citacao: Optional[date] = None
    observacoes: Optional[str] = None


@router.get("/civel")
async def civ_listar(db: AsyncSession = Depends(get_db),
                     cu: User = Depends(get_current_user),
                     tipo: Optional[str] = None,
                     limit: int = 50, offset: int = 0):
    return await _crud_listar(CivelCase, db, tipo, limit, offset, cu)

@router.post("/civel", status_code=201)
async def civ_criar(body: CivelIn, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(require_roles(_EQUIPE))):
    await _get_case(db, body.case_id, cu)
    data = body.model_dump()
    # Auto-calcular prazos de contestação e audiência se data_citacao fornecida
    if data.get("data_citacao"):
        cit = data["data_citacao"]
        tipo = data["tipo"]
        if tipo == "jec":
            data["data_contestacao"] = prazo_dias_corridos(cit, 10)   # Lei 9.099 art. 30
        else:
            data["data_contestacao"] = prazo_dias_uteis(cit, 15)      # CPC art. 335
    c = CivelCase(id=str(uuid4()), **data)
    db.add(c)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "civel_cases", c.id)
    await db.commit()
    return _serialize(c)


@router.patch("/civel/{cid}")
async def civ_atualizar(cid: str, body: CivelUpdate, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(CivelCase, "civel_cases", cid,
                                 body.model_dump(exclude_unset=True), db, cu)

@router.delete("/civel/{cid}")
async def civ_remover(cid: str, db: AsyncSession = Depends(get_db),
                      cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(CivelCase, "civel_cases", cid, db, cu)

# ── Ferramentas Cível ─────────────────────────────────────────────────────────
_MARCOS_CONTESTACAO = {
    "audiencia_conciliacao": "audiência de conciliação/mediação — CPC art. 335 I",
    "juntada_citacao": "juntada aos autos do comprovante de citação — CPC art. 335 III c/c art. 231",
}


@router.get("/civel/ferramentas/prazos-contestacao")
async def civ_prazo_contestacao(
    rito: Literal["comum", "jec", "fazenda_publica"],
    marco: Optional[Literal["audiencia_conciliacao", "juntada_citacao"]] = None,
    data_marco: Optional[date] = None,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazo de contestação por rito.
    • Rito comum: 15 dias ÚTEIS (CPC arts. 335 e 219), contados do marco do art. 335
      (audiência de conciliação ou juntada do comprovante de citação).
    • Fazenda Pública: prazo em DOBRO = 30 dias úteis (CPC art. 183). O antigo
      "quádruplo para contestar" (CPC/1973 art. 188) NÃO existe no CPC/2015.
    • JEC: NÃO há prazo universal em dias — a resposta é apresentada até a audiência
      de instrução, conforme o rito concentrado (Lei 9.099/95 arts. 28 e 30); prazos
      que o juiz fixar em dias contam-se em dias ÚTEIS (art. 12-A, Lei 13.728/2018).
    MINUTA — revisão humana obrigatória.
    """
    fontes = [
        "CPC (Lei 13.105/2015) arts. 219, 231, 335 e 183",
        "Lei 9.099/95 arts. 12-A, 28 e 30",
        "Lei 13.728/2018 (dias úteis nos Juizados — art. 12-A)",
    ]
    comuns = {
        "fontes": fontes,
        "vigencia_regra": "CPC/2015 (vigente desde 18/03/2016) · Lei 9.099/95 com art. 12-A "
                          "incluído pela Lei 13.728/2018 (vigente desde 31/10/2018)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA — revisão humana obrigatória. Verifique suspensões, recesso (CPC art. 220) "
                 "e especificidades do juízo.",
    }
    if rito == "jec":
        return {
            "rito": "jec",
            "prazo_calculado": None,
            "exige_ato_judicial_concreto": True,
            "orientacao": ("No JEC não existe prazo universal de contestação em dias: a resposta "
                           "(escrita ou oral) é apresentada até a audiência de instrução e "
                           "julgamento, conforme o rito concentrado dos arts. 28 e 30 da Lei "
                           "9.099/95. Quando o juiz fixar prazo em dias, a contagem é em dias "
                           "ÚTEIS (art. 12-A, incluído pela Lei 13.728/2018). Verifique a data da "
                           "audiência e eventual prazo fixado no ato judicial concreto."),
            **comuns,
        }
    if rito not in ("comum", "fazenda_publica"):
        raise HTTPException(422, "Rito inválido. Use: comum | jec | fazenda_publica")
    if marco is None or data_marco is None:
        raise HTTPException(422, (
            "Para o rito comum/fazenda pública informe `marco` (audiencia_conciliacao | "
            "juntada_citacao — CPC art. 335) e `data_marco` (data do marco)."))
    if marco not in _MARCOS_CONTESTACAO:
        raise HTTPException(422, f"Marco inválido. Use: {list(_MARCOS_CONTESTACAO)}")
    em_dobro = rito == "fazenda_publica"
    venc = prazo_dias_uteis(data_marco, 15, em_dobro=em_dobro)
    return {
        "rito": rito,
        "marco": marco,
        "marco_descricao": _MARCOS_CONTESTACAO[marco],
        "data_marco": data_marco,
        "prazo": "30 dias úteis (15 em dobro — CPC art. 183)" if em_dobro else "15 dias úteis",
        "vencimento": venc,
        "base_legal": ("CPC art. 335 c/c arts. 219 e 183 (prazo em dobro da Fazenda Pública)"
                       if em_dobro else "CPC art. 335 c/c art. 219 (contagem em dias úteis)"),
        **comuns,
    }


@router.get("/civel/ferramentas/alimentos-calcular")
async def civ_alimentos(salario_devedor: float, percentual: float,
                        filhos: int = 1, cu: User = Depends(require_roles(_EQUIPE))):
    """
    Estimativa de alimentos proporcionais ao salário.
    Não existe percentual jurisprudencial fixo: o valor depende das necessidades
    do alimentando, dos recursos do alimentante e das circunstâncias provadas.
    Base: CC art. 1.694 §1º e Lei 5.478/68. A Súmula 277/STJ trata apenas do
    termo inicial na investigação de paternidade e não fundamenta percentual.
    MINUTA — cálculo aritmético de apoio a partir do percentual informado.
    """
    valor = round(salario_devedor * (percentual / 100), 2)
    sm = _sm_vigente()
    return {
        "salario_devedor": salario_devedor,
        "percentual": percentual,
        "filhos": filhos,
        "valor_mensal": valor,
        "em_sm": round(valor / sm, 2),
        "base": "CC art. 1.694 §1º + Lei 5.478/68",
        "referencia": "Percentual informado pelo usuário; não há tabela ou padrão fixo do STJ.",
        "aviso": ("MINUTA de estimativa. Validar necessidades, recursos e circunstâncias "
                  "do caso; o magistrado fixa o valor a partir da prova."),
    }


@router.get("/civel/ferramentas/usucapiao-verificar")
async def civ_usucapiao(
    tipo: Literal["ordinaria","extraordinaria","especial_urbana","especial_rural","familiar"],
    anos_posse: float, posse_mansa: bool = True, cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Verifica requisitos de usucapião por modalidade. Base: CC arts. 1.238-1.244 + CF art. 183.
    """
    modalidades = {
        "extraordinaria":   {"anos": 15, "justo_titulo": False, "boaf": False,
                             "base": "CC art. 1.238 caput (ou 10 anos com moradia/prod. social)"},
        "ordinaria":        {"anos": 10, "justo_titulo": True, "boaf": True,
                             "base": "CC art. 1.242 (ou 5 anos com moradia/aquisição onerosa)"},
        "especial_urbana":  {"anos": 5,  "area_max_m2": 250, "justo_titulo": False, "boaf": False,
                             "base": "CF art. 183 + Estatuto da Cidade Lei 10.257/01 art. 9º"},
        "especial_rural":   {"anos": 5,  "area_max_ha": 50, "justo_titulo": False, "boaf": False,
                             "base": "CF art. 191 + CC art. 1.239"},
        "familiar":         {"anos": 2,  "abandono_lar": True, "area_max_m2": 250,
                             "base": "CC art. 1.240-A (ins. Lei 12.424/2011)"},
    }
    m = modalidades.get(tipo, {})
    prazo_min = m.get("anos", 0)
    preenche_prazo = anos_posse >= prazo_min
    return {
        "modalidade": tipo,
        "prazo_minimo_anos": prazo_min,
        "anos_posse_declarados": anos_posse,
        "posse_mansa": posse_mansa,
        "preenche_prazo": preenche_prazo,
        "requisitos": m,
        "viavel_preliminarmente": preenche_prazo and posse_mansa,
        "aviso": "MINUTA. Verificar cadeia dominial, confrontações e registro. Assessoria presencial obrigatória.",
    }


# ════════════════════════════════════════════════════════════════════════════
# 3. PENAL (/penal)
# ════════════════════════════════════════════════════════════════════════════
class PenalIn(BaseModel):
    case_id: str
    tipo_crime: PenalTipo
    fase: PenalFase = PenalFase.investigacao
    polo: Optional[str] = "reu"
    numero_bo: Optional[str] = None
    numero_ip: Optional[str] = None
    delegacia: Optional[str] = None
    data_fato: Optional[date] = None
    local_fato: Optional[str] = None
    preso: bool = False
    tipo_prisao: Optional[str] = None
    data_prisao: Optional[date] = None
    fianca_valor: Optional[float] = None
    artigo_imputado: Optional[str] = None
    pena_min_anos: Optional[float] = None
    pena_max_anos: Optional[float] = None
    anpp_proposto: bool = False
    data_denuncia: Optional[date] = None
    data_audiencia: Optional[date] = None
    observacoes: Optional[str] = None


@router.get("/penal")
async def pen_listar(db: AsyncSession = Depends(get_db),
                     cu: User = Depends(get_current_user),
                     fase: Optional[str] = None,
                     limit: int = 50, offset: int = 0):
    return await _crud_listar(PenalCase, db, fase, limit, offset, cu)

@router.post("/penal", status_code=201)
async def pen_criar(body: PenalIn, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(require_roles(_EQUIPE))):
    await _get_case(db, body.case_id, cu)
    data = body.model_dump()
    # Auto-calcular prazo de resposta à acusação
    if data.get("data_denuncia"):
        data["prazo_resposta_acusacao"] = prazo_dias_uteis(data["data_denuncia"], 10)
    p = PenalCase(id=str(uuid4()), **data)
    db.add(p)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "penal_cases", p.id)
    await db.commit()
    return _serialize(p)


@router.patch("/penal/{pid}")
async def pen_atualizar(pid: str, body: PenalUpdate, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(PenalCase, "penal_cases", pid,
                                 body.model_dump(exclude_unset=True), db, cu)

@router.delete("/penal/{pid}")
async def pen_remover(pid: str, db: AsyncSession = Depends(get_db),
                      cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(PenalCase, "penal_cases", pid, db, cu)

# ── Ferramentas Penais ────────────────────────────────────────────────────────
@router.get("/penal/ferramentas/prazos-processuais")
async def pen_prazos(
    data_citacao: date,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazos do processo penal — contagem em dias CORRIDOS (CPP art. 798: exclui-se
    o dia do começo e inclui-se o do vencimento; §3º: vencimento em domingo/feriado
    prorroga ao primeiro dia útil seguinte). A contagem em dias úteis do CPC NÃO
    se aplica ao processo penal.
    Marco calculado: resposta à acusação — 10 dias da CITAÇÃO (CPP art. 396).
    MINUTA — verificar suspensões e especificidades do caso.
    """
    # prazo_dias_corridos: vencimento = início + N dias (exclui o dia do começo,
    # inclui o do vencimento) com prorrogação para o 1º dia útil (CPP art. 798 §3º).
    return {
        "data_citacao": data_citacao,
        "contagem": ("Dias CORRIDOS (CPP art. 798 caput e §1º): exclui-se o dia do começo e "
                     "inclui-se o do vencimento; vencimento em domingo ou feriado prorroga "
                     "para o dia útil seguinte (§3º)."),
        "prazos": [
            {"evento": "Resposta à acusação",
             "data": prazo_dias_corridos(data_citacao, 10),
             "base": "CPP art. 396 — 10 dias corridos da citação"},
            {"evento": "Alegações finais por memoriais (quando convertidas)",
             "data": None,
             "base": "CPP art. 403 §3º — 5 dias sucessivos (marco fixado pelo juízo)"},
            {"evento": "RESE (Recurso em Sentido Estrito)",
             "data": None,
             "base": "CPP art. 586 — 5 dias corridos da intimação da decisão"},
            {"evento": "Apelação criminal",
             "data": None,
             "base": "CPP art. 593 — 5 dias corridos da intimação da sentença"},
            {"evento": "Embargos de declaração (criminal)",
             "data": None,
             "base": "CPP art. 619 — 2 dias corridos da publicação do acórdão"},
        ],
        "nota_suspensao_798a": ("CPP art. 798-A (Lei 14.365/2022): a contagem dos prazos "
                                "processuais penais fica SUSPENSA de 20/12 a 20/01 — exceção "
                                "que deve ser verificada quando o prazo atravessar o período."),
        "fontes": [
            "CPP (Decreto-Lei 3.689/1941) arts. 396, 403 §3º, 586, 593, 619, 798 e 798-A",
            "Lei 14.365/2022 (inclusão do art. 798-A — suspensão de fim de ano)",
        ],
        "vigencia_regra": "CPP art. 798 (contagem corrida) · art. 798-A vigente desde 09/06/2022",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Prazos sem data dependem do marco da "
                  "intimação/publicação; confirme o dies a quo e feriados locais no juízo."),
    }


@router.get("/penal/ferramentas/verificar-anpp")
async def pen_anpp(
    pena_minima_anos: float = Query(..., ge=0),
    sem_violencia_grave_ameaca: str = Query(...),
    confissao_formal_circunstanciada: str = Query(...),
    reincidente: str = Query(...),
    conduta_criminal_habitual_reiterada_profissional: str = Query(...),
    beneficiado_anpp_transacao_sursis_5anos: str = Query(...),
    violencia_domestica_familiar_ou_razao_genero: str = Query(...),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Verifica requisitos do Acordo de Não Persecução Penal — CPP art. 28-A
    (incluído pela Lei 13.964/2019). TODOS os requisitos e impeditivos legais são
    informados pelo advogado (sim | nao) — nada é presumido pelo sistema.
    `pena_minima_anos`: pena MÍNIMA cominada, consideradas as causas de aumento e
    de diminuição aplicáveis (entendimento consolidado — cf. Enunciados CNPG).
    """
    if pena_minima_anos < 0:
        raise HTTPException(422, "pena_minima_anos deve ser ≥ 0")
    sem_viol = _parse_sim_nao(sem_violencia_grave_ameaca, "sem_violencia_grave_ameaca")
    confessou = _parse_sim_nao(confissao_formal_circunstanciada, "confissao_formal_circunstanciada")
    eh_reincidente = _parse_sim_nao(reincidente, "reincidente")
    habitual = _parse_sim_nao(conduta_criminal_habitual_reiterada_profissional,
                              "conduta_criminal_habitual_reiterada_profissional")
    ja_beneficiado = _parse_sim_nao(beneficiado_anpp_transacao_sursis_5anos,
                                    "beneficiado_anpp_transacao_sursis_5anos")
    viol_domestica = _parse_sim_nao(violencia_domestica_familiar_ou_razao_genero,
                                    "violencia_domestica_familiar_ou_razao_genero")
    requisitos = [
        {"requisito": "Pena mínima inferior a 4 anos (consideradas causas de aumento/diminuição)",
         "base": "CPP art. 28-A caput", "tipo": "requisito",
         "atendido": pena_minima_anos < 4},
        {"requisito": "Infração sem violência ou grave ameaça",
         "base": "CPP art. 28-A caput", "tipo": "requisito",
         "atendido": sem_viol},
        {"requisito": "Confissão formal e circunstanciada",
         "base": "CPP art. 28-A caput", "tipo": "requisito",
         "atendido": confessou},
        {"requisito": "Não ser reincidente",
         "base": "CPP art. 28-A §2º II", "tipo": "impeditivo",
         "atendido": not eh_reincidente},
        {"requisito": "Ausência de conduta criminal habitual, reiterada ou profissional",
         "base": "CPP art. 28-A §2º II", "tipo": "impeditivo",
         "atendido": not habitual},
        {"requisito": "Não beneficiado com ANPP, transação penal ou sursis processual nos 5 anos anteriores",
         "base": "CPP art. 28-A §2º III", "tipo": "impeditivo",
         "atendido": not ja_beneficiado},
        {"requisito": "Crime sem violência doméstica/familiar nem contra a mulher por razões da condição de sexo feminino",
         "base": "CPP art. 28-A §2º IV", "tipo": "impeditivo",
         "atendido": not viol_domestica},
    ]
    for r in requisitos:
        r["situacao"] = ("atendido" if r["atendido"]
                         else ("impeditivo presente" if r["tipo"] == "impeditivo" else "não atendido"))
    elegivel = all(r["atendido"] for r in requisitos)
    return {
        "elegivel_anpp": elegivel,
        "pena_minima_anos": pena_minima_anos,
        "requisitos": requisitos,
        "condicoes_possiveis": [
            "Reparação do dano (salvo impossibilidade — inc. I)",
            "Renúncia a bens e direitos indicados como instrumentos/produto do crime (inc. II)",
            "Prestação de serviço à comunidade (inc. III)",
            "Prestação pecuniária (inc. IV)",
            "Outra condição indicada pelo MP, proporcional e compatível (inc. V)",
        ] if elegivel else [],
        "fontes": [
            "CPP art. 28-A, caput, §§1º-2º (incluído pela Lei 13.964/2019 — Pacote Anticrime)",
        ],
        "vigencia_regra": "CPP art. 28-A vigente desde 23/01/2020 (Lei 13.964/2019)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. O ANPP é proposto pelo MP e homologado "
                  "pelo juízo (§§4º-6º): a ferramenta indica elegibilidade objetiva, não "
                  "substitui a análise do caso, dos antecedentes e da suficiência da medida."),
    }


@router.get("/penal/ferramentas/prescricao-punitiva")
async def pen_prescricao(
    data_fato: date,
    pena_maxima_anos: Optional[float] = None,
    pena_concreta_anos: Optional[float] = None,
    marcos_interruptivos: Optional[str] = None,   # datas ISO separadas por vírgula (CP art. 117)
    menor_21_na_data_fato: str = "nao",
    maior_70_na_sentenca: str = "nao",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prescrição penal — implementação ÚNICA compartilhada com
    /penal/ferramentas/prescricao-penal (rota canônica). Ver _prescricao_penal_consolidada."""
    return _prescricao_penal_consolidada(
        rota_consultada="/penal/ferramentas/prescricao-punitiva",
        data_fato=data_fato, pena_maxima_anos=pena_maxima_anos,
        pena_concreta_anos=pena_concreta_anos, marcos_interruptivos=marcos_interruptivos,
        menor_21_na_data_fato=menor_21_na_data_fato, maior_70_na_sentenca=maior_70_na_sentenca,
    )


# ════════════════════════════════════════════════════════════════════════════
# 4. TRABALHISTA (/trabalhista-esp)
# ════════════════════════════════════════════════════════════════════════════
class TrabalhistaIn(BaseModel):
    case_id: str
    tipo: TrabalhistaTipo
    fase: TrabalhistaFase = TrabalhistaFase.pre_processual
    polo: str = "reclamante"
    salario_base: Optional[float] = None
    data_admissao: Optional[date] = None
    data_demissao: Optional[date] = None
    tipo_rescisao: Optional[str] = None
    cargo: Optional[str] = None
    cbo: Optional[str] = None
    regime_contratacao: str = "CLT"
    valor_causa_estimado: Optional[float] = None
    horas_extras_semana: Optional[float] = None
    adicional_percentual: Optional[float] = None
    data_acidente: Optional[date] = None
    cat_emitida: Optional[bool] = None
    cid: Optional[str] = None
    afastamento_dias: Optional[int] = None
    sequela_permanente: bool = False
    dano_moral_pedido: Optional[float] = None
    observacoes: Optional[str] = None


@router.get("/trabalhista-esp")
async def trab_listar(db: AsyncSession = Depends(get_db),
                      cu: User = Depends(get_current_user),
                      tipo: Optional[str] = None,
                      limit: int = 50, offset: int = 0):
    return await _crud_listar(TrabalhistaCase, db, tipo, limit, offset, cu)

@router.post("/trabalhista-esp", status_code=201)
async def trab_criar(body: TrabalhistaIn, db: AsyncSession = Depends(get_db),
                     cu: User = Depends(require_roles(_EQUIPE))):
    await _get_case(db, body.case_id, cu)
    data = body.model_dump()
    # Auto-calcular prazo do Recurso Ordinário se data de demissão fornecida
    # (O RO conta a partir da publicação da sentença — campo será atualizado depois)
    t = TrabalhistaCase(id=str(uuid4()), **data)
    db.add(t)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "trabalhista_cases", t.id)
    await db.commit()
    return _serialize(t)


@router.patch("/trabalhista-esp/{tid}")
async def trab_atualizar(tid: str, body: TrabalhistaUpdate, db: AsyncSession = Depends(get_db),
                         cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(TrabalhistaCase, "trabalhista_cases", tid,
                                 body.model_dump(exclude_unset=True), db, cu)

@router.delete("/trabalhista-esp/{tid}")
async def trab_remover(tid: str, db: AsyncSession = Depends(get_db),
                       cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(TrabalhistaCase, "trabalhista_cases", tid, db, cu)

# ── Ferramentas Trabalhistas ───────────────────────────────────────────────────
@router.get("/trabalhista-esp/ferramentas/prazos")
async def trab_prazos(data_sentenca: date, cu: User = Depends(require_roles(_EQUIPE))):
    """
    Prazos críticos trabalhistas a partir da sentença. MINUTA.
    """
    return _selo_homologacao("/trabalhista-esp/ferramentas/prazos", {
        "data_sentenca": data_sentenca,
        "prazos": [
            {"evento": "Recurso Ordinário (RO)",
             "data": prazo_dias_corridos(data_sentenca, 8),
             "base": "CLT art. 895 I — 8 dias corridos"},
            {"evento": "Depósito recursal (simultâneo ao RO)",
             "data": prazo_dias_corridos(data_sentenca, 8),
             "base": "CLT art. 899 + Súm. TST 245"},
            {"evento": "Embargos de declaração",
             "data": prazo_dias_corridos(data_sentenca, 5),
             "base": "CLT art. 897-A — 5 dias"},
        ],
        "aviso": "MINUTA. Marco: publicação da sentença ou intimação pessoal. Verificar com o juízo.",
    })


@router.get("/trabalhista-esp/ferramentas/prescricao-trabalhista")
async def trab_prescricao(
    data_demissao: Optional[date] = None,
    data_fato: Optional[date] = None,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prescrição trabalhista: 2 anos do término do contrato + 5 anos do crédito.
    Base: CLT art. 11 + CF art. 7º XXIX + Súm. TST 308.
    """
    hoje = date.today()
    result = {}
    if data_demissao:
        prescricao_bienal = date(data_demissao.year + 2, data_demissao.month, data_demissao.day)
        result["prescricao_bienal"] = {
            "data": prescricao_bienal,
            "prescrito": hoje > prescricao_bienal,
            "base": "CLT art. 11 caput + CF art. 7º XXIX — 2 anos do término do contrato",
        }
    if data_fato:
        prescricao_quinquenal = date(data_fato.year + 5, data_fato.month, data_fato.day)
        result["prescricao_quinquenal"] = {
            "data": prescricao_quinquenal,
            "prescrito": hoje > prescricao_quinquenal,
            "base": "CLT art. 11 caput — 5 anos do fato gerador (dentro do contrato)",
            "obs": "Súm. TST 308: conta-se retroativamente da data do ajuizamento",
        }
    result["aviso"] = "MINUTA. Verificar causas suspensivas (doença, MS) e interruptivas."
    return _selo_homologacao("/trabalhista-esp/ferramentas/prescricao-trabalhista", result)


@router.get("/trabalhista-esp/ferramentas/deposito-recursal")
async def trab_deposito(
    valor_condenacao: float,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Calcula depósito recursal para Recurso Ordinário e Recurso de Revista.
    Metodologia (CLT art. 899 §1º): o depósito recursal corresponde ao VALOR DA
    CONDENAÇÃO, limitado ao teto legal do recurso — NÃO a um percentual dela.
    Se a condenação < teto, recolhe-se o valor da condenação; se ≥ teto, recolhe-se
    o teto. Tetos 2026 (Ato TST GP 323/2025 — referência, atualização anual).
    MINUTA — confirmar teto vigente na data do recurso.
    """
    # Depósito = condenação limitada ao teto do recurso (art. 899 §1º).
    # Entre 1x e 2x o teto, recolher só metade tornaria o recurso DESERTO.
    dep_ro  = min(valor_condenacao, TETO_DEPOSITO_RO)
    dep_rr  = min(valor_condenacao, TETO_DEPOSITO_RR)
    return {
        "valor_condenacao": valor_condenacao,
        "deposito_ro": round(dep_ro, 2),
        "deposito_rr": round(dep_rr, 2),
        "teto_ro_2026": TETO_DEPOSITO_RO,
        "teto_rr_2026": TETO_DEPOSITO_RR,
        "metodologia": "Recolhimento = valor da condenação, limitado ao teto do recurso (CLT art. 899 §1º). Não é percentual da condenação.",
        "base": "CLT art. 899 §§1º-4º + Ato TST GP (atualização anual IPCA-E)",
        "aviso": "MINUTA. Confirmar teto vigente na data do recurso. Empresas em recuperação judicial têm tratamento específico.",
    }


# ════════════════════════════════════════════════════════════════════════════
# 5. ADMINISTRATIVO (/admin-esp)
# ════════════════════════════════════════════════════════════════════════════
class AdminIn(BaseModel):
    case_id: str
    tipo: AdminTipo
    status: AdminStatus = AdminStatus.prazo_recurso
    numero_auto_infracao: Optional[str] = None
    orgao_autuador: Optional[str] = None
    data_infracao: Optional[date] = None
    data_notificacao: Optional[date] = None
    codigo_infracao: Optional[str] = None
    valor_multa_original: Optional[float] = None
    valor_com_desconto: Optional[float] = None
    pontuacao_cnh: Optional[int] = None
    suspensao_cnh: bool = False
    data_ato_coator: Optional[date] = None
    autoridade_coatora: Optional[str] = None
    numero_pad: Optional[str] = None
    cargo_servidor: Optional[str] = None
    penalidade_imputada: Optional[str] = None
    observacoes: Optional[str] = None


@router.get("/admin-esp")
async def adm_listar(db: AsyncSession = Depends(get_db),
                     cu: User = Depends(get_current_user),
                     tipo: Optional[str] = None,
                     limit: int = 50, offset: int = 0):
    return await _crud_listar(AdminCase, db, tipo, limit, offset, cu)

@router.post("/admin-esp", status_code=201)
async def adm_criar(body: AdminIn, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(require_roles(_EQUIPE))):
    await _get_case(db, body.case_id, cu)
    data = body.model_dump()
    if data.get("data_notificacao"):
        dn = data["data_notificacao"]
        tipo = data.get("tipo","")
        if tipo == "recurso_multa_transito":
            data["prazo_recurso_1a_inst"] = prazo_dias_corridos(dn, 30)
        elif tipo in ("recurso_multa_ambiental","recurso_multa_tributaria","recurso_multa_trabalhista_adm"):
            data["prazo_recurso_1a_inst"] = prazo_dias_uteis(dn, 10)   # Lei 9.784 art. 59
        if data.get("data_ato_coator"):
            data["prazo_ms"] = prazo_dias_corridos(data["data_ato_coator"], 120)  # MS: 120 dias
    a = AdminCase(id=str(uuid4()), **data)
    db.add(a)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "admin_cases", a.id)
    await db.commit()
    return _serialize(a)


@router.patch("/admin-esp/{aid}")
async def adm_atualizar(aid: str, body: AdminUpdate, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(AdminCase, "admin_cases", aid,
                                 body.model_dump(exclude_unset=True), db, cu)

@router.delete("/admin-esp/{aid}")
async def adm_remover(aid: str, db: AsyncSession = Depends(get_db),
                      cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(AdminCase, "admin_cases", aid, db, cu)

# ── Ferramentas Administrativo ────────────────────────────────────────────────
@router.get("/admin-esp/ferramentas/recurso-multa-transito")
async def adm_multa_transito(
    data_notificacao: date,
    valor_multa: float,
    pontos_cnh: int = 0,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazos e estratégias para recursos de multas de trânsito.
    Base: CTB Lei 9.503/97 arts. 281-284.
    """
    prazo_1a = prazo_dias_corridos(data_notificacao, 30)   # JARI — CTB art. 281 §2º
    prazo_2a = prazo_dias_corridos(prazo_1a, 30)            # CETRAN/DENATRAN
    desconto_pagamento = round(valor_multa * 0.80, 2)       # 20% desconto pag. imediato CTB art. 284-A
    return _selo_homologacao("/admin-esp/ferramentas/recurso-multa-transito", {
        "data_notificacao": data_notificacao,
        "prazo_recurso_1a_inst_jari": prazo_1a,
        "prazo_recurso_2a_inst_cetran": prazo_2a,
        "valor_multa_original": valor_multa,
        "valor_com_desconto_20pct": desconto_pagamento,
        "pontos_cnh": pontos_cnh,
        "risco_suspensao": pontos_cnh >= 20,   # CTB art. 261
        "base": "CTB arts. 281-284 + Res. CONTRAN 619/2016",
        "aviso": "MINUTA. Prazo 1ª instância conta da notificação da autuação; 2ª da decisão da JARI.",
    })


# ── Ferramentas Trânsito (ramo próprio) ───────────────────────────────────────
@router.get("/transito/ferramentas/prazos-recurso")
async def transito_prazos_recurso(
    data_notificacao: date,
    valor_multa: float,
    fase: str = "autuacao",   # autuacao (defesa prévia) | penalidade (JARI)
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazos de defesa/recurso de multa e descontos (CTB Lei 9.503/97).
    Defesa prévia: a partir da notificação da AUTUAÇÃO (mín. 15 dias, CTB art. 281 §ú).
    Recurso à JARI: 30 dias da notificação da PENALIDADE (art. 285).
    Recurso ao CETRAN: 30 dias da decisão da JARI (art. 288).
    """
    if fase not in ("autuacao", "penalidade"):
        raise HTTPException(422, f"Fase inválida: '{fase}'. Use: autuacao | penalidade")
    defesa_previa = prazo_dias_corridos(data_notificacao, 15)
    jari = prazo_dias_corridos(data_notificacao, 30)
    cetran = prazo_dias_corridos(jari, 30)
    alvo = jari if fase == "penalidade" else defesa_previa
    dias_restantes = (alvo - date.today()).days
    return _selo_homologacao("/transito/ferramentas/prazos-recurso", {
        "data_notificacao": data_notificacao,
        "fase": fase,
        "prazo_defesa_previa": defesa_previa,
        "prazo_recurso_jari": jari,
        "prazo_recurso_cetran": cetran,
        "dias_restantes": dias_restantes,
        "urgente": dias_restantes <= 5,
        "valor_multa": valor_multa,
        "valor_desconto_40pct_sne": round(valor_multa * 0.60, 2),   # -40% adesão SNE (Lei 14.071/20)
        "valor_desconto_20pct": round(valor_multa * 0.80, 2),       # -20% pagto até venc. (art. 284)
        "base": "CTB Lei 9.503/97 arts. 281, 284, 285, 288 + Lei 14.071/2020",
        "aviso": "MINUTA — revisão humana obrigatória. Confira o prazo indicado na própria notificação.",
    })


@router.get("/transito/ferramentas/pontuacao-cnh")
async def transito_pontuacao_cnh(
    pontos_total: int,
    infracoes_gravissimas_12m: int = 0,
    categoria_profissional: str = "nao",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Limite de pontos para suspensão da CNH (Lei 14.071/2020 — CTB art. 261).
    O teto varia com o nº de infrações GRAVÍSSIMAS nos últimos 12 meses.
    """
    eh_prof = _parse_sim_nao(categoria_profissional, "categoria_profissional")
    if eh_prof:
        limite, regra = 30, "Condutor com atividade remunerada (EAR): teto de 30 pontos."
    elif infracoes_gravissimas_12m >= 2:
        limite, regra = 20, "2+ infrações gravíssimas em 12 meses: teto de 20 pontos."
    elif infracoes_gravissimas_12m == 1:
        limite, regra = 30, "1 infração gravíssima em 12 meses: teto de 30 pontos."
    else:
        limite, regra = 40, "Nenhuma infração gravíssima em 12 meses: teto de 40 pontos."
    excedeu = pontos_total >= limite
    return _selo_homologacao("/transito/ferramentas/pontuacao-cnh", {
        "pontos_total": pontos_total,
        "infracoes_gravissimas_12m": infracoes_gravissimas_12m,
        "condutor_profissional": eh_prof,
        "limite_aplicavel": limite,
        "regra_aplicada": regra,
        "atingiu_limite": excedeu,
        "pontos_para_suspensao": max(limite - pontos_total, 0),
        "consequencia": "Instauração de processo de suspensão do direito de dirigir (CTB art. 261)."
                        if excedeu else "Dentro do limite — monitorar.",
        "base": "CTB art. 261 c/c Lei 14.071/2020; condutor EAR: art. 261.",
        "aviso": "MINUTA — revisão humana obrigatória.",
    })


# ── Helper: soma de anos a uma data (trata 29/02) ─────────────────────────────
def _add_anos_data(d: date, anos: int) -> date:
    try:
        return d.replace(year=d.year + anos)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + anos)


def _add_meses_data(d: date, meses: int) -> date:
    """Soma meses a uma data. Múltiplos de 12 delegam a _add_anos_data (preserva
    29/02 em ano bissexto); demais casos fazem clamp do dia para 28 (segurança)."""
    if meses % 12 == 0:
        return _add_anos_data(d, meses // 12)
    total = d.month - 1 + meses
    ano, mes = d.year + total // 12, total % 12 + 1
    return date(ano, mes, min(d.day, 28))


# ── Prescrição penal consolidada (CP arts. 109, 110, 115 e 117) ───────────────
def _prescricao_prazo_anos(pena_anos: float) -> int:
    """Tabela do CP art. 109 (red. Lei 12.234/2010)."""
    if pena_anos > 12:
        return 20
    if pena_anos > 8:
        return 16
    if pena_anos > 4:
        return 12
    if pena_anos > 2:
        return 8
    if pena_anos >= 1:
        return 4
    return 3   # inferior a 1 ano — 3 anos (art. 109 VI, red. Lei 12.234/2010)


def _prescricao_penal_consolidada(
    rota_consultada: str,
    data_fato: date,
    pena_maxima_anos: Optional[float],
    pena_concreta_anos: Optional[float],
    marcos_interruptivos: Optional[str],
    menor_21_na_data_fato: str,
    maior_70_na_sentenca: str,
) -> dict:
    """Implementação ÚNICA das rotas /penal/ferramentas/prescricao-penal (canônica)
    e /penal/ferramentas/prescricao-punitiva (duplicata mantida até a Onda 3).
    Base: tabela do CP art. 109; pena concreta → art. 110 (retroativa/intercorrente);
    marcos interruptivos do art. 117 reiniciam a contagem intervalo a intervalo;
    art. 115 reduz o prazo à metade."""
    if pena_maxima_anos is None and pena_concreta_anos is None:
        raise HTTPException(422, (
            "Informe pena_maxima_anos (prescrição em abstrato, CP art. 109) OU "
            "pena_concreta_anos (prescrição retroativa/intercorrente, CP art. 110)."))
    usa_concreta = pena_concreta_anos is not None
    pena_base = pena_concreta_anos if usa_concreta else pena_maxima_anos
    if pena_base <= 0:
        raise HTTPException(422, "A pena informada deve ser maior que zero.")
    prazo_anos = _prescricao_prazo_anos(pena_base)
    reduzido = (_parse_sim_nao(menor_21_na_data_fato, "menor_21_na_data_fato")
                or _parse_sim_nao(maior_70_na_sentenca, "maior_70_na_sentenca"))
    prazo_meses = prazo_anos * 12 // (2 if reduzido else 1)

    marcos: list[date] = [data_fato]
    for token in (marcos_interruptivos or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            marco = date.fromisoformat(token)
        except ValueError:
            raise HTTPException(422, (
                f"Marco interruptivo inválido: '{token}'. Use datas ISO (AAAA-MM-DD) "
                "separadas por vírgula — ex.: 2021-03-10,2024-05-02."))
        if marco < data_fato:
            raise HTTPException(422, f"Marco interruptivo '{token}' anterior à data do fato.")
        marcos.append(marco)
    marcos.sort()

    hoje = date.today()
    analise: list[dict] = []
    intervalo_prescrito: Optional[int] = None
    for i, inicio in enumerate(marcos):
        ultimo = i + 1 == len(marcos)
        fim = hoje if ultimo else marcos[i + 1]
        limite = _add_meses_data(inicio, prazo_meses)
        estourou = fim > limite
        analise.append({
            "intervalo": i + 1,
            "inicio": inicio,
            "fim": None if ultimo else fim,
            "fim_descricao": "em aberto (contagem corrente até hoje)" if ultimo
                             else "marco interruptivo seguinte (CP art. 117 — reinicia a contagem)",
            "limite_prescricional": limite,
            "prescrito_no_intervalo": estourou,
        })
        if estourou and intervalo_prescrito is None:
            intervalo_prescrito = i + 1
    data_estimada = _add_meses_data(marcos[-1], prazo_meses)

    return _selo_homologacao(rota_consultada, {
        "rota_consultada": rota_consultada,
        "rota_canonica": "/penal/ferramentas/prescricao-penal",
        "base_de_calculo": "pena_concreta (CP art. 110 — retroativa/intercorrente)"
                           if usa_concreta else "pena_maxima_abstrata (CP art. 109)",
        "pena_considerada_anos": pena_base,
        "prazo_prescricional_anos": prazo_meses / 12 if prazo_meses % 12 else prazo_meses // 12,
        "reducao_metade_art_115": reduzido,
        "data_fato": data_fato,
        "marcos_interruptivos_considerados": marcos[1:],
        "analise_intervalos": analise,
        "prescrito": intervalo_prescrito is not None,
        "intervalo_prescrito": intervalo_prescrito,
        "data_prescricao_estimada": data_estimada,
        "fontes": [
            "CP art. 109 (red. Lei 12.234/2010) — tabela de prazos",
            "CP art. 110 — prescrição pela pena concreta (retroativa/intercorrente)",
            "CP art. 115 — redução à metade (<21 na data do fato / >70 na sentença)",
            "CP art. 117 — causas interruptivas (reiniciam a contagem)",
        ],
        "vigencia_regra": "CP arts. 109-117 com a redação da Lei 12.234/2010 (vigente desde 06/05/2010)",
        "versao_regra": _VERSAO_REGRA,
        "ressalvas": [
            "Termo inicial pode divergir da data do fato (CP art. 111 — ex.: crimes permanentes, "
            "crimes contra a dignidade sexual de menores).",
            "Causas suspensivas (CP art. 116) NÃO estão computadas.",
            "Prescrição retroativa não pode ter termo inicial anterior à denúncia/queixa "
            "(CP art. 110 §1º, red. Lei 12.234/2010).",
            "Crimes imprescritíveis: racismo (CF art. 5º XLII) e ação de grupos armados (XLIV).",
        ],
        "aviso": "MINUTA — revisão humana obrigatória; conferir marcos e certidões nos autos.",
    })


# ── Ferramentas Consumidor ────────────────────────────────────────────────────
@router.get("/consumidor/ferramentas/devolucao-dobro")
async def consumidor_devolucao_dobro(
    valor_cobrado: float,
    houve_ma_fe: str = "sim",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Repetição em dobro do indébito (CDC art. 42 §ú)."""
    ma_fe = _parse_sim_nao(houve_ma_fe, "houve_ma_fe")
    return _selo_homologacao("/consumidor/ferramentas/devolucao-dobro", {
        "valor_cobrado": valor_cobrado,
        "restituicao": round(valor_cobrado * 2, 2) if ma_fe else round(valor_cobrado, 2),
        "aplica_dobro": ma_fe,
        "observacao": "Dobro do valor pago indevidamente (+ correção e juros)." if ma_fe
                      else "Engano justificável afasta o dobro (restituição simples) — STJ.",
        "base": "CDC art. 42 §ú; STJ EAREsp 676.608 (modulação 30/03/2021).",
        "aviso": "MINUTA — revisão humana obrigatória.",
    })


@router.get("/consumidor/ferramentas/prazos-cdc")
async def consumidor_prazos_cdc(
    data_fato: date,
    tipo: str = "vicio_duravel",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Decadência/prescrição e arrependimento no CDC."""
    mapa = {
        "vicio_duravel":     (90, "dias", "Decadência — vício de produto durável (CDC art. 26 II)."),
        "vicio_nao_duravel": (30, "dias", "Decadência — não durável (art. 26 I)."),
        "arrependimento":    (7,  "dias", "Arrependimento — compra fora do estabelecimento (art. 49)."),
        "fato":              (5,  "anos", "Prescrição — fato do produto/serviço (art. 27)."),
        "cobranca_indevida": (3,  "anos", "Prescrição — cobrança indevida (CC art. 206 §3)."),
    }
    if tipo not in mapa:
        raise HTTPException(422, f"Tipo de prazo inválido: '{tipo}'. Use: {list(mapa)}")
    n, unid, desc = mapa[tipo]
    prazo = prazo_dias_corridos(data_fato, n) if unid == "dias" else _add_anos_data(data_fato, n)
    dias_rest = (prazo - date.today()).days
    return _selo_homologacao("/consumidor/ferramentas/prazos-cdc", {
        "tipo": tipo, "descricao": desc, "data_fato": data_fato, "prazo_final": prazo,
        "dias_restantes": dias_rest, "expirado": dias_rest < 0, "urgente": 0 <= dias_rest <= 15,
        "base": "CDC arts. 26, 27, 49.", "aviso": "MINUTA — revisão humana obrigatória.",
    })


# ── Ferramentas Família ───────────────────────────────────────────────────────
@router.get("/familia/ferramentas/debito-alimentos")
async def familia_debito_alimentos(
    valor_mensal: float,
    meses_atraso: int,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Débito de pensão e rito de execução (prisão civil x penhora)."""
    return {
        "valor_mensal": valor_mensal, "meses_atraso": meses_atraso,
        "debito_total": round(valor_mensal * meses_atraso, 2),
        "rito_prisao_civil_3_ultimas": round(valor_mensal * min(meses_atraso, 3), 2),
        "cabe_prisao": meses_atraso >= 1,
        "observacao": "Prisão civil (CPC art. 528 §3) cabe sobre as 3 últimas parcelas + vincendas "
                      "(Súmula 309 STJ); demais parcelas seguem rito de penhora (art. 528 §8).",
        "base": "CPC art. 528 §3 e §8; Súmula 309 STJ.",
        "aviso": "MINUTA — revisão humana obrigatória. Não inclui correção/juros.",
    }


# ── Ferramentas Imobiliário ───────────────────────────────────────────────────
@router.get("/imobiliario/ferramentas/reajuste-aluguel")
async def imobiliario_reajuste_aluguel(
    valor_atual: float,
    indice_percentual: float,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Reajuste anual de aluguel pelo índice contratual (IGP-M/IPCA)."""
    novo = round(valor_atual * (1 + indice_percentual / 100), 2)
    return {
        "valor_atual": valor_atual, "indice_percentual": indice_percentual,
        "valor_reajustado": novo, "aumento": round(novo - valor_atual, 2),
        "observacao": "Reajuste anual; índice conforme cláusula contratual (Lei 8.245/91 art. 18).",
        "base": "Lei 8.245/91 (Lei do Inquilinato) art. 18.",
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


@router.get("/imobiliario/ferramentas/prazos-despejo")
async def imobiliario_prazos_despejo(
    data_citacao: date,
    fundamento: str = "falta_pagamento",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prazos da ação de despejo e purga da mora (Lei 8.245/91)."""
    mapa = {
        "falta_pagamento": "Falta de pagamento — purga da mora em 15 dias (art. 62 II).",
        "denuncia_vazia":  "Denúncia vazia — desocupação em 15 dias após sentença (art. 63).",
        "infracao":        "Infração contratual/legal (art. 9).",
    }
    if fundamento not in mapa:
        raise HTTPException(422, f"Fundamento inválido: '{fundamento}'. Use: {list(mapa)}")
    return {
        "data_citacao": data_citacao, "fundamento": fundamento,
        "prazo_contestacao": prazo_dias_uteis(data_citacao, 15),
        "prazo_purga_mora": prazo_dias_corridos(data_citacao, 15) if fundamento == "falta_pagamento" else None,
        "descricao": mapa[fundamento],
        "base": "Lei 8.245/91 arts. 9, 59-63; CPC art. 335.",
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Ferramentas Previdenciário ────────────────────────────────────────────────
@router.get("/previdenciario/ferramentas/prazos")
async def previdenciario_prazos(
    data_indeferimento: date,
    tipo: str = "recurso_administrativo",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prazos previdenciários (recurso CRPS, decadência e prescrição)."""
    mapa = {
        "recurso_administrativo": (30, "dias", "Recurso ao CRPS contra indeferimento (Dec. 3.048/99)."),
        "decadencia_revisao":     (10, "anos", "Decadência para revisão do ato de concessão (Lei 8.213/91 art. 103)."),
        "prescricao_parcelas":    (5,  "anos", "Prescrição das parcelas vencidas (art. 103 §ú)."),
    }
    if tipo not in mapa:
        raise HTTPException(422, f"Tipo de prazo inválido: '{tipo}'. Use: {list(mapa)}")
    n, unid, desc = mapa[tipo]
    prazo = prazo_dias_corridos(data_indeferimento, n) if unid == "dias" else _add_anos_data(data_indeferimento, n)
    dias_rest = (prazo - date.today()).days
    return _selo_homologacao("/previdenciario/ferramentas/prazos", {
        "tipo": tipo, "descricao": desc, "data_base": data_indeferimento, "prazo_final": prazo,
        "dias_restantes": dias_rest, "expirado": dias_rest < 0,
        "base": "Lei 8.213/91 art. 103; Dec. 3.048/99.", "aviso": "MINUTA — revisão humana obrigatória.",
    })


# ── Ferramentas Digital / LGPD ────────────────────────────────────────────────
@router.get("/digital_lgpd/ferramentas/multa-lgpd")
async def lgpd_multa(
    faturamento_anual: float,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Teto de multa simples da LGPD (art. 52 II): 2% do faturamento, até R$ 50 mi/infração."""
    dois_pct = round(faturamento_anual * 0.02, 2)
    return {
        "faturamento_anual": faturamento_anual, "multa_2pct": dois_pct,
        "teto_aplicavel": min(dois_pct, 50_000_000.0),
        "limitada_ao_teto": dois_pct > 50_000_000.0,
        "observacao": "Multa simples de até 2% do faturamento no último exercício, limitada a R$ 50 milhões por infração.",
        "base": "LGPD Lei 13.709/18 art. 52 II.",
        "aviso": "MINUTA — revisão humana obrigatória. Dosimetria pela ANPD (art. 52 §1).",
    }


@router.get("/digital_lgpd/ferramentas/prazos-lgpd")
async def lgpd_prazos(
    data_evento: date,
    tipo: str = "resposta_titular",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prazos da LGPD (resposta ao titular e comunicação de incidente à ANPD)."""
    mapa = {
        "resposta_titular": (15, False, "Resposta ao titular sobre tratamento (LGPD art. 19 II)."),
        "incidente_anpd":   (3,  True,  "Comunicação de incidente à ANPD (Res. ANPD CD/15 2024: 3 dias úteis)."),
    }
    if tipo not in mapa:
        raise HTTPException(422, f"Tipo de prazo inválido: '{tipo}'. Use: {list(mapa)}")
    n, uteis, desc = mapa[tipo]
    prazo = prazo_dias_uteis(data_evento, n) if uteis else prazo_dias_corridos(data_evento, n)
    dias_rest = (prazo - date.today()).days
    return {
        "tipo": tipo, "descricao": desc, "data_evento": data_evento, "prazo_final": prazo,
        "dias_restantes": dias_rest, "expirado": dias_rest < 0,
        "base": "LGPD art. 19; Resolução ANPD CD/15 2024.", "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Previdenciário: tempo de contribuição (regra de pontos EC 103/2019) ────────
@router.get("/previdenciario/ferramentas/tempo-contribuicao")
async def previdenciario_tempo_contribuicao(
    idade: int,
    tempo_contribuicao_anos: float,
    sexo: str = "M",
    ano: int = 2026,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Regra de transição por pontos (EC 103/2019 art. 15). Pontos = idade + tempo."""
    s = (sexo or "").strip().upper()
    if s not in ("M", "F", "MASCULINO", "FEMININO"):
        raise HTTPException(422, f"Sexo inválido: '{sexo}'. Use: M | F")
    homem = s.startswith("M")
    # 2019: H 96 / M 86, +1 ponto por ano. Teto H 105 (2028), M 100 (2033).
    base = 96 if homem else 86
    teto = 105 if homem else 100
    exigido = min(base + max(0, ano - 2019), teto)
    pontos = round(idade + tempo_contribuicao_anos, 1)
    tempo_min = 35 if homem else 30
    return {
        "sexo": "masculino" if homem else "feminino", "ano": ano,
        "pontos_atingidos": pontos, "pontos_exigidos": exigido,
        "tempo_minimo_anos": tempo_min,
        "tempo_minimo_ok": tempo_contribuicao_anos >= tempo_min,
        "pode_aposentar": pontos >= exigido and tempo_contribuicao_anos >= tempo_min,
        "faltam_pontos": max(0, round(exigido - pontos, 1)),
        "observacao": "Regra de pontos sobe 1 ponto/ano. Verificar também idade mínima progressiva e demais regras de transição.",
        "base": "EC 103/2019 art. 15.", "aviso": "MINUTA — revisão humana obrigatória.",
    }


@router.get("/previdenciario/ferramentas/carencia")
async def previdenciario_carencia(
    meses_contribuicao: int,
    beneficio: str = "aposentadoria",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Carência exigida por benefício (Lei 8.213/91 art. 25-26)."""
    mapa = {
        "aposentadoria":        (180, "Aposentadoria por idade/tempo (art. 25 II)."),
        "auxilio_doenca":       (12,  "Auxílio por incapacidade temporária (art. 25 I)."),
        "aposentadoria_invalidez": (12, "Aposentadoria por incapacidade permanente (art. 25 I)."),
        "salario_maternidade":  (10,  "Salário-maternidade — contribuinte individual/facultativa (art. 25 III)."),
        "auxilio_acidente":     (0,   "Independe de carência (art. 26 I)."),
        "pensao_morte":         (0,   "Independe de carência (art. 26 I)."),
    }
    if beneficio not in mapa:
        raise HTTPException(422, f"Benefício inválido: '{beneficio}'. Use: {list(mapa)}")
    exigida, desc = mapa[beneficio]
    return {
        "beneficio": beneficio, "descricao": desc,
        "meses_contribuicao": meses_contribuicao, "carencia_exigida": exigida,
        "carencia_cumprida": meses_contribuicao >= exigida,
        "faltam_meses": max(0, exigida - meses_contribuicao),
        "base": "Lei 8.213/91 arts. 25 e 26.", "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Família: ITCMD no inventário ──────────────────────────────────────────────
@router.get("/familia/ferramentas/itcmd-inventario")
async def familia_itcmd(
    valor_monte: float,
    aliquota_percentual: float = 5.0,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """ITCMD sobre o monte partilhável (MG: 5% — Lei est. 14.941/03)."""
    imposto = round(valor_monte * aliquota_percentual / 100, 2)
    return {
        "valor_monte": valor_monte, "aliquota_percentual": aliquota_percentual,
        "itcmd_devido": imposto, "liquido_herdeiros": round(valor_monte - imposto, 2),
        "observacao": "Alíquota varia por estado (MG 5%; SP 4%; RJ progressiva). Conferir lei estadual e isenções.",
        "base": "CTN art. 35; MG Lei 14.941/03.", "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Penal: prescrição (rota CANÔNICA — implementação única) ───────────────────
@router.get("/penal/ferramentas/prescricao-penal")
async def penal_prescricao(
    data_fato: date,
    pena_maxima_anos: Optional[float] = None,
    pena_concreta_anos: Optional[float] = None,
    marcos_interruptivos: Optional[str] = None,   # datas ISO separadas por vírgula (CP art. 117)
    menor_21_na_data_fato: str = "nao",
    maior_70_na_sentenca: str = "nao",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prescrição penal (CP arts. 109, 110, 115 e 117) — rota canônica. A rota
    /penal/ferramentas/prescricao-punitiva usa a MESMA implementação e será
    removida na Onda 3 (após telemetria). Ver _prescricao_penal_consolidada."""
    return _prescricao_penal_consolidada(
        rota_consultada="/penal/ferramentas/prescricao-penal",
        data_fato=data_fato, pena_maxima_anos=pena_maxima_anos,
        pena_concreta_anos=pena_concreta_anos, marcos_interruptivos=marcos_interruptivos,
        menor_21_na_data_fato=menor_21_na_data_fato, maior_70_na_sentenca=maior_70_na_sentenca,
    )


_RE_FRACAO = re.compile(r"^(\d+)\s*/\s*(\d+)$")


def _parse_fracoes(csv: Optional[str], campo: str) -> list[dict]:
    """Parse de frações explícitas ("1/3,1/6") para as causas da 3ª fase.
    Fração fora do formato ou inválida → 422."""
    out: list[dict] = []
    for token in (csv or "").split(","):
        token = token.strip()
        if not token:
            continue
        m = _RE_FRACAO.match(token)
        if not m:
            raise HTTPException(422, (
                f"Fração inválida em {campo}: '{token}'. Use frações num/den separadas "
                "por vírgula — ex.: 1/3,1/6."))
        num, den = int(m.group(1)), int(m.group(2))
        if num == 0 or den == 0:
            raise HTTPException(422, f"Fração inválida em {campo}: '{token}' "
                                     "(numerador e denominador devem ser maiores que zero).")
        fracao = num / den
        if campo == "causas_diminuicao" and fracao >= 1:
            raise HTTPException(422, (
                f"Causa de diminuição '{token}' inválida: a fração deve ser menor que 1 "
                "(a pena não pode ser zerada ou negativa)."))
        out.append({"fracao": token, "valor": fracao})
    return out


def _meses_para_anos_meses(meses: float) -> dict:
    total = int(round(meses))
    return {"anos": total // 12, "meses": total % 12, "total_meses": round(meses, 1)}


@router.get("/penal/ferramentas/dosimetria")
async def penal_dosimetria(
    pena_minima_meses: int = Query(..., gt=0, description="Pena mínima cominada, em meses"),
    pena_maxima_meses: int = Query(..., gt=0, description="Pena máxima cominada, em meses"),
    circunstancias_judiciais_desfavoraveis: int = 0,
    n_agravantes: int = 0,
    n_atenuantes: int = 0,
    causas_aumento: Optional[str] = None,      # frações, ex.: "1/3,1/6"
    causas_diminuicao: Optional[str] = None,   # frações, ex.: "1/2,1/6"
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Simulador ASSISTIDO do cálculo trifásico da pena (CP art. 68), em MESES.
    1ª fase (art. 59): pena-base = mínimo + 1/8 do intervalo (máx−mín) por circunstância
      judicial desfavorável (fração referencial consolidada no STJ) — sempre DENTRO dos limites.
    2ª fase: agravantes/atenuantes a 1/6 da pena-base cada (referencial jurisprudencial);
      o resultado não desce abaixo do mínimo (Súmula 231 STJ) nem sobe acima do máximo.
    3ª fase: causas de aumento e de diminuição como FRAÇÕES explícitas, aplicadas em
      cascata — podem ultrapassar os limites cominados.
    """
    if pena_minima_meses <= 0 or pena_maxima_meses <= 0:
        raise HTTPException(422, "pena_minima_meses e pena_maxima_meses devem ser maiores que zero.")
    if pena_maxima_meses < pena_minima_meses:
        raise HTTPException(422, "pena_maxima_meses deve ser ≥ pena_minima_meses.")
    if not 0 <= circunstancias_judiciais_desfavoraveis <= 8:
        raise HTTPException(422, "circunstancias_judiciais_desfavoraveis deve estar entre 0 e 8 (CP art. 59).")
    if n_agravantes < 0 or n_atenuantes < 0:
        raise HTTPException(422, "n_agravantes e n_atenuantes devem ser ≥ 0.")
    aumentos = _parse_fracoes(causas_aumento, "causas_aumento")
    diminuicoes = _parse_fracoes(causas_diminuicao, "causas_diminuicao")

    # 1ª fase — pena-base (dentro dos limites por construção: 8/8 = máximo)
    intervalo = pena_maxima_meses - pena_minima_meses
    pena_base = pena_minima_meses + intervalo * circunstancias_judiciais_desfavoraveis / 8

    # 2ª fase — agravantes/atenuantes (1/6 da pena-base cada), com trava legal
    pena_2a_bruta = pena_base + (pena_base / 6) * (n_agravantes - n_atenuantes)
    pena_2a = min(max(pena_2a_bruta, pena_minima_meses), pena_maxima_meses)
    travada_no_minimo = pena_2a_bruta < pena_minima_meses
    travada_no_maximo = pena_2a_bruta > pena_maxima_meses

    # 3ª fase — causas em cascata (podem ultrapassar os limites cominados)
    pena_3a = pena_2a
    cascata: list[dict] = []
    for c in aumentos:
        antes = pena_3a
        pena_3a *= (1 + c["valor"])
        cascata.append({"operacao": f"aumento de {c['fracao']}", "de_meses": round(antes, 1),
                        "para_meses": round(pena_3a, 1)})
    for c in diminuicoes:
        antes = pena_3a
        pena_3a *= (1 - c["valor"])
        cascata.append({"operacao": f"diminuição de {c['fracao']}", "de_meses": round(antes, 1),
                        "para_meses": round(pena_3a, 1)})

    anos_definitivos = pena_3a / 12
    if anos_definitivos > 8:
        regime = "fechado"
    elif anos_definitivos > 4:
        regime = "semiaberto (não reincidente)"
    else:
        regime = "aberto (não reincidente)"

    return _selo_homologacao("/penal/ferramentas/dosimetria", {
        "pena_cominada": {"minima_meses": pena_minima_meses, "maxima_meses": pena_maxima_meses},
        "fase_1": {
            "circunstancias_judiciais_desfavoraveis": circunstancias_judiciais_desfavoraveis,
            "fracao_por_circunstancia": "1/8 do intervalo (máx − mín) — referencial STJ",
            "pena_base": _meses_para_anos_meses(pena_base),
        },
        "fase_2": {
            "n_agravantes": n_agravantes,
            "n_atenuantes": n_atenuantes,
            "fracao_por_circunstancia": "1/6 da pena-base — referencial jurisprudencial",
            "resultado_bruto_meses": round(pena_2a_bruta, 1),
            "limitada_ao_minimo_sum_231_stj": travada_no_minimo,
            "limitada_ao_maximo_legal": travada_no_maximo,
            "pena_intermediaria": _meses_para_anos_meses(pena_2a),
        },
        "fase_3": {
            "causas_aumento": [c["fracao"] for c in aumentos],
            "causas_diminuicao": [c["fracao"] for c in diminuicoes],
            "aplicacao": "em cascata (incidência sucessiva) — pode ultrapassar os limites cominados",
            "cascata": cascata,
            "pena_definitiva": _meses_para_anos_meses(pena_3a),
        },
        "regime_inicial_indicativo": {
            "regime": regime,
            "ressalva": ("Indicativo pelo CP art. 33 §2º para condenado NÃO reincidente, sem "
                         "considerar detração (CPP art. 387 §2º) nem as circunstâncias do art. "
                         "33 §3º — reincidência e circunstâncias desfavoráveis podem agravar o regime."),
        },
        "fontes": [
            "CP arts. 59, 61-67 e 68 (critério trifásico)",
            "Súmula 231 STJ (atenuante não reduz abaixo do mínimo)",
            "CP art. 33 §§2º-3º (regime inicial)",
            "STJ — referencial de 1/8 do intervalo por circunstância judicial (jurisprudência consolidada)",
        ],
        "vigencia_regra": "CP, Parte Geral, red. Lei 7.209/1984 (critério trifásico) — vigente",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — simulador assistido: as frações de 1/8 e 1/6 são REFERENCIAIS "
                  "jurisprudenciais, não vinculantes; o juiz fundamenta cada fase. Conferência "
                  "e fundamentação pelo advogado são obrigatórias."),
    })


# ── Trabalhista: horas extras + reflexos ──────────────────────────────────────
@router.get("/trabalhista/ferramentas/horas-extras")
async def trabalhista_horas_extras(
    salario_mensal: float,
    horas_extras_mes: float,
    adicional_percentual: float = 50.0,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Valor de horas extras + reflexos (jornada base 220h)."""
    valor_hora = salario_mensal / 220
    valor_he = valor_hora * (1 + adicional_percentual / 100) * horas_extras_mes
    # Reflexos estimados: DSR (~1/6), 13º (1/12), férias+1/3 (1/12*1.333), FGTS (8%)
    dsr = valor_he / 6
    base_reflexo = valor_he + dsr
    reflexos = base_reflexo * (1/12) + base_reflexo * (1/12) * (4/3)
    fgts = (base_reflexo + reflexos) * 0.08
    return {
        "valor_hora_normal": round(valor_hora, 2),
        "valor_horas_extras": round(valor_he, 2),
        "dsr_sobre_he": round(dsr, 2),
        "reflexos_13_ferias": round(reflexos, 2),
        "fgts_8pct": round(fgts, 2),
        "total_mes_estimado": round(valor_he + dsr + reflexos + fgts, 2),
        "observacao": "Estimativa mensal. Adicional mínimo 50% (CF art. 7 XVI); base de cálculo conforme Súmula 264 TST.",
        "base": "CF art. 7 XVI; CLT art. 59; Súmula 264 TST.", "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Empresarial: juros de mora (CC art. 406, red. Lei 14.905/2024) ────────────
_VIGENCIA_LEI_14905 = date(2024, 8, 30)   # nova taxa legal em vigor desde 30/08/2024


@router.get("/empresarial/ferramentas/juros-mora")
async def empresarial_juros_mora(
    regime: Literal["legal", "convencionada"],
    valor_principal: float = Query(..., gt=0),
    data_inicio_mora: date = Query(...),
    # Defaults planos (não Query): as calculadoras também são exercitadas por
    # chamada direta nos testes; validação explícita cobre o caminho HTTP e o direto.
    data_fim: Optional[date] = None,                      # data de apuração (default: hoje)
    selic_acumulada_percent: Optional[float] = None,      # Selic ACUMULADA do período novo (BCB)
    ipca_acumulado_percent: Optional[float] = None,       # IPCA ACUMULADO do mesmo período (IBGE)
    aplicar_regra_anterior: Optional[str] = None,         # sim|nao — mora iniciada antes de 30/08/2024
    taxa_mensal_percent: Optional[float] = None,          # taxa convencionada, % a.m.
    multa_pct: float = 0.0,                               # multa moratória pactuada, %
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Juros de mora sobre débito contratual — CC art. 406, red. Lei 14.905/2024.
    Desde 30/08/2024 NÃO existe mais o default de 1% a.m.: sem taxa convencionada,
    a taxa legal é a Selic DEDUZIDO o IPCA do período (art. 406 §1º); se o resultado
    for negativo, considera-se ZERO (§3º). Mora iniciada antes de 30/08/2024 pode ser
    segmentada: 1% a.m. (CC art. 406 na redação original c/c CTN art. 161 §1º) até
    29/08/2024 e regra nova em diante. MINUTA — revisão humana obrigatória.
    """
    fim = data_fim or date.today()
    if fim < data_inicio_mora:
        raise HTTPException(422, "data_fim anterior a data_inicio_mora.")
    if regime not in ("legal", "convencionada"):
        raise HTTPException(422, "Regime inválido. Use: legal | convencionada")
    if valor_principal <= 0:
        raise HTTPException(422, "valor_principal deve ser maior que zero.")
    if multa_pct < 0 or (taxa_mensal_percent is not None and taxa_mensal_percent < 0) \
            or (selic_acumulada_percent is not None and selic_acumulada_percent < 0):
        raise HTTPException(422, "Percentuais não podem ser negativos.")

    componentes: list[dict] = []
    if regime == "convencionada":
        if taxa_mensal_percent is None:
            raise HTTPException(422, (
                "Regime 'convencionada' exige taxa_mensal_percent (taxa de juros pactuada, "
                "% ao mês — CC art. 406 caput)."))
        meses = round((fim - data_inicio_mora).days / 30, 4)
        juros = valor_principal * (taxa_mensal_percent / 100) * meses
        componentes.append({
            "parcela": "juros convencionados (simples)",
            "periodo": f"{data_inicio_mora.isoformat()} a {fim.isoformat()}",
            "memoria": f"R$ {valor_principal:.2f} × {taxa_mensal_percent}% a.m. × {meses} meses (pro rata 30 dias)",
            "valor": round(juros, 2),
            "base": "CC art. 406 caput (taxa convencionada)",
        })
        nota_regime = ("Entre particulares não integrantes do SFN, a taxa convencionada não pode "
                       "exceder o DOBRO da taxa legal (Lei da Usura — Decreto 22.626/1933 art. 1º).")
    else:
        if selic_acumulada_percent is None or ipca_acumulado_percent is None:
            raise HTTPException(422, (
                "Regime 'legal' exige selic_acumulada_percent e ipca_acumulado_percent, "
                "ACUMULADOS do período sob a regra nova (de "
                f"{max(data_inicio_mora, _VIGENCIA_LEI_14905).isoformat()} a {fim.isoformat()}). "
                "Obtenha a Selic acumulada no BCB (SGS/Calculadora do Cidadão) e o IPCA "
                "acumulado no IBGE/SIDRA para o período exato."))
        if data_inicio_mora < _VIGENCIA_LEI_14905:
            if aplicar_regra_anterior is None:
                raise HTTPException(422, (
                    "A mora inicia antes de 30/08/2024 (vigência da Lei 14.905/2024): informe "
                    "aplicar_regra_anterior=sim para segmentar (1% a.m. até 29/08/2024 + taxa "
                    "legal nova em diante) ou aplicar_regra_anterior=nao para computar apenas "
                    "o período sob a regra nova."))
            if _parse_sim_nao(aplicar_regra_anterior, "aplicar_regra_anterior"):
                meses_ant = round((_VIGENCIA_LEI_14905 - data_inicio_mora).days / 30, 4)
                juros_ant = valor_principal * 0.01 * meses_ant
                componentes.append({
                    "parcela": "juros do período sob a regra anterior (1% a.m.)",
                    "periodo": f"{data_inicio_mora.isoformat()} a 2024-08-29",
                    "memoria": f"R$ {valor_principal:.2f} × 1% a.m. × {meses_ant} meses (pro rata 30 dias)",
                    "valor": round(juros_ant, 2),
                    "base": "CC art. 406 (redação original) c/c CTN art. 161 §1º — até 29/08/2024",
                })
            else:
                componentes.append({
                    "parcela": "período anterior a 30/08/2024 NÃO computado (por opção)",
                    "periodo": f"{data_inicio_mora.isoformat()} a 2024-08-29",
                    "valor": 0.0,
                    "base": "aplicar_regra_anterior=nao",
                })
        taxa_legal = max(selic_acumulada_percent - ipca_acumulado_percent, 0.0)
        zerada = (selic_acumulada_percent - ipca_acumulado_percent) < 0
        juros_novo = valor_principal * taxa_legal / 100
        componentes.append({
            "parcela": "juros legais (Selic − IPCA acumulados do período)",
            "periodo": f"{max(data_inicio_mora, _VIGENCIA_LEI_14905).isoformat()} a {fim.isoformat()}",
            "memoria": (f"R$ {valor_principal:.2f} × max({selic_acumulada_percent}% − "
                        f"{ipca_acumulado_percent}%, 0) = R$ {valor_principal:.2f} × {taxa_legal:.4f}%"),
            "valor": round(juros_novo, 2),
            "taxa_zerada_art_406_p3": zerada,
            "base": "CC art. 406 §§1º-3º (red. Lei 14.905/2024) — desde 30/08/2024",
        })
        nota_regime = ("Selic e IPCA acumulados devem ser apurados para o PERÍODO EXATO no "
                       "BCB e no IBGE; se Selic − IPCA for negativo, a taxa é ZERO (art. 406 §3º).")

    juros_total = round(sum(c["valor"] for c in componentes), 2)
    multa = round(valor_principal * multa_pct / 100, 2)
    return {
        "regime": regime,
        "valor_principal": valor_principal,
        "data_inicio_mora": data_inicio_mora,
        "data_fim": fim,
        "componentes": componentes,
        "juros_mora_total": juros_total,
        "multa": multa,
        "nota_multa": "Multa apenas se pactuada; em relação de consumo, limitada a 2% (CDC art. 52 §1º).",
        "total_devido": round(valor_principal + juros_total + multa, 2),
        "nota_regime": nota_regime,
        "fontes": [
            "CC art. 406, §§1º-3º (red. Lei 14.905/2024)",
            "CC art. 395 (efeitos da mora)",
            "Decreto 22.626/1933 art. 1º (Lei da Usura — limite da taxa convencionada)",
            "CDC art. 52 §1º (multa de 2% em relações de consumo)",
            "BCB (Selic acumulada) e IBGE (IPCA) — índices informados pelo usuário",
        ],
        "vigencia_regra": "Lei 14.905/2024 em vigor desde 30/08/2024; período anterior segmentado a 1% a.m.",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Cálculo SEM correção monetária do "
                  "principal (CC art. 389 §ú: IPCA salvo pactuação) e sem capitalização; "
                  "conferir índices oficiais do período no BCB/IBGE."),
    }


# ── Tributário: multa de mora + atraso ────────────────────────────────────────
@router.get("/tributario/ferramentas/multa-mora")
async def tributario_multa_mora(
    valor_tributo: float,
    dias_atraso: int,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Multa de mora 0,33%/dia limitada a 20% (tributos federais — Lei 9.430/96 art. 61)."""
    pct = min(0.33 * dias_atraso, 20.0)
    multa = round(valor_tributo * pct / 100, 2)
    return {
        "valor_tributo": valor_tributo, "dias_atraso": dias_atraso,
        "percentual_multa": round(pct, 2), "multa_mora": multa,
        "atingiu_teto_20pct": pct >= 20.0,
        "total_sem_juros": round(valor_tributo + multa, 2),
        "observacao": "Multa de mora de 0,33% por dia de atraso, limitada a 20%. Acrescer juros Selic acumulada (não incluídos).",
        "base": "Lei 9.430/96 art. 61.", "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Bancário: juros abusivos (contratada vs média de mercado) ─────────────────
@router.get("/bancario/ferramentas/juros-abusivos")
async def bancario_juros_abusivos(
    taxa_contratada_mensal_pct: float,
    taxa_media_bacen_mensal_pct: float,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Compara a taxa contratada com a média de mercado (BACEN) p/ tese revisional."""
    limite = round(taxa_media_bacen_mensal_pct * 1.5, 4)  # parâmetro usual STJ (1,5x a média)
    abusiva = taxa_contratada_mensal_pct > limite
    excesso = round(taxa_contratada_mensal_pct - taxa_media_bacen_mensal_pct, 4)
    return {
        "taxa_contratada": taxa_contratada_mensal_pct,
        "taxa_media_bacen": taxa_media_bacen_mensal_pct,
        "limite_referencia_1_5x": limite,
        "indicio_abusividade": abusiva,
        "excesso_pontos_pct": excesso,
        "observacao": "STJ não fixa teto rígido; abusividade aferida caso a caso, sendo a taxa média do BACEN o parâmetro (REsp 1.061.530). 1,5x é referência usual, não regra absoluta.",
        "base": "STJ REsp 1.061.530 (repetitivo); Súmula 530 STJ.",
        "aviso": "MINUTA — revisão humana obrigatória. Consultar a taxa média BACEN da modalidade/data.",
    }


# ── Imobiliário: distrato (Lei 13.786/2018) ───────────────────────────────────
@router.get("/imobiliario/ferramentas/distrato")
async def imobiliario_distrato(
    valor_pago: float,
    tem_patrimonio_afetacao: str = "nao",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Retenção em distrato de imóvel na planta (Lei do Distrato 13.786/18)."""
    afetacao = _parse_sim_nao(tem_patrimonio_afetacao, "tem_patrimonio_afetacao")
    pct_retencao = 50.0 if afetacao else 25.0
    retencao = round(valor_pago * pct_retencao / 100, 2)
    return {
        "valor_pago": valor_pago,
        "patrimonio_de_afetacao": afetacao,
        "percentual_retencao": pct_retencao,
        "valor_retido_incorporadora": retencao,
        "valor_a_restituir": round(valor_pago - retencao, 2),
        "observacao": "Retenção de até 25% dos valores pagos (50% se houver patrimônio de afetação). "
                      "Cláusulas que retêm mais podem ser revistas judicialmente.",
        "base": "Lei 13.786/2018 (art. 67-A da Lei 4.591/64).",
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Trânsito: valor da multa por gravidade ────────────────────────────────────
@router.get("/transito/ferramentas/valor-multa")
async def transito_valor_multa(
    gravidade: str = "media",
    multiplicador: int = 1,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Valor da multa por gravidade (CTB art. 258) com fator multiplicador."""
    tabela = {
        "leve":       (88.38,  3, "Leve — 3 pontos."),
        "media":      (130.16, 4, "Média — 4 pontos."),
        "grave":      (195.23, 5, "Grave — 5 pontos."),
        "gravissima": (293.47, 7, "Gravíssima — 7 pontos (multiplicador conforme infração)."),
    }
    if gravidade not in tabela:
        raise HTTPException(422, f"Gravidade inválida: '{gravidade}'. Use: {list(tabela)}")
    valor, pontos, desc = tabela[gravidade]
    total = round(valor * max(1, multiplicador), 2)
    return {
        "gravidade": gravidade, "descricao": desc,
        "valor_base": valor, "multiplicador": max(1, multiplicador),
        "valor_total": total, "pontos_cnh": pontos,
        "observacao": "Valores-base do CTB art. 258. Gravíssimas podem ter multiplicador (x2, x3, x5, x10, x20) conforme a infração.",
        "base": "CTB art. 258 c/c Lei 13.281/2016.",
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Consumidor: negativação indevida (dano moral) ─────────────────────────────
@router.get("/consumidor/ferramentas/negativacao-indevida")
async def consumidor_negativacao(
    existe_inscricao_anterior_legitima: str = "nao",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Triagem de dano moral por negativação indevida (Súmula 385 STJ)."""
    tem_anterior = _parse_sim_nao(existe_inscricao_anterior_legitima,
                                  "existe_inscricao_anterior_legitima")
    return {
        "existe_inscricao_anterior_legitima": tem_anterior,
        "cabe_dano_moral": not tem_anterior,
        "parametro_valor": "R$ 0 (Súmula 385 — só cabe cancelamento)" if tem_anterior
                           else "Faixa usual: R$ 5.000 a R$ 15.000 (varia por comarca/reincidência).",
        "dano_moral_in_re_ipsa": not tem_anterior,
        "observacao": "Súmula 385 STJ: havendo inscrição legítima preexistente, não cabe indenização por nova "
                      "anotação irregular, apenas o cancelamento. Sem preexistência, dano moral é in re ipsa.",
        "base": "Súmula 385 STJ; CDC art. 6 VI.",
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


@router.get("/admin-esp/ferramentas/mandado-seguranca")
async def adm_ms(
    data_ato_coator: date,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazo e requisitos do Mandado de Segurança.
    Base: Lei 12.016/2009 art. 23 (120 dias) + CF art. 5º LXIX.
    """
    prazo_ms = prazo_dias_corridos(data_ato_coator, 120)
    urgente = (prazo_ms - date.today()).days <= 10
    return {
        "data_ato_coator": data_ato_coator,
        "prazo_impetração": prazo_ms,
        "dias_restantes": max((prazo_ms - date.today()).days, 0),
        "urgente": urgente,
        "pressupostos": [
            "Direito líquido e certo — prova pré-constituída",
            "Ato de autoridade pública ou de pessoa no exercício de atribuição pública",
            "Ilegalidade ou abuso de poder",
        ],
        "base": "Lei 12.016/2009 art. 23 + CF art. 5º LXIX",
        "aviso": "MINUTA. Decadência de 120 dias do conhecimento do ato — confirme o dies a quo.",
    }


# ════════════════════════════════════════════════════════════════════════════
# 6. BANCÁRIO (/bancario)
# ════════════════════════════════════════════════════════════════════════════
class BancarioIn(BaseModel):
    case_id: str
    tipo: BancarioTipo
    status: BancarioStatus = BancarioStatus.analise_contrato
    instituicao_financeira: Optional[str] = None
    numero_contrato: Optional[str] = None
    modalidade_credito: Optional[str] = None
    data_contrato: Optional[date] = None
    valor_contratado: Optional[float] = None
    valor_pago: Optional[float] = None
    taxa_mensal_contratada: Optional[float] = None
    taxa_mensal_legal: Optional[float] = None
    cet_contratado: Optional[float] = None
    saldo_devedor_declarado: Optional[float] = None
    negativado: bool = False
    orgao_negativacao: Optional[str] = None
    data_negativacao: Optional[date] = None
    valor_negativado: Optional[float] = None
    dano_moral_pedido: Optional[float] = None
    superendividamento: bool = False
    renda_mensal: Optional[float] = None
    total_dividas: Optional[float] = None
    data_notificacao_ba: Optional[date] = None
    bem_garantia: Optional[str] = None
    observacoes: Optional[str] = None


@router.get("/bancario")
async def ban_listar(db: AsyncSession = Depends(get_db),
                     cu: User = Depends(get_current_user),
                     tipo: Optional[str] = None,
                     limit: int = 50, offset: int = 0):
    return await _crud_listar(BancarioCase, db, tipo, limit, offset, cu)

@router.post("/bancario", status_code=201)
async def ban_criar(body: BancarioIn, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(require_roles(_EQUIPE))):
    await _get_case(db, body.case_id, cu)
    data = body.model_dump()
    # Prazo para purga da mora em busca e apreensão: 5 dias (Dec.-Lei 911/69 art. 3º §2º)
    if data.get("data_notificacao_ba"):
        data["prazo_purga"] = prazo_dias_corridos(data["data_notificacao_ba"], 5)
    # Sinalizar spread excessivo
    if data.get("taxa_mensal_contratada") and data.get("taxa_mensal_legal"):
        data["spread_excessivo"] = data["taxa_mensal_contratada"] > data["taxa_mensal_legal"] * 1.5
    b = BancarioCase(id=str(uuid4()), **data)
    db.add(b)
    await criar_audit_log(db, cu.id, cu.role.value, "CREATE", "bancario_cases", b.id)
    await db.commit()
    return _serialize(b)


@router.patch("/bancario/{bid}")
async def ban_atualizar(bid: str, body: BancarioUpdate, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(BancarioCase, "bancario_cases", bid,
                                 body.model_dump(exclude_unset=True), db, cu)

@router.delete("/bancario/{bid}")
async def ban_remover(bid: str, db: AsyncSession = Depends(get_db),
                      cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(BancarioCase, "bancario_cases", bid, db, cu)

# ── Ferramentas Bancárias ─────────────────────────────────────────────────────
@router.get("/bancario/ferramentas/analise-juros")
async def ban_juros(
    taxa_mensal_contratada: float = Query(..., description="Taxa ao mês em %"),
    taxa_mensal_referencia: float = Query(..., description="Taxa de referência BCB/mercado %"),
    valor_contratado: float = Query(..., gt=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Análise de spreads e abusividade de juros.
    Súm. STJ 530: pactuação é livre para IF após a STJ 381 (revisada em 2015).
    STJ REsp 1.061.530 (leading case): abusividade exige demonstração concreta.
    MINUTA — confirmar com laudo pericial para processo.
    """
    taxa_anual_contrat = ((1 + taxa_mensal_contratada/100) ** 12 - 1) * 100
    taxa_anual_ref     = ((1 + taxa_mensal_referencia/100) ** 12 - 1) * 100
    spread_pct = taxa_mensal_contratada - taxa_mensal_referencia
    spread_relativo = (taxa_mensal_contratada / taxa_mensal_referencia - 1) * 100 if taxa_mensal_referencia else 0
    # Estimativa do valor pago a mais (12 meses)
    montante_contrat = valor_contratado * ((1 + taxa_mensal_contratada/100) ** 12)
    montante_ref     = valor_contratado * ((1 + taxa_mensal_referencia/100) ** 12)
    excesso_12m = round(montante_contrat - montante_ref, 2)
    return {
        "taxa_mensal_contratada_pct": taxa_mensal_contratada,
        "taxa_anual_efetiva_contratada_pct": round(taxa_anual_contrat, 4),
        "taxa_mensal_referencia_pct": taxa_mensal_referencia,
        "taxa_anual_referencia_pct": round(taxa_anual_ref, 4),
        "spread_absoluto_pct_mes": round(spread_pct, 4),
        "spread_relativo_pct": round(spread_relativo, 2),
        "excesso_estimado_12_meses": excesso_12m,
        "indicio_abusividade": spread_relativo > 50,   # > 50% acima da média de mercado
        "base_legal": [
            "STJ Súm. 530 (2015): pactuação livre, exige prova de abusividade",
            "STJ REsp 1.061.530 (recurso repetitivo): parâmetros de revisão",
            "Res. CMN 3.517/2007: obrigatoriedade de informação do CET",
            "CDC art. 52: informação clara e prévia do custo total",
        ],
        "aviso": "MINUTA. Laudo pericial contábil é indispensável para demonstrar abusividade em juízo.",
    }


@router.get("/bancario/ferramentas/superendividamento")
async def ban_superendiv(
    renda_mensal: float = Query(..., gt=0),
    total_parcelas_mes: float = Query(..., gt=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Verifica superendividamento (Lei 14.181/2021 — novo art. 54-A do CDC).
    Comprometimento do mínimo existencial = acima de 30% da renda (parâmetro STJ/doutrina).
    """
    sm = _sm_vigente()
    minimo_existencial = sm  # referência: 1 SM
    renda_disponivel = renda_mensal - minimo_existencial
    percentual_comprometido = (total_parcelas_mes / renda_mensal) * 100
    superendividado = percentual_comprometido > 30 or total_parcelas_mes > renda_disponivel
    return {
        "renda_mensal": renda_mensal,
        "total_parcelas_mensais": total_parcelas_mes,
        "percentual_comprometido": round(percentual_comprometido, 2),
        "minimo_existencial_referencia": minimo_existencial,
        "renda_disponivel_apos_min_exist": round(renda_disponivel, 2),
        "caracteriza_superendividamento": superendividado,
        "direitos_lei_14181": [
            "Repactuação de dívidas com todos os credores (art. 104-A CDC)",
            "Audiência de conciliação em 15 dias (art. 104-A §1º)",
            "Plano de pagamento mínimo de 5 anos (art. 104-A §3º)",
            "Proibição de novas contratações que comprometam mínimo existencial",
            "Nulidade de cláusulas abusivas nos contratos revisados",
        ],
        "base_legal": "Lei 14.181/2021 (art. 54-A CDC) + RE 632.212 STJ",
        "aviso": "MINUTA. O conceito de 'mínimo existencial' é casuístico. Análise completa requer avaliação da situação patrimonial.",
    }


@router.get("/bancario/ferramentas/busca-apreensao")
async def ban_ba(
    data_notificacao: date,
    valor_divida: float,
    bem_descricao: str,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazos e estratégias em busca e apreensão de bem alienado fiduciariamente.
    Base: Dec.-Lei 911/69 (red. Lei 13.043/2014 e 10.931/2004).
    """
    prazo_purga = prazo_dias_corridos(data_notificacao, 5)
    urgente = (prazo_purga - date.today()).days <= 2
    return {
        "data_notificacao": data_notificacao,
        "prazo_purga_mora": prazo_purga,
        "dias_restantes_purga": max((prazo_purga - date.today()).days, 0),
        "urgente": urgente,
        "valor_divida": valor_divida,
        "bem": bem_descricao,
        "estrategias": [
            {"estrategia": "Purga da mora",
             "prazo": prazo_purga,
             "desc": "Pagar integral da dívida vencida + encargos em 5 dias",
             "base": "Dec.-Lei 911/69 art. 3º §2º"},
            {"estrategia": "Embargos à BA",
             "prazo": "15 dias após citação",
             "desc": "Defesa no mérito — adimplemento substancial, invalidade etc.",
             "base": "CPC art. 914 + STJ REsp 1.622.555"},
            {"estrategia": "Adimplemento substancial",
             "desc": "STJ entende que pagamento de > 80% afasta a BA — verificar percentual quitado",
             "base": "STJ REsp 1.622.555-MG (2017) + AgRg REsp 1.580.036"},
        ],
        "aviso": "MINUTA. Urgência máxima. A purga da mora deve ser realizada antes do prazo — contate o banco imediatamente.",
    }


# ════════════════════════════════════════════════════════════════════════════
# FERRAMENTAS COMPLEMENTARES DA VITRINE (ramosConfig.ts — contrato 1:1)
# Cada endpoint abaixo corresponde EXATAMENTE a um card declarado em
# frontend/src/pages/ramos/ramosConfig.ts (mesmo path e mesmos parâmetros).
# O teste tests/test_calculadoras_ramos.py trava esse contrato no CI.
# ════════════════════════════════════════════════════════════════════════════
def _sm_vigente() -> float:
    """Salário mínimo VIGENTE (settings.SALARIO_MINIMO_BRL — decreto anual)."""
    return float(get_settings().SALARIO_MINIMO_BRL)


def _mais_anos(d: date, anos: int) -> date:
    """Soma anos preservando dia/mês (dia > 28 vira 28 — segurança p/ fevereiro)."""
    return date(d.year + anos, d.month, min(d.day, 28))


# ── Cível: prescrição/decadência do consumidor (CDC arts. 26-27) ─────────────
@router.get("/civel/ferramentas/prescricao-consumidor")
async def civ_prescricao_consumidor(
    data_fato: date,
    tipo_vicio: Literal["fato_produto", "fato_servico",
                        "servico_ou_produto", "cobranca_indevida"] = "fato_produto",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prescrição (5 anos, fato do produto/serviço) e decadência (30/90 dias, vício)."""
    if tipo_vicio in ("fato_produto", "fato_servico"):
        limite = _mais_anos(data_fato, 5)
        return {
            "pretensao": "Reparação por fato do produto/serviço (acidente de consumo)",
            "instituto": "prescrição",
            "prazo": "5 anos",
            "termo_inicial": data_fato,
            "data_limite": limite,
            "dias_restantes": max((limite - date.today()).days, 0),
            "base_legal": "CDC art. 27 — conta do conhecimento do dano e de sua autoria.",
            "aviso": "MINUTA — verificar causas suspensivas/interruptivas (CC arts. 197-202).",
        }
    if tipo_vicio == "servico_ou_produto":
        return {
            "pretensao": "Vício do produto/serviço",
            "instituto": "decadência",
            "termo_inicial": data_fato,
            "nao_duravel_30_dias": {"data_limite": data_fato + timedelta(days=30),
                                    "descricao": "Produto/serviço NÃO durável (CDC art. 26 I)"},
            "duravel_90_dias": {"data_limite": data_fato + timedelta(days=90),
                                "descricao": "Produto/serviço durável (CDC art. 26 II)"},
            "obsta_decadencia": "Reclamação comprovada ao fornecedor, até resposta negativa "
                                "inequívoca (CDC art. 26 §2º I).",
            "vicio_oculto": "No vício oculto o prazo conta do momento em que o defeito "
                            "se evidencia (CDC art. 26 §3º).",
            "base_legal": "CDC art. 26, I-II e §§ 2º-3º.",
            "aviso": "MINUTA — revisão humana obrigatória.",
        }
    # cobranca_indevida — repetição de indébito
    return {
        "pretensao": "Repetição de indébito (cobrança indevida)",
        "instituto": "prescrição",
        "termo_inicial": data_fato,
        "prazo_stj_10_anos": {"data_limite": _mais_anos(data_fato, 10),
                              "base": "CC art. 205 — STJ EAREsp 738.991/RS (Corte Especial)"},
        "corrente_3_anos": {"data_limite": _mais_anos(data_fato, 3),
                            "base": "CC art. 206 §3º IV (enriquecimento sem causa) — minoritária"},
        "devolucao_em_dobro": "Cabível quando a cobrança contraria a boa-fé objetiva "
                              "(CDC art. 42 § único — STJ EAREsp 676.608, sem exigir má-fé após 30/03/2021).",
        "base_legal": "CC art. 205 · CDC art. 42 § único · STJ EAREsp 738.991/RS.",
        "aviso": "MINUTA — prevalece o prazo decenal no STJ; avaliar o caso concreto.",
    }


# ── Cível: parâmetros ORIENTATIVOS de dano moral ──────────────────────────────
# Não há tabelamento legal de dano moral (tarifação é vedada — cf. ADPF 130).
# Faixas extraídas de precedentes usuais STJ/TJs, meramente indicativas.
_FAIXAS_DANO_MORAL = {
    "negativacao_indevida": (5_000.0, 15_000.0,
                             "Negativação indevida — dano in re ipsa (STJ REsp 1.059.663)."),
    "extravio_bagagem":     (5_000.0, 15_000.0,
                             "Extravio de bagagem — CDC prevalece sobre tarifação de convenções internacionais no dano moral."),
    "produto_defeituoso":   (3_000.0, 10_000.0,
                             "Produto defeituoso sem risco à saúde — mero vício, sem outros transtornos, pode não gerar dano moral."),
    "acidente_consumo":     (10_000.0, 50_000.0,
                             "Fato do produto/serviço com lesão à saúde — gravidade e sequelas elevam o quantum."),
    "cobranca_abusiva":     (3_000.0, 12_000.0,
                             "Cobrança vexatória/abusiva (CDC arts. 42 e 71)."),
    "outro":                (5_000.0, 20_000.0,
                             "Faixa genérica — pesquisar precedentes específicos do tema e da comarca."),
}


@router.get("/civel/ferramentas/calculo-dano-moral")
async def civ_dano_moral(
    tipo_caso: str = "negativacao_indevida",
    salarios_minimos_pedido: float = Query(10.0, ge=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Faixas ORIENTATIVAS de dano moral por tipo de caso (sem tabelamento legal)."""
    if tipo_caso not in _FAIXAS_DANO_MORAL:
        raise HTTPException(422, f"Tipo de caso inválido: '{tipo_caso}'. Use: {list(_FAIXAS_DANO_MORAL)}")
    minimo, maximo, nota = _FAIXAS_DANO_MORAL[tipo_caso]
    pedido = round(salarios_minimos_pedido * _sm_vigente(), 2)
    posicao = ("dentro da faixa usual" if minimo <= pedido <= maximo
               else "abaixo da faixa usual" if pedido < minimo
               else "acima da faixa usual")
    return {
        "tipo_caso": tipo_caso,
        "faixa_orientativa_min": minimo,
        "faixa_orientativa_max": maximo,
        "quantum_pedido": pedido,
        "pedido_em_sm": salarios_minimos_pedido,
        "posicao_do_pedido": posicao,
        "nota_jurisprudencial": nota,
        "metodo_bifasico_stj": "1ª fase: valor-base pelo interesse jurídico lesado (grupo de "
                               "precedentes); 2ª fase: ajuste às circunstâncias do caso "
                               "(STJ REsp 1.152.541).",
        "observacao": "Valores MERAMENTE ORIENTATIVOS — NÃO há tabelamento legal de dano "
                      "moral; o quantum é arbitrado judicialmente caso a caso.",
        "base": "CC arts. 186 e 944 · CDC art. 6º VI · STJ REsp 1.152.541 (método bifásico).",
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Cível: partilha no divórcio por regime de bens ────────────────────────────
_REGIMES_BENS = {
    "comunhao_parcial": {
        "rotulo": "Comunhão parcial de bens",
        "meacao": "50% dos bens adquiridos ONEROSAMENTE na constância do casamento (aquestos)",
        "partilham": [
            "Bens adquiridos onerosamente após o casamento (por qualquer dos cônjuges)",
            "Frutos dos bens particulares percebidos na constância (CC art. 1.660 V)",
            "FGTS depositado e valorização de cotas societárias na constância (STJ)",
        ],
        "nao_partilham": [
            "Bens anteriores ao casamento e os sub-rogados em seu lugar",
            "Herança e doação recebidas por um só cônjuge (CC art. 1.659 I)",
            "Bens de uso pessoal, livros e instrumentos de profissão",
        ],
        "base": "CC arts. 1.658-1.666",
    },
    "comunhao_universal": {
        "rotulo": "Comunhão universal de bens",
        "meacao": "50% de TODOS os bens, presentes e futuros, salvo exceções do art. 1.668",
        "partilham": ["Todos os bens, anteriores e posteriores ao casamento, inclusive heranças e doações"],
        "nao_partilham": [
            "Bens doados/herdados com cláusula de incomunicabilidade e sub-rogados",
            "Dívidas anteriores ao casamento (salvo proveito comum)",
            "Bens de uso pessoal, livros e instrumentos de profissão",
        ],
        "base": "CC arts. 1.667-1.671",
    },
    "separacao_obrigatoria": {
        "rotulo": "Separação obrigatória (legal) de bens",
        "meacao": "Em regra NÃO há meação; comunicam-se os aquestos adquiridos na constância "
                  "por ESFORÇO COMUM comprovado (Súmula 377 STF)",
        "partilham": ["Aquestos da constância mediante prova do esforço comum "
                      "(STJ EREsp 1.623.858 — esforço comum deve ser comprovado)"],
        "nao_partilham": ["Bens anteriores e os adquiridos sem participação comprovada do outro cônjuge"],
        "base": "CC art. 1.641 · Súmula 377 STF · STJ EREsp 1.623.858",
    },
    "separacao_voluntaria": {
        "rotulo": "Separação convencional de bens",
        "meacao": "NÃO há meação — cada cônjuge conserva a propriedade exclusiva de seus bens",
        "partilham": ["Somente bens em condomínio voluntário (co-aquisição em nome de ambos)"],
        "nao_partilham": ["Todos os demais bens de cada cônjuge, anteriores ou posteriores"],
        "base": "CC arts. 1.687-1.688 (exige pacto antenupcial)",
    },
    "participacao_final_aquestos": {
        "rotulo": "Participação final nos aquestos",
        "meacao": "Na dissolução, cada cônjuge tem direito à METADE dos aquestos onerosos "
                  "apurados contabilmente",
        "partilham": ["Aquestos adquiridos onerosamente na constância (apuração na dissolução, CC art. 1.674)"],
        "nao_partilham": ["Bens anteriores, sub-rogados, heranças e doações"],
        "base": "CC arts. 1.672-1.686 (exige pacto antenupcial)",
    },
}


@router.get("/civel/ferramentas/partilha-divorcio")
async def civ_partilha_divorcio(
    regime_bens: str = "comunhao_parcial",
    data_casamento: Optional[date] = None,
    data_separacao_fatos: Optional[date] = None,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """O que se partilha no divórcio, por regime de bens (CC arts. 1.658-1.688)."""
    regra = _REGIMES_BENS.get(regime_bens)
    if not regra:
        raise HTTPException(422, f"Regime inválido. Use: {list(_REGIMES_BENS)}")
    out: dict = {
        "regime": regra["rotulo"],
        "meacao": regra["meacao"],
        "o_que_se_partilha": regra["partilham"],
        "o_que_nao_se_partilha": regra["nao_partilham"],
        "base_legal": regra["base"],
    }
    fim = data_separacao_fatos or date.today()
    if data_casamento:
        out["anos_de_uniao"] = round(max((fim - data_casamento).days, 0) / 365.25, 1)
    if data_separacao_fatos:
        out["marco_final_da_comunhao"] = data_separacao_fatos
        out["nota_separacao_de_fato"] = ("A separação de fato faz cessar o regime de bens: "
                                         "aquisições posteriores NÃO se comunicam (STJ REsp 1.065.209).")
    out["aviso"] = ("MINUTA — a partilha concreta depende do inventário de bens, dívidas, "
                    "sub-rogações e provas. Revisão humana obrigatória.")
    return out


# ── Cível: rescisão de locação (Lei 8.245/91) ────────────────────────────────
@router.get("/civel/ferramentas/rescisao-locacao")
async def civ_rescisao_locacao(
    data_inicio: date,
    data_rescisao_pretendida: date,
    valor_aluguel: float = Query(..., gt=0),
    tipo_locacao: Literal["residencial", "comercial", "temporada"] = "residencial",
    quem_rescinde: Literal["locatario", "locador"] = "locatario",
    prazo_contrato_meses: int = Query(30, gt=0, description="Prazo contratual em meses (praxe residencial: 30)"),
    multa_contratual_alugueis: float = Query(3.0, ge=0, description="Multa pactuada em nº de aluguéis (praxe: 3)"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Multa PROPORCIONAL na devolução antecipada (Lei 8.245/91 art. 4º)."""
    if data_rescisao_pretendida < data_inicio:
        raise HTTPException(422, "Data de rescisão anterior ao início do contrato")
    meses_cumpridos = ((data_rescisao_pretendida.year - data_inicio.year) * 12
                       + (data_rescisao_pretendida.month - data_inicio.month))
    # Mês só conta como cumprido quando o DIA do aniversário foi alcançado
    # (auditoria: 31/01→01/02 não é 1 mês cumprido).
    if data_rescisao_pretendida.day < data_inicio.day:
        meses_cumpridos -= 1
    meses_cumpridos = max(0, min(meses_cumpridos, prazo_contrato_meses))
    meses_restantes = prazo_contrato_meses - meses_cumpridos
    multa = round(valor_aluguel * multa_contratual_alugueis
                  * meses_restantes / prazo_contrato_meses, 2)
    out: dict = {
        "quem_rescinde": quem_rescinde,
        "tipo_locacao": tipo_locacao,
        "prazo_contrato_meses": prazo_contrato_meses,
        "meses_cumpridos": meses_cumpridos,
        "meses_restantes": meses_restantes,
        "memoria_calculo": (f"multa = {multa_contratual_alugueis} aluguel(éis) de R$ {valor_aluguel:.2f} "
                            f"× {meses_restantes}/{prazo_contrato_meses} avos do prazo restante"),
    }
    if quem_rescinde == "locatario":
        out["multa_proporcional_devida"] = multa if meses_restantes > 0 else 0.0
        out["contrato_integralmente_cumprido"] = meses_restantes == 0
        out["regras"] = [
            "Devolução antecipada: multa pactuada, PROPORCIONAL ao período restante (art. 4º).",
            "Isenção de multa: transferência pelo empregador para outra localidade, com aviso "
            "escrito de 30 dias (art. 4º § único).",
            "Locação por prazo INDETERMINADO: denúncia com aviso escrito de 30 dias, sem multa (art. 6º).",
        ]
    else:
        out["multa_proporcional_devida"] = 0.0
        out["regras"] = [
            "Durante o prazo determinado o LOCADOR NÃO pode reaver o imóvel (art. 4º, 1ª parte).",
            "Residencial com prazo ≥ 30 meses: denúncia vazia ao término (art. 46).",
            "Residencial < 30 meses: retomada apenas nas hipóteses do art. 47 (uso próprio etc.).",
            "Comercial: retomada ao fim do prazo/denúncia (arts. 56-57); atenção à ação renovatória (art. 51).",
        ]
    out["base"] = "Lei 8.245/91 arts. 4º, 6º, 46-47, 51 e 56-57."
    out["aviso"] = ("MINUTA — prevalecem o prazo e a multa efetivamente PACTUADOS no contrato; "
                    "ajuste os parâmetros conforme o instrumento.")
    return out


# ── Trabalhista: verbas rescisórias (fachada da calculadora CLT auditável) ────
@router.get("/trabalhista-esp/ferramentas/verbas-rescisorias")
async def trab_verbas_rescisorias(
    salario: float = Query(..., gt=0),
    data_admissao: date = Query(...),
    data_demissao: date = Query(...),
    tipo_rescisao: str = "sem_justa_causa",
    saldo_fgts: float = Query(0.0, ge=0),
    aviso_previo: Literal["indenizado", "trabalhado", "dispensado"] = "indenizado",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Verbas rescisórias completas. Delegado à MESMA calculadora auditável de
    /calculadoras/trabalhista/rescisao (app/services/calc/trabalhista.py),
    remodelada para o shape do card do ramo (VerbaRescisView no RamoBase.tsx)."""
    from app.services.calc.trabalhista import calcular as calc_rescisao, EntradaRescisao
    # Rescisão indireta (CLT art. 483 §... falta grave do empregador): verbas
    # idênticas às da dispensa sem justa causa.
    tipo_calc = "sem_justa_causa" if tipo_rescisao == "rescisao_indireta" else tipo_rescisao
    try:
        det = calc_rescisao(EntradaRescisao(
            salario=salario, admissao=data_admissao, demissao=data_demissao,
            tipo=tipo_calc, aviso_indenizado=(aviso_previo == "indenizado"),
            saldo_fgts=saldo_fgts,
        ))
    except ValueError as e:
        raise HTTPException(422, str(e))

    def _verba(prefixo: str) -> float:
        return round(sum(p["valor"] for p in det["proventos"]
                         if p["verba"].startswith(prefixo)), 2)

    saldo_sal = _verba("Saldo de salário")
    aviso_val = _verba("Aviso prévio")
    decimo = _verba("13º salário")
    ferias = round(_verba("Férias proporcionais") + _verba("1/3 sobre férias"), 2)
    multa_fgts = _verba("Multa FGTS")
    # FGTS da rescisão: 8% sobre parcelas salariais + aviso indenizado
    # (Lei 8.036/90 arts. 15 e 18 §1º; Súmula 305 TST).
    fgts_resc = round((saldo_sal + decimo + aviso_val) * 0.08, 2)
    verbas = {
        "saldo_salario": saldo_sal,
        "aviso_previo": aviso_val,
        "decimo_terceiro_proporcional": decimo,
        "ferias_proporcionais_mais_um_terco": ferias,
        "fgts_rescisorio_8pct": fgts_resc,
        "multa_fgts": multa_fgts,
    }
    return {
        "verbas": verbas,
        "total_bruto_estimado": round(sum(verbas.values()), 2),
        "dados_contrato": {
            "tempo_contrato_anos": det["parametros"]["anos_completos"],
            "dias_aviso_previo": det["parametros"]["aviso_dias"],
            "tipo_rescisao": tipo_rescisao,
            "aviso_previo": aviso_previo,
        },
        "detalhamento": {
            "proventos": det["proventos"],
            "descontos": det["descontos"],
            "total_descontos": det["total_descontos"],
            "liquido_estimado": det["liquido"],
            "saque_fgts_liberado": det["saque_fgts_liberado"],
        },
        "base_legal": "CLT arts. 477-483 · Lei 12.506/2011 (aviso proporcional) · "
                      "Lei 8.036/90 arts. 15/18 · Súmula 305 TST",
        "aviso": ("MINUTA — total BRUTO (INSS/IRRF no detalhamento). Não inclui horas extras, "
                  "adicionais e reflexos. Revisão humana obrigatória."),
    }


# ── Administrativo: reajuste de contrato administrativo ───────────────────────
@router.get("/admin-esp/ferramentas/reajuste-contrato-administrativo")
async def adm_reajuste_contrato(
    valor_original: float = Query(..., gt=0),
    indice_acumulado_pct: float = Query(..., ge=-50, le=1000),
    meses_contrato: int = Query(..., ge=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Reajuste em sentido estrito por índice contratual, respeitada a ANUALIDADE
    (Lei 14.133/2021 arts. 25 §7º e 92 §3º c/c Lei 10.192/2001 art. 2º §1º)."""
    elegivel = meses_contrato >= 12
    reajuste = round(valor_original * indice_acumulado_pct / 100, 2)
    return {
        "elegivel_para_reajuste": elegivel,
        "motivo": ("Interregno mínimo de 12 meses cumprido"
                   if elegivel else
                   f"Anualidade NÃO cumprida — faltam {12 - meses_contrato} mês(es) "
                   f"(Lei 10.192/01 art. 2º §1º)"),
        "valor_original": valor_original,
        "indice_acumulado_pct": indice_acumulado_pct,
        "valor_do_reajuste": reajuste if elegivel else 0.0,
        "novo_valor_do_contrato": round(valor_original + reajuste, 2) if elegivel else valor_original,
        "memoria_calculo": (f"reajuste = R$ {valor_original:.2f} × {indice_acumulado_pct}% "
                            f"(índice previsto no contrato, acumulado em 12 meses)"),
        "marco_inicial": "Data do orçamento estimado ou da apresentação da proposta "
                         "(Lei 14.133 art. 25 §7º e art. 92 §3º).",
        "nao_confundir": "Reajuste (inflação, anual, índice previsto) ≠ repactuação (custos de "
                         "mão de obra, art. 135) ≠ reequilíbrio econômico-financeiro (álea "
                         "extraordinária, art. 124 II d).",
        "base": "Lei 14.133/2021 arts. 25 §7º, 92 §3º, 124 e 135 · Lei 10.192/2001 art. 2º §1º.",
        "aviso": "MINUTA — usar o ÍNDICE previsto no contrato administrativo e o período correto de apuração.",
    }


# ── Bancário: painel de taxas BACEN ao vivo ───────────────────────────────────
@router.get("/bancario/ferramentas/taxas-bacen")
async def bancario_taxas_bacen(cu: User = Depends(require_roles(_EQUIPE))):
    """Últimos valores oficiais SGS/BCB (SELIC meta, CDI, TR, IPCA-15).
    Fachada de bcb_service.painel_taxas — shape do TaxasBacenView (RamoBase.tsx)."""
    from app.services import bcb_service
    taxas = await bcb_service.painel_taxas()
    return {
        "taxas": taxas,
        "fonte": "Banco Central do Brasil — SGS (api.bcb.gov.br), séries 432 · 12 · 226 · 7478",
        "aviso": "Últimos valores oficiais divulgados pelo BCB. Para taxa média por modalidade "
                 "de crédito (tese de juros abusivos), use o Comparador de Juros BACEN.",
    }


# ── Tributário: auto de infração — prazos e reduções ──────────────────────────
@router.get("/tributario/ferramentas/auto-infracao-prazos")
async def trib_auto_infracao_prazos(
    data_ciencia: date,
    valor_multa: float = Query(0.0, ge=0),
    esfera: Literal["federal", "estadual", "municipal"] = "federal",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prazo de impugnação de auto de infração tributário (federal: 30 dias —
    Decreto 70.235/72 art. 15) e reduções de multa de ofício (Lei 8.218/91 art. 6º)."""
    venc = prazo_dias_corridos(data_ciencia, 30)   # corridos, prorroga p/ dia útil
    out: dict = {
        "esfera": esfera,
        "prazo_impugnacao": "30 dias corridos da ciência do auto",
        "data_ciencia": data_ciencia,
        "vencimento_impugnacao": venc,
        "dias_restantes": max((venc - date.today()).days, 0),
        "efeito_da_impugnacao": "Impugnação tempestiva SUSPENDE a exigibilidade do crédito "
                                "tributário (CTN art. 151 III).",
    }
    if esfera == "federal":
        out["reducoes_multa_de_oficio"] = {
            "pagamento_em_30_dias": {"reducao_pct": 50, "multa_reduzida": round(valor_multa * 0.50, 2)},
            "parcelamento_requerido_em_30_dias": {"reducao_pct": 40, "multa_reduzida": round(valor_multa * 0.60, 2)},
            "pagamento_em_30_dias_da_decisao_1a_instancia": {"reducao_pct": 30, "multa_reduzida": round(valor_multa * 0.70, 2)},
            "parcelamento_em_30_dias_da_decisao_1a_instancia": {"reducao_pct": 20, "multa_reduzida": round(valor_multa * 0.80, 2)},
            "base": "Lei 8.218/91 art. 6º",
        }
        out["fluxo_recursal"] = [
            "Impugnação à DRJ — 30 dias da ciência (Dec. 70.235 art. 15)",
            "Recurso voluntário ao CARF — 30 dias da ciência da decisão (art. 33)",
            "Recurso especial à CSRF — 15 dias, em caso de divergência (art. 37 §2º)",
        ]
        out["base"] = "Decreto 70.235/72 arts. 5º, 15, 33 e 37 · CTN art. 151 III · Lei 8.218/91 art. 6º."
    else:
        out["observacao_esfera"] = ("O prazo típico é de 30 dias, mas cada ente tem seu processo "
                                    "administrativo fiscal próprio (MG: RPTA — Dec. 44.747/2008, "
                                    "30 dias). CONFERIR a legislação indicada no próprio auto.")
        out["base"] = "Legislação de processo administrativo fiscal do ente · CTN art. 151 III."
    out["aviso"] = "MINUTA — confirmar a data exata de ciência (AR, DTe, publicação) e a lei local."
    return out


# ── Tributário: prescrição e decadência (CTN 150/173/174) ─────────────────────
@router.get("/tributario/ferramentas/prescricao-decadencia")
async def trib_prescricao_decadencia(
    data_fato_gerador: date,
    tipo: Literal["lancamento", "homologacao", "credito_nao_constituido"] = "homologacao",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Decadência do direito de lançar (CTN 150 §4º/173 I) e prescrição da
    cobrança do crédito constituído (CTN 174) — sempre 5 anos, marcos distintos."""
    if tipo == "homologacao":
        limite = _mais_anos(data_fato_gerador, 5)
        return {
            "instituto": "DECADÊNCIA — tributo por homologação COM pagamento antecipado",
            "marco_inicial": "Data do fato gerador",
            "prazo": "5 anos",
            "data_limite_para_o_fisco_lancar": limite,
            "dias_restantes": max((limite - date.today()).days, 0),
            "excecao": "SEM pagamento antecipado, ou havendo dolo/fraude/simulação, aplica-se o "
                       "art. 173 I — 1º dia do exercício seguinte (STJ REsp 973.733, repetitivo).",
            "base_legal": "CTN art. 150 §4º.",
            "aviso": "MINUTA — revisão humana obrigatória.",
        }
    if tipo == "credito_nao_constituido":
        marco = date(data_fato_gerador.year + 1, 1, 1)
        limite = _mais_anos(marco, 5)
        return {
            "instituto": "DECADÊNCIA — lançamento de ofício/sem pagamento antecipado",
            "marco_inicial": f"1º dia do exercício seguinte ({marco.isoformat()})",
            "prazo": "5 anos",
            "data_limite_para_o_fisco_lancar": limite,
            "dias_restantes": max((limite - date.today()).days, 0),
            "base_legal": "CTN art. 173 I.",
            "aviso": "MINUTA — notificação de medida preparatória antecipa o marco (art. 173 § único).",
        }
    # lancamento — crédito definitivamente constituído: prescrição da cobrança
    limite = _mais_anos(data_fato_gerador, 5)
    return {
        "instituto": "PRESCRIÇÃO — cobrança do crédito definitivamente constituído",
        "marco_inicial": "Constituição definitiva do crédito (fim do prazo de impugnação ou "
                         "decisão administrativa final) — informe essa data no campo de data",
        "prazo": "5 anos",
        "data_limite_para_execucao_fiscal": limite,
        "dias_restantes": max((limite - date.today()).days, 0),
        "interrupcoes": [
            "Despacho que ordena a citação em execução fiscal (CTN 174 § único I — LC 118/05)",
            "Protesto judicial (II)", "Ato judicial que constitua em mora (III)",
            "Confissão de dívida/parcelamento (IV — reinicia o prazo)",
        ],
        "prescricao_intercorrente": "Execução fiscal: 1 ano de suspensão + 5 anos de arquivamento "
                                    "(LEF art. 40 · STJ REsp 1.340.553, repetitivo).",
        "base_legal": "CTN art. 174 · Lei 6.830/80 art. 40.",
        "aviso": "MINUTA — verificar causas de suspensão da exigibilidade (CTN 151).",
    }


# ── Tributário: simulação de parcelamento ─────────────────────────────────────
# Constantes documentadas por modalidade. PERT/REFIS são programas ENCERRADOS —
# mantidos como referência histórica; a via atual é a transação tributária
# (Lei 13.988/2020). Simulação SIMPLIFICADA: não aplica Selic futura.
_MODALIDADES_PARCELAMENTO = {
    "pert": {"rotulo": "PERT — Lei 13.496/2017 (encerrado; referência)",
             "max_parcelas": 145, "parcela_minima": 1000.0,
             "reducao_juros_pct": 90, "reducao_multa_pct": 70,
             "nota": "Reduções máximas do programa (pagamento à vista do saldo). "
                     "Hoje: transação tributária — desconto de até 65% (100% de juros/multas), "
                     "até 120 meses (Lei 13.988/20 art. 11)."},
    "refis": {"rotulo": "REFIS/PAES (encerrados; referência histórica)",
              "max_parcelas": 180, "parcela_minima": 100.0,
              "reducao_juros_pct": 45, "reducao_multa_pct": 40,
              "nota": "Programas especiais encerrados. Usar transação tributária "
                      "(Lei 13.988/20) para débitos federais atuais."},
    "simples": {"rotulo": "Parcelamento do Simples Nacional",
                "max_parcelas": 60, "parcela_minima": 300.0,
                "reducao_juros_pct": 0, "reducao_multa_pct": 0,
                "nota": "LC 123/06 art. 21 §15 · Res. CGSN 140/18 arts. 46-55. "
                        "Sem descontos; parcela mínima R$ 300,00; juros Selic."},
    "parcelamento_comum": {"rotulo": "Parcelamento ordinário federal",
                           "max_parcelas": 60, "parcela_minima": 100.0,
                           "reducao_juros_pct": 0, "reducao_multa_pct": 0,
                           "nota": "Lei 10.522/02 arts. 10-14-A. Sem descontos; "
                                   "parcelas acrescidas de Selic."},
}


@router.get("/tributario/ferramentas/parcelamento")
async def trib_parcelamento(
    valor_total_debito: float = Query(..., gt=0),
    parcelas: int = Query(60, gt=0),
    modalidade: str = "pert",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Simulação SIMPLIFICADA de parcelamento tributário por modalidade."""
    m = _MODALIDADES_PARCELAMENTO.get(modalidade)
    if not m:
        raise HTTPException(422, f"Modalidade inválida. Use: {list(_MODALIDADES_PARCELAMENTO)}")
    parcelas_ef = min(parcelas, m["max_parcelas"])
    parcela_base = round(valor_total_debito / parcelas_ef, 2)
    abaixo_minimo = parcela_base < m["parcela_minima"]
    if abaixo_minimo:
        parcelas_ef = max(1, int(valor_total_debito // m["parcela_minima"]) or 1)
        parcela_base = round(valor_total_debito / parcelas_ef, 2)
    return {
        "modalidade": m["rotulo"],
        "valor_total_debito": valor_total_debito,
        "parcelas_solicitadas": parcelas,
        "parcelas_simuladas": parcelas_ef,
        "parcela_estimada_sem_juros": parcela_base,
        "parcela_minima_da_modalidade": m["parcela_minima"],
        "ajustado_pela_parcela_minima": abaixo_minimo,
        "reducoes_potenciais": {"juros_pct": m["reducao_juros_pct"],
                                "multa_pct": m["reducao_multa_pct"],
                                "nota": "Reduções incidem sobre JUROS e MULTAS (não sobre o principal); "
                                        "dependem da composição do débito e das regras do programa."},
        "memoria_calculo": f"parcela = R$ {valor_total_debito:.2f} ÷ {parcelas_ef} (sem Selic futura)",
        "observacao": m["nota"],
        "base": "CTN art. 151 VI e 155-A · Lei 10.522/02 · LC 123/06 · Lei 13.988/20 (transação).",
        "aviso": "SIMULAÇÃO SIMPLIFICADA — não aplica Selic futura nem consolida o débito; "
                 "o valor real é apurado no sistema do órgão (e-CAC/PGFN/PGE).",
    }


# ── Tributário: alíquota efetiva do Simples Nacional ──────────────────────────
# Tabelas OFICIAIS da LC 123/2006 (redação da LC 155/2016, vigente desde 2018 e
# inalterada até 2026): (limite superior RBT12, alíquota nominal %, parcela a
# deduzir R$). Fonte: LC 123/06, Anexos I a V · Res. CGSN 140/2018.
_SIMPLES_ANEXOS: dict[str, list[tuple[float, float, float]]] = {
    "I":   [(180_000, 4.0, 0), (360_000, 7.3, 5_940), (720_000, 9.5, 13_860),
            (1_800_000, 10.7, 22_500), (3_600_000, 14.3, 87_300), (4_800_000, 19.0, 378_000)],
    "II":  [(180_000, 4.5, 0), (360_000, 7.8, 5_940), (720_000, 10.0, 13_860),
            (1_800_000, 11.2, 22_500), (3_600_000, 14.7, 85_500), (4_800_000, 30.0, 720_000)],
    "III": [(180_000, 6.0, 0), (360_000, 11.2, 9_360), (720_000, 13.5, 17_640),
            (1_800_000, 16.0, 35_640), (3_600_000, 21.0, 125_640), (4_800_000, 33.0, 648_000)],
    "IV":  [(180_000, 4.5, 0), (360_000, 9.0, 8_100), (720_000, 10.2, 12_420),
            (1_800_000, 14.0, 39_780), (3_600_000, 22.0, 183_780), (4_800_000, 33.0, 828_000)],
    "V":   [(180_000, 15.5, 0), (360_000, 18.0, 4_500), (720_000, 19.5, 9_900),
            (1_800_000, 20.5, 17_100), (3_600_000, 23.0, 62_100), (4_800_000, 30.5, 540_000)],
}
_SIMPLES_ROTULOS = {
    "I": "Comércio", "II": "Indústria", "III": "Serviços (§5º-B... — locação de bens, etc.)",
    "IV": "Serviços (construção, advocacia, vigilância — CPP fora do DAS)",
    "V": "Serviços intelectuais (tecnologia, engenharia, auditoria)",
}


@router.get("/tributario/ferramentas/simples-nacional")
async def trib_simples_nacional(
    receita_bruta_12m: float = Query(..., gt=0),
    anexo: Literal["I", "II", "III", "IV", "V"] = "III",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Faixa, alíquota nominal e alíquota EFETIVA do Simples Nacional por RBT12.
    Fórmula legal: (RBT12 × alíquota nominal − parcela a deduzir) ÷ RBT12
    (LC 123/06 art. 18 §1º-A)."""
    if receita_bruta_12m > 4_800_000:
        return {
            "excede_teto": True,
            "rbt12": receita_bruta_12m,
            "teto_simples": 4_800_000.0,
            "consequencia": "Receita acima de R$ 4,8 milhões — EXCLUSÃO do Simples Nacional "
                            "(LC 123 art. 3º II); avaliar Lucro Presumido ou Real.",
            "base": "LC 123/2006 art. 3º II.",
            "aviso": "MINUTA — revisão humana obrigatória.",
        }
    tabela = _SIMPLES_ANEXOS[anexo]
    faixa_n, (aliq, pd) = 1, (tabela[0][1], tabela[0][2])
    for i, (limite, a, p) in enumerate(tabela, start=1):
        if receita_bruta_12m <= limite:
            faixa_n, aliq, pd = i, a, p
            break
    efetiva = (receita_bruta_12m * (aliq / 100) - pd) / receita_bruta_12m * 100
    das_mensal_estimado = round(receita_bruta_12m / 12 * efetiva / 100, 2)
    out = {
        "anexo": f"Anexo {anexo} — {_SIMPLES_ROTULOS[anexo]}",
        "rbt12": receita_bruta_12m,
        "faixa": faixa_n,
        "aliquota_nominal_pct": aliq,
        "parcela_a_deduzir": pd,
        "aliquota_efetiva_pct": round(efetiva, 4),
        "das_mensal_estimado": das_mensal_estimado,
        "memoria_calculo": (f"efetiva = (RBT12 {receita_bruta_12m:.2f} × {aliq}% − PD {pd:.2f}) "
                            f"÷ RBT12 = {efetiva:.4f}%"),
        "base": "LC 123/2006 art. 18 e Anexos I-V (red. LC 155/2016) · Res. CGSN 140/2018.",
        "aviso": "MINUTA — DAS estimado sobre a receita média mensal (RBT12/12); o cálculo real "
                 "usa a receita do MÊS. Verificar segregação de receitas e ICMS/ISS no sublimite.",
    }
    if anexo in ("III", "V"):
        out["fator_r"] = ("Folha de salários ≥ 28% da receita (Fator R) desloca atividades do "
                          "Anexo V para o III — e vice-versa (LC 123 art. 18 §5º-J/§5º-M).")
    if receita_bruta_12m > 3_600_000:
        out["sublimite"] = ("RBT12 acima de R$ 3,6 mi: ICMS e ISS são recolhidos FORA do DAS, "
                            "pelo regime normal (LC 123 arts. 13-A e 19-20).")
    return out


# ── Tributário: comparativo de regimes ────────────────────────────────────────
@router.get("/tributario/ferramentas/regime-tributario")
async def trib_regime_tributario(
    receita_bruta_anual: float = Query(..., gt=0),
    lucro_estimado_pct: float = Query(20.0, ge=0, le=100),
    atividade: Literal["comercio", "industria", "servicos"] = "servicos",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Comparativo ESTIMADO Simples × Lucro Presumido × Lucro Real (federais).
    Estimativa simplificada e documentada — NÃO substitui estudo tributário."""
    receita = receita_bruta_anual
    anexo = {"comercio": "I", "industria": "II", "servicos": "III"}[atividade]

    # Simples: alíquota efetiva do anexo correspondente (RBT12 = receita anual)
    simples: dict
    if receita > 4_800_000:
        simples = {"elegivel": False, "motivo": "Receita acima do teto de R$ 4,8 mi (LC 123 art. 3º II)"}
    else:
        tabela = _SIMPLES_ANEXOS[anexo]
        aliq, pd = tabela[0][1], tabela[0][2]
        for limite, a, p in tabela:
            if receita <= limite:
                aliq, pd = a, p
                break
        efetiva = (receita * (aliq / 100) - pd) / receita * 100
        simples = {"elegivel": True, "anexo": anexo,
                   "aliquota_efetiva_pct": round(efetiva, 4),
                   "carga_anual_estimada": round(receita * efetiva / 100, 2),
                   "nota": "DAS inclui IRPJ/CSLL/PIS/COFINS/CPP e ICMS ou ISS (até o sublimite)."}

    # Lucro Presumido: presunção 8%/32% (IRPJ) e 12%/32% (CSLL) + PIS/COFINS cumulativos
    pres_irpj_base = receita * (0.32 if atividade == "servicos" else 0.08)
    pres_csll_base = receita * (0.32 if atividade == "servicos" else 0.12)
    irpj_pres = pres_irpj_base * 0.15 + max(0.0, pres_irpj_base - 240_000) * 0.10
    csll_pres = pres_csll_base * 0.09
    piscofins_pres = receita * 0.0365          # PIS 0,65% + COFINS 3% (cumulativo)
    total_pres = round(irpj_pres + csll_pres + piscofins_pres, 2)

    # Lucro Real: IRPJ/CSLL sobre lucro estimado + PIS/COFINS não cumulativos (sem créditos)
    lucro = receita * lucro_estimado_pct / 100
    irpj_real = lucro * 0.15 + max(0.0, lucro - 240_000) * 0.10
    csll_real = lucro * 0.09
    piscofins_real = receita * 0.0925          # PIS 1,65% + COFINS 7,6% (SEM estimar créditos)
    total_real = round(irpj_real + csll_real + piscofins_real, 2)

    return {
        "parametros": {"receita_bruta_anual": receita, "atividade": atividade,
                       "lucro_estimado_pct": lucro_estimado_pct},
        "simples_nacional": simples,
        "lucro_presumido": {
            "carga_anual_estimada": total_pres,
            "pct_da_receita": round(total_pres / receita * 100, 2),
            "detalhe": {"irpj": round(irpj_pres, 2), "csll": round(csll_pres, 2),
                        "pis_cofins_cumulativo": round(piscofins_pres, 2)},
            "nota": "Não inclui ISS/ICMS nem CPP patronal (20% da folha).",
        },
        "lucro_real": {
            "carga_anual_estimada": total_real,
            "pct_da_receita": round(total_real / receita * 100, 2),
            "detalhe": {"irpj": round(irpj_real, 2), "csll": round(csll_real, 2),
                        "pis_cofins_nao_cumulativo": round(piscofins_real, 2)},
            "nota": "PIS/COFINS não cumulativos calculados SEM créditos (superestimado); "
                    "não inclui ISS/ICMS nem CPP.",
        },
        "premissas": [
            "Presunção do Presumido: IRPJ 8% (comércio/indústria) ou 32% (serviços); "
            "CSLL 12% ou 32% (Lei 9.249/95 arts. 15 e 20).",
            "IRPJ 15% + adicional de 10% sobre a base que exceder R$ 240 mil/ano; CSLL 9%.",
            "Comparativo cobre apenas tributos FEDERAIS sobre receita/lucro.",
        ],
        "base": "LC 123/06 · Lei 9.249/95 arts. 15/20 · Lei 9.430/96 · Leis 10.637/02 e 10.833/03.",
        "aviso": "ESTIMATIVA SIMPLIFICADA — a escolha real exige estudo com folha, créditos, "
                 "ISS/ICMS e benefícios setoriais. Revisão humana obrigatória.",
    }


# ── Tributário: reforma tributária (EC 132/2023 · LC 214/2025) ────────────────
_REFORMA_CRONOGRAMA = {
    "2026": "Fase-teste: CBS 0,9% + IBS 0,1%, compensáveis com PIS/COFINS "
            "(dispensa de recolhimento para quem cumprir as obrigações acessórias).",
    "2027": "CBS em alíquota cheia substitui PIS/COFINS (extintos); Imposto Seletivo (IS) "
            "entra em vigor; IPI zerado, exceto Zona Franca de Manaus; IBS a 0,1%.",
    "2029": "Início da transição do IBS: ICMS e ISS reduzidos a 90% das alíquotas; "
            "IBS sobe proporcionalmente.",
    "2030": "ICMS/ISS a 80% — IBS continua subindo.",
    "2031": "ICMS/ISS a 70%.",
    "2032": "ICMS/ISS a 60% — último ano dos tributos antigos.",
    "2033": "Extinção definitiva de ICMS e ISS — vigência plena do IVA dual (IBS + CBS).",
}
_REFORMA_ATIVIDADE = {
    "comercio":    "Tendência NEUTRA/redução: crédito amplo na cadeia compensa a alíquota nova.",
    "industria":   "Tendência de REDUÇÃO: fim da cumulatividade e desoneração de investimentos/exportações.",
    "servicos":    "Tendência de AUMENTO de carga: alíquota de referência (~28%) supera o atual "
                   "ISS+PIS/COFINS típico; impacto menor para quem vende a empresas (crédito ao cliente).",
    "financeiro":  "Regime ESPECÍFICO (LC 214): base e alíquota próprias para operações financeiras.",
    "imobiliario": "Regime ESPECÍFICO (LC 214): redutores de base e alíquota reduzida para locação/venda.",
}


@router.get("/tributario/ferramentas/reforma-tributaria")
async def trib_reforma_tributaria(
    receita_bruta_anual: float = Query(..., gt=0),
    regime_atual: Literal["simples", "lucro_presumido", "lucro_real"] = "simples",
    atividade: Literal["comercio", "industria", "servicos", "financeiro", "imobiliario"] = "servicos",
    ano_analise: Literal["2026", "2027", "2029", "2030", "2031", "2032", "2033"] = "2026",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Informativo estruturado da transição CBS/IBS (EC 132/2023 · LC 214/2025)."""
    if regime_atual == "simples":
        impacto_regime = ("O Simples Nacional PERMANECE (EC 132 preserva o regime). Novidade: opção "
                          "de apurar IBS/CBS 'por fora' do DAS para transferir crédito integral aos "
                          "clientes PJ — relevante em vendas B2B (LC 214).")
    elif regime_atual == "lucro_presumido":
        impacto_regime = ("PIS/COFINS (3,65% cumulativo) são substituídos pela CBS não cumulativa — "
                          "alíquota maior, porém com créditos amplos; avaliar migração de preços e "
                          "créditos da cadeia. ISS/ICMS migram ao IBS em 2029-2032.")
    else:
        impacto_regime = ("PIS/COFINS (9,25% não cumulativo) → CBS com crédito AMPLO (base financeira): "
                          "tende a simplificar e reduzir litígio sobre insumos. ISS/ICMS → IBS em 2029-2032.")
    estimativa_iva = round(receita_bruta_anual * 0.265, 2)
    return {
        "ano_analise": ano_analise,
        "marco_do_ano": _REFORMA_CRONOGRAMA[ano_analise],
        "cronograma_completo": _REFORMA_CRONOGRAMA,
        "impacto_no_regime_atual": impacto_regime,
        "impacto_da_atividade": _REFORMA_ATIVIDADE[atividade],
        "estimativa_informativa_iva_pleno": {
            "aliquota_referencia_pct": 26.5,
            "valor_anual_bruto_sobre_receita": estimativa_iva,
            "nota": "Alíquota de REFERÊNCIA estimada (trava de 26,5% — LC 214); valor bruto SEM "
                    "créditos, que reduzem substancialmente a carga efetiva. Para Simples, só se "
                    "aplica na opção de apuração 'por fora'.",
        },
        "novos_tributos": {
            "CBS": "Contribuição sobre Bens e Serviços (federal) — substitui PIS/COFINS/IPI.",
            "IBS": "Imposto sobre Bens e Serviços (estados+municípios) — substitui ICMS/ISS.",
            "IS": "Imposto Seletivo — bens/serviços prejudiciais à saúde e ao meio ambiente.",
        },
        "base": "EC 132/2023 · LC 214/2025 · ADCT arts. 125-133 (cronograma de transição).",
        "aviso": "INFORMATIVO — regulamentações complementares em edição; alíquotas de referência "
                 "serão fixadas por resolução do Senado. Revisão humana obrigatória.",
    }


# ── Ambiental: auto de infração (Dec. 6.514/2008) ─────────────────────────────
@router.get("/ambiental/ferramentas/auto-infracao-ambiental")
async def amb_auto_infracao(
    data_ciencia: date,
    valor_multa: float = Query(0.0, ge=0),
    tipo_infracao: str = "degradacao",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prazos, descontos e teses de defesa contra auto de infração ambiental
    federal (Lei 9.605/98 · Decreto 6.514/2008)."""
    prazos = prazo_defesa_ambiental(data_ciencia)   # 20 dias — utilitário canônico do EJC
    return {
        "prazo_defesa": "20 dias contados da ciência da autuação",
        "vencimento_legal": prazos["data_legal"],
        "protocolo_interno_sugerido": prazos["data_interna"],
        "dias_restantes": prazos["dias_restantes"],
        "tipo_infracao": tipo_infracao,
        "valor_multa": valor_multa,
        "pagamento_com_desconto": {
            "desconto_pct": 30,
            "valor_com_desconto": round(valor_multa * 0.70, 2),
            "condicao": "Pagamento no prazo de defesa (Dec. 6.514 art. 4º §1º) — implica "
                        "renúncia à defesa.",
        },
        "conversao_da_multa": {
            "ate_a_defesa": {"desconto_pct": 60, "valor": round(valor_multa * 0.40, 2)},
            "apos_a_defesa_ate_alegacoes": {"desconto_pct": 35, "valor": round(valor_multa * 0.65, 2)},
            "descricao": "Conversão em serviços de preservação/recuperação ambiental "
                         "(Dec. 6.514 arts. 139-148, red. Dec. 9.179/2017).",
        },
        "fluxo": [
            "Defesa — 20 dias da ciência (art. 113); conciliação ambiental quando cabível (art. 95-A)",
            "Alegações finais — 10 dias do encerramento da instrução (art. 122)",
            "Recurso à autoridade superior — 20 dias da ciência da decisão (art. 127)",
        ],
        "teses_usuais": [
            "Vícios formais do auto (competência, descrição do fato, dosimetria sem motivação)",
            "Atenuantes do art. 14 da Lei 9.605 (baixo grau de instrução, reparação espontânea)",
            "Prescrição quinquenal da pretensão punitiva (Lei 9.873/99 art. 1º) e "
            "intercorrente de 3 anos (art. 1º §1º)",
            "Ausência de dano ou de dolo/culpa na conduta específica",
        ],
        "base": "Lei 9.605/98 arts. 14-15 e 70-76 · Decreto 6.514/2008 arts. 4º, 95-A, 113, "
                "122, 127 e 139-148 · Lei 9.873/99 art. 1º.",
        "aviso": "MINUTA — órgãos ESTADUAIS/municipais têm ritos próprios; conferir a lei do "
                 "órgão autuador indicada no auto.",
    }


# ── Ambiental: crimes ambientais (Lei 9.605/98) ───────────────────────────────
_CRIMES_AMBIENTAIS = {
    "desmatamento": {"tipo": "Destruir/danificar floresta de preservação permanente",
                     "artigo": "art. 38", "pena": "detenção de 1 a 3 anos e/ou multa",
                     "pena_min_anos": 1.0, "pena_max_anos": 3.0},
    "poluicao":     {"tipo": "Poluição que possa resultar danos à saúde ou mortandade de animais",
                     "artigo": "art. 54", "pena": "reclusão de 1 a 4 anos e multa "
                     "(qualificada §2º: 1 a 5 anos)", "pena_min_anos": 1.0, "pena_max_anos": 4.0},
    "fauna":        {"tipo": "Matar/perseguir/caçar espécimes da fauna silvestre sem autorização",
                     "artigo": "art. 29", "pena": "detenção de 6 meses a 1 ano e multa",
                     "pena_min_anos": 0.5, "pena_max_anos": 1.0},
    "flora":        {"tipo": "Crimes contra a flora (cortar árvores em APP, incêndio etc.)",
                     "artigo": "arts. 38-53", "pena": "detenção/reclusão de 3 meses a 4 anos "
                     "conforme o tipo (incêndio, art. 41: reclusão 2-4 anos)",
                     "pena_min_anos": 0.25, "pena_max_anos": 4.0},
    "mineracao":    {"tipo": "Pesquisa/lavra sem autorização (c/c usurpação, Lei 8.176/91)",
                     "artigo": "art. 55", "pena": "detenção de 6 meses a 1 ano e multa",
                     "pena_min_anos": 0.5, "pena_max_anos": 1.0},
    "residuos":     {"tipo": "Produtos/substâncias tóxicas em desacordo com a lei",
                     "artigo": "art. 56", "pena": "reclusão de 1 a 4 anos e multa",
                     "pena_min_anos": 1.0, "pena_max_anos": 4.0},
    "upa":          {"tipo": "Dano a Unidade de Conservação",
                     "artigo": "art. 40", "pena": "reclusão de 1 a 5 anos",
                     "pena_min_anos": 1.0, "pena_max_anos": 5.0},
}


@router.get("/ambiental/ferramentas/crimes-ambientais")
async def amb_crimes_ambientais(
    tipo_crime: str = "poluicao",
    pessoa: Literal["fisica", "juridica"] = "fisica",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Penas e institutos despenalizadores por tipo de crime ambiental (Lei 9.605/98)."""
    crime = _CRIMES_AMBIENTAIS.get(tipo_crime)
    if not crime:
        raise HTTPException(422, f"Tipo inválido. Use: {list(_CRIMES_AMBIENTAIS)}")
    institutos = []
    if crime["pena_max_anos"] <= 2:
        institutos.append("Transação penal (IMPO — Lei 9.099/95 art. 76), CONDICIONADA à prévia "
                          "composição do dano ambiental (Lei 9.605 art. 27)")
    if crime["pena_min_anos"] <= 1:
        institutos.append("Suspensão condicional do processo (Lei 9.099 art. 89), com reparação "
                          "do dano como condição (Lei 9.605 art. 28)")
    if crime["pena_min_anos"] < 4:
        institutos.append("ANPP — acordo de não persecução penal (CPP art. 28-A), exige reparação "
                          "do dano quando possível")
    out: dict = {
        "crime": crime["tipo"],
        "artigo": f"Lei 9.605/98, {crime['artigo']}",
        "pena": crime["pena"],
        "institutos_cabiveis": institutos or
            ["Pena elevada — avaliar atenuantes (art. 14) e sursis da pena (CP art. 77)"],
        "responsabilidade_civil": "OBJETIVA e propter rem — independe de culpa; obrigação de "
                                  "reparar é imprescritível (Lei 6.938/81 art. 14 §1º · STF RE "
                                  "654.833 · STJ Súm. 623).",
        "tripla_responsabilizacao": "Penal, administrativa e civil são INDEPENDENTES "
                                    "(CF art. 225 §3º).",
    }
    if pessoa == "juridica":
        out["pessoa_juridica"] = {
            "responsabilidade_penal": "Cabível (Lei 9.605 art. 3º) — STF/STJ dispensam a dupla "
                                      "imputação obrigatória (RE 548.181).",
            "penas_aplicaveis": "Multa, restritivas de direitos (suspensão de atividades, "
                                "interdição, proibição de contratar com o Poder Público) e "
                                "prestação de serviços à comunidade (arts. 21-23).",
            "desconsideracao": "Personalidade jurídica pode ser desconsiderada se obstáculo ao "
                               "ressarcimento (art. 4º).",
        }
    out["base"] = "Lei 9.605/98 · Lei 9.099/95 arts. 76 e 89 · CPP art. 28-A · CF art. 225 §3º."
    out["aviso"] = "MINUTA — dosimetria e cabimento concreto dependem do caso (circunstâncias do art. 6º)."
    return out


# ── Ambiental: TAC (Lei 7.347/85 art. 5º §6º) ─────────────────────────────────
@router.get("/ambiental/ferramentas/tac-ambiental")
async def amb_tac(
    orgao_proponente: Literal["mp", "ibama", "estado", "municipio"] = "mp",
    tipo_dano: str = "desmatamento",
    area_afetada_ha: float = Query(0.0, ge=0),
    valor_estimado_dano: float = Query(0.0, ge=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Requisitos, cláusulas essenciais e efeitos do Termo de Ajustamento de Conduta."""
    legitimados = {
        "mp": "Ministério Público — legitimado clássico (Lei 7.347 art. 5º §6º)",
        "ibama": "IBAMA/ICMBio — órgãos públicos legitimados; TAC suspende exigibilidade da "
                 "multa convertível (Dec. 6.514 art. 146)",
        "estado": "Estado/órgão ambiental estadual (SEMAD/FEAM em MG)",
        "municipio": "Município/órgão ambiental municipal licenciador",
    }
    return {
        "orgao_proponente": legitimados[orgao_proponente],
        "tipo_dano": tipo_dano,
        "area_afetada_ha": area_afetada_ha,
        "valor_estimado_dano": valor_estimado_dano,
        "natureza": "Título executivo EXTRAJUDICIAL (Lei 7.347 art. 5º §6º) — descumprimento "
                    "leva direto à execução, sem nova fase de conhecimento.",
        "clausulas_essenciais": [
            "Identificação completa do dano e da área (georreferenciamento quando cabível)",
            "Obrigações de fazer/não fazer com CRONOGRAMA físico e prazos objetivos",
            "Multa (astreintes) por descumprimento de cada obrigação",
            "Garantias e responsáveis técnicos (ART) pela recuperação",
            "Critérios de monitoramento, laudos periódicos e condições de quitação",
        ],
        "efeitos": [
            "Suspende ações civis públicas sobre o mesmo objeto enquanto cumprido",
            "NÃO impede a ação penal (esferas independentes — CF art. 225 §3º); pode, porém, "
            "fundamentar composição do dano p/ transação penal (Lei 9.605 art. 27)",
            "Art. 79-A da Lei 9.605: TAC com órgão ambiental para adequação gradual de "
            "empreendimentos poluidores",
        ],
        "vantagens": [
            "Evita litígio longo e condenação com juros/honorários",
            "Permite parcelamento e execução gradual da recuperação",
            "Demonstra boa-fé — atenuante administrativa e penal (Lei 9.605 art. 14 II)",
        ],
        "base": "Lei 7.347/85 art. 5º §6º · Lei 9.605/98 arts. 27 e 79-A · Dec. 6.514/08 arts. 139-148.",
        "aviso": "MINUTA — o conteúdo do TAC é negocial; revisar cada cláusula com o órgão proponente.",
    }


# ── Ambiental: licenciamento (LC 140/2011 · CONAMA 237/97) ────────────────────
_FASES_LICENCA = {
    "lp": {"nome": "LP — Licença Prévia", "fase": "Planejamento: aprova localização e concepção, "
           "atesta viabilidade ambiental e fixa condicionantes das próximas fases",
           "validade": "Até 5 anos (mínimo: cronograma do projeto)",
           "docs": ["Requerimento e FCE/FOB do órgão", "Certidão de uso e ocupação do solo",
                    "EIA/RIMA ou estudo simplificado (RCA), conforme o porte/potencial",
                    "Publicidade do pedido (CONAMA 006/86)"]},
    "li": {"nome": "LI — Licença de Instalação", "fase": "Autoriza a INSTALAÇÃO conforme projeto "
           "aprovado, incluindo medidas de controle e condicionantes",
           "validade": "Até 6 anos",
           "docs": ["Projeto executivo/PCA (Plano de Controle Ambiental)", "Outorga de uso da "
                    "água (se aplicável)", "ART do responsável técnico",
                    "Comprovação de cumprimento das condicionantes da LP"]},
    "lo": {"nome": "LO — Licença de Operação", "fase": "Autoriza a OPERAÇÃO após verificação do "
           "cumprimento das licenças anteriores",
           "validade": "4 a 10 anos (renovação: requerer 120 dias antes de expirar — prorrogação "
           "automática até decisão, CONAMA 237 art. 18 §4º)",
           "docs": ["Comprovação das condicionantes da LI", "Testes/pré-operação quando exigidos",
                    "Programas de monitoramento e automonitoramento"]},
}


@router.get("/ambiental/ferramentas/licenciamento")
async def amb_licenciamento(
    fase: Literal["lp", "li", "lo"] = "lp",
    porte: Literal["pequeno", "medio", "grande"] = "medio",
    data_protocolo: Optional[date] = None,
    com_eia_rima: bool = False,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Fases, documentos mínimos e prazos do licenciamento ambiental."""
    f = _FASES_LICENCA[fase]
    out: dict = {
        "licenca": f["nome"],
        "para_que_serve": f["fase"],
        "validade": f["validade"],
        "documentos_minimos": f["docs"],
        "prazo_de_analise": "6 meses do protocolo (12 meses quando há EIA/RIMA ou audiência "
                            "pública) — CONAMA 237 art. 14 §... contagem suspensa durante "
                            "exigências ao empreendedor.",
        "porte": porte,
        "nota_porte": ("Porte/potencial poluidor definem o ENQUADRAMENTO, taxas e a modalidade "
                       "(MG: DN COPAM 217/2017 — classes 1-8; pequeno porte pode se enquadrar em "
                       "LAS/licenciamento simplificado ou concomitante)."),
        "competencia": "Definida pela LC 140/2011 (arts. 7º-10): União (IBAMA) — impacto "
                       "nacional/fronteiriço; Estado — regra residual; Município — impacto local.",
    }
    if data_protocolo:
        dias = 365 if com_eia_rima else 180
        out["data_protocolo"] = data_protocolo
        out["data_limite_analise_estimada"] = prazo_dias_corridos(data_protocolo, dias)
        out["nota_prazo"] = ("Estimativa em dias corridos (180/365); pedidos de complementação "
                             "SUSPENDEM a contagem (CONAMA 237 art. 14-15).")
    out["base"] = "LC 140/2011 · Res. CONAMA 237/97 arts. 8º, 14-15 e 18-19 · Lei 6.938/81."
    out["aviso"] = ("MINUTA — prazos e classes variam por estado (MG: SLA/SEMAD); conferir a "
                    "norma do órgão licenciador.")
    return out


# ── Ambiental: reserva legal (Lei 12.651/2012 arts. 12-17) ────────────────────
_RESERVA_LEGAL_PCT = {
    "amazonia":       (80, "Área de FLORESTA na Amazônia Legal — 80% (art. 12 I a)"),
    "cerrado":        (35, "CERRADO dentro da Amazônia Legal — 35% (art. 12 I b); "
                           "FORA da Amazônia Legal aplica-se a regra geral de 20%"),
    "pantanal":       (20, "Regra geral das demais regiões do País — 20% (art. 12 II)"),
    "caatinga":       (20, "Regra geral das demais regiões do País — 20% (art. 12 II)"),
    "mata_atlantica": (20, "Regra geral — 20% (art. 12 II); supressão de vegetação nativa "
                           "sujeita também à Lei 11.428/2006 (Lei da Mata Atlântica)"),
    "pampa":          (20, "Regra geral das demais regiões do País — 20% (art. 12 II)"),
}


@router.get("/ambiental/ferramentas/reserva-legal")
async def amb_reserva_legal(
    area_imovel_ha: float = Query(..., gt=0),
    bioma: str = "cerrado",
    inscrito_car: bool = False,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Percentual e área de Reserva Legal por bioma/localização (Código Florestal)."""
    regra = _RESERVA_LEGAL_PCT.get(bioma)
    if not regra:
        raise HTTPException(422, f"Bioma inválido. Use: {list(_RESERVA_LEGAL_PCT)}")
    pct, desc = regra
    area_rl = round(area_imovel_ha * pct / 100, 4)
    out: dict = {
        "bioma": bioma,
        "percentual_reserva_legal": pct,
        "regra_aplicada": desc,
        "area_imovel_ha": area_imovel_ha,
        "area_reserva_legal_ha": area_rl,
        "area_livre_uso_ha": round(area_imovel_ha - area_rl, 4),
        "memoria_calculo": f"RL = {area_imovel_ha} ha × {pct}% = {area_rl} ha",
        "car": ("✓ Inscrito no CAR — registro dispensa averbação em cartório (art. 18 §4º)."
                if inscrito_car else
                "✗ NÃO inscrito no CAR — inscrição é OBRIGATÓRIA (art. 29) e condição para "
                "aderir ao PRA e regularizar passivos (art. 59)."),
        "pequena_propriedade": "Imóvel de até 4 módulos fiscais: consolida-se a vegetação "
                               "existente em 22/07/2008 como RL (art. 67).",
        "app_nao_conta": "APP só computa no cálculo da RL nas condições do art. 15 "
                         "(não implicar novo desmatamento, CAR etc.).",
        "regularizacao_deficit": [
            "Recomposição em até 20 anos (1/10 a cada 2 anos — art. 66 §2º)",
            "Regeneração natural conduzida",
            "Compensação: CRA, arrendamento de servidão, doação de área em UC pendente "
            "de regularização fundiária (art. 66 §5º)",
        ],
        "base": "Lei 12.651/2012 arts. 12, 15, 17-18, 29, 59, 66-67.",
        "aviso": "MINUTA — enquadramento exato exige localização (Amazônia Legal?), módulos "
                 "fiscais e análise do CAR. Revisão humana obrigatória.",
    }
    return out
