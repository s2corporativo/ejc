# ── app/services/docx_service.py ─────────────────────────────────────────────
# Geração de DOCX editável (python-docx) para peças jurídicas, pareceres,
# propostas e relatórios. Complementa o pdf_service (PDF = versão final /
# protocolo; DOCX = versão editável de trabalho).
#
# Formatação jurídica (ABNT):
#   - Times New Roman 12pt (corpo), citações longas 11pt
#   - Margens: superior/esquerda 3cm, inferior/direita 2cm
#   - Espaçamento 1,5; parágrafos justificados; recuo 1ª linha 1,25cm
#   - Cabeçalho: identidade do escritório (settings) + nº do processo (meta)
#   - Rodapé: dados de contato + numeração de página (campos PAGE/NUMPAGES)
#
# Parser de markdown próprio (sem lib nova), cobrindo o que LegalDoc.conteudo
# usa: h1-h3 (#, ##, ###), **negrito**, *itálico*, listas (-, *, 1.),
# citações (>), parágrafos.
#
# LGPD: nenhum conteúdo é logado; apenas metadados de execução.
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import io
import logging
import re
from typing import Any

from app.core.config import get_settings
from app.services.document_format import juntar_segmentos, marca_minuta_ia
from app.services.visual_law_theme import OURO

logger = logging.getLogger("ejc.docx")

settings = get_settings()

# Identidade institucional — mesma FONTE ÚNICA usada pelo PDF (settings
# ESCRITORIO_*). OAB e endereço integram o timbre (cabeçalho) e o rodapé; setting
# vazia FAZ SUMIR o segmento inteiro (rótulo incluído) em vez de imprimir o
# placeholder de pendência interna no documento do cliente — ver
# Settings.escritorio_pendencias(), que mantém a pendência visível ao operador.
_SEP = "  |  "
ESCRITORIO_NOME = settings.ESCRITORIO_NOME
_ENDERECO_CIDADE = juntar_segmentos(
    (
        settings.escritorio_endereco(),
        f"{settings.ESCRITORIO_CIDADE}/{settings.ESCRITORIO_ESTADO}",
    ),
    " - ",
)
_OAB = f"OAB/MG {settings.escritorio_oab()}" if settings.escritorio_oab() else ""
_CEP = f"CEP {settings.escritorio_cep()}" if settings.escritorio_cep() else ""
# Sub-linha do timbre (cabeçalho): OAB + endereço — dados FIXOS do escritório.
ESCRITORIO_TIMBRE_SUB = juntar_segmentos((_OAB, _ENDERECO_CIDADE, _CEP), _SEP)
# Rodapé: contato completo (CNPJ + OAB + endereço + e-mail).
ESCRITORIO_CONTATO = juntar_segmentos(
    (
        f"CNPJ {settings.ESCRITORIO_CNPJ}" if settings.ESCRITORIO_CNPJ else "",
        _OAB,
        _ENDERECO_CIDADE,
        _CEP,
        settings.ESCRITORIO_EMAIL,
    ),
    _SEP,
)

# ── Parser de markdown (linha a linha) ───────────────────────────────────────

_H_RE = re.compile(r"^(#{1,3})\s+(.*)$")
_UL_RE = re.compile(r"^[-*]\s+(.*)$")
_OL_RE = re.compile(r"^(\d+)[.)]\s+(.*)$")
_QUOTE_RE = re.compile(r"^>\s?(.*)$")
# Inline: **negrito** e *itálico* (sem aninhamento — suficiente p/ LegalDoc).
_INLINE_RE = re.compile(r"(\*\*[^*]+\*\*|\*[^*\n]+\*)")


