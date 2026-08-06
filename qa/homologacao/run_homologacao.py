#!/usr/bin/env python3
"""Executor rigoroso da homologação H01–H15 do EJC.

Modos:

1. Validação estrutural, sem rede::

    python qa/homologacao/run_homologacao.py --validate

2. Execução HTTP real contra homologação/localhost::

    EJC_BASE_URL="http://localhost:8000" \
    EJC_TEST_EMAIL="admin@example.com" EJC_TEST_PASSWORD="senha" \
    EJC_PORTAL_EMAIL="cliente@example.com" EJC_PORTAL_PASSWORD="senha" \
    EJC_HAS_AI=true \
    python qa/homologacao/run_homologacao.py

O relatório não persiste tokens, credenciais, corpos de resposta nem payloads com
PII. Fixtures são fictícias, válidas e únicas por execução.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

MATRIX_PATH = Path(__file__).resolve().parent / "matriz_homologacao.json"
REPORT_DIR = Path(__file__).resolve().parent / "reports"
REPORT_PATH = REPORT_DIR / "homologacao_report.json"

PASS, FALHA, BLOQUEADO = "PASS", "FALHA", "BLOQUEADO"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _commit_sha() -> str:
    """SHA-1 completo do commit sob homologação — vincula o relatório H01–H15
    a um código exato, não a "o que estiver no branch quando alguém rodar".

    `EJC_HOMOLOGACAO_COMMIT_SHA` permite declarar o SHA quando o executor roda
    fora do checkout git da release (ex.: contra ambiente remoto já implantado,
    a partir de uma máquina com histórico git diferente). Sem a variável, exige
    `git rev-parse HEAD` do próprio checkout — é o caso do workflow de CI, que
    sempre roda com o SHA exato do evento como HEAD.
    """
    forced = os.getenv("EJC_HOMOLOGACAO_COMMIT_SHA", "").strip()
    if forced:
        sha = forced
    else:
        try:
            sha = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=Path(__file__).resolve().parent,
                capture_output=True,
                text=True,
                check=True,
                timeout=10,
            ).stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError, OSError) as exc:
            raise SystemExit(
                "Não foi possível determinar o commit_sha do relatório "
                f"(git rev-parse HEAD falhou: {exc}). Rode a partir de um "
                "checkout git válido ou declare EJC_HOMOLOGACAO_COMMIT_SHA."
            ) from exc
    if not _SHA_RE.fullmatch(sha):
        raise SystemExit(
            f"commit_sha inválido: {sha!r} — precisa ser SHA-1 completo (40 "
            "hex, minúsculo). O certificador (certificar_release.py) recusa "
            "qualquer outro formato."
        )
    return sha


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


_CHAVES_CENARIO = {"id", "titulo", "dimensao", "passos"}
_CHAVES_PASSO = {"nome", "tipo", "actor", "method", "path", "expected", "requires"}
_ESPERADO_IDS = [f"H{n:02d}" for n in range(1, 16)]
_ACTORS = {"anon", "staff", "portal"}
_TIPOS = {"happy", "negativo", "idempotencia", "resiliencia"}
_CAPS = {"stack", "ai", "portal", "ops"}


def carregar_matriz() -> dict[str, Any]:
    return json.loads(MATRIX_PATH.read_text(encoding="utf-8"))


def validar_matriz(matrix: dict[str, Any]) -> list[str]:
    """Retorna erros estruturais e semânticos; lista vazia significa íntegra."""
    erros: list[str] = []
    cenarios = matrix.get("cenarios", [])
    ids = [cenario.get("id") for cenario in cenarios]
    if ids != _ESPERADO_IDS:
        erros.append(f"IDs devem ser exatamente H01..H15 em ordem; obtido: {ids}")

    for cenario in cenarios:
        cid = cenario.get("id")
        faltando = _CHAVES_CENARIO - set(cenario)
        if faltando:
            erros.append(f"{cid}: faltam chaves {sorted(faltando)}")
        passos = cenario.get("passos", [])
        if not passos and not cenario.get("manual"):
            erros.append(f"{cid}: sem passos e sem nota manual")

        tem_negativo = False
        for passo in passos:
            nome = passo.get("nome")
            faltando_p = _CHAVES_PASSO - set(passo)
            if faltando_p:
                erros.append(f"{cid}/{nome}: faltam {sorted(faltando_p)}")
                continue
            tipo = passo["tipo"]
            if tipo not in _TIPOS:
                erros.append(f"{cid}/{nome}: tipo inválido {tipo!r}")
            if passo["actor"] not in _ACTORS:
                erros.append(f"{cid}/{nome}: actor inválido {passo['actor']!r}")
            caps = set(passo.get("requires", []))
            if not caps <= _CAPS:
                erros.append(f"{cid}/{nome}: requires inválido {sorted(caps - _CAPS)}")
            expected = passo.get("expected")
            if not isinstance(expected, list) or not expected:
                erros.append(f"{cid}/{nome}: expected deve ser lista não-vazia")
                continue
            if not all(isinstance(code, int) and 100 <= code <= 599 for code in expected):
                erros.append(f"{cid}/{nome}: status HTTP inválido em expected")
            if tipo == "happy" and any(code < 200 or code >= 300 for code in expected):
                erros.append(
                    f"{cid}/{nome}: happy path só pode aceitar 2xx; obtido {expected}"
                )
            if tipo == "negativo":
                tem_negativo = True
                if any(200 <= code < 300 for code in expected):
                    erros.append(f"{cid}/{nome}: teste negativo não pode aceitar 2xx")
            if tipo == "idempotencia" and 201 in expected:
                erros.append(
                    f"{cid}/{nome}: segunda execução não pode aceitar novo 201"
                )

        if passos and not tem_negativo:
            erros.append(f"{cid}: nenhum passo de acesso negativo declarado")
    return erros


def imprimir_plano(matrix: dict[str, Any]) -> None:
    print(f"\n{matrix['suite']}  v{matrix['version']}")
    print("=" * 78)
    for cenario in matrix["cenarios"]:
        passos = cenario.get("passos", [])
        negativos = sum(1 for passo in passos if passo["tipo"] == "negativo")
        especiais = sum(
            1
            for passo in passos
            if passo["tipo"] in ("idempotencia", "resiliencia")
        )
        caps = sorted(
            {cap for passo in passos for cap in passo.get("requires", [])}
        ) or cenario.get("requisitos", [])
        print(
            f"  {cenario['id']}  {cenario['titulo']:<38} "
            f"passos={len(passos):>2} neg={negativos} idem/resil={especiais} "
            f"caps={','.join(caps) or '—'}"
        )
    print("=" * 78)
    print(
        f"  Total: {len(matrix['cenarios'])} cenários "
        "(H13/H14 são operacionais e exigem runbook).\n"
    )


def _cpf_com_dv(base: int) -> str:
    nove = f"{base % 1_000_000_000:09d}"
    if len(set(nove)) == 1:
        nove = "123456789"
    numeros = [int(char) for char in nove]
    soma = sum(valor * peso for valor, peso in zip(numeros, range(10, 1, -1)))
    primeiro = (soma * 10 % 11) % 10
    numeros.append(primeiro)
    soma = sum(valor * peso for valor, peso in zip(numeros, range(11, 1, -1)))
    segundo = (soma * 10 % 11) % 10
    return nove + str(primeiro) + str(segundo)


def preparar_fixtures(matrix: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Clona e torna fixtures únicas sem alterar a matriz versionada."""
    prepared = copy.deepcopy(matrix)
    suffix = str(time.time_ns())[-12:]
    marker = f"HOMOLOG-FICTICIO-{suffix}"

    cliente = prepared["fixtures"]["cliente_pf"]
    cliente.update(
        {
            "nome": f"{marker} João da Silva Teste",
            "cpf": _cpf_com_dv(int(suffix)),
            "email": f"homolog.{suffix}@example.test",
            "telefone": f"319{suffix[-8:]}",
            "observacoes": f"Cliente fictício da rodada {marker}.",
        }
    )

    caso = prepared["fixtures"]["caso_manual"]
    caso.update(
        {
            "titulo": f"{marker} Ação de cobrança manual",
            "numero_processo": f"HML-{suffix}",
            "descricao_fatos": f"Caso fictício da rodada {marker}.",
        }
    )

    documento = prepared["fixtures"]["documento_texto"]
    documento.update(
        {
            "titulo": f"{marker} Relato",
            "filename": f"homolog-relato-{suffix}.txt",
            "content": f"{marker}. Relato inteiramente fictício para homologação.",
        }
    )
    return prepared, marker


