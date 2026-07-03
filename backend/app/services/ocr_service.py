# ── app/services/ocr_service.py ──────────────────────────────────────────────
# Extração de texto de documentos para busca por conteúdo.
# PDF nativo: PyMuPDF (rápido). PDF escaneado/imagens: Tesseract (se instalado).
# XML (NF-e): parse seguro (defusedxml se instalado; senão stdlib com bloqueio
# de DTD/entidades) + extração de campos fiscais estruturados.
# Falha de OCR NUNCA quebra o upload — apenas registra log.
from __future__ import annotations
import logging
import re

logger = logging.getLogger("ejc.ocr")

# Imports lazy/opcionais — sistema funciona sem OCR de imagem
try:
    import fitz  # PyMuPDF
    _PDF_OK = True
except ImportError:
    _PDF_OK = False

try:
    import pytesseract
    from PIL import Image
    _TESS_OK = True
except ImportError:
    _TESS_OK = False

try:
    import docx as _docx  # python-docx
    _DOCX_OK = True
except ImportError:
    _DOCX_OK = False

# XML: defusedxml (proteção XXE/billion-laughs nativa) com fallback stdlib.
# No fallback, XMLs com DTD/ENTITY são REJEITADOS antes do parse (ver _xml_root).
try:
    from defusedxml import ElementTree as _ET  # type: ignore
    _DEFUSED = True
except ImportError:
    import xml.etree.ElementTree as _ET  # noqa: N814
    _DEFUSED = False

MAX_OCR_CHARS = 200_000  # limite de armazenamento por documento


def extrair_texto(filepath: str, mimetype: str | None) -> str | None:
    """
    Retorna texto extraído (truncado) ou None se tipo não suportado/falha.
    Síncrono — chamado via asyncio.to_thread no router.
    """
    mt = (mimetype or "").lower()
    try:
        if "pdf" in mt and _PDF_OK:
            return _pdf(filepath)
        if mt.startswith("image/") and _TESS_OK:
            return _imagem(filepath)
        if ("wordprocessingml" in mt or filepath.endswith(".docx")) and _DOCX_OK:
            return _docx_texto(filepath)
        # XML antes do ramo text/ (text/xml também começa com "text/")
        if "xml" in mt or filepath.lower().endswith(".xml"):
            res = extrair_xml(filepath)
            return res.get("texto") if res else None
        if mt.startswith("text/") or filepath.endswith(".txt"):
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                return f.read()[:MAX_OCR_CHARS]
    except Exception as e:
        logger.warning(f"OCR falhou para {filepath}: {e}")
    return None


def _pdf(path: str) -> str:
    doc = fitz.open(path)
    partes = []
    for page in doc:
        txt = page.get_text("text")
        # Página sem texto nativo (escaneada) → tentar Tesseract na imagem
        if len(txt.strip()) < 20 and _TESS_OK:
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            txt = pytesseract.image_to_string(img, lang="por")
        partes.append(txt)
        if sum(len(p) for p in partes) > MAX_OCR_CHARS:
            break
    doc.close()
    return "\n".join(partes)[:MAX_OCR_CHARS]


def _imagem(path: str) -> str:
    return pytesseract.image_to_string(Image.open(path), lang="por")[:MAX_OCR_CHARS]


def _docx_texto(path: str) -> str:
    d = _docx.Document(path)
    return "\n".join(p.text for p in d.paragraphs)[:MAX_OCR_CHARS]


# ── XML / NF-e ────────────────────────────────────────────────────────────────

def _xml_root(bruto: str):
    """Parse seguro de XML. Sem defusedxml, rejeita DTD/entidades customizadas
    (mitigação de XXE e billion laughs no stdlib)."""
    if not _DEFUSED and re.search(r"<!\s*(DOCTYPE|ENTITY)", bruto, re.I):
        raise ValueError("XML com DTD/ENTITY rejeitado (defusedxml não instalado)")
    return _ET.fromstring(bruto)


def _local(tag) -> str:
    """Nome local do elemento, ignorando namespace ({ns}Tag → Tag)."""
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _extrair_nfe(root, bruto: str) -> dict | None:
    """
    Se o XML for uma NF-e (nfeProc/NFe/infNFe), extrai campos fiscais:
    chave de acesso (44 dígitos), CNPJ do emitente, valor total (vNF) e NCMs.
    Retorna None se o XML não for NF-e.
    """
    eh_nfe = any(_local(e.tag) in {"nfeProc", "NFe", "infNFe"} for e in root.iter())
    if not eh_nfe:
        return None

    chave = None
    for el in root.iter():
        if _local(el.tag) == "infNFe":
            digits = re.sub(r"\D", "", el.get("Id") or "")
            if len(digits) == 44:
                chave = digits
            break
    if not chave:  # fallback: 44 dígitos consecutivos no texto bruto
        m = re.search(r"(?<!\d)\d{44}(?!\d)", bruto)
        chave = m.group(0) if m else None

    cnpj_emitente = None
    for el in root.iter():
        if _local(el.tag) == "emit":
            for c in el.iter():
                if _local(c.tag) == "CNPJ" and c.text:
                    cnpj_emitente = re.sub(r"\D", "", c.text) or None
                    break
            break

    valor_total = None
    for el in root.iter():
        if _local(el.tag) == "ICMSTot":
            for c in el.iter():
                if _local(c.tag) == "vNF" and c.text:
                    try:
                        valor_total = float(c.text.strip())
                    except ValueError:
                        pass
                    break
            break

    ncms = sorted({
        e.text.strip() for e in root.iter()
        if _local(e.tag) == "NCM" and e.text and e.text.strip()
    })

    return {
        "chave_acesso": chave,
        "cnpj_emitente": cnpj_emitente,
        "valor_total": valor_total,
        "ncms": ncms,
    }


def extrair_xml(filepath: str) -> dict | None:
    """
    Extrai texto pesquisável de um XML e, se for NF-e, campos estruturados.
    Retorno: {"texto": str|None, "nfe": dict|None} ou None em falha de parse.
    Síncrono — chamar via asyncio.to_thread (mesmo padrão de extrair_texto).
    """
    try:
        with open(filepath, encoding="utf-8", errors="ignore") as f:
            bruto = f.read(MAX_OCR_CHARS * 2)
        root = _xml_root(bruto)
    except Exception as e:
        logger.warning(f"Parse XML falhou para {filepath}: {e}")
        return None

    texto = "\n".join(
        t.strip() for t in root.itertext() if t and t.strip()
    )[:MAX_OCR_CHARS] or None

    nfe = None
    try:
        nfe = _extrair_nfe(root, bruto)
    except Exception as e:
        # LGPD: log sem dados do documento — apenas o caminho e o erro
        logger.warning(f"Extração NF-e falhou para {filepath}: {e}")

    return {"texto": texto, "nfe": nfe}
