# ── app/routers/ramos_comum.py ──────────────────────────────────────────────
# Bloco COMPARTILHADO extraído de ramos.py no fatiamento P5 (20/08/2026).
# Imports, constantes, validadores, helpers RFC 8594, tabela única de
# metadados de regra (_REGRAS_FERRAMENTAS), decorator @_com_regra, helpers
# de ownership/CRUD e o logger. Os handlers vivem nos sub-routers ramos_*.py
# — nenhum path de rota mudou (paths absolutos).

# ── app/routers/ramos.py ──────────────────────────────────────────────────────
# Routers dos 6 ramos jurídicos especializados (além do Ambiental já existente).
# Padrão: CRUD + calculadoras/ferramentas específicas de cada área.
# Cada ramo tem: listar / criar / atualizar / remover (soft-delete) + ferramentas.
# HITL: todas as saídas de cálculo são minutas — revisão humana obrigatória.
from __future__ import annotations  # noqa: F401 (reexport p/ compat)
import logging  # noqa: F401 (reexport p/ compat)
import re  # noqa: F401 (reexport p/ compat)
from calendar import monthrange  # noqa: F401 (reexport p/ compat)
from datetime import date, timedelta  # noqa: F401 (reexport p/ compat)
from functools import wraps  # noqa: F401 (reexport p/ compat)
from decimal import Decimal  # noqa: F401 (reexport p/ compat)
from uuid import uuid4  # noqa: F401 (reexport p/ compat)
from typing import Optional, Literal  # noqa: F401 (reexport p/ compat)

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

_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]
_ADM    = ["superadmin", "admin", "socio"]
_CENT   = Decimal("0.01")

# ── Tetos do depósito recursal trabalhista (CLT art. 899 §§1º-4º) ─────────────
# Tabela VERSIONADA por período de vigência. ATUALIZAÇÃO ANUAL OBRIGATÓRIA: o TST
# reajusta os tetos pelo IPCA-E e publica novo Ato de GP com vigência em agosto.
# Para atualizar: ADICIONE uma nova faixa no INÍCIO da lista (mais recente
# primeiro) e feche o `fim` da faixa anterior — nunca edite valores históricos.
TETOS_DEPOSITO_RECURSAL: list[dict] = [
    # ATENÇÃO — ATUALIZAÇÃO ANUAL OBRIGATÓRIA: o TST reajusta os limites pela
    # variação acumulada do INPC/IBGE (julho a junho) e publica um Ato SEGJUD.GP
    # em meados de julho, com vigência a partir de 1º de agosto. Ao sair o Ato
    # novo: feche o `fim` da faixa vigente em 31/07 e acrescente a nova faixa
    # NO TOPO da lista. Conferir sempre em https://www.tst.jus.br/valores-vigentes
    # (histórico em https://www.tst.jus.br/historico-valores).
    # Ordem: da mais recente para a mais antiga.
    {"rotulo": "2026-2027",
     "inicio": date(2026, 8, 1), "fim": None,   # None = vigente (em aberto)
     "ro": 14_411.57, "rr": 28_823.14,
     "fonte": "Ato SEGJUD.GP 381/2026 (INPC/IBGE jul-2025 a jun-2026)"},
    {"rotulo": "2025-2026",
     "inicio": date(2025, 8, 1), "fim": date(2026, 7, 31),
     "ro": 13_813.83, "rr": 27_627.66,
     "fonte": "Ato SEGJUD.GP 391/2025 (INPC/IBGE jul-2024 a jun-2025)"},
    {"rotulo": "2024-2025",
     "inicio": date(2024, 8, 1), "fim": date(2025, 7, 31),
     "ro": 13_133.46, "rr": 26_266.92,
     "fonte": "Ato SEGJUD.GP 366/2024"},
    {"rotulo": "2023-2024",
     "inicio": date(2023, 8, 1), "fim": date(2024, 7, 31),
     "ro": 12_665.14, "rr": 25_330.28,
     "fonte": "Ato SEGJUD.GP 414/2023"},
    {"rotulo": "2022-2023",
     "inicio": date(2022, 8, 1), "fim": date(2023, 7, 31),
     "ro": 12_296.38, "rr": 24_592.76,
     "fonte": "Ato SEGJUD.GP 430/2022"},
]

# NÃO reintroduzir constantes TETO_DEPOSITO_RO/RR apontando para a faixa mais
# recente da lista: a faixa nova é cadastrada ANTES de entrar em vigor (o Ato sai
# em julho e vale a partir de 1º de agosto), então "mais recente" ≠ "vigente" por
# várias semanas ao ano. Use sempre _teto_deposito_para(<data do recurso>).
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

