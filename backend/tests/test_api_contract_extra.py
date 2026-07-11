"""Contrato frontend↔backend — cobertura EXTRA além de test_api_contract.py.

O extrator principal (app/utils/api_contract.py) enxerga `api.get("...")`,
`axios.post("...")` e `fetch("/api/...")`. A auditoria 2026-07-11 encontrou
três padrões REAIS de chamada que ficavam fora do radar:

1. `authFetch("/api/...", { method: ... })` — wrapper de fetch para SSE/stream
   (lib/stream.ts), usado em BancarioForense, AnaliseExtratos e
   PecaGeneratorModal. Um path errado ali seria 404 silencioso em produção.
2. Literais `endpoint: "/..."` / `endpoint={\`/...\`}` — paths declarados em
   CONFIG (pages/ramos/ramosConfig.ts, ~60 ferramentas) ou passados como prop
   (CasoDetalhe) e consumidos depois via `api.get(cfg.endpoint)` — o extrator
   principal pula a chamada por ser variável.
3. `new EventSource("...")` — nenhum uso hoje; o scan fica como guarda.

Este teste varre esses padrões e valida cada path contra as rotas REAIS do
app montado, reutilizando os helpers do módulo de contrato (sem duplicar a
lógica de resolução)."""
from __future__ import annotations

import re

import pytest

from app.utils.api_contract import (
    ALLOWLIST_SUBSTR,
    _collect_calls,  # noqa: F401  (documenta a relação; não usado direto)
    _final_url,
    _iter_frontend_files,
    _route_samples,
)


def _front_src() -> str:
    import os

    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", "frontend", "src"))


# authFetch("/api/x", { method: "POST" }) — path absoluto (não recebe baseURL).
_AUTHFETCH_RE = re.compile(
    r"\bauthFetch\(\s*([`'\"])(/api/[^`'\"]*?)\1\s*(?:,\s*\{(.{0,200}?)\})?",
    re.S,
)
_METHOD_RE = re.compile(r"method\s*:\s*[`'\"](\w+)", re.S)

# endpoint: "/x"  |  endpoint={`/x/${id}`}  — consumidos via api.<verbo>(cfg.endpoint),
# logo recebem o baseURL /api do axios. Aceita ", ' e ` nas duas formas.
_ENDPOINT_RE = re.compile(
    r"\bendpoint\s*[:=]\s*\{?\s*([`'\"])(/.*?)\1",
)

# new EventSource("/api/x") — guarda para uso futuro de SSE nativo.
_EVENTSOURCE_RE = re.compile(
    r"\bnew\s+EventSource\(\s*([`'\"])(/[^`'\"]*?)\1",
)


def _coletar_extras(front_src: str):
    """[(file, line, method|None, raw, final_url)] dos padrões extras."""
    achados = []
    import os

    for path in _iter_frontend_files(front_src):
        src = open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, front_src)

        def _linha(pos: int) -> int:
            return src[:pos].count("\n") + 1

        for m in _AUTHFETCH_RE.finditer(src):
            raw = m.group(2)
            if any(s in raw for s in ALLOWLIST_SUBSTR):
                continue
            mm = _METHOD_RE.search(m.group(3) or "")
            method = mm.group(1).upper() if mm else "GET"
            final = _final_url(False, raw)
            if final:
                achados.append((rel, _linha(m.start()), method, raw, final))

        for m in _ENDPOINT_RE.finditer(src):
            raw = m.group(2)
            if any(s in raw for s in ALLOWLIST_SUBSTR):
                continue
            final = _final_url(True, raw)  # consumido por api.* → baseURL /api
            if final:
                # método desconhecido no ponto de declaração (o consumidor
                # decide GET/POST) → casa contra qualquer método da rota.
                achados.append((rel, _linha(m.start()), None, raw, final))

        for m in _EVENTSOURCE_RE.finditer(src):
            raw = m.group(2)
            if any(s in raw for s in ALLOWLIST_SUBSTR):
                continue
            final = _final_url(False, raw)
            if final:
                achados.append((rel, _linha(m.start()), "GET", raw, final))
    return achados


def _casa_rota(final_url: str, method: str | None, samples) -> bool:
    """Mesma semântica do check principal: \x00 (segmento dinâmico da chamada)
    vira [^/]+ e casa contra a amostra concreta da rota."""
    rx = re.compile(
        "^" + "[^/]+".join(re.escape(p) for p in final_url.split("\x00")) + "/?$"
    )
    return any(
        (method is None or meth == method) and rx.match(sample)
        for meth, sample in samples
    )


def test_padroes_extras_de_chamada_batem_com_rotas_reais():
    front_src = _front_src()
    import os

    if not os.path.isdir(front_src):
        pytest.skip("frontend/src ausente neste checkout — nada a verificar")

    achados = _coletar_extras(front_src)
    # Sanidade: authFetch (3 call sites) + endpoints do ramosConfig (~60).
    assert len(achados) > 40, (
        f"poucos padrões extras extraídos ({len(achados)}) — regex quebrou?"
    )

    samples = _route_samples()
    mortos = [
        (f, ln, meth or "ANY", raw)
        for f, ln, meth, raw, final in achados
        if not _casa_rota(final, meth, samples)
    ]
    if mortos:
        linhas = "\n".join(
            f"  {meth:6} {raw}  <- {f}:{ln}" for f, ln, meth, raw in mortos
        )
        pytest.fail(
            f"{len(mortos)} chamada(s) de padrão extra sem rota no backend "
            f"(404 em produção):\n{linhas}"
        )


def test_extrator_extra_reconhece_authfetch_com_metodo():
    src = (
        'const r = await authFetch(`/api/bank-analysis/${id}/gerar-peca`, {\n'
        '  method: "POST",\n'
        "});\n"
    )
    m = _AUTHFETCH_RE.search(src)
    assert m is not None
    assert m.group(2) == "/api/bank-analysis/${id}/gerar-peca"
    assert _METHOD_RE.search(m.group(3)).group(1).upper() == "POST"


def test_extrator_extra_reconhece_endpoint_prop_e_config():
    prop = 'endpoint={`/documents/?case_id=${id}`}'
    cfg = 'endpoint: "/civel/ferramentas/calculo-dano-moral",'
    assert _ENDPOINT_RE.search(prop).group(2) == "/documents/?case_id=${id}"
    assert _ENDPOINT_RE.search(cfg).group(2) == "/civel/ferramentas/calculo-dano-moral"
