# ── app/services/ambiental/estrategia_auto.py ────────────────────────────────
# Simulador de Estratégia do Auto de Infração ambiental — motor DETERMINÍSTICO
# de decisão (v1 STATELESS: sem IA, sem persistência, sem migration).
#
# Compara, com números auditáveis, os caminhos reais que o advogado pondera
# diante de um auto ambiental federal (Lei 9.605/98 · Decreto 6.514/2008):
#   1) pagar_a_vista     — desconto de 30% (Dec. 6.514 art. 4º §1º);
#   2) converter_servicos — conversão em serviços de recuperação (arts. 139-148,
#      red. Dec. 9.179/2017): 60% até a defesa / 35% após;
#   3) defender          — valor ESPERADO = multa × prob. de manutenção informada
#      pelo advogado, com faixa de sensibilidade ±15 p.p.;
#   4) prescricao        — tese preliminar quinquenal (Lei 9.873/99 art. 1º).
#
# PRINCÍPIO DE HONESTIDADE: NÃO inventa faixas de valor de multa do Decreto
# 6.514 (variam por artigo). Trabalha SÓ com: matemática pura sobre o valor
# informado, datas/prazos e as constantes legais já vetadas no endpoint
# `amb_auto_infracao` (routers/ramos.py). Toda saída é ESTIMATIVA/MINUTA (HITL);
# as probabilidades são do ADVOGADO, não do sistema.
#
# Aritmética em Decimal (padrão de services/calc/cet.py); reusa o utilitário
# canônico prazo_defesa_ambiental (services/deadline_calculator.py).
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services.deadline_calculator import prazo_defesa_ambiental

_CENT = Decimal("0.01")

# Constantes legais (as MESMAS já vetadas em amb_auto_infracao):
_DESCONTO_A_VISTA = Decimal("0.30")            # Dec. 6.514 art. 4º §1º
_CONVERSAO_ANTES = Decimal("0.60")             # arts. 139-148, red. Dec. 9.179/2017
_CONVERSAO_APOS = Decimal("0.35")              # idem, após a defesa
_SENSIBILIDADE_PP = Decimal("15")              # ±15 p.p. na prob. de manutenção
_PRESCRICAO_ANOS = 5                           # Lei 9.873/99 art. 1º (quinquenal)

BASE_LEGAL_GERAL = (
    "Lei 9.605/98 arts. 14-15 e 70-76 · Decreto 6.514/2008 arts. 4º, 95-A, 113, "
    "122, 127 e 139-148 (red. Dec. 9.179/2017) · Lei 9.873/99 art. 1º e §1º."
)

AVISO_HITL = (
    "ESTIMATIVA / MINUTA — REVISÃO HUMANA OBRIGATÓRIA. Os valores são matemática "
    "pura sobre a multa informada; nenhuma faixa do Decreto 6.514 foi presumida. "
    "A probabilidade de manutenção do auto é ESTIMATIVA DO ADVOGADO, não do "
    "sistema. Os percentuais de desconto/conversão seguem o rito FEDERAL (Dec. "
    "6.514); órgãos ESTADUAIS/municipais têm ritos próprios — conferir a lei do "
    "órgão autuador indicada no auto."
)


def _dec(v) -> Decimal:
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _q(v: Decimal) -> Decimal:
    """Quantiza a 2 casas (centavos), ROUND_HALF_UP — padrão monetário do EJC."""
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def _moeda(v: Decimal) -> str:
    """R$ 10.000,00 — formatação pt-BR para a memória de cálculo."""
    from app.utils.format import formatar_brl  # #41: formatador BRL único
    return formatar_brl(v)


