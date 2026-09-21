"""Binding usuário↔arquivo dos PDFs gerados — Auditoria Real 2026-09-20.

§11 S2 (P0, ambiental), S3 (trabalhista) e S10 (previdenciário/tributário):
a confidencialidade dos arquivos gerados não pode ser apenas a não-
adivinhabilidade do UUID (capability URL). O arnês único
``services/visual_law_files`` agora registra um sidecar ``.origem.json`` na
geração e o download exige o próprio criador (ou perfil de gestão), fail-closed
para arquivo sem vínculo.

Provas: criador baixa; outro usuário é negado; gestão passa; sidecar ausente
(legado pré-hardening) é negado; purga TTL remove sidecar expirado.
"""

from __future__ import annotations

from types import SimpleNamespace
import time

import pytest
from fastapi import HTTPException

from app.models.user import UserRole
from app.services import visual_law_files as vlf


def _user(role: UserRole = UserRole.advogado, uid: str = "adv-1") -> SimpleNamespace:
    return SimpleNamespace(id=uid, role=role, full_name="Fulana")


@pytest.fixture()
def out_dir(tmp_path):
    return str(tmp_path)


def test_criador_baixa_arquivo(out_dir):
    vlf.registrar_origem(out_dir, "abc", criado_por="adv-1")
    vlf.exigir_origem(out_dir, "abc", _user(uid="adv-1"))  # não levanta


def test_outro_usuario_negado(out_dir):
    vlf.registrar_origem(out_dir, "abc", criado_por="adv-1")
    with pytest.raises(HTTPException) as e:
        vlf.exigir_origem(out_dir, "abc", _user(uid="adv-2"))
    assert e.value.status_code == 403


def test_gestao_passa_de_qualquer_usuario(out_dir):
    vlf.registrar_origem(out_dir, "abc", criado_por="adv-1")
    vlf.exigir_origem(out_dir, "abc", _user(role=UserRole.socio, uid="socio-9"))  # não levanta


def test_sidecar_ausente_fail_closed(out_dir):
    # Arquivo pré-hardening (sem vínculo): nunca liberar — instrução regenerar.
    with pytest.raises(HTTPException) as e:
        vlf.exigir_origem(out_dir, "sem-vinculo", _user(uid="adv-1"))
    assert e.value.status_code == 403
    assert "gere" in e.value.detail.lower()


def test_registrar_sem_diretorio_nao_levanta_e_download_fica_negado(out_dir):
    # Best-effort: registrar falha silenciosa → fail-closed no download.
    import os

    vlf.registrar_origem(os.path.join(out_dir, "nao-existe"), "abc", criado_por="adv-1")
    with pytest.raises(HTTPException):
        vlf.exigir_origem(out_dir, "abc", _user(uid="adv-1"))


def test_purga_remove_pdf_e_sidecar_expirados(out_dir, monkeypatch):
    monkeypatch.setattr(vlf, "PDF_TTL_SEGUNDOS", 10)
    pdf = out_dir + "/x.pdf"
    side = out_dir + f"/x{vlf.SUFIJO_ORIGEM}"
    vivo = out_dir + "/vivo.pdf"
    for p in (pdf, side, vivo):
        with open(p, "w") as fh:
            fh.write("x")
    antigo = time.time() - 100
    import os

    os.utime(pdf, (antigo, antigo))
    os.utime(side, (antigo, antigo))
    vlf.purgar_antigos(out_dir, ttl_segundos=10)
    import os

    assert not os.path.exists(pdf)
    assert not os.path.exists(side)
    assert os.path.exists(vivo)


def test_validar_uuid_ainda_barra_traversal(out_dir):
    with pytest.raises(HTTPException):
        vlf.validar_uuid("../secrets")
