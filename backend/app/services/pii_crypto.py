# ── app/services/pii_crypto.py ────────────────────────────────────────────────
# Criptografia de PII em repouso — CPF/CNPJ (LGPD, achado C6 / Bloco 6a).
#
# Duas primitivas complementares, propositalmente separadas:
#
# 1. encrypt()/decrypt() — Fernet (AES-128-CBC + HMAC, autenticado). NÃO
#    determinístico: o mesmo CPF cifrado duas vezes produz ciphertexts
#    diferentes (IV aleatório). Correto para armazenar o valor com segurança,
#    mas IMPOSSÍVEL de usar em WHERE/índice — por isso existe (2).
#
# 2. hash_documento() — HMAC-SHA256 determinístico ("índice cego"). O mesmo
#    CPF normalizado sempre gera o mesmo hash, mas o hash não é reversível
#    para o CPF original. Usado para: UNIQUE constraint, dedup no cadastro,
#    verificação de conflito de interesses (EOAB art. 134-135) — tudo que
#    precisa achar "é o mesmo CPF?" sem guardar/comparar o valor em claro.
#
# NÃO cobre busca PARCIAL (ex.: digitar 3 dígitos do CPF na busca) — decisão
# consciente (trade-off aceito no Bloco 6a): criptografia real é incompatível
# com ILIKE por natureza. Só busca EXATA sobrevive via hash_documento().
from __future__ import annotations

import hashlib
import hmac
import re

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()


def normalizar_documento(doc: str | None) -> str | None:
    """CPF/CNPJ só com dígitos, ou None. Mesma normalização usada em clients.py
    antes desta mudança — mantém compatibilidade com dados já digitados."""
    if not doc:
        return None
    limpo = re.sub(r"\D", "", doc)
    return limpo or None


def _fernet() -> Fernet:
    if not settings.PII_ENCRYPTION_KEY:
        raise RuntimeError(
            "PII_ENCRYPTION_KEY não configurada — impossível cifrar/decifrar "
            "CPF/CNPJ. Defina no .env (produção nunca gera chave efêmera "
            "automaticamente, ver core/config.py)."
        )
    return Fernet(settings.PII_ENCRYPTION_KEY.encode())


def encrypt(plaintext: str | None) -> str | None:
    """Cifra um valor (já normalizado) para armazenamento. None passa direto."""
    if plaintext is None:
        return None
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str | None) -> str | None:
    """Decifra um valor armazenado. None passa direto.

    Levanta ValueError (não silencia) se o ciphertext for inválido/corrompido
    ou cifrado com outra chave — mascarar isso retornaria dado errado sem
    avisar, pior do que falhar alto."""
    if ciphertext is None:
        return None
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise ValueError(
            "Falha ao decifrar PII — ciphertext inválido ou chave incorreta."
        ) from e


def hash_documento(doc_normalizado: str | None) -> str | None:
    """Índice cego determinístico (HMAC-SHA256, hex) para busca EXATA/dedup/
    conflito de interesses sem expor o valor em claro. None passa direto."""
    if not doc_normalizado:
        return None
    if not settings.PII_HASH_KEY:
        raise RuntimeError(
            "PII_HASH_KEY não configurada — impossível gerar índice de busca "
            "para CPF/CNPJ. Defina no .env."
        )
    return hmac.new(
        settings.PII_HASH_KEY.encode(), doc_normalizado.encode(), hashlib.sha256
    ).hexdigest()
