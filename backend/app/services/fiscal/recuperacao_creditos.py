# ── app/services/fiscal/recuperacao_creditos.py ──────────────────────────────
# Motor DETERMINÍSTICO de triagem de oportunidades tributárias — SEM IA.
# Recebe notas parseadas (nfe_parser) + regime e aplica hipóteses técnicas com
# base legal, memória de cálculo auditável e alertas de documentos faltantes.
#
# Regra de segurança: XML/NF-e sustenta pré-auditoria e estimativa matemática,
# mas NÃO prova, sozinho, elegibilidade, pagamento indevido ou prescrição.
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

_ZERO = Decimal("0")
_CENT = Decimal("0.01")

# ── Tema 69 STF (RE 574.706) ──────────────────────────────────────────────────
MODULACAO_TEMA_69 = date(2017, 3, 15)
ALIQ_PIS_COFINS = {
    "lucro_real": Decimal("0.0925"),
    "lucro_presumido": Decimal("0.0365"),
}

# ── Monofásicos (Simples Nacional) ────────────────────────────────────────────
# Tabela mínima para RADAR documental. NCM é sinal de triagem, não conclusão
# jurídica definitiva sobre produto/operação.
NCM_MONOFASICOS: dict[str, str] = {
    "2710": "Combustíveis derivados de petróleo (Lei 9.718/98, art. 4º)",
    "2711": "Gás de petróleo e hidrocarbonetos gasosos (Lei 9.718/98, art. 4º)",
    "3003": "Medicamentos (Lei 10.147/00, art. 1º, I, a)",
    "3004": "Medicamentos (Lei 10.147/00, art. 1º, I, a)",
    "3303": "Perfumes e águas-de-colônia (Lei 10.147/00, art. 1º, I, b)",
    "3304": "Produtos de beleza/maquiagem (Lei 10.147/00, art. 1º, I, b)",
    "3305": "Preparações capilares (Lei 10.147/00, art. 1º, I, b)",
    "3306": "Higiene bucal (Lei 10.147/00, art. 1º, I, b)",
    "3307": "Barbear/desodorantes/higiene (Lei 10.147/00, art. 1º, I, b)",
    "4011": "Pneus novos de borracha (Lei 10.485/02, art. 5º)",
    "4013": "Câmaras de ar de borracha (Lei 10.485/02, art. 5º)",
    "2201": "Águas (bebidas frias — Lei 13.097/15, arts. 14 e 28)",
    "2202": "Refrigerantes/isotônicos (bebidas frias — Lei 13.097/15, arts. 14 e 28)",
    "2203": "Cervejas de malte (bebidas frias — Lei 13.097/15, arts. 14 e 28)",
}

REPARTICAO_PIS_COFINS_ANEXO_I = Decimal("0.0276") + Decimal("0.1274")
ALIQ_EFETIVA_SIMPLES_ESTIMADA = Decimal("0.04")

AVISO_HITL = (
    "PRÉ-AUDITORIA TRIBUTÁRIA — não é parecer, liquidação nem reconhecimento "
    "de crédito recuperável. Os valores são estimativas matemáticas obtidas "
    "dos XMLs de saída e exigem validação jurídica, fiscal e contábil, inclusive "
    "PGDAS-D/SPED/EFD, pagamentos efetivos, retificações, modulação, legitimidade, "
    "termo inicial e prescrição, antes de qualquer medida administrativa ou judicial."
)

REGIMES_VALIDOS = ("simples", "lucro_presumido", "lucro_real")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def _fmt(v: Decimal) -> str:
    inteiro, _, dec = f"{_q(v):,.2f}".partition(".")
    return "R$ " + inteiro.replace(",", ".") + "," + dec


def _resumo_nota(n: dict) -> dict:
    if n.get("erro"):
        return {
            "chave": n.get("chave_acesso") or "",
            "numero": n.get("numero"),
            "data_emissao": None,
            "emitente_nome": None,
            "valor_total": 0.0,
            "icms_destacado": 0.0,
            "erro": n["erro"],
        }
    icms = sum((i["vicms"] for i in n["itens"]), _ZERO)
    emit = n.get("emitente") or {}
    return {
        "chave": n.get("chave_acesso") or "",
        "numero": n.get("numero"),
        "data_emissao": n["data_emissao"].isoformat() if n.get("data_emissao") else None,
        "emitente_nome": emit.get("nome"),
        "valor_total": float(_q(n.get("valor_total") or _ZERO)),
        "icms_destacado": float(_q(icms)),
        "erro": None,
    }


