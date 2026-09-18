"""Rate limit nos endpoints de clientes da prioridade 1 (Fase 8, onda 2-B).

O inventário da Fase 8 classificou as rotas de `app/routers/clients.py` como
ONLY_AUTH + sensíveis; 11 delas estavam SEM rate limit (5 já cobertas por
ondas anteriores, agora travadas no teste). Todas passam a ter cota
fixed-window de 60s por (rota, usuário-ou-IP).

Cobre a presença E o parâmetro de cada rate_limit (nome/limite), lendo o
fechamento de `rate_limit()` direto do objeto de rota real do app montado —
sem rede, sem banco. Mesma técnica de `test_users_rate_limit_gates.py`.

Critério dos limites:
- listas e detalhes que alimentam navegação normal (120/min);
- bloqueios de esquecimento (consulta de estado, 60/min);
- criação/edição de estado de negócio e relatórios/exportações LGPD (30/min);
- `resolver` por CPF/CNPJ tem cota baixa anti-enumeração (10/min);
- credencial de portal (`criar-acesso`) cota baixa (10/min);
- operações destrutivas: exclusão de cliente e esquecimento LGPD (5/min).
"""
from __future__ import annotations

from app.core.rate_limit import rate_limit as _rate_limit_factory

# (path, method) -> (nome esperado, limite máximo/minuto)
_ALVOS = {
    ("/api/clients/resolver", "POST"): ("clients-resolver", 10),
    ("/api/clients/verificar-conflito", "POST"): ("verificar-conflito", 10),
    ("/api/clients/checar-conflito", "POST"): ("checar-conflito", 10),
    ("/api/clients/", "GET"): ("clients-listar", 120),
    ("/api/clients/", "POST"): ("clients-criar", 30),
    ("/api/clients/{client_id}", "GET"): ("clients-detalhe", 120),
    ("/api/clients/{client_id}", "PATCH"): ("clients-atualizar", 30),
    ("/api/clients/{client_id}", "DELETE"): ("clients-excluir", 5),
    ("/api/clients/{client_id}/gerar-documentos", "POST"): ("kit-documental", 5),
    ("/api/clients/{client_id}/pecas-geradas", "GET"): ("kit-documental-list", 30),
    ("/api/clients/{client_id}/ia-analise", "POST"): ("cliente-ia-analise", 5),
    ("/api/clients/{client_id}/criar-acesso", "POST"): ("clients-criar-acesso", 10),
    ("/api/clients/{client_id}/relatorio-lgpd", "GET"): ("clients-relatorio-lgpd", 30),
    ("/api/clients/{client_id}/dados-lgpd.json", "GET"): ("clients-dados-lgpd", 30),
    ("/api/clients/{client_id}/esquecimento/bloqueios", "GET"): ("clients-bloqueios-esquecimento", 60),
    ("/api/clients/{client_id}/esquecimento", "POST"): ("clients-esquecimento", 5),
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
