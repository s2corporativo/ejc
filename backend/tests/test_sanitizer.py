"""Sanitização LGPD — Fase 3B (PII fora do RAG/Groq). REATIVADA na auditoria
(LGPD art. 33/46): CPF/CNPJ/nome/processo não podem sair em claro do VPS para
Anthropic/Groq. Estes testes fixam o contrato REAL restaurado."""
from app.services.sanitizer import (
    sanitizar_pii,
    validar_sem_pii,
    sanitizar_pii_interno,
    validar_sem_pii_interno,
)
from app.services.ai_guard import sanitizar_ou_abortar


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


# ── Uso interno (2026-07-04): CPF/CNPJ visíveis só na barreira de entrada ────

def test_sanitizar_pii_interno_preserva_cpf_cnpj_mas_remove_o_resto():
    out, mudou = sanitizar_pii_interno(
        "CPF 123.456.789-09, CNPJ 12.345.678/0001-99, "
        "processo 1234567-89.2020.8.13.0024, contato a@b.com"
    )
    assert "123.456.789-09" in out
    assert "12.345.678/0001-99" in out
    assert "[PROCESSO]" in out
    assert "[EMAIL]" in out
    assert mudou is True


def test_validar_sem_pii_interno_ignora_cpf_cnpj():
    assert validar_sem_pii_interno("resto 123.456.789-09 e 12.345.678/0001-99") == []
    assert "EMAIL" in validar_sem_pii_interno("contato a@b.com")


def test_sanitizar_ou_abortar_mantem_cpf_cnpj_para_uso_interno():
    """Barreira de ENTRADA: CPF/CNPJ passam íntegros (uso interno)."""
    limpo, _ = sanitizar_ou_abortar("Cliente CPF 123.456.789-09, CNPJ 12.345.678/0001-99")
    assert "123.456.789-09" in limpo
    assert "12.345.678/0001-99" in limpo


def test_sanitizar_ou_abortar_continua_mascarando_outros_tipos_de_pii():
    """RG/e-mail/telefone/CEP/processo continuam sendo removidos na barreira de
    entrada (só CPF/CNPJ deixaram de ser tratados como PII aqui)."""
    limpo, mudou = sanitizar_ou_abortar(
        "Processo 1234567-89.2020.8.13.0024 contato a@b.com"
    )
    assert "1234567-89.2020.8.13.0024" not in limpo
    assert "a@b.com" not in limpo
    assert "[PROCESSO]" in limpo
    assert "[EMAIL]" in limpo
    assert mudou is True


def test_sanitizar_ou_abortar_nao_aborta_mais_com_pii_residual(monkeypatch):
    """Decisão de produto (2026-07-06): a barreira de ENTRADA "sanitiza e SEGUE"
    — NÃO aborta mais (HTTP 422) quando sobra PII residual; retorna o texto
    sanitizado e apenas registra. A proteção real do provider externo é a
    barreira FINAL do gateway (testada em test_ai_core_nucleo), não este abort.
    Força um residual artificial e confirma que NÃO há mais exceção."""
    import app.services.ai_guard as ai_guard_mod

    monkeypatch.setattr(ai_guard_mod, "validar_sem_pii_interno", lambda t: ["EMAIL"])
    # Antes levantava HTTPException(422); agora deve retornar normalmente.
    limpo, _mudou = ai_guard_mod.sanitizar_ou_abortar("texto qualquer")
    assert isinstance(limpo, str)


def test_barreira_externa_do_gateway_remove_cpf_cnpj():
    """A barreira que protege Anthropic/Groq (ai_gateway) usa as funções
    completas: CPF/CNPJ é mascarado antes do provider externo e não sobra
    residual (LGPD art. 33/46)."""
    from app.services.ai_gateway import _sanitizar_messages_externo
    msgs = [{"role": "user", "content": "CPF 123.456.789-09 contato a@b.com"}]
    limpos, residual = _sanitizar_messages_externo(msgs)
    assert "[CPF]" in limpos[0]["content"]
    assert "[EMAIL]" in limpos[0]["content"]
    assert "123.456.789-09" not in limpos[0]["content"]
    assert residual == []
