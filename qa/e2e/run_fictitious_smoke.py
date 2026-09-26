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

import rbac_matrix  # qa/e2e/rbac_matrix.py — matriz papel x rota (Issue #700)

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = ROOT / "qa" / "e2e" / "fictitious_matrix.json"
ROUTERS_DIR = ROOT / "backend" / "app" / "routers"
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
    # Recursos criados por POSTs da matriz (fora dos três fluxos dedicados).
    # Sem isto eles não apareciam em lugar nenhum e viravam resíduo silencioso.
    extras_criados: list[tuple[str, str, str]] = field(default_factory=list)
    # Matriz papel x rota (Issue #700) — preenchida por `_matriz_rbac`.
    rbac_matrix: dict[str, Any] = field(default_factory=dict)


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
    timeout: float = 60,
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
            timeout=timeout,
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
        # Não existe GET /api/documents/{id} (só list/download/patch/delete —
        # 405 na releitura direta, pente fino de 29/08/2026). O efeito é
        # conferido pela LISTA filtrada por caso: o doc aparecer ali prova o
        # vínculo — mesmo assert, rota que existe.
        rel = _request(client, state, name="documentos.reler",
                       method="GET",
                       path=f"/api/documents/?case_id={state.case_id}&page_size=100",
                       expected=[200])
        if rel is not None and rel.status_code == 200:
            itens = (rel.json() or {}).get("data") or []
            _afirmar(state, "documentos.efeito_vinculo_caso",
                     any(str(d.get("id")) == str(state.document_id) for d in itens),
                     f"doc {state.document_id} não aparece na lista do caso {state.case_id}")


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


def _matrix_smoke(
    client: httpx.Client,
    state: SuiteState,
    matrix: dict[str, Any],
    *,
    covered_posts: set[str] | None = None,
    skipped_posts: dict[str, str] | None = None,
) -> None:
    covered = _POST_COBERTO_POR_FLUXO if covered_posts is None else covered_posts
    skipped = skipped_posts or {}
    for module in matrix["modules"]:
        for check in module.get("api_checks", []):
            if check["method"] == "POST" and check["path"] in skipped:
                state.nao_coberto.append({
                    "module_key": module["module_key"],
                    "method": check["method"],
                    "path": check["path"],
                    "motivo": skipped[check["path"]],
                })
                continue
            if check["method"] == "POST" and check["path"] in covered:
                # AI-005: em vez de sumir num `continue`, o pulo é DECLARADO no
                # relatório — cobertura omitida nunca se parece com cobertura.
                state.nao_coberto.append({
                    "module_key": module["module_key"],
                    "method": check["method"],
                    "path": check["path"],
                    "motivo": "coberto por fluxo dedicado com assert de efeito",
                })
                continue
            # A guarda de isolamento vive só no _cleanup. Este motor executa
            # QUALQUER método vindo da matriz, então um DELETE/PATCH/PUT com
            # path fixo apagaria ou alteraria registro PREEXISTENTE sem passar
            # por `criados_nesta_execucao`. Recusa explicitamente, em vez de
            # confiar em que ninguém vá adicioná-los.
            if check["method"] in ("DELETE", "PATCH", "PUT"):
                _afirmar(
                    state, f"{module['module_key']}.metodo_destrutivo_na_matriz",
                    False,
                    f"{check['method']} {check['path']}: a matriz não pode conter "
                    "método que altera/apaga registro — o smoke não tem como saber "
                    "se o alvo foi criado por esta execução",
                )
                continue
            resp = _request(
                client,
                state,
                name=f"{module['module_key']}.smoke",
                method=check["method"],
                path=check["path"],
                expected=check["expected"],
                json_body=check.get("body"),
            )
            # POST fora dos fluxos dedicados TAMBÉM cria recurso: sem registrar
            # o id, ele nunca entra no cleanup e vira resíduo permanente.
            if check["method"] == "POST" and resp is not None and resp.status_code < 300:
                try:
                    ident = (resp.json() or {}).get("id")
                except Exception:
                    ident = None
                if ident:
                    state.criados_nesta_execucao.add(str(ident))
                    state.extras_criados.append((module["module_key"], check["path"], str(ident)))
                else:
                    _afirmar(
                        state, f"{module['module_key']}.id_ausente", False,
                        f"POST {check['path']} respondeu {resp.status_code} sem `id` — "
                        "recurso criado e NÃO rastreável para o cleanup",
                    )