def simular_estrategia(
    valor_multa: Decimal,
    data_ciencia: date,
    fase: str,
    prob_manutencao_pct: Decimal,
    custo_recuperacao_estimado: Decimal | None = None,
    data_infracao: date | None = None,
    hoje: date | None = None,
) -> dict:
    """
    Simula os 4 caminhos diante de um auto de infração ambiental e devolve a
    consolidação com a recomendação DETERMINÍSTICA (menor desembolso entre os
    cenários aplicáveis; prescrição aplicável vence sempre).

    Args:
      valor_multa: valor da multa informado no auto (Decimal, ≥ 0).
      data_ciencia: data de ciência da autuação (dispara o prazo de defesa).
      fase: "antes_defesa" | "apos_defesa" — muda o teto de conversão.
      prob_manutencao_pct: prob. (0-100) de o auto ser mantido, estimada pelo
        advogado — usada no valor esperado da defesa.
      custo_recuperacao_estimado: custo estimado da recuperação ambiental (só
        explicita que a parte convertida vira investimento; não subtrai nada).
      data_infracao: data do fato (para a tese de prescrição quinquenal).
      hoje: injeção de relógio (testes); default date.today().
    """
    valor = _dec(valor_multa)
    fase = fase if fase in ("antes_defesa", "apos_defesa") else "antes_defesa"
    prob = _dec(prob_manutencao_pct)
    if prob < 0:
        prob = Decimal("0")
    if prob > 100:
        prob = Decimal("100")
    hoje = hoje or date.today()

    cenarios = [
        _cenario_pagar_a_vista(valor),
        _cenario_converter(valor, fase, custo_recuperacao_estimado),
        _cenario_defender(valor, prob, data_ciencia),
        _cenario_prescricao(data_infracao, hoje),
    ]

    recomendacao = _recomendar(cenarios)

    return {
        "cenarios": cenarios,
        "recomendacao": recomendacao,
        "aviso_hitl": AVISO_HITL,
        "base_legal_geral": BASE_LEGAL_GERAL,
    }


# ── Cenário 1: pagamento à vista com desconto ─────────────────────────────────
def _cenario_pagar_a_vista(valor: Decimal) -> dict:
    fator = Decimal("1") - _DESCONTO_A_VISTA  # 0,70
    desembolso = _q(valor * fator)
    return {
        "id": "pagar_a_vista",
        "titulo": "Pagamento à vista com desconto de 30%",
        "base_legal": "Decreto 6.514/2008, art. 4º, §1º.",
        "aplicavel": True,
        "desembolso_estimado": desembolso,
        "memoria_calculo": [
            f"Valor da multa informado: {_moeda(valor)}.",
            f"Desconto legal de 30% (art. 4º, §1º): {_moeda(valor)} × 0,70.",
            f"Desembolso à vista: {_moeda(desembolso)}.",
        ],
        "observacoes": [
            "O pagamento no prazo de defesa implica RENÚNCIA à defesa e o "
            "reconhecimento da infração (encerra a discussão administrativa).",
        ],
    }


# ── Cenário 2: conversão da multa em serviços de recuperação ──────────────────
def _cenario_converter(
    valor: Decimal, fase: str, custo_recuperacao: Decimal | None,
) -> dict:
    pct = _CONVERSAO_ANTES if fase == "antes_defesa" else _CONVERSAO_APOS
    convertida = _q(valor * pct)
    desembolso = _q(valor - convertida)  # parte que continua sendo DINHEIRO
    rotulo_fase = ("até o oferecimento da defesa"
                   if fase == "antes_defesa" else "após a defesa, até as "
                   "alegações finais")
    pct_int = int(pct * 100)
    memoria = [
        f"Valor da multa informado: {_moeda(valor)}.",
        f"Fase: {rotulo_fase} → teto de conversão de {pct_int}% "
        f"(arts. 139-148, red. Dec. 9.179/2017).",
        f"Parcela convertida em serviços: {_moeda(valor)} × 0,{pct_int} = "
        f"{_moeda(convertida)}.",
        f"Desembolso em DINHEIRO (parte não convertida): {_moeda(valor)} − "
        f"{_moeda(convertida)} = {_moeda(desembolso)}.",
    ]
    observacoes = [
        "A conversão substitui a parcela cabível por serviços de "
        "preservação/recuperação ambiental — não é dinheiro pago ao órgão.",
    ]
    if custo_recuperacao is not None:
        custo = _dec(custo_recuperacao)
        memoria.append(
            f"Parcela convertida ({_moeda(convertida)}) vira INVESTIMENTO na "
            f"própria recuperação; custo de recuperação estimado pelo cliente: "
            f"{_moeda(custo)}."
        )
        observacoes.append(
            "O custo de recuperação é informado pelo cliente e NÃO foi abatido "
            "do desembolso — serve para o advogado comparar o esforço real da "
            "conversão com a parcela convertida."
        )
    return {
        "id": "converter_servicos",
        "titulo": f"Conversão de {pct_int}% da multa em serviços de recuperação",
        "base_legal": "Decreto 6.514/2008, arts. 139-148 (red. Dec. 9.179/2017).",
        "aplicavel": True,
        "desembolso_estimado": desembolso,
        "memoria_calculo": memoria,
        "observacoes": observacoes,
    }


