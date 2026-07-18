"""Modo MANUAL da NFS-e — registro de notas emitidas FORA do sistema (Emissor
Nacional gov.br). Sem rede, sem banco (fakes no padrão de test_nfse).

Cobre: permissões (allowlist financeira) nos endpoints novos; funcionamento com
NFSE_ENABLED=false (ponto central do modo manual); validação de uploads por
extensão + magic bytes sem deixar arquivo órfão; download de PDF/XML local com
audit log; cancelamento lógico (motivo, duplo → 409, nota não-manual → 409);
vínculos fee/client (404, herança de client_id); e validações de campos.
"""
from __future__ import annotations

import operator
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
    """Fake que AVALIA o WHERE dos selects do router contra as notas em `objs`:
    duplicidade de número manual, nota manual ativa do fee (/emitir) e o
    select(...).with_for_update() do cancelamento manual. Assim cada teste
    exercita a condição REAL da query (ex.: status != cancelada libera o
    número), e não um retorno fixo independente da consulta feita."""

    def __init__(self, objs=None, scalar_result=None, rows=None):
        self.objs = objs or {}          # (ModelName, id) -> obj
        self.scalar_result = scalar_result  # selects SEM where (count da listagem)
        self.rows = rows or []
        self.added: list = []
        self.commits = 0

    async def get(self, model, ident):
        return self.objs.get((model.__name__, ident))

    @staticmethod
    def _satisfaz(nota, crits) -> bool:
        for c in crits:
            campo = getattr(getattr(c, "left", None), "key", None)
            alvo = getattr(getattr(c, "right", None), "value", None)
            atual = getattr(nota, campo, None)
            if c.operator is operator.eq and atual != alvo:
                return False
            if c.operator is operator.ne and atual == alvo:
                return False
        return True

    async def scalar(self, stmt):
        crits = list(getattr(stmt, "_where_criteria", ()))
        if not crits:
            return self.scalar_result
        for nota in (o for o in self.objs.values()
                     if isinstance(o, NotaFiscalServico)):
            if self._satisfaz(nota, crits):
                # select(Model) → entidade; select(Model.id) → só a coluna.
                nome = stmt.column_descriptions[0]["name"]
                return nota if nome == "NotaFiscalServico" else getattr(nota, nome)
        return None

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
    """UploadFile mínimo: filename + read(size) — o router lê em CHUNKS."""

    def __init__(self, filename: str, conteudo: bytes):
        self.filename = filename
        self._conteudo = conteudo
        self.reads = 0      # nº de chamadas a read() (prova a leitura em chunks)

    async def read(self, size: int = -1) -> bytes:
        self.reads += 1
        if size is None or size < 0:
            chunk, self._conteudo = self._conteudo, b""
        else:
            chunk, self._conteudo = self._conteudo[:size], self._conteudo[size:]
        return chunk


class _FakeRequest:
    """Request mínimo: só headers, como o teto por Content-Length usa."""

    def __init__(self, content_length=None):
        self.headers = (
            {"content-length": str(content_length)}
            if content_length is not None else {}
        )


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


async def _registrar(db, cu, *, pdf=None, xml=None, request=None, **kw):
    from app.routers.nfse import registrar_nfse_manual

    base = dict(numero="101", data_emissao="2026-07-10", valor=Decimal("500.00"),
                descricao="Serviços advocatícios", chave_acesso=None,
                competencia=None, client_id=None, fee_id=None)
    base.update(kw)
    return await registrar_nfse_manual(request=request, pdf=pdf, xml=xml,
                                       db=db, cu=cu, **base)


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


# ── Idempotência do registro: número manual duplicado ───────────────────────────

async def test_registrar_numero_manual_duplicado_409(upload_dir):
    """Nota manual ATIVA com o mesmo número já escriturada → 409, nada persiste."""
    existente = _nota_manual(numero="101")   # status autorizada (ativa)
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): existente})
    with pytest.raises(HTTPException) as exc:
        await _registrar(db, _financeiro(), numero="101")
    assert exc.value.status_code == 409
    assert "nm1" in exc.value.detail        # aponta a nota conflitante
    assert db.commits == 0
    assert not any(isinstance(o, NotaFiscalServico) for o in db.added)


