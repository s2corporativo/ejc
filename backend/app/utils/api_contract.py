"""
api_contract.py — verificador de contrato HTTP frontend↔backend.

Motivação (auditoria Graphify 2026-07-04): 9 bugs de 404 em produção nasceram
de paths hardcoded no frontend que divergiam das rotas reais do FastAPI
(docstrings anunciavam `/api/v1/...`, mas os prefixes não tinham `/v1`). Este
módulo é a versão executável e reutilizável daquela verificação: extrai as
rotas REAIS do app montado (já com o prefixo `/api`) e todas as chamadas HTTP
estáticas do frontend, e reporta as que não casam.

Uso: `check_frontend_contract()` retorna (unmatched, stats). O teste
`tests/test_api_contract.py` falha se `unmatched` não estiver vazio, travando
o drift no CI antes do merge.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# baseURL do axios no frontend (frontend/src/lib/api.ts) — toda chamada `api.*`
# é resolvida como este prefixo + o path informado.
AXIOS_BASE_URL = "/api"

# Chamadas cujo path NÃO é estaticamente resolvível (segmento inteiro vindo de
# variável) ou que batem em serviço externo — não são drift de contrato.
# Mantido curto e explícito; cada entrada é uma justificativa auditável.
ALLOWLIST_SUBSTR: tuple[str, ...] = (
    "${API",        # base configurável por env
    "http://",      # URL absoluta externa
    "https://",     # URL absoluta externa
)


@dataclass
class CallSite:
    file: str
    line: int
    method: str
    raw_path: str
    final_url: str


@dataclass
class ContractStats:
    routes: int = 0
    calls: int = 0
    matched: int = 0
    skipped: int = 0
    files: int = 0
    unmatched_list: list[CallSite] = field(default_factory=list)


def _iter_frontend_files(front_src: str):
    for root, dirs, files in os.walk(front_src):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "dist", ".vite")]
        for f in files:
            if f.endswith((".ts", ".tsx")) and not f.endswith(".d.ts"):
                yield os.path.join(root, f)


# api.get(...), apiClient.post<T>(...), axios.delete(...), http.put(...)
# Grupo 1 = cliente: `api`/`apiClient` têm baseURL "/api"; `axios`/`http` crus
# trazem o path já absoluto (não recebem o prefixo).
_CALL_RE = re.compile(
    r"\b(api|apiClient|axios|http)\s*\.\s*(get|post|put|patch|delete)\s*"
    r"(?:<[^>]*>)?\(\s*([`'\"])(.*?)\3",
    re.S,
)
_BASEURL_CLIENTS = {"api", "apiClient"}
# fetch("/api/...", { method: "POST", ... }) — captura o path e uma janela das
# opções logo após, para inferir o método (default GET quando ausente).
_FETCH_RE = re.compile(
    r"\bfetch\s*\(\s*([`'\"])(/api/[^`'\"]*?)\1\s*(?:,\s*\{(.{0,200}?)\})?",
    re.S,
)
_FETCH_METHOD_RE = re.compile(r"method\s*:\s*[`'\"](\w+)", re.S)


def _final_url(prefix_is_axios: bool, raw: str) -> str | None:
    """Resolve a URL final que o navegador chamaria. Retorna None se o path
    não começar de forma resolvível (variável no início)."""
    # normaliza interpolações `${...}` para um placeholder de 1 segmento
    norm = re.sub(r"\$\{[^}]*\}", "\x00", raw)
    norm = norm.split("?")[0].split("#")[0]
    if prefix_is_axios:
        if not norm.startswith("/"):
            return None  # path relativo/dinâmico não resolvível
        norm = AXIOS_BASE_URL + norm
    else:
        if not norm.startswith("/"):
            return None
    norm = norm.rstrip("/") or "/"
    return norm


def _collect_calls(front_src: str) -> tuple[list[CallSite], int, int]:
    calls: list[CallSite] = []
    skipped = 0
    nfiles = 0
    for path in _iter_frontend_files(front_src):
        nfiles += 1
        src = open(path, encoding="utf-8", errors="replace").read()
        rel = os.path.relpath(path, front_src)
        for m in _CALL_RE.finditer(src):
            client, method, raw = m.group(1), m.group(2).upper(), m.group(4)
            if any(s in raw for s in ALLOWLIST_SUBSTR):
                skipped += 1
                continue
            final = _final_url(client in _BASEURL_CLIENTS, raw)
            if final is None:
                skipped += 1
                continue
            line = src[: m.start()].count("\n") + 1
            calls.append(CallSite(rel, line, method, raw, final))
        for m in _FETCH_RE.finditer(src):
            raw = m.group(2)
            if any(s in raw for s in ALLOWLIST_SUBSTR):
                skipped += 1
                continue
            opts = m.group(3) or ""
            mm = _FETCH_METHOD_RE.search(opts)
            method = mm.group(1).upper() if mm else "GET"
            final = _final_url(False, raw)
            if final is None:
                skipped += 1
                continue
            line = src[: m.start()].count("\n") + 1
            calls.append(CallSite(rel, line, method, raw, final))
    return calls, skipped, nfiles


def _route_samples():
    """Amostra concreta de cada rota REAL do app montado: (method, sample_path),
    com {param} substituído por um valor fixo. A chamada do frontend é comparada
    como regex contra estas amostras, de modo que um segmento dinâmico da chamada
    (`${action}`) casa um literal da rota (/approve) — dispatch dinâmico válido."""
    from app.main import app  # import tardio: evita custo quando não usado

    samples: list[tuple[str, str]] = []
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", None)
        if not path or not methods:
            continue
        sample = re.sub(r"\{[^}]+\}", "\x01", path).rstrip("/") or "/"
        for meth in methods:
            samples.append((meth.upper(), sample))
    return samples


def check_frontend_contract(front_src: str | None = None) -> tuple[list[CallSite], ContractStats]:
    """Retorna (chamadas_sem_rota, stats). Lista vazia = contrato íntegro."""
    if front_src is None:
        here = os.path.dirname(os.path.abspath(__file__))
        front_src = os.path.abspath(os.path.join(here, "..", "..", "..", "frontend", "src"))

    stats = ContractStats()
    if not os.path.isdir(front_src):
        return [], stats  # sem frontend no checkout → nada a verificar

    samples = _route_samples()
    stats.routes = len(samples)
    calls, skipped, nfiles = _collect_calls(front_src)
    stats.calls = len(calls)
    stats.skipped = skipped
    stats.files = nfiles

    for c in calls:
        # A chamada (com \x00 = segmento dinâmico) vira regex; casa contra a
        # amostra concreta da rota (\x01 = valor de path param). Segmento
        # dinâmico da chamada [^/]+ casa tanto o \x01 quanto um literal de rota.
        call_rx = re.compile(
            "^" + "[^/]+".join(re.escape(p) for p in c.final_url.split("\x00")) + "/?$"
        )
        matched = any(
            meth == c.method and call_rx.match(sample)
            for meth, sample in samples
        )
        if matched:
            stats.matched += 1
        else:
            stats.unmatched_list.append(c)
    return stats.unmatched_list, stats
