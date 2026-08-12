#!/usr/bin/env python3
"""Diagnóstico de criação de caso."""
import requests, json

BASE = "http://localhost:8000/api"
s = requests.Session()
s.headers.update({"Content-Type": "application/json"})
r = s.post(BASE + "/auth/login", json={
    "email": "admin@seu-dominio.com.br",
    "password": "TROCAR_POR_SENHA_FORTE_INICIAL",
})
tok = r.json()["access_token"]
s.headers["Authorization"] = f"Bearer {tok}"

# localizar cliente de teste
r = s.get(BASE + "/clients/", params={"search": "TESTE_EJC_AUDITORIA_2026"})
data = r.json()
items = data.get("data", data) if isinstance(data, dict) else data
print("clientes:", json.dumps(items, default=str)[:400])
cid = None
for it in items:
    if "Alpha Ltda" in (it.get("razao_social") or ""):
        cid = it["id"]; break
if cid is None:
    cid = items[0]["id"]
print("cliente id:", cid)

payload = {
    "titulo": "TESTE_EJC_AUDITORIA_2026 - Caso Administrativo Tributário 01",
    "area": "tributario",
    "client_id": cid,
    "prioridade": "alta",
    "descricao_fatos": "Caso criado pela auditoria E2E 2026.",
}
r = s.post(BASE + "/cases/", json=payload)
print("STATUS:", r.status_code)
print(r.text[:900])
