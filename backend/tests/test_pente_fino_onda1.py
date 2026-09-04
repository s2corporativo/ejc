"""Pente fino 2026-07-26 (onda 1) — teto de upload compartilhado e ownership
em assinaturas.

Cobre sem Postgres (padrão test_pente_fino_uploads_2026_07_25):
- core.upload_guard.validar_upload: vazio 422, excesso 413, magic bytes %PDF;
- analise_bancaria.analisar_documento e defesas_revisoes._texto_upload chamam
  a guarda ANTES do parse (contrato por inspeção de fonte);
- signatures.listar: staff não-gestão filtra pela carteira (subquery de
  client_ownership) e `hash_completo` restrito a advogado+ e cliente_externo.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.upload_guard import validar_upload
from app.models.user import UserRole


# ── validar_upload (guarda pura) ─────────────────────────────────────────────

def test_upload_vazio_rejeitado_422():
    with pytest.raises(HTTPException) as exc:
        validar_upload(b"")
    assert exc.value.status_code == 422


def test_upload_acima_do_teto_rejeitado_413():
    with pytest.raises(HTTPException) as exc:
        validar_upload(b"x" * (1024 * 1024 + 1), max_mb=1)
    assert exc.value.status_code == 413


def test_upload_exigir_pdf_sem_assinatura_rejeitado_422():
    with pytest.raises(HTTPException) as exc:
        validar_upload(b"MZ\x90\x00 executavel disfarcado", exigir_pdf=True)
    assert exc.value.status_code == 422


def test_upload_pdf_valido_dentro_do_teto_passa():
    assert validar_upload(b"%PDF-1.7 conteudo", max_mb=1, exigir_pdf=True) is None


def test_teto_default_vem_do_settings():
    from app.core.config import get_settings

    limite = get_settings().MAX_UPLOAD_MB
    # 1 byte acima do default estoura; sem max_mb explícito.
    with pytest.raises(HTTPException) as exc:
        validar_upload(b"x" * (limite * 1024 * 1024 + 1))
    assert exc.value.status_code == 413


# ── Contratos: guarda aplicada antes do parse ────────────────────────────────

def test_analise_bancaria_valida_antes_do_fitz():
    from app.routers.analise_bancaria import analisar_documento

    fonte = inspect.getsource(analisar_documento)
    assert "validar_upload" in fonte
    assert fonte.index("validar_upload(") < fonte.index("import fitz")


def test_texto_upload_defesas_valida_antes_do_ocr():
    from app.routers.defesas_revisoes import _texto_upload

    fonte = inspect.getsource(_texto_upload)
    assert "validar_upload" in fonte
    assert fonte.index("validar_upload") < fonte.index("expandir_arquivo")


def test_defesas_avancado_reusa_o_mesmo_helper():
    # arquivo_base/arquivo_comparado/decisao passam todos por _texto_upload.
    from app.routers import defesas_revisoes, defesas_revisoes_avancado

    assert (defesas_revisoes_avancado._texto_upload
            is defesas_revisoes._texto_upload)


# ── signatures.listar — carteira + hash_completo ─────────────────────────────

class _Res:
    def __init__(self, lista=None):
        self._lista = list(lista or [])

    def scalars(self):
        return SimpleNamespace(all=lambda: self._lista)

    def all(self):
        return self._lista


class _FakeDB:
    def __init__(self, results):
        self.results = list(results)
        self.executed = []

    async def execute(self, stmt, *a, **k):
        self.executed.append(stmt)
        return self.results.pop(0)


def _sig(client_id="c1"):
    from app.models.signature import SignatureRequest, SignatureStatus

    return SignatureRequest(
        id="sig1", document_id="d1", client_id=client_id,
        status=SignatureStatus.pendente, hash_sha256="a" * 64,
    )


def _db_uma_solicitacao():
    return _FakeDB([
        _Res([_sig()]),                    # solicitações
        _Res([("d1", "Procuração", "application/pdf", "procuracao.pdf")]),  # id/título/mimetype/filename (#1365)
        _Res([]),                          # logins do portal
    ])


async def _listar_como(cu):
    from app.routers.signatures import listar

    db = _db_uma_solicitacao()
    out = await listar(db=db, cu=cu)
    return out, db


async def test_estagiario_filtra_carteira_e_nao_ve_hash_completo():
    cu = SimpleNamespace(id="e1", role=UserRole.estagiario, client_id=None)
    out, db = await _listar_como(cu)
    item = out["data"][0]
    assert item["hash_completo"] is None
    assert item["hash"] == "a" * 16 + "…"
    # A query principal embute a subquery de carteira (client_id IN ...).
    assert "client_id IN" in str(db.executed[0])


async def test_advogado_ve_hash_completo_e_filtra_carteira():
    cu = SimpleNamespace(id="adv1", role=UserRole.advogado, client_id=None)
    out, db = await _listar_como(cu)
    assert out["data"][0]["hash_completo"] == "a" * 64
    assert "client_id IN" in str(db.executed[0])


async def test_gestao_ve_tudo_sem_filtro_de_carteira():
    cu = SimpleNamespace(id="s1", role=UserRole.socio, client_id=None)
    out, db = await _listar_como(cu)
    assert out["data"][0]["hash_completo"] == "a" * 64
    assert "client_id IN" not in str(db.executed[0])


async def test_secretaria_ve_toda_a_base_mas_sem_hash_completo():
    # Decisão de produto (client_ownership._CLIENTES_VISAO_TOTAL): a secretaria
    # opera o CRM e vê a carteira completa; hash_completo segue advogado+.
    cu = SimpleNamespace(id="sec1", role=UserRole.secretaria, client_id=None)
    out, db = await _listar_como(cu)
    assert out["data"][0]["hash_completo"] is None
    assert "client_id IN" not in str(db.executed[0])


async def test_cliente_externo_mantem_comportamento_e_hash_completo():
    cu = SimpleNamespace(id="u1", role=UserRole.cliente_externo, client_id="c1")
    out, db = await _listar_como(cu)
    item = out["data"][0]
    assert item["hash_completo"] == "a" * 64
    # Isolamento do portal preservado: filtro direto por client_id.
    assert "client_id =" in str(db.executed[0])
