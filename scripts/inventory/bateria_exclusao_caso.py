# -*- coding: utf-8 -*-
"""Bateria de diagnóstico da exclusão de caso (DELETE /cases/{id}).

Hipóteses a verificar contra o servidor local (uvicorn porta 8000):
  H1: backend recusa body em DELETE (422) quando o frontend envia
      {"motivo": "..."} como JSON body.
  H2: exclusão funciona corretamente.
Rodar com: scripts/inventory/env_shell.sh python3 scripts/inventory/bateria_exclusao_caso.py
"""
import json
import sys
import traceback
import uuid

import requests

BASE = "http://localhost:8000/api/v1"
EMAIL = "ejc_qa_auth_admin@golocal.ejc"
SENHA = "EjcQa2026!SenhaForte"
AREA = "trabalhista"  # valor validado pelo _area_valida do schema

S = requests.Session()


def cpf_valido():
    """Gera CPF válido (dígito verificador correto)."""
    import random
    n = [random.randint(0, 9) for _ in range(9)]
    d1 = sum((10 - i) * v for i, v in enumerate(n)) % 11
    d1 = 0 if d1 < 2 else 11 - d1
    n.append(d1)
    d2 = sum((11 - i) * v for i, v in enumerate(n)) % 11
    d2 = 0 if d2 < 2 else 11 - d2
    n.append(d2)
    return "".join(map(str, n))


def log(msg):
    print(f"[BATERIA] {msg}", flush=True)


def token():
    r = S.post(f"{BASE}/auth/login", json={"email": EMAIL, "password": SENHA})
    if r.status_code != 200:
        raise SystemExit(f"Login falhou {r.status_code}: {r.text[:300]}")
    return r.json()["access_token"]


def main():
    sufixo = uuid.uuid4().hex[:8]
    clientes = []
    try:
        log("login admin")
        S.headers["Authorization"] = f"Bearer {token()}"

        # criar cliente real
        r = S.post(f"{BASE}/clients", json={
            "nome": f"Cliente QA {sufixo}",
            "tipo": "PF",
            "cpf": cpf_valido(),
            "email": f"qa-{sufixo}@golocal.ejc",
        })
        log(f"POST /clients status={r.status_code}")
        if r.status_code not in (200, 201):
            log(f"Body: {r.text[:400]}")
            log("SEM cliente — abortando bateria")
            return
        cid_cli = r.json()["id"]
        clientes.append(cid_cli)

        def criar_caso(titulo):
            return S.post(f"{BASE}/cases", json={
                "titulo": titulo,
                "area": AREA,
                "client_id": cid_cli,
                "proxima_acao": "Aguardando análise inicial",
            })

        log("criar caso de teste")
        r = criar_caso(f"QA_EXCLUSAO_{sufixo}")
        log(f"POST /cases status={r.status_code}")
        if r.status_code not in (200, 201):
            log(f"Body: {r.text[:400]}")
            log("SEM caso criado — abortando bateria")
            return
        cid = r.json()["id"]
        log(f"caso criado id={cid}")

        # H2: exclusão com body JSON (requests=json -> Content-Type application/json)
        r = S.delete(f"{BASE}/cases/{cid}", json={"motivo": "bateria qa exclusao caso"})
        log(f"DELETE body JSON status={r.status_code}")
        log(f"Resposta: {r.text[:400]}")

        # repetição: exclusão com data=bytes (simula axios {data})
        log("criar caso 2")
        r = criar_caso(f"QA_EXCLUSAO2_{sufixo}")
        if r.status_code in (200, 201):
            cid2 = r.json()["id"]
            log(f"caso 2 id={cid2}")
            r = S.delete(f"{BASE}/cases/{cid2}",
                         data=json.dumps({"motivo": "bateria qa exclusao caso"}),
                         headers={"Content-Type": "application/json"})
            log(f"DELETE data bytes status={r.status_code}")
            log(f"Resposta: {r.text[:400]}")
        else:
            log(f"caso 2 nao criado: {r.status_code} {r.text[:300]}")

        # referência: só query string
        log("criar caso 3")
        r = criar_caso(f"QA_EXCLUSAO3_{sufixo}")
        if r.status_code in (200, 201):
            cid3 = r.json()["id"]
            log(f"caso 3 id={cid3}")
            r = S.delete(f"{BASE}/cases/{cid3}",
                         params={"motivo": "bateria qa exclusao caso"})
            log(f"DELETE so query string status={r.status_code}")
            log(f"Resposta: {r.text[:400]}")
        else:
            log(f"caso 3 nao criado: {r.status_code} {r.text[:300]}")
    except Exception:
        traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    main()
