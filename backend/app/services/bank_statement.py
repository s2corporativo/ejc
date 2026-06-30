# ── app/services/bank_statement.py ───────────────────────────────────────────
# Parsers de extrato (OFX/CSV/PDF genérico) + motor de detecção de cobranças
# abusivas com base legal. Determinístico (sem IA). MVP: parser genérico;
# parsers por banco podem ser adicionados depois.
from __future__ import annotations
import re
import csv as _csv
import io
from datetime import datetime, date
from typing import Optional


# ─────────────────────────── normalização ────────────────────────────────────
def _num(s) -> Optional[float]:
    """Converte '1.234,56' / 'R$ -50,00' / '50.00' em float."""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    neg = t.startswith("-") or t.endswith("-") or "(" in t
    t = t.replace("(", "").replace(")", "").lstrip("-").rstrip("-")
    # Brasil: ponto = milhar, vírgula = decimal
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        v = float(t)
        return -v if neg else v
    except ValueError:
        return None


def _data(s) -> Optional[date]:
    if not s:
        return None
    s = str(s).strip()[:10]
    for fmt in ("%Y%m%d", "%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _tx(data, descricao, valor, saldo=None) -> dict:
    v = _num(valor)
    return {
        "data": _data(data),
        "descricao": (str(descricao or "").strip())[:500],
        "valor": abs(v) if v is not None else None,
        "tipo": ("debito" if (v is not None and v < 0) else "credito"),
        "saldo": _num(saldo),
    }


# ─────────────────────────────── parsers ─────────────────────────────────────
def parse_ofx(conteudo: str) -> list[dict]:
    """OFX (SGML) — extrai blocos <STMTTRN>."""
    txs = []
    for bloco in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", conteudo, re.DOTALL | re.IGNORECASE):
        def tag(t):
            m = re.search(rf"<{t}>([^<\r\n]*)", bloco, re.IGNORECASE)
            return m.group(1).strip() if m else ""
        memo = tag("MEMO") or tag("NAME")
        txs.append(_tx(tag("DTPOSTED"), memo, tag("TRNAMT")))
    return txs


def parse_csv(conteudo: str) -> list[dict]:
    """CSV genérico — detecta delimitador e colunas (data/descrição/valor)."""
    delim = ";" if conteudo.count(";") > conteudo.count(",") else ","
    linhas = list(_csv.reader(io.StringIO(conteudo), delimiter=delim))
    if not linhas:
        return []
    header = [c.strip().lower() for c in linhas[0]]

    def achar(*nomes):
        for i, h in enumerate(header):
            if any(n in h for n in nomes):
                return i
        return None

    i_data = achar("data", "date")
    i_desc = achar("descri", "histor", "lançamento", "lancamento", "memo", "title", "estabelec")
    i_val = achar("valor", "amount", "value", "montante")
    tem_header = i_data is not None or i_val is not None
    txs = []
    for row in (linhas[1:] if tem_header else linhas):
        if not row or len(row) < 2:
            continue
        d = row[i_data] if i_data is not None and i_data < len(row) else (row[0] if row else "")
        desc = row[i_desc] if i_desc is not None and i_desc < len(row) else (row[1] if len(row) > 1 else "")
        val = row[i_val] if i_val is not None and i_val < len(row) else (row[-1] if row else "")
        if _num(val) is None and _data(d) is None:
            continue
        txs.append(_tx(d, desc, val))
    return txs


def parse_pdf(caminho: str) -> list[dict]:
    """PDF genérico — extrai texto via PyMuPDF e busca linhas (data … valor).
    Best-effort: extratos têm layouts variados; parser por banco melhora a precisão."""
    import fitz  # PyMuPDF
    texto = ""
    with fitz.open(caminho) as doc:
        for pag in doc:
            texto += pag.get_text("text") + "\n"
    txs = []
    # linha: dd/mm[/aaaa]  <descrição>  <valor com vírgula decimal>
    padrao = re.compile(
        r"(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)\s+(-?\(?\s*R?\$?\s*[\d.]+,\d{2}\)?-?)\s*$"
    )
    for linha in texto.splitlines():
        m = padrao.search(linha.strip())
        if m:
            txs.append(_tx(m.group(1), m.group(2), m.group(3)))
    return txs


def parse_extrato(formato: str, conteudo_ou_caminho) -> list[dict]:
    f = (formato or "").lower()
    if f == "ofx":
        return parse_ofx(conteudo_ou_caminho)
    if f == "csv":
        return parse_csv(conteudo_ou_caminho)
    if f == "pdf":
        return parse_pdf(conteudo_ou_caminho)
    raise ValueError(f"Formato não suportado: {formato}")


# ──────────────────── motor de detecção de cobranças abusivas ─────────────────
# Cada regra: (regra, titulo, base_legal, prioridade, padrão regex na descrição).
# Aplica-se a DÉBITOS. Base legal só citada quando há fundamento — respeita a
# regra do escritório de não inventar. Os achados são INDÍCIOS p/ revisão (OAB).
REGRAS = [
    ("TAC", "Tarifa de Abertura de Crédito (TAC/TEC)",
     "CMN Res. 3.518/2007; STJ Tema 618", "URGENTE",
     r"\b(tac|tec)\b|tarifa de abertura|abertura de cr[ée]dito|tarifa de emiss[ãa]o|tarifa de cadastr"),
    ("SEGURO", "Seguro atrelado ao crédito (possível venda casada)",
     "CDC art. 39, I; BCB Res. 4.860/2020", "URGENTE",
     r"seguro|prestamista|prote[çc][ãa]o financeira"),
    ("JUROS_ROTATIVO", "Juros do rotativo — comparar à média BACEN",
     "Súmula 530 STJ", "URGENTE",
     r"rotativ|juros.*(cart[ãa]o|do m[êe]s)|encargo.*rotativ"),
    ("IOF", "IOF — verificar base de cálculo",
     "Dec. 6.306/2007", "MEDIO",
     r"\biof\b"),
    ("MORA_MULTA", "Multa/mora — verificar limites (multa ≤ 2%; mora ≤ 1% a.m.)",
     "CDC art. 52, §1º; CC art. 406", "MEDIO",
     r"\bmulta\b|\bmora\b|encargo.*atraso|juros de mora"),
    ("TARIFA_PIX", "Tarifa de PIX — PF/MEI deve ser isento",
     "BCB Res. BCB nº 1/2020", "MEDIO",
     r"(tarifa|taxa).*pix|pix.*(tarifa|taxa)"),
    ("PACOTE_SERVICOS", "Pacote/cesta de serviços — verificar autorização",
     "BCB Res. 97/2021", "MEDIO",
     r"pacote.*servi|cesta.*relacionamento|cesta.*servi|mensalidade.*conta|tarifa de manuten"),
    ("ANUIDADE", "Anuidade de cartão — verificar contratação",
     "BCB Res. 97/2021", "MEDIO",
     r"anuidade"),
]
_GENERICA = ("TARIFA_RESTRITIVO", "Tarifa com nomenclatura não padronizada",
             "CDC art. 46; BCB Res. 97/2021", "URGENTE",
             r"\b(tarifa|taxa|t[aá]rif)\b")


def detectar_abusivas(transacoes: list[dict]) -> list[dict]:
    achados = []
    vistos_genericos = set()
    # contagem p/ duplicatas (descrição normalizada + valor, no mesmo mês)
    chave_cont: dict = {}
    for t in transacoes:
        if t["tipo"] != "debito" or t["valor"] is None:
            continue
        mes = t["data"].strftime("%Y-%m") if t["data"] else "?"
        dn = re.sub(r"\s+", " ", (t["descricao"] or "").lower()).strip()
        chave_cont[(mes, dn, round(t["valor"], 2))] = chave_cont.get((mes, dn, round(t["valor"], 2)), 0) + 1

    for t in transacoes:
        desc = (t["descricao"] or "").lower()
        if t["valor"] is None:
            continue
        casou = False
        # débitos: regras de cobrança
        if t["tipo"] == "debito":
            for regra, titulo, base, prio, pad in REGRAS:
                if re.search(pad, desc):
                    achados.append(_achado(t, regra, titulo, base, prio))
                    casou = True
            if not casou and re.search(_GENERICA[4], desc):
                achados.append(_achado(t, *_GENERICA[:4]))
                casou = True
            # duplicata
            mes = t["data"].strftime("%Y-%m") if t["data"] else "?"
            dn = re.sub(r"\s+", " ", desc).strip()
            if chave_cont.get((mes, dn, round(t["valor"], 2)), 0) >= 2:
                k = (mes, dn, round(t["valor"], 2))
                if k not in vistos_genericos:
                    vistos_genericos.add(k)
                    achados.append(_achado(
                        t, "DUPLICATA", "Débito duplicado no mês (verificar)",
                        "STJ REsp 1.395.551", "URGENTE"))
        # créditos: estorno sugestivo (banco reconheceu)
        elif re.search(r"estorno", desc):
            achados.append(_achado(
                t, "ESTORNO_SUGESTIVO", "Estorno pelo banco (indício de reconhecimento)",
                "CDC art. 42", "MEDIO"))
    return achados


def _achado(t, regra, titulo, base, prio) -> dict:
    return {
        "transaction": t, "regra": regra, "titulo": titulo,
        "base_legal": base, "prioridade": prio, "valor": t["valor"],
        "descricao": f"{t['descricao']} — R$ {t['valor']:.2f}"
                     + (f" em {t['data'].strftime('%d/%m/%Y')}" if t["data"] else ""),
    }
