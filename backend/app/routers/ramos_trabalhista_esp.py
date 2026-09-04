# ── app/routers/ramos_trabalhista_esp.py ────────────────────────────────────────────────────
# Sub-router do domínio trabalhista-esp — extraído de ramos.py no fatiamento P5
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
from app.core.security import get_current_user, require_roles, require_roles_exact  # noqa: F401 (reexport p/ compat)
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
                     cu: User = Depends(require_roles_exact(_EQUIPE))):
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
                         cu: User = Depends(require_roles_exact(_EQUIPE))):
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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


