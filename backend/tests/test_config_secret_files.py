from pathlib import Path

import pytest

from app.core.config import Settings


def test_secret_file_sobrescreve_valor_do_ambiente(monkeypatch, tmp_path: Path):
    secret = tmp_path / "groq"
    secret.write_text("arquivo-seguro\n", encoding="utf-8")
    secret.chmod(0o600)
    monkeypatch.setenv("GROQ_API_KEY", "valor-antigo")
    monkeypatch.setenv("GROQ_API_KEY_FILE", str(secret))

    settings = Settings(APP_ENV="development")

    assert settings.GROQ_API_KEY == "arquivo-seguro"


def test_secret_file_inexistente_falha_fechado(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SMTP_PASSWORD_FILE", str(tmp_path / "nao-existe"))

    with pytest.raises(ValueError, match="SMTP_PASSWORD_FILE"):
        Settings(APP_ENV="development")


def test_secret_file_vazio_falha_fechado(monkeypatch, tmp_path: Path):
    secret = tmp_path / "vazio"
    secret.write_text("\n", encoding="utf-8")
    monkeypatch.setenv("MARITACA_API_KEY_FILE", str(secret))

    with pytest.raises(ValueError, match="MARITACA_API_KEY_FILE"):
        Settings(APP_ENV="development")
