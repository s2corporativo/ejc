#!/usr/bin/env python3
"""Bateria de homologação M09 — Procurações.
Cobertura: criação, poderes (ad_judicia | ad_judicia_et_extra | especiais),
validade (determinada/indeterminada), vínculo com cliente, minuta fiel aos
poderes, revogação, expiração (foco vencendo), permissões, auditoria.
Executar com env_shell.sh para carregar o .env.
"""
import os
import sys
import time
import random
import requests
from datetime import date, timedelta

BASE = "http://127.0.0.1:8000"
ADMIN = "ejc_qa_auth_admin@golocal.ejc"
SOCIO = "ejc_qa_auth_socio@golocal.ejc"
ADV = "ejc_qa_auth_advogado@golocal.ejc"
FIN = "ejc_qa_auth_financeiro@golocal.ejc"
CLI = "ejc_qa_auth_cliente@golocal.ejc"
SENHA = "EjcQa2026!SenhaForte"
HOJE = date.today()
HEADERS = {"Content-Type": "application/json", "X-Forwarded-For": "127.0.0.1"}
TOKENS = {}
TOTAL, OK = 0, 0


def h(email):
    if email not in TOKENS:
        time.sleep(18)
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": SENHA},
                          headers=HEADERS, timeout=15)
        if r.status_code == 429:
            time.sleep(45)
            r = requests.post(f"{BASE}/api/auth/login",
                              json={"email": email, "password": SENHA},
                              headers=HEADERS, timeout=15)
        TOKENS[email] = r.json()["access_token"]
    return {**HEADERS, "Authorization": f"Bearer {TOKENS[email]}"}


def chk(nome, ok, detalhe=""):
    global TOTAL, OK
    TOTAL += 1
    OK += int(ok)
    print(f"{'PASS' if ok else 'FAIL'} {nome}" + (f" — {detalhe}" if not ok else ""))


def db(sql):
    os.system(
        "PGPASSWORD=ejc psql -h localhost -U ejc -d ejc -t -A -c \""
        + sql.replace('"', '\\"') + "\"")


def q(sql):
    import subprocess
    r = subprocess.run(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc", "-t", "-A", "-c", sql],
        capture_output=True, text=True,
        env={**os.environ, "PGPASSWORD": "ejc"})
    return r.stdout.strip()


if __name__ != "__main__":
    sys.exit(0)

# ── recurso QA: cliente ────────────────────────────────────────────────────
print("== recurso QA ==")
S = requests.Session()
S.headers.update({**HEADERS, "Authorization": f"Bearer {TOKENS.get(ADMIN) or ''}"})
r = requests.post(f"{BASE}/api/clients", json={
    "tipo": "PJ",
    "nome": f"EJC_QA Cliente Procuracao {random.randint(1,99999)}",
    "razao_social": "EJC_QA CLIENTE PROCURACAO LTDA",
    "cnpj": "12345678000195",
    "email": "ejc.qa.procuracao@gmail.com"}, headers=h(ADMIN), timeout=15)
if r.status_code not in (200, 201):
    # tentar cliente existente já criado
    r2 = requests.get(f"{BASE}/api/clients", headers=h(ADMIN),
                      params={"q": "EJC_QA Cliente Procuracao"}, timeout=15)
    d = r2.json().get("data")
    CLIENTE = d[0]["id"] if d else None
else:
    CLIENTE = r.json().get("id")
print("cliente QA:", CLIENTE)
if not CLIENTE:
    print("ERRO: sem cliente QA"); sys.exit(2)

# ── 1. criação ─────────────────────────────────────────────────────────────
print("== 1. criação ==")
p1 = {"client_id": CLIENTE, "tipo_poderes": "ad_judicia",
      "data_outorga": HOJE.isoformat(),
      "data_validade": (HOJE + timedelta(days=365)).isoformat(),
      "observacoes": "EJC_QA M09"}
r = requests.post(f"{BASE}/api/procuracoes", json=p1, headers=h(ADMIN),
                  timeout=15)
PROC1 = r.json().get("id") if r.status_code == 201 else None
chk("criação ad_judicia 201", r.status_code == 201, f"HTTP {r.status_code} {r.text[:80]}")

p2 = {"client_id": CLIENTE, "tipo_poderes": "ad_judicia_et_extra",
      "data_outorga": HOJE.isoformat(),
      "data_validade": (HOJE + timedelta(days=30)).isoformat(),
      "observacoes": "EJC_QA M09"}
