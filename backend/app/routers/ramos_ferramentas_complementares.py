# ── app/routers/ramos_ferramentas_complementares.py ────────────────────────────────────────────────────
# Sub-router do domínio calculadoras transversais (cível/penal/trabalhista/admin/ — extraído de ramos.py no fatiamento P5
# (20/08/2026). Caminhos ABSOLUTOS: a montagem final é feita pelo agregador
# ramos.py sem prefixo adicional, preservando a paridade do snapshot de rotas.
# HITL: todas as saídas de cálculo são minutas — revisão humana obrigatória.

from __future__ import annotations  # noqa: F401 (reexport p/ compat)
import logging  # noqa: F401 (reexport p/ compat)
from calendar import monthrange  # noqa: F401 (reexport p/ compat)
from datetime import date, timedelta  # noqa: F401 (reexport p/ compat)
from decimal import Decimal  # noqa: F401 (reexport p/ compat)
from typing import Optional, Literal  # noqa: F401 (reexport p/ compat)

from fastapi import APIRouter, Depends, HTTPException, Query, Response  # noqa: F401 (reexport p/ compat)
from pydantic import BaseModel, field_validator  # noqa: F401 (reexport p/ compat)
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: F401 (reexport p/ compat)

from app.core.database import get_db  # noqa: F401 (reexport p/ compat)
from app.core.security import get_current_user, require_roles, require_roles_exact  # noqa: F401 (reexport p/ compat)
from app.models.user import User  # noqa: F401 (reexport p/ compat)
from app.models.case import Case  # noqa: F401 (reexport p/ compat)
from app.models.audit_log import criar_audit_log  # noqa: F401 (reexport p/ compat)
from app.core.ownership import verificar_acesso_caso, is_gestao  # noqa: F401 (reexport p/ compat)
from app.models.especializado import (  # noqa: F401 (reexport p/ compat)
    CivelCase, PenalCase, TrabalhistaCase, AdminCase, BancarioCase,
    CivelTipo, PenalTipo, PenalFase, TrabalhistaTipo, TrabalhistaFase,
    AdminTipo, AdminStatus, BancarioTipo, BancarioStatus,
)
from app.core.config import get_settings  # noqa: F401 (reexport p/ compat)
from app.routers.ramos_comum import (  # noqa: F401 (reexport p/ compat)
    logger,  # logger de módulo; handlers o usam diretamente
    _EQUIPE, _ADM, _CENT, _parse_sim_nao, _SIM_NAO,
    _VERSAO_REGRA, VERSAO_REGRA_ATUAL, _marcar_depreciada,
    _REGRAS_FERRAMENTAS, _com_regra, _get_case,
    _add_anos_data, _prescricao_prazo_anos, _prescricao_penal_consolidada,
    _sm_vigente, _classificar_taxa_vs_media,
    _ultimo_dia_do_mes, _add_meses_data,
    _atravessa_recesso, _SUSPENSAO_LEGAL, _info_suspensao,
    _prazo_util_com_recesso, _prazo_corrido_com_recesso,
)
from app.services.homologacao_ferramentas import (  # noqa: F401 (reexport p/ compat)
    FERRAMENTAS_BLOQUEADAS,
    FERRAMENTAS_NAO_HOMOLOGADAS,
    normalizar_caminho_ferramenta,
    selo_homologacao as _selo_homologacao,
)
from app.schemas.areas_atuacao import (  # noqa: F401 (reexport p/ compat)
    CivelUpdate, PenalUpdate, TrabalhistaUpdate, AdminUpdate, BancarioUpdate,
)
from app.services.deadline_calculator import (  # noqa: F401 (reexport p/ compat)
    prazo_dias_uteis, prazo_dias_corridos, prazo_defesa_ambiental, proximo_dia_util,
)

router = APIRouter(tags=["Áreas de Atuação"])

# ── Cível: prescrição/decadência do consumidor (CDC arts. 26-27) ─────────────
@router.get("/civel/ferramentas/prescricao-consumidor")
@_com_regra("civ_prescricao_consumidor")
async def civ_prescricao_consumidor(
    data_fato: date,
    tipo_vicio: Literal["fato_produto", "fato_servico",
                        "servico_ou_produto", "cobranca_indevida"] = "fato_produto",
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
async def bancario_taxas_bacen(cu: User = Depends(require_roles_exact(_EQUIPE))):
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    modalidade: str = "parcelamento_comum",
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    "2027": "CBS cobrada com alíquota reduzida em 0,1 ponto percentual (ainda NÃO plena) "
            "substitui PIS/COFINS (extintos); Imposto Seletivo (IS) entra em vigor; IPI "
            "zerado, exceto para produtos cuja industrialização seja também incentivada na "
            "Zona Franca de Manaus (mantido para preservar a competitividade da ZFM, mesmo "
            "se o produto concorrente for fabricado fora dela); IBS mantido em 0,1%. Sem "
            "redução de ICMS/ISS.",
    "2028": "Continuidade do regime de 2027: CBS ainda com alíquota reduzida em 0,1 ponto "
            "percentual (não plena); IBS mantido em 0,1%; IS e extinção de PIS/COFINS seguem "
            "vigentes. Ainda sem redução de ICMS/ISS — a transição proporcional só começa em 2029.",
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
    ano_analise: Literal["2026", "2027", "2028", "2029", "2030", "2031", "2032", "2033"] = "2026",
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
                 "serão fixadas por resolução do Senado. Regimes específicos (financeiro, "
                 "imobiliário, combustíveis, cesta básica e outros da LC 214/2025) têm regras "
                 "próprias que podem divergir deste cronograma geral — não cobertos por esta "
                 "estimativa. Revisão humana obrigatória.",
    }


# ── Ambiental: auto de infração (Dec. 6.514/2008) ─────────────────────────────
@router.get("/ambiental/ferramentas/auto-infracao-ambiental")
@_com_regra("amb_auto_infracao")
async def amb_auto_infracao(
    data_ciencia: date,
    valor_multa: float = Query(0.0, ge=0),
    tipo_infracao: str = "degradacao",
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