def _negativas_de_autorizacao(client: httpx.Client, state: SuiteState) -> None:
    """AI-005: o smoke só media caminho feliz. Um endpoint que devolve 200 sem
    token — ou para id inexistente — é falha de segurança, não 'ok'."""
    _request(client, state, name="auth.sem_token_401", method="GET",
             path="/api/cases/", expected=[401], autenticado=False)
    _request(client, state, name="auth.id_inexistente_404", method="GET",
             path="/api/cases/00000000-0000-0000-0000-000000000000",
             expected=[404], degradado_ok=True)


# ── Matriz papel × rota (Issue #700) ─────────────────────────────────────────
# O runner autenticava com UMA conta só; a única negativa de autorização
# exercitada era "sem token" (401). Nunca se provava que financeiro,
# secretaria, estagiario e cliente_externo são barrados ONDE deveriam ser —
# a Issue #694 documenta 27 gates frouxos que nenhum passo desta suíte pegaria.
#
# `rbac_matrix.py` deriva a matriz por parsing estático dos routers reais
# (não uma lista escrita à mão que envelhece); aqui só autenticamos em cada
# papel e sondamos.

# (chave_do_papel, var_de_email, var_de_senha). O papel de GESTÃO (socio/admin)
# reaproveita a conta já obrigatória (EJC_TEST_EMAIL/EJC_TEST_PASSWORD) — ver
# `_matriz_rbac`; não está nesta lista porque não é uma credencial OPCIONAL a
# mais, a suíte inteira já depende dela.
PAPEIS_MATRIZ: tuple[tuple[str, str, str], ...] = (
    ("advogado", "EJC_TEST_EMAIL_ADVOGADO", "EJC_TEST_PASSWORD_ADVOGADO"),
    ("estagiario", "EJC_TEST_EMAIL_ESTAGIARIO", "EJC_TEST_PASSWORD_ESTAGIARIO"),
    ("financeiro", "EJC_TEST_EMAIL_FINANCEIRO", "EJC_TEST_PASSWORD_FINANCEIRO"),
    ("secretaria", "EJC_TEST_EMAIL_SECRETARIA", "EJC_TEST_PASSWORD_SECRETARIA"),
    ("cliente_externo", "EJC_TEST_EMAIL_CLIENTE_EXTERNO", "EJC_TEST_PASSWORD_CLIENTE_EXTERNO"),
)

# Papéis aceitos para a conta de GESTÃO (login primário, EJC_TEST_EMAIL) —
# usado por `_papel_gestao_confere` (achado #4 do review do PR #708).
ROLES_GESTAO: frozenset[str] = frozenset({"superadmin", "admin", "socio"})


def _papel_confere(role_key: str, actual_role: str | None) -> bool:
    """Achado #4 do review do PR #708: se uma variável de ambiente apontar
    para a conta errada (ex.: `EJC_TEST_EMAIL_FINANCEIRO` autentica um
    admin), o runner NÃO pode calcular expectativas com `actual_role` e
    registrar a célula sob `role_key` — isso reporta cobertura completa sem
    nunca ter exercitado o papel pedido. Só reaproveita `actual_role or
    role_key` quando os dois batem; caso contrário a célula fica FALTANTE,
    nunca aprovação silenciosa."""
    return actual_role == role_key


def _papel_gestao_confere(actual_role: str | None) -> bool:
    """Mesma ideia do achado #4 aplicada à conta primária (EJC_TEST_EMAIL):
    ela precisa autenticar um papel de GESTÃO de fato — senão a célula
    'gestao(login_primario)' mediria RBAC com um piso de privilégio errado
    sem avisar."""
    return actual_role in ROLES_GESTAO


def _login_papel(rc: httpx.Client, email: str, password: str) -> tuple[str | None, str | None, int | None]:
    """Login isolado por papel, em cliente httpx PRÓPRIO (cookie jar isolado
    do login primário — trocar de papel não pode contaminar a sessão da
    conta de gestão usada pelo resto da suíte)."""
    try:
        resp = rc.post("/api/auth/login", json={"email": email, "password": password}, timeout=60)
    except Exception:
        return None, None, None
    if resp.status_code != 200:
        return None, None, resp.status_code
    try:
        data = resp.json()
    except Exception:
        return None, None, resp.status_code
    return data.get("access_token"), data.get("role"), resp.status_code


