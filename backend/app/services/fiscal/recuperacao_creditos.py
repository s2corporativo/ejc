# ── app/services/fiscal/recuperacao_creditos.py ──────────────────────────────
# Motor DETERMINÍSTICO de recuperação de créditos tributários — SEM IA.
# Recebe notas parseadas (nfe_parser) + regime e aplica teses consolidadas,
# cada uma com base_legal, fundamento e memória de cálculo auditável (mesmo
# padrão do vertical Bancário: services/abusividade_service.py, calc/cet.py).
#
# Princípio: NUNCA inventar número. O que não dá para calcular do XML de
# saída vira alerta pedindo o documento certo (PGDAS, GIA, SPED/EFD).
# Todo resultado é ESTIMATIVA PRELIMINAR para triagem — HITL obrigatório.
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP

_ZERO = Decimal("0")
_CENT = Decimal("0.01")

# ── Tema 69 STF (RE 574.706) ──────────────────────────────────────────────────
MODULACAO_TEMA_69 = date(2017, 3, 15)  # efeitos a partir de 15/03/2017
ALIQ_PIS_COFINS = {
    # não-cumulativo (Leis 10.637/02 e 10.833/03): 1,65% + 7,6%
    "lucro_real":       Decimal("0.0925"),
    # cumulativo (Lei 9.718/98): 0,65% + 3%
    "lucro_presumido":  Decimal("0.0365"),
}

# ── Monofásicos (Simples Nacional) ────────────────────────────────────────────
# Tabela mínima HONESTA: capítulos/posições NCM com incidência monofásica
# consolidada de PIS/COFINS. Prefixo NCM → base legal.
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
# Repartição do Anexo I da LC 123/06 (comércio): dentro da alíquota do Simples,
# PIS = 2,76% e COFINS = 12,74% do DAS → 15,50% da alíquota efetiva.
REPARTICAO_PIS_COFINS_ANEXO_I = Decimal("0.0276") + Decimal("0.1274")  # 0.1550
# Alíquota efetiva usada na ESTIMATIVA: 4% (1ª faixa do Anexo I — conservador).
# O valor exato depende do RBT12 real, apurado no PGDAS.
ALIQ_EFETIVA_SIMPLES_ESTIMADA = Decimal("0.04")

AVISO_HITL = (
    "ESTIMATIVA PRELIMINAR PARA TRIAGEM — não é parecer nem cálculo de "
    "liquidação. Os valores foram apurados exclusivamente a partir dos XMLs "
    "de saída fornecidos e exigem conferência do advogado responsável com o "
    "PGDAS-D, SPED/EFD-Contribuições e a apuração de ICMS do contribuinte "
    "antes de qualquer medida administrativa ou judicial."
)

REGIMES_VALIDOS = ("simples", "lucro_presumido", "lucro_real")


def _q(v: Decimal) -> Decimal:
    return v.quantize(_CENT, rounding=ROUND_HALF_UP)


def _fmt(v: Decimal) -> str:
    """Formata Decimal em R$ pt-BR para a memória de cálculo."""
    inteiro, _, dec = f"{_q(v):,.2f}".partition(".")
    return "R$ " + inteiro.replace(",", ".") + "," + dec


def _resumo_nota(n: dict) -> dict:
    """Mapeia uma nota parseada (ok OU com erro) para o resumo que a tabela do
    frontend consome (contrato NotaAnalisada). Nota com erro vem com campos
    vazios e `erro` preenchido — o frontend a pinta em vermelho na tabela e
    deriva a lista de erros por `notas.filter(n => n.erro)`."""
    if n.get("erro"):
        return {
            "chave":          n.get("chave_acesso") or "",
            "numero":         n.get("numero"),
            "data_emissao":   None,
            "emitente_nome":  None,
            "valor_total":    0.0,
            "icms_destacado": 0.0,
            "erro":           n["erro"],
        }
    icms = sum((i["vicms"] for i in n["itens"]), _ZERO)
    emit = n.get("emitente") or {}
    return {
        "chave":          n.get("chave_acesso") or "",
        "numero":         n.get("numero"),
        "data_emissao":   n["data_emissao"].isoformat() if n.get("data_emissao") else None,
        "emitente_nome":  emit.get("nome"),
        "valor_total":    float(_q(n.get("valor_total") or _ZERO)),
        "icms_destacado": float(_q(icms)),
        "erro":           None,
    }