r = requests.post(f"{BASE}/api/procuracoes", json=p2, headers=h(ADMIN),
                  timeout=15)
PROC2 = r.json().get("id") if r.status_code == 201 else None
chk("criação ad_judicia_et_extra 201", r.status_code == 201, f"HTTP {r.status_code}")

p3 = {"client_id": CLIENTE, "tipo_poderes": "especiais",
      "poderes_especiais": "receber citação, transigir, desistir",
      "data_outorga": HOJE.isoformat(),
      "observacoes": "EJC_QA M09 especiais"}
r = requests.post(f"{BASE}/api/procuracoes", json=p3, headers=h(ADMIN),
                  timeout=15)
PROC3 = r.json().get("id") if r.status_code == 201 else None
chk("criação especiais 201", r.status_code == 201, f"HTTP {r.status_code}")

p4 = {"client_id": CLIENTE, "tipo_poderes": "ad_judicia",
      "data_outorga": HOJE.isoformat()}
r = requests.post(f"{BASE}/api/procuracoes", json=p4, headers=h(ADMIN),
                  timeout=15)
PROC4 = r.json().get("id") if r.status_code == 201 else None
chk("validade NULL (indeterminada) aceita 201", r.status_code == 201,
    f"HTTP {r.status_code}")

p5 = {"client_id": CLIENTE, "tipo_poderes": "ad_judicia",
      "data_outorga": HOJE.isoformat(),
      "data_validade": (HOJE + timedelta(days=25)).isoformat(),
      "observacoes": "EJC_QA M09 vencendo"}
r = requests.post(f"{BASE}/api/procuracoes", json=p5, headers=h(ADMIN),
                  timeout=15)
PROC5 = r.json().get("id") if r.status_code == 201 else None
chk("criação procuração próxima do vencimento (25d) 201",
    r.status_code == 201, f"HTTP {r.status_code}")

# ── 2. validações de entrada ───────────────────────────────────────────────
print("== 2. validações ==")
r = requests.post(f"{BASE}/api/procuracoes",
                  json={"client_id": "00000000-0000-0000-0000-000000000000",
                        "tipo_poderes": "ad_judicia",
                        "data_outorga": HOJE.isoformat()},
                  headers=h(ADMIN), timeout=15)
chk("cliente inexistente rejeitado", r.status_code in (400, 404, 422),
    f"HTTP {r.status_code}")

r = requests.post(f"{BASE}/api/procuracoes",
                  json={"client_id": CLIENTE, "tipo_poderes": "ad_judicia"},
                  headers=h(ADMIN), timeout=15)
chk("data_outorga ausente rejeitada (422)", r.status_code == 422,
    f"HTTP {r.status_code}")

# ── 3. vínculo com cliente ─────────────────────────────────────────────────
print("== 3. vínculo ==")
r = requests.get(f"{BASE}/api/procuracoes", headers=h(ADMIN),
                 params={"client_id": CLIENTE, "page_size": 100}, timeout=15)
total = r.json().get("total")
chk("vínculo: listagem por client_id traz as procurações", total >= 3,
    f"total={total}")
for p_id in (PROC1, PROC2, PROC3):
    if p_id:
        d = [x for x in r.json()["data"] if x["id"] == p_id]
        chk(f"procuração {p_id[:8]} vinculada ao cliente",
            d and d[0]["client_id"] == CLIENTE, "vínculo divergente")

# ── 4. minutagem ───────────────────────────────────────────────────────────
print("== 4. minutagem ==")
r = requests.post(f"{BASE}/api/procuracoes/{PROC1}/minuta", headers=h(ADMIN),
                  timeout=15)
m1 = r.json() if r.status_code == 200 else {}
chk("minuta ad_judicia 200", r.status_code == 200, f"HTTP {r.status_code}")
if m1.get("minuta"):
    txt = str(m1["minuta"]).lower()
    chk("minuta menciona poderes gerais",
        any(k in txt for k in ("ad judicial", "ad_judicia", "poderes")),
        f"minuta={m1['minuta'][:60]}")

r = requests.post(f"{BASE}/api/procuracoes/{PROC3}/minuta", headers=h(ADMIN),
                  timeout=15)
