"""Assinatura eletrônica — ownership do solicitante (DOC-106/SYS-068) e
revalidação de hash no aceite (DOC-108). Fakes locais, sem rede."""
from __future__ import annotations

import hashlib
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.config import get_settings
from app.models.user import UserRole
from app.models.signature import SignatureRequest, SignatureStatus


class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return SimpleNamespace(all=lambda: [])


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.committed = 0

    async def execute(self, *a, **k):
        return self.results.pop(0) if self.results else _Res(None)

    def add(self, obj):
        pass

    async def commit(self):
        self.committed += 1


def _req():
    return SimpleNamespace(headers={"user-agent": "pytest"},
                           client=SimpleNamespace(host="10.0.0.9"))


# ── DOC-106: ownership do solicitante ─────────────────────────────────────────

async def test_criar_solicitacao_barra_advogado_de_outra_carteira():
    from app.routers.signatures import criar_solicitacao, CriarSolicitacaoReq

    # doc de cliente ao qual o advogado NÃO tem caso atribuído (sem case_id):
    doc = SimpleNamespace(id="d1", client_id="cli-x", case_id=None,
                          uploaded_by="outro-uploader", titulo="Procuração",
                          confidencialidade=SimpleNamespace(value="normal"),
                          filepath="p.pdf")
    # 1º execute → doc; 2º execute (dentro de _verificar_acesso_cliente_sem_caso)
    # → nenhum caso do advogado com esse cliente → 403.
    db = _FakeDB([_Res(one=doc), _Res(one=None)])
    cu = SimpleNamespace(id="adv-sem-acesso", role=UserRole.advogado, client_id=None)
    with pytest.raises(HTTPException) as ei:
        await criar_solicitacao(
            CriarSolicitacaoReq(document_id="d1", client_id="cli-x"), db=db, cu=cu
        )
    assert ei.value.status_code == 403


# ── DOC-108: revalidação de hash no aceite ────────────────────────────────────

async def test_assinar_hash_divergente_barra_e_invalida():
    from app.routers.signatures import assinar

    settings = get_settings()
    rel = f"teste_sig_{uuid4().hex}.pdf"
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    full = os.path.join(settings.UPLOAD_DIR, rel)
    with open(full, "wb") as f:
        f.write(b"conteudo ALTERADO apos a solicitacao")
    try:
        sr = SignatureRequest(id="sig1", document_id="d1", client_id="c1",
                              status=SignatureStatus.pendente,
                              hash_sha256="0" * 64)  # não bate com o arquivo
        doc = SimpleNamespace(id="d1", filepath=rel)
        db = _FakeDB([_Res(one=sr), _Res(one=doc)])
        cu = SimpleNamespace(id="cli1", role=UserRole.cliente_externo, client_id="c1")
        with pytest.raises(HTTPException) as ei:
            await assinar("sig1", _req(), db=db, cu=cu)
        assert ei.value.status_code == 409
        # invalidada (cancelada) — não fica pendente para nova tentativa cega:
        assert sr.status == SignatureStatus.cancelado
    finally:
        os.remove(full)


async def test_assinar_hash_coincidente_registra_revalidado():
    from app.routers.signatures import assinar

    settings = get_settings()
    rel = f"teste_sig_ok_{uuid4().hex}.pdf"
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    full = os.path.join(settings.UPLOAD_DIR, rel)
    conteudo = b"conteudo integro assinado"
    with open(full, "wb") as f:
        f.write(conteudo)
    try:
        h = hashlib.sha256(conteudo).hexdigest()
        sr = SignatureRequest(id="sig2", document_id="d2", client_id="c1",
                              status=SignatureStatus.pendente, hash_sha256=h)
        doc = SimpleNamespace(id="d2", filepath=rel)
        db = _FakeDB([_Res(one=sr), _Res(one=doc)])
        cu = SimpleNamespace(id="cli1", role=UserRole.cliente_externo, client_id="c1")
        out = await assinar("sig2", _req(), db=db, cu=cu)
        assert sr.status == SignatureStatus.assinado
        assert out["comprovante"]["hash_revalidado"] is True
        assert out["comprovante"]["hash_documento"] == h
    finally:
        os.remove(full)
