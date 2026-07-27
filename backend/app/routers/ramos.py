# ── app/routers/ramos.py ──────────────────────────────────────────────────────
# Routers dos 6 ramos jurídicos especializados (além do Ambiental já existente).
# Padrão: CRUD + calculadoras/ferramentas específicas de cada área.
# Cada ramo tem: listar / criar / atualizar / remover (soft-delete) + ferramentas.
# HITL: todas as saídas de cálculo são minutas — revisão humana obrigatória.
from __future__ import annotations
import logging
import re
from calendar import monthrange
from datetime import date, timedelta
from functools import wraps
from decimal import Decimal
from uuid import uuid4
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
    prazo_dias_uteis, prazo_dias_corridos, prazo_defesa_ambiental, proximo_dia_util,
)
from app.schemas.areas_atuacao import (
    EmpresarialUpdate, CivelUpdate, PenalUpdate,
    TrabalhistaUpdate, AdminUpdate, BancarioUpdate,
    validar_tipo_societario,
)
from app.services.homologacao_ferramentas import (  # noqa: F401 (reexport p/ compat)
    FERRAMENTAS_BLOQUEADAS,
    FERRAMENTAS_NAO_HOMOLOGADAS,
    selo_homologacao as _selo_homologacao,
)
# `bloquear_nao_homologada` NÃO é importado aqui: nenhuma ferramenta está
# bloqueada hoje (FERRAMENTAS_BLOQUEADAS vazio). O mecanismo continua vivo no
# módulo de homologação — para bloquear uma ferramenta, importe a função no
# handler e adicione o caminho ao frozenset.

_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]
_ADM    = ["superadmin", "admin", "socio"]
_CENT   = Decimal("0.01")

# ── Tetos do depósito recursal trabalhista (CLT art. 899 §§1º-4º) ─────────────
# Tabela VERSIONADA por período de vigência. ATUALIZAÇÃO ANUAL OBRIGATÓRIA: o TST
# reajusta os tetos pelo IPCA-E e publica novo Ato de GP com vigência em agosto.
# Para atualizar: ADICIONE uma nova faixa no INÍCIO da lista (mais recente
# primeiro) e feche o `fim` da faixa anterior — nunca edite valores históricos.
TETOS_DEPOSITO_RECURSAL: list[dict] = [
    {"rotulo": "2025-2026",
     "inicio": date(2025, 8, 1), "fim": None,   # None = vigente (em aberto)
     "ro": 12_127.64, "rr": 24_255.28,
     "fonte": "Ato TST GP 323/2025 (reajuste anual pelo IPCA-E)"},
]

# Compatibilidade: constantes apontam para a faixa mais recente da tabela.
TETO_DEPOSITO_RO = TETOS_DEPOSITO_RECURSAL[0]["ro"]   # Recurso Ordinário
TETO_DEPOSITO_RR = TETOS_DEPOSITO_RECURSAL[0]["rr"]   # Recurso de Revista


def _teto_deposito_para(referencia: date) -> dict:
    """Faixa de tetos vigente na data de referência; sem tabela p/ o período → 422."""
    for faixa in TETOS_DEPOSITO_RECURSAL:
        if referencia >= faixa["inicio"] and (faixa["fim"] is None or referencia <= faixa["fim"]):
            return faixa
    raise HTTPException(422, (
        f"Não há tabela de tetos de depósito recursal cadastrada para "
        f"{referencia.isoformat()}. Cadastre o Ato TST GP do período em "
        "TETOS_DEPOSITO_RECURSAL ou informe uma data_referencia coberta."))

logger = logging.getLogger(__name__)

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

# ── Rotas DUPLICADAS mantidas por compatibilidade (Onda 3 §4.5) ──────────────
# Cada uma delega à implementação da rota canônica. Aqui elas passam a se
# ANUNCIAR como depreciadas: `deprecated=True` no decorator (visível no
# OpenAPI/Swagger) + cabeçalhos RFC 8594 (`Deprecation`/`Sunset`/`Link`) e
# campos na resposta. A remoção física é da Onda 5 e depende da telemetria de
# uso (services/route_usage.py) apontar 30-60 dias sem chamadas.
_SUNSET_DUPLICATAS = "Tue, 30 Jun 2026 23:59:59 GMT"
_DUPLICATAS_DEPRECIADAS: dict[str, str] = {
    "/penal/ferramentas/prescricao-punitiva": "/penal/ferramentas/prescricao-penal",
    "/admin-esp/ferramentas/recurso-multa-transito": "/transito/ferramentas/prazos-recurso",
    "/trabalhista/ferramentas/horas-extras": "/trabalhista-esp/ferramentas/horas-extras",
}


def _marcar_depreciada(rota: str, resposta: dict, response: Response) -> dict:
    """Carimba cabeçalhos RFC 8594 + campos de aviso na resposta da duplicata."""
    canonica = _DUPLICATAS_DEPRECIADAS[rota]
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = _SUNSET_DUPLICATAS
    response.headers["Link"] = f'<{canonica}>; rel="successor-version"'
    if isinstance(resposta, dict):
        resposta["deprecated"] = True
        resposta["rota_canonica"] = canonica
        resposta["sunset"] = _SUNSET_DUPLICATAS
        resposta["aviso_deprecacao"] = (
            f"Rota DEPRECIADA — migre para {canonica}. Esta rota continua respondendo "
            "com o mesmo resultado (implementação compartilhada) até a remoção prevista.")
    return resposta

# ── Metadados de regra por ferramenta (Onda 2 — Fase D) ──────────────────────
# Tabela ÚNICA e auditável: cada entrada carimba `fontes`, `vigencia_regra` e
# `versao_regra` na resposta da ferramenta, via decorator @_com_regra. Handlers
# que já montam esses campos no corpo continuam prevalecendo (setdefault).
_REGRAS_FERRAMENTAS: dict[str, dict] = {
    "transito_valor_multa": {
        "fontes": ["CTB (Lei 9.503/97) art. 258 e Anexo I (red. Lei 13.281/2016)",
                   "Regulamentação CONTRAN vigente (multiplicadores por infração)"],
        "vigencia_regra": "Valores-base do CTB art. 258 na redação da Lei 13.281/2016 (desde 01/11/2016)"},
    "adm_ms": {
        "fontes": ["Lei 12.016/2009 arts. 1º e 23", "CF art. 5º LXIX-LXX", "Súmula 632 STF"],
        "vigencia_regra": "Lei 12.016/2009 — vigente; decadência de 120 dias (art. 23)"},
    "ban_superendiv": {
        "fontes": ["CDC arts. 54-A a 54-G e 104-A a 104-C (incl. Lei 14.181/2021)",
                   "Decreto 11.150/2022 (regulamento do mínimo existencial), red. Dec. 11.567/2023"],
        "vigencia_regra": "Lei 14.181/2021 (desde 01/07/2021) · Dec. 11.150/2022 com a red. do Dec. 11.567/2023"},
    "ban_ba": {
        "fontes": ["Decreto-Lei 911/69 arts. 2º-3º (red. Leis 10.931/2004 e 13.043/2014)",
                   "STJ REsp 1.418.593 (repetitivo — purgação pelo total da dívida)",
                   "CPC art. 914 (embargos)"],
        "vigencia_regra": "DL 911/69 com a redação da Lei 13.043/2014 — vigente"},
    "civ_prescricao_consumidor": {
        "fontes": ["CDC arts. 26, 27 e 42 §ún.", "CC arts. 205 e 206 §3º",
                   "STJ EAREsp 738.991/RS (prazo decenal na repetição contratual)"],
        "vigencia_regra": "CDC arts. 26-27 · CC arts. 205-206 · tese do EAREsp 738.991/RS (2023)"},
    "civ_partilha_divorcio": {
        "fontes": ["CC arts. 1.639-1.688 (regimes de bens)", "Súmula 377 STF",
                   "STJ EREsp 1.623.858 (esforço comum na separação obrigatória)",
                   "STJ REsp 1.065.209 (separação de fato cessa o regime)"],
        "vigencia_regra": "CC/2002, Livro de Direito de Família — vigente"},
    "civ_rescisao_locacao": {
        "fontes": ["Lei 8.245/91 arts. 4º, 6º, 46-47, 51 e 56-57"],
        "vigencia_regra": "Lei 8.245/91 com a redação da Lei 12.112/2009 — vigente"},
    "trab_verbas_rescisorias": {
        "fontes": ["CLT arts. 477-487 (red. Lei 13.467/2017, inclui art. 484-A)",
                   "Lei 12.506/2011 (aviso prévio proporcional)",
                   "Lei 8.036/90 arts. 15 e 18 §§1º-2º (FGTS e multa rescisória)",
                   "Súmula 305 TST"],
        "vigencia_regra": "CLT com a red. da Lei 13.467/2017 · Lei 12.506/2011 · Lei 8.036/90 — vigentes"},
    "adm_reajuste_contrato": {
        "fontes": ["Lei 14.133/2021 arts. 25 §7º, 92 §3º, 124 II 'd' e 135",
                   "Lei 10.192/2001 art. 2º §1º (anualidade)"],
        "vigencia_regra": "Lei 14.133/2021 (vigente; Lei 8.666/93 revogada desde 30/12/2023) · Lei 10.192/2001"},
    "bancario_taxas_bacen": {
        "fontes": ["Banco Central do Brasil — séries SGS 432 (Selic meta), 12 (CDI), 226 (TR) e 7478 (IPCA-15)"],
        "vigencia_regra": "Últimos valores divulgados pelo BCB na consulta (dado vivo, não versionado)"},
    "trib_auto_infracao_prazos": {
        "fontes": ["Decreto 70.235/72 arts. 15, 33 e 37 §2º", "CTN art. 151 III",
                   "Lei 8.218/91 art. 6º (reduções da multa de ofício)"],
        "vigencia_regra": "Dec. 70.235/72 e Lei 8.218/91 — vigentes (processo administrativo fiscal federal)"},
    "trib_prescricao_decadencia": {
        "fontes": ["CTN arts. 150 §4º, 173 I e §ún., e 174",
                   "Súmula Vinculante 8 STF (inconstitucionais os arts. 45-46 da Lei 8.212/91)",
                   "STJ REsp 973.733 e REsp 1.340.553 (repetitivos)", "Lei 6.830/80 art. 40"],
        "vigencia_regra": "CTN — prazos de 5 anos; SV 8 STF (2008) afasta prazo decenal previdenciário"},
    "trib_regime_tributario": {
        "fontes": ["LC 123/2006 (Simples)", "Lei 9.249/95 arts. 15 e 20 (presunções)",
                   "Lei 9.430/96", "Leis 10.637/2002 e 10.833/2003 (PIS/COFINS não cumulativos)"],
        "vigencia_regra": "Legislação federal vigente em 2026-07 — estimativa sem ISS/ICMS e sem CPP"},
    "trib_reforma_tributaria": {
        "fontes": ["EC 132/2023", "LC 214/2025", "ADCT arts. 125-133 (cronograma de transição)"],
        "vigencia_regra": "EC 132/2023 · LC 214/2025 — regulamentação complementar em edição"},
    "amb_auto_infracao": {
        "fontes": ["Lei 9.605/98 arts. 14-15 e 70-76",
                   "Decreto 6.514/2008 arts. 4º, 21, 95-A, 113, 122, 127 e 139-148 (red. Dec. 9.179/2017)",
                   "Lei 9.873/99 art. 1º (prescrição quinquenal e intercorrente)"],
        "vigencia_regra": "Dec. 6.514/2008 com a red. do Dec. 9.179/2017 — vigente (esfera federal)"},
    "amb_crimes_ambientais": {
        "fontes": ["Lei 9.605/98 (arts. 3º-4º, 14, 21-23, 27-28, 29-56)",
                   "Lei 9.099/95 arts. 76 e 89", "CPP art. 28-A", "CF art. 225 §3º",
                   "STF RE 548.181 (dispensa da dupla imputação)"],
        "vigencia_regra": "Lei 9.605/98 — vigente; ANPP conforme CPP art. 28-A (Lei 13.964/2019)"},
    "amb_tac": {
        "fontes": ["Lei 7.347/85 art. 5º §6º", "Lei 9.605/98 arts. 27 e 79-A",
                   "Decreto 6.514/2008 arts. 139-148"],
        "vigencia_regra": "Lei 7.347/85 e Lei 9.605/98 — vigentes"},
    "amb_licenciamento": {
        "fontes": ["LC 140/2011 arts. 7º-10", "Res. CONAMA 237/97 arts. 8º, 14-15 e 18-19",
                   "Lei 6.938/81", "Norma do órgão licenciador estadual/municipal (conferência obrigatória)"],
        "vigencia_regra": "LC 140/2011 · CONAMA 237/97 — vigentes; prazos e classes conforme o ente"},
    "amb_reserva_legal": {
        "fontes": ["Lei 12.651/2012 arts. 12-13, 15, 17-18, 29, 59 e 66-67",
                   "Lei 11.428/2006 (Mata Atlântica)"],
        "vigencia_regra": "Código Florestal (Lei 12.651/2012) — vigente; percentuais como regra federal geral"},
    "previdenciario_tempo_contribuicao": {
        "fontes": ["EC 103/2019 arts. 15-20 (regras de transição)",
                   "Lei 8.213/91 arts. 52-56"],
        "vigencia_regra": "EC 103/2019, vigente desde 13/11/2019 — regra de pontos do art. 15"},
}


