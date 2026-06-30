# ── app/services/ocr_service.py ──────────────────────────────────────────────
# Extração de texto de documentos para busca por conteúdo.
# PDF nativo: PyMuPDF (rápido). PDF escaneado/imagens: Tesseract (se instalado).
# Falha de OCR NUNCA quebra o upload — apenas registra log.
from __future__ import annotations
import logging

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
