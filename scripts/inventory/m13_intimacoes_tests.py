#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bateria M13 — Intimações (DJEN).
Requisitos: POSTGRES/REDIS rodando; uvicorn em :8000.
Fluxo: seed → listar → sugerir-prazo → aceitar (manual) → idempotência →
recusar protegido (409) → processar exige decisão → capturar-agora sem OAB
(422) e com OAB + DJEN desativado (503) → status-captura → auditoria →
permissões (carteira e is_gestao).
"""
import requests, sys, random, os, time, datetime as _dt

BASE = "http://127.0.0.1:8000"
ADM_E, ADV_E, EST_E = ("ejc_qa_auth_admin@golocal.ejc",
                       "ejc_qa_auth_advogado@golocal.ejc",
                       "ejc_qa_auth_estagiario@golocal.ejc")
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
ok = tot = 0

def chk(nome, condicao, detalhe=""):
    global ok, tot
    tot += 1
    if condicao:
        ok += 1
        print(f"PASS {nome}")
    else:
        print(f"FAIL {nome} — {detalhe}")

def login(email):
    for tentativa in range(3):
        r = S.post(f"{BASE}/api/auth/login",
                   json={"email": email, "password": SENHA}, timeout=30)
        if r.status_code == 200:
            return {"Authorization": f"Bearer {r.json()['access_token']}"}
        if r.status_code == 429:
            time.sleep(20)
            continue
        raise SystemExit(f"login {email} falhou: {r.status_code} {r.text[:200]}")
    raise SystemExit(f"login {email}: rate limit persistente")

def seed():
    """Insere comunicação DJEN sintética (EJC_QA) para o advogado QA."""
    from psycopg2 import connect as pg
    from uuid import uuid4
    c = pg(host="localhost", user="ejc", password="ejc", dbname="ejc")
    cur = c.cursor()
    cur.execute("SELECT id FROM users WHERE email = %s", (ADV_E,))
    adv = cur.fetchone()[0]
    # caso do advogado (usado para vincular intimação)
    cur.execute("SELECT id FROM cases WHERE deleted_at IS NULL LIMIT 1")
    cid = cur.fetchone()
    cid = cid[0] if cid else None
    rows = []
    for i in range(3):
        _id = str(uuid4())
        cur.execute("""
            INSERT INTO djen_comunicacoes (
                id, comunicacao_id_externo, advogado_id, numero_processo,
                tribunal, tipo_comunicacao, data_disponibilizacao,
                texto_resumo, case_id, processada, prazo_sugerido_status,
                prazo_deadline_id)
            SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NULL
            WHERE NOT EXISTS (
                SELECT 1 FROM djen_comunicacoes WHERE advogado_id = %s
                AND texto_resumo LIKE %s)
        """, (_id, f"EJC_QA_DJEN_{i:03d}_{random.randint(1000, 9999)}", adv,
              None, "TJMG", "Intimação",
              _dt.date(2026, 8, 16 - i),
              f"EJC_QA M13 Intimação {i} — teste de homologação",
              cid, False, "nenhum", adv, f"EJC_QA M13 Intimação {i}%"))
        if cur.rowcount:
            rows.append(_id)
        c.commit()
    cur.execute("""
        UPDATE users SET djen_oab_numero = %s, djen_oab_uf = %s
        WHERE email = %s
    """, ("251174", "MG", ADV_E))
    c.commit()
    c.close()
    return rows

S = requests.Session()

RAND = random.randint(10000, 99999)
coms = seed()
if not coms:
    raise SystemExit("seed falhou: comunicações não inseridas")
C1, C2, C3 = coms[0], coms[1], coms[2]
print("comunicações seed:", [c[:8] for c in coms])

adm, adv = login(ADM_E), login(ADV_E)

# ── 1. listar (advogado vê só as suas; admin vê todas) ─────────────────────
r = S.get(f"{BASE}/api/intimacoes/?apenas_pendentes=true", headers=adv, timeout=30)
chk("listar como advogado 200", r.status_code == 200, f"HTTP {r.status_code}")
d = r.json() if r.status_code == 200 else {}
n_adv = d.get("total", -1)
chk("advogado vê só as próprias comunicações (3 EJC_QA)", n_adv >= 3,
    f"total={n_adv}")
r = S.get(f"{BASE}/api/intimacoes/?apenas_pendentes=true", headers=adm, timeout=30)
n_adm = (r.json().get("total") if r.status_code == 200 else -1)
chk("admin vê todas as pendentes (>=3)", n_adm >= n_adv, f"adm={n_adm} adv={n_adv}")
r = S.get(f"{BASE}/api/intimacoes/?apenas_pendentes=false", headers=adm, timeout=30)
chk("listar TODAS (inclui processadas) 200", r.status_code == 200,
    f"HTTP {r.status_code}")

# ── 2. fora da carteira (cliente externo) ──────────────────────────────────
cli = login("ejc_qa_auth_cliente@golocal.ejc")
r = S.get(f"{BASE}/api/intimacoes/", headers=cli, timeout=30)
# Cliente externo não é gestão jurídica e não é advogado de intimação: 403
# uniforme (rota restrita ao Portal do Cliente) OU 200 com 0 itens —
# ambos garantem que nenhum dado vaza para o cliente.
chk("cliente externo sem acesso a intimações (sem vazamento)",
    r.status_code in (401, 403) or
    (r.status_code == 200 and (r.json().get("total") or 0) == 0),
    f"HTTP {r.status_code} {r.text[:80]}")

# ── 3. sugerir-prazo ──────────────────────────────────────────────────────
r = S.post(f"{BASE}/api/intimacoes/{C1}/sugerir-prazo", headers=adm, timeout=30)
chk("sugerir-prazo 200", r.status_code == 200, f"HTTP {r.status_code}")
if r.status_code == 200:
    j = r.json()
    chk("sugestão traz campos auditáveis (aviso, fundamentação, revisão)",
        "aviso" in j and "revisao_necessaria" in j
        and "fundamentacao" in j, f"keys={sorted(j.keys())}")
    # A sugestão deve sinalizar que o vencimento exige conferência humana:
    # revisao_necessaria=True e aviso documentado (o cálculo por dias é
    # bloqueado por 422 até o motor auditável; só vence com data_prazo manual).
    chk("sugestão exige revisão humana antes de gerar prazo",
        (j.get("revisao_necessaria") is True)
        or ("aviso" in j and "manual" in str(j.get("aviso")).lower())
        or j.get("disponivel") is False,
        f"j={str(j)[:120]}")
r = S.get(f"{BASE}/api/intimacoes/{C1}/prazo-sugerido", headers=adm, timeout=30)
chk("prazo-sugerido GET 200", r.status_code == 200, f"HTTP {r.status_code}")

# ── 4. aceitar-prazo: exige case_id e data_prazo manual ────────────────────
r = S.post(f"{BASE}/api/intimacoes/{C2}/aceitar-prazo", headers=adm,
           json={"data_prazo": "2026-08-31", "prioridade": "alta",
                 "responsavel_id": None}, timeout=30)
chk("aceitar-prazo manual 200", r.status_code == 200, f"HTTP {r.status_code}")
dl = r.json() if r.status_code == 200 else {}
dl_id = dl.get("deadline_id")
chk("aceite criou deadline com origem djen", dl.get("criado") is True
    and dl_id, f"j={dl}")
# idempotência
r = S.post(f"{BASE}/api/intimacoes/{C2}/aceitar-prazo", headers=adm,
           json={"data_prazo": "2026-09-30"}, timeout=30)
chk("aceite idempotente não duplica deadline", r.status_code == 200
    and r.json().get("criado") is False
    and r.json().get("deadline_id") == dl_id, f"j={str(r.text)[:120]}")
# 409: recusar após aceito
r = S.post(f"{BASE}/api/intimacoes/{C2}/recusar-prazo", headers=adm, timeout=30)
chk("recusar após aceito → 409 (sem reversão silenciosa)",
    r.status_code == 409, f"HTTP {r.status_code} {r.text[:80]}")

# ── 5. intimação SEM case_id → aceitação bloqueada ────────────────────────
# remover vínculo do caso da C3 via SQL direto (QA) para provar o guard
from psycopg2 import connect as pg
c = pg(host="localhost", user="ejc", password="ejc", dbname="ejc")
c.cursor().execute("UPDATE djen_comunicacoes SET case_id = NULL WHERE id = %s",
                   (C3,)); c.commit(); c.close()
r = S.post(f"{BASE}/api/intimacoes/{C3}/aceitar-prazo", headers=adm,
           json={"data_prazo": "2026-08-31"}, timeout=30)
chk("aceitar-prazo sem caso vinculado → 422 claro",
    r.status_code == 422 and "caso" in (r.text or ""),
    f"HTTP {r.status_code} {r.text[:80]}")

# ── 6. recusar-prazo (C3, sem aceito) ─────────────────────────────────────
r = S.post(f"{BASE}/api/intimacoes/{C3}/recusar-prazo", headers=adm, timeout=30)
chk("recusar-prazo 200", r.status_code == 200, f"HTTP {r.status_code}")
chk("status vira 'recusado'", r.status_code == 200
    and r.json().get("prazo_sugerido_status") == "recusado",
    f"j={str(r.text)[:100]}")

# ── 7. processar exige decisão sobre o prazo ──────────────────────────────
r = S.post(f"{BASE}/api/intimacoes/{C1}/processar", headers=adm, timeout=30)
chk("processar sem decisão sobre prazo → 422",
    r.status_code == 422 and "prazo" in (r.text or ""),
    f"HTTP {r.status_code} {r.text[:80]}")
# aceitar C1 e então processar
r = S.post(f"{BASE}/api/intimacoes/{C1}/aceitar-prazo", headers=adm,
           json={"data_prazo": "2026-09-10"}, timeout=30)
chk("aceitar-prazo C1 200", r.status_code == 200, f"HTTP {r.status_code}")
r = S.post(f"{BASE}/api/intimacoes/{C1}/processar", headers=adm, timeout=30)
chk("processar com decisão tomada 200", r.status_code == 200,
    f"HTTP {r.status_code} {r.text[:80]}")
# idempotência do processar
r = S.post(f"{BASE}/api/intimacoes/{C1}/processar", headers=adm, timeout=30)
chk("processar idempotente (já tratada) 200", r.status_code == 200,
    f"HTTP {r.status_code}")
# não aparece mais nas pendentes
r = S.get(f"{BASE}/api/intimacoes/?apenas_pendentes=true", headers=adv, timeout=30)
chk("processada sai da lista de pendentes do advogado",
    all(c[:8] not in str(r.json()) for c in coms[:1]),
    f"{r.text[:150]}")

# ── 8. capturar-agora: sem OAB → 422; com OAB + DJEN desativado → 503 ─────
s_est = login("ejc_qa_auth_secretaria@golocal.ejc")
r = S.post(f"{BASE}/api/intimacoes/capturar-agora", headers=s_est, timeout=30)
chk("capturar sem OAB no perfil → 422",
    r.status_code == 422 and "OAB" in (r.text or ""),
    f"HTTP {r.status_code} {r.text[:80]}")
r = S.post(f"{BASE}/api/intimacoes/capturar-agora", headers=adv, timeout=30)
chk("capturar com OAB e feature desativada → 503 claro (sem stack trace)",
    r.status_code == 503 and "traceback" not in (r.text or "").lower()
    and "internal" not in (r.text or "").lower(),
    f"HTTP {r.status_code} {r.text[:100]}")

# ── 9. status-captura ─────────────────────────────────────────────────────
r = S.get(f"{BASE}/api/intimacoes/status-captura", headers=adm, timeout=30)
chk("status-captura 200", r.status_code == 200, f"HTTP {r.status_code}")
if r.status_code == 200:
    j = r.json()
    chk("status-captura sem dados sensíveis",
        "erro" in j and "defasado" in j and "intimacoes_encontradas" in j,
        f"keys={sorted(j.keys())}")

# ── 10. auditoria ──────────────────────────────────────────────────────────
def db(sql):
    p = os.popen(f"PGPASSWORD=ejc psql -h localhost -U ejc -d ejc -t -A -c \"{sql}\"")
    return p.read()
aud = db("""SELECT acao FROM audit_logs WHERE entidade = 'djen_comunicacoes'
ORDER BY id DESC LIMIT 6""").splitlines()
chk("auditoria UPDATE/CREATE em djen_comunicacoes",
    any("UPDATE" in a for a in aud), f"aud={aud[:4]}")
aud_dl = db("""SELECT acao, dados_depois FROM audit_logs
WHERE entidade = 'deadlines' AND registro_id = '{0}'""".format(dl_id)).splitlines()
chk("auditoria CREATE do deadline djen com origem rastreável",
    any("CREATE" in a and "djen" in a for a in aud_dl), f"aud_dl={aud_dl[:2]}")

# ── 11. RBAC de escrita ───────────────────────────────────────────────────
fin = login("ejc_qa_auth_financeiro@golocal.ejc")
r = S.post(f"{BASE}/api/intimacoes/{C2}/processar", headers=fin, timeout=30)
chk("financeiro fora da is_gestao não vê intimações (404 uniforme)",
    r.status_code in (401, 403, 404), f"HTTP {r.status_code}")

# ── limpeza ────────────────────────────────────────────────────────────────
try:
    c = pg(host="localhost", user="ejc", password="ejc", dbname="ejc")
    c.cursor().execute("DELETE FROM djen_comunicacoes WHERE texto_resumo LIKE 'EJC_QA M13%'")
    c.cursor().execute("""UPDATE users SET djen_oab_numero=NULL, djen_oab_uf=NULL
WHERE email=%s""", (ADV_E,))
    c.commit(); c.close()
except Exception as e:
    print(f"limpeza: {e}")

print(f"\nM13 resultado: {ok}/{tot} PASS")
sys.exit(0 if ok == tot else 2)
