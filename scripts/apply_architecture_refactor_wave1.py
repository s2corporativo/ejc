#!/usr/bin/env python3
"""Aplica a primeira onda da reorganização arquitetural do EJC.

A operação é determinística, idempotente e conservadora:
- cria contratos canônicos de domínio e rotas;
- disponibiliza /api/v1 sem remover /api;
- migra o cliente HTTP do frontend para /api/v1 com normalização legada;
- consolida rotas históricas em workspaces canônicos;
- renomeia a rota pública de Ramos para Áreas de Atuação com aliases;
- expõe um manifesto auditável das rotas FastAPI.

O script falha se os marcadores esperados divergirem, evitando alterações cegas.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write_new(relative: str, content: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != content:
            raise RuntimeError(f"Arquivo já existe com conteúdo divergente: {relative}")
        return
    path.write_text(content, encoding="utf-8")


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"Esperava 1 ocorrência em {relative}, encontrei {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_route_for_key(text: str, key: str, old_path: str, new_path: str) -> str:
    pattern = re.compile(
        rf'(key:\s*"{re.escape(key)}"[\s\S]{{0,500}}?path:\s*)"{re.escape(old_path)}"'
    )
    if f'key: "{key}"' in text and f'path: "{new_path}"' in text:
        return text
    updated, count = pattern.subn(rf'\1"{new_path}"', text, count=1)
    if count != 1:
        raise RuntimeError(f"Rota {old_path} da chave {key} não encontrada de forma única")
    return updated


def update_module_registry() -> None:
    relative = "frontend/src/config/moduleRegistry.tsx"
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")

    import_line = 'import { LEGACY_CANONICAL_REDIRECTS } from "./canonicalRoutes";\n'
    marker = '} from "lucide-react";\n'
    if import_line not in text:
        if text.count(marker) != 1:
            raise RuntimeError("Import de lucide-react não encontrado de forma única")
        text = text.replace(marker, marker + import_line, 1)

    replacements = {
        "ramos": ("/ramos", "/areas-de-atuacao"),
        "ramo-detalhe": ("/ramos/:slug", "/areas-de-atuacao/:slug"),
        "prazos": ("/prazos", "/legado/prazos"),
        "tarefas": ("/tarefas", "/legado/tarefas"),
        "intimacoes": ("/intimacoes", "/legado/intimacoes"),
        "suspensoes": ("/suspensoes", "/legado/suspensoes"),
        "knowledge-hub": ("/knowledge-hub", "/legado/knowledge-hub"),
    }
    for key, (old_path, new_path) in replacements.items():
        text = replace_route_for_key(text, key, old_path, new_path)

    redirects_marker = "export const LEGACY_REDIRECTS: LegacyRedirect[] = [\n"
    redirects_new = redirects_marker + "  ...LEGACY_CANONICAL_REDIRECTS,\n"
    if redirects_new not in text:
        if text.count(redirects_marker) != 1:
            raise RuntimeError("LEGACY_REDIRECTS não encontrado de forma única")
        text = text.replace(redirects_marker, redirects_new, 1)

    text = text.replace('to: "/knowledge-hub",', 'to: "/inteligencia?tab=conhecimento",')
    text = text.replace('to: "/ramos/ambiental",', 'to: "/areas-de-atuacao/ambiental",')
    text = text.replace(
        'reason: "O núcleo ambiental foi incorporado aos Ramos do Direito.",',
        'reason: "O núcleo ambiental foi incorporado às Áreas de Atuação.",',
    )
    path.write_text(text, encoding="utf-8")


def update_app_routes() -> None:
    relative = "frontend/src/App.tsx"
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")

    function_marker = "function RouteFallback() {\n"
    redirect_function = '''function AreaAtuacaoLegacyRedirect() {
  const { slug } = useParams();
  return <Navigate to={`/areas-de-atuacao/${slug}`} replace />;
}

'''
    if "function AreaAtuacaoLegacyRedirect()" not in text:
        if text.count(function_marker) != 1:
            raise RuntimeError("RouteFallback não encontrado de forma única")
        text = text.replace(function_marker, redirect_function + function_marker, 1)

    route_marker = '''              <Route
                path="/clientes/:clientId/dossie"
                element={<ClienteDossieRedirect />}
              />
'''
    route_new = route_marker + '''              <Route
                path="/ramos/:slug"
                element={<AreaAtuacaoLegacyRedirect />}
              />
'''
    if 'path="/ramos/:slug"' not in text:
        if text.count(route_marker) != 1:
            raise RuntimeError("Rota dinâmica de dossiê não encontrada de forma única")
        text = text.replace(route_marker, route_new, 1)
    path.write_text(text, encoding="utf-8")


def update_api_client() -> None:
    relative = "frontend/src/lib/api.ts"
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")

    old_create = 'const api = axios.create({ baseURL: "/api", withCredentials: true });'
    new_create = '''export const API_BASE_URL = "/api/v1";
const api = axios.create({ baseURL: API_BASE_URL, withCredentials: true });'''
    if new_create not in text:
        if text.count(old_create) != 1:
            raise RuntimeError("Criação do cliente Axios não encontrada de forma única")
        text = text.replace(old_create, new_create, 1)

    old_interceptor = '''api.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});'''
    new_interceptor = '''api.interceptors.request.use((config) => {
  // Compatibilidade transitória: chamadas antigas que ainda informam /api ou
  // /v1 não podem duplicar o prefixo agora que o cliente usa /api/v1.
  const url = String(config.url || "");
  if (url.startsWith("/api/v1/")) config.url = url.slice("/api/v1".length);
  else if (url.startsWith("/api/")) config.url = url.slice("/api".length);
  else if (url.startsWith("/v1/")) config.url = url.slice("/v1".length);

  const token = getAccessToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});'''
    if new_interceptor not in text:
        if text.count(old_interceptor) != 1:
            raise RuntimeError("Interceptor Axios não encontrado de forma única")
        text = text.replace(old_interceptor, new_interceptor, 1)

    text = text.replace('axios\n    .post<AuthTokens>("/api/auth/refresh"', 'axios\n    .post<AuthTokens>("/api/v1/auth/refresh"')
    path.write_text(text, encoding="utf-8")


def update_main() -> None:
    replace_once(
        "backend/app/main.py",
        "from app.core.auth_middleware import AuthMiddleware\n",
        "from app.core.auth_middleware import AuthMiddleware\nfrom app.core.api_version_middleware import APIVersionCompatibilityMiddleware\n",
    )
    replace_once(
        "backend/app/main.py",
        "from app.routers import workflow\n",
        "from app.routers import workflow\nfrom app.routers import architecture\n",
    )
    replace_once(
        "backend/app/main.py",
        "app.add_middleware(AuthMiddleware)          # ← P0-1 CORRIGIDO: registrado!\n",
        "app.add_middleware(AuthMiddleware)          # ← P0-1 CORRIGIDO: registrado!\napp.add_middleware(APIVersionCompatibilityMiddleware)\n",
    )
    replace_once(
        "backend/app/main.py",
        "app.include_router(workflow.router, prefix=API)\n",
        "app.include_router(workflow.router, prefix=API)\napp.include_router(architecture.router, prefix=API)\n",
    )


def create_files() -> None:
    write_new(
        "backend/app/core/api_version_middleware.py",
        '''"""Compatibilidade entre a API histórica /api e o contrato canônico /api/v1."""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_EXEMPT_PREFIXES = ("/api/health", "/api/docs", "/api/openapi.json")


class APIVersionCompatibilityMiddleware:
    """Expõe /api/v1 reusando as rotas atuais e sinaliza o prefixo legado.

    A migração é reversível: nenhum router é duplicado e /api continua ativo.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        original_path = str(scope.get("path") or "")
        canonical_request = original_path == "/api/v1" or original_path.startswith("/api/v1/")
        legacy_request = (
            original_path.startswith("/api/")
            and not canonical_request
            and not original_path.startswith(_EXEMPT_PREFIXES)
        )

        if canonical_request:
            rewritten = dict(scope)
            suffix = original_path[len("/api/v1") :] or ""
            rewritten["path"] = f"/api{suffix}"
            raw_path = rewritten["path"].encode("utf-8")
            rewritten["raw_path"] = raw_path
            scope = rewritten

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                if canonical_request:
                    headers.append((b"content-location", original_path.encode("utf-8")))
                    headers.append((b"x-ejc-api-version", b"1"))
                elif legacy_request:
                    successor = f"/api/v1{original_path[len('/api'):]}"
                    headers.extend(
                        [
                            (b"deprecation", b"true"),
                            (b"link", f'<{successor}>; rel="successor-version"'.encode("utf-8")),
                            (b"x-ejc-api-version", b"legacy"),
                        ]
                    )
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
''',
    )
    write_new(
        "backend/app/core/domain_contracts.py",
        '''"""Vocabulário canônico do domínio EJC, sem alterar enums físicos do banco."""
