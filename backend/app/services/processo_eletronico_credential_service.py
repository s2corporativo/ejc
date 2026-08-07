# ── app/services/processo_eletronico_credential_service.py ──────────────────
# Cifra/decifra id_consultante e senha_consultante_ref das credenciais MNI
# (tabela `credenciais_processo_eletronico`, migração 132).
#
# Reaproveita o primitivo Fernet de app/services/pii_crypto.py (mesma chave
# PII_ENCRYPTION_KEY já usada para CPF/CNPJ) em vez de inventar uma cifra
# nova — é o padrão do projeto (ver CLAUDE.md, "reaproveite pii_crypto.py").
#
# NÃO confundir com app/routers/credential_vault.py + credential_vault_service:
# aquele é o Cofre de Credenciais genérico do EJC (chaves de API de
# providers). Este módulo é específico do MNI: guarda idConsultante/senha
# por (advogado, tribunal), nunca devolve o valor em claro para camadas
# acima do necessário (só o MNIConnector decifra, dentro da task Celery).
from __future__ import annotations

from app.services.pii_crypto import decrypt, encrypt


def cifrar_id_consultante(id_consultante: str | None) -> str | None:
    return encrypt(id_consultante)


def decifrar_id_consultante(id_consultante_cifrado: str | None) -> str | None:
    return decrypt(id_consultante_cifrado)


def cifrar_senha(senha: str | None) -> str | None:
    return encrypt(senha)


def decifrar_senha(senha_ref: str | None) -> str | None:
    return decrypt(senha_ref)