async def test_registrar_numero_de_nota_cancelada_ok(upload_dir):
    """Nota anterior com o mesmo número mas CANCELADA não bloqueia o registro."""
    cancelada = _nota_manual(numero="101", status=NFSeStatus.cancelada.value)
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): cancelada})
    resp = await _registrar(db, _financeiro(), numero="101")
    assert resp["status"] == NFSeStatus.autorizada.value
    assert db.commits == 1


async def test_registrar_numero_diferente_nao_conflita(upload_dir):
    existente = _nota_manual(numero="101")
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): existente})
    resp = await _registrar(db, _financeiro(), numero="102")
    assert resp["numero"] == "102" and db.commits == 1


# ── /emitir (provedor) × nota manual ativa vinculada ao fee ─────────────────────

async def test_emitir_provedor_409_com_nota_manual_ativa_do_fee(monkeypatch):
    """Fee com nota manual ATIVA → 409 ANTES de reservar referência/tocar provedor."""
    from app.routers.nfse import EmitirIn, emitir_nfse

    s = get_settings()
    monkeypatch.setattr(s, "NFSE_ENABLED", True)
    monkeypatch.setattr(s, "NFSE_PROVEDOR", "nuvemfiscal")
    manual = _nota_manual(fee_id="f1")
    db = _FakeDB(objs={("Fee", "f1"): _fee(),
                       ("NotaFiscalServico", "nm1"): manual})
    with pytest.raises(HTTPException) as exc:
        await emitir_nfse(EmitirIn(fee_id="f1"), db=db, cu=_socio())
    assert exc.value.status_code == 409
    assert "manual" in exc.value.detail
    assert db.commits == 0      # nem chegou a reservar a referência
    assert not any(isinstance(o, NotaFiscalServico) for o in db.added)


async def test_emitir_provedor_ignora_nota_manual_cancelada_do_fee(monkeypatch):
    """Nota manual CANCELADA do fee não bloqueia — segue ao fluxo do provedor."""
    from app.routers.nfse import EmitirIn, emitir_nfse
    from app.services.nfse import NFSeResultado

    s = get_settings()
    monkeypatch.setattr(s, "NFSE_ENABLED", True)
    monkeypatch.setattr(s, "NFSE_PROVEDOR", "nuvemfiscal")

    class _Prov:
        async def emitir(self, pedido):
            return NFSeResultado(status="processando", provider_id="nf_ok")

    monkeypatch.setattr("app.services.nfse.get_provider", lambda: _Prov())
    cancelada = _nota_manual(fee_id="f1", status=NFSeStatus.cancelada.value)
    db = _FakeDB(objs={("Fee", "f1"): _fee(), ("Client", "c1"): _cliente(),
                       ("NotaFiscalServico", "nm1"): cancelada})
    resp = await emitir_nfse(EmitirIn(fee_id="f1"), db=db, cu=_socio())
    assert resp["status"] == "processando" and resp["provider_id"] == "nf_ok"


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


async def test_content_length_acima_do_teto_413_cedo(upload_dir, monkeypatch):
    """Header Content-Length acima do teto → 413 ANTES de ler qualquer upload."""
    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_MB", 1)
    pdf = _FakeUpload("nota.pdf", PDF_MINIMO)   # pequeno — nem deve ser lido
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), pdf=pdf,
                         request=_FakeRequest(content_length=2 * 1024 * 1024))
    assert exc.value.status_code == 413
    assert pdf.reads == 0                       # rejeição cedo, sem ler o stream
    assert _arquivos_manual(upload_dir) == []


async def test_content_length_mentiroso_stream_grande_413(upload_dir, monkeypatch):
    """Content-Length pequeno (mentira) mas stream acima do teto → 413 na
    leitura em CHUNKS (o teto não depende do header)."""
    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_MB", 1)
    grande = PDF_MINIMO + b"0" * (1024 * 1024 + 10)
    pdf = _FakeUpload("nota.pdf", grande)
    with pytest.raises(HTTPException) as exc:
        await _registrar(_FakeDB(), _financeiro(), pdf=pdf,
                         request=_FakeRequest(content_length=1024))
    assert exc.value.status_code == 413
    assert pdf.reads >= 2                       # leitura foi mesmo em chunks
    assert _arquivos_manual(upload_dir) == []


async def test_content_length_dentro_do_teto_nao_bloqueia(upload_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "MAX_UPLOAD_MB", 1)
    resp = await _registrar(_FakeDB(), _financeiro(),
                            request=_FakeRequest(content_length=512))
    assert resp["status"] == NFSeStatus.autorizada.value


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


