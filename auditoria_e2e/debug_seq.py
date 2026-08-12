import requests, time
BASE = "http://localhost:8000"
PREFIX = "TESTE_EJC_AUDITORIA_2026"

def sj(resp):
    try:
        return resp.json()
    except Exception:
        return {}

s = requests.Session()
s.headers["Content-Type"] = "application/json"
s.headers["Connection"] = "close"
r = s.post(BASE + "/api/auth/login", json={"email": "admin@seu-dominio.com.br", "password": "TROCAR_POR_SENHA_FORTE_INICIAL"})
tok = r.json()["access_token"]
s.headers["Authorization"] = f"Bearer {tok}"

def get(path, **kw):
    return s.get(BASE + path, **kw)

t0 = time.time()
for name, call in [
    ("T01-6", lambda: get("/api/ai/status", timeout=30)),
    ("T01-7", lambda: get("/api/rag/buscar", params={"q": "teste RAG auditoria"}, timeout=30)),
]:
    r = call()
    print(name, r.status_code, str(r.text)[:80], f"{time.time()-t0:.1f}s")

t1 = time.time()
r = get("/api/clients/", params={"search": PREFIX}, timeout=10)
print("find", r.status_code, str(r.text)[:100], f"{time.time()-t1:.2f}s")
