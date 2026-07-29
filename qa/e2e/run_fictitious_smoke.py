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

AI-005 (auditoria máxima 2026-07-26) — este runner era um smoke frouxo:
POSTs da matriz eram PULADOS em silêncio, códigos de módulo ausente
(404/405) contavam como sucesso e nenhum passo verificava EFEITO real. Agora:

  • cada escrita é RELIDA pela API e o conteúdo é conferido (assert de efeito
    — o proxy possível para "assert de banco" sem acesso direto ao Postgres);
  • 404/405/503 nunca são "ok": passam a marcar o passo como DEGRADADO,
    reportado à parte e FALHA em modo estrito (default; EJC_E2E_STRICT=false
    afrouxa para ambiente incompleto);
  • POST da matriz não coberto por fluxo dedicado é executado; o que for
    deliberadamente pulado entra no relatório como `nao_coberto` (nunca some);
  • negativas de autorização (sem token → 401; id inexistente → 404) são
    exercitadas — um endpoint que responde 200 nesses casos é falha;
  • cleanup idempotente ao final remove os recursos fictícios criados.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
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

# ── Identidade EXCLUSIVA por execução ────────────────────────────────────────
# Sem isto, os payloads da matriz são idênticos em toda execução (mesmo CPF,
# mesmo número de processo): a segunda execução leva 409, cai no fallback "achar
# pelo marcador" e passa a operar sobre o registro de OUTRA execução. O cleanup
# recusa apagá-lo (correto), mas o caso e o documento criados ficam pendurados
# num cliente alheio. Com RUN_ID cada execução cria dados só seus, o 409 deixa de
# acontecer e o isolamento não depende mais de heurística.
RUN_ID = (os.getenv("EJC_E2E_RUN_ID") or uuid.uuid4().hex[:8]).strip()
MARKER_RUN = f"{MARKER}-{RUN_ID}"
MOTIVO_CLEANUP = f"Limpeza automatica do E2E {MARKER_RUN}"

# Valores literais da matriz que precisam variar por execução.
CPF_MATRIZ = "52998224725"
PROCESSO_MATRIZ = "5000000-83.2026.8.13.0027"


def _processo_da_execucao(run_id: str) -> str:
    """Número CNJ fictício por execução, com dígito verificador CALCULADO.

    O backend VALIDA o DV (módulo 97, Res. CNJ 65/2008 — schemas/case.py chama
    validar_cnj sempre que o número tem 20 dígitos). Variar só o sequencial e
    manter o "-83" do número original produzia DV inválido em ~99% das
    execuções: `POST /api/cases/` respondia 422, o caso não era criado e toda a
    metade seguinte da suíte (upload, follow-ups, cleanup) era pulada."""
    seq = int(hashlib.sha256(run_id.encode()).hexdigest()[:6], 16) % 10_000_000
    # NNNNNNN AAAA J TR OOOO, com o DV zerado, e DV = 98 - (resto * 100) % 97.
    corpo = f"{seq:07d}" + "2026" + "8" + "13" + "0027"
    dv = 98 - (int(corpo) * 100) % 97
    return f"{seq:07d}-{dv:02d}.2026.8.13.0027"


def _cpf_da_execucao(run_id: str) -> str:
    """CPF sintético determinístico por execução, com dígitos verificadores
    válidos (o cadastro de cliente valida — routers/clients.py)."""
    base = [int(c, 16) % 10 for c in hashlib.sha256(run_id.encode()).hexdigest()[:9]]
    if len(set(base)) == 1:  # CPFs de dígito repetido são rejeitados
        base[0] = (base[0] + 1) % 10
    for _ in range(2):
        soma = sum(d * p for d, p in zip(base, range(len(base) + 1, 1, -1)))
        resto = (soma * 10) % 11
        base.append(0 if resto == 10 else resto)
    return "".join(str(d) for d in base)


def _personalizar(valor: Any) -> Any:
    """Reescreve os dados fictícios da matriz com a identidade desta execução.
    Percorre a estrutura inteira: prefixo do marcador nos textos, CPF e número
    de processo próprios."""
    if isinstance(valor, dict):
        return {k: _personalizar(v) for k, v in valor.items()}
    if isinstance(valor, list):
        return [_personalizar(v) for v in valor]
    if isinstance(valor, str):
        if valor == CPF_MATRIZ:
            return _cpf_da_execucao(RUN_ID)
        if valor == PROCESSO_MATRIZ:
            return _processo_da_execucao(RUN_ID)
        # Só troca o marcador "puro" — não duplica o sufixo em reprocessamento.
        if MARKER in valor and MARKER_RUN not in valor:
            return valor.replace(MARKER, MARKER_RUN)
    return valor


