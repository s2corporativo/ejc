#!/usr/bin/env python3
"""Adaptador temporário da homologação H01–H15 para usuário QA com TOTP."""
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


def main() -> None:
    matrix = base.carregar_matriz()
    erros = base.validar_matriz(matrix)
    if erros:
        raise SystemExit("Matriz inválida: " + " | ".join(erros))
    base_url = base._base_url_segura(base._env("EJC_BASE_URL"))
    runtime_matrix, marker = base.preparar_fixtures(matrix)
    # Corrige apenas o domínio sintético reservado do executor antigo; os dados
    # seguem fictícios, mas passam pelo EmailStr real do backend.
    runtime_matrix["fixtures"]["cliente_pf"]["email"] = (
        f"homolog.{marker.rsplit('-', 1)[-1]}@homolog.com.br"
    )
    executor = ExecutorTotp(base_url, marker)
    executor.detectar_capacidades()
    print(f"Capacidades detectadas: {sorted(executor.caps) or ['(nenhuma)']}")
    resultados = executor.executar(runtime_matrix)
    base._imprimir_resultados(resultados)
    raise SystemExit(base._escrever_report(base_url, marker, resultados))


if __name__ == "__main__":
    main()