from __future__ import annotations

from enum import StrEnum


class CaseLifecycleStatus(StrEnum):
    TRIAGEM = "triagem"
    EM_ANALISE = "em_analise"
    AGUARDANDO_DOCUMENTOS = "aguardando_documentos"
    PROPOSTA_APRESENTADA = "proposta_apresentada"
    CONTRATACAO_PENDENTE = "contratacao_pendente"
    CONTRATADO = "contratado"
    EM_ANDAMENTO = "em_andamento"
    SUSPENSO = "suspenso"
    ENCERRADO = "encerrado"
    ARQUIVADO = "arquivado"
    NAO_CONTRATADO = "nao_contratado"


class TaskLifecycleStatus(StrEnum):
    PENDENTE = "pendente"
    EM_EXECUCAO = "em_execucao"
    AGUARDANDO_TERCEIRO = "aguardando_terceiro"
    CONCLUIDA = "concluida"
    CANCELADA = "cancelada"
    VENCIDA = "vencida"


class DocumentLifecycleStatus(StrEnum):
    RASCUNHO = "rascunho"
    EM_ELABORACAO = "em_elaboracao"
    EM_REVISAO = "em_revisao"
    APROVADO = "aprovado"
    ASSINADO = "assinado"
    PROTOCOLADO = "protocolado"
    SUBSTITUIDO = "substituido"
    ARQUIVADO = "arquivado"


