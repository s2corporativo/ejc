"""Regressões dos findings de review da Fase A DB-03."""
from __future__ import annotations

from pathlib import Path
from sqlalchemy.exc import IntegrityError


def test_downgrade_158_falha_antes_de_drop_se_houver_pii_cifrada():
    fonte = (Path(__file__).resolve().parents[1] / "alembic/versions/158_case_partes_trabalhista_pii_expand.py").read_text(encoding="utf-8")
    bloco = fonte.split("def downgrade() -> None:", 1)[1]
    assert "RAISE EXCEPTION" in bloco
    for marcador in ("cpf_cnpj_enc IS NOT NULL", "email_enc IS NOT NULL", "telefone_enc IS NOT NULL", "cid_enc IS NOT NULL"):
        assert marcador in bloco
    assert bloco.index("RAISE EXCEPTION") < bloco.index("DROP COLUMN")


class _OrigDireta(Exception):
    constraint_name = "ux_case_partes_case_doc_hash_active"

class _Diag:
    constraint_name = "ux_case_partes_case_doc_hash_active"

class _OrigDiag(Exception):
    diag = _Diag()

class _OrigOutra(Exception):
    constraint_name = "case_partes_client_id_fkey"


def _integrity(orig: Exception) -> IntegrityError:
    return IntegrityError("INSERT", {}, orig)


def test_integrity_409_reconhece_somente_constraint_do_hmac():
    from app.routers.case_partes import _integrity_e_duplicidade_documento
    assert _integrity_e_duplicidade_documento(_integrity(_OrigDireta())) is True
    assert _integrity_e_duplicidade_documento(_integrity(_OrigDiag())) is True
    assert _integrity_e_duplicidade_documento(_integrity(_OrigOutra())) is False
