import requests, json
BASE = "http://localhost:8000"
s = requests.Session()
s.headers["Content-Type"] = "application/json"
r = s.post(BASE + "/api/auth/login", json={"email": "admin@seu-dominio.com.br", "password": "TROCAR_POR_SENHA_FORTE_INICIAL"})
tok = r.json()["access_token"]
s.headers["Authorization"] = f"Bearer {tok}"

for path in ["/api/clients/", "/api/clients/?search=TESTE_EJC_AUDITORIA_2026", "/api/cases/", "/api/dashboard"]:
    rr = s.get(BASE + path)
    body = rr.text[:120]
    print(path, "→", rr.status_code, body)
