"""Rate limit nos endpoints de casos da prioridade 1 (Fase 8, onda 2-A).

O inventário da Fase 8 classificou as rotas de `app/routers/cases.py` como
ONLY_AUTH + sensíveis; 18 delas estavam SEM rate limit (2 já cobertas:
kit-documental e teses-sugeridas). Todas passam a ter cota fixed-window de
60s por (rota, usuário-ou-IP).

Cobre a presença E o parâmetro de cada rate_limit (nome/limite), lendo o
fechamento de `rate_limit()` direto do objeto de rota real do app montado —
sem rede, sem banco. Mesma técnica de `test_users_rate_limit_gates.py`.

Critério dos limites:
- listas e detalhes que alimentam navegação normal (120/min);
- estatísticas e diagnóstico (60/min);
- criação/edição de estado de negócio (30/min);
- arquivar/desarquivar/reabrir, movimentos destrutivos, encerramento,
  extração IA e movimentos que disparam transições (10/min);
- operações destrutivas, integração externa DataJud e IA pesada
  (exclusão de caso 5/min, sincronização de processo 5/min,
  análise estratégica 6/min — alinhada à cota de `entrada-analisar`).
"""
from __future__ import annotations

from app.core.rate_limit import rate_limit as _rate_limit_factory

# (path, method) -> (nome esperado, limite máximo/minuto)
_ALVOS = {
    ("/api/cases/", "GET"): ("cases-listar", 120),
    ("/api/cases/stats", "GET"): ("cases-stats", 60),
    ("/api/cases/", "POST"): ("cases-criar", 30),
    ("/api/cases/{case_id}", "GET"): ("cases-detalhe", 120),
    ("/api/cases/{case_id}", "PATCH"): ("cases-atualizar", 30),
    ("/api/cases/{case_id}/arquivar", "POST"): ("cases-arquivar", 10),
    ("/api/cases/{case_id}/desarquivar", "POST"): ("cases-desarquivar", 10),
    ("/api/cases/{case_id}/reabrir", "POST"): ("cases-reabrir", 10),
    ("/api/cases/{case_id}", "DELETE"): ("cases-excluir", 5),
    ("/api/cases/{case_id}/gerar-documentos", "POST"): ("kit-documental", 5),
    ("/api/cases/{case_id}/movimentos", "GET"): ("cases-movimentos-lista", 120),
    ("/api/cases/{case_id}/movimentos", "POST"): ("cases-movimentos-cria", 30),
    ("/api/cases/{case_id}/movimentos/{movimento_id}", "PATCH"): ("cases-movimentos-edita", 30),
    ("/api/cases/{case_id}/movimentos/{movimento_id}", "DELETE"): ("cases-movimentos-exclui", 10),
    ("/api/cases/{case_id}/sincronizar-processo", "POST"): ("cases-sincroniza-processo", 5),
    ("/api/cases/{case_id}/encerrar/diagnostico", "GET"): ("cases-diagnostico-encerrar", 60),
    ("/api/cases/{case_id}/encerrar", "POST"): ("cases-encerrar", 10),
    ("/api/cases/{case_id}/aplicar-extracao", "POST"): ("cases-aplica-extracao", 10),
    ("/api/cases/{case_id}/teses-sugeridas", "GET"): ("teses-sugeridas", 15),
    ("/api/cases/{case_id}/analisar", "POST"): ("cases-analisar-ia", 6),
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
    devolve (nome, limite) lidos do próprio fechamento."""
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
    """Nome duplicado faria dois endpoints diferentes compartilhar a mesma
    cota — um esvazia o limite do outro."""
    nomes = [nome for nome, _ in _ALVOS.values()]
    assert len(nomes) == len(set(nomes)), nomes
