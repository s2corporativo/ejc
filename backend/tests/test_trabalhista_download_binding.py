"""SEC-03: o UUID de um PDF trabalhista não é uma autorização.

A rota deve exigir o vínculo criado_por↔arquivo, negar sidecar ausente e
permitir somente o criador ou a gestão.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.user import UserRole
from app.routers import trabalhista_liquidacao as router
from app.services import visual_law_files as vlf


def _user(user_id: str, role: UserRole = UserRole.advogado) -> SimpleNamespace:
    return SimpleNamespace(id=user_id, role=role, full_name="Usuário de teste")


@pytest.mark.asyncio
async def test_download_trabalhista_exige_binding_do_criador(tmp_path, monkeypatch):
    arquivo_id = str(uuid4())
    monkeypatch.setattr(router, "_pdf_dir", lambda: str(tmp_path))
    pdf = Path(tmp_path) / f"liquidacao_{arquivo_id}.pdf"
    pdf.write_bytes(b"%PDF-test")
    vlf.registrar_origem(str(tmp_path), arquivo_id, criado_por="u-criador")

    resposta = await router.download_planilha(arquivo_id, _user("u-criador"))

    assert resposta.path == str(pdf)
    assert resposta.media_type == "application/pdf"


@pytest.mark.asyncio
async def test_download_trabalhista_nega_outro_usuario(tmp_path, monkeypatch):
    arquivo_id = str(uuid4())
    monkeypatch.setattr(router, "_pdf_dir", lambda: str(tmp_path))
    (Path(tmp_path) / f"liquidacao_{arquivo_id}.pdf").write_bytes(b"%PDF-test")
    vlf.registrar_origem(str(tmp_path), arquivo_id, criado_por="u-criador")

    with pytest.raises(HTTPException) as exc:
        await router.download_planilha(arquivo_id, _user("u-outro"))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_download_trabalhista_nega_arquivo_legado_sem_sidecar(tmp_path, monkeypatch):
    arquivo_id = str(uuid4())
    monkeypatch.setattr(router, "_pdf_dir", lambda: str(tmp_path))
    (Path(tmp_path) / f"liquidacao_{arquivo_id}.pdf").write_bytes(b"%PDF-legacy")

    with pytest.raises(HTTPException) as exc:
        await router.download_planilha(arquivo_id, _user("u-criador"))

    assert exc.value.status_code == 403
    assert "vínculo" in exc.value.detail.lower()
