"""Modo MANUAL da NFS-e — registro de notas emitidas FORA do sistema (Emissor
Nacional gov.br). Sem rede, sem banco (fakes no padrão de test_nfse).

Cobre: permissões (allowlist financeira) nos endpoints novos; funcionamento com
NFSE_ENABLED=false (ponto central do modo manual); validação de uploads por
extensão + magic bytes sem deixar arquivo órfão; download de PDF/XML local com
audit log; cancelamento lógico (motivo, duplo → 409, nota não-manual → 409);
vínculos fee/client (404, herança de client_id); e validações de campos.
"""
from __future__ import annotations

import os
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.client import Client
from app.models.fee import Fee
from app.models.nfse import NFSeStatus, NotaFiscalServico
from app.models.user import User, UserRole

# Conteúdos mínimos com magic bytes REAIS (reconhecidos pelo libmagic).
PDF_MINIMO = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n"
XML_MINIMO = b'<?xml version="1.0" encoding="UTF-8"?>\n<NFSe><infNFSe/></NFSe>\n'


# ── Fakes (padrão test_nfse) ────────────────────────────────────────────────────

class _FakeDB:
    def __init__(self, objs=None, scalar_result=None, rows=None):
        self.objs = objs or {}          # (ModelName, id) -> obj
        self.scalar_result = scalar_result
        self.rows = rows or []
        self.added: list = []
        self.commits = 0

    async def get(self, model, ident):
        return self.objs.get((model.__name__, ident))

    async def scalar(self, stmt):
        return self.scalar_result

    async def execute(self, stmt):
        rows = self.rows

        class _Res:
            def scalars(self):
                return self

            def all(self):
                return rows

        return _Res()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1


class _FakeUpload:
    """UploadFile mínimo: só filename + read(), como o router usa."""

    def __init__(self, filename: str, conteudo: bytes):
        self.filename = filename
        self._conteudo = conteudo

    async def read(self) -> bytes:
        return self._conteudo


def _fee():
    return Fee(id="f1", descricao="Honorários", valor=1500, client_id="c1",
               deleted_at=None)


def _cliente():
    return Client(id="c1", nome="Fulano da Silva", cpf="52998224725",
                  estado="MG", cep="32600-000")


def _financeiro() -> User:
    return User(id="uf", role=UserRole.financeiro)


def _socio() -> User:
    return User(id="us", role=UserRole.socio)


def _nota_manual(**kw) -> NotaFiscalServico:
    base = dict(id="nm1", provider="manual", referencia="manual-abc",
                status=NFSeStatus.autorizada.value, numero="101",
                valor=Decimal("500.00"), descricao="Serviço")
    base.update(kw)
    return NotaFiscalServico(**base)


@pytest.fixture()
def upload_dir(tmp_path, monkeypatch):
    """Storage isolado por teste (mesmo UPLOAD_DIR do GED, monkeypatchado)."""
    monkeypatch.setattr(get_settings(), "UPLOAD_DIR", str(tmp_path))
    return tmp_path


def _arquivos_manual(upload_dir) -> list[str]:
    sub = upload_dir / "nfse"
    return sorted(os.listdir(sub)) if sub.is_dir() else []


async def _registrar(db, cu, *, pdf=None, xml=None, **kw):
    from app.routers.nfse import registrar_nfse_manual

    base = dict(numero="101", data_emissao="2026-07-10", valor=Decimal("500.00"),
                descricao="Serviços advocatícios", chave_acesso=None,
                competencia=None, client_id=None, fee_id=None)
    base.update(kw)
    return await registrar_nfse_manual(pdf=pdf, xml=xml, db=db, cu=cu, **base)


# ── Rotas do modo manual montadas em main ───────────────────────────────────────

def test_rotas_manuais_montadas_em_main():
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p.endswith("/nfse") for p in paths)                       # GET lista
    assert any(p.endswith("/nfse/manual") for p in paths)
    assert any(p.endswith("/nfse/manual/{nota_id}/cancelar") for p in paths)


# ── Permissões: allowlist financeira nos endpoints novos ────────────────────────
# Padrão de test_nfse (test_leitura_nfse_usa_gate_financeiro): os endpoints são
# chamados direto (sem HTTP), então o 403 é garantido por (a) o gate rejeitar o
# perfil e (b) o endpoint estar WIRED no gate via Depends.