def _sondar_papel(
    rc: httpx.Client,
    role_key: str,
    token: str,
    actual_role: str,
    gates: list[rbac_matrix.RouteGate],
    state: SuiteState,
) -> list[dict[str, Any]]:
    """Roda a amostra GET inteira sob o token de UM papel. Só GET: métodos
    mutantes não são seguros para sondar negativamente sem efeito colateral
    (ver limitação documentada em rbac_matrix.py)."""
    celulas: list[dict[str, Any]] = []
    headers = {"Authorization": f"Bearer {token}"}
    for gate in gates:
        esperado = gate.resultado_esperado(actual_role)
        # Pente fino §5.5: rota com query obrigatória ganha a query mínima
        # VÁLIDA do mapa — o 422 deixava a sonda "inconclusiva" e o handler
        # nunca era exercitado; com a query, papel permitido executa o handler
        # de verdade e papel negado prova o 403 mesmo em gate de corpo.
        qm = rbac_matrix.QUERY_MINIMA_POR_ROTA.get(gate.path)
        url = gate.path if qm is None else f"{gate.path}?{qm.query_string()}"
        try:
            resp = rc.get(url, headers=headers, timeout=30)
            status = resp.status_code
        except Exception as exc:
            _record(state, StepResult(
                name=f"rbac.{role_key}", method="GET", path=gate.path,
                ok=False, detail=f"erro de rede sondando papel {role_key}: {exc}",
            ))
            continue

        degraded = False
        if status == esperado:
            ok, detail = True, ""
        elif qm is not None and esperado == 200 and status in qm.aceitos_alem_de_200:
            # Código documentado no mapa (ex.: 404 de recurso fictício em rota
            # que exige recurso existente) — o handler EXECUTOU depois do gate,
            # que é o que a sonda com query mínima quer provar.
            ok = True
            detail = f"aceito {status} com query mínima: {qm.motivo}"
        elif qm is not None and status == 422:
            # §5.5: rota COBERTA pelo mapa de query mínima nunca mais aceita
            # 422 em silêncio — se a query do mapa deixou de validar, o mapa
            # envelheceu (parâmetro renomeado/novo obrigatório) e precisa ser
            # atualizado; tratar como inconclusivo esconderia a regressão.
            ok = False
            detail = (
                f"QUERY MÍNIMA DESATUALIZADA: GET {gate.path} respondeu 422 MESMO "
                f"com a query mínima do mapa ({url.split('?', 1)[1] if '?' in url else ''}) — "
                "atualize rbac_matrix.QUERY_MINIMA_POR_ROTA para os parâmetros "
                "atuais da rota; 422 não é aceito para rotas cobertas pelo mapa "
                f"(esperado sem a validação de query: {esperado})."
            )
        elif status in DEGRADADOS:
            # Rota ausente/indisponível NESTE ambiente — não é achado de RBAC
            # (mesma semântica de DEGRADADOS no resto da suíte).
            ok, degraded = (not STRICT), True
            detail = (f"DEGRADADO: {status} (rota ausente/indisponível neste ambiente) — "
                      f"esperado={esperado}" + ("" if STRICT else " (tolerado: EJC_E2E_STRICT=false)"))
        elif esperado == 403 and status == 200:
            # É ISTO que a Issue #700 pede: célula "negado" respondendo 200
            # reprova a execução, nomeando papel e rota.
            ok = False
            detail = (
                f"GATE RBAC FROUXO: papel '{role_key}' (token com role='{actual_role}') "
                f"deveria ser NEGADO (403) em GET {gate.path} — gate={gate.gate_kind}, "
                f"min_level exigido={gate.min_level} ({gate.source_file}:{gate.source_line}) — "
                f"mas a API respondeu 200. Ver Issue #694 para o padrão desta classe de defeito."
            )
        elif esperado == 200 and status == 403:
            ok = False
            detail = (
                f"DIVERGÊNCIA: papel '{role_key}' (role='{actual_role}') deveria ser "
                f"PERMITIDO (200) em GET {gate.path} — obteve 403. Ou o gate está mais "
                "restritivo do que o código sugere, ou a matriz derivada está errada "
                "para esta rota; investigar antes de ignorar."
            )
        elif status == 422 and esperado == 403 and gate.via_depends:
            # Achado #3 do review do PR #708: quando o gate é resolvido via
            # `Depends(...)` (de assinatura OU de `dependencies=[...]` do
            # router — `gate.via_depends`), o FastAPI resolve TODA
            # sub-dependência ANTES de validar os parâmetros (path/query) da
            # PRÓPRIA rota — um papel NEGADO deveria ter recebido 403 já
            # nessa fase, sem nunca alcançar a validação de query. Um 422
            # aqui não é "faltou o parâmetro para o gate rodar": é a
            # validação de query tendo sido ALCANÇADA porque o gate deixou
            # o papel passar — exatamente o bypass que a Issue #694
            # documenta, só que mascarado atrás de um 422 em vez de um 200.
            # Tratar isto como inconclusivo esconderia a regressão.
            ok = False
            detail = (
                f"GATE RBAC FROUXO (via 422): papel '{role_key}' (token com role="
                f"'{actual_role}') deveria ser NEGADO (403) em GET {gate.path} — "
                f"gate={gate.gate_kind} roda via Depends() (resolvido ANTES da "
                f"validação de query), min_level exigido={gate.min_level} "
                f"({gate.source_file}:{gate.source_line}) — mas a API respondeu 422 "
                "(chegou a validar query, o que só acontece se o gate deixou passar). "
                "Ver Issue #694 para o padrão desta classe de defeito."
            )
        elif status == 422:
            # Limitação CONHECIDA e documentada: um GET com query param
            # OBRIGATÓRIO responde 422 ANTES do gate rodar — mas só
            # quando o gate é verificado no CORPO do handler (requer_advogado /
            # local_level / local_membership / "nenhum", ou seja
            # `gate.via_depends is False`): o FastAPI resolve e valida
            # path/query params, e só ENTÃO executa o corpo — se faltar um
            # param obrigatório, o handler nunca roda, e o `if papel ...:
            # raise 403` dentro dele nunca é alcançado (para NENHUM papel,
            # permitido ou negado). Evidência real: em `/api/calculadoras/inss`
            # (gate por `Depends(require_roles(_EQUIPE))`, avaliado ANTES da
            # validação de query) um papel negado recebeu 403 mesmo sem os
            # params — mas em rotas com gate NO CORPO, a mesma ausência de
            # params produz 422 tanto para papéis permitidos quanto negados,
            # sem nunca provar nada sobre RBAC. Fica inconclusivo (não
            # reprova), nunca desaparece do relatório (degraded=True). Quando
            # `esperado == 403` e `gate.via_depends` é True, o ramo ACIMA já
            # tratou o caso como falha real, não chega aqui. Rota coberta por
            # QUERY_MINIMA_POR_ROTA (§5.5) também nunca chega aqui: o ramo do
            # mapa reprova o 422 em vez de aceitá-lo como inconclusivo.
            ok, degraded = True, True
            detail = (f"422 (validação de query — rota provavelmente exige parâmetros "
                      f"que esta sonda não envia): inconclusivo para RBAC, gate={gate.gate_kind} "
                      f"(esperado sem considerar a validação: {esperado})")
        else:
            ok = False
            detail = f"status inesperado: esperado={esperado}, obtido={status}"

        celulas.append({
            "papel": role_key, "role_no_token": actual_role, "method": "GET",
            "path": gate.path, "gate_kind": gate.gate_kind, "min_level_exigido": gate.min_level,
            "esperado": esperado, "obtido": status, "ok": ok,
            "query_minima_aplicada": qm is not None,
        })
        _record(state, StepResult(
            name=f"rbac.{role_key}", method="GET", path=gate.path,
            status_code=status, ok=ok, detail=detail, degraded=degraded,
        ))
    return celulas


