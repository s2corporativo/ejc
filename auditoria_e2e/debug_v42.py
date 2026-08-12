"""Diagnóstico do ABORT: reproduz o fluxo T04 da bateria."""
import requests
import sys
sys.path.insert(0, "/home/ubuntu/ejc/auditoria_e2e")

# importa o próprio script para reutilizar helpers (get/post/safe_json/restart_if_down/PREFIX)
import importlib.util
spec = importlib.util.spec_from_file_location("suite", "/home/ubuntu/ejc/auditoria_e2e/testes_e2e.py")

BASE = "http://localhost:8000/api"
s = requests.Session()
s.headers["Content-Type"] = "application/json"
s.headers["Connection"] = "close"
r = s.post(BASE + "/auth/login", json={"email": "admin@seu-dominio.com.br", "password": "TROCAR_POR_SENHA_FORTE_INICIAL"})
print("login:", r.status_code)
tok = r.json()["access_token"]
s.headers["Authorization"] = "Bearer " + tok

PREFIX = "TESTE_EJC_AUDITORIA_2026"
r = s.get(BASE + "/clients/", params={"search": PREFIX}, timeout=10)
print("search:", r.status_code, repr(r.text[:200]))
data = r.json() if r.status_code == 200 else {}
print("json:", str(data)[:300])

r = s.post(BASE + "/clients/", json={
    "tipo": "PJ",
    "razao_social": f"{PREFIX} Cliente Alpha Ltda-2",
    "nome_fantasia": f"{PREFIX} Alpha-2",
    "cnpj": "11222333000181",
    "email": f"{PREFIX.lower()}-2@cliente.teste.br",
    "telefone": "31 99999-0001",
    "logradouro": "Rua da Auditoria", "numero": "100", "bairro": "Centro",
    "cidade": "Betim", "estado": "MG", "cep": "32510000",
    "origem": "indicacao", "status": "lead",
}, timeout=15)
print("create:", r.status_code, repr(r.text[:200]))

r = s.get(BASE + "/clients/", params={"search": PREFIX}, timeout=10)
print("search2:", r.status_code, repr(r.text[:200]))
