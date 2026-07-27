"""Política central e reversível para desativação temporária do 2FA.

FAIL-CLOSED: o padrão é 2FA LIGADO. A desativação temporária só ocorre se
`TWO_FACTOR_AUTH_ENABLED` for definido explicitamente como falso no ambiente —
nunca por omissão da variável (um deploy sem a flag roda com 2FA ativo).

A desativação não apaga `totp_secret` nem altera permanentemente `totp_enabled`
no banco. Enquanto desligada, usuários carregados pelo SQLAlchemy são tratados
como sem TOTP apenas na sessão corrente e a lista de papéis obrigados a
configurar 2FA é esvaziada no objeto de configurações em uso.

Reativação: remover a variável (ou defini-la como true) e reiniciar. Os valores
persistidos voltam a ser observados sem migration ou recadastro.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import event
from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import get_settings
from app.models.user import User

_FALSE_VALUES = frozenset({"0", "false", "no", "off", "nao", "não"})

logger = logging.getLogger("ejc.security")


def two_factor_enabled() -> bool:
    """Decisão operacional global; o padrão é LIGADO (fail-closed)."""
    return os.getenv("TWO_FACTOR_AUTH_ENABLED", "true").strip().lower() not in _FALSE_VALUES


def apply_runtime_policy(user: User) -> None:
    """Suprime TOTP somente no objeto carregado, preservando o valor no banco."""
    if not two_factor_enabled() and bool(getattr(user, "totp_enabled", False)):
        set_committed_value(user, "totp_enabled", False)


# O objeto Settings é cacheado. Alterá-lo em memória evita que login, refresh e
# troca de senha emitam sessão limitada para configuração obrigatória enquanto a
# política temporária estiver desligada. Reiniciar sem a flag falsa restaura a
# lista configurada no ambiente/default sem alterar o banco.
if not two_factor_enabled():
    get_settings().REQUIRE_2FA_ROLES = ""
    logger.warning(
        "2FA DESATIVADO por TWO_FACTOR_AUTH_ENABLED=false — decisão operacional "
        "declarada; o login aceita apenas senha. Para exigir o autenticador, "
        "defina TWO_FACTOR_AUTH_ENABLED=true (ver docs/SECURITY_2FA_TEMPORARY_DISABLE.md)."
    )


@event.listens_for(User, "load", propagate=True)
def _suppress_totp_when_disabled(user: User, _context) -> None:
    apply_runtime_policy(user)
