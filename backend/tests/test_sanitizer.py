"""Sanitização LGPD — Fase 3B (PII fora do RAG/Groq)."""
from app.services.sanitizer import sanitizar_pii, validar_sem_pii


def test_mascara_cpf_e_cnpj():
    out, mudou = sanitizar_pii("CPF 123.456.789-09 e CNPJ 12.345.678/0001-99")
    assert "[CPF]" in out
    assert "[CNPJ]" in out
    assert mudou is True


def test_mascara_processo_e_email():
    out, _ = sanitizar_pii("Processo 1234567-89.2020.8.13.0024 contato a@b.com")
    assert "[PROCESSO]" in out
    assert "[EMAIL]" in out


def test_nomes_proteger():
    out, mudou = sanitizar_pii("O cliente João da Silva compareceu", ["João da Silva"])
    assert "João da Silva" not in out
    assert "[PARTE_1]" in out
    assert mudou is True


def test_texto_limpo_nao_muda():
    out, mudou = sanitizar_pii("peça sobre direito do trabalho sem dados pessoais")
    assert mudou is False
    assert validar_sem_pii(out) == []


def test_validar_detecta_residual():
    assert "CPF" in validar_sem_pii("resto 123.456.789-09")
