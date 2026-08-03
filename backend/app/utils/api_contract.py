"""
api_contract.py — verificador de contrato HTTP frontend↔backend.

Motivação (auditoria Graphify 2026-07-04): bugs de 404 em produção nasceram
de paths hardcoded no frontend que divergiam das rotas reais do FastAPI.
Este módulo extrai as rotas REAIS do app montado e todas as chamadas HTTP
estáticas do frontend, reportando as que não casam.

Desde a Onda 1, o contrato público canônico é /api/v1, enquanto os routers
continuam montados internamente em /api e o middleware de compatibilidade faz
a reescrita. O verificador modela essa equivalência explicitamente; assim ele
não gera falso positivo e também não mascara uma rota realmente inexistente.

Uso: `check_frontend_contract()` retorna (unmatched, stats). O teste
`tests/test_api_contract.py` falha se `unmatched` não estiver vazio.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# baseURL real do cliente axios em frontend/src/lib/api.ts.
AXIOS_BASE_URL = "/api/v1"

# Chamadas cujo path NÃO é estaticamente resolvível (segmento inteiro vindo de
# variável) ou que batem em serviço externo — não são drift de contrato.
ALLOWLIST_SUBSTR: tuple[str, ...] = (
    "${API",
    "http://",
    "https://",
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
        dirs[:] = [
            d
            for d in dirs
            if d not in ("node_modules", "dist", ".vite", "__tests__", "__mocks__")
        ]
        for f in files:
            if not f.endswith((".ts", ".tsx")) or f.endswith(".d.ts"):
                continue
            if f.endswith((".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")):
                continue
            yield os.path.join(root, f)


# api.get(...), apiClient.post<T>(...), axios.delete(...), http.put(...)
_CALL_RE = re.compile(
    r"\b(api|apiClient|axios|http)\s*\.\s*(get|post|put|patch|delete)\s*"
    r"(?:<[^>]*>)?\(\s*([`'\"])(.*?)\3",
    re.S,
)
_BASEURL_CLIENTS = {"api", "apiClient"}
_FETCH_RE = re.compile(
    r"\bfetch\s*\(\s*([`'\"])(/api/[^`'\"]*?)\1\s*(?:,\s*\{(.{0,200}?)\})?",
    re.S,
)
_FETCH_METHOD_RE = re.compile(r"method\s*:\s*[`'\"](\w+)", re.S)


def _final_url(prefix_is_axios: bool, raw: str) -> str | None:
    """Resolve a URL final que o navegador chamaria."""
    norm = re.sub(r"\$\{[^}]*\}", "\x00", raw)
    norm = norm.split("?")[0].split("#")[0]
    if prefix_is_axios:
        if not norm.startswith("/"):
            return None
        norm = AXIOS_BASE_URL + norm
    elif not norm.startswith("/"):
        return None
    return norm.rstrip("/") or "/"


def _internal_api_url(path: str) -> str:
    """Converte o contrato público /api/v1 para o path interno dos routers.

    A função espelha APIVersionCompatibilityMiddleware sem liberar aliases
    arbitrários: somente o prefixo exato /api/v1 é convertido para /api.
    """
    if path == "/api/v1":
        return "/api"
    if path.startswith("/api/v1/"):
        return "/api" + path[len("/api/v1") :]
    return path


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
    """Amostra concreta de cada rota REAL do app montado."""
    from app.main import app

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
        front_src = os.path.abspath(
            os.path.join(here, "..", "..", "..", "frontend", "src")
        )

    stats = ContractStats()
    if not os.path.isdir(front_src):
        return [], stats

    samples = _route_samples()
    stats.routes = len(samples)
    calls, skipped, nfiles = _collect_calls(front_src)
    stats.calls = len(calls)
    stats.skipped = skipped
    stats.files = nfiles

    for c in calls:
        # Rotas FastAPI estão montadas em /api; chamadas do cliente canônico
        # chegam em /api/v1 e são reescritas pelo middleware antes do dispatch.
        comparable_url = _internal_api_url(c.final_url)
        call_rx = re.compile(
            "^"
            + "[^/]+".join(
                re.escape(p) for p in comparable_url.split("\x00")
            )
            + "/?$"
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
