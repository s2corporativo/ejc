#!/usr/bin/env python3
"""Gera arquivos de teste com magic bytes reais para a bateria M10."""
import io
import zipfile

TXT = b"EJC_QA M10 documento de teste - homologacao de homologacao " * 50


def pdf():
    """PDF mínimo detectado por libmagic como application/pdf."""
    return (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n")


def xlsx():
    """XLSX mínimo válido (ZIP OOXML) detectado como
    application/vnd.openxmlformats-officedocument.spreadsheetml.sheet."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml",
                    '<?xml version="1.0"?>'
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                    '<Default Extension="xml" ContentType="application/xml"/>'
                    '<Override PartName="/xl/workbook.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                    '<Override PartName="/xl/worksheets/sheet1.xml" '
                    'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                    "</Types>")
        zf.writestr("docProps/app.xml",
                    '<?xml version="1.0"?><Properties/>')
        zf.writestr("_rels/.rels",
                    '<?xml version="1.0"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
                    'Target="xl/workbook.xml"/>'
                    "</Relationships>")
        zf.writestr("xl/_rels/workbook.xml.rels",
                    '<?xml version="1.0"?>'
                    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                    'Target="worksheets/sheet1.xml"/>'
                    "</Relationships>")
        zf.writestr("xl/workbook.xml",
                    '<?xml version="1.0"?>'
                    '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    "<sheets><sheet name=\"Plan1\" sheetId=\"1\" r:id=\"rId1\" "
                    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></sheets>'
                    "</workbook>")
        zf.writestr("xl/worksheets/sheet1.xml",
                    '<?xml version="1.0"?>'
                    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                    "<sheetData/></worksheet>")
    return buf.getvalue()


def png():
    """PNG mínimo real (IHDR + IEND) detectado como image/png."""
    from PIL import Image
    buf = io.BytesIO()
    img = Image.new("RGB", (2, 2), (255, 0, 0))
    img.save(buf, format="PNG")
    return buf.getvalue()


if __name__ == "__main__":
    open("/tmp/ejc_qa_test.pdf", "wb").write(pdf())
    open("/tmp/ejc_qa_test.xlsx", "wb").write(xlsx())
    open("/tmp/ejc_qa_test.png", "wb").write(png())
    print("gerados:", "/tmp/ejc_qa_test.{pdf,xlsx,png}")
