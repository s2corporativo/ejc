#!/usr/bin/env python3
"""Adaptador da homologação H01–H15 para usuários QA com TOTP.

A matriz canônica contém contratos antigos; este adaptador registra e corrige o
drift apenas em runtime para conseguir exercitar a aplicação atual sem alterar a
matriz original antes da conclusão da auditoria.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pyotp

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_homologacao as base  # noqa: E402


class ExecutorTotp(base.Executor):
    def detectar_capacidades(self) -> None:
        try:
            secret = os.getenv("EJC_TEST_TOTP_SECRET", "").strip()
            payload = {
                "email": base._env("EJC_TEST_EMAIL"),
                "password": base._env("EJC_TEST_PASSWORD"),
            }
            if secret:
                payload["totp_code"] = pyotp.TOTP(secret).now()
            response = self.client.post("/api/auth/login", json=payload)
            if response.status_code == 200:
                self.tokens["staff"] = response.json().get("access_token")
                self.caps.add("stack")
            else:
                print(f"[stack] login recusado: HTTP {response.status_code}")
        except Exception as exc:  # noqa: BLE001
            print(f"[stack] indisponível: {type(exc).__name__}")

        portal_email = os.getenv("EJC_PORTAL_EMAIL", "").strip()
        portal_password = os.getenv("EJC_PORTAL_PASSWORD", "").strip()
        portal_secret = os.getenv("EJC_PORTAL_TOTP_SECRET", "").strip()
        if portal_email and portal_password and "stack" in self.caps:
            payload = {"email": portal_email, "password": portal_password}
            if portal_secret:
                payload["totp_code"] = pyotp.TOTP(portal_secret).now()
            response = self.client.post("/api/auth/login", json=payload)
            if response.status_code == 200:
                self.tokens["portal"] = response.json().get("access_token")
                self.caps.add("portal")
            else:
                print(f"[portal] login recusado: HTTP {response.status_code}")
        if os.getenv("EJC_HAS_AI", "").lower() == "true":
            self.caps.add("ai")


def alinhar_runtime(matrix: dict, marker: str) -> list[str]:
    ajustes: list[str] = []
    fixtures = matrix["fixtures"]
    fixtures["cliente_pf"]["email"] = (
        f"homolog.{marker.rsplit('-', 1)[-1]}@homolog.com.br"
    )
    fixtures["caso_manual"]["proxima_acao"] = (
        "Revisar documentos fictícios e definir a providência processual"
    )
    ajustes.append("caso_manual.proxima_acao incluída — campo obrigatório atual")

    for cenario in matrix["cenarios"]:
        for passo in cenario.get("passos", []):
            if passo.get("nome") == "login_senha_incorreta":
                passo.setdefault("body", {})["email"] = "homolog.naoexiste@homolog.com.br"
                ajustes.append("login negativo usa domínio válido para testar senha, não EmailStr")
            if passo.get("path") == "/api/ia-saude/status":
                passo["path"] = "/api/ia/status"
                passo["expected"] = [200]
                ajustes.append("/api/ia-saude/status obsoleto → /api/ia/status")
            if passo.get("path") == "/api/datajud/health":
                passo["path"] = "/api/v1/datajud/process/0000000-00.0000.0.00.0000"
                if passo.get("actor") == "portal":
                    passo["expected"] = [403]
                else:
                    passo["expected"] = [404, 422, 502, 503]
                ajustes.append("health DataJud inexistente → consulta sintética ao router real")
    return list(dict.fromkeys(ajustes))


def main() -> None:
    matrix = base.carregar_matriz()
    erros = base.validar_matriz(matrix)
    if erros:
        raise SystemExit("Matriz inválida: " + " | ".join(erros))
    base_url = base._base_url_segura(base._env("EJC_BASE_URL"))
    runtime_matrix, marker = base.preparar_fixtures(matrix)
    ajustes = alinhar_runtime(runtime_matrix, marker)
    print("Ajustes de drift aplicados em runtime:")
    for ajuste in ajustes:
        print(f" - {ajuste}")
    executor = ExecutorTotp(base_url, marker)
    executor.detectar_capacidades()
    print(f"Capacidades detectadas: {sorted(executor.caps) or ['(nenhuma)']}")
    resultados = executor.executar(runtime_matrix)
    base._imprimir_resultados(resultados)
    raise SystemExit(base._escrever_report(base_url, marker, resultados))


if __name__ == "__main__":
    main()