def _pct(v: Decimal) -> str:
    return f"{(v * 100).normalize()}".replace(".", ",") + "%"


def _referencia_documental_cinco_anos(hoje: date) -> date:
    """Referência visual de 5 anos; NÃO é termo inicial jurídico de prescrição."""
    try:
        return hoje.replace(year=hoje.year - 5)
    except ValueError:
        return hoje.replace(year=hoje.year - 5, day=28)


def _eh_saida(cfop: str | None) -> bool:
    return bool(cfop) and cfop[0] in "567"


def _eh_saida_st(cfop: str | None) -> bool:
    return bool(cfop) and len(cfop) == 4 and cfop[0] in "56" and cfop[1:3] == "40"


def _tese(tese_id: str, titulo: str, base_legal: list[str], fundamento: str) -> dict:
    return {
        "tese_id": tese_id,
        "titulo": titulo,
        "base_legal": base_legal,
        "fundamento": fundamento,
        # `aplicavel` é contrato legado da UI e significa apenas compatibilidade
        # técnica preliminar com regime/documentos; não elegibilidade jurídica.
        "aplicavel": False,
        "motivo_inaplicavel": None,
        "valor_estimado": _ZERO,
        "memoria_calculo": [],
        "alertas": [],
        "nivel_confianca": "estimativa_preliminar",
    }


def _alerta_elegibilidade() -> str:
    return (
        "Elegibilidade e prescrição NÃO foram avaliadas pelo XML. Confirmar "
        "pagamento/extinção do crédito, declarações, escrituração, termo inicial "
        "legal, modulação e via procedimental antes de tratar a estimativa como crédito."
    )


# ── Teses / radares ───────────────────────────────────────────────────────────
def _tema_69_stf(notas_validas: list[dict], regime: str) -> dict:
    t = _tese(
        "tema_69_stf",
        "Exclusão do ICMS da base de cálculo do PIS/COFINS (Tema 69 STF)",
        [
            "RE 574.706/PR (STF, Tema 69 de repercussão geral)",
            "Modulação de efeitos: fatos geradores a partir de 15/03/2017 "
            "(embargos de declaração julgados em 13/05/2021)",
            "CTN arts. 165-168, na redação vigente (termo inicial a validar no caso)",
        ],
        "O Tema 69 autoriza a exclusão do ICMS destacado da base de PIS/COFINS "
        "nas hipóteses alcançadas pelo precedente. O XML permite estimar a grandeza "
        "matemática, mas não demonstra sozinho pagamento indevido ou direito atual à recuperação.",
    )
    if regime == "simples":
        t["motivo_inaplicavel"] = (
            "Radar não compatível com esta fórmula para Simples Nacional: "
            "PIS/COFINS são recolhidos no DAS e exigem análise própria do regime."
        )
        return t

    aliq = ALIQ_PIS_COFINS[regime]
    consideradas = [
        n for n in notas_validas
        if not n["data_emissao"] or n["data_emissao"] >= MODULACAO_TEMA_69
    ]
    moduladas = [
        n for n in notas_validas
        if n["data_emissao"] and n["data_emissao"] < MODULACAO_TEMA_69
    ]

    v_icms = _ZERO
    n_notas = 0
    for nota in consideradas:
        icms_nota = sum(
            (i["vicms"] for i in nota["itens"] if _eh_saida(i["cfop"])),
            _ZERO,
        )
        if icms_nota > _ZERO:
            n_notas += 1
            v_icms += icms_nota

    t["aplicavel"] = True
    t["valor_estimado"] = _q(v_icms * aliq)
    regime_txt = (
        "não-cumulativo (1,65% + 7,6% = 9,25%)"
        if regime == "lucro_real"
        else "cumulativo (0,65% + 3% = 3,65%)"
    )
    t["memoria_calculo"] = [
        "1. NF-e de saída próprias usadas apenas para estimativa documental "
        f"(CFOP 5xxx/6xxx/7xxx e modulação do Tema 69): {n_notas} com ICMS destacado.",
        f"2. Soma do ICMS destacado nos itens de saída: {_fmt(v_icms)}.",
        f"3. Regime informado: {regime}; alíquota PIS/COFINS {regime_txt}.",
        f"4. Estimativa matemática = {_fmt(v_icms)} × {_pct(aliq)} = {_fmt(v_icms * aliq)}.",
    ]
    if moduladas:
        t["alertas"].append(
            f"{len(moduladas)} nota(s) anterior(es) a 15/03/2017 excluída(s) "
            "somente pela modulação temporal do Tema 69."
        )
    t["alertas"].append(
        "Conferir EFD-Contribuições e apurações do período para verificar se o "
        "ICMS já foi excluído da base e qual valor foi efetivamente recolhido."
    )
    t["alertas"].append(_alerta_elegibilidade())
    return t