# Alias público (Onda 3, Issue #702): o gate de proveniência do demonstrativo
# de cálculo (routers/peca_geracao.py) compara o `versao_regra` declarado
# pelo cliente com a versão REALMENTE vigente — um demonstrativo que alega
# uma versão diferente da atual não pode ter saído de uma execução real da
# ferramenta (é o sinal mínimo de forjamento que o piso de proveniência
# consegue detectar sem recalcular no servidor). Ver PR da Issue #702.
VERSAO_REGRA_ATUAL: str = _VERSAO_REGRA

# ── Rotas DUPLICADAS mantidas por compatibilidade (Onda 3 §4.5) ──────────────
# Cada uma delega à implementação da rota canônica. Aqui elas passam a se
# ANUNCIAR como depreciadas: `deprecated=True` no decorator (visível no
# OpenAPI/Swagger) + cabeçalhos RFC 8594 (`Deprecation`/`Sunset`/`Link`) e
# campos na resposta. A remoção física é da Onda 5 e depende da telemetria de
# uso (services/route_usage.py) apontar 30-60 dias sem chamadas.
# Data-alvo do desligamento anunciado nos cabeçalhos RFC 8594. DEVE SER FUTURA:
# um Sunset no passado diz ao cliente que a rota já saiu, enquanto ela segue no
# ar aguardando a janela de telemetria — anúncio incoerente e ignorado.
# REVISAR quando a telemetria (services/route_usage.py) autorizar a remoção:
# a data deve acompanhar a janela real de 30-60 dias de uso zero, não ficar fixa.
_SUNSET_DUPLICATAS = "Thu, 31 Dec 2026 23:59:59 GMT"
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
    """Serializa modelo ORM sem estado SQLAlchemy nem colunas internas/sensíveis."""
    internas = set(getattr(obj, "__api_internal_columns__", ()))
    return {
        c.key: getattr(obj, c.key)
        for c in obj.__table__.columns
        if c.key not in internas
    }


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


# Colunas de CONTROLE nunca editáveis via PATCH (auditoria 2026-07-26, AI-121:
# derivar a whitelist de TODAS as colunas da tabela permitia mass assignment de
# soft-delete/timestamps).
_COLUNAS_CONTROLE = frozenset({"id", "case_id", "created_at", "updated_at", "deleted_at"})


async def _crud_atualizar(Model, table: str, item_id: str, body: dict,
                          db: AsyncSession, cu: User) -> dict:
    obj = (await db.execute(
        select(Model).where(Model.id == item_id, Model.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not obj:
        raise HTTPException(404, "Registro não encontrado")
    # Ownership por caso (IDOR): só edita registros de casos a que tem acesso.
    await verificar_acesso_caso(db, cu, obj.case_id)
    # AI-121 (auditoria 2026-07-26): TODA coluna de negócio é editável, mas
    # colunas de CONTROLE (id/case_id/timestamps/soft-delete) são bloqueadas e
    # campo desconhecido/bloqueado responde 422 — nunca ignorado em silêncio
    # (um PATCH que "não pega" esconderia perda de dado de desfecho/prazo).
    internas = set(getattr(Model, "__api_internal_columns__", ()))
    editaveis = (
        {c.key for c in Model.__table__.columns}
        - _COLUNAS_CONTROLE
        - internas
    )
    rejeitados = sorted(k for k in body if k not in editaveis)
    if rejeitados:
        raise HTTPException(
            422, f"Campos não editáveis neste registro: {', '.join(rejeitados)}")
    # NB: a versão que veio do #493 calculava um set `allowed` e não o
    # usava — o loop abaixo itera `body` direto. Aquela "defesa em
    # profundidade" era código morto; esta rejeita de fato, com 422.
    for k, v in body.items():
        setattr(obj, k, v)
    await criar_audit_log(db, cu.id, cu.role.value, "UPDATE", table, item_id)
    await db.commit()
    # Colunas com onupdate/server_default (ex.: updated_at) podem ficar
    # expiradas após o flush mesmo com expire_on_commit=False. Recarregar de
    # forma assíncrona evita lazy IO síncrono em _serialize (MissingGreenlet).
    await db.refresh(obj)
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




# ── Helpers cross-domínio (movidos do corpo original) ──────────────────────

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




# Cada endpoint abaixo corresponde EXATAMENTE a um card declarado em
# frontend/src/pages/ramos/ramosConfig.ts (mesmo path e mesmos parâmetros).
# O teste tests/test_calculadoras_ramos.py trava esse contrato no CI.
# ════════════════════════════════════════════════════════════════════════════
def _sm_vigente() -> float:
    """Salário mínimo VIGENTE (settings.SALARIO_MINIMO_BRL — decreto anual)."""
    return float(get_settings().SALARIO_MINIMO_BRL)




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