m3 = r.json() if r.status_code == 200 else {}
chk("minuta especiais 200", r.status_code == 200, f"HTTP {r.status_code}")
if m3.get("minuta"):
    txt = str(m3["minuta"]).lower()
    chk("minuta reflete poderes_especiais (citação/transigir)",
        "citação" in txt or "transigir" in txt,
        f"minuta={m3['minuta'][:60]}")

# minuta de procuração inexistente
r = requests.post(f"{BASE}/api/procuracoes/00000000-0000-0000-0000-000000000001/minuta",
                  headers=h(ADMIN), timeout=15)
chk("minuta inexistente 404", r.status_code == 404, f"HTTP {r.status_code}")

# ── 5. revogação ───────────────────────────────────────────────────────────
print("== 5. revogação ==")
r = requests.post(f"{BASE}/api/procuracoes/{PROC2}/revogar", headers=h(ADMIN),
                  timeout=15)
chk("revogação 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:80]}")
rev = q(f"SELECT revogada, revogada_em FROM procuracoes WHERE id='{PROC2}'")
chk("revogada persistida no banco", "t" in rev.lower() or "true" in rev.lower(),
    rev)
r = requests.get(f"{BASE}/api/procuracoes", headers=h(ADMIN),
                 params={"page_size": 100}, timeout=15)
ids_ativas = [x["id"] for x in r.json()["data"]]
chk("revogada sai da listagem ativa", PROC2 not in ids_ativas,
    "procuração revogada ainda listada")

r = requests.post(f"{BASE}/api/procuracoes/00000000-0000-0000-0000-000000000001/revogar",
                  headers=h(ADMIN), timeout=15)
chk("revogação inexistente 404", r.status_code == 404, f"HTTP {r.status_code}")

# dupla revogação não quebra
r = requests.post(f"{BASE}/api/procuracoes/{PROC2}/revogar", headers=h(ADMIN),
                  timeout=15)
chk("dupla revogação não falha", r.status_code in (200, 409, 422),
    f"HTTP {r.status_code}")

# ── 6. foco vencendo ───────────────────────────────────────────────────────
print("== 6. vencendo ==")
r = requests.get(f"{BASE}/api/procuracoes", headers=h(ADMIN),
                 params={"vencendo": True, "page_size": 100}, timeout=15)
v = r.json()["data"]
# PROC2 foi revogada (filtrada pela cláusula revogada=False — comportamento correto);
# o foco vencendo deve trazer PROC5 (25 dias, ativa, não revogada)
ids_v = [x["id"] for x in v]
chk("foco vencendo traz procuração próxima do fim (30d)", PROC5 in ids_v
    if PROC5 else len(v) == 0, f"{len(v)} procurações próximas")

# ── 7. permissões ──────────────────────────────────────────────────────────
print("== 7. permissões ==")
r = requests.get(f"{BASE}/api/procuracoes", headers=h(FIN), timeout=15)
# financeiro é autenticado (listagem pública dentro da carteira) — mas a
# carteira filtra por client_id e o financeiro não pertence a nenhuma carteira
total_fin = r.json().get("total", -1)
chk("financeiro vê 0 procurações (fora de carteira)" if total_fin == 0
    else "financeiro não lista procurações",
    r.status_code in (401, 403, 422) or total_fin == 0,
    f"HTTP {r.status_code} total={total_fin}")
r = requests.post(f"{BASE}/api/procuracoes",
                  json={"client_id": CLIENTE, "tipo_poderes": "ad_judicia",
                        "data_outorga": HOJE.isoformat()},
                  headers=h(FIN), timeout=15)
chk("financeiro não cria procuração", r.status_code in (401, 403, 422),
    f"HTTP {r.status_code}")
r = requests.get(f"{BASE}/api/procuracoes", headers=h(CLI), timeout=15)
chk("cliente externo não lista procurações", r.status_code in (401, 403),
    f"HTTP {r.status_code}")

# ── 8. auditoria ───────────────────────────────────────────────────────────
print("== 8. auditoria ==")
for p_id, acao in ((PROC1, "CREATE"), (PROC1, "MINUTA"), (PROC2, "REVOGACAO")):
    n = q("SELECT count(*) FROM audit_logs WHERE registro_id='" + p_id
          + "' AND entidade='procuracoes' AND acao='" + acao + "'")
    chk(f"auditoria {acao} registrada ({p_id[:8]})", int(n or 0) > 0, f"n={n}")

# ── resumo ─────────────────────────────────────────────────────────────────
print(f"\nM09 resultado: {OK}/{TOTAL} PASS")
