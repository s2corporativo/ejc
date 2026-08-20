# ── app/routers/ramos_admin_esp.py ────────────────────────────────────────────────────
# Sub-router do domínio admin-esp — extraído de ramos.py no fatiamento P5
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
            # Lei 9.784/99 art. 59: recurso administrativo de 10 dias ÚTEIS.
            # PRZ-03 (issue #1080): fora do Poder Judiciário — sem recesso
            # forense 20/12–06/01 (Lei 5.010/1966 art. 62, I; Res. CNJ 241/2016).
            data["prazo_recurso_1a_inst"] = prazo_dias_uteis(dn, 10, forense=False)
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