def test_endpoints_manuais_usam_gate_financeiro():
    import inspect

    from app.routers.nfse import (
        _req_financeiro_leitura, cancelar_nfse_manual, listar_nfse,
        registrar_nfse_manual,
    )

    for endpoint in (listar_nfse, registrar_nfse_manual, cancelar_nfse_manual):
        dep = inspect.signature(endpoint).parameters["cu"].default.dependency
        assert dep is _req_financeiro_leitura, endpoint.__name__


def test_gate_financeiro_403_estagiario_advogado_cliente_externo():
    from app.routers.nfse import _req_financeiro_leitura

    for role in (UserRole.estagiario, UserRole.advogado, UserRole.cliente_externo):
        with pytest.raises(HTTPException) as exc:
            _req_financeiro_leitura(User(id="u1", role=role))
        assert exc.value.status_code == 403, role


def test_gate_financeiro_permite_financeiro_e_socio():
    from app.routers.nfse import _req_financeiro_leitura

    for role in (UserRole.financeiro, UserRole.socio):
        cu = User(id="u1", role=role)
        assert _req_financeiro_leitura(cu) is cu


async def test_listar_nfse_financeiro_ok():
    from app.routers.nfse import listar_nfse

    db = _FakeDB(scalar_result=1, rows=[_nota_manual()])
    resp = await listar_nfse(limit=50, offset=0, status=None, client_id=None,
                             provider=None, db=db, cu=_financeiro())
    assert resp["total"] == 1
    assert resp["items"][0]["id"] == "nm1"
    assert resp["items"][0]["provider"] == "manual"
    # Paths de servidor nunca expostos — só booleans.
    assert "pdf_path" not in resp["items"][0]
    assert "xml_path" not in resp["items"][0]


# ── Registro manual funciona com NFSE_ENABLED=false (ponto central) ─────────────

async def test_registrar_manual_com_nfse_desligado(upload_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "NFSE_ENABLED", False)

    db = _FakeDB()
    resp = await _registrar(db, _financeiro())

    assert resp["provider"] == "manual"
    assert resp["status"] == NFSeStatus.autorizada.value
    assert resp["numero"] == "101"
    assert resp["ambiente"] == "producao"       # nota real do Emissor Nacional
    assert resp["data_emissao"] == "2026-07-10"
    assert resp["valor"] == "500.00"
    assert resp["referencia"].startswith("manual-")
    assert resp["tem_pdf"] is False and resp["tem_xml"] is False

    notas = [o for o in db.added if isinstance(o, NotaFiscalServico)]
    assert len(notas) == 1 and notas[0].created_by == "uf"
    acoes = [o.acao for o in db.added if o.__class__.__name__ == "AuditLog"]
    assert acoes == ["NFSE_MANUAL_REGISTRADA"]
    assert db.commits == 1


async def test_registrar_manual_socio_ok(upload_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "NFSE_ENABLED", False)
    resp = await _registrar(_FakeDB(), _socio())
    assert resp["provider"] == "manual" and resp["status"] == "autorizada"


# ── Uploads inválidos: 4xx SEM criar arquivo ────────────────────────────────────

async def test_pdf_sem_magic_bytes_415_sem_arquivo(upload_dir):
    pdf = _FakeUpload("nota.pdf", b"conteudo texto qualquer, nao e um PDF")
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), pdf=pdf)
    assert exc.value.status_code == 415
    assert _arquivos_manual(upload_dir) == []


async def test_xml_invalido_415_sem_arquivo(upload_dir):
    # libmagic aceita text/plain para .xml — o reforço `<`/`<?xml` barra.
    xml = _FakeUpload("nota.xml", b"isto nao e xml de jeito nenhum")
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), xml=xml)
    assert exc.value.status_code == 415
    assert _arquivos_manual(upload_dir) == []


async def test_extensao_errada_415(upload_dir):
    pdf = _FakeUpload("nota.txt", PDF_MINIMO)
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), pdf=pdf)
    assert exc.value.status_code == 415
    assert _arquivos_manual(upload_dir) == []


async def test_arquivo_vazio_422(upload_dir):
    pdf = _FakeUpload("nota.pdf", b"")
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), pdf=pdf)
    assert exc.value.status_code == 422
    assert _arquivos_manual(upload_dir) == []


async def test_arquivo_excede_limite_413(upload_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_MB", 1)
    grande = PDF_MINIMO + b"0" * (1024 * 1024 + 10)
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(),
                         pdf=_FakeUpload("nota.pdf", grande))
    assert exc.value.status_code == 413
    assert _arquivos_manual(upload_dir) == []


