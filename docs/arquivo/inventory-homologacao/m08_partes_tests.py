#!/usr/bin/env python3
"""Bateria M08 — Partes e Representações (EJC).
Cobre: criação (tipos, CPF/CNPJ, vínculo), edição (PATCH), exclusão endurecida,
duplicidade, permissões, auditoria e consistência da listagem.
Execução: /home/ubuntu/ejc_repo/scripts/inventory/env_shell.sh python3 <script>
"""
from __future__ import annotations
import random, sys, time
import requests

BASE = "http://127.0.0.1:8000"
ADMIN = "ejc_qa_auth_admin@golocal.ejc"
SOCIO = "ejc_qa_auth_socio@golocal.ejc"
ADV = "ejc_qa_auth_advogado@golocal.ejc"
FIN = "ejc_qa_auth_financeiro@golocal.ejc"
CLI = "ejc_qa_auth_cliente@golocal.ejc"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
# CPF válido (módulo 11) e CNPJ válido com dígito
CPF_VALIDO = "12345678909"

def _dv_cpf(base: str) -> str:
    # mesma fórmula do app (app/services/validators_service.validar_cpf):
    # dv = (soma * 10 % 11) % 10, pesos decrescentes (i+1-j)
    result = list(base)
    for i in (9, 10):
        soma = sum(int(result[j]) * ((i + 1) - j) for j in range(i))
        dv = (soma * 10 % 11) % 10
        result.append(str(dv))
    return "".join(result)

CPF_VALIDO_2 = _dv_cpf(f"98765{random.randint(1000,9999)}")

def _dv_cnpj(base: str) -> str:
    # mesma fórmula do app (validar_cnpj): pesos1=[5..2], pesos2=[6]+pesos1,
    # dv = 11 - soma % 11, com dv = 0 quando >= 10
    c = list(base)
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        s = sum(int(c[i]) * pesos[i] for i in range(pos))
        dv = 11 - s % 11
        dv = 0 if dv >= 10 else dv
        c.append(str(dv))
    return "".join(c)

CNPJ_VALIDO = _dv_cnpj(f"112223{random.randint(100000,999999)}")
HEADERS = {"Content-Type": "application/json", "X-Forwarded-For": "127.0.0.1"}
TOKENS = {}
TOTAL, OK = 0, 0

def chk(nome, cond, motivo=""):
    global TOTAL, OK
    TOTAL += 1
    if cond:
        OK += 1
        print(f"PASS {nome}")
    else:
        print(f"FAIL {nome} — {motivo}")

def login(email):
    if email in TOKENS:
        return TOKENS[email]
    time.sleep(18)
    for _ in range(3):
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": SENHA},
                          headers=HEADERS, timeout=15)
        if r.status_code == 429:
            time.sleep(45)
            continue
        r.raise_for_status()
        TOKENS[email] = r.json()["access_token"]
        return TOKENS[email]
    raise SystemExit(f"rate limit em {email}")

def h(email):
    return {**HEADERS, "Authorization": f"Bearer {login(email)}"}

def db(sql):
    import os, subprocess
    env = {**os.environ, "PGPASSWORD": "ejc"}
    return subprocess.run(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc", "-t", "-A", "-c", sql],
        capture_output=True, text=True, env=env).stdout.strip()

def caso_qa():
    """Um caso ativo pertencente ao admin (carteira do cliente QA)."""
    r = requests.get(f"{BASE}/api/cases", headers=h(ADMIN), timeout=15,
                     params={"q": "EJC_QA M07"})
    for c in r.json().get("data", []):
        return c["id"]
    raise SystemExit("sem caso QA ativo")

CASO = caso_qa()
print("caso QA:", CASO)

# ── 1. criação básica ──────────────────────────────────────────────────────
print("== 1. criação ==")
p = {"tipo": "autor", "nome": "EJC_QA Autor M08", "papel_processual": "Parte autora"}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("criação autor 201", r.status_code == 201, f"HTTP {r.status_code} {r.text[:80]}")
AUTOR = r.json().get("id") if r.status_code == 201 else None

