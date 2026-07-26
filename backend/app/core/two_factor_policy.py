"""Política central e reversível para (des)ativação do 2FA (kill-switch).

A decisão não apaga `totp_secret` nem altera permanentemente `totp_enabled` no
banco. Enquanto o 2FA estiver desligado, usuários carregados pelo SQLAlchemy são
tratados como sem TOTP apenas na sessão corrente e a lista de papéis obrigados a
configurar 2FA é esvaziada no objeto de configurações em uso.

SYS-007: o padrão agora é fail-secure — LIGADO em produção (APP_ENV=production)
e desligado fora de produção. O kill-switch break-glass continua intacto:
definir `TWO_FACTOR_AUTH_ENABLED=false` DESLIGA mesmo em produção; `=true` LIGA
em qualquer ambiente. Reativação após break-glass: remover/`=true` a flag e
reiniciar — os valores persistidos voltam a ser observados sem migration.
`REQUIRE_2FA_ROLES` (config.py) segue definindo QUEM é obrigado quando ligado.
"""
from __future__ import annotations

import os

from sqlalchemy import event
from sqlalchemy.orm.attributes import set_committed_value

from app.core.config import get_settings
from app.models.user import User

_TRUE_VALUES = frozenset({"1", "true", "yes", "on", "sim"})


def two_factor_enabled() -> bool:
    """Decisão operacional global do 2FA (kill-switch).

    - `TWO_FACTOR_AUTH_ENABLED` definido explicitamente: honrado
      (true/1/yes/on/sim → ligado; qualquer outro valor → desligado). É o
      break-glass — permite DESLIGAR até em produção sem tocar em código.
    - Sem override explícito: LIGADO em produção (fail-secure), desligado fora
      de produção (dev/testes não são forçados a 2FA).
    """
    raw = os.getenv("TWO_FACTOR_AUTH_ENABLED")
    if raw is not None and raw.strip() != "":
        return raw.strip().lower() in _TRUE_VALUES
    return (os.getenv("APP_ENV", "") or "").strip().lower() == "production"


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
