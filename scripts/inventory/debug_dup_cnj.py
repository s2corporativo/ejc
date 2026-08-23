#!/usr/bin/env python3
"""Reproduz a falha de duplicidade CNJ na bateria M07.
Estratégia: replicar o MESMO fluxo exato da bateria (mesmo CNJ valido,
mesma ordem) e isolar quando o 409 deixa de valer."""
import random, requests, time


def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v


SENHA = _qa_pw('DEBUG')
BASE = "http://127.0.0.1:8000"
S = requests.Session()
S.headers.update({"Content-Type": "application/json", "X-Forwarded-For": "127.0.0.1"})

def cnj_valido():
    n = f"{random.randint(1000000, 9999999)}"
    ano = "2026"
    j, tr, oo = "8", "01", "0001"
    corpo = int(f"{n}{ano}{j}{tr}{oo}00")
    dv = (1 - corpo) % 97
    return f"{n}-{dv:02d}.{ano}.{j}.{tr}.{oo}"

time.sleep(18)
r = S.post(f"{BASE}/api/auth/login",
           json={"email": "ejc_qa_auth_admin@golocal.ejc",
                 "password": SENHA})
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

CLIENT_ID = "9e6cd7cd-148c-49c9-95cb-d61de37fe520"
TIT = f"EJC_QA DupBug Caso {random.randint(10000, 99999)}"
valido = cnj_valido()
print("CNJ:", valido)

r = S.post(f"{BASE}/api/cases", json={
    "titulo": TIT, "area": "tributario", "client_id": CLIENT_ID,
    "numero_processo": valido, "tribunal": "TJ-MG",
    "comarca": "Belo Horizonte", "vara": "2ª Vara Cível",
    "parte_contraria": "EJC_QA Fazenda Exemplo", "valor_causa": 150000,
    "descricao_fatos": "EJC_QA fatos", "proxima_acao": "próxima ação"},
    headers=H, timeout=20)
print("criação:", r.status_code)
caso = r.json().get("id") if r.status_code == 201 else None

# sequência igual à bateria
for url in (f"{BASE}/api/cases/{caso}",):
    S.get(url, headers=H, timeout=15)
S.patch(f"{BASE}/api/cases/{caso}", headers=H, json={
    "status": "em_instrucao", "fase": "conhecimento", "prioridade": "alta",
    "valor_causa": 200000, "kanban_column": "andamento", "kanban_position": 1},
    timeout=20)
S.patch(f"{BASE}/api/cases/{caso}", headers=H,
        json={"fase": "fase_inexistente"}, timeout=15)
S.patch(f"{BASE}/api/cases/{caso}", headers=H,
        json={"advogado_responsavel_id":
              "4701ecbf-cf9b-422f-b75a-b906814b8213"}, timeout=15)
S.get(f"{BASE}/api/cases", headers=H, params={"q": "DupBug Caso"}, timeout=15)
S.get(f"{BASE}/api/cases", headers=H, params={"client_id": CLIENT_ID,
        "area": "tributario"}, timeout=15)
S.get(f"{BASE}/api/cases/stats", headers=H, timeout=15)
S.get(f"{BASE}/api/cases/kanban", headers=H, timeout=15)
S.post(f"{BASE}/api/cases/{caso}/movimentos", headers=H,
       json={"tipo": "despacho", "descricao": "despacho"}, timeout=15)
S.get(f"{BASE}/api/cases/{caso}/movimentos", headers=H, timeout=15)
S.post(f"{BASE}/api/cases/{caso}/arquivar", headers=H, timeout=15)
S.get(f"{BASE}/api/cases", headers=H, params={"arquivo": "arquivados",
        "q": TIT}, timeout=15)
S.get(f"{BASE}/api/cases", headers=H, params={"arquivo": "ativos",
        "q": TIT}, timeout=15)
S.post(f"{BASE}/api/cases/{caso}/desarquivar", headers=H, timeout=15)
# aqui o teste de duplicidade
r2 = S.post(f"{BASE}/api/cases", json={
    "titulo": f"EJC_QA DupBug Duplicado {random.randint(1, 99999)}",
    "area": "tributario", "client_id": CLIENT_ID, "proxima_acao": "EJC_QA",
    "numero_processo": valido}, headers=H, timeout=15)
print("duplicidade:", r2.status_code, r2.text[:140])