# ── Cenário 3: defender (valor esperado + faixa de sensibilidade) ─────────────
def _cenario_defender(valor: Decimal, prob: Decimal, data_ciencia: date) -> dict:
    def esperado(p: Decimal) -> Decimal:
        return _q(valor * (p / Decimal("100")))

    prob_baixa = max(Decimal("0"), prob - _SENSIBILIDADE_PP)
    prob_alta = min(Decimal("100"), prob + _SENSIBILIDADE_PP)
    valor_esperado = esperado(prob)
    piso = esperado(prob_baixa)
    teto = esperado(prob_alta)

    prazos = prazo_defesa_ambiental(data_ciencia)  # utilitário canônico do EJC

    return {
        "id": "defender",
        "titulo": "Apresentar defesa administrativa",
        "base_legal": "Decreto 6.514/2008, arts. 113, 122 e 127.",
        "aplicavel": True,
        "desembolso_estimado": valor_esperado,
        "memoria_calculo": [
            f"Valor da multa informado: {_moeda(valor)}.",
            f"Probabilidade de manutenção do auto (estimativa do advogado): "
            f"{prob.normalize()}%.",
            f"Valor ESPERADO = {_moeda(valor)} × {prob.normalize()}% = "
            f"{_moeda(valor_esperado)}.",
            f"Faixa de sensibilidade (±15 p.p.): de {prob_baixa.normalize()}% a "
            f"{prob_alta.normalize()}% → entre {_moeda(piso)} e {_moeda(teto)}.",
        ],
        "observacoes": [
            f"Prazo de defesa: 20 dias da ciência (art. 113). Vencimento legal "
            f"em {prazos['data_legal'].strftime('%d/%m/%Y')}; protocolo interno "
            f"sugerido em {prazos['data_interna'].strftime('%d/%m/%Y')} "
            f"({prazos['base_legal']}).",
            "Rito: defesa (art. 113) → alegações finais em 10 dias (art. 122) → "
            "recurso à autoridade superior em 20 dias (art. 127). O efeito sobre "
            "a exigibilidade segue o rito do órgão autuador — não presumir "
            "suspensão automática.",
            "O valor esperado é probabilístico e depende da estimativa de êxito; "
            "não é o desembolso certo, apenas a média ponderada pela chance de "
            "manutenção do auto.",
        ],
        "faixa_sensibilidade": {"piso": piso, "teto": teto,
                                "prob_baixa_pct": prob_baixa,
                                "prob_alta_pct": prob_alta},
    }


