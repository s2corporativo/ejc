# ── app/routers/ramos_penal.py ────────────────────────────────────────────────────
# Sub-router do domínio penal — extraído de ramos.py no fatiamento P5
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
                    cu: User = Depends(require_roles_exact(_EQUIPE))):
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
                        cu: User = Depends(require_roles_exact(_EQUIPE))):
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Prescrição penal — implementação ÚNICA compartilhada com
    /penal/ferramentas/prescricao-penal (rota canônica). Ver _prescricao_penal_consolidada."""
    return _marcar_depreciada("/penal/ferramentas/prescricao-punitiva", _prescricao_penal_consolidada(
        rota_consultada="/penal/ferramentas/prescricao-punitiva",
        data_fato=data_fato, pena_maxima_anos=pena_maxima_anos,
        pena_concreta_anos=pena_concreta_anos, marcos_interruptivos=marcos_interruptivos,
        menor_21_na_data_fato=menor_21_na_data_fato, maior_70_na_sentenca=maior_70_na_sentenca,
    ), response)


