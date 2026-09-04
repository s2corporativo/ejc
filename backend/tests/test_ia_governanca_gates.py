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


# ── AUD27-P2-1 (extensão) — os dois painéis contam a MESMA coisa ─────────────


def test_dashboard_e_guardrails_usam_o_mesmo_filtro_de_peca_viva():
    """`/dashboard` e `/guardrails` medem a mesma cobertura HITL.

    O `/guardrails` foi corrigido para ignorar peça de caso EXCLUÍDO
    (`_peca_de_caso_vivo`), mas o `/dashboard` seguia com o filtro ingênuo
    (`LegalDoc.deleted_at IS NULL`). Dois painéis do mesmo controle com
    filtros diferentes dão duas verdades sobre a mesma cobertura de revisão —
    a armadilha de "fonte de verdade divergente" que o CLAUDE.md já registra
    para os endpoints de provedores de IA.

    O teste lê a FONTE porque o defeito é da condição da consulta, e checá-la
    por AST pega a divergência sem precisar de Postgres.
    """
    import ast
    import inspect

    from app.routers import ia_governanca

    fonte = inspect.getsource(ia_governanca.dashboard_governanca)
    corpo = ast.parse(inspect.cleandoc(fonte).replace("@router.get", "# @router.get"))

    contadores = [
        n for n in ast.walk(corpo)
        if isinstance(n, ast.Assign)
        and any(getattr(t, "id", "").startswith("pecas_ia_") for t in n.targets)
    ]
    assert len(contadores) == 2, "os contadores de peça de IA do dashboard mudaram de forma"

    for node in contadores:
        trecho = ast.dump(node)
        assert "_viva_dash" in trecho or "_peca_de_caso_vivo" in trecho, (
            "contador de peça de IA do /dashboard voltou ao filtro ingênuo — "
            "vai divergir do /guardrails contando peça de caso excluído"
        )
        assert "deleted_at" not in trecho, (
            "filtro ingênuo remanescente: use só `_peca_de_caso_vivo()`, que já "
            "cobre o deleted_at da própria peça"
        )
