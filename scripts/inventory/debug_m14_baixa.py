#!/usr/bin/env python3
"""Probe: resposta real do PATCH baixa (concluido) de um prazo."""
import os
import subprocess

import requests

BASE = "http://127.0.0.1:8000"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
env = dict(os.environ)
env["PGPASSWORD"] = "ejc"


def db(sql):
    o = subprocess.run(["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc",
                        "-t", "-A", "-c", sql], capture_output=True, text=True, env=env)
    return o.stdout.strip().split("\n")[0]


s = requests.Session()
s.headers = {"X-Forwarded-For": "127.0.0.1"}
ADM = {"email": "ejc_qa_auth_admin@golocal.ejc", "senha": SENHA}
ADV = {"email": "ejc_qa_auth_advogado@golocal.ejc", "senha": SENHA}


# Criar caso QA com admin para garantir carteira acessível pelo advogado
r = s.post(f"{BASE}/api/auth/login", json={"email": ADM["email"], "password": SENHA})
adm_h = {"Authorization": f"Bearer {r.json()['access_token']}"}
# Reutilizar o cliente M06 (CPF 12345678909) em vez de criar duplicado.
r = s.get(f"{BASE}/api/clients", headers=adm_h,
          params={"q": "EJC_QA Cliente"}, timeout=15)
print("get clientes:", r.status_code, r.text[:100])
lista = r.json()
data = lista.get("data", lista if isinstance(lista, list) else [])
cli = data[0]["id"] if data else None
print("cliente reutilizado:", cli)
r = s.post(f"{BASE}/api/cases", json={
    "titulo": "EJC_QA probe caso prazo", "case_number": "", "area": "tributario",
    "status": "em_instrucao", "fase": "conhecimento",
    "client_id": cli, "proxima_acao": "EJC_QA probe prazo",
    "responsavel_id": None, "partes": []}, headers=adm_h, timeout=15)
print("caso:", r.status_code, r.text[:80])
cid = r.json().get("id")

r = s.post(f"{BASE}/api/auth/login", json={"email": ADV["email"], "password": SENHA})
print("login adv:", r.status_code)
h = {"Authorization": f"Bearer {r.json()['access_token']}"}
adv_id = db("SELECT id FROM users WHERE email='ejc_qa_auth_advogado@golocal.ejc'")
print("adv:", adv_id[:8] if adv_id else "NENHUM")
r = s.patch(f"{BASE}/api/cases/{cid}", json={"advogado_responsavel_id": adv_id},
            headers=adm_h, timeout=15)
print("atribuir resp:", r.status_code, r.text[:60])

print("case usado:", cid[:8] if cid else "NENHUM")
if not cid:
    raise SystemExit("sem casos QA")

r = s.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA probe baixa", "tipo": "processual",
    "data_prazo": "2026-12-01", "case_id": cid,
}, headers=h, timeout=15)
print("criar:", r.status_code)
j = r.json()
did = j.get("id")
if not did:
    print("RESPOSTA CRIACAO:", j)
    raise SystemExit("sem id")

r = s.patch(f"{BASE}/api/deadlines/{did}", json={"status": "concluido"}, headers=h, timeout=15)
print("baixa:", r.status_code)
c = r.json()
print("CHAVES DA RESPOSTA:", sorted(c.keys()))
print("CAMPOS CONCLUSAO/STATUS:")
for k in c:
    if "conclu" in k or k == "status":
        print(f"  {k} = {c[k]!r}")
