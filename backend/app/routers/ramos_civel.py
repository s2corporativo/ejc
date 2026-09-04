# ── app/routers/ramos_civel.py ────────────────────────────────────────────────────
# Sub-router do domínio civel — extraído de ramos.py no fatiamento P5
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
                    cu: User = Depends(require_roles_exact(_EQUIPE))):
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
                        cu: User = Depends(require_roles_exact(_EQUIPE))):
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
