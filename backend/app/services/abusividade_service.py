# ── app/services/abusividade_service.py ──────────────────────────────────────
# Motor determinístico de ABUSIVIDADE de juros bancários.
#
# 1) Consulta a taxa MÉDIA de mercado da modalidade na época da contratação
#    (BCB/Olinda, série diária de taxas de juros — mesma fonte já usada pelo
#    router analise_bancaria; a consulta foi EXTRAÍDA para cá para reúso).
# 2) Veredito fundamentado no repetitivo do STJ (REsp 1.061.530/RS, Tema 27):
#    abusividade exige taxa que destoe SUBSTANCIALMENTE da média de mercado.
#    A jurisprudência consolidada usa ~1,5x a média como BALIZA (não é
#    tabelamento legal — Súmula 596/STF afasta a Lei de Usura dos bancos):
#      razao = taxa_contrato / taxa_media
#      ≥ 1,5x → "indicio_forte_abusividade" · 1,2–1,5x → "zona_de_atencao"
#      < 1,2x → "dentro_da_normalidade"
#    A caracterização é SEMPRE judicial e depende do caso concreto (HITL).
# 3) Expurgo/recálculo: com indício forte, recalcula a parcela (Price) com a
#    taxa média BACEN e apresenta o cenário revisional (economia mensal/total).
#
# FALHA DA API BCB — decisão: FAIL-SOFT. A avaliação NUNCA inventa média:
# se o BCB estiver indisponível, retorna taxa_media=None, veredito
# "indeterminado" e aviso claro, preservando os dados do contrato informados
# para nova tentativa. (Alternativa 503 rejeitada: o advogado perderia o
# contexto já digitado sem ganho — a resposta explicita a indisponibilidade.)
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from app.services.calc.cet import parcela_price

OLINDA_DIA = ("https://olinda.bcb.gov.br/olinda/servico/taxaJuros/versao/v2/"
              "odata/TaxasJurosDiariaPorInicioPeriodo")

# Atalhos de modalidade → termos buscados (case-insensitive) no campo
# Modalidade da API Olinda. Também é aceita a string EXATA da modalidade
# (como devolvida por GET /analise-bancaria/modalidades).
MODALIDADES_MAP: dict[str, list[str]] = {
    "credito_pessoal": ["crédito pessoal não-consignado"],
    "credito_pessoal_consignado_inss": ["consignado", "inss"],
    "credito_pessoal_consignado_privado": ["consignado", "privado"],
    "credito_pessoal_consignado_publico": ["consignado", "público"],
    "veiculos": ["aquisição de veículos"],
    "cheque_especial": ["cheque especial"],
    "cartao_rotativo": ["cartão de crédito rotativo"],
    "cartao_parcelado": ["cartão de crédito parcelado"],
    "aquisicao_outros_bens": ["aquisição de outros bens"],
    "capital_de_giro": ["capital de giro com prazo superior"],
    "conta_garantida": ["conta garantida"],
}

LIMIAR_FORTE = Decimal("1.5")     # baliza jurisprudencial (~1,5x a média)
LIMIAR_ATENCAO = Decimal("1.2")

BASE_LEGAL_ABUSIVIDADE = [
    "STJ, REsp 1.061.530/RS (recurso repetitivo, Tema 27): a abusividade exige "
    "taxa que destoe substancialmente da média de mercado",
    "Súmula 596/STF: Lei de Usura não se aplica às instituições financeiras "
    "(não há tabelamento legal de juros bancários)",
    "CDC art. 51, IV e §1º, III: nulidade de cláusula que estabelece obrigação "
    "iníqua/abusiva ou onerosidade excessiva",
]

AVISO_HITL = (
    "A razão de 1,5x sobre a média de mercado é BALIZA jurisprudencial, não "
    "tabelamento legal. A caracterização de abusividade é JUDICIAL e depende do "
    "caso concreto (perfil de risco, garantias, época e praça da contratação). "
    "Resultado é apoio ao advogado — revisão humana obrigatória (HITL)."
)


class TaxaMediaIndisponivel(Exception):
    """API do BCB fora do ar / resposta inválida — nunca inventar média."""


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


