"""Probe isolado — advogado aprova snapshot e lê GET /{snapshot_id} (reproduz falha da bateria)."""
import sys, time, requests
sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")

API = "http://127.0.0.1:8000"
CLIENTE_ID = "3d0aaf26-6942-4355-9553-b0dae90e18e4"
ADVOGADO_ID = "4701ecbf-cf9b-422f-b75a-b906814b8213"
PASS = "EjcQa2026!SenhaForte"

def tok(role):
    S = requests.Session()
    time.sleep(16)
    r = S.post(f"{API}/api/auth/login", json={
        "email": f"ejc_qa_auth_{role}@golocal.ejc", "password": PASS}, timeout=30)
    return S, r.json()["access_token"]

S, t = tok("advogado")
S.headers["Authorization"] = f"Bearer {t}"

r = S.post(f"{API}/api/cases", json={
    "titulo": "EJC_QA M28 PROBE GET", "area": "civil", "client_id": CLIENTE_ID,
    "advogado_responsavel_id": ADVOGADO_ID, "descricao_fatos": "probe get",
    "status": "em_instrucao", "fase": "pre_processual", "prioridade": "media",
    "proxima_acao": "x"}, timeout=30)
caso = r.json().get("id") if r.status_code in (200, 201) else None
print("caso:", r.status_code, caso)
if not caso:
    sys.exit(1)

import asyncio
from app.core.database import AsyncSessionLocal
from app.services.case_intelligence_service import criar_snapshot

async def prep():
    async with AsyncSessionLocal() as db:
        snap = await criar_snapshot(
            db, caso, "manual",
            {"area": "civil", "fatos": "f", "teses": {"principal": "t", "secundarias": []},
             "riscos": "", "provas": [], "pedidos": [], "fontes": ["probe"]},
            resumo="probe", ai_log_ids=[], criado_por=None)
        return snap

snap = asyncio.run(prep())
snap_id = snap.id
print("snapshot:", snap_id, "congelado=", snap.congelado)

r = S.post(f"{API}/api/cases/{caso}/inteligencia/{snap_id}/aprovar", timeout=30)
print("aprovar:", r.status_code, r.text[:150])

for role in ("estagiario", "financeiro", "cliente"):
    S2, t2 = tok(role)
    S2.headers["Authorization"] = f"Bearer {t2}"
    r2 = S2.post(f"{API}/api/cases/{caso}/inteligencia/{snap_id}/aprovar", timeout=30)
    print(f"aprovar {role}:", r2.status_code)

S3, t3 = tok("advogado")
S3.headers["Authorization"] = f"Bearer {t3}"
r3 = S3.get(f"{API}/api/cases/{caso}/inteligencia/{snap_id}", timeout=30)
print("GET snapshot:", r3.status_code, r3.text[:200])
r4 = S3.get(f"{API}/api/cases/{caso}/inteligencia", timeout=30)
print("GET inteligencia:", r4.status_code)
