"""Sanitização de PII em prompts de IA — DESATIVADA (decisão do titular,
2026-07-05): as funções do sanitizer viraram passthrough. Estes testes fixam
o contrato atual: nada é mascarado, nada aborta, e o gateway não bloqueia
provider externo por PII. (O comportamento antigo está no histórico git.)"""
from app.services.sanitizer import (
    sanitizar_pii,
    validar_sem_pii,
    sanitizar_pii_interno,
    validar_sem_pii_interno,
)
from app.services.ai_guard import sanitizar_ou_abortar


def test_sanitizar_pii_e_passthrough():
    texto = ("CPF 123.456.789-09, CNPJ 12.345.678/0001-99, "
             "processo 1234567-89.2020.8.13.0024, contato a@b.com")
    out, mudou = sanitizar_pii(texto, ["João da Silva"])
    assert out == texto
    assert mudou is False


def test_sanitizar_pii_interno_e_passthrough():
    texto = "CPF 123.456.789-09 contato a@b.com tel (31) 99999-9999"
    out, mudou = sanitizar_pii_interno(texto)
    assert out == texto
    assert mudou is False


def test_validar_sem_pii_nunca_acusa_residual():
    assert validar_sem_pii("resto 123.456.789-09 e a@b.com") == []
    assert validar_sem_pii_interno("contato a@b.com") == []
    # OAB (padrão adicionado à sanitização antiga) também não acusa residual.
    assert validar_sem_pii("subscritor OAB/MG 123.456") == []


def test_oab_tambem_e_passthrough():
    # A main adicionou mascaramento de OAB ([OAB]) à implementação antiga;
    # com a sanitização desativada, a inscrição passa intacta.
    texto = "Dr. Fulano, OAB/MG 123.456, protocolou"
    out, mudou = sanitizar_pii(texto)
    assert out == texto
    assert mudou is False


def test_sanitizar_ou_abortar_nao_mascara_nem_aborta():
    """Barreira de ENTRADA desativada: texto passa intacto, sem 422."""
    texto = ("Cliente CPF 123.456.789-09, processo 1234567-89.2020.8.13.0024, "
             "contato a@b.com")
    limpo, mudou = sanitizar_ou_abortar(texto)
    assert limpo == texto
    assert mudou is False


def test_barreira_externa_do_gateway_nao_bloqueia():
    """A barreira final do gateway (Anthropic/Groq) vira no-op: conteúdo em
    claro e residual sempre vazio (nenhum provider é pulado por PII)."""
    from app.services.ai_gateway import _sanitizar_messages_externo
    msgs = [{"role": "user", "content": "CPF 123.456.789-09 contato a@b.com"}]
    limpos, residual = _sanitizar_messages_externo(msgs)
    assert limpos[0]["content"] == msgs[0]["content"]
    assert residual == []