p = {"tipo": "reu", "nome": "EJC_QA Réu M08"}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("criação réu 201", r.status_code == 201, f"HTTP {r.status_code}")
REU = r.json().get("id") if r.status_code == 201 else None

p = {"tipo": "terceiro", "nome": "EJC_QA Terceiro M08", "qualificacao": "assistente"}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("criação terceiro 201", r.status_code == 201, f"HTTP {r.status_code}")

p = {"tipo": "advogado", "nome": "EJC_QA Advogado M08", "oab": "OAB/MG 123456"}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("criação advogado 201", r.status_code == 201, f"HTTP {r.status_code}")

p = {"tipo": "procurador", "nome": "EJC_QA Procurador M08",
     "representante_legal": "EJC_QA Autor M08"}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("criação procurador 201", r.status_code == 201, f"HTTP {r.status_code}")

# ── 2. validações PII e tipo ───────────────────────────────────────────────
print("== 2. validações ==")
p = {"tipo": "tipo_inexistente", "nome": "EJC_QA Ruim"}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("tipo inválido rejeitado (422)", r.status_code == 422, f"HTTP {r.status_code}")

p = {"tipo": "reu", "nome": "EJC_QA CPF Ruim", "cpf_cnpj": "11111111111"}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("CPF inválido rejeitado (422)", r.status_code == 422, f"HTTP {r.status_code}")

p = {"tipo": "reu", "nome": "EJC_QA CNPJ Ruim", "cpf_cnpj": "11111111000100"}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("CNPJ inválido rejeitado (422)", r.status_code == 422, f"HTTP {r.status_code}")

p = {"tipo": "reu", "nome": "EJC_QA CNPJ BOM", "cpf_cnpj": CNPJ_VALIDO}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("CNPJ válido aceito 201", r.status_code == 201, f"HTTP {r.status_code} {r.text[:80]}")

p = {"tipo": "reu", "nome": "EJC_QA CPF BOM", "cpf_cnpj": CPF_VALIDO_2}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("CPF válido aceito 201", r.status_code == 201, f"HTTP {r.status_code} {r.text[:80]}")

# ── 3. duplicidade CPF/CNPJ ────────────────────────────────────────────────
print("== 3. duplicidade ==")
# Setup idempotente: garante uma parte ATIVA com CPF_VALIDO no caso ANTES do
# teste de duplicidade — sem isto o cenário dependia de resíduo de runs
# anteriores e falhava em execução limpa (regressão de homologação final).
r = requests.get(f"{BASE}/api/cases/{CASO}/partes", headers=h(ADMIN), timeout=15)
data_dup = r.json() if r.status_code == 200 else []
if not any(
        d.get("cpf_cnpj") == CPF_VALIDO and d.get("ativo", True) is not False
        for d in data_dup):
    p = {"tipo": "reu", "nome": "EJC_QA Base Duplicidade CPF",
         "cpf_cnpj": CPF_VALIDO}
    rb = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p,
                       headers=h(ADMIN), timeout=15)
    chk("setup base duplicidade (201)", rb.status_code in (201, 409),
        f"HTTP {rb.status_code} {rb.text[:80]}")
    BASE_DUP_ID = rb.json().get("id") if rb.status_code == 201 else None
else:
    BASE_DUP_ID = None
p = {"tipo": "terceiro", "nome": "EJC_QA Duplicata CPF", "cpf_cnpj": CPF_VALIDO}
r = requests.post(f"{BASE}/api/cases/{CASO}/partes", json=p, headers=h(ADMIN),
                  timeout=15)
chk("mesmo CPF no caso rejeitado (409)", r.status_code == 409, f"HTTP {r.status_code}")

