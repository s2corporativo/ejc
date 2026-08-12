import requests, json
BASE = "http://localhost:8000/api"
s = requests.Session()
s.headers["Content-Type"] = "application/json"
r = s.post(BASE + "/auth/login", json={"email": "admin@seu-dominio.com.br", "password": "TROCAR_POR_SENHA_FORTE_INICIAL"})
s.headers["Authorization"] = "Bearer " + r.json()["access_token"]
r = s.post(BASE + "/clients/", json={"tipo":"PJ","razao_social":"DUP CHECK","cnpj":"11222333000181","email":"dup@t.br"})
print("re-create same CNPJ:", r.status_code, r.text[:150])