def _com_regra(chave: str):
    """Carimba `fontes`, `vigencia_regra` e `versao_regra` na resposta da
    ferramenta a partir de _REGRAS_FERRAMENTAS. Campos já definidos no corpo do
    handler PREVALECEM (setdefault) — o decorator só preenche o que falta."""
    meta = _REGRAS_FERRAMENTAS[chave]

    def deco(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            out = await fn(*args, **kwargs)
            if isinstance(out, dict):
                out.setdefault("fontes", meta["fontes"])
                out.setdefault("vigencia_regra", meta["vigencia_regra"])
                out.setdefault("versao_regra", _VERSAO_REGRA)
            return out
        return wrapper
    return deco


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
    venc, suspensao = _prazo_util_com_recesso(data_marco, 15, "cpc", em_dobro=em_dobro)
    return {
        "rito": rito,
        "marco": marco,
        "marco_descricao": _MARCOS_CONTESTACAO[marco],
        "data_marco": data_marco,
        "prazo": "30 dias úteis (15 em dobro — CPC art. 183)" if em_dobro else "15 dias úteis",
        "vencimento": venc,
        "suspensao_aplicada": suspensao,
        "base_legal": ("CPC art. 335 c/c arts. 219 e 183 (prazo em dobro da Fazenda Pública)"
                       if em_dobro else "CPC art. 335 c/c art. 219 (contagem em dias úteis)"),
        **comuns,
    }


@router.get("/civel/ferramentas/alimentos-calcular")
async def civ_alimentos(
    salario_devedor: float = Query(..., ge=0),
    percentual: float = Query(..., ge=0, le=100),
    filhos: int = Query(1, ge=1),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Estimativa aritmética de alimentos a partir do percentual INFORMADO.
    NÃO existe percentual legal ou jurisprudencial fixo (o "30%" é praxe forense,
    não regra): o valor é fixado pelo binômio necessidade × possibilidade (CC art.
    1.694 §1º), na proporção dos recursos do alimentante e das necessidades
    provadas do alimentando. MINUTA — revisão humana obrigatória.
    """
    if salario_devedor < 0:
        raise HTTPException(422, "salario_devedor não pode ser negativo.")
    if not 0 <= percentual <= 100:
        raise HTTPException(422, "percentual deve estar entre 0 e 100.")
    if filhos < 1:
        raise HTTPException(422, "filhos deve ser ≥ 1.")
    valor = round(salario_devedor * (percentual / 100), 2)
    sm = _sm_vigente()
    return {
        "salario_devedor": salario_devedor,
        "percentual_informado": percentual,
        "filhos": filhos,
        "valor_mensal": valor,
        "em_sm": round(valor / sm, 2) if sm else None,
        "memoria_calculo": f"valor = R$ {salario_devedor:.2f} × {percentual}%",
        "sem_percentual_sugerido": True,
        "binomio_necessidade_possibilidade": [
            "NECESSIDADE: despesas comprovadas do alimentando (educação, saúde, moradia, alimentação, lazer)",
            "POSSIBILIDADE: renda e patrimônio do alimentante, encargos e demais dependentes",
            "PROPORCIONALIDADE: o juiz arbitra o quantum a partir da prova (CC art. 1.694 §1º)",
        ],
        "referencia": ("Percentual informado pelo USUÁRIO. Não há tabela, percentual legal nem "
                       "padrão vinculante do STJ; a praxe de 30% é referencial de mercado, não "
                       "regra. A Súmula 277/STJ trata apenas do termo inicial na investigação "
                       "de paternidade e não fundamenta percentual."),
        "fontes": [
            "CC arts. 1.694 §1º, 1.695 e 1.699",
            "Lei 5.478/68 (Lei de Alimentos)",
            "Súmula 277 STJ (termo inicial — não fixa percentual)",
        ],
        "vigencia_regra": "CC/2002 arts. 1.694-1.710 · Lei 5.478/68 — vigentes",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA de estimativa aritmética. Validar necessidades, recursos e "
                  "circunstâncias do caso; o magistrado fixa o valor a partir da prova."),
    }


@router.get("/civel/ferramentas/usucapiao-verificar")
async def civ_usucapiao(
    tipo: Literal["ordinaria", "extraordinaria", "especial_urbana",
                  "especial_rural", "familiar"],
    anos_posse: float = Query(..., ge=0),
    posse_mansa: bool = True,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Requisitos de usucapião por modalidade (CC arts. 1.238-1.244 · CF arts. 183 e 191).
    Prazos REDUZIDOS têm requisitos próprios e são informados à parte — a ferramenta
    devolve o prazo da regra geral de cada modalidade. MINUTA.
    """
    modalidades = {
        "extraordinaria": {
            "anos": 15, "justo_titulo": False, "boa_fe": False,
            "prazo_reduzido": "10 anos se o possuidor houver estabelecido moradia habitual ou "
                              "realizado obras/serviços de caráter produtivo (CC art. 1.238 §ún.)",
            "base": "CC art. 1.238 caput"},
        "ordinaria": {
            "anos": 10, "justo_titulo": True, "boa_fe": True,
            "prazo_reduzido": "5 anos se o imóvel foi adquirido onerosamente com registro depois "
                              "cancelado, havendo moradia ou investimentos de interesse social e "
                              "econômico (CC art. 1.242 §ún.)",
            "base": "CC art. 1.242 caput"},
        "especial_urbana": {
            "anos": 5, "area_max_m2": 250, "justo_titulo": False, "boa_fe": False,
            "requisitos_proprios": "moradia própria/da família e não ser proprietário de outro imóvel",
            "base": "CF art. 183 · CC art. 1.240 · Lei 10.257/2001 art. 9º"},
        "especial_rural": {
            "anos": 5, "area_max_ha": 50, "justo_titulo": False, "boa_fe": False,
            "requisitos_proprios": "posse produtiva pelo trabalho próprio/da família, moradia e "
                                   "não ser proprietário de outro imóvel",
            "base": "CF art. 191 · CC art. 1.239"},
        "familiar": {
            "anos": 2, "area_max_m2": 250, "abandono_lar": True,
            "requisitos_proprios": "ex-cônjuge/companheiro que permaneceu no imóvel após o "
                                   "abandono do lar pelo outro, sem ser proprietário de outro imóvel",
            "base": "CC art. 1.240-A (incl. Lei 12.424/2011)"},
    }
    if tipo not in modalidades:
        raise HTTPException(422, f"Modalidade inválida. Use: {list(modalidades)}")
    if anos_posse < 0:
        raise HTTPException(422, "anos_posse não pode ser negativo.")
    m = modalidades[tipo]
    prazo_min = m["anos"]
    preenche_prazo = anos_posse >= prazo_min
    return {
        "modalidade": tipo,
        "prazo_minimo_anos": prazo_min,
        "anos_posse_declarados": anos_posse,
        "posse_mansa": posse_mansa,
        "preenche_prazo": preenche_prazo,
        "requisitos": m,
        "viavel_preliminarmente": preenche_prazo and posse_mansa,
        "requisitos_comuns": [
            "posse mansa, pacífica e ININTERRUPTA, com ANIMUS DOMINI",
            "possibilidade de soma das posses (accessio possessionis — CC art. 1.243)",
            "bem PÚBLICO não é usucapível (CF art. 183 §3º e art. 191 §ún.; Súm. 340 STF)",
        ],
        "fontes": [
            "CC arts. 1.238-1.244 (incl. 1.240-A, Lei 12.424/2011)",
            "CF arts. 183 e 191 · Lei 10.257/2001 art. 9º",
            "Súmula 340 STF (bens públicos)",
        ],
        "vigencia_regra": "CC/2002 arts. 1.238-1.244 · art. 1.240-A vigente desde 16/06/2011",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Verificar cadeia dominial, "
                  "confrontações, registro e a via adequada (judicial ou extrajudicial, "
                  "CPC art. 216-A da LRP)."),
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
    # Dias corridos (CPP art. 798) COM a suspensão do art. 798-A (Lei 14.365/2022):
    # a contagem não corre entre 20/12 e 20/01, deslocando o vencimento.
    venc_resposta, suspensao = _prazo_corrido_com_recesso(data_citacao, 10, "cpp")
    return {
        "data_citacao": data_citacao,
        "contagem": ("Dias CORRIDOS (CPP art. 798 caput e §1º): exclui-se o dia do começo e "
                     "inclui-se o do vencimento; vencimento em domingo ou feriado prorroga "
                     "para o dia útil seguinte (§3º). Contagem SUSPENSA de 20/12 a 20/01 "
                     "(art. 798-A, Lei 14.365/2022)."),
        "prazos": [
            {"evento": "Resposta à acusação",
             "data": venc_resposta,
             "suspensao_aplicada": suspensao,
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
                                "processuais penais fica SUSPENSA de 20/12 a 20/01 — efeito já "
                                "APLICADO ao prazo calculado (ver suspensao_aplicada)."),
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


@router.get("/penal/ferramentas/prescricao-punitiva", deprecated=True)
async def pen_prescricao(
    response: Response,
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
    return _marcar_depreciada("/penal/ferramentas/prescricao-punitiva", _prescricao_penal_consolidada(
        rota_consultada="/penal/ferramentas/prescricao-punitiva",
        data_fato=data_fato, pena_maxima_anos=pena_maxima_anos,
        pena_concreta_anos=pena_concreta_anos, marcos_interruptivos=marcos_interruptivos,
        menor_21_na_data_fato=menor_21_na_data_fato, maior_70_na_sentenca=maior_70_na_sentenca,
    ), response)


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
_PRAZOS_TRABALHISTAS = {
    "recurso_ordinario":   (8, "Recurso Ordinário (RO)", "CLT art. 895 I — 8 dias ÚTEIS"),
    "embargos_declaracao": (5, "Embargos de declaração", "CLT art. 897-A — 5 dias ÚTEIS"),
    "recurso_de_revista":  (8, "Recurso de Revista (RR)", "CLT art. 896 — 8 dias ÚTEIS"),
}


@router.get("/trabalhista-esp/ferramentas/prazos")
async def trab_prazos(
    data_ciencia: date,
    tipo_prazo: Literal["recurso_ordinario", "embargos_declaracao",
                        "recurso_de_revista", "todos"] = "todos",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazos recursais trabalhistas a partir da CIÊNCIA da decisão — TODOS em dias
    ÚTEIS (CLT art. 775, red. Lei 13.467/2017). O depósito recursal e as custas
    são comprovados dentro do próprio prazo do recurso (CLT art. 899 §1º; Súm. 245
    TST) — não há prazo autônomo. MINUTA — revisão humana obrigatória.
    """
    if tipo_prazo != "todos" and tipo_prazo not in _PRAZOS_TRABALHISTAS:
        raise HTTPException(422, f"Tipo de prazo inválido: '{tipo_prazo}'. "
                                 f"Use: {list(_PRAZOS_TRABALHISTAS) + ['todos']}")
    selecionados = (_PRAZOS_TRABALHISTAS if tipo_prazo == "todos"
                    else {tipo_prazo: _PRAZOS_TRABALHISTAS[tipo_prazo]})
    prazos = []
    for chave, (dias, rotulo, base) in selecionados.items():
        venc, suspensao = _prazo_util_com_recesso(data_ciencia, dias, "clt")
        prazos.append({"tipo": chave, "evento": rotulo, "data": venc,
                       "base": base, "tipo_contagem": "úteis",
                       "suspensao_aplicada": suspensao})
    return {
        "data_ciencia": data_ciencia,
        "contagem": ("Dias ÚTEIS (CLT art. 775, red. Lei 13.467/2017), excluído o dia do começo, "
                     "com suspensão de 20/12 a 20/01 (CLT art. 775-A)."),
        "prazos": prazos,
        "nota_deposito_recursal": ("Depósito recursal e custas: comprovação DENTRO do prazo do "
                                   "recurso a que se referem (CLT art. 899 §1º; Súm. 245 TST) — "
                                   "o recolhimento acompanha o prazo recursal."),
        "fontes": [
            "CLT art. 775 (red. Lei 13.467/2017 — contagem em dias úteis)",
            "CLT arts. 895 I, 896, 897-A e 899 §1º",
            "Súmula 245 TST",
        ],
        "vigencia_regra": "CLT art. 775 com a redação da Lei 13.467/2017, vigente desde 11/11/2017",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Marco: ciência da decisão (publicação/"
                  "intimação); verificar feriados locais e suspensões (CLT art. 775-A) no juízo."),
    }


@router.get("/trabalhista-esp/ferramentas/prescricao-trabalhista")
async def trab_prescricao(
    data_extincao_contrato: date,
    data_ajuizamento: Optional[date] = None,   # data (real ou prevista) do ajuizamento; default hoje
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prescrição trabalhista — CF art. 7º XXIX c/c CLT art. 11 e Súm. 308 TST.
    • BIENAL: a ação deve ser ajuizada até 2 anos após a extinção do contrato.
    • QUINQUENAL RETROATIVA: são exigíveis as parcelas dos 5 anos ANTERIORES ao
      AJUIZAMENTO (Súm. 308 TST) — a contagem NUNCA é projetada para frente.
    MINUTA — revisão humana obrigatória.
    """
    ajuizamento = data_ajuizamento or date.today()
    limite_bienal = _add_anos_data(data_extincao_contrato, 2)
    limite_retroativo = _add_anos_data(ajuizamento, -5)
    dentro_bienal = ajuizamento <= limite_bienal
    return {
        "data_extincao_contrato": data_extincao_contrato,
        "data_ajuizamento": ajuizamento,
        "data_ajuizamento_presumida_hoje": data_ajuizamento is None,
        "prescricao_bienal": {
            "limite_para_ajuizar": limite_bienal,
            "acao_dentro_da_bienal": dentro_bienal,
            "base": "CF art. 7º XXIX c/c CLT art. 11 — 2 anos da extinção do contrato",
        },
        "prescricao_quinquenal": {
            "limite_retroativo": limite_retroativo,
            "descricao": (f"Ajuizando em {ajuizamento.isoformat()}, são exigíveis as parcelas "
                          f"vencidas a partir de {limite_retroativo.isoformat()} (5 anos "
                          "RETROATIVOS do ajuizamento — Súm. 308 TST). Parcelas anteriores "
                          "estão prescritas."),
            "base": "CF art. 7º XXIX c/c CLT art. 11 · Súm. 308 I TST (contagem retroativa)",
        },
        "sintese": ("Ação dentro da bienal — parcelas exigíveis desde o limite retroativo."
                    if dentro_bienal else
                    "PRESCRIÇÃO BIENAL CONSUMADA: ajuizamento posterior a 2 anos da extinção "
                    "do contrato fulmina a pretensão (ressalvadas hipóteses de suspensão/"
                    "interrupção e parcelas de FGTS com regime próprio — STF ARE 709.212)."),
        "fontes": [
            "CF art. 7º XXIX",
            "CLT art. 11 (red. Lei 13.467/2017)",
            "Súmula 308 TST (quinquenal retroativa do ajuizamento)",
            "STF ARE 709.212 (prescrição do FGTS — regime próprio)",
        ],
        "vigencia_regra": "CF/88 art. 7º XXIX · CLT art. 11 red. Lei 13.467/2017 · Súm. 308 TST",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Verificar causas suspensivas/"
                  "interruptivas (protesto, ação anterior arquivada — Súm. 268 TST) e a data "
                  "exata da extinção (projeção do aviso prévio, OJ 83 SDI-1)."),
    }


@router.get("/trabalhista-esp/ferramentas/deposito-recursal")
async def trab_deposito(
    valor_condenacao: float,
    data_referencia: Optional[date] = None,   # data do recurso; default hoje
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Calcula depósito recursal para Recurso Ordinário e Recurso de Revista.
    Metodologia (CLT art. 899 §1º): o depósito recursal corresponde ao VALOR DA
    CONDENAÇÃO, limitado ao teto legal do recurso — NÃO a um percentual dela.
    Tetos lidos da tabela VERSIONADA (TETOS_DEPOSITO_RECURSAL) pela data de
    referência; sem tabela para o período → 422.
    MINUTA — confirmar teto vigente na data do recurso.
    """
    if valor_condenacao < 0:
        raise HTTPException(422, "valor_condenacao não pode ser negativo.")
    ref = data_referencia or date.today()
    faixa = _teto_deposito_para(ref)
    # Depósito = condenação limitada ao teto do recurso (art. 899 §1º).
    # Entre 1x e 2x o teto, recolher só metade tornaria o recurso DESERTO.
    dep_ro = min(valor_condenacao, faixa["ro"])
    dep_rr = min(valor_condenacao, faixa["rr"])
    return {
        "valor_condenacao": valor_condenacao,
        "data_referencia": ref,
        "deposito_ro": round(dep_ro, 2),
        "deposito_rr": round(dep_rr, 2),
        "teto_ro": faixa["ro"],
        "teto_rr": faixa["rr"],
        "vigencia_tabela": (f"{faixa['inicio'].isoformat()} a "
                            f"{faixa['fim'].isoformat() if faixa['fim'] else 'vigente'}"),
        "fonte": faixa["fonte"],
        "metodologia": "Recolhimento = valor da condenação, limitado ao teto do recurso (CLT art. 899 §1º). Não é percentual da condenação.",
        "fontes": [
            "CLT art. 899 §§1º-4º",
            faixa["fonte"],
        ],
        "vigencia_regra": f"Tetos do período {faixa['rotulo']} — {faixa['fonte']}",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Confirmar o Ato TST GP vigente na data "
                  "do recurso; entidades sem fins lucrativos, MEI/EPP e empresas em recuperação "
                  "judicial recolhem METADE (CLT art. 899 §9º) ou são isentas (§10)."),
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

# ── Trânsito: prazos de defesa/recurso (fonte ÚNICA — CTB red. Lei 14.071/2020)
_FASES_RECURSO_TRANSITO = {
    "defesa_previa": {
        "campo": "data_notificacao_autuacao",
        "marco": "notificação da AUTUAÇÃO",
        "prazo_desc": "prazo MÍNIMO de 30 dias",
        "base": "CTB art. 281-A (red. Lei 14.071/2020)",
    },
    "jari": {
        "campo": "data_notificacao_penalidade",
        "marco": "notificação da PENALIDADE",
        "prazo_desc": "30 dias",
        "base": "CTB art. 285",
    },
    "cetran": {
        "campo": "data_ciencia_decisao_jari",
        "marco": "ciência da decisão da JARI",
        "prazo_desc": "30 dias",
        "base": "CTB art. 288",
    },
}


def _prazos_recurso_transito(
    rota_consultada: str,
    fase: str,
    data_notificacao_autuacao: Optional[date],
    data_notificacao_penalidade: Optional[date],
    data_ciencia_decisao_jari: Optional[date],
    valor_multa: Optional[float],
) -> dict:
    """Implementação ÚNICA de /transito/ferramentas/prazos-recurso (canônica) e
    /admin-esp/ferramentas/recurso-multa-transito (alias até a Onda 3).
    Cada fase tem marco PRÓPRIO — nunca se encadeia um prazo ao fim do anterior."""
    if fase not in _FASES_RECURSO_TRANSITO:
        raise HTTPException(422, f"Fase inválida: '{fase}'. Use: {list(_FASES_RECURSO_TRANSITO)}")
    datas = {
        "data_notificacao_autuacao": data_notificacao_autuacao,
        "data_notificacao_penalidade": data_notificacao_penalidade,
        "data_ciencia_decisao_jari": data_ciencia_decisao_jari,
    }
    cfg = _FASES_RECURSO_TRANSITO[fase]
    data_marco = datas[cfg["campo"]]
    if data_marco is None:
        raise HTTPException(422, (
            f"A fase '{fase}' conta da {cfg['marco']} ({cfg['base']}): informe {cfg['campo']}."))
    incompativeis = [nome for nome, valor in datas.items()
                     if valor is not None and nome != cfg["campo"]]
    if incompativeis:
        raise HTTPException(422, (
            f"Data(s) incompatível(is) com a fase '{fase}': {', '.join(incompativeis)}. "
            f"Esta fase usa apenas {cfg['campo']} ({cfg['marco']} — {cfg['base']})."))
    vencimento = prazo_dias_corridos(data_marco, 30)
    dias_restantes = (vencimento - date.today()).days
    vencido = dias_restantes < 0
    out: dict = {
        "rota_consultada": rota_consultada,
        "rota_canonica": "/transito/ferramentas/prazos-recurso",
        "fase": fase,
        "marco": cfg["marco"],
        "data_marco": data_marco,
        "prazo": f"{cfg['prazo_desc']} — {cfg['base']}",
        "vencimento": vencimento,
        "dias_restantes": dias_restantes,
        "vencido": vencido,
        "dias_desde_o_vencimento": abs(dias_restantes) if vencido else 0,
        # "urgente" só faz sentido para prazo em curso; prazo vencido é `vencido`.
        "urgente": (not vencido) and dias_restantes <= 5,
        "nota_marco": ("Cada fase tem marco INDEPENDENTE (autuação → defesa prévia; penalidade → "
                       "JARI; decisão da JARI → CETRAN); os prazos NÃO se encadeiam entre si. "
                       "Prevalece a data-limite impressa na própria notificação, se maior "
                       "(o art. 281-A fixa MÍNIMO de 30 dias para a defesa prévia)."),
        "fontes": [
            "CTB (Lei 9.503/97) arts. 281-A, 285 e 288, red. Lei 14.071/2020",
            "Regulamentação CONTRAN vigente (notificações e julgamento)",
        ],
        "vigencia_regra": "CTB com a redação da Lei 14.071/2020, vigente desde 12/04/2021",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Confira o prazo e o meio de notificação "
                  "indicados no próprio documento do órgão autuador."),
    }
    if valor_multa is not None:
        if valor_multa < 0:
            raise HTTPException(422, "valor_multa não pode ser negativo.")
        out["descontos"] = {
            "valor_multa": valor_multa,
            "desconto_40pct_sne": round(valor_multa * 0.60, 2),
            "desconto_20pct_ate_vencimento": round(valor_multa * 0.80, 2),
            "base": "CTB art. 284 §1º (20%) · art. 284 §4º c/c SNE (40%, red. Lei 14.071/2020)",
            "nota": "Pagamento com desconto de 40% pelo SNE implica renúncia a defesa/recurso.",
        }
    return out


# ── Ferramentas Administrativo ────────────────────────────────────────────────
@router.get("/admin-esp/ferramentas/recurso-multa-transito", deprecated=True)
async def adm_multa_transito(
    response: Response,
    fase: Literal["defesa_previa", "jari", "cetran"],
    data_notificacao_autuacao: Optional[date] = None,
    data_notificacao_penalidade: Optional[date] = None,
    data_ciencia_decisao_jari: Optional[date] = None,
    valor_multa: Optional[float] = None,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Alias mantido por compatibilidade — delega à implementação ÚNICA de
    /transito/ferramentas/prazos-recurso (rota canônica; retirada na Onda 3)."""
    return _marcar_depreciada("/admin-esp/ferramentas/recurso-multa-transito", _prazos_recurso_transito(
        rota_consultada="/admin-esp/ferramentas/recurso-multa-transito",
        fase=fase, data_notificacao_autuacao=data_notificacao_autuacao,
        data_notificacao_penalidade=data_notificacao_penalidade,
        data_ciencia_decisao_jari=data_ciencia_decisao_jari, valor_multa=valor_multa,
    ), response)


# ── Ferramentas Trânsito (ramo próprio) ───────────────────────────────────────
@router.get("/transito/ferramentas/prazos-recurso")
async def transito_prazos_recurso(
    fase: Literal["defesa_previa", "jari", "cetran"],
    data_notificacao_autuacao: Optional[date] = None,
    data_notificacao_penalidade: Optional[date] = None,
    data_ciencia_decisao_jari: Optional[date] = None,
    valor_multa: Optional[float] = None,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazos de defesa/recurso de multa de trânsito (CTB red. Lei 14.071/2020).
    • Defesa prévia: MÍNIMO 30 dias da notificação da AUTUAÇÃO (art. 281-A);
    • JARI: 30 dias da notificação da PENALIDADE (art. 285);
    • CETRAN/2ª instância: 30 dias da CIÊNCIA da decisão da JARI (art. 288).
    Informe a data do marco DA FASE escolhida — data de outra fase → 422.
    """
    return _prazos_recurso_transito(
        rota_consultada="/transito/ferramentas/prazos-recurso",
        fase=fase, data_notificacao_autuacao=data_notificacao_autuacao,
        data_notificacao_penalidade=data_notificacao_penalidade,
        data_ciencia_decisao_jari=data_ciencia_decisao_jari, valor_multa=valor_multa,
    )


@router.get("/transito/ferramentas/pontuacao-cnh")
async def transito_pontuacao_cnh(
    pontos_total: int,
    qtd_gravissimas: int = Query(..., ge=0, description="Infrações gravíssimas no período de 12 meses"),
    exerce_atividade_remunerada: str = Query(..., description="sim | nao (EAR na CNH)"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Sistema 20/30/40 de pontos da CNH — CTB art. 261 (red. Lei 14.071/2020):
    40 pontos sem infração gravíssima; 30 com UMA gravíssima; 20 com DUAS ou mais.
    Condutor que exerce atividade remunerada (EAR): limite ÚNICO de 40 pontos,
    independentemente da gravidade, com opção de curso preventivo de reciclagem
    ao atingir 30 pontos (nota informativa — não altera o limite).
    """
    if pontos_total < 0 or qtd_gravissimas < 0:
        raise HTTPException(422, "pontos_total e qtd_gravissimas devem ser ≥ 0.")
    ear = _parse_sim_nao(exerce_atividade_remunerada, "exerce_atividade_remunerada")
    if ear:
        limite = 40
        regra = ("Condutor com EAR: limite ÚNICO de 40 pontos, independentemente da "
                 "natureza das infrações (CTB art. 261 §ú, red. Lei 14.071/2020).")
    elif qtd_gravissimas >= 2:
        limite = 20
        regra = "Duas ou mais infrações gravíssimas em 12 meses: limite de 20 pontos."
    elif qtd_gravissimas == 1:
        limite = 30
        regra = "Uma infração gravíssima em 12 meses: limite de 30 pontos."
    else:
        limite = 40
        regra = "Nenhuma infração gravíssima em 12 meses: limite de 40 pontos."
    atingiu = pontos_total >= limite
    out: dict = {
        "pontos_total": pontos_total,
        "qtd_gravissimas": qtd_gravissimas,
        "exerce_atividade_remunerada": ear,
        "limite_aplicavel": limite,
        "regra_aplicada": regra,
        "atingiu_limite": atingiu,
        "margem_pontos": max(limite - pontos_total, 0),
        "situacao": ("Limite ATINGIDO — instauração de processo de suspensão do direito de "
                     "dirigir (CTB art. 261)." if atingiu else "Dentro do limite — monitorar."),
        "fontes": [
            "CTB (Lei 9.503/97) art. 261, red. Lei 14.071/2020 — sistema 20/30/40",
            "Regulamentação CONTRAN vigente (curso preventivo de reciclagem)",
        ],
        "vigencia_regra": "CTB art. 261 com a redação da Lei 14.071/2020, vigente desde 12/04/2021",
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA — revisão humana obrigatória. Conferir o prontuário no DETRAN.",
    }
    if ear:
        out["nota_curso_preventivo_ear"] = (
            "Ao atingir 30 pontos, o condutor com EAR pode OPTAR pelo curso preventivo de "
            "reciclagem (CTB art. 261, red. Lei 14.071/2020, c/c regulamentação CONTRAN "
            "vigente); concluído o curso, os pontos são zerados no prontuário. É opção "
            "informativa — o limite de suspensão permanece 40 pontos.")
    return out


# ── Helper: soma de anos a uma data (trata 29/02) ─────────────────────────────
def _add_anos_data(d: date, anos: int) -> date:
    """Soma anos preservando dia/mês; 29/02 em ano não bissexto → 28/02."""
    try:
        return d.replace(year=d.year + anos)
    except ValueError:
        return d.replace(month=2, day=28, year=d.year + anos)


# ── Suspensão legal da contagem (recesso/férias forenses) ────────────────────
# CPC art. 220 (20/12 a 20/01), CLT art. 775-A e CPP art. 798-A (Lei 14.365/2022)
# suspendem o curso dos prazos PROCESSUAIS. deadline_calculator.prazo_dias_uteis
# implementa o efeito via aplicar_recesso=True.
_SUSPENSAO_LEGAL = {
    "cpc": "CPC art. 220 — suspensão do curso dos prazos processuais de 20/12 a 20/01",
    "clt": "CLT art. 775-A (red. Lei 13.467/2017) — suspensão de 20/12 a 20/01",
    "cpp": "CPP art. 798-A (incl. Lei 14.365/2022) — suspensão de 20/12 a 20/01",
}


def _atravessa_recesso(inicio: date, fim: date) -> bool:
    """True se o intervalo [inicio, fim] toca a janela de recesso de algum ano."""
    for ano in range(inicio.year, fim.year + 1):
        if inicio <= date(ano, 12, 20) <= fim or inicio <= date(ano, 1, 20) <= fim:
            return True
    return False


def _info_suspensao(regime: str, inicio: date, fim_sem_recesso: date, fim_com_recesso: date) -> dict:
    """Bloco auditável sobre a suspensão aplicada ao prazo."""
    aplicada = fim_com_recesso != fim_sem_recesso
    return {
        "aplicada": aplicada,
        "base": _SUSPENSAO_LEGAL[regime],
        "janela": "20/12 a 20/01",
        "vencimento_sem_suspensao": fim_sem_recesso,
        "dias_prorrogados": (fim_com_recesso - fim_sem_recesso).days,
        "observacao": ("Prazo atravessa o recesso — contagem suspensa no período."
                       if aplicada else
                       "Prazo não atravessa o recesso — contagem sem suspensão."),
    }


def _prazo_util_com_recesso(inicio: date, dias: int, regime: str,
                            em_dobro: bool = False) -> tuple[date, dict]:
    """Prazo em dias úteis COM a suspensão legal do regime, mais o bloco auditável."""
    sem = prazo_dias_uteis(inicio, dias, em_dobro=em_dobro, aplicar_recesso=False)
    com = prazo_dias_uteis(inicio, dias, em_dobro=em_dobro, aplicar_recesso=True)
    return com, _info_suspensao(regime, inicio, sem, com)


def _prazo_corrido_com_recesso(inicio: date, dias: int, regime: str) -> tuple[date, dict]:
    """Prazo em dias CORRIDOS com suspensão legal (CPP art. 798-A): a contagem
    corrida NÃO corre entre 20/12 e 20/01, deslocando o vencimento."""
    sem = prazo_dias_corridos(inicio, dias)
    atual, contados = inicio, 0
    while contados < dias:
        atual += timedelta(days=1)
        # Dentro da janela de recesso a contagem fica suspensa (dia não conta).
        em_recesso = (atual.month == 12 and atual.day >= 20) or \
                     (atual.month == 1 and atual.day <= 20)
        if not em_recesso:
            contados += 1
    com = proximo_dia_util(atual, forense=False)
    return com, _info_suspensao(regime, inicio, sem, com)


def _ultimo_dia_do_mes(ano: int, mes: int) -> int:
    """Último dia do mês (trata fevereiro bissexto)."""
    return monthrange(ano, mes)[1]


def _add_meses_data(d: date, meses: int) -> date:
    """Soma (ou subtrai) meses preservando o DIA: 31/07 − 3 meses = 30/04, e não
    28/04. Quando o dia não existe no mês de destino, usa o ÚLTIMO dia do mês.
    Regressão coberta em test_areas_atuacao_onda2 (rito de alimentos e art. 115)."""
    if meses % 12 == 0:
        return _add_anos_data(d, meses // 12)
    total = d.month - 1 + meses
    ano, mes = d.year + total // 12, total % 12 + 1
    return date(ano, mes, min(d.day, _ultimo_dia_do_mes(ano, mes)))


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
    data_consumacao: Optional[date] = None
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
            intervalo_prescrito, data_consumacao = i + 1, limite
    # A data estimada deve refletir o intervalo em que a prescrição SE CONSUMOU;
    # projetar do último marco exibiria data futura junto de prescrito=True.
    data_estimada = data_consumacao or _add_meses_data(marcos[-1], prazo_meses)

    return _selo_homologacao(rota_consultada, {
        "rota_consultada": rota_consultada,
        "rota_canonica": "/penal/ferramentas/prescricao-penal",
        "base_de_calculo": "pena_concreta (CP art. 110 — retroativa/intercorrente)"
                           if usa_concreta else "pena_maxima_abstrata (CP art. 109)",
        "pena_considerada_anos": pena_base,
        "prazo_prescricional_base_anos": prazo_anos,       # tabela do art. 109, antes do art. 115
        "prazo_prescricional_anos": prazo_meses / 12 if prazo_meses % 12 else prazo_meses // 12,
        "prazo_prescricional_meses": prazo_meses,
        "reducao_metade_art_115": reduzido,
        "memoria_prazo": (f"art. 109: {prazo_anos} anos"
                          + (f" ÷ 2 (art. 115) = {prazo_meses} meses" if reduzido
                             else f" = {prazo_meses} meses")),
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
    valor_cobrado_indevidamente: float = Query(..., gt=0),
    houve_pagamento: str = Query(..., description="sim | nao — a repetição pressupõe PAGAMENTO"),
    cobranca_contraria_boa_fe_objetiva: str = Query(..., description="sim | nao"),
    engano_justificavel: str = Query(..., description="sim | nao"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Repetição em dobro do indébito — CDC art. 42 §ún. c/c STJ EAREsp 676.608/RS:
    o dobro NÃO exige má-fé; basta a cobrança indevida contrária à boa-fé OBJETIVA,
    salvo engano justificável (restituição simples). Sem pagamento não há repetição
    (apenas discussão da cobrança/dano). MINUTA — revisão humana obrigatória.
    """
    if valor_cobrado_indevidamente <= 0:
        raise HTTPException(422, "valor_cobrado_indevidamente deve ser maior que zero.")
    pagou = _parse_sim_nao(houve_pagamento, "houve_pagamento")
    contraria = _parse_sim_nao(cobranca_contraria_boa_fe_objetiva, "cobranca_contraria_boa_fe_objetiva")
    engano = _parse_sim_nao(engano_justificavel, "engano_justificavel")
    analise = [
        {"requisito": "Pagamento do valor cobrado (a repetição pressupõe quantia PAGA em excesso)",
         "base": "CDC art. 42 §ún. — 'cobrado em quantia indevida ... o que pagou em excesso'",
         "atendido": pagou},
        {"requisito": "Cobrança contrária à boa-fé OBJETIVA (não se exige má-fé subjetiva)",
         "base": "STJ EAREsp 676.608/RS (Corte Especial)",
         "atendido": contraria},
        {"requisito": "Ausência de engano justificável",
         "base": "CDC art. 42 §ún., parte final",
         "atendido": not engano},
    ]
    if not pagou:
        resultado, restituicao = "sem_repeticao", 0.0
        conclusao = ("Sem pagamento não há repetição de indébito (simples ou em dobro): "
                     "cabe discutir a cobrança indevida e eventuais danos (CDC arts. 6º VI e 71).")
    elif contraria and not engano:
        resultado, restituicao = "dobro", round(valor_cobrado_indevidamente * 2, 2)
        conclusao = ("Restituição em DOBRO do que foi pago em excesso (+ correção monetária e "
                     "juros): cobrança contrária à boa-fé objetiva sem engano justificável — "
                     "independe de má-fé (EAREsp 676.608/RS).")
    else:
        resultado, restituicao = "simples", round(valor_cobrado_indevidamente, 2)
        conclusao = ("Restituição SIMPLES: o engano justificável (ou a ausência de contrariedade "
                     "à boa-fé objetiva) afasta o dobro (CDC art. 42 §ún., parte final).")
    return {
        "valor_cobrado_indevidamente": valor_cobrado_indevidamente,
        "analise_requisitos": analise,
        "resultado": resultado,
        "restituicao_estimada": restituicao,
        "conclusao": conclusao,
        "nota_modulacao_temporal": ("EAREsp 676.608/RS (modulação): a dispensa de má-fé vale para "
                                    "cobranças POSTERIORES a 30/03/2021; para pagamentos "
                                    "anteriores, a jurisprudência então vigente exigia má-fé."),
        "fontes": [
            "CDC (Lei 8.078/90) art. 42 §ún.",
            "STJ EAREsp 676.608/RS (Corte Especial, j. 21/10/2020 — modulação 30/03/2021)",
        ],
        "vigencia_regra": "CDC art. 42 §ún. · tese do EAREsp 676.608/RS para cobranças após 30/03/2021",
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA — revisão humana obrigatória. Valores sem correção monetária e juros.",
    }


_PRETENSOES_CDC = {
    "vicio_aparente_nao_duravel": {
        "instituto": "decadência", "dias": 30, "anos": None,
        "termo_inicial": "entrega efetiva do produto ou término da execução do serviço",
        "base": "CDC art. 26 I e §1º",
    },
    "vicio_aparente_duravel": {
        "instituto": "decadência", "dias": 90, "anos": None,
        "termo_inicial": "entrega efetiva do produto ou término da execução do serviço",
        "base": "CDC art. 26 II e §1º",
    },
    "vicio_oculto": {
        "instituto": "decadência", "dias": None, "anos": None,   # 30/90 conforme durabilidade
        "termo_inicial": "momento em que o defeito ficar EVIDENCIADO (aparecimento do vício)",
        "base": "CDC art. 26 §3º",
    },
    "acidente_de_consumo": {
        "instituto": "prescrição", "dias": None, "anos": 5,
        "termo_inicial": "conhecimento do DANO e de sua AUTORIA (fato do produto/serviço)",
        "base": "CDC art. 27",
    },
    "repeticao_indebito_contratual": {
        "instituto": "prescrição", "dias": None, "anos": 10,
        "termo_inicial": "pagamento indevido (cada parcela paga)",
        "base": "CC art. 205 — prazo DECENAL (STJ EAREsp 738.991/RS, Corte Especial)",
    },
}


@router.get("/consumidor/ferramentas/prazos-cdc")
async def consumidor_prazos_cdc(
    pretensao: Literal["vicio_aparente_nao_duravel", "vicio_aparente_duravel",
                       "vicio_oculto", "acidente_de_consumo",
                       "repeticao_indebito_contratual"],
    data_marco: date = Query(..., description="Data do TERMO INICIAL correto da pretensão"),
    bem_duravel: Optional[str] = None,   # sim|nao — obrigatório para vicio_oculto (30 ou 90 dias)
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Decadência/prescrição do consumidor — a PRETENSÃO define instituto, prazo e
    termo inicial: vício aparente 30/90 dias da entrega (CDC art. 26 I-II e §1º);
    vício oculto conta do APARECIMENTO do defeito (art. 26 §3º); acidente de
    consumo 5 anos do conhecimento do dano e da autoria (art. 27); repetição de
    indébito contratual: prescrição DECENAL (CC art. 205 — EAREsp 738.991/RS).
    MINUTA — revisão humana obrigatória.
    """
    if pretensao not in _PRETENSOES_CDC:
        raise HTTPException(422, f"Pretensão inválida: '{pretensao}'. Use: {list(_PRETENSOES_CDC)}")
    regra = dict(_PRETENSOES_CDC[pretensao])
    if pretensao == "vicio_oculto":
        if bem_duravel is None:
            raise HTTPException(422, (
                "Para vício OCULTO informe bem_duravel=sim|nao — a decadência é de 90 dias "
                "(durável) ou 30 dias (não durável), contada do aparecimento do defeito "
                "(CDC art. 26 §3º)."))
        regra["dias"] = 90 if _parse_sim_nao(bem_duravel, "bem_duravel") else 30
    # Prazos materiais (decadência/prescrição): contagem simples, SEM prorrogação
    # automática para dia útil.
    if regra["dias"] is not None:
        data_limite = data_marco + timedelta(days=regra["dias"])
        prazo_desc = f"{regra['dias']} dias"
    else:
        data_limite = _add_anos_data(data_marco, regra["anos"])
        prazo_desc = f"{regra['anos']} anos"
    dias_rest = (data_limite - date.today()).days
    return {
        "pretensao": pretensao,
        "instituto": regra["instituto"],
        "prazo": prazo_desc,
        "termo_inicial_correto": regra["termo_inicial"],
        "data_marco": data_marco,
        "data_limite": data_limite,
        "dias_restantes": dias_rest,
        "expirado": dias_rest < 0,
        "dias_desde_o_vencimento": abs(dias_rest) if dias_rest < 0 else 0,
        "urgente": 0 <= dias_rest <= 15,
        "base_legal": regra["base"],
        "nota_causas_obstativas": ("Obstam a DECADÊNCIA do art. 26 (§2º): a reclamação "
                                   "comprovada ao fornecedor, até resposta negativa transmitida "
                                   "de forma inequívoca (I), e a instauração de inquérito civil, "
                                   "até seu encerramento (III)."),
        "fontes": [
            "CDC (Lei 8.078/90) arts. 26 (I-III, §§1º-3º) e 27",
            "CC art. 205 · STJ EAREsp 738.991/RS (repetição de indébito contratual — decenal)",
        ],
        "vigencia_regra": "CDC arts. 26-27 · tese do EAREsp 738.991/RS (Corte Especial, 2023)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Confirme o termo inicial no caso "
                  "concreto e eventuais causas obstativas/suspensivas."),
    }


# ── Ferramentas Família ───────────────────────────────────────────────────────
@router.get("/familia/ferramentas/debito-alimentos")
async def familia_debito_alimentos(
    datas_vencimento_em_aberto: str = Query(
        ..., description="Datas ISO de vencimento das parcelas em aberto, separadas por vírgula"),
    data_ajuizamento_execucao: date = Query(...),
    valor_parcela: Optional[float] = None,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Rito da execução de alimentos (CPC art. 528 §7º; Súm. 309 STJ): autorizam a
    PRISÃO civil as 3 prestações ANTERIORES ao ajuizamento e as que VENCEREM no
    curso do processo; parcelas mais antigas seguem o rito da EXPROPRIAÇÃO
    (penhora — art. 528 §8º). MINUTA — revisão humana obrigatória.
    """
    parcelas: list[date] = []
    for token in (datas_vencimento_em_aberto or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            parcelas.append(date.fromisoformat(token))
        except ValueError:
            raise HTTPException(422, (
                f"Data de vencimento inválida: '{token}'. Use datas ISO (AAAA-MM-DD) "
                "separadas por vírgula — ex.: 2026-03-05,2026-04-05."))
    if not parcelas:
        raise HTTPException(422, "Informe ao menos uma data de vencimento em datas_vencimento_em_aberto.")
    if valor_parcela is not None and valor_parcela <= 0:
        raise HTTPException(422, "valor_parcela deve ser maior que zero.")
    parcelas.sort()
    corte = _add_meses_data(data_ajuizamento_execucao, -3)
    rito_prisao = [p for p in parcelas if p >= corte]        # 3 meses anteriores + vincendas
    rito_expropriacao = [p for p in parcelas if p < corte]
    out: dict = {
        "data_ajuizamento_execucao": data_ajuizamento_execucao,
        "marco_corte_3_meses": corte,
        "parcelas_rito_prisao": rito_prisao,
        "parcelas_rito_expropriacao": rito_expropriacao,
        "descricao_ritos": {
            "prisao": ("Parcelas vencidas nos 3 meses anteriores ao ajuizamento + as vencidas no "
                       "curso do processo — cumprimento sob pena de prisão (CPC art. 528 §§3º e "
                       "7º; Súm. 309 STJ)."),
            "expropriacao": ("Parcelas anteriores ao trimestre que precede o ajuizamento — "
                             "execução por penhora/expropriação (CPC art. 528 §8º c/c art. 831)."),
        },
        "fontes": [
            "CPC (Lei 13.105/2015) art. 528 §§3º, 7º e 8º",
            "Súmula 309 STJ",
        ],
        "vigencia_regra": "CPC/2015 art. 528 · Súm. 309 STJ (redação de 2006)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Valores sem correção monetária e juros; "
                  "as parcelas vincendas no curso do processo também autorizam a prisão."),
    }
    if valor_parcela is not None:
        out["valores"] = {
            "valor_parcela": valor_parcela,
            "debito_rito_prisao": round(valor_parcela * len(rito_prisao), 2),
            "debito_rito_expropriacao": round(valor_parcela * len(rito_expropriacao), 2),
            "debito_total": round(valor_parcela * len(parcelas), 2),
        }
    return out


# ── Ferramentas Imobiliário ───────────────────────────────────────────────────
@router.get("/imobiliario/ferramentas/reajuste-aluguel")
async def imobiliario_reajuste_aluguel(
    valor_atual: float = Query(..., gt=0),
    indice_percentual: float = Query(..., description="Variação ACUMULADA do índice contratual no período"),
    indice_nome: str = Query(..., description="Índice pactuado no contrato (ex.: IGP-M/FGV, IPCA/IBGE)"),
    data_base: date = Query(..., description="Data-base do último reajuste/início do contrato"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Reajuste de aluguel pelo índice PACTUADO no contrato (Lei 8.245/91 art. 18),
    respeitada a periodicidade ANUAL mínima (Lei 10.192/2001 art. 2º §1º).
    O índice e a variação acumulada são INFORMADOS pelo usuário — não há índice
    default: consultar a série oficial (FGV/IBGE) para o período exato.
    """
    if valor_atual <= 0:
        raise HTTPException(422, "valor_atual deve ser maior que zero.")
    if not (indice_nome or "").strip():
        raise HTTPException(422, "Informe indice_nome — o índice previsto na cláusula contratual.")
    hoje = date.today()
    aniversario = _add_anos_data(data_base, 1)
    anualidade_ok = hoje >= aniversario
    novo = round(valor_atual * (1 + indice_percentual / 100), 2)
    return {
        "valor_atual": valor_atual,
        "indice_nome": indice_nome.strip(),
        "indice_percentual_acumulado": indice_percentual,
        "data_base": data_base,
        "proximo_aniversario": aniversario,
        "periodicidade_anual_cumprida": anualidade_ok,
        "valor_reajustado": novo if anualidade_ok else valor_atual,
        "aumento": round(novo - valor_atual, 2) if anualidade_ok else 0.0,
        "memoria_calculo": (f"reajustado = R$ {valor_atual:.2f} × (1 + {indice_percentual}%) "
                            f"— índice {indice_nome.strip()} acumulado desde {data_base.isoformat()}"),
        "observacao": ("Reajuste só é exigível após 12 meses da data-base (Lei 10.192/2001 art. 2º "
                       "§1º). Índice e período devem corresponder à cláusula contratual; índices "
                       "negativos (deflação) reduzem o aluguel, salvo cláusula em contrário."
                       if anualidade_ok else
                       "PERIODICIDADE ANUAL NÃO CUMPRIDA: reajuste inexigível antes de 12 meses "
                       "da data-base (Lei 10.192/2001 art. 2º §1º)."),
        "fontes": [
            "Lei 8.245/91 (Lei do Inquilinato) arts. 17-19",
            "Lei 10.192/2001 art. 2º §1º (periodicidade anual)",
            "Série oficial do índice pactuado (FGV/IBGE) — consulta pelo usuário",
        ],
        "vigencia_regra": "Lei 8.245/91 · Lei 10.192/2001 — vigentes; índice conforme contrato e período",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Confira a série oficial do índice no "
                  "período e a cláusula de reajuste; cabe ação revisional após 3 anos (art. 19)."),
    }


@router.get("/imobiliario/ferramentas/prazos-despejo")
async def imobiliario_prazos_despejo(
    data_citacao: date,
    forma_comunicacao: Literal["citacao_pessoal", "citacao_ficta"],
    fundamento: str = "falta_pagamento",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prazos da ação de despejo e purga da mora (Lei 8.245/91 art. 62 II:
    15 dias contados da CITAÇÃO para purga)."""
    mapa = {
        "falta_pagamento": "Falta de pagamento — purga da mora em 15 dias da citação (art. 62 II).",
        "denuncia_vazia":  "Denúncia vazia — desocupação em 15 dias após sentença (art. 63).",
        "infracao":        "Infração contratual/legal (art. 9).",
    }
    if fundamento not in mapa:
        raise HTTPException(422, f"Fundamento inválido: '{fundamento}'. Use: {list(mapa)}")
    if forma_comunicacao not in ("citacao_pessoal", "citacao_ficta"):
        raise HTTPException(422, "forma_comunicacao inválida. Use: citacao_pessoal | citacao_ficta")
    ficta = forma_comunicacao == "citacao_ficta"
    contestacao, suspensao = _prazo_util_com_recesso(data_citacao, 15, "cpc")
    purga = prazo_dias_corridos(data_citacao, 15) if fundamento == "falta_pagamento" else None
    out = {
        "data_citacao": data_citacao, "fundamento": fundamento,
        "forma_comunicacao": forma_comunicacao,
        "prazo_contestacao": None if ficta else contestacao,
        "prazo_purga_mora": None if ficta else purga,
        "prazos_calculados": not ficta,
        "descricao": mapa[fundamento],
        "suspensao_aplicada": suspensao,
        "fontes": ["Lei 8.245/91 arts. 9º, 59-63", "CPC arts. 72 II, 220, 231, 252-259 e 335"],
        "vigencia_regra": "Lei 8.245/91 art. 62 (red. Lei 12.112/2009) · CPC/2015 art. 220",
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA — revisão humana obrigatória.",
    }
    if ficta:
        # Na citação ficta o dies a quo NÃO é a data informada: depende do
        # aperfeiçoamento do ato (CPC art. 231 IV/V) e da atuação do curador
        # especial — devolver data calculada seria induzir a erro.
        out["suspensao_aplicada"] = None
        out["nota_termo_inicial"] = (
            "CITAÇÃO FICTA: prazos NÃO calculados. O termo inicial depende do aperfeiçoamento "
            "do ato — hora certa: juntada do mandado cumprido; edital: fim do prazo do edital "
            "(CPC art. 231 IV e V) —, e o réu revel citado fictamente tem curador especial "
            "(CPC art. 72 II). Apure o dies a quo nos autos e recalcule pela citação pessoal.")
    else:
        out["nota_termo_inicial"] = (
            "Prazos contados da CITAÇÃO pessoal efetivada (Lei 8.245/91 art. 62 II; CPC art. "
            "231). Contestação em dias úteis com suspensão do recesso (CPC art. 220); a purga "
            "da mora é prazo material, em dias corridos.")
    return out


# ── Ferramentas Previdenciário ────────────────────────────────────────────────
@router.get("/previdenciario/ferramentas/prazos")
async def previdenciario_prazos(
    natureza: Literal["revisao_ato_concessao", "recurso_administrativo", "parcelas_atrasadas"],
    data_primeiro_pagamento: Optional[date] = None,   # revisão: 1º pagamento do benefício
    data_ciencia_decisao: Optional[date] = None,      # recurso: ciência da decisão do INSS
    data_ajuizamento: Optional[date] = None,          # parcelas: default hoje
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Motor de marcos previdenciários — cada natureza tem marco PRÓPRIO:
    • revisão do ato de concessão: DECADÊNCIA de 10 anos do dia 1º do mês seguinte
      ao PRIMEIRO PAGAMENTO (Lei 8.213/91 art. 103, red. Lei 13.846/2019);
    • recurso administrativo: 30 dias da CIÊNCIA da decisão (Dec. 3.048/99 art. 305);
    • parcelas atrasadas: prescrição quinquenal MÓVEL — prescritas as parcelas
      anteriores aos 5 anos do ajuizamento (art. 103 §ún.; Súm. 85 STJ) — não há
      "data final única". MINUTA — revisão humana obrigatória.
    """
    datas = {
        "revisao_ato_concessao": ("data_primeiro_pagamento", data_primeiro_pagamento),
        "recurso_administrativo": ("data_ciencia_decisao", data_ciencia_decisao),
        "parcelas_atrasadas": ("data_ajuizamento", data_ajuizamento),
    }
    if natureza not in datas:
        raise HTTPException(422, f"Natureza inválida: '{natureza}'. Use: {list(datas)}")
    incompativeis = [nome for nat, (nome, valor) in datas.items()
                     if valor is not None and nat != natureza]
    if incompativeis:
        raise HTTPException(422, (
            f"Data(s) incompatível(is) com a natureza '{natureza}': {', '.join(incompativeis)}. "
            f"Esta natureza usa apenas {datas[natureza][0]}."))
    comuns = {
        "natureza": natureza,
        "fontes": [
            "Lei 8.213/91 art. 103, caput (red. Lei 13.846/2019) e §ún.",
            "Decreto 3.048/99 art. 305 (recurso ao CRPS)",
            "Súmula 85 STJ (relação de trato sucessivo — prescrição do fundo não ocorre)",
        ],
        "vigencia_regra": "Lei 8.213/91 art. 103 com a redação da Lei 13.846/2019 (vigente desde 18/06/2019)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Verificar suspensões, menoridade "
                  "(prescrição não corre — CC art. 198 I) e o caso concreto."),
    }
    if natureza == "revisao_ato_concessao":
        if data_primeiro_pagamento is None:
            raise HTTPException(422, ("A revisão do ato de concessão exige data_primeiro_pagamento "
                                      "(Lei 8.213/91 art. 103: decadência de 10 anos do dia 1º do "
                                      "mês seguinte ao primeiro pagamento)."))
        ano = data_primeiro_pagamento.year + (1 if data_primeiro_pagamento.month == 12 else 0)
        mes = 1 if data_primeiro_pagamento.month == 12 else data_primeiro_pagamento.month + 1
        marco = date(ano, mes, 1)
        limite = _add_anos_data(marco, 10)
        return {
            "instituto": "decadência (10 anos)",
            "marco_inicial": f"dia 1º do mês seguinte ao primeiro pagamento ({marco.isoformat()})",
            "data_limite": limite,
            "dias_restantes": max((limite - date.today()).days, 0),
            "expirado": date.today() > limite,
            "base": "Lei 8.213/91 art. 103 caput (red. Lei 13.846/2019)",
            **comuns,
        }
    if natureza == "recurso_administrativo":
        if data_ciencia_decisao is None:
            raise HTTPException(422, ("O recurso administrativo exige data_ciencia_decisao "
                                      "(30 dias da ciência — Dec. 3.048/99 art. 305)."))
        limite = prazo_dias_corridos(data_ciencia_decisao, 30)
        return {
            "instituto": "prazo recursal administrativo (30 dias)",
            "marco_inicial": "ciência da decisão do INSS",
            "data_limite": limite,
            "dias_restantes": max((limite - date.today()).days, 0),
            "expirado": date.today() > limite,
            "base": "Decreto 3.048/99 art. 305 · Lei 9.784/99 art. 66 §1º (prorrogação p/ dia útil)",
            **comuns,
        }
    # parcelas_atrasadas — prescrição quinquenal MÓVEL
    ajuizamento = data_ajuizamento or date.today()
    limite_retroativo = _add_anos_data(ajuizamento, -5)
    return {
        "instituto": "prescrição quinquenal MÓVEL das parcelas",
        "data_ajuizamento": ajuizamento,
        "data_ajuizamento_presumida_hoje": data_ajuizamento is None,
        "limite_retroativo": limite_retroativo,
        "descricao": (f"Ajuizando em {ajuizamento.isoformat()}, são exigíveis as parcelas vencidas "
                      f"a partir de {limite_retroativo.isoformat()}; as anteriores estão prescritas. "
                      "NÃO há data final única: a janela de 5 anos se move com a data do "
                      "ajuizamento (trato sucessivo — Súm. 85 STJ)."),
        "base": "Lei 8.213/91 art. 103 §ún. · Súm. 85 STJ",
        **comuns,
    }


# ── Ferramentas Digital / LGPD ────────────────────────────────────────────────
@router.get("/digital_lgpd/ferramentas/multa-lgpd")
async def lgpd_multa(
    faturamento_anual: float = Query(..., ge=0, description="Faturamento no Brasil no último exercício (grupo/conglomerado)"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    TETO da multa simples da LGPD (art. 52 II): até 2% do faturamento no Brasil no
    último exercício, excluídos tributos, limitada a R$ 50 milhões POR INFRAÇÃO.
    O valor é um TETO, não a multa devida — a dosimetria é da ANPD (art. 52 §1º e
    Res. CD/ANPD nº 4/2023). MINUTA — revisão humana obrigatória.
    """
    if faturamento_anual < 0:
        raise HTTPException(422, "faturamento_anual não pode ser negativo.")
    dois_pct = round(faturamento_anual * 0.02, 2)
    return {
        "faturamento_anual": faturamento_anual,
        "multa_2pct": dois_pct,
        "teto_por_infracao": min(dois_pct, 50_000_000.0),
        "limitada_ao_teto_50mi": dois_pct > 50_000_000.0,
        "e_apenas_teto": True,
        "observacao": ("Multa SIMPLES de até 2% do faturamento da pessoa jurídica/grupo no Brasil "
                       "no último exercício, excluídos os tributos, limitada a R$ 50 milhões POR "
                       "INFRAÇÃO (art. 52 II). Há ainda multa DIÁRIA (art. 52 III), observado o "
                       "mesmo teto total."),
        "dosimetria_anpd": [
            "gravidade e natureza da infração e dos direitos afetados (art. 52 §1º I)",
            "boa-fé e vantagem auferida pelo infrator (II-III)",
            "condição econômica, reincidência e grau do dano (IV-VI)",
            "cooperação, adoção de política de boas práticas e medidas corretivas (VII-IX)",
            "critérios e faixas da Res. CD/ANPD nº 4/2023 (Regulamento de Dosimetria)",
        ],
        "fontes": [
            "LGPD (Lei 13.709/2018) art. 52, I-III e §1º",
            "Resolução CD/ANPD nº 4, de 24/02/2023 (dosimetria e aplicação de sanções)",
        ],
        "vigencia_regra": "LGPD art. 52 (sanções vigentes desde 01/08/2021) · Res. CD/ANPD 4/2023",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. O resultado é o TETO legal, não a multa "
                  "esperada; a dosimetria concreta é da ANPD."),
    }


@router.get("/digital_lgpd/ferramentas/prazos-lgpd")
async def lgpd_prazos(
    # `incidente` é o valor CANÔNICO (alinhado ao frontend); `incidente_anpd`
    # segue aceito como alias legado.
    tipo: Literal["resposta_titular", "incidente", "incidente_anpd"] = "resposta_titular",
    data_evento: Optional[date] = None,          # resposta_titular: data do requerimento do titular
    data_conhecimento: Optional[date] = None,    # incidente: data do CONHECIMENTO do incidente
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prazos da LGPD: resposta ao titular (15 dias — art. 19 II) e comunicação de
    incidente à ANPD em 3 dias ÚTEIS do CONHECIMENTO (Res. CD/ANPD nº 15/2024)."""
    if tipo not in ("resposta_titular", "incidente", "incidente_anpd"):
        raise HTTPException(422, "Tipo inválido. Use: resposta_titular | incidente")
    if tipo in ("incidente", "incidente_anpd"):
        tipo = "incidente"   # normaliza o alias legado para o valor canônico
        if data_conhecimento is None:
            raise HTTPException(422, ("Para incidente informe data_conhecimento — o prazo de 3 "
                                      "dias ÚTEIS conta do CONHECIMENTO do incidente pelo "
                                      "controlador (Res. CD/ANPD nº 15/2024 art. 6º)."))
        marco, prazo = data_conhecimento, prazo_dias_uteis(data_conhecimento, 3)
        desc = "Comunicação de incidente de segurança à ANPD e ao titular — 3 dias úteis do conhecimento."
        base = "LGPD art. 48 · Res. CD/ANPD nº 15/2024"
    else:
        if data_evento is None:
            raise HTTPException(422, "Para resposta ao titular informe data_evento (data do requerimento).")
        marco, prazo = data_evento, prazo_dias_corridos(data_evento, 15)
        desc = "Resposta ao titular sobre o tratamento de dados — 15 dias do requerimento."
        base = "LGPD art. 19 II"
    dias_rest = (prazo - date.today()).days
    return {
        "tipo": tipo, "descricao": desc, "data_marco": marco, "prazo_final": prazo,
        "dias_restantes": dias_rest, "expirado": dias_rest < 0,
        "base": base,
        "versao_norma": "Resolução CD/ANPD nº 15, de 24/04/2024 (comunicação de incidentes)",
        "fontes": ["LGPD (Lei 13.709/2018) arts. 19 II e 48", "Res. CD/ANPD nº 15/2024"],
        "vigencia_regra": "LGPD arts. 19/48 · Res. CD/ANPD nº 15/2024 (vigente desde 30/04/2024)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Previdenciário: tempo de contribuição (regra de pontos EC 103/2019) ────────
@router.get("/previdenciario/ferramentas/tempo-contribuicao")
@_com_regra("previdenciario_tempo_contribuicao")
async def previdenciario_tempo_contribuicao(
    idade: int,
    tempo_contribuicao_anos: float,
    sexo: Literal["F", "M"] = "M",
    ano: int = 2026,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Regra de transição por pontos (EC 103/2019 art. 15). Pontos = idade + tempo."""
    # Fim do startswith("M") — "Mulher" era tratado como masculino. Domínio fechado F|M.
    if sexo not in ("F", "M"):
        raise HTTPException(422, f"Sexo inválido: '{sexo}'. Use exatamente: F | M")
    homem = sexo == "M"
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
    beneficio: Literal["aposentadoria_idade_tc", "auxilio_incapacidade", "salario_maternidade"],
    categoria: Literal["empregada", "contribuinte_individual_facultativa", "segurada_especial"],
    meses_contribuicao: int = Query(..., ge=0),
    decorre_acidente_ou_doenca_isenta: str = Query(
        ..., description="sim | nao — acidente de qualquer natureza ou doença da lista (art. 26 II)"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Carência por benefício e categoria (Lei 8.213/91 arts. 24-27):
    aposentadorias 180 contribuições (art. 25 II); auxílio por incapacidade 12
    (art. 25 I), ISENTO se decorrente de acidente de qualquer natureza ou doença
    da lista (art. 26 II); salário-maternidade: ISENTO para empregada (art. 26 VI)
    e 10 contribuições para CI/facultativa/segurada especial (art. 25 III).
    MINUTA — revisão humana obrigatória.
    """
    beneficios_validos = ("aposentadoria_idade_tc", "auxilio_incapacidade", "salario_maternidade")
    categorias_validas = ("empregada", "contribuinte_individual_facultativa", "segurada_especial")
    if beneficio not in beneficios_validos:
        raise HTTPException(422, f"Benefício inválido: '{beneficio}'. Use: {list(beneficios_validos)}")
    if categoria not in categorias_validas:
        raise HTTPException(422, f"Categoria inválida: '{categoria}'. Use: {list(categorias_validas)}")
    if meses_contribuicao < 0:
        raise HTTPException(422, "meses_contribuicao deve ser ≥ 0.")
    isenta_acidente = _parse_sim_nao(decorre_acidente_ou_doenca_isenta,
                                     "decorre_acidente_ou_doenca_isenta")
    if beneficio == "aposentadoria_idade_tc":
        exigida, base = 180, "Lei 8.213/91 art. 25 II — 180 contribuições mensais"
        desc = "Aposentadoria por idade/tempo de contribuição."
    elif beneficio == "auxilio_incapacidade":
        if isenta_acidente:
            exigida, base = 0, "Lei 8.213/91 art. 26 II — ISENTO (acidente de qualquer natureza ou doença da lista)"
            desc = "Auxílio por incapacidade — carência dispensada."
        else:
            exigida, base = 12, "Lei 8.213/91 art. 25 I — 12 contribuições mensais"
            desc = "Auxílio por incapacidade temporária/permanente."
    else:   # salario_maternidade
        if categoria == "empregada":
            exigida, base = 0, "Lei 8.213/91 art. 26 VI — ISENTO para empregada (e trab. avulsa/doméstica)"
            desc = "Salário-maternidade — segurada empregada."
        else:
            exigida, base = 10, "Lei 8.213/91 art. 25 III — 10 contribuições mensais"
            desc = "Salário-maternidade — CI/facultativa/segurada especial (comprovação de atividade p/ especial)."
    return {
        "beneficio": beneficio,
        "categoria": categoria,
        "descricao": desc,
        "meses_contribuicao": meses_contribuicao,
        "carencia_exigida": exigida,
        "carencia_cumprida": meses_contribuicao >= exigida,
        "faltam_meses": max(0, exigida - meses_contribuicao),
        "base_legal": base,
        "nota_perda_qualidade": ("Perda da qualidade de segurado: para recontagem, exige-se METADE "
                                 "da carência do benefício após a nova filiação (Lei 8.213/91 "
                                 "art. 27-A, red. Lei 13.846/2019)."),
        "fontes": [
            "Lei 8.213/91 arts. 24-27 (carência) e 27-A (red. Lei 13.846/2019)",
        ],
        "vigencia_regra": "Lei 8.213/91 arts. 24-27-A com a redação da Lei 13.846/2019",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Conferir CNIS, qualidade de segurado na "
                  "DER e a lista de doenças isentas (Portaria interministerial vigente)."),
    }


# ── Família: ITCMD no inventário (sem tabela hardcoded por UF) ────────────────
@router.get("/familia/ferramentas/itcmd-inventario")
async def familia_itcmd(
    valor_monte: float = Query(..., gt=0),
    uf: str = Query(..., min_length=2, max_length=2, description="UF do fato gerador (2 letras)"),
    aliquota_percent: float = Query(..., ge=0, le=8,
                                    description="Alíquota da LEI ESTADUAL da UF na data do fato gerador"),
    data_fato_gerador: date = Query(..., description="Óbito (causa mortis) ou doação"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    ITCMD sobre o monte partilhável — SEM alíquota default: a alíquota é a da LEI
    ESTADUAL da UF vigente na data do fato gerador (Súm. 112 STF: alíquota do tempo
    da abertura da sucessão), limitada a 8% (Res. Senado 9/1992).
    MINUTA — revisão humana obrigatória.
    """
    uf_norm = (uf or "").strip().upper()
    if len(uf_norm) != 2 or not uf_norm.isalpha():
        raise HTTPException(422, "UF inválida — informe a sigla de 2 letras (ex.: MG, SP).")
    if valor_monte <= 0:
        raise HTTPException(422, "valor_monte deve ser maior que zero.")
    if not 0 <= aliquota_percent <= 8:
        raise HTTPException(422, ("aliquota_percent fora do intervalo 0-8%: o teto nacional do "
                                  "ITCMD é 8% (Resolução do Senado nº 9/1992). Confira a lei "
                                  "estadual da UF."))
    imposto = round(valor_monte * aliquota_percent / 100, 2)
    return {
        "uf": uf_norm,
        "data_fato_gerador": data_fato_gerador,
        "valor_monte": valor_monte,
        "aliquota_percent": aliquota_percent,
        "itcmd_estimado": imposto,
        "liquido_herdeiros": round(valor_monte - imposto, 2),
        "nota_aliquota": ("Alíquota INFORMADA pelo usuário — confira a lei estadual da UF "
                          f"({uf_norm}) vigente em {data_fato_gerador.isoformat()} (Súm. 112 STF: "
                          "aplica-se a alíquota vigente ao tempo da abertura da sucessão; "
                          "Súm. 114 STF: exigível só após a homologação do cálculo)."),
        "nota_base_calculo": ("Base de cálculo, progressividade, isenções e descontos dependem da "
                              "legislação estadual e da AVALIAÇÃO dos bens — o cálculo real é "
                              "apurado na declaração do ITCMD do estado."),
        "fontes": [
            "CF art. 155 I e §1º · CTN arts. 35-42",
            "Resolução do Senado Federal nº 9/1992 (teto de 8%)",
            "Súmulas 112 e 114 STF",
            "Legislação estadual da UF informada (conferência obrigatória)",
        ],
        "vigencia_regra": "Regras gerais CF/CTN · alíquota conforme lei estadual na data do fato gerador",
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA — revisão humana obrigatória.",
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


# ── Trabalhista: horas extras (divisor explícito + componentes opcionais) ─────
@router.get("/trabalhista-esp/ferramentas/horas-extras")   # rota CANÔNICA
@router.get("/trabalhista/ferramentas/horas-extras", deprecated=True)   # alias legado (compat vitrine)
async def trabalhista_horas_extras(
    salario_mensal: float = Query(..., gt=0),
    horas_extras_mes: float = Query(..., ge=0),
    divisor: int = Query(..., description="Divisor de horas: 220 (44h/sem), 200 (40h — Súm. 431 TST), 180 (36h) ou o da norma coletiva"),
    percentual_he: float = 50.0,
    incluir_dsr: str = Query(..., description="sim | nao — DSR de 1/6 sobre as HE"),
    incluir_reflexo_fgts: str = Query(..., description="sim | nao — FGTS de 8% sobre HE+DSR"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Valor mensal de horas extras com DIVISOR explícito (220/200/180 ou o previsto
    em norma coletiva) e componentes opcionais discriminados (DSR 1/6; FGTS 8%).
    Adicional mínimo de 50% (CF art. 7º XVI); norma coletiva pode fixar percentual
    superior. MINUTA — revisão humana obrigatória.
    """
    if salario_mensal <= 0 or horas_extras_mes < 0:
        raise HTTPException(422, "salario_mensal deve ser > 0 e horas_extras_mes ≥ 0.")
    if divisor <= 0:
        raise HTTPException(422, "Divisor inválido — use 220, 200, 180 ou o divisor da norma coletiva (> 0).")
    if percentual_he < 50:
        raise HTTPException(422, "percentual_he abaixo do mínimo constitucional de 50% (CF art. 7º XVI).")
    com_dsr = _parse_sim_nao(incluir_dsr, "incluir_dsr")
    com_fgts = _parse_sim_nao(incluir_reflexo_fgts, "incluir_reflexo_fgts")

    valor_hora = salario_mensal / divisor
    valor_he = valor_hora * (1 + percentual_he / 100) * horas_extras_mes
    dsr = valor_he / 6 if com_dsr else 0.0
    fgts = (valor_he + dsr) * 0.08 if com_fgts else 0.0
    return {
        "rota_canonica": "/trabalhista-esp/ferramentas/horas-extras",
        "parametros": {"salario_mensal": salario_mensal, "divisor": divisor,
                       "percentual_he": percentual_he, "horas_extras_mes": horas_extras_mes,
                       "incluir_dsr": com_dsr, "incluir_reflexo_fgts": com_fgts},
        "componentes": {
            "valor_hora_normal": round(valor_hora, 2),
            "valor_horas_extras": round(valor_he, 2),
            "dsr_sobre_he": round(dsr, 2),
            "fgts_8pct_sobre_he_dsr": round(fgts, 2),
        },
        "total_mes_estimado": round(valor_he + dsr + fgts, 2),
        "memoria_calculo": (f"hora = {salario_mensal:.2f} ÷ {divisor}; HE = hora × "
                            f"(1 + {percentual_he}%) × {horas_extras_mes}"
                            + ("; DSR = HE ÷ 6" if com_dsr else "")
                            + ("; FGTS = 8% × (HE + DSR)" if com_fgts else "")),
        "nota_divisor": ("Divisores usuais: 220 (jornada 44h/sem), 200 (40h/sem — Súm. 431 TST), "
                         "180 (36h/sem). Prevalece o divisor da norma coletiva, se houver."),
        "nota_reflexos": ("Reflexos em 13º, férias+1/3 e aviso prévio NÃO estão incluídos — "
                          "apurar em liquidação (Súm. 264 TST: base = globalidade salarial; "
                          "OJ 394 SDI-1, nova redação 2023: repercussão do DSR majorado nas "
                          "demais parcelas para HE a partir de 20/03/2023)."),
        "fontes": [
            "CF art. 7º XVI (adicional mínimo de 50%)",
            "CLT art. 59 e art. 64 (valor da hora)",
            "Súmula 264 TST (base de cálculo) · Súmula 431 TST (divisor 200)",
            "Lei 605/49 art. 7º (DSR) · OJ 394 SDI-1/TST (red. 2023)",
        ],
        "vigencia_regra": "CF/88 art. 7º XVI · Súm. 264/431 TST · OJ 394 SDI-1 red. 2023 (modulação 20/03/2023)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Estimativa mensal simples; conferir "
                  "norma coletiva (divisor, percentual e base) e verbas habituais integrantes."),
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
        # Período INTEIRAMENTE anterior à Lei 14.905/2024: só a regra antiga se
        # aplica — não faz sentido exigir Selic/IPCA de um período inexistente.
        if fim < _VIGENCIA_LEI_14905:
            meses_ant = round((fim - data_inicio_mora).days / 30, 4)
            juros_ant = valor_principal * 0.01 * meses_ant
            componentes.append({
                "parcela": "juros do período sob a regra anterior (1% a.m.)",
                "periodo": f"{data_inicio_mora.isoformat()} a {fim.isoformat()}",
                "memoria": f"R$ {valor_principal:.2f} × 1% a.m. × {meses_ant} meses (pro rata 30 dias)",
                "valor": round(juros_ant, 2),
                "base": "CC art. 406 (redação original) c/c CTN art. 161 §1º — até 29/08/2024",
            })
            juros_total = round(sum(c["valor"] for c in componentes), 2)
            multa_ant = round(valor_principal * multa_pct / 100, 2)
            return {
                "regime": regime,
                "valor_principal": valor_principal,
                "data_inicio_mora": data_inicio_mora,
                "data_fim": fim,
                "componentes": componentes,
                "juros_mora_total": juros_total,
                "multa": multa_ant,
                "nota_multa": "Multa apenas se pactuada; em relação de consumo, limitada a 2% (CDC art. 52 §1º).",
                "total_devido": round(valor_principal + juros_total + multa_ant, 2),
                "nota_regime": ("Período INTEGRALMENTE anterior a 30/08/2024: aplica-se apenas a "
                                "regra anterior (1% a.m.); a taxa legal da Lei 14.905/2024 não "
                                "incide sobre esse intervalo."),
                "fontes": [
                    "CC art. 406 (redação original) c/c CTN art. 161 §1º",
                    "CC art. 395 (efeitos da mora)",
                    "CDC art. 52 §1º (multa de 2% em relações de consumo)",
                ],
                "vigencia_regra": "Regra anterior à Lei 14.905/2024 (mora encerrada antes de 30/08/2024)",
                "versao_regra": _VERSAO_REGRA,
                "aviso": ("MINUTA — revisão humana obrigatória. Cálculo SEM correção monetária "
                          "do principal e sem capitalização."),
            }
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
                # Regra antiga vigora ATÉ 29/08/2024 (inclusive); a nova, a partir de 30/08.
                fim_regra_antiga = _VIGENCIA_LEI_14905 - timedelta(days=1)
                meses_ant = round((fim_regra_antiga - data_inicio_mora).days / 30, 4)
                juros_ant = valor_principal * 0.01 * meses_ant
                componentes.append({
                    "parcela": "juros do período sob a regra anterior (1% a.m.)",
                    "periodo": f"{data_inicio_mora.isoformat()} a {fim_regra_antiga.isoformat()}",
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


# ── Tributário: multa de mora (regra federal SÓ para ente federal) ────────────
@router.get("/tributario/ferramentas/multa-mora")
async def tributario_multa_mora(
    ente: Literal["federal", "estadual", "municipal"],
    valor_tributo: float = Query(..., gt=0),
    dias_atraso: int = Query(..., ge=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Multa de mora de tributos: FEDERAL = 0,33%/dia limitada a 20% (Lei 9.430/96
    art. 61). Estadual/municipal: a multa é a da LEI DO ENTE — sem cálculo com a
    regra federal."""
    if ente not in ("federal", "estadual", "municipal"):
        raise HTTPException(422, "Ente inválido. Use: federal | estadual | municipal")
    if valor_tributo <= 0 or dias_atraso < 0:
        raise HTTPException(422, "valor_tributo deve ser > 0 e dias_atraso ≥ 0.")
    comuns = {
        "ente": ente,
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA — revisão humana obrigatória.",
    }
    if ente != "federal":
        return {
            "calculo": None,
            "orientacao": (f"Tributo {ente}: a multa de mora é definida pela legislação do "
                           "PRÓPRIO ente (ex.: MG — Lei 6.763/75; municípios — código tributário "
                           "municipal). A regra federal de 0,33%/dia (Lei 9.430/96 art. 61) NÃO "
                           "se aplica. Confira a lei indicada na guia/auto e recalcule."),
            "fontes": ["Legislação tributária do ente competente (conferência obrigatória)",
                       "CTN art. 161 (juros de mora — norma geral)"],
            "vigencia_regra": "Multa conforme a lei do ente na data do vencimento",
            **comuns,
        }
    pct = min(0.33 * dias_atraso, 20.0)
    multa = round(valor_tributo * pct / 100, 2)
    return {
        "valor_tributo": valor_tributo, "dias_atraso": dias_atraso,
        "percentual_multa": round(pct, 2), "multa_mora": multa,
        "atingiu_teto_20pct": pct >= 20.0,
        "total_sem_juros": round(valor_tributo + multa, 2),
        "observacao": ("Multa de mora federal: 0,33% por dia de atraso, limitada a 20%. Acrescer "
                       "juros Selic acumulada (não incluídos)."),
        "fontes": ["Lei 9.430/96 art. 61 §§1º-2º"],
        "vigencia_regra": "Lei 9.430/96 art. 61 — tributos federais, vigente",
        **comuns,
    }


# ── Bancário: taxa contratada × média BACEN (classificação INDICATIVA) ────────
# Sem booleano "abusivo sim/não": o STJ afere abusividade caso a caso, tendo a
# taxa média de mercado como parâmetro (REsp 1.061.530/RS) e 1,5× como
# REFERENCIAL jurisprudencial, não vinculante.
_LIMIARES_TAXA_MEDIA = {
    "abaixo_da_media": "razão < 0,95 (mais de 5% abaixo da média)",
    "na_media": "razão entre 0,95 e 1,10 (até 10% acima da média)",
    "acima_da_media": "razão entre 1,10 e 1,50",
    "substancialmente_acima": "razão > 1,50 — REFERENCIAL jurisprudencial (REsp 1.061.530/RS), não vinculante",
}
_COMPARABILIDADE_REQUISITOS = [
    "mesma MODALIDADE de crédito (série BCB específica)",
    "mesma DATA/mês de contratação",
    "perfil do tomador (PF/PJ, risco de crédito)",
    "garantias oferecidas (consignação, alienação fiduciária etc.)",
    "prazo da operação",
    "CET — custo efetivo total (Res. CMN 3.517/2007), não apenas a taxa nominal",
]


def _classificar_taxa_vs_media(contratada: float, media: float) -> dict:
    if media <= 0 or contratada < 0:
        raise HTTPException(422, "Taxas inválidas: a média deve ser > 0 e a contratada ≥ 0.")
    razao = contratada / media
    if razao < 0.95:
        classificacao = "abaixo_da_media"
    elif razao <= 1.10:
        classificacao = "na_media"
    elif razao <= 1.50:
        classificacao = "acima_da_media"
    else:
        classificacao = "substancialmente_acima"
    return {
        "razao_sobre_media": round(razao, 4),
        "distancia_percentual": round((razao - 1) * 100, 2),
        "classificacao_indicativa": classificacao,
        "limiares_classificacao": _LIMIARES_TAXA_MEDIA,
        "comparabilidade_requisitos": _COMPARABILIDADE_REQUISITOS,
    }


@router.get("/bancario/ferramentas/juros-abusivos")
async def bancario_juros_abusivos(
    taxa_contratada_mensal_pct: float,
    taxa_media_bacen_mensal_pct: float,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Compara a taxa contratada com a média de mercado (BACEN) p/ tese revisional —
    classificação INDICATIVA, sem veredito de abusividade (aferição é casuística)."""
    comp = _classificar_taxa_vs_media(taxa_contratada_mensal_pct, taxa_media_bacen_mensal_pct)
    return {
        "taxa_contratada": taxa_contratada_mensal_pct,
        "taxa_media_bacen": taxa_media_bacen_mensal_pct,
        **comp,
        "observacao": ("O STJ NÃO fixa teto rígido: a abusividade é aferida caso a caso, com a "
                       "taxa média do BACEN como parâmetro (REsp 1.061.530/RS); 1,5× a média é "
                       "referencial usual, não regra. A comparação só é válida se atendidos os "
                       "requisitos de comparabilidade listados."),
        "fontes": [
            "STJ REsp 1.061.530/RS (recurso repetitivo)",
            "Súmula 530 STJ",
            "Res. CMN 3.517/2007 (CET)",
            "BCB — séries de taxas médias por modalidade",
        ],
        "vigencia_regra": "Jurisprudência consolidada do STJ (REsp 1.061.530/RS · Súm. 530)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Laudo pericial e a série BCB exata da "
                  "modalidade/data são indispensáveis para a tese revisional."),
    }


# ── Imobiliário: distrato (Lei 13.786/2018 — art. 67-A da Lei 4.591/64) ───────
@router.get("/imobiliario/ferramentas/distrato")
async def imobiliario_distrato(
    valor_pago: float = Query(..., gt=0),
    regime_patrimonio_afetacao: str = Query(..., description="sim | nao"),
    percentual_retencao: Optional[float] = None,   # dentro do teto do regime; default = teto
    comissao_corretagem: float = 0.0,              # dedutível (art. 67-A §2º)
    meses_fruicao: int = 0,
    valor_fruicao_mensal: float = 0.0,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Distrato de imóvel na planta (Lei 13.786/2018): pena convencional de ATÉ 25%
    da quantia paga — ou ATÉ 50% quando a incorporação estiver submetida a
    patrimônio de AFETAÇÃO (art. 67-A caput e §5º) — além das deduções do §2º
    (corretagem, fruição etc.). MINUTA — revisão humana obrigatória.
    """
    if valor_pago <= 0:
        raise HTTPException(422, "valor_pago deve ser maior que zero.")
    if comissao_corretagem < 0 or meses_fruicao < 0 or valor_fruicao_mensal < 0:
        raise HTTPException(422, "Deduções (corretagem/fruição) não podem ser negativas.")
    afetacao = _parse_sim_nao(regime_patrimonio_afetacao, "regime_patrimonio_afetacao")
    teto = 50.0 if afetacao else 25.0
    # Omissão assume o TETO (pior cenário para o consumidor) — sinalizado de forma
    # explícita na resposta para não passar por percentual efetivamente pactuado.
    assumido_por_omissao = percentual_retencao is None
    pct = teto if assumido_por_omissao else percentual_retencao
    if not 0 <= pct <= teto:
        raise HTTPException(422, (
            f"percentual_retencao fora do teto do regime: máximo de {teto:.0f}% "
            f"({'com' if afetacao else 'sem'} patrimônio de afetação — Lei 13.786/2018, "
            "art. 67-A caput/§5º da Lei 4.591/64)."))
    pena = round(valor_pago * pct / 100, 2)
    fruicao = round(meses_fruicao * valor_fruicao_mensal, 2)
    a_restituir = round(max(valor_pago - pena - comissao_corretagem - fruicao, 0.0), 2)
    return {
        "regime_patrimonio_afetacao": afetacao,
        "teto_legal_retencao_pct": teto,
        "percentual_retencao_aplicado": pct,
        "retencao_assumida_por_omissao": assumido_por_omissao,
        "alerta_retencao": (f"percentual_retencao NÃO informado — assumido o TETO legal de "
                            f"{teto:.0f}% (pior cenário para o adquirente). Informe o percentual "
                            "efetivamente PACTUADO no contrato para o cálculo real."
                            if assumido_por_omissao else
                            "Percentual informado pelo usuário conforme cláusula contratual."),
        "memoria_calculo": {
            "valor_pago": valor_pago,
            "pena_convencional": pena,
            "comissao_corretagem_deduzida": round(comissao_corretagem, 2),
            "deducao_fruicao": fruicao,
            "formula": (f"restituir = {valor_pago:.2f} − pena {pct}% ({pena:.2f}) − corretagem "
                        f"({comissao_corretagem:.2f}) − fruição ({fruicao:.2f})"),
        },
        "valor_a_restituir": a_restituir,
        "prazo_devolucao": ("SEM patrimônio de afetação: restituição em parcela única em até 180 "
                            "dias do desfazimento; COM afetação: em até 30 dias após o habite-se "
                            "(Lei 4.591/64, art. 67-A §§5º-6º, incl. Lei 13.786/2018). CONFIRA a "
                            "cláusula do contrato — condições contratuais mais favoráveis prevalecem."),
        "fontes": [
            "Lei 4.591/64 art. 67-A (incluído pela Lei 13.786/2018), caput e §§2º, 5º-6º",
        ],
        "vigencia_regra": "Lei 13.786/2018, vigente desde 28/12/2018 (contratos posteriores; "
                          "anteriores seguem a jurisprudência do STJ — retenção usual de 10-25%)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. Deduções de impostos e taxas condominiais "
                  "fruídos (art. 67-A §2º) não computadas; cláusulas acima do teto são revisáveis."),
    }


# ── Trânsito: valor da multa por gravidade ────────────────────────────────────
@router.get("/transito/ferramentas/valor-multa")
@_com_regra("transito_valor_multa")
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
    if multiplicador < 1:
        raise HTTPException(422, "multiplicador deve ser ≥ 1 (fator do CTB art. 258 §§1º-2º).")
    if gravidade != "gravissima" and multiplicador > 1:
        raise HTTPException(422, ("Multiplicador só se aplica a infrações GRAVÍSSIMAS previstas "
                                  "com fator próprio (CTB art. 258 §2º)."))
    valor, pontos, desc = tabela[gravidade]
    total = round(valor * multiplicador, 2)
    return {
        "gravidade": gravidade, "descricao": desc,
        "valor_base": valor, "multiplicador": multiplicador,
        "valor_total": total, "pontos_cnh": pontos,
        "vigencia_tabela": "Valores-base do CTB art. 258 na redação da Lei 13.281/2016 (desde 01/11/2016)",
        "fonte": "CTB (Lei 9.503/97) art. 258 c/c Lei 13.281/2016",
        "observacao": "Valores-base do CTB art. 258. Gravíssimas podem ter multiplicador (x2, x3, x5, x10, x20) conforme a infração.",
        "base": "CTB art. 258 c/c Lei 13.281/2016.",
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


# ── Consumidor: negativação indevida — checklist de análise (Súm. 385 STJ) ────
@router.get("/consumidor/ferramentas/negativacao-indevida")
async def consumidor_negativacao(
    existe_inscricao_anterior: str = Query(..., description="sim | nao"),
    inscricao_anterior_legitima_e_ativa: Optional[str] = None,   # sim|nao — obrigatório se anterior=sim
    origem_verificada: Optional[str] = None,                     # sim|nao — obrigatório se anterior=sim
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Checklist de análise da negativação indevida — a Súmula 385 STJ só afasta o
    dano moral se a inscrição ANTERIOR for LEGÍTIMA, CONTEMPORÂNEA e ATIVA; a
    resposta estrutura o que precisa ser verificado, nunca um sim/não seco.
    MINUTA — revisão humana obrigatória.
    """
    tem_anterior = _parse_sim_nao(existe_inscricao_anterior, "existe_inscricao_anterior")
    verificacoes = [
        "Contemporaneidade: a inscrição anterior estava ATIVA à época da nova anotação?",
        "Baixa/quitação: a anotação anterior já havia sido baixada ou paga quando da nova inscrição?",
        "Impugnação: a inscrição anterior é objeto de questionamento judicial/administrativo?",
    ]
    if not tem_anterior:
        return {
            "existe_inscricao_anterior": False,
            "sumula_385_aplicavel": False,
            "conclusao_indicativa": ("Sem inscrição preexistente, o dano moral pela negativação "
                                     "indevida é presumido (in re ipsa — STJ REsp 1.059.663); a "
                                     "Súm. 385 não incide."),
            "verificacoes_pendentes": [
                "Confirmar nos 3 birôs (SPC/Serasa/SCR-BCB) a inexistência de outras anotações "
                "contemporâneas à inscrição impugnada.",
            ],
            "fontes": ["Súmula 385 STJ", "STJ REsp 1.059.663", "CDC arts. 6º VI e 43"],
            "vigencia_regra": "Súm. 385 STJ (2009) e jurisprudência consolidada do STJ",
            "versao_regra": _VERSAO_REGRA,
            "aviso": "MINUTA — revisão humana obrigatória.",
        }
    if inscricao_anterior_legitima_e_ativa is None or origem_verificada is None:
        raise HTTPException(422, (
            "Havendo inscrição anterior, informe inscricao_anterior_legitima_e_ativa=sim|nao e "
            "origem_verificada=sim|nao — a Súm. 385 STJ só incide se a anotação preexistente for "
            "legítima, contemporânea e ativa."))
    legitima = _parse_sim_nao(inscricao_anterior_legitima_e_ativa, "inscricao_anterior_legitima_e_ativa")
    origem_ok = _parse_sim_nao(origem_verificada, "origem_verificada")
    pendentes = list(verificacoes)
    if not origem_ok:
        pendentes.insert(0, "ORIGEM não verificada: confirmar junto ao credor/órgão a validade e "
                            "a origem do débito da inscrição anterior.")
    if legitima and origem_ok:
        conclusao = ("Indicativo de INCIDÊNCIA da Súm. 385 STJ: inscrição anterior legítima e "
                     "ativa afasta a indenização pela nova anotação irregular — cabe apenas o "
                     "cancelamento. Concluir somente após as verificações pendentes.")
    else:
        conclusao = ("Indicativo de NÃO incidência da Súm. 385 STJ: sem legitimidade/atividade "
                     "comprovada da anotação anterior (ou origem não verificada), o dano moral "
                     "pela nova inscrição permanece discutível. Concluir após as verificações.")
    return {
        "existe_inscricao_anterior": True,
        "inscricao_anterior_legitima_e_ativa": legitima,
        "origem_verificada": origem_ok,
        "sumula_385_aplicavel": ("somente se a inscrição anterior for legítima, contemporânea e "
                                 "ativa — ver verificações pendentes"),
        "conclusao_indicativa": conclusao,
        "verificacoes_pendentes": pendentes,
        "fontes": ["Súmula 385 STJ", "STJ REsp 1.059.663", "CDC arts. 6º VI e 43"],
        "vigencia_regra": "Súm. 385 STJ (2009) e jurisprudência consolidada do STJ",
        "versao_regra": _VERSAO_REGRA,
        "aviso": "MINUTA — revisão humana obrigatória.",
    }


@router.get("/admin-esp/ferramentas/mandado-seguranca")
@_com_regra("adm_ms")
async def adm_ms(
    data_ato_coator: date,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazo DECADENCIAL do Mandado de Segurança: 120 dias CORRIDOS contados da
    ciência, pelo interessado, do ato impugnado (Lei 12.016/2009 art. 23) —
    prazo não se suspende nem se interrompe; vencimento em dia não útil prorroga
    para o primeiro dia útil. MINUTA — revisão humana obrigatória.
    """
    prazo_ms = prazo_dias_corridos(data_ato_coator, 120)
    dias_restantes = (prazo_ms - date.today()).days
    vencido = dias_restantes < 0
    return {
        "data_ato_coator": data_ato_coator,
        "prazo_impetracao": prazo_ms,
        "prazo_impetração": prazo_ms,   # chave legada (compat. com a vitrine)
        "dias_restantes": dias_restantes,
        "vencido": vencido,
        "dias_desde_o_vencimento": abs(dias_restantes) if vencido else 0,
        "urgente": (not vencido) and dias_restantes <= 10,
        "natureza_do_prazo": ("DECADENCIAL — não se suspende nem se interrompe (Lei 12.016/2009 "
                              "art. 23); constitucionalidade reconhecida (Súm. 632 STF). Em "
                              "obrigações de trato sucessivo, o prazo renova-se a cada prestação."),
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
    comp = _classificar_taxa_vs_media(taxa_mensal_contratada, taxa_mensal_referencia)
    return {
        "taxa_mensal_contratada_pct": taxa_mensal_contratada,
        "taxa_anual_efetiva_contratada_pct": round(taxa_anual_contrat, 4),
        "taxa_mensal_referencia_pct": taxa_mensal_referencia,
        "taxa_anual_referencia_pct": round(taxa_anual_ref, 4),
        "spread_absoluto_pct_mes": round(spread_pct, 4),
        "spread_relativo_pct": round(spread_relativo, 2),
        "excesso_estimado_12_meses": excesso_12m,
        **comp,
        "fontes": [
            "STJ Súm. 530 (2015): pactuação livre, exige prova de abusividade",
            "STJ REsp 1.061.530/RS (recurso repetitivo): parâmetros de revisão",
            "Res. CMN 3.517/2007: obrigatoriedade de informação do CET",
            "CDC art. 52: informação clara e prévia do custo total",
        ],
        "vigencia_regra": "Jurisprudência consolidada do STJ (REsp 1.061.530/RS · Súm. 530)",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — classificação INDICATIVA (sem veredito de abusividade). Laudo "
                  "pericial contábil é indispensável para demonstrar abusividade em juízo."),
    }


@router.get("/bancario/ferramentas/superendividamento")
@_com_regra("ban_superendiv")
async def ban_superendiv(
    renda_mensal: float = Query(..., gt=0),
    total_parcelas_mes: float = Query(..., gt=0),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Triagem de superendividamento (CDC art. 54-A, incl. Lei 14.181/2021).
    MÍNIMO EXISTENCIAL: o Decreto 11.150/2022 (red. Dec. 11.567/2023) fixa a
    renda mensal líquida de 25% do salário mínimo como parâmetro — NÃO 1 SM nem
    percentual fixo de comprometimento. O superendividamento é a impossibilidade
    manifesta de pagar a totalidade das dívidas de consumo sem comprometer o
    mínimo existencial. MINUTA — revisão humana obrigatória.
    """
    if renda_mensal <= 0 or total_parcelas_mes < 0:
        raise HTTPException(422, "renda_mensal deve ser > 0 e total_parcelas_mes ≥ 0.")
    sm = _sm_vigente()
    minimo_existencial = round(sm * 0.25, 2)   # Dec. 11.150/2022, red. Dec. 11.567/2023
    renda_disponivel = round(renda_mensal - minimo_existencial, 2)
    percentual_comprometido = (total_parcelas_mes / renda_mensal) * 100
    compromete_minimo = total_parcelas_mes > renda_disponivel
    return {
        "renda_mensal": renda_mensal,
        "total_parcelas_mensais": total_parcelas_mes,
        "percentual_comprometido": round(percentual_comprometido, 2),
        "minimo_existencial_referencia": minimo_existencial,
        "criterio_minimo_existencial": ("25% do salário mínimo vigente (Dec. 11.150/2022, art. 3º, "
                                        f"red. Dec. 11.567/2023) — R$ {minimo_existencial:.2f}"),
        "renda_disponivel_apos_min_exist": renda_disponivel,
        "compromete_minimo_existencial": compromete_minimo,
        "indicativo_superendividamento": compromete_minimo,
        "nota_criterio": ("Não há percentual legal de comprometimento (o '30% da renda' é praxe "
                          "bancária, não regra do CDC): o critério legal é a impossibilidade "
                          "manifesta de pagar sem comprometer o mínimo existencial (art. 54-A §1º), "
                          "excluídas as dívidas de consumo contraídas com má-fé, sem propósito "
                          "de pagamento, ou provenientes de contratos de luxo (§3º)."),
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
@_com_regra("ban_ba")
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


# ── Cível: prescrição/decadência do consumidor (CDC arts. 26-27) ─────────────
@router.get("/civel/ferramentas/prescricao-consumidor")
@_com_regra("civ_prescricao_consumidor")
async def civ_prescricao_consumidor(
    data_fato: date,
    tipo_vicio: Literal["fato_produto", "fato_servico",
                        "servico_ou_produto", "cobranca_indevida"] = "fato_produto",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Prescrição (5 anos, fato do produto/serviço) e decadência (30/90 dias, vício)."""
    if tipo_vicio in ("fato_produto", "fato_servico"):
        limite = _add_anos_data(data_fato, 5)
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
        "prazo_stj_10_anos": {"data_limite": _add_anos_data(data_fato, 10),
                              "base": "CC art. 205 — STJ EAREsp 738.991/RS (Corte Especial)"},
        "corrente_3_anos": {"data_limite": _add_anos_data(data_fato, 3),
                            "base": "CC art. 206 §3º IV (enriquecimento sem causa) — minoritária"},
        "devolucao_em_dobro": "Cabível quando a cobrança contraria a boa-fé objetiva "
                              "(CDC art. 42 § único — STJ EAREsp 676.608, sem exigir má-fé após 30/03/2021).",
        "base_legal": "CC art. 205 · CDC art. 42 § único · STJ EAREsp 738.991/RS.",
        "aviso": "MINUTA — prevalece o prazo decenal no STJ; avaliar o caso concreto.",
    }


# ── Cível: dano moral — SEM faixas fixas (tarifação vedada) ───────────────────
# Qualificadores DESCRITIVOS por tipo de caso; nenhum valor absoluto hardcoded.
_TIPOS_DANO_MORAL = {
    "negativacao_indevida": "Negativação indevida — dano in re ipsa (STJ REsp 1.059.663); verificar Súm. 385 STJ.",
    "extravio_bagagem":     "Extravio de bagagem — CDC prevalece sobre a tarifação de convenções internacionais quanto ao dano moral.",
    "produto_defeituoso":   "Produto defeituoso sem risco à saúde — mero vício, sem outros transtornos, pode não gerar dano moral.",
    "acidente_consumo":     "Fato do produto/serviço com lesão à saúde — gravidade e sequelas elevam o quantum.",
    "cobranca_abusiva":     "Cobrança vexatória/abusiva (CDC arts. 42 e 71).",
    "outro":                "Hipótese genérica — pesquisar precedentes específicos do tema, tribunal e período.",
}


@router.get("/civel/ferramentas/calculo-dano-moral")
async def civ_dano_moral(
    tipo_caso: str = "negativacao_indevida",
    salarios_minimos_pedido: float = Query(0.0, ge=0, description="Opcional — pedido pretendido, em SM, apenas para contextualização"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Estruturação metodológica do dano moral — SEM valor sugerido automático:
    não há tabelamento legal (tarifação vedada) e o quantum é arbitrado caso a
    caso pelo método BIFÁSICO do STJ (REsp 1.152.541). A ferramenta orienta a
    pesquisa jurimétrica contextual em vez de faixas fixas.
    """
    if tipo_caso not in _TIPOS_DANO_MORAL:
        raise HTTPException(422, f"Tipo de caso inválido: '{tipo_caso}'. Use: {list(_TIPOS_DANO_MORAL)}")
    out: dict = {
        "tipo_caso": tipo_caso,
        "qualificador_descritivo": _TIPOS_DANO_MORAL[tipo_caso],
        "sem_valor_sugerido": True,
        "metodologia": {
            "metodo": "bifásico (STJ REsp 1.152.541)",
            "fase_1": "valor-BASE conforme o interesse jurídico lesado, a partir do GRUPO de "
                      "precedentes sobre o mesmo tema no tribunal competente",
            "fase_2": "ajuste do valor-base às circunstâncias do CASO CONCRETO (para mais ou para menos)",
        },
        "fatores": [
            "gravidade do fato e extensão do dano (CC art. 944)",
            "condições pessoais e econômicas do ofendido e do ofensor",
            "grau de culpa/dolo e reprovabilidade da conduta",
            "reincidência/contumácia do ofensor",
            "caráter pedagógico-punitivo sem enriquecimento sem causa",
            "duração e repercussão da lesão",
        ],
        "orientacao_jurimetrica": ("Pesquisar precedentes CONTEXTUAIS: mesmo tema e tribunal "
                                   "(TJMG/TRF/STJ), período recente (24-36 meses) e amostra "
                                   "razoável de acórdãos, anotando valores mínimo/mediano/máximo — "
                                   "use o módulo de jurisprudência/Deep Research do EJC. Faixas "
                                   "fixas descontextualizadas não são parâmetro válido."),
        "fontes": [
            "CC arts. 186 e 944 · CDC art. 6º VI",
            "STJ REsp 1.152.541 (método bifásico)",
            "STF RE 447.584 e ADPF 130 (vedação de tarifação)",
        ],
        "vigencia_regra": "Método bifásico consolidado no STJ — sem tabelamento legal",
        "versao_regra": _VERSAO_REGRA,
        "aviso": ("MINUTA — revisão humana obrigatória. O quantum é arbitrado judicialmente; "
                  "esta ferramenta NÃO sugere valor."),
    }
    if salarios_minimos_pedido > 0:
        out["quantum_pedido_contextual"] = {
            "pedido_em_sm": salarios_minimos_pedido,
            "pedido_em_reais": round(salarios_minimos_pedido * _sm_vigente(), 2),
            "nota": "Valor informado pelo usuário, apenas para contextualização do pedido — "
                    "não é sugestão da ferramenta.",
        }
    return out


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
@_com_regra("civ_partilha_divorcio")
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
@_com_regra("civ_rescisao_locacao")
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
@_com_regra("trab_verbas_rescisorias")
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
@_com_regra("adm_reajuste_contrato")
async def adm_reajuste_contrato(
    valor_original: float = Query(..., gt=0),
    indice_acumulado_pct: float = Query(..., ge=-50, le=1000),
    meses_contrato: int = Query(..., ge=0),
    indice_nome: str = Query(..., description="Índice PREVISTO no contrato (ex.: IPCA/IBGE, INCC/FGV)"),
    data_base: date = Query(..., description="Data-base: orçamento estimado ou apresentação da proposta"),
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Reajuste em sentido estrito pelo índice PREVISTO no contrato, respeitada a
    ANUALIDADE (Lei 14.133/2021 arts. 25 §7º e 92 §3º c/c Lei 10.192/2001 art. 2º
    §1º). Índice e variação acumulada são informados — não há índice default."""
    if not (indice_nome or "").strip():
        raise HTTPException(422, "Informe indice_nome — o índice previsto no contrato administrativo.")
    if valor_original <= 0:
        raise HTTPException(422, "valor_original deve ser maior que zero.")
    elegivel = meses_contrato >= 12
    reajuste = round(valor_original * indice_acumulado_pct / 100, 2)
    return {
        "elegivel_para_reajuste": elegivel,
        "motivo": ("Interregno mínimo de 12 meses cumprido"
                   if elegivel else
                   f"Anualidade NÃO cumprida — faltam {12 - meses_contrato} mês(es) "
                   f"(Lei 10.192/01 art. 2º §1º)"),
        "valor_original": valor_original,
        "indice_nome": indice_nome.strip(),
        "indice_acumulado_pct": indice_acumulado_pct,
        "data_base": data_base,
        "proximo_aniversario_data_base": _add_anos_data(data_base, 1),
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
@_com_regra("bancario_taxas_bacen")
async def bancario_taxas_bacen(cu: User = Depends(require_roles(_EQUIPE))):
    """Últimos valores oficiais SGS/BCB (SELIC meta, CDI, TR, IPCA-15).
    Fachada de bcb_service.painel_taxas — shape do TaxasBacenView (RamoBase.tsx)."""
    from app.services import bcb_service
    # Integração VIVA: indisponibilidade do SGS/BCB degrada graciosamente — a
    # ferramenta responde sem taxas e sinaliza a falha, em vez de estourar 500.
    try:
        taxas = await bcb_service.painel_taxas()
        indisponivel = None
    except Exception as exc:                      # noqa: BLE001 — degradação graciosa
        logger.warning("Painel de taxas BCB indisponível: %s", exc)
        taxas, indisponivel = {}, "Serviço SGS/BCB indisponível no momento da consulta."
    return {
        "taxas": taxas,
        "dados_disponiveis": bool(taxas),
        "indisponibilidade": indisponivel,
        "consultado_em": date.today(),
        "fonte": "Banco Central do Brasil — SGS (api.bcb.gov.br), séries 432 · 12 · 226 · 7478",
        "natureza_do_dado": ("Dado VIVO (não versionado): último valor divulgado pelo BCB na data "
                             "da consulta. Índices são REFERENCIAIS — para a tese de juros "
                             "abusivos use a taxa média da MODALIDADE e do mês do contrato."),
        "aviso": ("MINUTA — revisão humana obrigatória. Últimos valores oficiais divulgados pelo "
                  "BCB; para taxa média por modalidade de crédito, use o Comparador de Juros BACEN."),
    }


# ── Tributário: auto de infração — prazos e reduções ──────────────────────────
@router.get("/tributario/ferramentas/auto-infracao-prazos")
@_com_regra("trib_auto_infracao_prazos")
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
@_com_regra("trib_prescricao_decadencia")
async def trib_prescricao_decadencia(
    data_fato_gerador: date,
    tipo: Literal["lancamento", "homologacao", "credito_nao_constituido"] = "homologacao",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Decadência do direito de lançar (CTN 150 §4º/173 I) e prescrição da
    cobrança do crédito constituído (CTN 174) — sempre 5 anos, marcos distintos."""
    if tipo == "homologacao":
        limite = _add_anos_data(data_fato_gerador, 5)
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
        limite = _add_anos_data(marco, 5)
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
    limite = _add_anos_data(data_fato_gerador, 5)
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
        "vigencia_tabela": "Parâmetros consolidados em 2026-07 — PERT/REFIS encerrados (referência histórica); via atual: transação tributária (Lei 13.988/2020)",
        "fonte": m["rotulo"],
        "versao_regra": _VERSAO_REGRA,
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
        "vigencia_tabela": "Anexos I-V na redação da LC 155/2016 — vigentes desde 01/01/2018, sem alteração até 2026",
        "fonte": "LC 123/2006, Anexos I-V (red. LC 155/2016) · Res. CGSN 140/2018",
        "versao_regra": _VERSAO_REGRA,
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
@_com_regra("trib_regime_tributario")
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
@_com_regra("trib_reforma_tributaria")
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
        "estimativa_nao_vinculante": True,
        "estimativa_informativa_iva_pleno": {
            "aliquota_referencia_pct": 26.5,
            "carater": ("ESTIMATIVA NÃO VINCULANTE: a alíquota de referência será fixada por "
                        "resolução do Senado Federal (EC 132/2023 art. 156-A §1º); 26,5% é a "
                        "trava de avaliação da LC 214/2025, não alíquota em vigor."),
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
@_com_regra("amb_auto_infracao")
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
        "prescricao_administrativa": ("Pretensão punitiva: 5 anos da prática do ato ou, em "
                                      "infração permanente/continuada, do dia em que tiver cessado "
                                      "(Dec. 6.514/2008 art. 21 c/c Lei 9.873/99 art. 1º). "
                                      "Intercorrente: 3 anos de paralisação do processo "
                                      "(art. 21 §2º; Lei 9.873/99 art. 1º §1º)."),
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
@_com_regra("amb_crimes_ambientais")
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
@_com_regra("amb_tac")
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
@_com_regra("amb_licenciamento")
async def amb_licenciamento(
    uf: str = Query(..., min_length=2, max_length=2, description="UF do empreendimento"),
    fase: Literal["lp", "li", "lo"] = "lp",
    porte: Literal["pequeno", "medio", "grande"] = "medio",
    orgao: Optional[str] = Query(None, description="Órgão licenciador (IBAMA/SEMAD/municipal), se conhecido"),
    data_protocolo: Optional[date] = None,
    com_eia_rima: bool = False,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Fases, documentos mínimos e prazos do licenciamento ambiental — classes,
    modalidades e prazos CONCRETOS dependem da UF e da norma do órgão licenciador."""
    uf_norm = (uf or "").strip().upper()
    if len(uf_norm) != 2 or not uf_norm.isalpha():
        raise HTTPException(422, "UF inválida — informe a sigla de 2 letras (ex.: MG).")
    if fase not in _FASES_LICENCA:
        raise HTTPException(422, f"Fase inválida. Use: {list(_FASES_LICENCA)}")
    f = _FASES_LICENCA[fase]
    out: dict = {
        "uf": uf_norm,
        "orgao_licenciador_informado": orgao,
        "nota_localizacao": (f"Procedimento, classes e prazos CONCRETOS dependem da norma do "
                             f"ente licenciador em {uf_norm} (LC 140/2011 define a competência; "
                             "em MG: DN COPAM 217/2017 e SLA/SEMAD). Confira a norma do órgão."),
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
@_com_regra("amb_reserva_legal")
async def amb_reserva_legal(
    area_imovel_ha: float = Query(..., gt=0),
    uf: str = Query(..., min_length=2, max_length=2, description="UF do imóvel rural"),
    bioma: str = "cerrado",
    inscrito_car: bool = False,
    municipio: Optional[str] = None,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """Percentual e área de Reserva Legal por bioma/localização — percentuais do
    art. 12 da Lei 12.651/2012 como REGRA FEDERAL GERAL; o enquadramento concreto
    depende da localização (Amazônia Legal, zoneamento estadual)."""
    uf_norm = (uf or "").strip().upper()
    if len(uf_norm) != 2 or not uf_norm.isalpha():
        raise HTTPException(422, "UF inválida — informe a sigla de 2 letras (ex.: MG).")
    regra = _RESERVA_LEGAL_PCT.get(bioma)
    if not regra:
        raise HTTPException(422, f"Bioma inválido. Use: {list(_RESERVA_LEGAL_PCT)}")
    pct, desc = regra
    area_rl = round(area_imovel_ha * pct / 100, 4)
    out: dict = {
        "uf": uf_norm,
        "municipio": municipio,
        "nota_localizacao": ("Percentuais do art. 12 da LF 12.651/2012 são a REGRA FEDERAL "
                             "GERAL: os incisos de 80%/35% valem apenas DENTRO da Amazônia "
                             f"Legal; confirme se o imóvel em {uf_norm}"
                             + (f"/{municipio}" if municipio else "")
                             + " integra a Amazônia Legal, o ZEE estadual (reduções/ampliações "
                               "do art. 12 §§4º-5º e art. 13) e os módulos fiscais no CAR."),
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
