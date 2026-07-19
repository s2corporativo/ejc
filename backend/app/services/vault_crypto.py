# ── app/services/vault_crypto.py ──────────────────────────────────────────────
# Criptografia do Cofre de Credenciais (integration_credentials, migration 108).
#
# Política de chaves (VAULT_MASTER_KEYS, CSV no .env):
#
#   * A PRIMEIRA chave do CSV é a PRIMÁRIA — é ela que CIFRA todo valor novo.
#   * TODAS as chaves do CSV DECIFRAM (MultiFernet tenta em ordem) — é isso
#     que torna a rotação de mestra um processo sem downtime.
#   * Rotação de mestra = PREPEND da chave nova na frente do CSV (a antiga
#     continua decifrando o legado) + re-encrypt em background de cada token
#     via rotacionar() (MultiFernet.rotate: decifra com qualquer chave da
#     lista, recifra com a primária). Só depois de re-cifrar tudo a chave
#     antiga pode sair do CSV.
#   * A chave vive FORA do banco (só no .env) e é EXCLUSIVA do cofre — nunca
#     derivada de SECRET_KEY (trocar o SECRET_KEY desloga usuários; não pode
#     também inutilizar credenciais) nem reusada de PII/BACKUP (rotacionar
#     uma não pode invalidar a outra).
#
# Mesma filosofia de pii_crypto.py: falhar ALTO. Token inválido/corrompido ou
# cifrado com chave que não está mais no CSV → ValueError explícito; mascarar
# isso devolveria credencial errada para uma integração externa sem avisar.
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from app.core.config import get_settings

settings = get_settings()


def chaves_configuradas() -> bool:
    """True se há ao menos uma chave mestra no CSV (cofre operável)."""
    return bool(settings.vault_master_keys_list)


def _multifernet() -> MultiFernet:
    chaves = settings.vault_master_keys_list
    if not chaves:
        raise RuntimeError(
            "VAULT_MASTER_KEYS não configurada — impossível cifrar/decifrar "
            "credenciais do cofre. Defina no .env (produção nunca gera chave "
            "efêmera automaticamente, ver core/config.py)."
        )
    return MultiFernet([Fernet(chave.encode()) for chave in chaves])


def cifrar(valor: str) -> str:
    """Cifra um segredo com a chave PRIMÁRIA (primeira do CSV)."""
    return _multifernet().encrypt(valor.encode()).decode()


def decifrar(token: str) -> str:
    """Decifra um token do cofre, tentando TODAS as chaves do CSV em ordem.

    Levanta ValueError (não silencia) se o token for inválido/corrompido ou
    cifrado com chave que já saiu do CSV — mascarar isso entregaria credencial
    errada a uma integração externa, pior do que falhar alto."""
    try:
        return _multifernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError(
            "Falha ao decifrar credencial do cofre — token inválido ou "
            "nenhuma chave de VAULT_MASTER_KEYS o decifra."
        ) from e


def rotacionar(token: str) -> str:
    """Recifra um token legado com a chave primária atual (MultiFernet.rotate).

    Uso: após PREPEND de uma chave nova em VAULT_MASTER_KEYS, chamar para cada
    registro cifrado; o retorno substitui o token antigo no banco. Idempotente
    na prática — token já cifrado com a primária sai recifrado por ela mesma."""
    try:
        return _multifernet().rotate(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError(
            "Falha ao rotacionar credencial do cofre — token inválido ou "
            "nenhuma chave de VAULT_MASTER_KEYS o decifra."
        ) from e