async def test_pdf_valido_xml_invalido_nao_deixa_orfao(upload_dir):
    """Validação dos DOIS anexos ANTES de gravar qualquer um."""
    pdf = _FakeUpload("nota.pdf", PDF_MINIMO)
    xml = _FakeUpload("nota.xml", b"nao e xml")
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), pdf=pdf, xml=xml)
    assert exc.value.status_code == 415
    assert _arquivos_manual(upload_dir) == []   # PDF válido NÃO virou órfão


# ── Upload válido + download com audit ──────────────────────────────────────────

async def test_pdf_valido_cria_nota_com_tem_pdf(upload_dir):
    db = _FakeDB()
    resp = await _registrar(db, _financeiro(),
                            pdf=_FakeUpload("danfse.pdf", PDF_MINIMO),
                            xml=_FakeUpload("nfse.xml", XML_MINIMO))
    assert resp["tem_pdf"] is True and resp["tem_xml"] is True
    nota = next(o for o in db.added if isinstance(o, NotaFiscalServico))
    # Nome gerado (uuid), nunca o filename do usuário; subpasta nfse/.
    assert nota.pdf_path.startswith("nfse/") and nota.pdf_path.endswith(".pdf")
    assert "danfse" not in nota.pdf_path
    assert len(_arquivos_manual(upload_dir)) == 2
    assert (upload_dir / nota.pdf_path).read_bytes() == PDF_MINIMO
    assert (upload_dir / nota.xml_path).read_bytes() == XML_MINIMO


async def test_download_pdf_manual_serve_arquivo_e_audita(upload_dir):
    from app.routers.nfse import baixar_pdf_nfse

    db = _FakeDB()
    await _registrar(db, _financeiro(), pdf=_FakeUpload("n.pdf", PDF_MINIMO))
    nota = next(o for o in db.added if isinstance(o, NotaFiscalServico))

    db2 = _FakeDB(objs={("NotaFiscalServico", nota.id): nota})
    resp = await baixar_pdf_nfse(nota.id, db=db2, cu=_financeiro())

    assert resp.media_type == "application/pdf"
    with open(resp.path, "rb") as f:
        assert f.read() == PDF_MINIMO
    assert f'filename="nfse-101.pdf"' in resp.headers["content-disposition"]
    acoes = [o.acao for o in db2.added if o.__class__.__name__ == "AuditLog"]
    assert acoes == ["NFSE_ARQUIVO_BAIXADO"]
    assert db2.commits == 1     # audit de download COMMITADO


async def test_download_xml_manual_serve_arquivo_e_audita(upload_dir):
    from app.routers.nfse import baixar_xml_nfse

    db = _FakeDB()
    await _registrar(db, _financeiro(), xml=_FakeUpload("n.xml", XML_MINIMO))
    nota = next(o for o in db.added if isinstance(o, NotaFiscalServico))

    db2 = _FakeDB(objs={("NotaFiscalServico", nota.id): nota})
    resp = await baixar_xml_nfse(nota.id, db=db2, cu=_financeiro())
    assert resp.media_type == "application/xml"
    with open(resp.path, "rb") as f:
        assert f.read() == XML_MINIMO
    acoes = [o.acao for o in db2.added if o.__class__.__name__ == "AuditLog"]
    assert acoes == ["NFSE_ARQUIVO_BAIXADO"]


async def test_download_pdf_manual_sem_anexo_404(upload_dir):
    from app.routers.nfse import baixar_pdf_nfse

    nota = _nota_manual(pdf_path=None)
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): nota})
    with pytest.raises(HTTPException) as exc:
        await baixar_pdf_nfse("nm1", db=db, cu=_financeiro())
    assert exc.value.status_code == 404
    # Sem audit de download quando nada foi baixado.
    assert not [o for o in db.added if o.__class__.__name__ == "AuditLog"]


async def test_download_pdf_manual_path_traversal_404(upload_dir):
    from app.routers.nfse import baixar_pdf_nfse

    fora = upload_dir.parent / "segredo.pdf"
    fora.write_bytes(PDF_MINIMO)
    nota = _nota_manual(pdf_path="../segredo.pdf")
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): nota})
    with pytest.raises(HTTPException) as exc:
        await baixar_pdf_nfse("nm1", db=db, cu=_financeiro())
    assert exc.value.status_code == 404


# ── Cancelamento lógico ─────────────────────────────────────────────────────────