def _blocos_markdown(conteudo_md: str) -> list[dict[str, Any]]:
    """Converte markdown básico em lista de blocos tipados.

    Tipos: heading (nivel 1-3), paragraph, ul_item, ol_item, quote.
    Linhas consecutivas de texto são agrupadas num mesmo parágrafo
    (comportamento padrão do markdown).
    """
    blocos: list[dict[str, Any]] = []
    par_atual: list[str] = []

    def fecha_paragrafo() -> None:
        if par_atual:
            blocos.append({"tipo": "paragraph", "texto": " ".join(par_atual)})
            par_atual.clear()

    for linha in (conteudo_md or "").splitlines():
        limpa = linha.strip()
        if not limpa:
            fecha_paragrafo()
            continue

        m = _H_RE.match(limpa)
        if m:
            fecha_paragrafo()
            blocos.append({"tipo": "heading", "nivel": len(m.group(1)),
                           "texto": m.group(2).strip()})
            continue

        m = _QUOTE_RE.match(limpa)
        if m:
            fecha_paragrafo()
            texto = m.group(1).strip()
            # Agrupa linhas consecutivas de citação num único bloco.
            if blocos and blocos[-1]["tipo"] == "quote":
                blocos[-1]["texto"] += (" " + texto) if texto else ""
            else:
                blocos.append({"tipo": "quote", "texto": texto})
            continue

        m = _UL_RE.match(limpa)
        if m:
            fecha_paragrafo()
            blocos.append({"tipo": "ul_item", "texto": m.group(1).strip()})
            continue

        m = _OL_RE.match(limpa)
        if m:
            fecha_paragrafo()
            blocos.append({"tipo": "ol_item", "numero": m.group(1),
                           "texto": m.group(2).strip()})
            continue

        par_atual.append(limpa)

    fecha_paragrafo()
    return blocos


# ── Montagem do DOCX ─────────────────────────────────────────────────────────

def _add_runs_inline(paragraph, texto: str, *, font_name: str, size_pt: float) -> None:
    """Adiciona runs ao parágrafo interpretando **negrito** e *itálico*."""
    from docx.shared import Pt

    for parte in _INLINE_RE.split(texto):
        if not parte:
            continue
        if parte.startswith("**") and parte.endswith("**") and len(parte) > 4:
            run = paragraph.add_run(parte[2:-2])
            run.bold = True
        elif parte.startswith("*") and parte.endswith("*") and len(parte) > 2:
            run = paragraph.add_run(parte[1:-1])
            run.italic = True
        else:
            run = paragraph.add_run(parte)
        run.font.name = font_name
        run.font.size = Pt(size_pt)


def _add_campo(paragraph, instrucao: str) -> None:
    """Insere um campo do Word (PAGE, NUMPAGES) via OOXML — numeração dinâmica."""
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instrucao
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instr)
    run._r.append(end)


