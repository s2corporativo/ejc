"""Hash de senha (bcrypt) — Fase 0/2 (seed admin) e auth."""
from app.core.security import get_password_hash, verify_password


def test_hash_roundtrip():
    h = get_password_hash("Segredo#123")
    assert h != "Segredo#123"
    assert verify_password("Segredo#123", h) is True
    assert verify_password("senha-errada", h) is False


def test_hash_eh_bcrypt():
    assert get_password_hash("x").startswith("$2")


def test_hashes_distintos_por_salt():
    assert get_password_hash("igual") != get_password_hash("igual")
