# ── app/routers/ramos_vitrine.py ────────────────────────────────────────────────────
# Sub-router do domínio vitrine transversal (consumidor/família/imobiliário/previdenciário/LGPD/trânsito/tributário/bancário juros) — extraído de ramos.py no fatiamento P5
# (20/08/2026). Caminhos ABSOLUTOS: a montagem final é feita pelo agregador
# ramos.py sem prefixo adicional, preservando a paridade do snapshot de rotas.
# HITL: todas as saídas de cálculo são minutas — revisão humana obrigatória.

from __future__ import annotations  # noqa: F401 (reexport p/ compat)
from datetime import date, timedelta  # noqa: F401 (reexport p/ compat)
from decimal import Decimal  # noqa: F401 (reexport p/ compat)
from typing import Optional, Literal  # noqa: F401 (reexport p/ compat)

from fastapi import APIRouter, Depends, HTTPException, Query, Response  # noqa: F401 (reexport p/ compat)
from pydantic import BaseModel  # noqa: F401 (reexport p/ compat)

from app.core.config import get_settings  # noqa: F401 (reexport p/ compat)
from app.core.security import require_roles_exact  # noqa: F401 (reexport p/ compat)
from app.models.user import User  # noqa: F401 (reexport p/ compat)
from app.services.deadline_calculator import (  # noqa: F401 (reexport p/ compat)
    prazo_dias_uteis, prazo_dias_corridos, proximo_dia_util,
)
from app.routers.ramos_comum import (  # noqa: F401 (reexport p/ compat)
    logger,  # logger de módulo; handlers o usam diretamente
    _EQUIPE, _parse_sim_nao, _VERSAO_REGRA, VERSAO_REGRA_ATUAL,
    _marcar_depreciada, _com_regra,
    _add_anos_data, _sm_vigente,
    _ultimo_dia_do_mes, _add_meses_data,
    _parse_fracoes, _meses_para_anos_meses,
    _prescricao_penal_consolidada, _prazo_util_com_recesso,
)
from app.services.homologacao_ferramentas import (  # noqa: F401 (reexport p/ compat)
    FERRAMENTAS_BLOQUEADAS,
    FERRAMENTAS_NAO_HOMOLOGADAS,
    normalizar_caminho_ferramenta,
    selo_homologacao as _selo_homologacao,
)
router = APIRouter(tags=["Áreas de Atuação"])


