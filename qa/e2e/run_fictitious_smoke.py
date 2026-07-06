#!/usr/bin/env python3
"""Smoke/E2E funcional do EJC com dados fictícios.

Executa contra uma URL de homologação/staging informada por variáveis de
ambiente. Não deve ser rodado contra produção sem autorização explícita.

Uso:
  EJC_BASE_URL="https://staging.exemplo" \
  EJC_TEST_EMAIL="admin@example.com" \
  EJC_TEST_PASSWORD="senha" \
  python qa/e2e/run_fictitious_smoke.py

Saída:
  - imprime resumo no terminal;
  - grava JSON em qa/e2e/reports/e2e_fictitious_report.json.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "qa" / "e2e" / "fictitious_matrix.json"
REPORT_DIR = ROOT / "qa" / "e2e" / "reports"
REPORT_PATH = REPORT_DIR / "e2e_fictitious_report.json"
MARKER = "E2E-FICTICIO"


@dataclass
class StepResult:
    name: str
    method: str
    path: str
    status_code: int | None = None
    ok: bool = False
    detail: str = ""
    response_excerpt: Any = None


@dataclass
class SuiteState:
    base_url: str
    access_token: str | None = None
    refresh_token: str | None = None
    user: dict[str, Any] = field(default_factory=dict)
    client_id: str | None = None
    case_id: str | None = None
    document_id: str | None = None
    results: list[StepResult] = field(default_factory=list)


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Variável obrigatória ausente: {name}")
    return value


def _load_matrix() -> dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def _excerpt(resp: httpx.Response) -> Any:
    try:
        data = resp.json()
    except Exception:
        return resp.text[:800]
    if isinstance(data, dict):
        redacted = dict(data)
        for key in ["access_token", "refresh_token", "token", "senha", "password"]:
            if key in redacted:
                redacted[key] = "***"
        return redacted
    return data


def _record(state: SuiteState, result: StepResult) -> None:
    state.results.append(result)
    icon = "OK" if result.ok else "FAIL"
    print(f"[{icon}] {result.name} {result.method} {result.path} -> {result.status_code} {result.detail}")


def _request(
    client: httpx.Client,
    state: SuiteState,
    *,
    name: str,
    method: str,
    path: str,
    expected: list[int],
    json_body: dict[str, Any] | None = None,
    files: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
) -> httpx.Response | None:
    headers = {}
    if state.access_token:
        headers["Authorization"] = f"Bearer {state.access_token}"
    try:
        resp = client.request(
            method,
            path,
            headers=headers,
            json=json_body,
            files=files,
            data=data,
            timeout=60,
        )
        ok = resp.status_code in expected
        _record(
            state,
            StepResult(
                name=name,
                method=method,
                path=path,
                status_code=resp.status_code,
                ok=ok,
                detail="" if ok else f"esperado={expected}",
                response_excerpt=_excerpt(resp),
            ),
        )
        return resp
    except Exception as exc:
        _record(
            state,
            StepResult(name=name, method=method, path=path, ok=False, detail=str(exc)),
        )
        return None


def _login(client: httpx.Client, state: SuiteState) -> None:
    email = _env("EJC_TEST_EMAIL")
    password = _env("EJC_TEST_PASSWORD")
    resp = _request(
        client,
        state,
        name="auth.login",
        method="POST",
        path="/api/auth/login",
        expected=[200],
        json_body={"email": email, "password": password},
    )
    if not resp or resp.status_code != 200:
        raise SystemExit("Login falhou; abortando para não gerar resultados falsos.")
    data = resp.json()
    state.access_token = data.get("access_token")
    state.refresh_token = data.get("refresh_token")
    state.user = {k: data.get(k) for k in ["user_id", "full_name", "role"]}


def _create_client(client: httpx.Client, state: SuiteState, matrix: dict[str, Any]) -> None:
    payload = matrix["fictional_data"]["cliente_pf"]
    resp = _request(
        client,
        state,
        name="clientes.criar_pf_ficticio",
        method="POST",
        path="/api/clients/",
        expected=[201, 409, 422],
        json_body=payload,
    )
    if resp and resp.status_code == 201:
        state.client_id = resp.json().get("id")
        return

    # Se já existir ou a validação mudar, tenta localizar pelo marcador para seguir o fluxo.
    resp = _request(
        client,
        state,
        name="clientes.buscar_marcador",
        method="GET",
        path=f"/api/clients/?search={MARKER}",
        expected=[200],
    )
    if resp and resp.status_code == 200:
        rows = resp.json().get("data") or []
        if rows:
            state.client_id = rows[0].get("id")


def _create_case(client: httpx.Client, state: SuiteState, matrix: dict[str, Any]) -> None:
    if not state.client_id:
        _record(state, StepResult("casos.criar", "POST", "/api/cases/", ok=False, detail="sem client_id"))
        return
    payload = dict(matrix["fictional_data"]["caso_consumidor"])
    payload["client_id"] = state.client_id
    resp = _request(
        client,
        state,
        name="casos.criar_consumidor_ficticio",
        method="POST",
        path="/api/cases/",
        expected=[200, 201, 422],
        json_body=payload,
    )
    if resp and resp.status_code in {200, 201}:
        state.case_id = resp.json().get("id")
        return

    resp = _request(
        client,
        state,
        name="casos.buscar_marcador",
        method="GET",
        path=f"/api/cases/?search={MARKER}",
        expected=[200],
    )
    if resp and resp.status_code == 200:
        rows = resp.json().get("data") or []
        if rows:
            state.case_id = rows[0].get("id")


def _upload_document(client: httpx.Client, state: SuiteState, matrix: dict[str, Any]) -> None:
    if not state.case_id:
        _record(state, StepResult("documentos.upload", "POST", "/api/documents/upload", ok=False, detail="sem case_id"))
        return
    doc = matrix["fictional_data"]["documento_texto"]
    files = {
        "file": (
            doc["filename"],
            doc["content"].encode("utf-8"),
            doc["content_type"],
        )
    }
    data = {
        "titulo": doc["titulo"],
        "tipo": "prova",
        "confidencialidade": "normal",
        "case_id": state.case_id,
    }
    resp = _request(
        client,
        state,
        name="documentos.upload_txt_ficticio",
        method="POST",
        path="/api/documents/upload",
        expected=[201],
        files=files,
        data=data,
    )
    if resp and resp.status_code == 201:
        state.document_id = resp.json().get("id")


def _case_followups(client: httpx.Client, state: SuiteState, matrix: dict[str, Any]) -> None:
    if not state.case_id:
        return
    _request(client, state, name="casos.detalhe", method="GET", path=f"/api/cases/{state.case_id}", expected=[200])
    _request(
        client,
        state,
        name="casos.atualizar",
        method="PATCH",
        path=f"/api/cases/{state.case_id}",
        expected=[200],
        json_body=matrix["fictional_data"]["atualizacao_caso"],
    )
    _request(
        client,
        state,
        name="casos.movimento",
        method="POST",
        path=f"/api/cases/{state.case_id}/movimentos",
        expected=[200, 201, 404, 405],
        json_body=matrix["fictional_data"]["movimento"],
    )


def _document_followups(client: httpx.Client, state: SuiteState) -> None:
    if not state.document_id:
        return
    _request(
        client,
        state,
        name="documentos.classificar",
        method="POST",
        path=f"/api/documents/{state.document_id}/classificar",
        expected=[200, 422, 503],
    )


def _matrix_smoke(client: httpx.Client, state: SuiteState, matrix: dict[str, Any]) -> None:
    for module in matrix["modules"]:
        for check in module.get("api_checks", []):
            # Evita repetir criação complexa já coberta pelos fluxos específicos.
            if check["method"] == "POST":
                continue
            _request(
                client,
                state,
                name=f"{module['module_key']}.smoke",
                method=check["method"],
                path=check["path"],
                expected=check["expected"],
            )


def _write_report(state: SuiteState, matrix: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(state.results)
    failed = [r for r in state.results if not r.ok]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": state.base_url,
        "marker": MARKER,
        "user": state.user,
        "created_refs": {
            "client_id": state.client_id,
            "case_id": state.case_id,
            "document_id": state.document_id,
        },
        "summary": {
            "total": total,
            "passed": total - len(failed),
            "failed": len(failed),
            "modules_in_matrix": len(matrix["modules"]),
        },
        "results": [r.__dict__ for r in state.results],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRelatório gravado em: {REPORT_PATH}")
    if failed:
        print(f"Falhas: {len(failed)}")
        sys.exit(2)


def main() -> None:
    base_url = _env("EJC_BASE_URL").rstrip("/")
    if os.getenv("EJC_ALLOW_PRODUCTION_E2E") != "true" and "staging" not in base_url and "homolog" not in base_url and "localhost" not in base_url:
        raise SystemExit(
            "Proteção ativa: use staging/homologação/localhost ou defina EJC_ALLOW_PRODUCTION_E2E=true com autorização explícita."
        )

    matrix = _load_matrix()
    state = SuiteState(base_url=base_url)
    with httpx.Client(base_url=base_url, follow_redirects=True) as client:
        _request(client, state, name="health.live", method="GET", path="/api/health", expected=[200])
        _login(client, state)
        _matrix_smoke(client, state, matrix)
        _create_client(client, state, matrix)
        _create_case(client, state, matrix)
        _upload_document(client, state, matrix)
        _case_followups(client, state, matrix)
        _document_followups(client, state)

    _write_report(state, matrix)


if __name__ == "__main__":
    main()