def _env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise SystemExit(f"Variável obrigatória ausente: {name}")
    return value


def _base_url_segura(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        raise SystemExit("EJC_BASE_URL não pode conter credenciais na URL")
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("EJC_BASE_URL inválida")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")


class Executor:
    def __init__(self, base_url: str, marker: str):
        import httpx

        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(
            base_url=self.base_url,
            follow_redirects=True,
            timeout=60,
        )
        self.tokens: dict[str, str | None] = {"anon": None}
        self.caps: set[str] = set()
        self.state: dict[str, Any] = {}
        self.marker = marker

    def detectar_capacidades(self) -> None:
        try:
            response = self.client.post(
                "/api/auth/login",
                json={
                    "email": _env("EJC_TEST_EMAIL"),
                    "password": _env("EJC_TEST_PASSWORD"),
                },
            )
            if response.status_code == 200:
                self.tokens["staff"] = response.json().get("access_token")
                self.caps.add("stack")
        except Exception as exc:  # noqa: BLE001
            print(f"[stack] indisponível: {type(exc).__name__}")

        portal_email = os.getenv("EJC_PORTAL_EMAIL")
        portal_password = os.getenv("EJC_PORTAL_PASSWORD")
        if portal_email and portal_password and "stack" in self.caps:
            response = self.client.post(
                "/api/auth/login",
                json={"email": portal_email, "password": portal_password},
            )
            if response.status_code == 200:
                self.tokens["portal"] = response.json().get("access_token")
                self.caps.add("portal")
        if os.getenv("EJC_HAS_AI", "").lower() == "true":
            self.caps.add("ai")

    def _headers(self, actor: str) -> dict[str, str]:
        token = self.tokens.get(actor)
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _garantir_cliente(self, matrix: dict[str, Any]) -> str | None:
        if self.state.get("client_id"):
            return self.state["client_id"]
        payload = matrix["fixtures"]["cliente_pf"]
        response = self.client.post(
            "/api/clients/",
            headers=self._headers("staff"),
            json=payload,
        )
        if response.status_code == 201:
            self.state["client_id"] = response.json().get("id")
        else:
            listing = self.client.get(
                f"/api/clients/?search={self.marker}",
                headers=self._headers("staff"),
            )
            if listing.status_code == 200:
                rows = listing.json().get("data") or []
                if rows:
                    self.state["client_id"] = rows[0].get("id")
        return self.state.get("client_id")

    def executar_passo(
        self,
        passo: dict[str, Any],
        matrix: dict[str, Any],
    ) -> PassoResult:
        result = PassoResult(
            nome=passo["nome"],
            tipo=passo["tipo"],
            actor=passo["actor"],
            method=passo["method"],
            path=passo["path"],
            expected=passo["expected"],
        )
        faltando = set(passo.get("requires", [])) - self.caps
        if faltando:
            result.detail = f"capacidade ausente: {','.join(sorted(faltando))}"
            return result

        path = passo["path"]
        json_body = None
        files = None
        form_data = None
        if passo.get("body_ref"):
            json_body = copy.deepcopy(matrix["fixtures"][passo["body_ref"]])
        elif passo.get("body"):
            json_body = copy.deepcopy(passo["body"])
        if passo.get("needs_client"):
            client_id = self._garantir_cliente(matrix)
            if json_body is not None and client_id:
                json_body["client_id"] = client_id
        if passo.get("upload_ref"):
            document = matrix["fixtures"][passo["upload_ref"]]
            files = {
                "file": (
                    document["filename"],
                    document["content"].encode("utf-8"),
                    document["content_type"],
                )
            }
            form_data = {
                "titulo": document["titulo"],
                "tipo": "prova",
                "confidencialidade": "normal",
            }
            if self.state.get("case_id"):
                form_data["case_id"] = self.state["case_id"]

        placeholders = {
            "{document_id}": self.state.get("document_id"),
            "{case_id}": self.state.get("case_id"),
            "{client_id}": self.state.get("client_id"),
        }
        for placeholder, value in placeholders.items():
            if placeholder in path:
                if not value:
                    result.detail = f"sem {placeholder[1:-1]} de passo anterior"
                    return result
                path = path.replace(placeholder, str(value))

        try:
            started = time.perf_counter()
            response = self.client.request(
                passo["method"],
                path,
                headers=self._headers(passo["actor"]),
                json=json_body,
                files=files,
                data=form_data,
            )
            result.elapsed_ms = int((time.perf_counter() - started) * 1000)
            result.status_code = response.status_code
            ok = response.status_code in passo["expected"]
            max_ms = passo.get("max_ms")
            if ok and max_ms and result.elapsed_ms > max_ms:
                ok = False
                result.detail = f"lento: {result.elapsed_ms}ms > {max_ms}ms"
            result.status = PASS if ok else FALHA
            if not ok and not result.detail:
                result.detail = (
                    f"esperado {passo['expected']}, obtido {response.status_code}"
                )

            if ok and response.status_code in (200, 201):
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        if passo.get("upload_ref") and body.get("id"):
                            self.state["document_id"] = body["id"]
                        if passo["path"] == "/api/clients/" and body.get("id"):
                            self.state["client_id"] = body["id"]
                        if passo["path"] == "/api/cases/" and body.get("id"):
                            self.state["case_id"] = body["id"]
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            result.status = FALHA
            result.detail = f"erro de rede: {type(exc).__name__}"
        return result

    def executar(self, matrix: dict[str, Any]) -> list[CenarioResult]:
        resultados: list[CenarioResult] = []
        for cenario in matrix["cenarios"]:
            resultado = CenarioResult(
                id=cenario["id"],
                titulo=cenario["titulo"],
                dimensao=cenario.get("dimensao", ""),
                manual=cenario.get("manual", ""),
            )
            resultado.passos = [
                self.executar_passo(passo, matrix)
                for passo in cenario.get("passos", [])
            ]
            executaveis = [
                passo for passo in resultado.passos if passo.status != BLOQUEADO
            ]
            capacidades_ausentes = (
                set(cenario.get("requisitos", [])) - self.caps
            )
            if capacidades_ausentes or not resultado.passos or not executaveis:
                resultado.status = BLOQUEADO
            elif any(passo.status == FALHA for passo in executaveis):
                resultado.status = FALHA
            elif any(passo.status == BLOQUEADO for passo in resultado.passos):
                resultado.status = BLOQUEADO
            else:
                resultado.status = PASS
            resultados.append(resultado)
        return resultados


def _imprimir_resultados(resultados: list[CenarioResult]) -> None:
    icon = {PASS: "PASS ", FALHA: "FALHA", BLOQUEADO: "BLOQ "}
    print("\nResultado por cenário")
    print("-" * 78)
    for cenario in resultados:
        print(f"  [{icon[cenario.status]}] {cenario.id}  {cenario.titulo}")
        for passo in cenario.passos:
            extra = f" ({passo.detail})" if passo.detail else ""
            code = passo.status_code if passo.status_code is not None else "—"
            print(
                f"        [{icon[passo.status]}] {passo.tipo:<12} "
                f"{passo.actor:<6} {passo.method} {passo.path} -> {code}{extra}"
            )
    print("-" * 78)


def _escrever_report(
    base_url: str,
    marker: str,
    resultados: list[CenarioResult],
) -> int:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    resumo = {
        status: sum(1 for resultado in resultados if resultado.status == status)
        for status in (PASS, FALHA, BLOQUEADO)
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit_sha": _commit_sha(),
        "base_url": base_url,
        "run_marker": marker,
        "resumo": resumo,
        "cenarios": [
            {
                **{key: value for key, value in asdict(cenario).items() if key != "passos"},
                "passos": [asdict(passo) for passo in cenario.passos],
            }
            for cenario in resultados
        ],
    }
    REPORT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nResumo: {resumo}  →  {REPORT_PATH}")
    return 2 if resumo[FALHA] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Homologação H01–H15 do EJC")
    parser.add_argument(
        "--validate",
        action="store_true",
        help="valida a matriz e imprime o plano, sem rede",
    )
    args = parser.parse_args()
    matrix = carregar_matriz()

    erros = validar_matriz(matrix)
    if args.validate:
        imprimir_plano(matrix)
        if erros:
            print("MATRIZ INVÁLIDA:")
            for erro in erros:
                print(f"  - {erro}")
            raise SystemExit(1)
        print("Matriz H01–H15 íntegra e semanticamente rigorosa.")
        raise SystemExit(0)
    if erros:
        raise SystemExit("Matriz inválida; execute --validate para detalhes")

    base_url = _base_url_segura(_env("EJC_BASE_URL"))
    if os.getenv("EJC_ALLOW_PRODUCTION_E2E") != "true" and not any(
        marker in base_url
        for marker in ("staging", "homolog", "localhost", "127.0.0.1")
    ):
        raise SystemExit(
            "Proteção ativa: use staging/homologação/localhost ou "
            "EJC_ALLOW_PRODUCTION_E2E=true com autorização explícita."
        )

    runtime_matrix, marker = preparar_fixtures(matrix)
    executor = Executor(base_url, marker)
    executor.detectar_capacidades()
    print(f"Capacidades detectadas: {sorted(executor.caps) or ['(nenhuma)']}")
    resultados = executor.executar(runtime_matrix)
    _imprimir_resultados(resultados)
    raise SystemExit(_escrever_report(base_url, marker, resultados))


if __name__ == "__main__":
    main()
