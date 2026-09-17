"""Rate limit nos routers finais da P1 (Fase 8, onda 2-F).

Encerra a onda 2 da Fase 8: `entrada_universal`, `portal` (superfície
EXTERNA do cliente — a mais exposta) e `financeiro_consolidado`.

Cobre a presença E o parâmetro de cada rate_limit (nome/limite), lendo o
fechamento de `rate_limit()` direto do objeto de rota real do app montado —
sem rede, sem banco. Mesma técnica de `test_users_rate_limit_gates.py`.

Critério dos limites:
- consulta de lote em polling (120/min) e catálogo de formatos (60/min);
- portal: leituras de navegação 60/min, polling de mensagens não lidas
  120/min, envio de mensagem 10/min (escrita em superfície externa);
- preparar pacote de documentos 10/min (pesada), vínculo de lote ao caso
  30/min, processar lote com IA 6/min (já coberta, travada aqui);
- financeiro: agregações 60/min, demonstrativo 30/min, fechamento
  inteligente 10/min.
"""
from __future__ import annotations

from app.core.rate_limit import rate_limit as _rate_limit_factory

# (path, method) -> (nome esperado, limite máximo/minuto)
_ALVOS = {
    ("/api/entrada-universal/meta", "GET"): ("entrada-universal-meta", 60),
    ("/api/entrada-universal/processar", "POST"): ("entrada-universal-processar", 6),
    ("/api/entrada-universal/{batch_id}", "GET"): ("entrada-universal-batch", 120),
    ("/api/entrada-universal/{batch_id}/preparar-pacote", "POST"): ("entrada-universal-pacote", 10),
    ("/api/entrada-universal/{batch_id}/vincular-caso", "POST"): ("entrada-universal-vincular", 30),
    ("/api/portal/meus-casos", "GET"): ("portal-meus-casos", 60),
    ("/api/portal/casos/{case_id}", "GET"): ("portal-caso-detalhe", 60),
    ("/api/portal/documentos", "GET"): ("portal-documentos", 60),
    ("/api/portal/financeiro", "GET"): ("portal-financeiro", 60),
    ("/api/portal/mensagens/nao-lidas", "GET"): ("portal-mensagens-nao-lidas", 120),
    ("/api/portal/casos/{case_id}/mensagens", "GET"): ("portal-mensagens-lista", 60),
    ("/api/portal/casos/{case_id}/mensagens", "POST"): ("portal-mensagens-envia", 10),
    ("/api/financeiro/consolidado", "GET"): ("fin-consolidado", 60),
    ("/api/financeiro/atencao", "GET"): ("fin-atencao", 60),
    ("/api/financeiro/demonstrativo", "GET"): ("fin-demonstrativo", 30),
    ("/api/financeiro/fechamento-inteligente", "GET"): ("fin-fechamento-inteligente", 10),
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