def gerar_docx(titulo: str, conteudo_md: str, meta: dict | None = None) -> bytes:
    """Gera DOCX com formatação jurídica a partir de markdown básico.

    meta (todas as chaves opcionais):
      - numero_processo / processo: exibido no cabeçalho sob o nome do escritório.

    Levanta RuntimeError se python-docx não estiver instalado.
    """
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.shared import Cm, Pt, RGBColor
    except ImportError:
        raise RuntimeError("python-docx não instalado. Execute: pip install python-docx")

    meta = meta or {}
    fonte = "Times New Roman"
    # Dourado institucional (tema central Visual Law) nos títulos.
    cor_titulo = RGBColor.from_string(OURO.lstrip("#").upper())
    doc = Document()

    # ── Página + estilo base ────────────────────────────────────────────
    section = doc.sections[0]
    section.top_margin = Cm(3)
    section.left_margin = Cm(3)
    section.bottom_margin = Cm(2)
    section.right_margin = Cm(2)

    normal = doc.styles["Normal"]
    normal.font.name = fonte
    normal.font.size = Pt(12)
    # Garante a fonte também para caracteres complexos/asiáticos (Word).
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), fonte)
    normal.paragraph_format.line_spacing = 1.5

    # ── Cabeçalho: escritório (nome + OAB/endereço) + nº do processo ────
    header = section.header
    ph = header.paragraphs[0]
    ph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = ph.add_run(ESCRITORIO_NOME)
    run.bold = True
    run.font.name = fonte
    run.font.size = Pt(10)

    # Sub-linha do timbre: OAB + endereço (dados FIXOS das settings).
    psub = header.add_paragraph()
    psub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rsub = psub.add_run(ESCRITORIO_TIMBRE_SUB)
    rsub.font.name = fonte
    rsub.font.size = Pt(8)

    numero_processo = meta.get("numero_processo") or meta.get("processo")
    if numero_processo:
        pproc = header.add_paragraph()
        pproc.alignment = WD_ALIGN_PARAGRAPH.CENTER
        rp = pproc.add_run(f"Processo nº {numero_processo}")
        rp.font.name = fonte
        rp.font.size = Pt(9)

    # ── Rodapé: contato + numeração de página ──────────────────────────
    footer = section.footer
    pf = footer.paragraphs[0]
    pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rf = pf.add_run(ESCRITORIO_CONTATO)
    rf.font.name = fonte
    rf.font.size = Pt(8)

    ppag = footer.add_paragraph()
    ppag.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r1 = ppag.add_run("Página ")
    _add_campo(ppag, "PAGE")
    r2 = ppag.add_run(" de ")
    _add_campo(ppag, "NUMPAGES")
    for r in ppag.runs:
        r.font.name = fonte
        r.font.size = Pt(8)
    # (runs de campo herdam o tamanho do parágrafo; r1/r2 fixados acima)
    r1.font.size = Pt(8)
    r2.font.size = Pt(8)

    # Linha de controle EJC-<...> (Fase D) — render-only, montada pelo chamador.
    linha_controle = meta.get("linha_controle")
    if linha_controle:
        pctrl = footer.add_paragraph()
        pctrl.alignment = WD_ALIGN_PARAGRAPH.CENTER
        rc = pctrl.add_run(str(linha_controle))
        rc.font.name = fonte
        rc.font.size = Pt(7.5)
        rc.font.color.rgb = RGBColor(75, 85, 99)

    # ── Marca de minuta IA (só rascunho não-revisado) ───────────────────
    # Embute a origem-IA no CORPO da 1ª página quando a peça é ai_generated e
    # ainda NÃO foi human_reviewed — a salvaguarda VIAJA com o .docx baixado.
    # Versão final revisada (meta sem minuta_ia) sai LIMPA.
    if meta.get("minuta_ia"):
        pmin = doc.add_paragraph()
        pmin.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pmin.paragraph_format.space_after = Pt(10)
        rmin = pmin.add_run(marca_minuta_ia())
        rmin.bold = True
        rmin.font.name = fonte
        rmin.font.size = Pt(11)
        rmin.font.color.rgb = RGBColor(0xB9, 0x1C, 0x1C)  # vermelho de alerta

    # ── Título do documento ─────────────────────────────────────────────
    pt = doc.add_paragraph()
    pt.alignment = WD_ALIGN_PARAGRAPH.CENTER
    pt.paragraph_format.space_after = Pt(12)
    rt = pt.add_run((titulo or "Documento jurídico").upper())
    rt.bold = True
    rt.font.name = fonte
    rt.font.size = Pt(12)
    rt.font.color.rgb = cor_titulo

    quadro = doc.add_paragraph()
    quadro.alignment = WD_ALIGN_PARAGRAPH.CENTER
    quadro.paragraph_format.space_after = Pt(8)
    q = quadro.add_run("CONTROLE VISUAL LAW EJC")
    q.bold = True
    q.font.name = fonte
    q.font.size = Pt(10)
    q.font.color.rgb = cor_titulo

    codigo_peca = meta.get("codigo_peca")
    versao_doc = f"v{int(meta.get('versao') or 1)}.0"
    status_doc = meta.get("status") or "Versão de trabalho"
    tabela = doc.add_table(rows=2, cols=3)
    campos = [
        ("Controle", str(codigo_peca or "Visual Law")),
        ("Versão", versao_doc),
        ("Status", str(status_doc)),
        ("Processo", str(numero_processo or "—")),
        ("Formato", "DOCX editável"),
        ("Revisão", "Obrigatória"),
    ]
    for cell, (label, valor) in zip(tabela._cells, campos):
        p = cell.paragraphs[0]
        p.paragraph_format.space_after = Pt(0)
        r_label = p.add_run(label.upper() + "\n")
        r_label.bold = True
        r_label.font.name = fonte
        r_label.font.size = Pt(7.5)
        r_label.font.color.rgb = cor_titulo
        r_valor = p.add_run(valor)
        r_valor.bold = True
        r_valor.font.name = fonte
        r_valor.font.size = Pt(9.5)

    nota = doc.add_paragraph()
    nota.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    nota.paragraph_format.space_before = Pt(8)
    nota.paragraph_format.space_after = Pt(14)
    nr = nota.add_run(
        "Documento estruturado com elementos de Visual Law para facilitar leitura, "
        "controle de versão e conferência profissional, sem alteração do teor."
    )
    nr.italic = True
    nr.font.name = fonte
    nr.font.size = Pt(9)
    nr.font.color.rgb = RGBColor(75, 85, 99)

    # ── Corpo (blocos do markdown) ──────────────────────────────────────
    for bloco in _blocos_markdown(conteudo_md):
        tipo = bloco["tipo"]

        if tipo == "heading":
            p = doc.add_paragraph()
            nivel = bloco["nivel"]
            p.alignment = (WD_ALIGN_PARAGRAPH.CENTER if nivel == 1
                           else WD_ALIGN_PARAGRAPH.LEFT)
            p.paragraph_format.space_before = Pt(14)
            p.paragraph_format.space_after = Pt(8)
            p.paragraph_format.line_spacing = 1.5
            texto = bloco["texto"].upper() if nivel == 1 else bloco["texto"]
            _add_runs_inline(p, texto, font_name=fonte, size_pt=12)
            for r in p.runs:
                r.bold = True
                r.font.color.rgb = cor_titulo

        elif tipo == "quote":
            # Citação longa (padrão ABNT): recuo 4cm, 11pt, espaçamento simples.
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Cm(4)
            p.paragraph_format.line_spacing = 1.0
            p.paragraph_format.space_before = Pt(6)
            p.paragraph_format.space_after = Pt(6)
            _add_runs_inline(p, bloco["texto"], font_name=fonte, size_pt=11)

        elif tipo == "ul_item":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Cm(1.25)
            p.paragraph_format.line_spacing = 1.5
            r = p.add_run("– ")
            r.font.name = fonte
            r.font.size = Pt(12)
            _add_runs_inline(p, bloco["texto"], font_name=fonte, size_pt=12)

        elif tipo == "ol_item":
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.left_indent = Cm(1.25)
            p.paragraph_format.line_spacing = 1.5
            r = p.add_run(f"{bloco['numero']}. ")
            r.font.name = fonte
            r.font.size = Pt(12)
            _add_runs_inline(p, bloco["texto"], font_name=fonte, size_pt=12)

        else:  # paragraph
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p.paragraph_format.first_line_indent = Cm(1.25)
            p.paragraph_format.line_spacing = 1.5
            p.paragraph_format.space_after = Pt(6)
            _add_runs_inline(p, bloco["texto"], font_name=fonte, size_pt=12)

    buf = io.BytesIO()
    doc.save(buf)
    logger.info("DOCX gerado (%d bytes)", buf.getbuffer().nbytes)
    return buf.getvalue()


async def gerar_docx_async(titulo: str, conteudo_md: str, meta: dict | None = None) -> bytes:
    """Versão assíncrona — delega para executor (python-docx é síncrono/CPU)."""
    import asyncio
    return await asyncio.get_event_loop().run_in_executor(
        None, gerar_docx, titulo, conteudo_md, meta
    )