async def olinda_get(params: dict) -> list:
    """GET na série diária de taxas de juros do BCB (Olinda). Levanta
    TaxaMediaIndisponivel em qualquer falha de rede/HTTP/payload."""
    import httpx
    params = {**params, "$format": "json"}
    try:
        async with httpx.AsyncClient(timeout=30) as cli:
            r = await cli.get(OLINDA_DIA, params=params)
            r.raise_for_status()
            return r.json().get("value", [])
    except TaxaMediaIndisponivel:
        raise
    except Exception as e:  # rede, HTTP != 2xx, JSON inválido
        raise TaxaMediaIndisponivel(f"Falha ao consultar BCB/Olinda: {str(e)[:120]}") from e


def _match_modalidade(row_mod: str, termos: list[str]) -> bool:
    rm = (row_mod or "").casefold()
    return all(t.casefold() in rm for t in termos)


async def consultar_taxa_media(
    modalidade: str,
    segmento: str | None = None,
    data_referencia: date | None = None,
) -> dict:
    """Taxa média de mercado (min/média/máx a.m. e a.a.) da modalidade no
    período mais recente ≤ ``data_referencia`` (época da contratação); sem
    data, usa o período mais recente disponível.

    ``modalidade`` aceita um atalho de MODALIDADES_MAP ou a string exata da
    API. Levanta TaxaMediaIndisponivel (BCB fora) ou LookupError (sem dados).
    """
    avisos: list[str] = []
    # 1) descobre o período de referência
    filtro_periodo = None
    if data_referencia:
        ref = data_referencia.isoformat()
        ult = await olinda_get({"$filter": f"InicioPeriodo le '{ref}'",
                                "$orderby": "InicioPeriodo desc",
                                "$top": "1", "$select": "InicioPeriodo"})
        if ult:
            filtro_periodo = ult[0]["InicioPeriodo"]
        else:
            avisos.append(f"BCB sem série anterior a {ref}; usado o período mais "
                          "recente disponível.")
    if not filtro_periodo:
        ult = await olinda_get({"$top": "1", "$orderby": "InicioPeriodo desc",
                                "$select": "InicioPeriodo"})
        if not ult:
            raise LookupError("BCB sem dados na série diária de taxas de juros")
        filtro_periodo = ult[0]["InicioPeriodo"]

    # 2) baixa o período e filtra a modalidade client-side (case-insensitive,
    #    robusto a variações de caixa/acentuação da API)
    rows = await olinda_get({
        "$filter": f"InicioPeriodo eq '{filtro_periodo}'",
        "$select": "Modalidade,Segmento,TaxaJurosAoMes,TaxaJurosAoAno",
        "$top": "8000",
    })
    termos = MODALIDADES_MAP.get(modalidade, [modalidade])
    sel = [x for x in rows
           if _match_modalidade(x.get("Modalidade", ""), termos)
           and x.get("TaxaJurosAoMes") is not None]
    if segmento:
        seg = segmento.casefold()
        sel = [x for x in sel if seg in (x.get("Segmento") or "").casefold()]
    if not sel:
        raise LookupError(f"Modalidade '{modalidade}' sem dados no BCB para o "
                          f"período {filtro_periodo}")

    am = [_dec(x["TaxaJurosAoMes"]) for x in sel]
    aa = [_dec(x["TaxaJurosAoAno"]) for x in sel if x.get("TaxaJurosAoAno") is not None]

    def _agg(vals: list[Decimal]) -> dict:
        return {"min": float(_q2(min(vals))),
                "media": float(_q2(sum(vals) / len(vals))),
                "max": float(_q2(max(vals)))}

    return {
        "modalidade": modalidade,
        "modalidade_bcb": sel[0].get("Modalidade"),
        "segmento": segmento,
        "periodo": filtro_periodo,
        "instituicoes": len(sel),
        "ao_mes": _agg(am),
        "ao_ano": _agg(aa) if aa else None,
        "fonte": "Banco Central do Brasil — Taxas de Juros (Olinda, série diária)",
        "avisos": avisos,
    }


