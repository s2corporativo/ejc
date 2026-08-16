#!/usr/bin/env python3
"""Debug: segunda criação de caso na bateria M11."""
import os, time
import requests as S_
import subprocess

BASE = "http://127.0.0.1:8000"
ADM_E = "ejc_qa_auth_admin@golocal.ejc"
PWD = "EjcQa2026!SenhaForte"

def db(sql):
    env = dict(os.environ, PGPASSWORD="ejc")
    out = subprocess.run(["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc",
                          "-t", "-A", "-c", sql], capture_output=True, text=True, env=env)
    return out.stdout.strip()

S = S_.Session()
S.headers.update({"X-Forwarded-For": "127.0.0.1"})

time.sleep(18)
r = S.post(f"{BASE}/api/auth/login", json={"email": ADM_E, "password": PWD}, timeout=10)
print("login:", r.status_code, r.text[:60])
h = {"Authorization": f"Bearer {r.json()['access_token']}"}

# cliente QA
_r = S.get(f"{BASE}/api/clients", headers=h, params={"q": "EJC_QA Cliente M11"}, timeout=30)
print("clientes:", _r.status_code, _r.text[:200])
_cli = (_r.json().get("data") or [None])[0]
print("cliente:", _cli["id"] if _cli else "AUSENTE")

# achar caso A
_r = S.get(f"{BASE}/api/cases", params={"page_size": 100}, timeout=30)
casos = [c for c in (_r.json().get("data") or [])
         if c.get("client_id") == (_cli["id"] if _cli else "") and "EJC_QA M11" in c.get("titulo", "")]
print("casos M11 existentes:", len(casos))
for c in casos:
    print("  -", c["id"][:8], c["titulo"])

if not _cli:
    print("sem cliente — rodar bateria principal primeiro")
    raise SystemExit(1)

time.sleep(18)
r = S.post(f"{BASE}/api/auth/login", json={"email": ADM_E, "password": PWD}, timeout=10)
print("login:", r.status_code, r.text[:60])
h = {"Authorization": f"Bearer {r.json()['access_token']}"}

# segunda criação (mesmo client_id)
payload = {"titulo": "EJC_QA M11 Caso B debug", "area": "tributario",
           "client_id": _cli["id"], "parte_contraria": "EJC_QA",
           "descricao_fatos": "EJC_QA", "proxima_acao": "EJC_QA"}
r = S.post(f"{BASE}/api/cases", headers=h, json=payload, timeout=30)
print("caso B:", r.status_code, r.text[:300])