def _monofasicos_simples(notas_validas: list[dict], regime: str) -> dict:
    t = _tese(
        "monofasicos_simples",
        "PIS/COFINS monofásicos revendidos por optante do Simples Nacional",
        [
            "LC 123/06, art. 18, §4º-A, I",
            "Lei 9.718/98, art. 4º",
            "Lei 10.147/00",
            "Lei 10.485/02",
            "Lei 13.097/15",
            "CTN arts. 165-168, na redação vigente",
        ],
        "A presença de NCMs compatíveis com regimes monofásicos pode indicar "
        "oportunidade de revisar a segregação de receitas no Simples. NCM e XML "
        "não provam, isoladamente, recolhimento em duplicidade ou crédito recuperável.",
    )
    if regime != "simples":
        t["motivo_inaplicavel"] = (
            "Radar configurado para a segregação de receitas do Simples Nacional; "
            "outros regimes exigem análise própria da incidência na revenda."
        )
        return t

    receita_mono = _ZERO
    itens_mono = 0
    bases_detectadas: set[str] = set()
    for nota in notas_validas:
        for item in nota["itens"]:
            ncm = item["ncm"] or ""
            if not _eh_saida(item["cfop"]):
                continue
            for prefixo, base in NCM_MONOFASICOS.items():
                if ncm.startswith(prefixo):
                    receita_mono += item["vprod"]
                    itens_mono += 1
                    bases_detectadas.add(f"NCM {prefixo}: {base}")
                    break

    parcela = ALIQ_EFETIVA_SIMPLES_ESTIMADA * REPARTICAO_PIS_COFINS_ANEXO_I
    t["aplicavel"] = True
    if itens_mono == 0:
        t["valor_estimado"] = _ZERO
        t["memoria_calculo"] = [
            "1. Nenhum item com NCM do radar monofásico detectado nas NF-e de saída analisadas.",
        ]
    else:
        t["valor_estimado"] = _q(receita_mono * parcela)
        t["memoria_calculo"] = [
            f"1. Itens de saída sinalizados pelo radar de NCM: {itens_mono}; "
            f"receita documental associada: {_fmt(receita_mono)}.",
            "2. Referências dos NCMs sinalizados: " + "; ".join(sorted(bases_detectadas)) + ".",
            "3. Cenário preliminar: repartição do Anexo I (PIS 2,76% + COFINS 12,74% "
            "do DAS) aplicada sobre alíquota efetiva estimada de 4%.",
            f"4. Estimativa matemática = {_fmt(receita_mono)} × {_pct(parcela)} = "
            f"{_fmt(receita_mono * parcela)}.",
        ]
        t["alertas"].append(
            "O valor exato depende da alíquota efetiva real de cada competência, "
            "RBT12, anexo, PGDAS-D e segregação efetivamente declarada."
        )
    t["alertas"].append(
        "Autopeças e outras listas legais exigem conferência item a item; o radar "
        "não substitui a classificação fiscal completa do produto/operação."
    )
    t["alertas"].append(_alerta_elegibilidade())
    return t


