"""Issue #697 — três lacunas no upload do GED (backend/app/routers/documents.py):

1. Hash de integridade (sha256) gravado no upload e conferível na resposta/download.
2. Varredura antivírus opt-in (MALWARE_SCAN_ENABLED, default OFF) — desligada não
   muda o fluxo; ligada, EICAR é recusado, arquivo limpo passa, serviço
   indisponível BLOQUEIA o upload (fail-closed — decisão registrada no PR).
3. `_bloquear_comprovante_protocolo` generalizado para CentroCusto.comprovante_id
   e FeePayment.comprovante_doc_id, além de LegalDoc.protocolo_comprovante_doc_id.

Fakes no padrão de tests/test_correcoes_go_live.py (sem harness global de banco).
Dados 100% fictícios.
"""
from __future__ import annotations

import hashlib
import io
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from fastapi import UploadFile
from starlette.datastructures import Headers

from app.models.document import DocConfidencialidade
from app.routers import documents as docs_mod


# ── Fakes ─────────────────────────────────────────────────────────────────────

class _Res:
    def __init__(self, one=None):
        self._one = one

    def scalar_one_or_none(self):
        return self._one


class _FakeDB:
    """Devolve resultados na ordem da fila `results` (um por execute)."""

    def __init__(self, results=None):
        self.results = list(results or [])
        self.added = []
        self.committed = 0

    async def execute(self, *_a, **_k):
        r = self.results.pop(0) if self.results else None
        return r if isinstance(r, _Res) else _Res(r)

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed += 1


def _cu_socio(uid="user-1"):
    return SimpleNamespace(id=uid, role=SimpleNamespace(value="socio"))


def _upload_file(nome: str, conteudo: bytes) -> UploadFile:
    return UploadFile(
        file=io.BytesIO(conteudo),
        filename=nome,
        headers=Headers({"content-type": "application/pdf"}),
    )


_PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF conteudo de teste do GED"
# String de teste padrão da industria antivirus (EICAR) — NAO e malware real.
_EICAR = (
    b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$'
    b'EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
)


