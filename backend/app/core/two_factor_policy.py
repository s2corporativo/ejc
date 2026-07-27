"""Política central e reversível para desativação temporária do 2FA.

A decisão não apaga `totp_secret` nem altera permanentemente `totp_enabled` no
banco. Enquanto `TWO_FACTOR_AUTH_ENABLED` não for verdadeiro, usuários carregados
pelo SQLAlchemy são tratados como sem TOTP apenas na sessão corrente e a lista de
papéis obrigados a configurar 2FA é esvaziada no objeto de configurações em uso.

Reativação: definir `TWO_FACTOR_AUTH_ENABLED=true` e reiniciar a aplicação. Os
valores persistidos voltam a ser observados sem migration ou recadastro.
"""
from __future__ import annotations

import os

from sqlalchemy import event
from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import get_settings
from app.models.user import User

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "sim"})


def two_factor_enabled() -> bool:
    """Retorna a decisão operacional global; o padrão temporário é desligado."""
    return os.getenv("TWO_FACTOR_AUTH_ENABLED", "false").strip().lower() in _TRUE_VALUES


def apply_runtime_policy(user: User) -> None:
    """Suprime TOTP somente no objeto carregado, preservando o valor no banco."""
    if not two_factor_enabled() and bool(getattr(user, "totp_enabled", False)):
        set_committed_value(user, "totp_enabled", False)


# O objeto Settings é cacheado. Alterá-lo em memória evita que login, refresh e
# troca de senha emitam sessão limitada para configuração obrigatória enquanto a
# política temporária estiver desligada. Reiniciar com a flag verdadeira restaura
# a lista configurada no ambiente/default sem alterar o banco.
if not two_factor_enabled():
    get_settings().REQUIRE_2FA_ROLES = ""


@event.listens_for(User, "load", propagate=True)
def _suppress_totp_when_disabled(user: User, _context) -> None:
    apply_runtime_policy(user)