def _pct(v: Decimal) -> str:
    """0.0925 → '9,25%' (para a memória de cálculo)."""
    return f"{(v * 100).normalize()}".replace(".", ",") + "%"


def _data_corte_prescricao(hoje: date) -> date:
    """hoje − 5 anos (CTN art. 168, I), com fallback para 29/02."""
    try:
        return hoje.replace(year=hoje.year - 5)
    except ValueError:  # 29/02 em ano não bissexto
        return hoje.replace(year=hoje.year - 5, day=28)


def _eh_saida(cfop: str | None) -> bool:
    """CFOP de saída: começa em 5 (estadual), 6 (interestadual) ou 7 (exterior)."""
    return bool(cfop) and cfop[0] in "567"


def _eh_saida_st(cfop: str | None) -> bool:
    """CFOPs x40x — saídas com substituição tributária (5401/5403/5405/6404...)."""
    return bool(cfop) and len(cfop) == 4 and cfop[0] in "56" and cfop[1:3] == "40"


def _tese(tese_id: str, titulo: str, base_legal: list[str], fundamento: str) -> dict:
    return {
        "tese_id":            tese_id,
        "titulo":             titulo,
        "base_legal":         base_legal,
        "fundamento":         fundamento,
        "aplicavel":          False,
        "motivo_inaplicavel": None,
        "valor_estimado":     _ZERO,
        "memoria_calculo":    [],
        "alertas":            [],
        "nivel_confianca":    "estimativa_preliminar",
    }


# ── Teses ─────────────────────────────────────────────────────────────────────

def _tema_69_stf(notas_validas: list[dict], regime: str,
                 notas_prescritas: list[dict]) -> dict:
    t = _tese(
        "tema_69_stf",
        "Exclusão do ICMS da base de cálculo do PIS/COFINS (Tema 69 STF)",
        ["RE 574.706/PR (STF, Tema 69 de repercussão geral)",
         "Modulação de efeitos: fatos geradores a partir de 15/03/2017 "
         "(embargos de declaração julgados em 13/05/2021)",
         "CTN art. 168, I (prazo de 5 anos para repetição do indébito)"],
        "O ICMS destacado na nota não compõe faturamento/receita bruta e deve "
        "ser excluído da base de PIS/COFINS; o indébito dos últimos 5 anos é "
        "recuperável por compensação ou repetição.",
    )
    if regime == "simples":
        t["motivo_inaplicavel"] = (
            "Inaplicável ao Simples Nacional: PIS/COFINS são recolhidos em "
            "alíquota única dentro do DAS (LC 123/06), sem base de cálculo "
            "própria da qual o ICMS possa ser excluído."
        )
        return t

    aliq = ALIQ_PIS_COFINS[regime]
    consideradas = [n for n in notas_validas
                    if not n["data_emissao"] or n["data_emissao"] >= MODULACAO_TEMA_69]
    moduladas = [n for n in notas_validas
                 if n["data_emissao"] and n["data_emissao"] < MODULACAO_TEMA_69]

    v_icms = _ZERO
    n_notas = 0
    for nota in consideradas:
        icms_nota = sum((i["vicms"] for i in nota["itens"]
                         if _eh_saida(i["cfop"])), _ZERO)
        if icms_nota > _ZERO:
            n_notas += 1
            v_icms += icms_nota

    t["aplicavel"] = True
    t["valor_estimado"] = _q(v_icms * aliq)
    regime_txt = ("não-cumulativo (1,65% + 7,6% = 9,25%)" if regime == "lucro_real"
                  else "cumulativo (0,65% + 3% = 3,65%)")
    t["memoria_calculo"] = [
        f"1. Notas de saída próprias consideradas (CFOP 5xxx/6xxx/7xxx, "
        f"emissão a partir de 15/03/2017): {n_notas} com ICMS destacado.",
        f"2. Soma do ICMS destacado nos itens de saída: {_fmt(v_icms)}.",
        f"3. Regime {regime}: alíquota PIS/COFINS {regime_txt}.",
        f"4. Crédito estimado = {_fmt(v_icms)} × {_pct(aliq)} = "
        f"{_fmt(v_icms * aliq)}.",
    ]
    if moduladas:
        t["alertas"].append(
            f"{len(moduladas)} nota(s) anterior(es) a 15/03/2017 excluída(s) "
            "da soma pela modulação de efeitos do Tema 69."
        )
    if notas_prescritas:
        t["alertas"].append(
            f"{len(notas_prescritas)} nota(s) fora da janela de 5 anos "
            "(CTN art. 168, I) excluída(s) da soma."
        )
    t["alertas"].append(
        "Conferir com a EFD-Contribuições se o ICMS já foi excluído da base "
        "nas apurações do período (a exclusão é obrigatória desde a IN RFB "
        "2.121/22, art. 26, XII)."
    )
    return t