# CPF reutilizado em OUTRO caso é permitido (mesma pessoa em casos distintos)
# cliente secundário para o teste de cliente distinto (multi-tenant)
CLI2_ID = None
try:
    r = requests.post(f"{BASE}/api/clients", json={
        "tipo": "PJ",
        "nome": "EJC_QA Cliente Secundário M08",
        "razao_social": "EJC_QA CLIENTE SECUNDARIO M08 LTDA",
        "cnpj": _dv_cnpj(f"223344{random.randint(100000,999999)}"),
        "email": "ejc.qa.m08.cliente2@gmail.com"}, headers=h(ADMIN), timeout=15)
    CLI2_ID = r.json().get("id") if r.status_code in (200, 201) else None
except Exception:
    CLI2_ID = None
CASO2_ID = None
if CLI2_ID:
    try:
        r = requests.post(f"{BASE}/api/cases", json={
            "titulo": f"EJC_QA M08 Caso 2 {random.randint(1,99999)}",
            "area": "tributario", "client_id": CLI2_ID,
            "parte_contraria": "EJC_QA", "descricao_fatos": "EJC_QA",
            "proxima_acao": "EJC_QA"}, headers=h(ADMIN), timeout=15)
        CASO2_ID = r.json().get("id") if r.status_code in (200, 201) else None
    except Exception:
        CASO2_ID = None
if CASO2_ID:
    p = {"tipo": "autor", "nome": "EJC_QA Mesmo CPF outro cliente",
         "cpf_cnpj": CPF_VALIDO}
    r = requests.post(f"{BASE}/api/cases/{CASO2_ID}/partes", json=p,
                      headers=h(ADMIN), timeout=15)
    chk("mesmo CPF em cliente distinto aceito", r.status_code == 201,
        f"HTTP {r.status_code} {r.text[:80]}")
else:
    chk("mesmo CPF em cliente distinto aceito", False, "cliente/caso secundário não criado")

# ── 4. listagem ────────────────────────────────────────────────────────────
print("== 4. listagem ==")
r = requests.get(f"{BASE}/api/cases/{CASO}/partes", headers=h(ADMIN), timeout=15)
data = r.json() if r.status_code == 200 else []
tipos = {d.get("tipo") for d in data}
chk("listagem traz as partes ativas", r.status_code == 200
    and {"autor", "reu", "terceiro", "advogado", "procurador"}.issubset(tipos),
    f"HTTP {r.status_code} tipos={tipos}")

# parte excluída some da listagem
if REU:
    requests.delete(f"{BASE}/api/cases/{CASO}/partes/{REU}", headers=h(ADMIN),
                    timeout=15)
    r = requests.get(f"{BASE}/api/cases/{CASO}/partes", headers=h(ADMIN),
                     timeout=15)
    ids = {d.get("id") for d in r.json()}
    chk("excluída some da listagem", REU not in ids, f"ids={ids}")

# ── 5. edição (PATCH) ──────────────────────────────────────────────────────
print("== 5. edição ==")
if AUTOR:
    r = requests.patch(f"{BASE}/api/cases/{CASO}/partes/{AUTOR}",
                       json={"nome": "EJC_QA Autor M08 EDITADA",
                             "oab": "sem oab"},
                       headers=h(ADMIN), timeout=15)
    chk("edição 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:90]}")
    r = requests.get(f"{BASE}/api/cases/{CASO}/partes", headers=h(ADMIN),
                     timeout=15)
    reg = [d for d in r.json() if d.get("id") == AUTOR]
    chk("edição refletida (nome atualizado)",
        len(reg) == 1 and reg[0].get("nome") == "EJC_QA Autor M08 EDITADA",
        f"{reg}")
    # validação na edição
    r = requests.patch(f"{BASE}/api/cases/{CASO}/partes/{AUTOR}",
                       json={"cpf_cnpj": "99999999999"}, headers=h(ADMIN),
                       timeout=15)
    chk("CPF inválido na edição rejeitado (422)", r.status_code == 422,
        f"HTTP {r.status_code}")
    # idempotência parcial: nada a atualizar
    r = requests.patch(f"{BASE}/api/cases/{CASO}/partes/{AUTOR}",
                       json={}, headers=h(ADMIN), timeout=15)
    chk("body vazio rejeitado (422)", r.status_code == 422, f"HTTP {r.status_code}")
    # edição de parte inexistente
    r = requests.patch(f"{BASE}/api/cases/{CASO}/partes/00000000-0000-0000-0000-000000000000",
                       json={"nome": "x"}, headers=h(ADMIN), timeout=15)
    chk("edição de inexistente 404", r.status_code == 404, f"HTTP {r.status_code}")
    # duplicidade de CPF via edição
    r = requests.patch(f"{BASE}/api/cases/{CASO}/partes/{AUTOR}",
                       json={"cpf_cnpj": CPF_VALIDO}, headers=h(ADMIN),
                       timeout=15)
    chk("duplicidade CPF na edição (409)", r.status_code == 409,
        f"HTTP {r.status_code}")

