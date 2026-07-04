# ── tests/test_ocr_service.py ────────────────────────────────────────────────
# OCR service (Fase 3A) — API baseada em bytes usada por /rag/ingest-pdf.
# PDF sintético gerado com reportlab (texto nativo → não exige tesseract).
import io

import pytest

from app.services.extracao_estruturada import extrair_estruturas
from app.services.ocr_service import (
    extrair_texto_imagem,
    extrair_texto_pdf,
    ocr_disponivel,
)


def _pdf_sintetico(linhas: list[str]) -> bytes:
    """Gera um PDF de 1 página com texto nativo via reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    y = 800
    for linha in linhas:
        c.drawString(50, y, linha)
        y -= 20
    c.showPage()
    c.save()
    return buf.getvalue()


def test_pdf_texto_nativo_extraido_sem_ocr():
    raw = _pdf_sintetico([
        "CONTRATO DE HONORARIOS ADVOCATICIOS",
        "Processo 0001234-56.2024.8.13.0027",
        "Contratante: CPF 529.982.247-25",
        "Valor: R$ 15.000,00",
    ])
    res = extrair_texto_pdf(raw)
    assert res["paginas"] == 1
    assert res["paginas_ocr"] == 0          # texto nativo — OCR não acionado
    assert "CONTRATO DE HONORARIOS" in res["texto"]
    assert "0001234-56.2024.8.13.0027" in res["texto"]


def test_pdf_extraido_alimenta_extracao_estruturada():
    """Fluxo do /rag/ingest-pdf: PDF → texto → extração estruturada."""
    raw = _pdf_sintetico([
        "Processo 0001234-56.2024.8.13.0027",
        "CPF 529.982.247-25 e CNPJ 11.222.333/0001-81",
        "Condenacao de R$ 15.000,00 em 15/03/2024",
    ])
    texto = extrair_texto_pdf(raw)["texto"]
    ex = extrair_estruturas(texto)
    assert [o["valor"] for o in ex["processos_cnj"]] == ["0001234-56.2024.8.13.0027"]
    assert [o["valor"] for o in ex["cpfs"]] == ["529.982.247-25"]
    assert [o["valor"] for o in ex["cnpjs"]] == ["11.222.333/0001-81"]
    assert "R$ 15.000,00" in [o["valor"] for o in ex["valores"]]
    assert "15/03/2024" in [o["valor"] for o in ex["datas"]]


def test_pdf_invalido_levanta_valueerror():
    with pytest.raises(ValueError):
        extrair_texto_pdf(b"isto nao e um pdf")


def test_pdf_pagina_em_branco_nao_quebra():
    """Página sem texto: com tesseract ausente, degrada para vazio sem exceção."""
    import fitz
    doc = fitz.open()          # PDF vazio
    doc.new_page()             # 1 página em branco (equivale a escaneada s/ OCR)
    raw = doc.tobytes()
    doc.close()
    res = extrair_texto_pdf(raw)
    assert res["paginas"] == 1
    assert isinstance(res["texto"], str)
    assert res["ocr_disponivel"] == ocr_disponivel()
    if not res["ocr_disponivel"]:
        assert res["paginas_ocr"] == 0


def test_imagem_sem_tesseract_degrada_gracioso():
    """PNG válido: sem tesseract → texto vazio; com tesseract → não explode."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(buf, format="PNG")
    res = extrair_texto_imagem(buf.getvalue())
    assert res["paginas"] == 1
    assert isinstance(res["texto"], str)


def test_imagem_invalida_levanta_valueerror():
    if not ocr_disponivel():
        pytest.skip("tesseract ausente — validação da imagem não é alcançada")
    with pytest.raises(ValueError):
        extrair_texto_imagem(b"nao e imagem")


@pytest.mark.skipif(not ocr_disponivel(), reason="binário tesseract ausente")
def test_ocr_real_em_pdf_escaneado():
    """PDF 'escaneado' (página renderizada como imagem) → OCR recupera o texto."""
    import fitz
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (800, 200), "white")
    ImageDraw.Draw(img).text((40, 80), "PROCESSO JUDICIAL 12345", fill="black")
    ibuf = io.BytesIO()
    img.save(ibuf, format="PNG")
    doc = fitz.open()
    page = doc.new_page(width=800, height=200)
    page.insert_image(fitz.Rect(0, 0, 800, 200), stream=ibuf.getvalue())
    raw = doc.tobytes()
    doc.close()
    res = extrair_texto_pdf(raw)
    assert res["paginas_ocr"] == 1
    assert "12345" in res["texto"]
