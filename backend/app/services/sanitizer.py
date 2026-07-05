# ── app/services/sanitizer.py ────────────────────────────────────────────────
# Sanitização de PII em prompts de IA — DESATIVADA.
#
# Decisão do titular do sistema (2026-07-05): os prompts de IA passam a levar
# os dados como digitados/armazenados (CPF, CNPJ, nomes, processo, contato),
# porque o mascaramento degradava as análises — a IA não conseguia trabalhar
# o caso sem saber de quem/do que se trata. Consequência assumida: provedores
# EXTERNOS (Anthropic/Groq, fora do VPS) também recebem esses dados em claro.
#
# As funções abaixo são mantidas como PASSTHROUGH para preservar o contrato
# dos ~40 pontos de chamada (ai_guard, ai_gateway, services de IA) e permitir
# reativação simples: a implementação anterior (regex de CPF/CNPJ/processo/
# RG/OAB/e-mail/telefone/CEP/cartão/PIX + nomes protegidos) está no histórico
# git deste arquivo.
from __future__ import annotations


def sanitizar_pii(texto: str, nomes_proteger: list[str] | None = None) -> tuple[str, bool]:
    """Passthrough — devolve o texto intacto. Retorna (texto, False)."""
    return texto, False


def sanitizar_pii_interno(texto: str, nomes_proteger: list[str] | None = None) -> tuple[str, bool]:
    """Passthrough — devolve o texto intacto. Retorna (texto, False)."""
    return texto, False


def validar_sem_pii(texto: str) -> list[str]:
    """Passthrough — nunca acusa PII residual (lista vazia = liberado)."""
    return []


def validar_sem_pii_interno(texto: str) -> list[str]:
    """Passthrough — nunca acusa PII residual (lista vazia = liberado)."""
    return []
