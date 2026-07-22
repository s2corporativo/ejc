#!/usr/bin/env python3
"""Executor da homologação H01–H15 do EJC.

Espelha qa/e2e/run_fictitious_smoke.py (HTTP contra a API real), mas orientado
ao roteiro formal de homologação: lê matriz_homologacao.json e reporta, POR
CENÁRIO, um de três estados:

  • PASS       — todos os passos executáveis passaram;
  • FALHA      — algum passo executável falhou (status fora do esperado);
  • BLOQUEADO  — nenhum passo pôde rodar por falta de capacidade de ambiente
                 (sem stack de pé, sem provedor de IA, sem credencial de portal,
                  ou passo puramente operacional — backup/deploy).

Dois modos:

  # 1) Validação estrutural — SEM rede. Roda em CI, valida a matriz e imprime o
  #    plano H01–H15. Sai 0 se a matriz é íntegra.
  python qa/homologacao/run_homologacao.py --validate

  # 2) Execução real — HTTP contra a API. Exige stack de pé.
  EJC_BASE_URL="http://localhost:8000" \
  EJC_TEST_EMAIL="admin@example.com" EJC_TEST_PASSWORD="senha" \
  EJC_PORTAL_EMAIL="cliente@example.com" EJC_PORTAL_PASSWORD="senha" \
  EJC_HAS_AI=true \
  python qa/homologacao/run_homologacao.py

Saída (modo 2): resumo no terminal + JSON em qa/homologacao/reports/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MATRIX_PATH = Path(__file__).resolve().parent / "matriz_homologacao.json"
REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_PATH = REPORT_DIR / "homologacao_report.json"

PASS, FALHA, BLOQUEADO = "PASS", "FALHA", "BLOQUEADO"


# ── Modelo de resultado ───────────────────────────────────────────────────────


@dataclass
class PassoResult:
    nome: str
    tipo: str
    actor: str
    method: str
    path: str
    status: str = BLOQUEADO
    status_code: int | None = None
    expected: list[int] = field(default_factory=list)
    elapsed_ms: int | None = None
    detail: str = ""


@dataclass
class CenarioResult:
    id: str
    titulo: str
    dimensao: str
    status: str = BLOQUEADO
    passos: list[PassoResult] = field(default_factory=list)
    manual: str = ""


# ── Validação estrutural (sem rede) ───────────────────────────────────────────

_CHAVES_CENARIO = {"id", "titulo", "dimensao", "passos"}
_CHAVES_PASSO = {"nome", "tipo", "actor", "method", "path", "expected", "requires"}
_ESPERADO_IDS = [f"H{n:02d}" for n in range(1, 16)]
_ACTORS = {"anon", "staff", "portal"}
_CAPS = {"stack", "ai", "portal", "ops"}


def carregar_matriz() -> dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def validar_matriz(matrix: dict[str, Any]) -> list[str]:
    """Retorna lista de erros (vazia = íntegra)."""
    erros: list[str] = []
    cenarios = matrix.get("cenarios", [])
    ids = [c.get("id") for c in cenarios]
    if ids != _ESPERADO_IDS:
        erros.append(f"IDs devem ser exatamente H01..H15 em ordem; obtido: {ids}")
    for c in cenarios:
        faltando = _CHAVES_CENARIO - set(c)
        if faltando:
            erros.append(f"{c.get('id')}: faltam chaves {faltando}")
        tem_negativo = False
        tem_passo_ou_manual = bool(c.get("passos")) or bool(c.get("manual"))
        if not tem_passo_ou_manual:
            erros.append(f"{c.get('id')}: sem passos e sem nota manual")
        for p in c.get("passos", []):
            faltando_p = _CHAVES_PASSO - set(p)
            if faltando_p:
                erros.append(f"{c.get('id')}/{p.get('nome')}: faltam {faltando_p}")
                continue
            if p["actor"] not in _ACTORS:
                erros.append(f"{c['id']}/{p['nome']}: actor inválido {p['actor']}")
            caps = set(p.get("requires", []))
            if not caps <= _CAPS:
                erros.append(f"{c['id']}/{p['nome']}: requires inválido {caps - _CAPS}")
            if not isinstance(p.get("expected"), list) or not p["expected"]:
                erros.append(
                    f"{c['id']}/{p['nome']}: expected deve ser lista não-vazia"
                )
            if p["tipo"] == "negativo":
                tem_negativo = True
        # Regra do roteiro: todo cenário com stack tem ao menos um acesso negativo
        # (os puramente operacionais — só nota manual — são exceção).
        if c.get("passos") and not tem_negativo:
            erros.append(f"{c['id']}: nenhum passo de acesso NEGATIVO declarado")
    return erros


def imprimir_plano(matrix: dict[str, Any]) -> None:
    print(f"\n{matrix['suite']}  v{matrix['version']}")
    print("=" * 78)
    for c in matrix["cenarios"]:
        passos = c.get("passos", [])
        neg = sum(1 for p in passos if p["tipo"] == "negativo")
        idem = sum(1 for p in passos if p["tipo"] in ("idempotencia", "resiliencia"))
        caps = sorted({cap for p in passos for cap in p.get("requires", [])}) or c.get(
            "requisitos", []
        )
        print(
            f"  {c['id']}  {c['titulo']:<38} "
            f"passos={len(passos):>2} neg={neg} idem/resil={idem} "
            f"caps={','.join(caps) or '—'}"
        )
    print("=" * 78)
    print(
        f"  Total: {len(matrix['cenarios'])} cenários "
        f"(H13/H14 são operacionais — validação manual por RUNBOOK).\n"
    )


# ── Execução HTTP real ────────────────────────────────────────────────────────


def _env(name: str) -> str:
    v = os.getenv(name, "").strip()
    if not v:
        raise SystemExit(f"Variável obrigatória ausente: {name}")
    return v


class Executor:
    def __init__(self, base_url: str):
        import httpx  # import tardio: --validate não depende de httpx

        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url, follow_redirects=True, timeout=60
        )
        self.tokens: dict[str, str | None] = {"anon": None}
        self.caps: set[str] = set()
        self.state: dict[str, Any] = {}
        self.marker = "HOMOLOG-FICTICIO"

    # -- capacidades / login --
    def detectar_capacidades(self, matrix: dict[str, Any]) -> None:
        # stack: login staff funciona
        try:
            r = self.client.post(
                "/api/auth/login",
                json={
                    "email": _env("EJC_TEST_EMAIL"),
                    "password": _env("EJC_TEST_PASSWORD"),
                },
            )
            if r.status_code == 200:
                self.tokens["staff"] = r.json().get("access_token")
                self.caps.add("stack")
        except Exception as e:  # noqa: BLE001
            print(f"[stack] indisponível: {e}")
        # portal: credenciais opcionais
        pe, pp = os.getenv("EJC_PORTAL_EMAIL"), os.getenv("EJC_PORTAL_PASSWORD")
        if pe and pp and "stack" in self.caps:
            r = self.client.post("/api/auth/login", json={"email": pe, "password": pp})
            if r.status_code == 200:
                self.tokens["portal"] = r.json().get("access_token")
                self.caps.add("portal")
        # ai: sinalizado por env (não presumimos provedor)
        if os.getenv("EJC_HAS_AI", "").lower() == "true":
            self.caps.add("ai")

    def _headers(self, actor: str) -> dict[str, str]:
        tok = self.tokens.get(actor)
        return {"Authorization": f"Bearer {tok}"} if tok else {}

    def _garantir_cliente(self, matrix: dict[str, Any]) -> str | None:
        if self.state.get("client_id"):
            return self.state["client_id"]
        payload = matrix["fixtures"]["cliente_pf"]
        r = self.client.post(
            "/api/clients/", headers=self._headers("staff"), json=payload
        )
        if r.status_code == 201:
            self.state["client_id"] = r.json().get("id")
        else:
            g = self.client.get(
                f"/api/clients/?search={self.marker}", headers=self._headers("staff")
            )
            if g.status_code == 200:
                rows = g.json().get("data") or []
                if rows:
                    self.state["client_id"] = rows[0].get("id")
        return self.state.get("client_id")

    # -- execução de um passo --
    def executar_passo(
        self, passo: dict[str, Any], matrix: dict[str, Any]
    ) -> PassoResult:
        pr = PassoResult(
            nome=passo["nome"],
            tipo=passo["tipo"],
            actor=passo["actor"],
            method=passo["method"],
            path=passo["path"],
            expected=passo["expected"],
        )
        faltando = set(passo.get("requires", [])) - self.caps
        if faltando:
            pr.status = BLOQUEADO
            pr.detail = f"capacidade ausente: {','.join(sorted(faltando))}"
            return pr

        path = passo["path"]
        json_body = None
        files = None
        data = None

        if passo.get("body_ref"):
            json_body = dict(matrix["fixtures"][passo["body_ref"]])
        elif passo.get("body"):
            json_body = dict(passo["body"])
        if passo.get("needs_client"):
            cid = self._garantir_cliente(matrix)
            if json_body is not None and cid:
                json_body["client_id"] = cid
        if passo.get("upload_ref"):
            doc = matrix["fixtures"][passo["upload_ref"]]
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
            }
            if self.state.get("case_id"):
                data["case_id"] = self.state["case_id"]
        if "{document_id}" in path:
            if not self.state.get("document_id"):
                pr.status = BLOQUEADO
                pr.detail = "sem document_id de um upload anterior"
                return pr
            path = path.replace("{document_id}", self.state["document_id"])

        try:
            t0 = time.perf_counter()
            r = self.client.request(
                passo["method"],
                path,
                headers=self._headers(passo["actor"]),
                json=json_body,
                files=files,
                data=data,
            )
            pr.elapsed_ms = int((time.perf_counter() - t0) * 1000)
            pr.status_code = r.status_code
            ok = r.status_code in passo["expected"]
            max_ms = passo.get("max_ms")
            if ok and max_ms and pr.elapsed_ms > max_ms:
                ok = False
                pr.detail = f"lento: {pr.elapsed_ms}ms > {max_ms}ms"
            pr.status = PASS if ok else FALHA
            if not ok and not pr.detail:
                pr.detail = f"esperado {passo['expected']}, obtido {r.status_code}"
            # guarda ids úteis para passos seguintes
            if ok and r.status_code in (200, 201):
                try:
                    body = r.json()
                    if isinstance(body, dict):
                        if passo.get("upload_ref") and body.get("id"):
                            self.state["document_id"] = body["id"]
                        if passo["path"] == "/api/cases/" and body.get("id"):
                            self.state["case_id"] = body["id"]
                except Exception:  # noqa: BLE001
                    pass
        except Exception as e:  # noqa: BLE001
            pr.status = FALHA
            pr.detail = f"erro de rede: {e}"
        return pr

    def executar(self, matrix: dict[str, Any]) -> list[CenarioResult]:
        resultados: list[CenarioResult] = []
        for c in matrix["cenarios"]:
            cr = CenarioResult(
                id=c["id"],
                titulo=c["titulo"],
                dimensao=c.get("dimensao", ""),
                manual=c.get("manual", ""),
            )
            for passo in c.get("passos", []):
                cr.passos.append(self.executar_passo(passo, matrix))
            executaveis = [p for p in cr.passos if p.status != BLOQUEADO]
            if not cr.passos:
                cr.status = BLOQUEADO  # cenário operacional (H13/H14)
            elif not executaveis:
                cr.status = BLOQUEADO
            elif any(p.status == FALHA for p in executaveis):
                cr.status = FALHA
            else:
                cr.status = PASS
            resultados.append(cr)
        return resultados


def _imprimir_resultados(resultados: list[CenarioResult]) -> None:
    icon = {PASS: "PASS ", FALHA: "FALHA", BLOQUEADO: "BLOQ "}
    print("\nResultado por cenário")
    print("-" * 78)
    for cr in resultados:
        print(f"  [{icon[cr.status]}] {cr.id}  {cr.titulo}")
        for p in cr.passos:
            extra = f" ({p.detail})" if p.detail else ""
            code = p.status_code if p.status_code is not None else "—"
            print(
                f"        [{icon[p.status]}] {p.tipo:<12} {p.actor:<6} "
                f"{p.method} {p.path} -> {code}{extra}"
            )
    print("-" * 78)


def _escrever_report(base_url: str, resultados: list[CenarioResult]) -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    resumo = {
        s: sum(1 for r in resultados if r.status == s) for s in (PASS, FALHA, BLOQUEADO)
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "resumo": resumo,
        "cenarios": [
            {
                **{k: v for k, v in asdict(cr).items() if k != "passos"},
                "passos": [asdict(p) for p in cr.passos],
            }
            for cr in resultados
        ],
    }
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nResumo: {resumo}  →  {REPORT_PATH}")
    return 2 if resumo[FALHA] else 0


def main() -> None:
    ap = argparse.ArgumentParser(description="Homologação H01–H15 do EJC")
    ap.add_argument(
        "--validate",
        action="store_true",
        help="valida a matriz e imprime o plano, SEM rede",
    )
    args = ap.parse_args()

    matrix = carregar_matriz()

    if args.validate:
        erros = validar_matriz(matrix)
        imprimir_plano(matrix)
        if erros:
            print("MATRIZ INVÁLIDA:")
            for e in erros:
                print(f"  - {e}")
            sys.exit(1)
        print("Matriz H01–H15 íntegra (estrutura, negativos e capacidades declarados).")
        sys.exit(0)

    base_url = _env("EJC_BASE_URL").rstrip("/")
    if os.getenv("EJC_ALLOW_PRODUCTION_E2E") != "true" and not any(
        s in base_url for s in ("staging", "homolog", "localhost", "127.0.0.1")
    ):
        raise SystemExit(
            "Proteção ativa: use staging/homologação/localhost ou "
            "EJC_ALLOW_PRODUCTION_E2E=true com autorização explícita."
        )

    ex = Executor(base_url)
    ex.detectar_capacidades(matrix)
    print(f"Capacidades detectadas: {sorted(ex.caps) or ['(nenhuma)']}")
    resultados = ex.executar(matrix)
    _imprimir_resultados(resultados)
    sys.exit(_escrever_report(base_url, resultados))


if __name__ == "__main__":
    main()