async def test_cancelar_manual_persiste_motivo_e_audita():
    from app.routers.nfse import CancelarIn, cancelar_nfse_manual

    nota = _nota_manual()
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): nota})
    resp = await cancelar_nfse_manual(
        "nm1", CancelarIn(motivo="Nota emitida em duplicidade"),
        db=db, cu=_financeiro(),
    )
    assert resp["status"] == NFSeStatus.cancelada.value
    assert resp["motivo_cancelamento"] == "Nota emitida em duplicidade"
    assert nota.status == NFSeStatus.cancelada.value
    logs = [o for o in db.added if o.__class__.__name__ == "AuditLog"]
    assert [l.acao for l in logs] == ["NFSE_MANUAL_CANCELADA"]
    assert db.commits == 1


async def test_cancelar_manual_duplo_409():
    from app.routers.nfse import CancelarIn, cancelar_nfse_manual

    nota = _nota_manual(status=NFSeStatus.cancelada.value,
                        motivo_cancelamento="já cancelada antes")
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): nota})
    with pytest.raises(HTTPException) as exc:
        await cancelar_nfse_manual("nm1", CancelarIn(motivo="de novo"),
                                   db=db, cu=_financeiro())
    assert exc.value.status_code == 409
    assert nota.motivo_cancelamento == "já cancelada antes"   # não sobrescreve
    assert db.commits == 0


async def test_cancelar_nao_manual_pela_rota_manual_409():
    from app.routers.nfse import CancelarIn, cancelar_nfse_manual

    nota = _nota_manual(provider="nuvemfiscal")
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): nota})
    with pytest.raises(HTTPException) as exc:
        await cancelar_nfse_manual("nm1", CancelarIn(motivo="teste"),
                                   db=db, cu=_financeiro())
    assert exc.value.status_code == 409
    assert nota.status == NFSeStatus.autorizada.value   # intacta


async def test_cancelar_manual_inexistente_404():
    from app.routers.nfse import CancelarIn, cancelar_nfse_manual

    with pytest.raises(HTTPException) as exc:
        await cancelar_nfse_manual("nao-existe", CancelarIn(motivo="teste"),
                                   db=_FakeDB(), cu=_financeiro())
    assert exc.value.status_code == 404


def test_cancelar_motivo_curto_rejeitado():
    from pydantic import ValidationError

    from app.routers.nfse import CancelarIn

    with pytest.raises(ValidationError):
        CancelarIn(motivo="ab")     # min_length=3


# ── Vínculos fee/client ─────────────────────────────────────────────────────────

async def test_fee_inexistente_404(upload_dir):
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), fee_id="nao-existe")
    assert exc.value.status_code == 404


async def test_fee_soft_deletado_404(upload_dir):
    from datetime import datetime

    fee = _fee()
    fee.deleted_at = datetime(2026, 1, 1)
    db = _FakeDB(objs={("Fee", "f1"): fee})
    with pytest.raises(HTTPException) as exc:
        await _registrar(db, _financeiro(), fee_id="f1")
    assert exc.value.status_code == 404


async def test_client_inexistente_404(upload_dir):
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), client_id="nao-existe")
    assert exc.value.status_code == 404


async def test_fee_valido_herda_client_id(upload_dir):
    db = _FakeDB(objs={("Fee", "f1"): _fee(), ("Client", "c1"): _cliente()})
    resp = await _registrar(db, _financeiro(), fee_id="f1")
    assert resp["fee_id"] == "f1"
    assert resp["client_id"] == "c1"    # herdado de fee.client_id


# ── Validações de campos ────────────────────────────────────────────────────────

async def test_valor_zero_e_negativo_422(upload_dir):
    for valor in (Decimal("0"), Decimal("-10.00")):
        with pytest.raises(HTTPException) as exc:
            await _registrar(_FakeDB(), _financeiro(), valor=valor)
        assert exc.value.status_code == 422, valor


async def test_data_emissao_malformada_422(upload_dir):
    for data in ("18/07/2026", "2026-13-40", "ontem"):
        with pytest.raises(HTTPException) as exc:
            await _registrar(_FakeDB(), _financeiro(), data_emissao=data)
        assert exc.value.status_code == 422, data


async def test_competencia_malformada_422(upload_dir):
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), competencia="07-2026")
    assert exc.value.status_code == 422


async def test_numero_em_branco_422(upload_dir):
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), numero="   ")
    assert exc.value.status_code == 422


async def test_descricao_em_branco_422(upload_dir):
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), descricao="   ")
    assert exc.value.status_code == 422