# Códigos que indicam MÓDULO AUSENTE/INDISPONÍVEL. Aceitá-los como sucesso era
# o defeito central do AI-005 — um router removido passava despercebido.
DEGRADADOS = {404, 405, 501, 503}

# Modo estrito (default): passo degradado conta como FALHA. Só afrouxe em
# ambiente sabidamente incompleto — e o relatório continua registrando tudo.
STRICT = os.getenv("EJC_E2E_STRICT", "true").strip().lower() != "false"


@dataclass
class StepResult:
    name: str
    method: str
    path: str
    status_code: int | None = None
    ok: bool = False
    detail: str = ""
    response_excerpt: Any = None
    degraded: bool = False


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
    # Checks da matriz deliberadamente não executados — vão ao relatório em vez
    # de sumirem num `continue` (AI-005).
    nao_coberto: list[dict[str, Any]] = field(default_factory=list)
    # IDs REALMENTE criados por esta execução. O cleanup só remove estes: um
    # registro encontrado pelo marcador (reexecução após 409) é de OUTRA
    # execução e apagá-lo destruiria dado alheio no staging compartilhado.
    criados_nesta_execucao: set[str] = field(default_factory=set)


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Variável obrigatória ausente: {name}")
    return value


def _load_matrix() -> dict[str, Any]:
    matriz = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    # Carimba a identidade desta execução nos dados fictícios — todos os fluxos
    # leem daqui, então nenhum deles precisa lembrar de personalizar.
    if "fictional_data" in matriz:
        matriz["fictional_data"] = _personalizar(matriz["fictional_data"])
    return matriz


# Chaves cujo VALOR nunca pode ir para o relatório em claro. Além de segredos,
# inclui PII: o relatório grava trechos de `GET /api/clients/`, e ClientResponse
# devolve o CPF DECIFRADO — o sistema cifra CPF em repouso justamente para isso,
# e o relatório o reescrevia em texto puro no disco do runner (e em artefato de
# CI, se publicado).
_CHAVES_REDIGIDAS = frozenset({
    # Segredos
    "access_token", "refresh_token", "token", "senha", "password", "secret",
    "api_key", "authorization",
    # Identificadores do titular
    "cpf", "cpf_plain", "cnpj", "cnpj_plain", "rg", "cnh",
    "email", "telefone", "whatsapp", "celular",
    # Demais campos de ClientBase — o relatório podia sair com nome completo,
    # data de nascimento, endereço e o campo livre `observacoes`, que é onde o
    # escritório concentra a anotação mais sensível do cliente.
    "nome", "nome_completo", "full_name", "razao_social", "nome_fantasia",
    "data_nascimento", "profissao", "observacoes",
    "cep", "logradouro", "numero", "complemento", "bairro", "endereco",
})

# Padrões de PII para o corpo NÃO-JSON (erro HTML de proxy, text/plain, CSV):
# esse caminho devolvia `resp.text` cru, sem passar por redação nenhuma.
_PADROES_PII = (
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),                  # CPF
    re.compile(r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b"),           # CNPJ
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),                          # e-mail
    re.compile(r"\b(?:\+55\s?)?\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b"),      # telefone
)


def _redigir_texto(bruto: str) -> str:
    for padrao in _PADROES_PII:
        bruto = padrao.sub("***", bruto)
    return bruto


def _redigir(valor: Any, profundidade: int = 0) -> Any:
    """Redação RECURSIVA: a versão anterior só olhava o nível superior de um
    dict, então a lista sob `data` (onde ficam os clientes) passava intacta."""
    if profundidade > 6:
        return "..."
    if isinstance(valor, dict):
        return {
            k: ("***" if str(k).lower() in _CHAVES_REDIGIDAS
                else _redigir(v, profundidade + 1))
            for k, v in valor.items()
        }
    if isinstance(valor, list):
        return [_redigir(v, profundidade + 1) for v in valor[:20]]
    return valor


def _excerpt(resp: httpx.Response) -> Any:
    try:
        data = resp.json()
    except Exception:
        # Corpo não-JSON também passa pela redação — antes ia cru.
        return _redigir_texto(resp.text[:800])
    return _redigir(data)


