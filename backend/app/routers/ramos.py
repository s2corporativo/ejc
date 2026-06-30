# ── app/routers/ramos.py ──────────────────────────────────────────────────────
# Routers dos 6 ramos jurídicos especializados (além do Ambiental já existente).
# Padrão: CRUD + calculadoras/ferramentas específicas de cada área.
# Cada ramo tem: listar / criar / atualizar / remover (soft-delete) + ferramentas.
# HITL: todas as saídas de cálculo são minutas — revisão humana obrigatória.
from __future__ import annotations
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user, require_roles, ROLE_LEVEL
from app.core.ownership import verificar_acesso_caso, is_gestao
from app.models.user import User
from app.models.case import Case
from app.models.audit_log import criar_audit_log
from app.models.especializado import (
    EmpresarialCase, EmpresarialTipo, EmpresarialStatus,
    CivelCase, CivelTipo, CivelStatus,
    PenalCase, PenalTipo, PenalFase,
    TrabalhistaCase, TrabalhistaTipo, TrabalhistaFase,
    AdminCase, AdminTipo, AdminStatus,
    BancarioCase, BancarioTipo, BancarioStatus,
)
from app.services.deadline_calculator import (
    prazo_dias_uteis, prazo_dias_corridos, proximo_dia_util,
)

_EQUIPE = ["superadmin", "admin", "socio", "advogado", "advogado_auxiliar", "estagiario"]
_ADM    = ["superadmin", "admin", "socio"]
_CENT   = Decimal("0.01")