# ── 6. exclusão endurecida ─────────────────────────────────────────────────
print("== 6. exclusão ==")
r = requests.delete(f"{BASE}/api/cases/{CASO}/partes/00000000-0000-0000-0000-000000000000",
                    headers=h(ADMIN), timeout=15)
chk("exclusão de inexistente 404", r.status_code == 404, f"HTTP {r.status_code}")
if AUTOR:
    requests.delete(f"{BASE}/api/cases/{CASO}/partes/{AUTOR}",
                    headers=h(ADMIN), timeout=15)
    r = requests.delete(f"{BASE}/api/cases/{CASO}/partes/{AUTOR}",
                        headers=h(ADMIN), timeout=15)
    chk("dupla exclusão 404 (não silenciosa)", r.status_code == 404,
        f"HTTP {r.status_code}")

# ── 7. integridade DB (ativo/updated_at/auditoria) ─────────────────────────
print("== 7. banco ==")
if AUTOR:
    at = db(f"SELECT ativo FROM case_partes WHERE id='{AUTOR}'")
    chk("exclusão via banco (ativo=false)", at == "f", f"ativo={at}")
    aud = db(f"SELECT EXISTS(SELECT 1 FROM audit_logs WHERE entidade='case_partes' "
             f"AND registro_id='{AUTOR}' AND acao='DELETE')")
    chk("auditoria DELETE registrada", aud == "t", f"aud={aud}")
    aud_u = db(f"SELECT EXISTS(SELECT 1 FROM audit_logs WHERE entidade='case_partes' "
               f"AND registro_id='{AUTOR}' AND acao='UPDATE')")
    chk("auditoria UPDATE registrada", aud_u == "t", f"aud={aud_u}")

# ── 8. permissões ──────────────────────────────────────────────────────────
print("== 8. permissões ==")
for email, nome in ((FIN, "financeiro"), (CLI, "cliente externo")):
    r = requests.post(f"{BASE}/api/cases/{CASO}/partes",
                      json={"tipo": "autor", "nome": "EJC_QA"},
                      headers=h(email), timeout=15)
    # owner fora do caso (advogado de outra carteira) → 403/404
    chk(f"{nome} não cria parte", r.status_code in (403, 404),
        f"{nome}: HTTP {r.status_code}")
    r = requests.get(f"{BASE}/api/cases/{CASO}/partes", headers=h(email),
                     timeout=15)
    chk(f"{nome} não lista partes", r.status_code in (403, 404),
        f"{nome}: HTTP {r.status_code}")

# caso de OUTRA carteira: advogado fora não vê partes
if CASO2_ID:
    r = requests.get(f"{BASE}/api/cases/{CASO2_ID}/partes", headers=h(FIN),
                     timeout=15)
    chk("fora da carteira não lista partes", r.status_code in (403, 404),
        f"HTTP {r.status_code}")

# ── limpeza: partes criadas ────────────────────────────────────────────────
print(f"\nM08 resultado: {OK}/{TOTAL} PASS")
sys.exit(0 if OK == TOTAL else 1)