def _record(state: SuiteState, result: StepResult) -> None:
    state.results.append(result)
    icon = "DEGR" if result.degraded and result.ok else ("OK" if result.ok else "FAIL")
    print(f"[{icon}] {result.name} {result.method} {result.path} -> {result.status_code} {result.detail}")


def _afirmar(state: SuiteState, nome: str, condicao: bool, detalhe: str) -> bool:
    """Assert de EFEITO (AI-005): confere o que a API devolveu DEPOIS da escrita.
    Um 201 que não persiste nada deixa de passar como sucesso."""
    _record(state, StepResult(
        name=nome, method="ASSERT", path="-", status_code=None,
        ok=condicao, detail="" if condicao else detalhe,
    ))
    return condicao


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
    autenticado: bool = True,
    degradado_ok: bool = False,
) -> httpx.Response | None:
    headers = {}
    if autenticado and state.access_token:
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
        esperado = resp.status_code in expected
        # AI-005: bater num código de módulo ausente NÃO é sucesso, mesmo que a
        # matriz o liste como aceitável — é sinalizado e, em modo estrito, falha.
        # `degradado_ok` cobre os casos em que o código É o resultado correto
        # (cleanup idempotente, negativa de autorização, 404 proposital).
        degradado = (not degradado_ok
                     and resp.status_code in DEGRADADOS
                     and resp.status_code in expected)
        ok = esperado and not (degradado and STRICT)
        if not esperado:
            detalhe = f"esperado={expected}"
        elif degradado:
            detalhe = (f"DEGRADADO: {resp.status_code} indica módulo ausente/indisponível"
                       + ("" if STRICT else " (tolerado: EJC_E2E_STRICT=false)"))
        else:
            detalhe = ""
        _record(
            state,
            StepResult(
                name=name,
                method=method,
                path=path,
                status_code=resp.status_code,
                ok=ok,
                detail=detalhe,
                response_excerpt=_excerpt(resp),
                degraded=degradado,
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
    # AI-005: 422 saiu do "esperado" — validação quebrada não é sucesso. 409
    # (já existe) segue válido: o fluxo então localiza o registro pelo marcador.
    resp = _request(
        client,
        state,
        name="clientes.criar_pf_ficticio",
        method="POST",
        path="/api/clients/",
        expected=[201, 409],
        json_body=payload,
    )
    if resp and resp.status_code == 201:
        state.client_id = resp.json().get("id")
        if state.client_id:
            state.criados_nesta_execucao.add(str(state.client_id))
        # Assert de efeito: o cliente existe e traz os dados enviados.
        rel = _request(client, state, name="clientes.reler",
                       method="GET", path=f"/api/clients/{state.client_id}",
                       expected=[200])
        if rel is not None and rel.status_code == 200:
            corpo = rel.json()
            _afirmar(state, "clientes.efeito_persistido",
                     str(corpo.get("nome") or "") == str(payload.get("nome") or ""),
                     f"nome relido={corpo.get('nome')!r} != enviado={payload.get('nome')!r}")
        return

    # Se já existir ou a validação mudar, tenta localizar pelo marcador para seguir o fluxo.
    resp = _request(
        client,
        state,
        name="clientes.buscar_marcador",
        method="GET",
        path=f"/api/clients/?search={MARKER_RUN}",
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
        expected=[200, 201],   # AI-005: 422 não é sucesso
        json_body=payload,
    )
    if resp and resp.status_code in {200, 201}:
        state.case_id = resp.json().get("id")
        if state.case_id:
            state.criados_nesta_execucao.add(str(state.case_id))
        rel = _request(client, state, name="casos.reler",
                       method="GET", path=f"/api/cases/{state.case_id}",
                       expected=[200])
        if rel is not None and rel.status_code == 200:
            corpo = rel.json()
            _afirmar(state, "casos.efeito_vinculo_cliente",
                     str(corpo.get("client_id") or "") == str(state.client_id),
                     f"client_id relido={corpo.get('client_id')!r} != {state.client_id!r}")
        return

    resp = _request(
        client,
        state,
        name="casos.buscar_marcador",
        method="GET",
        path=f"/api/cases/?search={MARKER_RUN}",
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
        if state.document_id:
            state.criados_nesta_execucao.add(str(state.document_id))
        rel = _request(client, state, name="documentos.reler",
                       method="GET", path=f"/api/documents/{state.document_id}",
                       expected=[200])
        if rel is not None and rel.status_code == 200:
            corpo = rel.json()
            _afirmar(state, "documentos.efeito_vinculo_caso",
                     str(corpo.get("case_id") or "") == str(state.case_id),
                     f"case_id relido={corpo.get('case_id')!r} != {state.case_id!r}")


def _case_followups(client: httpx.Client, state: SuiteState, matrix: dict[str, Any]) -> None:
    if not state.case_id:
        return
    _request(client, state, name="casos.detalhe", method="GET", path=f"/api/cases/{state.case_id}", expected=[200])
    atualizacao = matrix["fictional_data"]["atualizacao_caso"]
    _request(
        client,
        state,
        name="casos.atualizar",
        method="PATCH",
        path=f"/api/cases/{state.case_id}",
        expected=[200],
        json_body=atualizacao,
    )
    # Assert de efeito: o PATCH mudou mesmo o registro (um handler que aceita e
    # descarta o corpo passava despercebido — foi exatamente o bug AI-121).
    rel = _request(client, state, name="casos.reler_apos_patch", method="GET",
                   path=f"/api/cases/{state.case_id}", expected=[200])
    if rel is not None and rel.status_code == 200:
        corpo = rel.json()
        divergentes = [k for k, v in atualizacao.items()
                       if k in corpo and str(corpo.get(k)) != str(v)]
        # Campo que não volta na releitura NÃO é "ok por omissão": sem ele não
        # há como provar persistência. Se NENHUM campo é verificável, o assert
        # falha (fail-closed) — ignorá-los reproduziria a frouxidão do AI-005.
        ausentes = [k for k in atualizacao if k not in corpo]
        verificaveis = [k for k in atualizacao if k in corpo]
        _afirmar(
            state, "casos.efeito_patch_persistido",
            not divergentes and bool(verificaveis),
            (f"campos não persistidos pelo PATCH: {divergentes}" if divergentes
             else f"nenhum campo do PATCH é verificável na releitura: {ausentes}"),
        )
        if ausentes and verificaveis:
            print(f"      (campos do PATCH ausentes na releitura, não verificáveis: {ausentes})")

    mov = matrix["fictional_data"]["movimento"]
    resp = _request(
        client,
        state,
        name="casos.movimento",
        method="POST",
        path=f"/api/cases/{state.case_id}/movimentos",
        expected=[200, 201],   # AI-005: 404/405 = módulo quebrado, não sucesso
        json_body=mov,
    )
    if resp is not None and resp.status_code in {200, 201}:
        lst = _request(client, state, name="casos.movimentos_listar", method="GET",
                       path=f"/api/cases/{state.case_id}/movimentos", expected=[200])
        if lst is not None and lst.status_code == 200:
            corpo = lst.json()
            linhas = corpo.get("data") if isinstance(corpo, dict) else corpo
            alvo = str(mov.get("descricao") or "")
            _afirmar(
                state, "casos.efeito_movimento_na_timeline",
                any(alvo and alvo in str((r or {}).get("descricao") or "")
                    for r in (linhas or [])),
                "movimento criado não aparece na timeline do caso",
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


# POSTs da matriz já exercitados (com asserts de efeito) pelos fluxos dedicados
# — repetí-los criaria lixo duplicado. Qualquer OUTRO POST é EXECUTADO.
_POST_COBERTO_POR_FLUXO = {"/api/clients/", "/api/cases/", "/api/documents/upload"}


def _matrix_smoke(client: httpx.Client, state: SuiteState, matrix: dict[str, Any]) -> None:
    for module in matrix["modules"]:
        for check in module.get("api_checks", []):
            if check["method"] == "POST" and check["path"] in _POST_COBERTO_POR_FLUXO:
                # AI-005: em vez de sumir num `continue`, o pulo é DECLARADO no
                # relatório — cobertura omitida nunca se parece com cobertura.
                state.nao_coberto.append({
                    "module_key": module["module_key"],
                    "method": check["method"],
                    "path": check["path"],
                    "motivo": "coberto por fluxo dedicado com assert de efeito",
                })
                continue
            _request(
                client,
                state,
                name=f"{module['module_key']}.smoke",
                method=check["method"],
                path=check["path"],
                expected=check["expected"],
                json_body=check.get("body"),
            )


def _negativas_de_autorizacao(client: httpx.Client, state: SuiteState) -> None:
    """AI-005: o smoke só media caminho feliz. Um endpoint que devolve 200 sem
    token — ou para id inexistente — é falha de segurança, não 'ok'."""
    _request(client, state, name="auth.sem_token_401", method="GET",
             path="/api/cases/", expected=[401], autenticado=False)
    _request(client, state, name="auth.id_inexistente_404", method="GET",
             path="/api/cases/00000000-0000-0000-0000-000000000000",
             expected=[404], degradado_ok=True)


def _cleanup(client: httpx.Client, state: SuiteState) -> None:
    """Remove (soft-delete) SOMENTE os recursos criados por ESTA execução.
    Idempotente: 404 significa que já não existe — aceitável em reexecução.

    Registro localizado pelo MARCADOR (reexecução após 409/erro) pertence a
    outra execução e NÃO é apagado: o alvo pode ser um staging compartilhado —
    ou, com EJC_ALLOW_PRODUCTION_E2E, a própria produção."""
    # DELETE /api/cases/{id} EXIGE `motivo` (min 5 chars, body ou query) e
    # responde 422 sem ele — routers/cases.py:589. Sem o motivo, o cleanup do
    # caso falhava em toda execução e o caso fictício ficava no ambiente.
    alvos = [
        ("documentos", state.document_id, "/api/documents/{}"),
        ("casos", state.case_id, f"/api/cases/{{}}?motivo={MOTIVO_CLEANUP}"),
        ("clientes", state.client_id, "/api/clients/{}"),
    ]
    for rotulo, ident, molde in alvos:
        if not ident:
            continue
        if str(ident) not in state.criados_nesta_execucao:
            state.nao_coberto.append({
                "module_key": rotulo, "method": "DELETE",
                "path": molde.format(ident),
                "motivo": "registro preexistente (localizado pelo marcador) — "
                          "cleanup NÃO remove dado de outra execução",
            })
            print(f"[skip] {rotulo}.cleanup — registro preexistente, preservado")
            continue
        _request(client, state, name=f"{rotulo}.cleanup", method="DELETE",
                 path=molde.format(ident), expected=[200, 204, 404],
                 degradado_ok=True)


def _write_report(state: SuiteState, matrix: dict[str, Any]) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    total = len(state.results)
    failed = [r for r in state.results if not r.ok]
    degradados = [r for r in state.results if r.degraded]
    asserts = [r for r in state.results if r.method == "ASSERT"]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": state.base_url,
        "marker": MARKER, "marker_run": MARKER_RUN, "run_id": RUN_ID,
        "modo_estrito": STRICT,
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
            "degradados": len(degradados),
            "asserts_de_efeito": len(asserts),
            "checks_nao_cobertos": len(state.nao_coberto),
            "modules_in_matrix": len(matrix["modules"]),
        },
        # Cobertura omitida fica EXPLÍCITA no artefato (AI-005).
        "nao_coberto": state.nao_coberto,
        "results": [r.__dict__ for r in state.results],
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nRelatório gravado em: {REPORT_PATH}")
    print(f"Asserts de efeito: {len(asserts)} · degradados: {len(degradados)} · "
          f"checks não cobertos: {len(state.nao_coberto)}")
    if degradados:
        print("Endpoints degradados (404/405/501/503):")
        for r in degradados:
            print(f"  - {r.name} {r.method} {r.path} -> {r.status_code}")
    if failed:
        print(f"Falhas: {len(failed)}")
        for r in failed:
            print(f"  - {r.name} {r.method} {r.path} -> {r.status_code} {r.detail}")
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
        # O cleanup e o relatório vão no `finally`: qualquer exceção no meio do
        # fluxo (proxy devolvendo HTML, payload inesperado) abortava a execução
        # ANTES do cleanup e os registros fictícios ficavam no ambiente — sem
        # sequer deixar no relatório os IDs vazados. Os IDs são registrados
        # incrementalmente logo após cada criação, então o `finally` sempre
        # sabe o que remover, inclusive após falha parcial.
        try:
            _request(client, state, name="health.live", method="GET", path="/api/health", expected=[200])
            _login(client, state)
            _negativas_de_autorizacao(client, state)
            _matrix_smoke(client, state, matrix)
            _create_client(client, state, matrix)
            _create_case(client, state, matrix)
            _upload_document(client, state, matrix)
            _case_followups(client, state, matrix)
            _document_followups(client, state)
        finally:
            # Cleanup idempotente: a suíte não deixa resíduo fictício no ambiente.
            if os.getenv("EJC_E2E_CLEANUP", "true").strip().lower() != "false":
                _cleanup(client, state)
            _write_report(state, matrix)


if __name__ == "__main__":
    main()
