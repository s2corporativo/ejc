import requests, json
BASE = "http://localhost:8000"
PREFIX = "TESTE_EJC_AUDITORIA_2026"
s = requests.Session()
s.headers["Content-Type"] = "application/json"
r = s.post(BASE + "/api/auth/login", json={"email": "admin@seu-dominio.com.br", "password": "TROCAR_POR_SENHA_FORTE_INICIAL"})
tok = r.json()["access_token"]
s.headers["Authorization"] = f"Bearer {tok}"

def sj(resp):
    try:
        return resp.json()
    except Exception:
        return {}

rr = s.get(BASE + "/api/clients/", params={"search": PREFIX})
dd = sj(rr)
print("status:", rr.status_code, "keys:", list(dd.keys()) if isinstance(dd, dict) else type(dd))
items = dd.get("data", dd) if isinstance(dd, dict) else dd
print("items:", len(items) if isinstance(items, list) else "notlist")
if isinstance(items, list):
    for it in items[:5]:
        print(" -", it.get("razao_social"))
        if (it.get("razao_social") or "").startswith(PREFIX):
            print("MATCH id:", it["id"])