class FinancialLifecycleStatus(StrEnum):
    PREVISTO = "previsto"
    FATURADO = "faturado"
    PARCIALMENTE_RECEBIDO = "parcialmente_recebido"
    RECEBIDO = "recebido"
    VENCIDO = "vencido"
    RENEGOCIADO = "renegociado"
    CANCELADO = "cancelado"


LEGACY_CASE_STATUS_TO_CANONICAL: dict[str, CaseLifecycleStatus] = {
    "triagem": CaseLifecycleStatus.TRIAGEM,
    "ativo": CaseLifecycleStatus.EM_ANDAMENTO,
    "suspenso": CaseLifecycleStatus.SUSPENSO,
    "acordo": CaseLifecycleStatus.ENCERRADO,
    "encerrado": CaseLifecycleStatus.ENCERRADO,
    "arquivado": CaseLifecycleStatus.ARQUIVADO,
}


def canonical_case_status(value: str) -> CaseLifecycleStatus:
    """Normaliza status novo ou legado sem modificar a persistência existente."""
    try:
        return CaseLifecycleStatus(value)
    except ValueError:
        if value in LEGACY_CASE_STATUS_TO_CANONICAL:
            return LEGACY_CASE_STATUS_TO_CANONICAL[value]
        raise ValueError(f"Status de caso desconhecido: {value}") from None
''',
    )
    write_new(
        "backend/app/core/route_registry.py",
        '''"""Manifesto auditável das rotas montadas no FastAPI."""
from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import FastAPI
from fastapi.routing import APIRoute


def build_route_manifest(app: FastAPI) -> dict[str, Any]:
    routes: list[dict[str, Any]] = []
    identities: list[str] = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        methods = sorted(m for m in (route.methods or set()) if m not in {"HEAD", "OPTIONS"})
        for method in methods:
            identity = f"{method} {route.path}"
            identities.append(identity)
            routes.append(
                {
                    "method": method,
                    "path": route.path,
                    "name": route.name,
                    "tags": list(route.tags or []),
                    "deprecated": bool(route.deprecated),
                }
            )
    duplicates = sorted(key for key, count in Counter(identities).items() if count > 1)
    return {
        "total": len(routes),
        "duplicates": duplicates,
        "routes": sorted(routes, key=lambda item: (item["path"], item["method"])),
    }
