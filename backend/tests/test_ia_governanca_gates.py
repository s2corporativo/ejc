"""Gate do painel de provedores de IA (`/ia-governanca/provedores`).

Regressão do pente fino E2E de 29/08/2026: `_require_gestao` listava só
("admin", "socio") e barrava o SUPERADMIN — o papel mais alto da hierarquia
(ROLE_LEVEL) ficava com 403 exatamente na rota que o CLAUDE.md aponta como
fonte de verdade sobre provedores. O conjunto correto é o mesmo do
`_require_admin_socio` do próprio arquivo.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.security import ROLE_LEVEL
from app.routers.ia_governanca import _require_gestao

_ACEITOS = ("superadmin", "admin", "socio")


def _user(role: str):
    return SimpleNamespace(role=SimpleNamespace(value=role))


@pytest.mark.parametrize("role", _ACEITOS)
def test_require_gestao_aceita_gestao(role):
    _require_gestao(_user(role))


# Negados derivados do ROLE_LEVEL: papel novo no futuro entra automaticamente
# no lado negado (allowlist exata — achado baixo da auditoria de segurança).
@pytest.mark.parametrize("role", sorted(set(ROLE_LEVEL) - set(_ACEITOS)))
def test_require_gestao_nega_demais_papeis(role):
    with pytest.raises(HTTPException) as exc:
        _require_gestao(_user(role))
    assert exc.value.status_code == 403
