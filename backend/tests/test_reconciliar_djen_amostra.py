# ── tests/test_reconciliar_djen_amostra.py ───────────────────────────────────
# O script da reconciliação DJEN (RUNBOOK_RECONCILIACAO_DJEN.md, Issue #572)
# montava seu SELECT com `User.name` — atributo que o modelo não tem (o campo
# é `full_name`). O AttributeError acontecia na CONSTRUÇÃO da query, antes de
# tocar o banco: toda execução do runbook quebrava, e a única cobertura que o
# script tinha era nenhuma. Este teste exercita o caminho com uma sessão
# falsa, que é suficiente porque a falha era anterior ao `execute`.
from __future__ import annotations


async def test_reconciliar_djen_amostra_localiza_advogado(monkeypatch):
    import scripts.reconciliar_djen_amostra as mod

    class _Resultado:
        def first(self):
            return ("uid-1", "Guilherme Teixeira")

    class _DB:
        async def execute(self, stmt):
            return _Resultado()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(mod, "AsyncSessionLocal", lambda: _DB())
    # Antes da correção isto levantava AttributeError na MONTAGEM do select,
    # antes mesmo de tocar o banco — ou seja, em toda execução do runbook.
    assert await mod._localizar_advogado("252599", "mg") == ("uid-1", "Guilherme Teixeira")
