"""Documento Único de Anexos — cofre de confidencialidade (DOC-076) e manifesto
de completude / fail-closed (DOC-077). Fakes locais, sem DB/rede/weasyprint."""
from __future__ import annotations

import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import anexos_service as svc
from app.services.anexos_service import ContextoAnexos, ItemAnexo


def _ctx() -> ContextoAnexos:
    return ContextoAnexos(
        titulo_acao="AÇÃO TESTE", partes="A vs. B",
        referencia="REF-1", rodape="Comarca Fictícia",
    )


class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)

    async def execute(self, *a, **k):
        return self.results.pop(0)


def _doc(conf: str):
    return SimpleNamespace(
        id="d1", titulo="Documento Sigiloso",
        confidencialidade=SimpleNamespace(value=conf),
        filepath="a.pdf", mimetype="application/pdf", tipo="prova",
        ocr_text=None, case_id="caso1",
    )


# ── DOC-076: cofre de confidencialidade por item ──────────────────────────────

async def test_resolver_itens_bloqueia_restrito_para_advogado():
    db = _FakeDB([_Res(one=_doc("restrito"))])
    cu = SimpleNamespace(id="u", role=SimpleNamespace(value="advogado"))
    with pytest.raises(HTTPException) as ei:
        await svc.resolver_itens(
            db, cu_id="u", case_id="caso1",
            itens_in=[{"document_id": "d1"}], com_ia=False, cu=cu,
        )
    assert ei.value.status_code == 403


async def test_resolver_itens_permite_restrito_para_socio():
    db = _FakeDB([_Res(one=_doc("restrito"))])
    cu = SimpleNamespace(id="u", role=SimpleNamespace(value="socio"))
    itens = await svc.resolver_itens(
        db, cu_id="u", case_id="caso1",
        itens_in=[{"document_id": "d1"}], com_ia=False, cu=cu,
    )
    assert itens[0].document_id == "d1"


async def test_resolver_itens_normal_passa_para_advogado():
    db = _FakeDB([_Res(one=_doc("normal"))])
    cu = SimpleNamespace(id="u", role=SimpleNamespace(value="advogado"))
    itens = await svc.resolver_itens(
        db, cu_id="u", case_id="caso1",
        itens_in=[{"document_id": "d1"}], com_ia=False, cu=cu,
    )
    assert itens[0].titulo == "Documento Sigiloso"


# ── DOC-077: manifesto + fail-closed ──────────────────────────────────────────

def _pdf1() -> bytes:
    from pypdf import PdfWriter
    w = PdfWriter()
    w.add_blank_page(width=200, height=200)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _patch_render(monkeypatch):
    async def fake_render(html):
        return _pdf1()
    monkeypatch.setattr(svc, "_render_pdf", fake_render)


async def test_manifesto_pdf_corrompido_aborta_fail_closed(monkeypatch):
    _patch_render(monkeypatch)
    monkeypatch.setattr(svc, "_caminho_anexo", lambda item: "/fake/a.pdf")

    async def fake_anexo(ctx, item):
        return None  # arquivo existe mas não pôde ser incorporado (corrompido)
    monkeypatch.setattr(svc, "_anexo_para_pdf", fake_anexo)

    item = ItemAnexo(ordem=1, titulo="Corrompido")
    item._mimetype = "application/pdf"
    item._filepath = "a.pdf"
    with pytest.raises(svc.DocumentoUnicoIncompletoError) as ei:
        await svc.montar_documento_unico_com_manifesto(_ctx(), [item])
    assert ei.value.manifesto  # manifesto acompanha o erro
    assert ei.value.manifesto[-1]["incorporado"] is False


async def test_manifesto_nao_inlineavel_sinalizado_nao_omitido(monkeypatch):
    _patch_render(monkeypatch)
    monkeypatch.setattr(svc, "_caminho_anexo", lambda item: "/fake/planilha.xlsx")

    item = ItemAnexo(ordem=1, titulo="Planilha")
    item._mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    item._filepath = "planilha.xlsx"
    pdf, manifesto = await svc.montar_documento_unico_com_manifesto(_ctx(), [item])
    assert pdf  # o pacote é gerado (só capa+separador), sem omitir em silêncio
    m = manifesto[-1]
    assert m["formato"] == "nao_inlineavel"
    assert m["incorporado"] is False and m["motivo"]


async def test_manifesto_obrigatorio_nao_incorporavel_aborta(monkeypatch):
    _patch_render(monkeypatch)
    monkeypatch.setattr(svc, "_caminho_anexo", lambda item: None)

    item = ItemAnexo(ordem=1, titulo="Exigido", obrigatorio=True, document_id="d9")
    item._filepath = "sumido.pdf"
    item._mimetype = "application/pdf"
    with pytest.raises(svc.DocumentoUnicoIncompletoError):
        await svc.montar_documento_unico_com_manifesto(_ctx(), [item])


async def test_manifesto_pdf_incorporado_ok(monkeypatch):
    _patch_render(monkeypatch)
    monkeypatch.setattr(svc, "_caminho_anexo", lambda item: "/fake/ok.pdf")

    async def fake_anexo(ctx, item):
        return _pdf1()
    monkeypatch.setattr(svc, "_anexo_para_pdf", fake_anexo)

    item = ItemAnexo(ordem=1, titulo="OK")
    item._mimetype = "application/pdf"
    item._filepath = "ok.pdf"
    pdf, manifesto = await svc.montar_documento_unico_com_manifesto(_ctx(), [item])
    assert pdf and manifesto[-1]["incorporado"] is True