async def test_download_pdf_fora_da_subpasta_nfse_404(upload_dir):
    """rel_path DENTRO do UPLOAD_DIR mas fora de nfse/ (ex.: doc do GED
    apontado por registro adulterado) → 404, mesmo com o arquivo existindo."""
    from app.routers.nfse import baixar_pdf_nfse

    (upload_dir / "ged").mkdir()
    (upload_dir / "ged" / "doc.pdf").write_bytes(PDF_MINIMO)
    nota = _nota_manual(pdf_path="ged/doc.pdf")
    db = _FakeDB(objs={("NotaFiscalServico", "nm1"): nota})
    with pytest.raises(HTTPException) as exc:
        await baixar_pdf_nfse("nm1", db=db, cu=_financeiro())
    assert exc.value.status_code == 404
    # Sem audit de download quando nada foi servido.
    assert not [o for o in db.added if o.__class__.__name__ == "AuditLog"]


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


def test_cancelar_motivo_acima_de_500_chars_rejeitado():
    from pydantic import ValidationError

    from app.routers.nfse import CancelarIn

    with pytest.raises(ValidationError):
        CancelarIn(motivo="x" * 501)    # max_length=500
    assert CancelarIn(motivo="x" * 500).motivo == "x" * 500   # limite passa


# ── GET /nfse/status: advogado+ OU allowlist financeira ─────────────────────────

def test_status_usa_gate_proprio():
    import inspect

    from app.routers.nfse import _req_status_nfse, status_nfse

    dep = inspect.signature(status_nfse).parameters["cu"].default.dependency
    assert dep is _req_status_nfse


def test_gate_status_permite_financeiro_e_advogado():
    from app.routers.nfse import _req_status_nfse

    for role in (UserRole.financeiro, UserRole.advogado, UserRole.socio,
                 UserRole.admin, UserRole.superadmin):
        cu = User(id="u1", role=role)
        assert _req_status_nfse(cu) is cu, role


def test_gate_status_403_perfis_baixos():
    from app.routers.nfse import _req_status_nfse

    for role in (UserRole.advogado_auxiliar, UserRole.estagiario,
                 UserRole.secretaria, UserRole.cliente_externo):
        with pytest.raises(HTTPException) as exc:
            _req_status_nfse(User(id="u1", role=role))
        assert exc.value.status_code == 403, role


# ── HTTP real (TestClient): validações que acontecem ANTES do endpoint ──────────
# max_length dos Form é aplicado pelo FastAPI na entrada — chamada direta ao
# handler não a exercita. Mini-app só com o router (padrão de
# test_bloco6_lixeira_restore): o AuthMiddleware do app principal 401aria
# antes do dependency_overrides.

@pytest.fixture()
def client_http(upload_dir):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core.database import get_db
    from app.core.rate_limit import _limpar_janelas
    from app.core.security import get_current_user
    from app.routers import nfse as nfse_router

    _limpar_janelas()
    app = FastAPI()
    app.include_router(nfse_router.router)
    db = _FakeDB()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = _financeiro
    try:
        yield TestClient(app)
    finally:
        _limpar_janelas()


_FORM_OK = {"numero": "101", "data_emissao": "2026-07-10",
            "valor": "500.00", "descricao": "Serviços advocatícios"}


def test_form_max_length_estourado_422(client_http):
    for campo, valor in (("numero", "9" * 31),          # max_length=30
                         ("chave_acesso", "A" * 61),    # max_length=60
                         ("descricao", "x" * 2001)):    # max_length=2000
        dados = dict(_FORM_OK, **{campo: valor})
        r = client_http.post("/nfse/manual", data=dados)
        assert r.status_code == 422, (campo, r.status_code, r.text[:200])


def test_form_no_limite_maximo_passa(client_http):
    dados = dict(_FORM_OK, numero="9" * 30, chave_acesso="A" * 60)
    r = client_http.post("/nfse/manual", data=dados)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["numero"] == "9" * 30


def test_status_http_financeiro_200(client_http):
    """Papel financeiro consegue o gate da UI (antes tomava 403 na hierarquia)."""
    r = client_http.get("/nfse/status")
    assert r.status_code == 200
    assert r.json()["manual_disponivel"] is True