def _matriz_rbac(base_url: str, state: SuiteState) -> None:
    """Autentica em cada papel disponível e prova, célula a célula, que o
    resultado bate com o gate REAL do backend (critérios de aceite #1-#4)."""
    try:
        gates_todas = rbac_matrix.discover_gates(ROUTERS_DIR)
    except Exception as exc:
        _afirmar(state, "rbac.matriz_derivada", False,
                 f"falha ao derivar a matriz a partir de {ROUTERS_DIR}: {exc}")
        return
    amostra, excluidos = rbac_matrix.selecionar_amostra_get(gates_todas)
    _afirmar(state, "rbac.matriz_derivada_nao_vazia", len(amostra) > 0,
             "nenhuma rota elegível derivada dos routers — matriz RBAC vazia")
    for g in excluidos:
        state.nao_coberto.append({
            "module_key": f"rbac.{g.module_key}", "method": g.method, "path": g.path,
            "motivo": ("parâmetro de path exige id real — fora do escopo desta amostra"
                       if "{" in g.path else
                       "gate com lista de papéis não resolvida estaticamente (indeterminado)"),
        })

    celulas_por_papel: dict[str, list[dict[str, Any]]] = {}
    papeis_faltantes: list[str] = []

    # Papel de gestão: reaproveita o login primário já feito por `_login`,
    # numa sessão httpx isolada (não reusa `client` para não misturar cookies
    # de refresh entre papéis).
    papel_gestao_primario = str(state.user["role"]) if state.user.get("role") else None
    if state.access_token and papel_gestao_primario and _papel_gestao_confere(papel_gestao_primario):
        with httpx.Client(base_url=base_url, follow_redirects=True) as rc:
            celulas_por_papel["gestao(login_primario)"] = _sondar_papel(
                rc, "gestao(login_primario)", state.access_token, papel_gestao_primario,
                amostra, state,
            )
    else:
        papeis_faltantes.append("gestao(login_primario)")
        if not state.access_token or not papel_gestao_primario:
            motivo = "login primário indisponível — matriz não testou o papel de gestão"
        else:
            # Achado #4 do review do PR #708: EJC_TEST_EMAIL autenticou um
            # papel que não é de gestão — testar RBAC com esse token mediria
            # o piso errado sem avisar.
            motivo = (
                f"EJC_TEST_EMAIL autenticou papel '{papel_gestao_primario}', não um papel "
                f"de gestão ({sorted(ROLES_GESTAO)}) — célula NÃO testada"
            )
        _afirmar(state, "rbac.login.gestao.papel_confere", False, motivo)
        state.nao_coberto.append({
            "module_key": "rbac.gestao", "method": "*", "path": "*",
            "motivo": motivo,
        })

    for role_key, email_var, password_var in PAPEIS_MATRIZ:
        email = os.getenv(email_var, "").strip()
        password = os.getenv(password_var, "").strip()
        if not email or not password:
            # Critério de aceite: ausência de conta é cobertura FALTANTE
            # relatada — nunca aprovação silenciosa.
            papeis_faltantes.append(role_key)
            state.nao_coberto.append({
                "module_key": f"rbac.{role_key}", "method": "*", "path": "*",
                "motivo": (f"cobertura RBAC FALTANTE — defina {email_var} e {password_var} "
                           "com credenciais fictícias de homologação para este papel"),
            })
            continue
        with httpx.Client(base_url=base_url, follow_redirects=True) as rc:
            token, actual_role, login_status = _login_papel(rc, email, password)
            _record(state, StepResult(
                name=f"rbac.login.{role_key}", method="POST", path="/api/auth/login",
                status_code=login_status, ok=bool(token),
                detail="" if token else "login falhou para este papel — célula(s) não testadas",
            ))
            if not token:
                papeis_faltantes.append(role_key)
                state.nao_coberto.append({
                    "module_key": f"rbac.{role_key}", "method": "*", "path": "*",
                    "motivo": f"login falhou (status={login_status}) — credencial incorreta/expirada?",
                })
                continue
            if not _papel_confere(role_key, actual_role):
                # Achado #4 do review do PR #708: `email_var` pode apontar
                # para a conta ERRADA (ex.: EJC_TEST_EMAIL_FINANCEIRO
                # autentica um admin) — calcular expectativas com
                # `actual_role` e registrar sob `role_key` reportaria
                # cobertura completa sem nunca ter exercitado o papel pedido.
                # Falha, não registra célula nenhuma sob `role_key`.
                papeis_faltantes.append(role_key)
                motivo = (
                    f"{email_var} autenticou papel '{actual_role}', não '{role_key}' — "
                    "provável credencial apontando para a conta errada; célula NÃO "
                    "testada (nunca contada como cobertura)"
                )
                _afirmar(state, f"rbac.login.{role_key}.papel_confere", False, motivo)
                state.nao_coberto.append({
                    "module_key": f"rbac.{role_key}", "method": "*", "path": "*",
                    "motivo": motivo,
                })
                continue
            celulas_por_papel[role_key] = _sondar_papel(
                rc, role_key, token, actual_role, amostra, state,
            )

    state.rbac_matrix = {
        "papeis_testados": sorted(celulas_por_papel.keys()),
        "papeis_faltantes": sorted(papeis_faltantes),
        "rotas_na_amostra": len(amostra),
        "rotas_excluidas_da_amostra": len(excluidos),
        "celulas": celulas_por_papel,
    }
    print(
        f"[rbac] papéis testados: {sorted(celulas_por_papel.keys())} · "
        f"faltantes: {sorted(papeis_faltantes)} · rotas na amostra: {len(amostra)}"
    )


