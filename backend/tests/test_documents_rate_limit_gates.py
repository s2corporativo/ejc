"""Rate limit nos endpoints de documentos da prioridade 1 (Fase 8, onda 2-D).

O inventário da Fase 8 classificou as rotas de `app/routers/documents.py`
como ONLY_AUTH + sensíveis; 13 delas estavam SEM rate limit (`classificar`
já coberta, agora travada no teste). Todas passam a ter cota fixed-window
de 60s por (rota, usuário-ou-IP).

Cobre a presença E o parâmetro de cada rate_limit (nome/limite), lendo o
fechamento de `rate_limit()` direto do objeto de rota real do app montado —
sem rede, sem banco. Mesma técnica de `test_users_rate_limit_gates.py`.

Critério dos limites:
- catálogo de tipos, listas, detalhes (120/min);
- downloads binários locais e via Drive (60/min);
- upload/atualização de metadados (30/min);
- sugestão de tipo por IA, publicação no portal, uploads/links assinados
  do Drive e exclusões Drive (10/min);
- exclusão de documento no GED (5/min).
"""
from __future__ import annotations

from app.core.rate_limit import rate_limit as _rate_limit_factory

# (path, method) -> (nome esperado, limite máximo/minuto)
_ALVOS = {
    ("/api/documents/tipos", "GET"): ("doc-tipos", 120),
    ("/api/documents/sugerir-tipo", "POST"): ("doc-sugere-tipo", 10),
    ("/api/documents/upload", "POST"): ("doc-upload", 30),
    ("/api/documents/", "GET"): ("doc-listar", 120),
    ("/api/documents/{doc_id}", "GET"): ("doc-detalhe", 120),
    ("/api/documents/{doc_id}/download", "GET"): ("doc-download", 60),
    ("/api/documents/{doc_id}", "DELETE"): ("doc-excluir", 5),
    ("/api/documents/{doc_id}", "PATCH"): ("doc-atualizar", 30),
    ("/api/documents/{doc_id}/publicacao-portal", "PATCH"): ("doc-publica-portal", 10),
    ("/api/documents/{doc_id}/classificar", "POST"): ("doc-classificar", 15),
    ("/api/documents/drive/upload", "POST"): ("doc-drive-upload", 10),
    ("/api/documents/drive/{file_id}/link", "GET"): ("doc-drive-link", 10),
    ("/api/documents/drive/{file_id}/download", "GET"): ("doc-drive-download", 60),
    ("/api/documents/drive/{file_id}", "DELETE"): ("doc-drive-excluir", 10),
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