# ── Cenário 4: prescrição quinquenal (tese preliminar) ────────────────────────
def _cenario_prescricao(data_infracao: date | None, hoje: date) -> dict:
    if data_infracao is None:
        return {
            "id": "prescricao",
            "titulo": "Prescrição quinquenal da pretensão punitiva",
            "base_legal": "Lei 9.873/99, art. 1º e §1º.",
            "aplicavel": False,
            "desembolso_estimado": None,
            "memoria_calculo": [],
            "observacoes": [
                "Informe a DATA DO FATO (data da infração) para avaliar a "
                "prescrição quinquenal (Lei 9.873/99 art. 1º) e a intercorrente "
                "de 3 anos (art. 1º §1º).",
            ],
        }

    dias = (hoje - data_infracao).days
    # 5 anos "completos" a partir da data do fato (art. 1º da Lei 9.873/99).
    # adicionar_anos trata 29/02 com segurança (replace(year=...) estouraria
    # ValueError se a infração fosse 29/02 e o ano-limite não for bissexto).
    from app.utils.datas import adicionar_anos
    limite = adicionar_anos(data_infracao, _PRESCRICAO_ANOS)
    prescrito = hoje > limite
    anos_aprox = dias / 365.25

    if not prescrito:
        return {
            "id": "prescricao",
            "titulo": "Prescrição quinquenal da pretensão punitiva",
            "base_legal": "Lei 9.873/99, art. 1º e §1º.",
            "aplicavel": False,
            "desembolso_estimado": None,
            "memoria_calculo": [
                f"Data do fato: {data_infracao.strftime('%d/%m/%Y')}; "
                f"decorridos ~{anos_aprox:.1f} anos até "
                f"{hoje.strftime('%d/%m/%Y')}.",
                f"Prazo quinquenal (5 anos) completa-se em "
                f"{limite.strftime('%d/%m/%Y')} — ainda NÃO transcorrido.",
            ],
            "observacoes": [
                "Prescrição da pretensão punitiva ainda não consumada pela "
                "contagem simples; avaliar marcos interruptivos e a "
                "intercorrente de 3 anos (art. 1º §1º) no caso concreto.",
            ],
        }

    return {
        "id": "prescricao",
        "titulo": "Prescrição quinquenal da pretensão punitiva",
        "base_legal": "Lei 9.873/99, art. 1º e §1º.",
        "aplicavel": True,
        "desembolso_estimado": Decimal("0.00"),
        "memoria_calculo": [
            f"Data do fato: {data_infracao.strftime('%d/%m/%Y')}; decorridos "
            f"~{anos_aprox:.1f} anos até {hoje.strftime('%d/%m/%Y')}.",
            f"Prazo quinquenal (5 anos) completou-se em "
            f"{limite.strftime('%d/%m/%Y')} — transcorrido.",
            "Reconhecida a prescrição, extingue-se a exigibilidade da multa → "
            "desembolso estimado R$ 0,00.",
        ],
        "observacoes": [
            "TESE A SER RECONHECIDA pela autoridade — a extinção do crédito "
            "depende de reconhecimento (administrativo ou judicial), não é "
            "automática. Verificar marcos INTERRUPTIVOS (art. 2º) que reabram "
            "a contagem antes de contar com o desembolso zero.",
        ],
    }


# ── Recomendação determinística ───────────────────────────────────────────────
def _recomendar(cenarios: list[dict]) -> dict:
    por_id = {c["id"]: c for c in cenarios}

    presc = por_id.get("prescricao")
    if presc and presc["aplicavel"]:
        return {
            "cenario_id": "prescricao",
            "racional": (
                "Há tese de PRESCRIÇÃO quinquenal (Lei 9.873/99 art. 1º) com o "
                "prazo aparentemente transcorrido — se reconhecida, extingue a "
                "exigibilidade (desembolso R$ 0,00). É a via de menor risco "
                "econômico e deve ser suscitada como preliminar."
            ),
        }

    ordem = {"pagar_a_vista": 0, "converter_servicos": 1, "defender": 2}
    candidatos = [c for c in cenarios
                  if c["aplicavel"] and c["id"] in ordem
                  and c["desembolso_estimado"] is not None]
    escolha = min(candidatos,
                  key=lambda c: (c["desembolso_estimado"], ordem[c["id"]]))

    return {
        "cenario_id": escolha["id"],
        "racional": (
            f"Menor desembolso estimado entre os cenários aplicáveis: "
            f"'{escolha['titulo']}' resulta em {_moeda(escolha['desembolso_estimado'])}. "
            "Comparação puramente econômica sobre o valor informado — a decisão "
            "final pondera risco processual e objetivos do cliente (HITL)."
        ),
    }
