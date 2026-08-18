"""Rate limit nos endpoints de IA que chamam provedor externo (auditoria de
segurança 18/08).

11 endpoints de app/routers/ai.py + o /analisar de ia_defensiva.py chamavam
provedor de IA (custo real por chamada) sem `@rate_limit` — o único endpoint
determinístico da vizinhança (`/citacoes/verificar`, sem LLM) tinha. Cobre a
presença E o parâmetro de cada rate_limit (nome/limite), lendo o fechamento
de `rate_limit()` direto do objeto de rota real do app montado — sem rede,
sem banco.
"""
from __future__ import annotations

from app.core.rate_limit import rate_limit as _rate_limit_factory

# (path, method) -> (nome esperado, limite máximo/minuto)
_ALVOS = {
    ("/api/ai/analisar-caso", "POST"): ("ia-analisar-caso", 15),
    ("/api/ai/resumir-documento", "POST"): ("ia-resumir-documento", 15),
    ("/api/ai/teses-ocultas", "POST"): ("ia-teses-ocultas", 15),
    ("/api/ai/auditar-peca", "POST"): ("ia-auditar-peca", 10),
    ("/api/ai/preparar-audiencia", "POST"): ("ia-preparar-audiencia", 15),
    ("/api/ai/casos/{case_id}/assistente", "POST"): ("ia-assistente-estrategico", 15),
    ("/api/ai/casos/{case_id}/dual", "POST"): ("ia-dual", 10),
    ("/api/ai/caso/{case_id}/visual-law", "POST"): ("ia-visual-law", 10),
    ("/api/ai/caso/{case_id}/estrategia", "POST"): ("ia-motor-estrategia", 10),
    ("/api/ai/analisar-contrato", "POST"): ("ia-analisar-contrato", 15),
    ("/api/ai/detectar-prazos", "POST"): ("ia-detectar-prazos", 15),
    ("/api/ia-defensiva/analisar", "POST"): ("ia-defensiva-analisar", 15),
}


def _rotas_do_app() -> dict[tuple[str, str], object]:
    from app.main import app

    saida = {}
    for r in app.routes:
        path = getattr(r, "path", None)
        metodos = getattr(r, "methods", None) or set()
        if path is None:
            continue
        for m in metodos:
            saida[(path, m)] = r
    return saida


def _fechamento_do_rate_limit(rota):
    """Acha, entre `rota.dependencies`, a closure `_dep` de rate_limit() e
    devolve (nome, limite) lidos do próprio fechamento — não confia em
    inferência por nome de variável, lê o valor real capturado."""
    referencia = _rate_limit_factory("sonda", 1)  # mesmo formato de closure
    for dep in getattr(rota, "dependencies", []) or []:
        fn = getattr(dep, "dependency", None)
        if fn is None or fn.__code__ is not referencia.__code__:
            continue
        limite, nome = (c.cell_contents for c in fn.__closure__)
        return nome, limite
    return None


def test_todos_os_alvos_tem_rate_limit_com_o_limite_esperado():
    rotas = _rotas_do_app()
    faltando = []
    divergentes = []
    for chave, (nome_esperado, limite_esperado) in _ALVOS.items():
        rota = rotas.get(chave)
        assert rota is not None, f"rota sumiu do app: {chave}"
        achado = _fechamento_do_rate_limit(rota)
        if achado is None:
            faltando.append(chave)
            continue
        nome, limite = achado
        if (nome, limite) != (nome_esperado, limite_esperado):
            divergentes.append((chave, achado, (nome_esperado, limite_esperado)))
    assert not faltando, f"sem rate_limit: {faltando}"
    assert not divergentes, f"rate_limit com parâmetros diferentes do esperado: {divergentes}"


def test_nomes_de_rate_limit_sao_unicos():
    """Nome duplicado faria dois endpoints diferentes compartilharem a mesma
    cota — um esvazia o limite do outro."""
    nomes = [nome for nome, _ in _ALVOS.values()]
    assert len(nomes) == len(set(nomes)), nomes


def test_endpoint_deterministico_sem_llm_nao_precisa_de_rate_limit_de_ia():
    """/citacoes/verificar não chama provedor — não faz parte deste conjunto,
    mas TEM o seu próprio rate_limit (achado do relatório: era irônico que o
    único sem LLM tivesse limite e os 12 com LLM não)."""
    rotas = _rotas_do_app()
    rota = rotas[("/api/ai/citacoes/verificar", "POST")]
    achado = _fechamento_do_rate_limit(rota)
    assert achado is not None
    assert achado[0] == "verificar-citacoes"