''',
    )
    write_new(
        "backend/app/routers/architecture.py",
        '''"""Governança arquitetural e manifesto de rotas do EJC."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.core.route_registry import build_route_manifest
from app.core.security import require_roles

router = APIRouter(prefix="/architecture", tags=["Arquitetura"])
_GESTORES = ["superadmin", "admin", "socio"]


@router.get("/routes")
async def route_manifest(request: Request, _=Depends(require_roles(_GESTORES))):
    """Lista endpoints efetivamente montados e colisões exatas de método+caminho."""
    return build_route_manifest(request.app)


@router.get("/contracts")
async def domain_contracts(_=Depends(require_roles(_GESTORES))):
    """Expõe o vocabulário canônico sem revelar dados de negócio."""
    from app.core.domain_contracts import (
        CaseLifecycleStatus,
        DocumentLifecycleStatus,
        FinancialLifecycleStatus,
        TaskLifecycleStatus,
    )

    return {
        "case_status": [item.value for item in CaseLifecycleStatus],
        "task_status": [item.value for item in TaskLifecycleStatus],
        "document_status": [item.value for item in DocumentLifecycleStatus],
        "financial_status": [item.value for item in FinancialLifecycleStatus],
        "api_canonical_prefix": "/api/v1",
        "api_legacy_prefix": "/api",
    }
''',
    )
    write_new(
        "backend/tests/test_api_version_middleware.py",
        '''from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.api_version_middleware import APIVersionCompatibilityMiddleware


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(APIVersionCompatibilityMiddleware)

    @app.get("/api/ping")
    async def ping():
        return {"ok": True}

    return app


def test_api_v1_rewrites_to_existing_router():
    response = TestClient(_app()).get("/api/v1/ping")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert response.headers["x-ejc-api-version"] == "1"


def test_legacy_api_remains_available_with_successor_header():
    response = TestClient(_app()).get("/api/ping")
    assert response.status_code == 200
    assert response.headers["deprecation"] == "true"
    assert response.headers["link"] == '</api/v1/ping>; rel="successor-version"'
''',
    )
    write_new(
        "frontend/src/config/canonicalRoutes.ts",
        '''export const CANONICAL_ROUTES = {
  dashboard: "/",
  clientes: "/clientes",
  casos: "/casos",
  atividades: "/atividades",
  documentos: "/documentos",
  pecas: "/pecas",
  inteligencia: "/inteligencia",
  areasAtuacao: "/areas-de-atuacao",
  financeiro: "/financeiro",
  configuracoes: "/configuracoes",
} as const;

export type LegacyCanonicalRedirect = {
  from: string;
  to: string;
  reason: string;
};

export const LEGACY_CANONICAL_REDIRECTS: LegacyCanonicalRedirect[] = [
  {
    from: "/prazos",
    to: "/atividades?tipo=prazo",
    reason: "Prazos foram consolidados na Central de Agenda e Prazos.",
  },
  {
    from: "/tarefas",
    to: "/atividades?tipo=tarefa",
    reason: "Tarefas foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/intimacoes",
    to: "/atividades?tipo=intimacao",
    reason: "Intimações foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/suspensoes",
    to: "/atividades?tipo=suspensao",
    reason: "Suspensões foram consolidadas na Central de Agenda e Prazos.",
  },
  {
    from: "/knowledge-hub",
    to: "/inteligencia?tab=conhecimento",
    reason: "Conhecimento Jurídico foi consolidado em Pesquisa e IA.",
  },
  {
    from: "/ramos",
    to: "/areas-de-atuacao",
    reason: "Ramos do Direito passou a se chamar Áreas de Atuação.",
  },
];
''',
    )
    # frontend/src/config/domainContracts.ts NÃO é mais gerado aqui: o arquivo
    # nasceu órfão (nenhum call site em todo o frontend), duplicava à mão os
    # literais de backend/app/core/domain_contracts.py — sem replicar a lógica
    # associada (canonical_case_status) — e foi removido em 1befdf0. Regerá-lo
    # recriaria a dívida de sincronização manual; se um dia o frontend precisar
    # desses unions, gerar a partir do OpenAPI em vez de copiar.
    write_new(
        "frontend/src/config/__tests__/canonicalRoutes.test.ts",
        '''import { describe, expect, it } from "vitest";
import { CANONICAL_ROUTES, LEGACY_CANONICAL_REDIRECTS } from "../canonicalRoutes";


describe("canonical routes", () => {
  it("uses semantic area-of-practice naming", () => {
    expect(CANONICAL_ROUTES.areasAtuacao).toBe("/areas-de-atuacao");
  });

  it("has unique legacy aliases and canonical destinations", () => {
    const sources = LEGACY_CANONICAL_REDIRECTS.map((item) => item.from);
    expect(new Set(sources).size).toBe(sources.length);
    for (const item of LEGACY_CANONICAL_REDIRECTS) {
      expect(item.from.startsWith("/")).toBe(true);
      expect(item.to.startsWith("/")).toBe(true);
      expect(item.reason.length).toBeGreaterThan(10);
    }
  });
});
''',
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="Falha se o script produzir mudanças")
    args = parser.parse_args()

    create_files()
    update_main()
    update_api_client()
    update_module_registry()
    update_app_routes()

    if args.check:
        import subprocess

        changed = subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True, capture_output=True, check=True
        ).stdout.strip()
        if changed:
            print(changed)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