# ── Ferramentas Consumidor ────────────────────────────────────────────────────
@router.get("/consumidor/ferramentas/devolucao-dobro")
async def consumidor_devolucao_dobro(
    valor_cobrado_indevidamente: float = Query(..., gt=0),
    houve_pagamento: str = Query(..., description="sim | nao — a repetição pressupõe PAGAMENTO"),
    cobranca_contraria_boa_fe_objetiva: str = Query(..., description="sim | nao"),
    engano_justificavel: str = Query(..., description="sim | nao"),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    # Súm. 309 STJ + CPC art. 528 §7º: são as TRÊS PRESTAÇÕES anteriores ao
    # ajuizamento — contagem por PARCELA, não por intervalo de calendário. O
    # corte por "-3 meses" errava nos dois sentidos: com vencimento dia 05 e
    # ajuizamento em 31/07, a parcela de 05/04 (a terceira anterior, coberta)
    # caía em expropriação; e em cronogramas não mensais (quinzenal, trimestral)
    # a janela de 3 meses captura mais ou menos de 3 prestações.
    vencidas = [p for p in parcelas if p <= data_ajuizamento_execucao]
    vincendas = [p for p in parcelas if p > data_ajuizamento_execucao]
    tres_ultimas = vencidas[-3:]                 # as 3 mais recentes ANTES do ajuizamento
    rito_prisao = sorted(tres_ultimas + vincendas)
    rito_expropriacao = vencidas[:-3]            # as demais, mais antigas
    out: dict = {
        "data_ajuizamento_execucao": data_ajuizamento_execucao,
        "criterio_selecao": ("as 3 PRESTAÇÕES vencidas mais recentes na data do ajuizamento "
                             "(Súm. 309 STJ), somadas às vincendas — não é janela de 3 meses"),
        "parcelas_vencidas_no_ajuizamento": len(vencidas),
        "parcelas_vincendas": len(vincendas),
        "parcelas_rito_prisao": rito_prisao,
        "parcelas_rito_expropriacao": rito_expropriacao,
        "descricao_ritos": {
            "prisao": ("As 3 últimas prestações vencidas antes do ajuizamento + as que "
                       "vencerem no curso do processo — cumprimento sob pena de prisão "
                       "(CPC art. 528 §§3º e 7º; Súm. 309 STJ)."),
            "expropriacao": ("Prestações anteriores a essas três — execução por penhora/"
                             "expropriação (CPC art. 528 §8º c/c art. 831)."),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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



@router.get("/penal/ferramentas/dosimetria")
async def penal_dosimetria(
    pena_minima_meses: int = Query(..., gt=0, description="Pena mínima cominada, em meses"),
    pena_maxima_meses: int = Query(..., gt=0, description="Pena máxima cominada, em meses"),
    circunstancias_judiciais_desfavoraveis: int = 0,
    n_agravantes: int = 0,
    n_atenuantes: int = 0,
    causas_aumento: Optional[str] = None,      # frações, ex.: "1/3,1/6"
    causas_diminuicao: Optional[str] = None,   # frações, ex.: "1/2,1/6"
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
async def trabalhista_horas_extras(
    salario_mensal: float = Query(..., gt=0),
    horas_extras_mes: float = Query(..., ge=0),
    divisor: int = Query(..., description="Divisor de horas: 220 (44h/sem), 200 (40h — Súm. 431 TST), 180 (36h) ou o da norma coletiva"),
    percentual_he: float = 50.0,
    incluir_dsr: str = Query(..., description="sim | nao — DSR de 1/6 sobre as HE"),
    incluir_reflexo_fgts: str = Query(..., description="sim | nao — FGTS de 8% sobre HE+DSR"),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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


@router.get("/trabalhista/ferramentas/horas-extras", deprecated=True)
async def trabalhista_horas_extras_alias(
    response: Response,
    salario_mensal: float = Query(..., gt=0),
    horas_extras_mes: float = Query(..., ge=0),
    divisor: int = Query(..., description="Divisor de horas: 220 (44h/sem), 200 (40h — Súm. 431 TST), 180 (36h) ou o da norma coletiva"),
    percentual_he: float = 50.0,
    incluir_dsr: str = Query(..., description="sim | nao — DSR de 1/6 sobre as HE"),
    incluir_reflexo_fgts: str = Query(..., description="sim | nao — FGTS de 8% sobre HE+DSR"),
    cu: User = Depends(require_roles_exact(_EQUIPE)),
):
    """Alias DEPRECIADO de /trabalhista-esp/ferramentas/horas-extras.

    Handler próprio (e não decorator empilhado) porque o alias precisa do
    ``Response`` para emitir os cabeçalhos RFC 8594 — empilhado, o mesmo handler
    servia os dois paths sem distinguir a origem e o alias saía sem
    ``Deprecation``/``Sunset``/``Link``, diferente das outras duas duplicatas.
    O cálculo é o da rota canônica: delega, não duplica.
    """
    return _marcar_depreciada(
        "/trabalhista/ferramentas/horas-extras",
        await trabalhista_horas_extras(
            salario_mensal=salario_mensal, horas_extras_mes=horas_extras_mes,
            divisor=divisor, percentual_he=percentual_he, incluir_dsr=incluir_dsr,
            incluir_reflexo_fgts=incluir_reflexo_fgts, cu=cu,
        ),
        response,
    )



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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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
    cu: User = Depends(require_roles_exact(_EQUIPE)),
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

