"""Verificador de citações (IA-05) — extrai súmulas/artigos e checa na base."""


class _Row:
    def first(self):
        return None   # base "vazia": nada confirmado


class _FakeDB:
    async def execute(self, *a, **k):
        return _Row()


async def test_extrai_e_marca_nao_confirmadas():
    from app.services.citation_check import verificar_citacoes
    texto = "Aplica-se a Súmula 7 do STJ e o art. 927 do CC ao caso."
    r = await verificar_citacoes(_FakeDB(), texto)
    assert r["total"] == 2                       # achou súmula + artigo
    assert r["confirmadas"] == 0                  # base fake não confirma nada
    assert r["nao_encontradas"] == 2
    rotulos = [c["citacao"] for c in r["citacoes"]]
    assert any("Súmula 7" in x for x in rotulos)
    assert any("927" in x for x in rotulos)


async def test_texto_sem_citacao():
    from app.services.citation_check import verificar_citacoes
    r = await verificar_citacoes(_FakeDB(), "Texto sem nenhuma citação jurídica formal.")
    assert r["total"] == 0