def _monofasicos_simples(notas_validas: list[dict], regime: str,
                         notas_prescritas: list[dict]) -> dict:
    t = _tese(
        "monofasicos_simples",
        "PIS/COFINS monofásicos revendidos por optante do Simples Nacional",
        ["LC 123/06, art. 18, §4º-A, I (segregação de receitas monofásicas)",
         "Lei 9.718/98, art. 4º (combustíveis)",
         "Lei 10.147/00 (medicamentos, perfumaria e higiene)",
         "Lei 10.485/02 (pneus, câmaras e autopeças)",
         "Lei 13.097/15 (bebidas frias)",
         "CTN art. 168, I (prazo de 5 anos)"],
        "Na revenda de produtos com PIS/COFINS já recolhidos pelo fabricante "
        "(monofasia), o optante do Simples pode segregar essas receitas e "
        "excluir a parcela de PIS/COFINS do DAS, recuperando o que pagou em "
        "duplicidade nos últimos 5 anos.",
    )
    if regime != "simples":
        t["motivo_inaplicavel"] = (
            "Tese específica da segregação de receitas do Simples Nacional "
            "(LC 123/06, art. 18, §4º-A). No lucro real/presumido a monofasia "
            "opera por alíquota zero na revenda, sem crédito a segregar no DAS."
        )
        return t

    receita_mono = _ZERO
    itens_mono = 0
    bases_detectadas: set[str] = set()
    for nota in notas_validas:
        for item in nota["itens"]:
            ncm = (item["ncm"] or "")
            if not _eh_saida(item["cfop"]):
                continue
            for prefixo, base in NCM_MONOFASICOS.items():
                if ncm.startswith(prefixo):
                    receita_mono += item["vprod"]
                    itens_mono += 1
                    bases_detectadas.add(f"NCM {prefixo}: {base}")
                    break

    parcela = ALIQ_EFETIVA_SIMPLES_ESTIMADA * REPARTICAO_PIS_COFINS_ANEXO_I
    if itens_mono == 0:
        t["aplicavel"] = True  # tese cabível no regime; sem itens detectados
        t["valor_estimado"] = _ZERO
        t["memoria_calculo"] = [
            "1. Nenhum item com NCM monofásico detectado nas notas de saída "
            "analisadas — receita segregável estimada em R$ 0,00.",
        ]
    else:
        t["aplicavel"] = True
        t["valor_estimado"] = _q(receita_mono * parcela)
        t["memoria_calculo"] = [
            f"1. Itens de saída com NCM monofásico detectados: {itens_mono} "
            f"— receita segregável de {_fmt(receita_mono)}.",
            "2. Bases legais dos NCMs detectados: "
            + "; ".join(sorted(bases_detectadas)) + ".",
            "3. Parcela PIS/COFINS estimada pela repartição do Anexo I da "
            "LC 123/06 (PIS 2,76% + COFINS 12,74% = 15,50% do DAS) sobre "
            "alíquota efetiva estimada de 4% (1ª faixa do Anexo I) → "
            f"{_pct(parcela)} da receita segregada.",
            f"4. Crédito estimado = {_fmt(receita_mono)} × {_pct(parcela)} "
            f"= {_fmt(receita_mono * parcela)}.",
        ]
        t["alertas"].append(
            "Valor estimado pela repartição do Anexo I com alíquota efetiva "
            "de 4%: o valor EXATO depende da alíquota efetiva real de cada "
            "competência, apurada no PGDAS-D (RBT12 e anexo aplicável)."
        )
    t["alertas"].append(
        "Autopeças (Lei 10.485/02, Anexos I e II) também são monofásicas, "
        "mas a identificação exige conferência item a item dos anexos — não "
        "foram detectadas automaticamente por NCM."
    )
    t["alertas"].append(
        "Prescrição: apenas competências dos últimos 5 anos são recuperáveis "
        "(CTN art. 168, I)."
    )
    if notas_prescritas:
        t["alertas"].append(
            f"{len(notas_prescritas)} nota(s) fora da janela de 5 anos "
            "excluída(s) da soma."
        )
    return t