def classificar_razao(razao: Decimal) -> str:
    if razao >= LIMIAR_FORTE:
        return "indicio_forte_abusividade"
    if razao >= LIMIAR_ATENCAO:
        return "zona_de_atencao"
    return "dentro_da_normalidade"


def cenario_expurgo(
    valor_financiado,
    n_parcelas: int,
    taxa_contrato_am_pct,
    taxa_media_am_pct,
    parcela_contratual=None,
) -> dict:
    """Cenário revisional: recalcula a parcela (Tabela Price) com a taxa média
    BACEN e compara com a parcela contratual (informada ou calculada com a
    taxa do contrato). Decimal em todo o cálculo."""
    pv = _dec(valor_financiado)
    i_c = _dec(taxa_contrato_am_pct) / 100
    i_m = _dec(taxa_media_am_pct) / 100
    if parcela_contratual is not None:
        p_orig = _q2(_dec(parcela_contratual))
        origem = "parcela contratual informada"
    else:
        p_orig = parcela_price(pv, i_c, n_parcelas)
        origem = f"Price com a taxa do contrato ({taxa_contrato_am_pct}% a.m.)"
    p_rev = parcela_price(pv, i_m, n_parcelas)
    eco_mensal = _q2(p_orig - p_rev)
    eco_total = _q2(eco_mensal * n_parcelas)
    return {
        "parcela_original": float(p_orig),
        "parcela_revisada": float(p_rev),
        "economia_mensal": float(eco_mensal),
        "economia_total": float(eco_total),
        "total_original": float(_q2(p_orig * n_parcelas)),
        "total_revisado": float(_q2(p_rev * n_parcelas)),
        "memoria": [
            f"1. Parcela original: {origem} = R$ {p_orig}.",
            f"2. Parcela revisada: Price(PV=R$ {_q2(pv)}, i={_q2(_dec(taxa_media_am_pct))}% "
            f"a.m. — taxa média BACEN, n={n_parcelas}) = R$ {p_rev}.",
            f"3. Economia mensal = R$ {eco_mensal}; economia total no prazo "
            f"({n_parcelas} parcelas) = R$ {eco_total}.",
            "4. PMT = PV·i / (1 − (1+i)^−n) — Sistema Price, aritmética Decimal.",
        ],
    }


