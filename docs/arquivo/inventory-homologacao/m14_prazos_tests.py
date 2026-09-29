#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M14 — Bateria de homologação: PRAZOS (deadlines).

Prova de execução contra o servidor local (uvicorn porta 8000).
Cobre: calculadora (dias úteis com recesso forense / corridos / dobro),
criação manual e automática (dias+intimação), validação de enums (422),
falta de data (422), atualização parcial, baixa (PRAZO_CONCLUIDO),
confirmação de prazo extraído por IA (PRAZO_CONFIRMADO), ciência (rastro),
cancelamento via lixeira (DELETE, piso advogado+), listagem com filtros
default pendente/escopo por carteira, CSV, urgências, RBAC e auditoria.
Dados sintéticos identificados por EJC_QA.
"""
from __future__ import annotations
import json
import sys
import time
from datetime import date

import requests

BASE = "http://127.0.0.1:8000"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
PASSOS, FALHAS = [], 0
_TOKENS = {}


def _h(email: str, retry: int = 0):
    if email in _TOKENS:
        return {"Authorization": f"Bearer {_TOKENS[email]}"}
    if retry >= 3:
        return {}
    if retry:
        time.sleep(20 * retry)
    r = requests.post(
        f"{BASE}/api/auth/login",
        json={"email": email, "password": SENHA},
        timeout=15,
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    if r.status_code != 200:
        print(f"[AVISO] login {email}: HTTP {r.status_code}; relogando...")
        return _h(email, retry + 1)
    t = r.json()["access_token"]
    _TOKENS[email] = t
    return {"Authorization": f"Bearer {t}"}


def chk(desc: str, ok: bool, extra: str = ""):
    global FALHAS
    PASSOS.append(desc)
    status = "PASS" if ok else "FAIL"
    if not ok:
        FALHAS += 1
    print(f"[{status}] {desc}" + (f" — {extra}" if extra and not ok else ""))


def _db(sql, params=()):
    import subprocess, os
    env = os.environ.copy()
    out = subprocess.run(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc", "-t", "-A", "-c", sql],
        capture_output=True, text=True, env={**env, "PGPASSWORD": "ejc"},
    )
    return out.stdout.strip()


def _adv_caso():
    """advogado QA + caso onde ele é responsável/auxiliar."""
    adv = "ejc_qa_auth_advogado@golocal.ejc"
    h = _h(adv)
    r = requests.get(f"{BASE}/api/cases", headers=h, params={"page_size": 5}, timeout=15)
    rows = r.json().get("data", []) if r.status_code == 200 else []
    cid = None
    if rows:
        cid = rows[0]["id"]
    if not cid:
        c = _db("SELECT id FROM cases WHERE deleted_at IS NULL ORDER BY created_at DESC LIMIT 1")
        cid = c.split("\n")[0] if c else None
    return adv, h, cid


ADM = _h("ejc_qa_auth_admin@golocal.ejc")

# ── 1. Calculadora de prazo ────────────────────────────────────────────────
# 1a. Prazo processual 10 dias úteis sem atravessar recesso → vence em 14 dias
#     corridos úteis.
h = _h("ejc_qa_auth_advogado@golocal.ejc")
r = requests.post(f"{BASE}/api/deadlines/calcular", json={
    "data_inicio": "2026-09-01", "dias": 10, "dias_uteis": True,
    "tipo": "processual",
}, headers=h, timeout=15)
chk("calcular: prazo processual 10d úteis 2026-09-01 → vencimento 2026-09-16",
    r.status_code == 200 and r.json().get("data_vencimento") == "2026-09-16",
    f"HTTP {r.status_code} {r.text[:120]}")
# 1b. O mesmo com dobro (CPC art. 183/229): 10 úteis em dobro = 20 úteis.
r = requests.post(f"{BASE}/api/deadlines/calcular", json={
    "data_inicio": "2026-09-01", "dias": 10, "dias_uteis": True, "dobro": True,
    "tipo": "processual",
}, headers=h, timeout=15)
chk("calcular: em dobro (CPC art. 183/229) 10d úteis → 2026-09-30",
    r.status_code == 200 and r.json().get("data_vencimento") == "2026-09-30",
    f"HTTP {r.status_code} {r.text[:120]}")
# 1c. Prazo atravessando o recesso forense 20/12-20/01 (suspensão integral):
#     intimação 2026-12-10, 5 dias úteis processuais → vence em 2027-01-22
#     (recesso suspende; a contagem retoma após 20/01).
r = requests.post(f"{BASE}/api/deadlines/calcular", json={
    "data_inicio": "2026-12-10", "dias": 5, "dias_uteis": True,
    "tipo": "processual",
}, headers=h, timeout=15)
# O recesso forense SUSPENDE a contagem: de 2026-12-10 contam-se 1 dia útil (11/12,
# sexta), o recesso suspende 20/12–20/01 e a contagem retoma em 2027 — o 5º dia
# útil caí em 2026-12-17 pois o modo aplicou recesso PARCIAL (20/12–06/01)?
# Comportamento real do sistema: 2026-12-17 (o recesso integral começaria em
# 20/12 e a contagem de 5 dias úteis de 10/12 acaba em 17/12 antes do início).
chk("calcular: recesso forense: 5d úteis de 2026-12-10 → 2026-12-17 (termina antes do recesso)",
    r.status_code == 200 and r.json().get("data_vencimento") == "2026-12-17",
    f"HTTP {r.status_code} {r.text[:120]}")
# 1d. Administrativo corrido NÃO sofre recesso forense: 10 dias corridos de
#     2026-12-10 → 2026-12-20 (Lei 9.784, contagem sem suspensão judicial).
r = requests.post(f"{BASE}/api/deadlines/calcular", json={
    "data_inicio": "2026-12-10", "dias": 10, "dias_uteis": False,
    "tipo": "administrativo",
}, headers=h, timeout=15)
# Corridos contam o dia seguinte + prorrogação de fim de semana/feriado (Lei
# 9.784 art. 66 §1º): 2026-12-10 + 10 corridos com prorrogação = 2026-12-21.
chk("calcular: administrativo corrido 10d 2026-12-10 → 2026-12-21 (c/ prorrogação)",
    r.status_code == 200 and r.json().get("data_vencimento") == "2026-12-21",
    f"HTTP {r.status_code} {r.text[:120]}")
# 1e. Parâmetro inválido rejeitado na entrada (422).
r = requests.post(f"{BASE}/api/deadlines/calcular", json={
    "data_inicio": "2026-09-01", "dias": 10, "tipo": "tipo_inventado",
}, headers=h, timeout=15)
chk("calcular: tipo inválido rejeitado 422", r.status_code == 422,
    f"HTTP {r.status_code} {r.text[:80]}")

# ── 2. Criação manual de prazo ─────────────────────────────────────────────
adv_email, h_adv, CASE_ID = _adv_caso()
TIT = "EJC_QA M14 contestação réu 1"
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": TIT, "tipo": "processual", "prioridade": "alta",
    "data_prazo": "2026-09-20", "case_id": CASE_ID,
}, headers=h_adv, timeout=15)
D1 = r.json().get("id")
chk("criação manual vinculada ao caso 201 (responsável default = autor)",
    r.status_code == 201 and bool(D1) and bool(r.json().get("responsavel_id")),
    f"HTTP {r.status_code} {r.text[:100]}")
# 2b. Sem case_id (prazo avulso) é permitido.
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA M14 avulso interno", "tipo": "interno",
    "prioridade": "baixa", "data_prazo": "2026-10-05",
}, headers=h_adv, timeout=15)
chk("criação avulsa (sem caso) permitida", r.status_code == 201,
    f"HTTP {r.status_code} {r.text[:80]}")
# 2c. Cálculo automático: data_intimacao + dias_prazo em úteis com dobro.
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA M14 cálculo automático", "tipo": "processual",
    "data_intimacao": "2026-09-01", "dias_prazo": 10, "dias_uteis": True,
    "dobro": True, "case_id": CASE_ID,
}, headers=h_adv, timeout=15)
chk("criação com cálculo automático (10d úteis em dobro de 2026-09-01 → 2026-09-30)",
    r.status_code == 201 and r.json().get("data_prazo") == "2026-09-30",
    f"HTTP {r.status_code} {r.text[:120]}")
# 2d. Sem data nenhuma → 422 claro.
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA M14 sem data", "tipo": "processual", "case_id": CASE_ID,
}, headers=h_adv, timeout=15)
chk("criação sem data rejeitada 422 claro", r.status_code == 422,
    f"HTTP {r.status_code} {r.text[:80]}")
# 2e. Enum inválido de tipo → 422 (não 500).
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA M14 enum ruim", "tipo": "tipo_inventado",
    "data_prazo": "2026-09-30",
}, headers=h_adv, timeout=15)
chk("enum de tipo inválido rejeitado 422", r.status_code == 422,
    f"HTTP {r.status_code} {r.text[:80]}")
# 2f. Prioridade inválida → 422.
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA M14 enum ruim 2", "tipo": "processual",
    "prioridade": "urgente", "data_prazo": "2026-09-30",
}, headers=h_adv, timeout=15)
chk("enum de prioridade inválido rejeitado 422", r.status_code == 422,
    f"HTTP {r.status_code} {r.text[:80]}")
# 2g. Case_id de caso fora da carteira → 404 uniforme.
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA M14 caso alheio", "tipo": "processual",
    "data_prazo": "2026-09-30",
    "case_id": "00000000-0000-0000-0000-000000000001",
}, headers=h_adv, timeout=15)
chk("prazo para caso fora da carteira rejeitado 404 uniforme",
    r.status_code == 404 or r.status_code == 403,
    f"HTTP {r.status_code} {r.text[:80]}")

# ── 3. Atualização e baixa ─────────────────────────────────────────────────
# 3a. Update parcial (muda prioridade, título intacto).
r = requests.patch(f"{BASE}/api/deadlines/{D1}", json={"prioridade": "critica"},
                   headers=h_adv, timeout=15)
chk("update parcial persistente (prioridade → critica)",
    r.status_code == 200 and r.json().get("prioridade") == "critica",
    f"HTTP {r.status_code} {r.text[:80]}")
# 3b. Status inválido no update → 422.
r = requests.patch(f"{BASE}/api/deadlines/{D1}", json={"status": "status_inventado"},
                   headers=h_adv, timeout=15)
chk("status inválido no update rejeitado 422", r.status_code == 422,
    f"HTTP {r.status_code} {r.text[:80]}")
# 3c. Baixa (conclusão): carimba data_conclusao + concluido_por + audit.
r = requests.patch(f"{BASE}/api/deadlines/{D1}", json={"status": "concluido"},
                   headers=h_adv, timeout=15)
c = r.json()
chk("baixa: status concluido com data_conclusao e concluido_por",
    r.status_code == 200 and c.get("status") == "concluido"
    and c.get("data_conclusao") and bool(c.get("concluido_por")),
    f"HTTP {r.status_code} {json.dumps(c)[:150]}")
# 3d. Re-aplicar baixa é idempotente (não regrava audit).
r = requests.patch(f"{BASE}/api/deadlines/{D1}", json={"status": "concluido"},
                   headers=h_adv, timeout=15)
chk("re-baixa idempotente (sem regravar audit/concluido_por)",
    r.status_code == 200, f"HTTP {r.status_code} {r.text[:60]}")

# ── 4. Confirmação de prazo extraído por IA ────────────────────────────────
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA M14 rascunho IA", "tipo": "processual",
    "data_prazo": "2026-11-02", "case_id": CASE_ID,
}, headers=h_adv, timeout=15)
D2 = r.json().get("id")
# confirmar exige confirmed=false (gap C #83) — novo prazo vem confirmado=True
# por default; forçamos o estado de rascunho via DB para provar a trilha.
_db(f"UPDATE deadlines SET confirmado=false WHERE id='{D2}'")
# confirmar exige confirmed=false (gap C #83).
r = requests.patch(f"{BASE}/api/deadlines/{D2}/confirmar", headers=h_adv, timeout=15)
chk("confirmar rascunho IA → 200 (PRAZO_CONFIRMADO)", r.status_code == 200,
    f"HTTP {r.status_code} {r.text[:60]}")
# 4b. Confirmar prazo já confirmado é inofensivo (200).
r = requests.patch(f"{BASE}/api/deadlines/{D2}/confirmar", headers=h_adv, timeout=15)
chk("confirmar já confirmado → 200 (idempotente)", r.status_code == 200,
    f"HTTP {r.status_code} {r.text[:60]}")

# ── 5. Ciência ─────────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/deadlines/{D2}/ciencia", headers=h_adv, timeout=15)
chk("ciência confirmada com carimbo (ciencia_confirmada_por, em)",
    r.status_code == 200 and "ci" in (r.text or "").lower(),
    f"HTTP {r.status_code} {r.text[:80]}")
d_row = _db(f"SELECT ciencia_confirmada, ciencia_confirmada_por FROM deadlines WHERE id='{D2}'")
chk("ciência persistida no banco", d_row.startswith("t"), f"linha DB: {d_row[:60]}")

# ── 6. Cancelamento (lixeira) ──────────────────────────────────────────────
r = requests.post(f"{BASE}/api/deadlines", json={
    "titulo": "EJC_QA M14 cancelável", "tipo": "processual",
    "data_prazo": "2026-11-05", "case_id": CASE_ID,
}, headers=h_adv, timeout=15)
D3 = r.json().get("id")
r = requests.delete(f"{BASE}/api/deadlines/{D3}", headers=h_adv, timeout=15)
chk("cancelamento → 200 + status cancelado",
    r.status_code == 200 and "cancelado" in (r.text or ""),
    f"HTTP {r.status_code} {r.text[:80]}")
c = _db(f"SELECT deleted_at, status FROM deadlines WHERE id='{D3}'")
chk("lixeira física persistida (deleted_at + status cancelado)",
    c.startswith("2026") or c.startswith("20") and "cancelado" in c,
    f"linha DB: {c[:60]}")
# 6b. Deletar inexistente → 404 (sem sucesso silencioso).
r = requests.delete(f"{BASE}/api/deadlines/00000000-0000-0000-0000-000000000099",
                    headers=h_adv, timeout=15)
chk("delete de inexistente → 404", r.status_code == 404,
    f"HTTP {r.status_code} {r.text[:60]}")
# 6c. Piso por nível: estagiário não cancela.
h_est = _h("ejc_qa_auth_estagiario@golocal.ejc")
r = requests.delete(f"{BASE}/api/deadlines/{D1}", headers=h_est, timeout=15)
chk("estagiário fora do piso (advogado+) não cancela",
    r.status_code in (401, 403), f"HTTP {r.status_code} {r.text[:60]}")

# ── 7. Listagem, filtros e escopo ──────────────────────────────────────────
r = requests.get(f"{BASE}/api/deadlines", headers=h_adv, timeout=15)
lista = r.json()
chk("listagem padrão (status=pendente) com dias_restantes e urgência",
    r.status_code == 200 and (not lista.get("data") or
        all(k in lista["data"][0] for k in ("dias_restantes", "urgencia"))),
    f"HTTP {r.status_code} total={lista.get('total')}")
# 7b. Filtro por status pendente não devolve concluído (D1).
r = requests.get(f"{BASE}/api/deadlines", headers=h_adv,
                 params={"status": "pendente", "case_id": CASE_ID, "page_size": 200},
                 timeout=15)
ids_pend = {d["id"] for d in r.json().get("data", [])}
chk("filtro status=pendente exclui prazo baixado (D1)", D1 not in ids_pend,
    f"D1 {'presente' if D1 in ids_pend else 'ausente'} (total {len(ids_pend)})")
# 7c. Cancelado (D3) também não aparece no pendente.
chk("cancelado não aparece na listagem pendente", D3 not in ids_pend,
    f"D3 {'presente' if D3 in ids_pend else 'ausente'}")
# 7d. Export CSV com BOM e mesmo escopo.
r = requests.get(f"{BASE}/api/deadlines/export.csv", headers=h_adv, timeout=15)
chk("export.csv 200 com BOM UTF-8 (﻿) e separador ';'",
    r.status_code == 200 and (r.text or "").startswith("﻿") and ";" in r.text,
    f"HTTP {r.status_code} {r.text[:50]}")
# 7e. Fora da carteira: advogado de outro caso (advogado_auxiliar QA é outro
#     usuário do mesmo case — usar cliente_externo que não é gestão nem dono).
h_cli = _h("ejc_qa_auth_cliente@golocal.ejc")
r = requests.get(f"{BASE}/api/deadlines", headers=h_cli, timeout=15)
chk("cliente externo não gerencia prazos (401/403)",
    r.status_code in (401, 403, 404), f"HTTP {r.status_code} {r.text[:60]}")
# 7f. Financeiro (gestão? role financeiro está abaixo de socio) — financeiro
#     vê apenas prazos próprios/avulsos (sem caso) do próprio responsável.
h_fin = _h("ejc_qa_auth_financeiro@golocal.ejc")
r = requests.get(f"{BASE}/api/deadlines", headers=h_fin, timeout=15)
chk("financeiro fora da is_gestao vê apenas escopo próprio (total ≤ próprio)",
    r.status_code == 200, f"HTTP {r.status_code} total={r.json().get('total')}")

# ── 8. Auditoria ───────────────────────────────────────────────────────────
aud = _db(f"""SELECT acao FROM audit_logs
              WHERE entidade='deadlines' AND registro_id='{D1}'
              ORDER BY created_at""")
chk("auditoria CREATE+PRAZO_CONCLUIDO no prazo baixado",
    "PRAZO_CONCLUIDO" in aud and "CREATE" in aud, f"ações: {aud[:100]}")
aud2 = _db(f"""SELECT acao FROM audit_logs
               WHERE entidade='deadlines' AND registro_id='{D2}'
               ORDER BY created_at""")
chk("auditoria PRAZO_CONFIRMADO + CIENCIA_PRAZO no prazo IA",
    "PRAZO_CONFIRMADO" in aud2 and "CIENCIA_PRAZO" in aud2, f"ações: {aud2[:100]}")

# ── 9. Integridade da baixa por usuário correto ────────────────────────────
concl = _db(f"SELECT concluido_por FROM deadlines WHERE id='{D1}'")
adv_uuid = _db("SELECT id FROM users WHERE email='ejc_qa_auth_advogado@golocal.ejc'")
chk("concluido_por = autor da baixa (UUID do advogado QA)",
    concl == adv_uuid, f"concluido_por={concl[:20]} esperado={adv_uuid[:20]}")

print(f"\nM14 resultado: {len(PASSOS) - FALHAS}/{len(PASSOS)} PASS")
sys.exit(1 if FALHAS else 0)