def _icms_st_ressarcimento(notas_validas: list[dict], regime: str) -> dict:
    t = _tese(
        "icms_st_ressarcimento",
        "Ressarcimento de ICMS-ST — venda abaixo da base presumida (radar)",
        [
            "RE 593.849/MG (STF, Tema 201 de repercussão geral)",
            "CF/88, art. 150, §7º",
        ],
        "CFOP de saída sujeito à substituição tributária é apenas sinal de triagem. "
        "A existência e o valor de eventual ressarcimento dependem da base presumida, "
        "operação efetiva, legislação do ente e documentação de aquisição/apuração.",
    )
    notas_st = []
    receita_st = _ZERO
    for nota in notas_validas:
        itens_st = [i for i in nota["itens"] if _eh_saida_st(i["cfop"])]
        if itens_st:
            notas_st.append(nota)
            receita_st += sum((i["vprod"] for i in itens_st), _ZERO)

    if not notas_st:
        t["motivo_inaplicavel"] = (
            "Nenhuma saída com CFOP do radar de substituição tributária (x40x) "
            "foi detectada nas notas analisadas."
        )
        return t

    t["aplicavel"] = True
    t["valor_estimado"] = _ZERO
    t["memoria_calculo"] = [
        f"1. {len(notas_st)} nota(s) com CFOP de saída sinalizado como ST, "
        f"somando {_fmt(receita_st)} em produtos.",
        "2. Valor estimado = R$ 0,00: a NF-e de saída não basta para reconstruir "
        "a base presumida/ICMS-ST retido e calcular honestamente a diferença.",
    ]
    t["alertas"].append(
        "Potencial de revisão detectado. Solicitar notas de aquisição, base presumida "
        "(MVA/PMPF), apuração/GIA ou obrigação estadual equivalente e legislação do ente."
    )
    t["alertas"].append(_alerta_elegibilidade())
    return t


# ── Consolidação ──────────────────────────────────────────────────────────────
def analisar_recuperacao(
    notas: list[dict],
    regime: str,
    hoje: date | None = None,
) -> dict:
    """Consolida a pré-auditoria sem inferir prescrição pela emissão da NF-e.

    `hoje` é mantido no contrato para testes/reprodutibilidade. Ele serve apenas
    para uma referência documental informativa de cinco anos; nunca para excluir
    nota ou concluir prescrição/restituição.
    """
    if regime not in REGIMES_VALIDOS:
        raise ValueError(f"Regime inválido: {regime!r}. Use um de {REGIMES_VALIDOS}.")

    hoje = hoje or date.today()
    referencia = _referencia_documental_cinco_anos(hoje)
    notas_ok = [n for n in notas if not n.get("erro")]
    notas_erro = [n for n in notas if n.get("erro")]
    antigas_por_emissao = [
        n for n in notas_ok
        if n.get("data_emissao") and n["data_emissao"] < referencia
    ]

    # P0 #1553: NENHUMA NF-e é excluída por suposta prescrição baseada somente
    # em `data_emissao`. Todas seguem para a estimativa documental, salvo filtro
    # jurídico específico e independente, como a modulação temporal do Tema 69.
    teses = [
        _tema_69_stf(notas_ok, regime),
        _monofasicos_simples(notas_ok, regime),
        _icms_st_ressarcimento(notas_ok, regime),
    ]

    alertas_globais: list[str] = [
        "PRESCRIÇÃO NÃO AVALIADA: a data de emissão da NF-e não é termo inicial "
        "universal do CTN arts. 165-168. Confirmar pagamento/extinção, hipótese "
        "legal, modulação, decisão judicial quando houver e demais marcos do caso."
    ]
    if antigas_por_emissao:
        alertas_globais.append(
            f"{len(antigas_por_emissao)} nota(s) têm emissão anterior a "
            f"{referencia.strftime('%d/%m/%Y')}. Permaneceram na estimativa: esse "
            "corte é somente referência documental de cinco anos e NÃO declaração de prescrição."
        )
    if notas_erro:
        alertas_globais.append(
            f"{len(notas_erro)} arquivo(s) não pôde(ram) ser lido(s) como NF-e "
            "válida — consultar o campo `erro` das notas retornadas."
        )

    datas = sorted(n["data_emissao"] for n in notas_ok if n.get("data_emissao"))
    total = sum((t["valor_estimado"] for t in teses), _ZERO)

    for t in teses:
        if isinstance(t["base_legal"], (list, tuple)):
            t["base_legal"] = " · ".join(t["base_legal"])
        t["valor_estimado"] = float(t["valor_estimado"])

    return {
        "regime": regime,
        "total_estimado": float(_q(total)),
        "notas_analisadas": len(notas_ok),
        "notas_com_erro": len(notas_erro),
        # Campo legado do contrato da rota/PDF. Zero NÃO significa conclusão de
        # inexistência de prescrição; a apuração está explicitamente desabilitada.
        "notas_prescritas": 0,
        "periodo": {
            "inicio": datas[0].isoformat() if datas else None,
            "fim": datas[-1].isoformat() if datas else None,
        },
        "teses": teses,
        "alertas_globais": alertas_globais,
        "aviso_hitl": AVISO_HITL,
        "notas": [_resumo_nota(n) for n in notas],
    }