def _icms_st_ressarcimento(notas_validas: list[dict], regime: str) -> dict:
    t = _tese(
        "icms_st_ressarcimento",
        "Ressarcimento de ICMS-ST — venda abaixo da base presumida (radar)",
        ["RE 593.849/MG (STF, Tema 201 de repercussão geral)",
         "CF/88, art. 150, §7º (restituição na não ocorrência do fato "
         "gerador presumido)"],
        "Quando a venda efetiva ao consumidor sai por valor MENOR que a base "
        "presumida da substituição tributária, o contribuinte substituído tem "
        "direito ao ressarcimento da diferença de ICMS-ST (Tema 201 STF).",
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
            "Nenhuma saída com CFOP de substituição tributária (x40x) "
            "detectada nas notas analisadas."
        )
        return t

    t["aplicavel"] = True
    t["valor_estimado"] = _ZERO  # radar: sem base presumida no XML de saída
    t["memoria_calculo"] = [
        f"1. {len(notas_st)} nota(s) com CFOP de saída sob substituição "
        f"tributária (x40x), somando {_fmt(receita_st)} em produtos.",
        "2. Valor estimado = R$ 0,00: o XML de saída NÃO traz a base "
        "presumida (MVA/PMPF) retida na etapa anterior — sem ela não há "
        "cálculo honesto da diferença.",
    ]
    t["alertas"].append(
        "Potencial de ressarcimento detectado, mas o cálculo exige as GIAs/"
        "apuração de ICMS-ST e as notas de AQUISIÇÃO com o ICMS-ST retido "
        "(base presumida). Solicite esses documentos para quantificar."
    )
    return t


# ── Consolidação ──────────────────────────────────────────────────────────────

def analisar_recuperacao(notas: list[dict], regime: str,
                         hoje: date | None = None) -> dict:
    """
    Consolida as teses de recuperação sobre as notas parseadas.
    `notas` é a saída de nfe_parser.parse_lote (notas com `erro` são contadas
    e ignoradas nos cálculos). Determinístico e stateless.
    """
    if regime not in REGIMES_VALIDOS:
        raise ValueError(f"Regime inválido: {regime!r}. Use um de {REGIMES_VALIDOS}.")
    hoje = hoje or date.today()
    corte = _data_corte_prescricao(hoje)

    notas_ok = [n for n in notas if not n.get("erro")]
    notas_erro = [n for n in notas if n.get("erro")]

    # d) prescrição (CTN 168, I): fora da janela de 5 anos → fora das somas
    prescritas = [n for n in notas_ok
                  if n["data_emissao"] and n["data_emissao"] < corte]
    prescritas_ids = {id(n) for n in prescritas}
    validas = [n for n in notas_ok if id(n) not in prescritas_ids]

    teses = [
        _tema_69_stf(validas, regime, prescritas),
        _monofasicos_simples(validas, regime, prescritas),
        _icms_st_ressarcimento(validas, regime),
    ]

    alertas_globais: list[str] = []
    if prescritas:
        alertas_globais.append(
            f"{len(prescritas)} nota(s) com emissão anterior a "
            f"{corte.strftime('%d/%m/%Y')} está(ão) fora da janela de "
            "repetição de indébito (CTN art. 168, I) e foi(ram) excluída(s) "
            "de todas as somas."
        )
    if notas_erro:
        alertas_globais.append(
            f"{len(notas_erro)} arquivo(s) não pôde(ram) ser lido(s) como "
            "NF-e válida — ver campo `erro` de cada um em `notas_com_erro`."
        )

    datas = sorted(n["data_emissao"] for n in notas_ok if n["data_emissao"])
    total = sum((t["valor_estimado"] for t in teses), _ZERO)

    # base_legal sai como STRING única (contrato do frontend); internamente
    # cada tese guarda a lista — junta-se aqui na fronteira de saída.
    for t in teses:
        if isinstance(t["base_legal"], (list, tuple)):
            t["base_legal"] = " · ".join(t["base_legal"])
        t["valor_estimado"] = float(t["valor_estimado"])

    return {
        "regime":           regime,
        "total_estimado":   float(_q(total)),
        "notas_analisadas": len(notas_ok),
        "notas_com_erro":   len(notas_erro),
        "notas_prescritas": len(prescritas),
        "periodo": {
            "inicio": datas[0].isoformat() if datas else None,
            "fim":    datas[-1].isoformat() if datas else None,
        },
        "teses":           teses,
        "alertas_globais": alertas_globais,
        "aviso_hitl":      AVISO_HITL,
        "notas":           [_resumo_nota(n) for n in notas],
    }