def _preparar_upload_basico(monkeypatch, tmp_path):
    """Isola o handler upload() de I/O externo não relevante ao teste:
    diretório gravável, magic-bytes já 'validado' e OCR desligado."""
    monkeypatch.setattr(docs_mod.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(docs_mod, "_validar_conteudo", lambda ext, conteudo: "application/pdf")
    monkeypatch.setattr(docs_mod, "extrair_texto", lambda *a, **k: None)


# ── 1. Hash de integridade ───────────────────────────────────────────────────

async def test_upload_grava_sha256_conferivel(monkeypatch, tmp_path):
    _preparar_upload_basico(monkeypatch, tmp_path)
    monkeypatch.setattr(docs_mod.settings, "MALWARE_SCAN_ENABLED", False)

    db = _FakeDB()
    resp = await docs_mod.upload(
        background_tasks=BackgroundTasks(),
        file=_upload_file("contrato.pdf", _PDF),
        titulo="Contrato de teste", tipo=None,
        confidencialidade="confidencial",
        case_id=None, client_id=None,
        db=db, cu=_cu_socio(),
    )

    # Digest calculado de forma independente pelo teste — não reaproveita
    # nenhum estado interno do handler.
    esperado = hashlib.sha256(_PDF).hexdigest()
    assert resp["sha256"] == esperado

    doc_criado = next(o for o in db.added if isinstance(o, docs_mod.Document))
    assert doc_criado.sha256 == esperado


# ── 2a. Varredura desligada (default) — não-regressão ────────────────────────

async def test_upload_com_varredura_desligada_e_identico_ao_fluxo_anterior(monkeypatch, tmp_path):
    _preparar_upload_basico(monkeypatch, tmp_path)
    assert docs_mod.settings.MALWARE_SCAN_ENABLED is False  # default do config.py

    def _nao_deveria_ser_chamado(*a, **k):
        raise AssertionError("escanear() não deve ser importado/chamado com a flag OFF")
    monkeypatch.setattr(
        "app.services.malware_scan_service.escanear", _nao_deveria_ser_chamado
    )

    db = _FakeDB()
    resp = await docs_mod.upload(
        background_tasks=BackgroundTasks(),
        file=_upload_file("contrato.pdf", _PDF),
        titulo="Contrato de teste", tipo=None,
        confidencialidade="confidencial",
        case_id=None, client_id=None,
        db=db, cu=_cu_socio(),
    )
    assert resp["detail"] == "Documento enviado"
    assert db.committed == 1


# ── 2b. Varredura ligada — EICAR recusado, limpo passa, serviço indisponível bloqueia ──

async def test_upload_com_varredura_ligada_recusa_eicar(monkeypatch, tmp_path):
    _preparar_upload_basico(monkeypatch, tmp_path)
    monkeypatch.setattr(docs_mod.settings, "MALWARE_SCAN_ENABLED", True)

    async def _detecta_eicar(conteudo, **kwargs):
        assert conteudo == _EICAR  # a string EICAR real chega até o cliente de varredura
        return "Eicar-Test-Signature"
    monkeypatch.setattr("app.services.malware_scan_service.escanear", _detecta_eicar)

    db = _FakeDB()
    with pytest.raises(HTTPException) as exc:
        await docs_mod.upload(
            background_tasks=BackgroundTasks(),
            file=_upload_file("eicar.pdf", _EICAR),
            titulo="Arquivo de teste EICAR", tipo=None,
            confidencialidade="confidencial",
            case_id=None, client_id=None,
            db=db, cu=_cu_socio(),
        )
    assert exc.value.status_code == 422
    assert "Eicar-Test-Signature" in exc.value.detail
    assert db.added == []       # nenhum Document persistido
    assert db.committed == 0


async def test_upload_com_varredura_ligada_aceita_arquivo_limpo(monkeypatch, tmp_path):
    _preparar_upload_basico(monkeypatch, tmp_path)
    monkeypatch.setattr(docs_mod.settings, "MALWARE_SCAN_ENABLED", True)

    async def _limpo(conteudo, **kwargs):
        return None
    monkeypatch.setattr("app.services.malware_scan_service.escanear", _limpo)

    db = _FakeDB()
    resp = await docs_mod.upload(
        background_tasks=BackgroundTasks(),
        file=_upload_file("contrato.pdf", _PDF),
        titulo="Contrato de teste", tipo=None,
        confidencialidade="confidencial",
        case_id=None, client_id=None,
        db=db, cu=_cu_socio(),
    )
    assert resp["detail"] == "Documento enviado"
    assert resp["sha256"] == hashlib.sha256(_PDF).hexdigest()


async def test_upload_com_varredura_ligada_e_servico_fora_do_ar_bloqueia_fail_closed(
    monkeypatch, tmp_path
):
    """Decisão registrada no PR: clamd indisponível com a flag LIGADA nunca
    aceita o upload como 'não varrido' — bloqueia (503). Controle de
    segurança explicitamente pedido pelo operador, não recurso degradável."""
    _preparar_upload_basico(monkeypatch, tmp_path)
    monkeypatch.setattr(docs_mod.settings, "MALWARE_SCAN_ENABLED", True)

    async def _indisponivel(conteudo, **kwargs):
        from app.services.malware_scan_service import MalwareScanIndisponivelError
        raise MalwareScanIndisponivelError("clamd recusou a conexão")
    monkeypatch.setattr("app.services.malware_scan_service.escanear", _indisponivel)

    db = _FakeDB()
    with pytest.raises(HTTPException) as exc:
        await docs_mod.upload(
            background_tasks=BackgroundTasks(),
            file=_upload_file("contrato.pdf", _PDF),
            titulo="Contrato de teste", tipo=None,
            confidencialidade="confidencial",
            case_id=None, client_id=None,
            db=db, cu=_cu_socio(),
        )
    assert exc.value.status_code == 503
    assert db.added == []
    assert db.committed == 0


# ── 3. Guarda de comprovante — CentroCusto e FeePayment (além de LegalDoc) ───

def _documento(case_id=None, uploaded_by="user-1", deleted_at=None):
    return SimpleNamespace(
        id="doc-1", case_id=case_id, uploaded_by=uploaded_by,
        deleted_at=deleted_at, client_id=None,
        confidencialidade=DocConfidencialidade.normal,
    )


async def test_bloquear_comprovante_sem_nenhuma_referencia_nao_levanta(monkeypatch):
    """Base de comparação: sem vínculo em nenhuma das três tabelas, a checagem
    não bloqueia — é o comportamento que a exclusão/movimentação teria em
    seguida (sem exceção alguma vinda daqui)."""
    db = _FakeDB(results=[None, None, None])
    await docs_mod._bloquear_comprovante_protocolo(db, "doc-1", "excluído")


async def test_bloquear_comprovante_referenciado_por_centro_custo_409(monkeypatch):
    ref_custo = SimpleNamespace(
        id="cc-1", descricao="Custas do recurso", case_id="caso-9",
    )
    # Fila: LegalDoc (nenhuma referência) → CentroCusto (referenciado).
    db = _FakeDB(results=[None, ref_custo])
    with pytest.raises(HTTPException) as exc:
        await docs_mod._bloquear_comprovante_protocolo(db, "doc-1", "excluído")
    assert exc.value.status_code == 409
    assert "Custas do recurso" in exc.value.detail
    assert "cc-1" in exc.value.detail


async def test_bloquear_comprovante_referenciado_por_pagamento_honorario_409(monkeypatch):
    ref_fee = SimpleNamespace(id="pgto-1", fee_id="fee-9")
    # Fila: LegalDoc (None) → CentroCusto (None) → FeePayment (referenciado).
    db = _FakeDB(results=[None, None, ref_fee])
    with pytest.raises(HTTPException) as exc:
        await docs_mod._bloquear_comprovante_protocolo(db, "doc-1", "excluído")
    assert exc.value.status_code == 409
    assert "pgto-1" in exc.value.detail
    assert "fee-9" in exc.value.detail


async def test_excluir_documento_referenciado_por_centro_custo_e_bloqueado(monkeypatch):
    """Prova da diferença (critério 4): o MESMO documento, com um lançamento de
    centro de custos apontando para ele, passa de exclusão permitida
    (teste anterior, sem referência) para 409 — só a referência muda."""
    d = _documento()
    ref_custo = SimpleNamespace(id="cc-1", descricao="Perícia", case_id="caso-9")
    db = _FakeDB(results=[d, None, ref_custo])  # Document, LegalDoc, CentroCusto
    with pytest.raises(HTTPException) as exc:
        await docs_mod.remover(doc_id="doc-1", db=db, cu=_cu_socio())
    assert exc.value.status_code == 409
    assert d.deleted_at is None  # nunca chegou a marcar soft-delete


async def test_mover_documento_de_caso_referenciado_por_centro_custo_e_bloqueado(monkeypatch):
    """Critério 5: o mesmo guarda vale para PATCH (mover de caso), como já
    ocorria para peças (LegalDoc)."""
    d = _documento(case_id=None)
    ref_custo = SimpleNamespace(id="cc-1", descricao="Diligência", case_id="caso-9")
    db = _FakeDB(results=[d, None, ref_custo])  # Document, LegalDoc, CentroCusto
    req = docs_mod.DocumentPatchRequest(case_id="caso-novo")
    with pytest.raises(HTTPException) as exc:
        await docs_mod.atualizar_metadados(doc_id="doc-1", req=req, db=db, cu=_cu_socio())
    assert exc.value.status_code == 409
    assert d.case_id is None  # nunca chegou a mover