async def avaliar_abusividade(
    taxa_contrato_am_pct,
    modalidade: str,
    data_contrato: date | None = None,
    segmento: str | None = None,
    valor_financiado=None,
    n_parcelas: int | None = None,
    parcela_contratual=None,
) -> dict:
    """Avalia indício de abusividade da taxa contratada frente à média de
    mercado BACEN da época da contratação. Fail-soft se o BCB estiver fora
    (taxa_media=None + aviso; nunca inventa média)."""
    taxa_c = _dec(taxa_contrato_am_pct)
    if taxa_c <= 0:
        raise ValueError("taxa_contrato_am_pct deve ser positiva")

    avisos = [AVISO_HITL]
    base = {
        "taxa_contrato_am_pct": float(taxa_c),
        "modalidade": modalidade,
        "segmento": segmento,
        "data_contrato": data_contrato.isoformat() if data_contrato else None,
        "base_legal": BASE_LEGAL_ABUSIVIDADE,
    }

    try:
        tm = await consultar_taxa_media(modalidade, segmento=segmento,
                                        data_referencia=data_contrato)
    except TaxaMediaIndisponivel as e:
        return {**base, "taxa_media": None, "razao": None,
                "veredito": "indeterminado", "expurgo": None,
                "fundamentacao": ("Não foi possível obter a taxa média de mercado "
                                  "junto ao Banco Central neste momento."),
                "avisos": avisos + [
                    f"API do BCB indisponível ({e}). A avaliação NÃO foi realizada "
                    "— nenhuma média foi estimada. Tente novamente mais tarde."]}
    except LookupError as e:
        return {**base, "taxa_media": None, "razao": None,
                "veredito": "indeterminado", "expurgo": None,
                "fundamentacao": str(e),
                "avisos": avisos + [
                    "Modalidade sem série no BCB para o período — confira o nome da "
                    "modalidade em GET /analise-bancaria/modalidades."]}

    avisos += tm.pop("avisos", [])
    media_am = _dec(str(tm["ao_mes"]["media"]))
    razao = (taxa_c / media_am).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    veredito = classificar_razao(razao)

    fundamentacao = (
        f"Taxa contratada de {taxa_c}% a.m. contra média de mercado de "
        f"{media_am}% a.m. (BACEN, período {tm['periodo']}, {tm['instituicoes']} "
        f"instituições) — razão de {razao}x. Nos termos do REsp 1.061.530/RS "
        "(Tema 27/STJ), a revisão exige que a taxa destoe SUBSTANCIALMENTE da "
        "média de mercado; a jurisprudência consolidada adota ~1,5x como baliza. "
        + {
            "indicio_forte_abusividade": "A razão apurada SUPERA a baliza de 1,5x — "
            "há indício forte de abusividade, apto a fundamentar pedido revisional.",
            "zona_de_atencao": "A razão apurada fica entre 1,2x e 1,5x — zona de "
            "atenção; a viabilidade revisional depende de reforço probatório.",
            "dentro_da_normalidade": "A razão apurada é inferior a 1,2x — a taxa "
            "não destoa substancialmente da média de mercado.",
        }[veredito]
    )

    expurgo = None
    if veredito == "indicio_forte_abusividade":
        if valor_financiado is not None and n_parcelas:
            expurgo = cenario_expurgo(valor_financiado, int(n_parcelas),
                                      taxa_c, media_am, parcela_contratual)
        else:
            avisos.append("Informe valor_financiado e n_parcelas para obter o "
                          "cenário de expurgo (parcela recalculada pela média BACEN).")

    return {**base, "taxa_media": tm, "razao": float(razao), "veredito": veredito,
            "fundamentacao": fundamentacao, "expurgo": expurgo, "avisos": avisos}


# ── Integração com a esteira de peças (bank_analysis.gerar_peca) ─────────────
def formatar_expurgo_para_peca(avaliacao: dict) -> str | None:
    """Converte o resultado de avaliar_abusividade() em parágrafo determinístico
    para a descrição de fatos da minuta revisional. Só usa NÚMEROS validados e
    rótulos fixos (evita injeção de texto arbitrário no prompt da IA).
    Retorna None se não houver expurgo calculado."""
    if not isinstance(avaliacao, dict):
        return None
    exp = avaliacao.get("expurgo")
    if not isinstance(exp, dict):
        return None
    try:
        taxa_c = float(avaliacao["taxa_contrato_am_pct"])
        media = float(avaliacao["taxa_media"]["ao_mes"]["media"])
        periodo = re.sub(r"[^0-9A-Za-z:\-]", "", str(avaliacao["taxa_media"]["periodo"]))[:32]
        razao = float(avaliacao["razao"])
        p_orig = float(exp["parcela_original"])
        p_rev = float(exp["parcela_revisada"])
        eco_m = float(exp["economia_mensal"])
        eco_t = float(exp["economia_total"])
    except (KeyError, TypeError, ValueError):
        return None
    mod = re.sub(r"[^\w\sÀ-ÿ/().-]", "", str(avaliacao.get("modalidade") or ""))[:80]

    from app.utils.format import formatar_brl as brl  # #41: formatador BRL único

    return (
        "CÁLCULO DETERMINÍSTICO DE ABUSIVIDADE DOS JUROS (fonte: BACEN/Olinda): "
        f"a taxa contratada de {taxa_c:.2f}% a.m. supera em {razao:.2f}x a taxa média "
        f"de mercado da modalidade {mod or 'informada'} ({media:.2f}% a.m., período "
        f"{periodo}), destoando substancialmente da média (REsp 1.061.530/RS, Tema "
        "27/STJ). Recalculada a operação pela taxa média (Tabela Price), a parcela "
        f"cairia de {brl(p_orig)} para {brl(p_rev)}, com economia mensal de "
        f"{brl(eco_m)} e economia total de {brl(eco_t)} no prazo do contrato. "
        "Use EXATAMENTE esses valores — não invente números."
    )