router = APIRouter(tags=["Ramos Jurídicos"])


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
# estes helpers. Ownership por caso (IDOR) e serialização sem _sa_instance_state.
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
    allowed = {c.key for c in Model.__table__.columns
               if c.key not in ("id", "case_id", "created_at")}
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
async def emp_atualizar(eid: str, body: dict, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(EmpresarialCase, "empresarial_cases", eid, body, db, cu)

@router.delete("/empresarial/{eid}")
async def emp_remover(eid: str, db: AsyncSession = Depends(get_db),
                      cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(EmpresarialCase, "empresarial_cases", eid, db, cu)

# ── Ferramentas Empresariais ──────────────────────────────────────────────────
@router.get("/empresarial/ferramentas/prazos-rj")
async def emp_prazos_rj(
    data_distribuicao: date,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazos críticos de recuperação judicial — Lei 11.101/2005.
    Base legal verificada: arts. 36, 53, 55, 61, 73.
    MINUTA — o advogado valida com o juízo da recuperação.
    """
    return {
        "data_distribuicao": data_distribuicao,
        "prazos": [
            {"evento": "Deferimento do processamento", "prazo": None,
             "descricao": "Juiz decide em até 5 dias (art. 52)", "base": "Lei 11.101/05 art. 52"},
            {"evento": "Apresentação do plano de recuperação",
             "data": prazo_dias_corridos(data_distribuicao, 60),
             "base": "Lei 11.101/05 art. 53", "tipo": "corridos"},
            {"evento": "Assembleia de credores delibera plano",
             "data": prazo_dias_corridos(data_distribuicao, 150),
             "base": "Lei 11.101/05 art. 56 + Súm. 555 STJ", "tipo": "corridos"},
            {"evento": "Prazo de supervisão judicial",
             "data": prazo_dias_corridos(data_distribuicao, 730),
             "base": "Lei 11.101/05 art. 61 §1º — 2 anos", "tipo": "corridos"},
        ],
        "aviso": "MINUTA de cálculo. Confirmar com o juízo e o administrador judicial.",
    }


@router.get("/empresarial/ferramentas/verificar-cade")
async def emp_cade(valor_faturamento_br: float, valor_operacao: float,
                   cu: User = Depends(require_roles(_EQUIPE))):
    """
    Verifica obrigatoriedade de notificação ao CADE.
    Lei 12.529/2011 art. 88: um dos grupos com fat. ≥ R$750M e outro ≥ R$75M no Brasil.
    """
    limiar_a = 750_000_000.00
    limiar_b = 75_000_000.00
    obrigatorio = valor_faturamento_br >= limiar_a
    return {
        "faturamento_informado": valor_faturamento_br,
        "valor_operacao": valor_operacao,
        "notificacao_obrigatoria": obrigatorio,
        "prazo_notificacao": "30 dias (art. 88 §2º Lei 12.529/11)" if obrigatorio else None,
        "taxa_cade_estimada": "R$ 85.000 (tabela CADE 2026)" if obrigatorio else "N/A",
        "base": "Lei 12.529/2011 art. 88 caput e §2º",
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
async def civ_atualizar(cid: str, body: dict, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(CivelCase, "civel_cases", cid, body, db, cu)

@router.delete("/civel/{cid}")
async def civ_remover(cid: str, db: AsyncSession = Depends(get_db),
                      cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(CivelCase, "civel_cases", cid, db, cu)

# ── Ferramentas Cível ─────────────────────────────────────────────────────────
@router.get("/civel/ferramentas/prazos-contestacao")
async def civ_prazo_contestacao(
    data_citacao: date,
    tipo: Literal["cpc","jec","fazenda_publica"] = "cpc",
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazo de contestação por rito.
    CPC art. 335: 15 dias úteis | JEC Lei 9.099/95 art. 30: 10 dias corridos
    Fazenda Pública CPC art. 183: prazo em quádruplo = 60 dias úteis (Súm. STJ 116 — só se autorizado).
    """
    if tipo == "jec":
        venc = prazo_dias_corridos(data_citacao, 10)
        base = "Lei 9.099/95 art. 30 — 10 dias corridos"
    elif tipo == "fazenda_publica":
        venc = prazo_dias_uteis(data_citacao, 30)   # em dobro (Lei 9.469/97 + CPC art. 183)
        base = "CPC art. 183 — 30 dias úteis (prazo em dobro)"
    else:
        venc = prazo_dias_uteis(data_citacao, 15)
        base = "CPC art. 335 — 15 dias úteis"
    return {"data_citacao": data_citacao, "tipo_rito": tipo,
            "vencimento": venc, "base_legal": base,
            "aviso": "MINUTA. Verifique suspensões e especificidades do juízo."}


@router.get("/civel/ferramentas/alimentos-calcular")
async def civ_alimentos(salario_devedor: float, percentual: float,
                        filhos: int = 1, cu: User = Depends(require_roles(_EQUIPE))):
    """
    Estimativa de alimentos proporcionais ao salário.
    Padrão STJ: 1/3 do salário para 1 filho; valores variam per case.
    Base: CC art. 1.694 §1º; Lei 5.478/68; Súm. STJ 277 (alimentos provisionais).
    MINUTA — cálculo de apoio, o juiz fixa.
    """
    valor = round(salario_devedor * (percentual / 100), 2)
    sm = 1518.00   # SM 2026
    return {
        "salario_devedor": salario_devedor,
        "percentual": percentual,
        "filhos": filhos,
        "valor_mensal": valor,
        "em_sm": round(valor / sm, 2),
        "base": "CC art. 1.694 §1º + Lei 5.478/68",
        "referencia": f"Padrão STJ: 1/3 a 30% p/ 1 filho (varia p/ caso)",
        "aviso": "MINUTA de estimativa. O magistrado fixa com base no binômio necessidade/possibilidade.",
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
async def pen_atualizar(pid: str, body: dict, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(PenalCase, "penal_cases", pid, body, db, cu)

@router.delete("/penal/{pid}")
async def pen_remover(pid: str, db: AsyncSession = Depends(get_db),
                      cu: User = Depends(require_roles(_ADM))):
    return await _crud_remover(PenalCase, "penal_cases", pid, db, cu)

# ── Ferramentas Penais ────────────────────────────────────────────────────────
@router.get("/penal/ferramentas/prazos-processuais")
async def pen_prazos(
    data_denuncia: date,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Prazos críticos do processo penal. Base: CPP.
    MINUTA — verificar suspensões e especificidades do caso.
    """
    return {
        "data_denuncia": data_denuncia,
        "prazos": [
            {"evento": "Resposta à acusação",
             "data": prazo_dias_uteis(data_denuncia, 10),
             "base": "CPP art. 396-A — 10 dias úteis"},
            {"evento": "Alegações finais (prazo máximo)",
             "data": None,
             "base": "CPP art. 403 — 10 dias após instrução (data depende do juízo)"},
            {"evento": "RESE (Recurso em Sentido Estrito)",
             "data": None,
             "base": "CPP art. 586 — 5 dias da decisão (marco da intimação)"},
            {"evento": "Apelação criminal",
             "data": None,
             "base": "CPP art. 593 §4º — 5 dias da publicação da sentença"},
            {"evento": "Embargos de declaração (criminal)",
             "data": None,
             "base": "CPP art. 620 — 2 dias"},
        ],
        "aviso": "MINUTA. Prazos a partir da intimação/publicação — verificar exato marco.",
    }


@router.get("/penal/ferramentas/verificar-anpp")
async def pen_anpp(
    pena_min_anos: float,
    confessou: bool,
    nao_violento: bool,
    primario: bool,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Verifica requisitos do Acordo de Não Persecução Penal (art. 28-A CPP).
    Inserido pelo Pacote Anticrime — Lei 13.964/2019.
    """
    requisitos = {
        "pena_minima_inferior_4_anos": pena_min_anos < 4,
        "crime_sem_violencia": nao_violento,
        "confissao_formal": confessou,
        "nao_reincidente": primario,
        "crime_sem_viol_dom_familiar": True,  # verificar per case
    }
    elegivel = all(requisitos.values())
    return {
        "elegivel_anpp": elegivel,
        "requisitos": requisitos,
        "base_legal": "CPP art. 28-A (red. Lei 13.964/2019)",
        "condicoes_possiveis": [
            "Reparação do dano (salvo impossibilidade)",
            "Renúncia a bens ou direitos (confisco)",
            "Prestação de serviço à comunidade",
            "Prestação pecuniária",
            "Cumprimento de outra condição fixada pelo MP",
        ] if elegivel else [],
        "aviso": "MINUTA. O MP propõe; o juízo homologa. Análise definitiva exige verificação dos antecedentes e tipo penal completo.",
    }


@router.get("/penal/ferramentas/prescricao-punitiva")
async def pen_prescricao(
    pena_maxima_anos: float,
    data_fato: date,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Verifica prescrição da pretensão punitiva em abstrato.
    Base: CP art. 109 (prazos) + art. 115 (redução p/ menores/maiores de 70).
    MINUTA — verificar causas interruptivas (CP art. 117).
    """
    # Tabela CP art. 109
    if pena_maxima_anos > 12:    prazo = 20
    elif pena_maxima_anos > 8:   prazo = 16
    elif pena_maxima_anos > 4:   prazo = 12
    elif pena_maxima_anos > 2:   prazo = 8
    elif pena_maxima_anos > 1:   prazo = 4
    else:                        prazo = 3
    data_prescricao = date(data_fato.year + prazo, data_fato.month, data_fato.day)
    prescrito = date.today() > data_prescricao
    return {
        "pena_maxima_anos": pena_maxima_anos,
        "data_fato": data_fato,
        "prazo_prescricional_anos": prazo,
        "data_prescricao_estimada": data_prescricao,
        "prescrito_em_abstrato": prescrito,
        "base_legal": "CP art. 109",
        "ressalvas": [
            "Causa interruptiva pela denúncia zera o prazo (CP art. 117 I)",
            "Redução pela metade se réu < 21 ou > 70 anos na data do fato/sentença (CP art. 115)",
            "Crimes imprescritíveis: racismo (CF art. 5º XLII) e ação de grupos armados (XLIV)",
        ],
        "aviso": "MINUTA em abstrato — não considera a prescrição retroativa (CP art. 110 §1º).",
    }


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
async def trab_atualizar(tid: str, body: dict, db: AsyncSession = Depends(get_db),
                         cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(TrabalhistaCase, "trabalhista_cases", tid, body, db, cu)

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
    return {
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
    }


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
    return result


@router.get("/trabalhista-esp/ferramentas/deposito-recursal")
async def trab_deposito(
    valor_condenacao: float,
    cu: User = Depends(require_roles(_EQUIPE)),
):
    """
    Calcula depósito recursal para Recurso Ordinário e Recurso de Revista.
    Tabela TST publicada anualmente. Valores 2026 (Ato TST GP 323/2025 — referência).
    MINUTA — confirmar teto vigente na data do recurso.
    """
    # Tetos vigentes 2026 (referência — confirmar portaria TST do ano)
    teto_ro  = 12_127.64   # RO
    teto_rr  = 24_255.28   # RR (dobro do RO)
    dep_ro  = min(valor_condenacao * 0.50, teto_ro)   # 50% até o teto, prática usual
    dep_rr  = min(valor_condenacao * 0.50, teto_rr)
    return {
        "valor_condenacao": valor_condenacao,
        "deposito_ro": round(dep_ro, 2),
        "deposito_rr": round(dep_rr, 2),
        "teto_ro_2026": teto_ro,
        "teto_rr_2026": teto_rr,
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
async def adm_atualizar(aid: str, body: dict, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(AdminCase, "admin_cases", aid, body, db, cu)

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
    return {
        "data_notificacao": data_notificacao,
        "prazo_recurso_1a_inst_jari": prazo_1a,
        "prazo_recurso_2a_inst_cetran": prazo_2a,
        "valor_multa_original": valor_multa,
        "valor_com_desconto_20pct": desconto_pagamento,
        "pontos_cnh": pontos_cnh,
        "risco_suspensao": pontos_cnh >= 20,   # CTB art. 261
        "base": "CTB arts. 281-284 + Res. CONTRAN 619/2016",
        "aviso": "MINUTA. Prazo 1ª instância conta da notificação da autuação; 2ª da decisão da JARI.",
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
async def ban_atualizar(bid: str, body: dict, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(require_roles(_EQUIPE))):
    return await _crud_atualizar(BancarioCase, "bancario_cases", bid, body, db, cu)

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
    sm = 1518.00  # SM 2026
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
             "prazo": f"15 dias após citação",
             "desc": "Defesa no mérito — adimplemento substancial, invalidade etc.",
             "base": "CPC art. 914 + STJ REsp 1.622.555"},
            {"estrategia": "Adimplemento substancial",
             "desc": "STJ entende que pagamento de > 80% afasta a BA — verificar percentual quitado",
             "base": "STJ REsp 1.622.555-MG (2017) + AgRg REsp 1.580.036"},
        ],
        "aviso": "MINUTA. Urgência máxima. A purga da mora deve ser realizada antes do prazo — contate o banco imediatamente.",
    }
