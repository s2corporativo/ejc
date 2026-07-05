# ── app/services/fiscal/nfe_parser.py ────────────────────────────────────────
# Parser SEGURO de NF-e (XML de terceiros → XXE é vetor real: defusedxml
# obrigatório, nunca xml.etree cru — mesmo racional de ocr_service.py).
#
# Aceita os dois formatos reais: <nfeProc> (com protNFe) e <NFe> "bare".
# Namespace http://www.portalfiscal.inf.br/nfe tratado por NOME LOCAL
# (wildcard): XMLs reais variam entre ns default, prefixado e ausente.
#
# Valores monetários SEMPRE em Decimal (padrão do projeto — services/calc/cet.py).
# Fail-soft por arquivo: XML inválido ou nota duplicada NÃO derruba o lote —
# a nota volta com o campo `erro` preenchido e o restante segue.
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation

from defusedxml import ElementTree as ET

_ZERO = Decimal("0")


def _local(tag) -> str:
    """Nome local do elemento, ignorando namespace ({ns}Tag → Tag)."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _find(el, nome_local: str):
    """Primeiro descendente com o nome local dado (wildcard de namespace)."""
    if el is None:
        return None
    for c in el.iter():
        if _local(c.tag) == nome_local:
            return c
    return None


def _texto(el, nome_local: str) -> str | None:
    achado = _find(el, nome_local)
    if achado is not None and achado.text and achado.text.strip():
        return achado.text.strip()
    return None


def _dec(txt: str | None) -> Decimal:
    """Converte texto do XML em Decimal; ausente/ilegível → 0 (não inventa)."""
    if not txt:
        return _ZERO
    try:
        return Decimal(txt.strip())
    except (InvalidOperation, AttributeError):
        return _ZERO


def _data_emissao(ide) -> date | None:
    """dhEmi (v3/v4: '2024-05-10T14:30:00-03:00') ou dEmi legado ('2024-05-10')."""
    bruto = _texto(ide, "dhEmi") or _texto(ide, "dEmi")
    if not bruto:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", bruto)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _parse_emitente(inf_nfe) -> dict:
    emit = _find(inf_nfe, "emit")
    return {
        "cnpj": re.sub(r"\D", "", _texto(emit, "CNPJ") or "") or None,
        "nome": _texto(emit, "xNome"),
        "uf":   _texto(_find(emit, "enderEmit"), "UF") if emit is not None else None,
        # CRT: 1 = Simples Nacional, 3 = Regime normal (NT 2013.005)
        "crt":  _texto(emit, "CRT"),
    }


def _parse_destinatario(inf_nfe) -> dict:
    dest = _find(inf_nfe, "dest")
    doc = None
    if dest is not None:
        doc = _texto(dest, "CNPJ") or _texto(dest, "CPF")
        doc = re.sub(r"\D", "", doc or "") or None
    return {
        "doc":  doc,
        "nome": _texto(dest, "xNome"),
        "uf":   _texto(_find(dest, "enderDest"), "UF") if dest is not None else None,
    }


def _parse_item(det) -> dict:
    prod = _find(det, "prod")
    imposto = _find(det, "imposto")

    # ICMS: grupo <ICMS>/<ICMSxx|ICMSSNxxx> — CST (regime normal) OU CSOSN
    # (Simples). vICMS pode não existir (não destacado) → 0.
    cst_icms = csosn = None
    v_icms = _ZERO
    grupo_icms = _find(imposto, "ICMS")
    if grupo_icms is not None:
        csosn = _texto(grupo_icms, "CSOSN")
        cst_icms = _texto(grupo_icms, "CST") if csosn is None else None
        v_icms = _dec(_texto(grupo_icms, "vICMS"))

    # PIS/COFINS/IPI: busca escopada em cada grupo, para não capturar o vPIS
    # de outro tributo por acidente.
    v_pis = _dec(_texto(_find(imposto, "PIS"), "vPIS"))
    v_cofins = _dec(_texto(_find(imposto, "COFINS"), "vCOFINS"))
    v_ipi = _dec(_texto(_find(imposto, "IPI"), "vIPI"))

    try:
        numero = int(det.get("nItem") or 0)
    except ValueError:
        numero = 0

    return {
        "numero":    numero,
        "descricao": _texto(prod, "xProd"),
        "ncm":       _texto(prod, "NCM"),
        "cfop":      _texto(prod, "CFOP"),
        "cst_icms":  cst_icms,
        "csosn":     csosn,
        "vprod":     _dec(_texto(prod, "vProd")),
        "vicms":     v_icms,
        "vpis":      v_pis,
        "vcofins":   v_cofins,
        "vipi":      v_ipi,
    }


def _nota_erro(arquivo: str, erro: str) -> dict:
    return {"arquivo": arquivo, "erro": erro}


def parse_nfe(conteudo: bytes | str, arquivo: str = "") -> dict:
    """
    Parse de UM XML de NF-e (nfeProc ou NFe bare). Retorna a nota estruturada;
    em falha, {"arquivo": ..., "erro": ...} (fail-soft — nunca lança).
    """
    try:
        if isinstance(conteudo, bytes):
            conteudo = conteudo.decode("utf-8", errors="replace")
        root = ET.fromstring(conteudo)
    except Exception as e:  # inclui DTD/entidades bloqueadas pelo defusedxml
        return _nota_erro(arquivo, f"XML inválido ou inseguro: {e}")

    raiz_local = _local(root.tag)
    if raiz_local not in {"nfeProc", "NFe"}:
        return _nota_erro(arquivo, f"XML não é NF-e (raiz <{raiz_local}>): "
                                   "esperado <nfeProc> ou <NFe>.")

    inf_nfe = _find(root, "infNFe")
    if inf_nfe is None:
        return _nota_erro(arquivo, "NF-e sem elemento <infNFe>.")

    chave = re.sub(r"\D", "", inf_nfe.get("Id") or "")
    if len(chave) != 44:
        return _nota_erro(
            arquivo, "Chave de acesso inválida no Id do infNFe "
                     f"({len(chave)} dígitos; esperado 44).")

    ide = _find(inf_nfe, "ide")
    icms_tot = _find(_find(inf_nfe, "total"), "ICMSTot")

    itens = [_parse_item(det) for det in inf_nfe.iter() if _local(det.tag) == "det"]

    return {
        "arquivo":       arquivo,
        "erro":          None,
        "chave_acesso":  chave,
        "numero":        _texto(ide, "nNF"),
        "serie":         _texto(ide, "serie"),
        "data_emissao":  _data_emissao(ide),
        "emitente":      _parse_emitente(inf_nfe),
        "destinatario":  _parse_destinatario(inf_nfe),
        "valor_total":   _dec(_texto(icms_tot, "vNF")),
        "itens":         itens,
    }


def parse_lote(arquivos: list[tuple[str, bytes]]) -> list[dict]:
    """
    Parse de um lote [(nome_arquivo, conteudo_bytes), ...]. Nota com a MESMA
    chave de acesso de outra já vista no lote vira erro (duplicada) — as somas
    do motor de teses não podem contar a mesma nota duas vezes.
    """
    vistos: set[str] = set()
    notas: list[dict] = []
    for nome, conteudo in arquivos:
        nota = parse_nfe(conteudo, arquivo=nome)
        chave = nota.get("chave_acesso")
        if not nota.get("erro") and chave:
            if chave in vistos:
                nota = _nota_erro(nome, f"Nota duplicada no lote (chave {chave}).")
            else:
                vistos.add(chave)
        notas.append(nota)
    return notas