def _cleanup(client: httpx.Client, state: SuiteState) -> None:
    """Remove (soft-delete) SOMENTE os recursos criados por ESTA execução.
    Idempotente: 404 significa que já não existe — aceitável em reexecução.

    Registro localizado pelo MARCADOR (reexecução após 409/erro) pertence a
    outra execução e NÃO é apagado: o alvo pode ser um staging compartilhado —
    ou, com EJC_ALLOW_PRODUCTION_E2E, a própria produção."""
    # DELETE /api/cases/{id} EXIGE `motivo` (min 5 chars, body ou query) e
    # responde 422 sem ele — routers/cases.py:589. Sem o motivo, o cleanup do
    # caso falhava em toda execução e o caso fictício ficava no ambiente.
    # 4º campo: molde da CONFIRMAÇÃO pós-DELETE. Documents não tem GET por id
    # (405) — a confirmação usa o download, que 404 depois do soft-delete.
    alvos = [
        ("documentos", state.document_id, "/api/documents/{}",
         "/api/documents/{}/download"),
        ("casos", state.case_id, f"/api/cases/{{}}?motivo={MOTIVO_CLEANUP}",
         "/api/cases/{}"),
        ("clientes", state.client_id, "/api/clients/{}", "/api/clients/{}"),
    ]
    for rotulo, ident, molde, molde_confirmacao in alvos:
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
        # RELÊ o recurso: 404 no DELETE era aceito como sucesso, mas ele tanto
        # pode significar "já removido" quanto "rota de DELETE inexistente ou
        # renomeada" — e nesse segundo caso o registro FICA no ambiente enquanto
        # o relatório afirma que foi limpo. A releitura desfaz a ambiguidade.
        verificacao = _request(
            client, state, name=f"{rotulo}.cleanup_confirmado", method="GET",
            path=molde_confirmacao.format(ident).split("?")[0],
            expected=[404, 410], degradado_ok=True,
        )
        if verificacao is not None and verificacao.status_code < 300:
            _afirmar(
                state, f"{rotulo}.cleanup_nao_removeu", False,
                f"o registro {ident} ainda responde {verificacao.status_code} após o "
                "DELETE — resíduo fictício permanece no ambiente",
            )

    # Recursos criados por POSTs da matriz: sem rota de remoção conhecida, o
    # honesto é DECLARAR o resíduo no relatório em vez de omiti-lo.
    for module_key, path, ident in state.extras_criados:
        state.nao_coberto.append({
            "module_key": module_key, "method": "DELETE", "path": path,
            "motivo": f"recurso {ident} criado por POST da matriz — sem rota de "
                      "cleanup dedicada; remover manualmente do staging",
        })
        print(f"[resíduo] {module_key}: {ident} criado e NÃO removido")


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
            "rbac_papeis_testados": len(state.rbac_matrix.get("papeis_testados", [])),
            "rbac_papeis_faltantes": len(state.rbac_matrix.get("papeis_faltantes", [])),
        },
        # Cobertura omitida fica EXPLÍCITA no artefato (AI-005 e, para a
        # matriz por papel, Issue #700 — ausência de conta é FALTANTE, nunca
        # aprovação silenciosa).
        "nao_coberto": state.nao_coberto,
        # Matriz papel x rota (Issue #700). Nunca contém token/senha/e-mail —
        # só papel, método, path e códigos de status.
        "rbac_matrix": state.rbac_matrix,
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
    if state.rbac_matrix:
        print(f"Matriz RBAC — papéis testados: {state.rbac_matrix.get('papeis_testados')}")
        if state.rbac_matrix.get("papeis_faltantes"):
            print(f"  cobertura FALTANTE (sem credencial ou login falhou): "
                  f"{state.rbac_matrix['papeis_faltantes']}")
        gates_frouxos = [r for r in state.results
                         if r.name.startswith("rbac.") and not r.ok and "GATE RBAC FROUXO" in r.detail]
        if gates_frouxos:
            print(f"  GATES FROUXOS DETECTADOS ({len(gates_frouxos)}) — célula negada respondeu 200:")
            for r in gates_frouxos:
                print(f"    - {r.name} {r.method} {r.path} -> {r.status_code}")
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
            try:
                _matriz_rbac(base_url, state)
            except Exception as exc:
                # A matriz RBAC é uma frente NOVA (Issue #700) — um bug nela
                # não pode impedir cleanup/relatório dos fluxos já existentes.
                _afirmar(state, "rbac.matriz_execucao", False,
                         f"matriz RBAC multi-papel abortou com exceção: {exc}")
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
