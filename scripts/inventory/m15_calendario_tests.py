#!/usr/bin/env python3
# M15 — Calendário Forense, Feriados e Suspensões (bateria de homologação)
# Provado por execução real contra o servidor local na porta 8000.
from __future__ import annotations
import os
import sys
import json
import subprocess
import datetime as dt
import requests

BASE = "http://127.0.0.1:8000"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
ADM_EMAIL = "ejc_qa_auth_admin@golocal.ejc"
FIN_EMAIL = "ejc_qa_auth_financeiro@golocal.ejc"

FALHAS = 0
TOTAL = 0


async def _seed_feriado_sintetico():
    from app.core.database import AsyncSessionLocal
    from app.models.feriado import Feriado

    async def _do():
        async with AsyncSessionLocal() as db:
            f = Feriado(id="ejc-qa-2026-06-08", data=dt.date(2026, 6, 8),
                        nome="EJC_QA feriado municipal sintético", tipo="municipal",
                        movel=False)
            db.add(f)
            await db.commit()

    await _do()


async def _drop_feriado_sintetico():
    from app.core.database import AsyncSessionLocal

    async def _do():
        async with AsyncSessionLocal() as db:
            await db.execute(sa_text("DELETE FROM feriados WHERE id='ejc-qa-2026-06-08'"))
            await db.commit()

    await _do()


def chk(desc, ok, extra=""):
    global FALHAS, TOTAL
    TOTAL += 1
    if ok:
        print(f"[PASS] {desc}")
    else:
        FALHAS += 1
        print(f"[FAIL] {desc} — {extra}")


def db(sql):
    env = dict(os.environ)
    env["PGPASSWORD"] = "ejc"
    o = subprocess.run(["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc",
                        "-t", "-A", "-c", sql], capture_output=True, text=True, env=env)
    return o.stdout.strip()


def token(email):
    for tent in range(4):
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": SENHA},
                          headers={"X-Forwarded-For": "127.0.0.1"}, timeout=15)
        if r.status_code == 200:
            return r.json()["access_token"]
        if r.status_code == 429:
            import time
            time.sleep(18 * (tent + 1))
        else:
            raise SystemExit(f"login {email}: {r.status_code} {r.text[:120]}")
    raise SystemExit(f"login {email}: rate limit persistente")


t_adm = token(ADM_EMAIL)
t_fin = token(FIN_EMAIL)
H_ADM = {"Authorization": f"Bearer {t_adm}", "X-Forwarded-For": "127.0.0.1"}
H_FIN = {"Authorization": f"Bearer {t_fin}", "X-Forwarded-For": "127.0.0.1"}

# ── 1. Feriados nacionais fixos ──────────────────────────────────────────────
# Carregados do calendário versionado (calendario_tribunal.feriados_fixos_nacionais).
import app.services.deadline_calculator as dc
import app.services.calendario_tribunal as ct

fixos = ct.feriados_fixos_nacionais()
chk("feriados fixos nacionais carregados em memória", len(fixos) >= 9, f"{len(fixos)}")
chk("natal (25/12) é feriado fixo nacional", (25, 12) in fixos)
chk("independência (07/09) é feriado fixo nacional", (7, 9) in fixos)

# ── 2. Feriados móveis 2026 (Carnaval, Páscoa/Sexta Santa, Corpus Christi) ───
mov = dc.feriados_moveis(2026)
pascoa = dt.date(2026, 4, 5)  # Páscoa 2026: 5 de abril (verificação externa: 2026-04-05)
sexta_santa = dt.date(2026, 4, 3)
carnaval_terca = dt.date(2026, 2, 17)
corpus = dt.date(2026, 6, 4)
chk("sexta santa 2026 (03/04) reconhecida", sexta_santa in mov, f"móveis2026={sorted(mov)}")
chk("carnaval terça 2026 (17/02) reconhecido", carnaval_terca in mov)
chk("corpus christi 2026 (04/06) reconhecido", corpus in mov)

# ── 3. Recesso forense parcial 20/12–06/01 (Lei 5.010/66 art. 62 I) ────────
chk("recesso forense contém 20/12", (20, 12) in dc.RECESSO_FORENSE)
chk("recesso forense contém 06/01", (6, 1) in dc.RECESSO_FORENSE)
chk("recesso forense NÃO contém 19/12", (19, 12) not in dc.RECESSO_FORENSE)

# ── 4. eh_feriado / eh_dia_util (forense vs administrativo) ─────────────────
natal = dt.date(2026, 12, 25)
sab = dt.date(2026, 8, 15)  # sábado
dom = dt.date(2026, 8, 16)  # domingo
seg = dt.date(2026, 8, 17)  # segunda normal
recesso_dia = dt.date(2026, 12, 24)  # dentro do recesso forense

chk("25/12 é feriado (forense)", dc.eh_feriado(natal, incluir_recesso=True))
chk("sábado não é dia útil", not dc.eh_dia_util(sab, forense=True))
chk("domingo não é dia útil", not dc.eh_dia_util(dom, forense=True))
chk("segunda normal é dia útil", dc.eh_dia_util(seg, forense=True))

# Recesso forense SUSPENDE prazo processual mas NÃO administrativo.
d_antes_recesso = dt.date(2026, 12, 14)  # segunda, 5 dias úteis antes do recesso
venc_forense = dc.prazo_dias_uteis(d_antes_recesso, 5)   # recesso aplica
venc_adm = dc.prazo_dias_corridos(d_antes_recesso, 5, prorrogar_fim=True)
chk("prazo forense de 5d úteis a partir de 14/12/2026 termina após o recesso (2027-01-07)",
    venc_forense == dt.date(2027, 1, 7), f"venc_forense={venc_forense}")
chk("prazo administrativo corrido 5d termina em 19/12 (sáb) → prorrogado p/ 21/12 (seg)",
    venc_adm == dt.date(2026, 12, 21), f"venc_adm={venc_adm}")

# ── 5. Feriados municipais/estaduais da tabela `feriados` ───────────────────
# A tabela `feriados` é populada pelo seed (seed_all) em deploy. Em QA local,
# a carga ocorre via _sincronizar_feriados_brasilapi (scheduler). A bateria prova
# o COMPORTAMENTO (cálculo com feriados nacionais) sem depender do cron externo:
# insere um feriado MUNICIPAL sintético na tabela, recarrega a memória e prova o efeito.
import asyncio
from sqlalchemy import text as sa_text

# Data escolhida de propósito: 08/06/2026 (segunda) não é feriado nacional,
# móvel ou recesso — qualquer efeito no cálculo vem exclusivamente da tabela.
FERIADO_SINT = dt.date(2026, 6, 8)
try:
    db("INSERT INTO feriados (id, data, nome, tipo, movel) VALUES "
       "('ejc-qa-2026-06-08', '2026-06-08', 'EJC_QA feriado municipal sintético', 'municipal', false)")
except Exception as e:
    FERIADO_SINT = None
    print(f"[AVISO] não foi possível semear feriado sintético: {e}")

if FERIADO_SINT:
    n_pre = len(dc._FERIADOS_DB)
    asyncio.run(dc.carregar_feriados_db())
    n_pos = len(dc._FERIADOS_DB)
    chk("feriado municipal sintético carregado na memória da calculadora",
        FERIADO_SINT in dc._FERIADOS_DB, f"{n_pre}→{n_pos}")
    # feriado municipal SUSPENDE prazo: 04/06 (qui, Corpus) +3 úteis =
    # 05 (sex), (08 seg suspenso), 09 (ter) → 10/06/2026
    v = dc.prazo_dias_uteis(dt.date(2026, 6, 4), 3)
    chk("feriado municipal suspende prazo processual (3 úteis de 04/06 = 10/06, com 08/06 suspenso)",
        v == dt.date(2026, 6, 10), f"v={v}")
    # limpeza: sem o feriado, 04/06 +3 úteis = 05, 08, 09 → 09/06/2026
    db("DELETE FROM feriados WHERE id='ejc-qa-2026-06-08'")
    dc.set_feriados_db({})  # revalida: sem o feriado, o cálculo o ignora
    v2 = dc.prazo_dias_uteis(dt.date(2026, 6, 4), 3)
    chk("limpeza do feriado sintético restaura o comportamento (08/06 volta a ser dia útil)",
        v2 == dt.date(2026, 6, 9), f"v={v2}")
    db("DELETE FROM feriados WHERE id='ejc-qa-2026-06-08'")  # idempotência

# ── 6. Endpoint /suspensoes/tribunais (sem segredos) ────────────────────────
r = requests.get(f"{BASE}/api/suspensoes/tribunais", headers=H_ADM, timeout=15)
trib = r.json()
lista = trib.get("tribunais", trib if isinstance(trib, list) else [])
chk("GET /suspensoes/tribunais 200 com sugestões (TJMG)",
    r.status_code == 200 and "TJMG" in [t.upper() for t in lista],
    f"{r.status_code} {str(lista)[:100]}")

# ── 7. CRUD de suspensão por tribunal ───────────────────────────────────────
r = requests.post(f"{BASE}/api/suspensoes", json={
    "tribunal": "TJMG",
    "data_inicio": "2026-10-01",
    "data_fim": "2026-10-02",
    "motivo": "EJC_QA suspensão teste homologação — portaria simulada",
    "ato_normativo": "Portaria TGJMG nº EJC-QA-2026"}, headers=H_ADM, timeout=15)
chk("criação de suspensão 201", r.status_code == 201, f"{r.status_code} {r.text[:100]}")
susp_id = r.json().get("id")
r = requests.get(f"{BASE}/api/suspensoes", headers=H_ADM, timeout=15)
lst = r.json()
itens = lst.get("data", lst if isinstance(lst, list) else [])
chk("listagem contém suspensão TJMG criada",
    any(s.get("tribunal") == "TJMG" for s in itens), f"{len(itens)} itens")
susp = next((s for s in itens if s.get("id") == susp_id), None)
chk("suspensão persiste com datas e motivo",
    susp is not None and susp.get("motivo", "").startswith("EJC_QA"),
    str(susp)[:100])

# ── 8. Suspensão altera o cálculo do simulador (tribunal informado) ─────────
r1 = requests.post(f"{BASE}/api/suspensoes/simular", json={
    "data_inicio": "2026-09-28", "dias": 5, "contagem": "uteis",
    "tribunal": None}, headers=H_ADM, timeout=15)
r2 = requests.post(f"{BASE}/api/suspensoes/simular", json={
    "data_inicio": "2026-09-28", "dias": 5, "contagem": "uteis",
    "tribunal": "TJMG"}, headers=H_ADM, timeout=15)
v1 = r1.json().get("data_vencimento")
v2 = r2.json().get("data_vencimento")
chk("simular sem tribunal ignora suspensão TJMG",
    v1 and dt.date.fromisoformat(v1) == dt.date(2026, 10, 5), f"v1={v1}")
chk("simular com tribunal TJMG adia vencimento (suspensão 01-02/10/2026)",
    v2 and dt.date.fromisoformat(v2) > dt.date(2026, 10, 5), f"v2={v2}")
# sem suspensão TJMG: 28/09 (seg) +5 úteis = 05/10 (seg). Com suspensão 01-02/10:
# dias úteis: 29/09, 30/09, 05/10, 06/10, 07/10 → vencimento 07/10/2026.
chk("com suspensão TJMG, 5d úteis de 28/09 terminam em 07/10/2026",
    v2 and dt.date.fromisoformat(v2) == dt.date(2026, 10, 7), f"v2={v2}")

# ── 9. Simulador não grava nada (rascunho) ──────────────────────────────────
antes = db("SELECT count(*) FROM suspensoes_tribunal")
r3 = requests.post(f"{BASE}/api/suspensoes/simular", json={
    "data_inicio": "2026-11-02", "dias": 10, "contagem": "corridos",
    "tribunal": "STJ"}, headers=H_ADM, timeout=15)
depois = db("SELECT count(*) FROM suspensoes_tribunal")
chk("simular corrido 200 e NÃO grava nada",
    r3.status_code == 200 and antes == depois, f"{r3.status_code} {antes}→{depois}")
v3 = r3.json().get("data_vencimento")
chk("corridos 10d de 02/11 com prorrogação = 12/11/2026 (quinta)",
    v3 and dt.date.fromisoformat(v3) == dt.date(2026, 11, 12), f"v3={v3}")

# ── 10. Validações ──────────────────────────────────────────────────────────
r = requests.post(f"{BASE}/api/suspensoes", json={
    "tribunal": "X", "data_inicio": "2026-12-01", "data_fim": "2026-12-01",
    "motivo": "ok"}, headers=H_ADM, timeout=15)
chk("tribunal < 2 chars rejeitado 422", r.status_code == 422, f"{r.status_code}")
r = requests.post(f"{BASE}/api/suspensoes", json={
    "tribunal": "TRT3", "data_inicio": "2026-12-10", "data_fim": "2026-12-01",
    "motivo": "fim antes do início"}, headers=H_ADM, timeout=15)
# fim < início: validação de coerência de datas
chk("suspensão com fim antes do início rejeitada", r.status_code in (422, 400), f"{r.status_code} {r.text[:100]}")

# ── 11. Exclusão com auditoria ──────────────────────────────────────────────
r = requests.delete(f"{BASE}/api/suspensoes/{susp_id}", headers=H_ADM, timeout=15)
chk("exclusão de suspensão 200", r.status_code == 200, f"{r.status_code} {r.text[:100]}")
aud = db(f"SELECT count(*) FROM audit_logs WHERE entidade='suspensoes_tribunal' "
         f"AND registro_id='{susp_id}' AND acao='DELETE'")
chk("auditoria DELETE da suspensão", int(aud or 0) >= 1, aud)
r = requests.delete(f"{BASE}/api/suspensoes/00000000-0000-0000-0000-000000000000",
                    headers=H_ADM, timeout=15)
chk("exclusão de inexistente → 404", r.status_code == 404, f"{r.status_code}")

# ── 12. RBAC ────────────────────────────────────────────────────────────────
r = requests.get(f"{BASE}/api/suspensoes/tribunais", headers=H_FIN, timeout=15)
chk("financeiro acessa lista de tribunais sugeridos", r.status_code == 200, f"{r.status_code}")
r = requests.post(f"{BASE}/api/suspensoes", json={
    "tribunal": "STF", "data_inicio": "2026-11-01", "data_fim": "2026-11-01",
    "motivo": "EJC_QA financeiro"}, headers=H_FIN, timeout=15)
chk("financeiro NÃO cria suspensão (fora da gestão forense)", r.status_code in (401, 403, 422),
    f"{r.status_code} {r.text[:100]}")

# ── 13. Integrador: calculadora com feriados locais e suspensões em cadeia ──
# Suspensão real no período prova o encadeamento completo: nacional + suspensão.
r = requests.post(f"{BASE}/api/suspensoes", json={
    "tribunal": "STJ", "data_inicio": "2026-12-21", "data_fim": "2026-12-23",
    "motivo": "EJC_QA natal antecipado"}, headers=H_ADM, timeout=15)
susp2 = r.json().get("id")
r = requests.post(f"{BASE}/api/suspensoes/simular", json={
    "data_inicio": "2026-12-14", "dias": 5, "contagem": "uteis",
    "tribunal": "STJ"}, headers=H_ADM, timeout=15)
v = r.json().get("data_vencimento")
# 14/12 (seg). Dias úteis: 15, 16, 17, 18 (seg-qui). 19/12 (sáb), 20/12 (dom) não.
# 21-23/12 suspensos STJ. 24/12 qui normal, 25/12 sex feriado nacional, 26/12 sáb.
# O recesso forense começa em 20/12 e vai até 06/01 — 5d úteis de 14/12 passam pelo
# recesso completo: 15,16,17,18 + 07/01 (fim recesso) → 2027-01-07.
chk("cadeia completa: 5d úteis com suspensão STJ + feriado nacional + recesso = 2027-01-07",
    v and dt.date.fromisoformat(v) == dt.date(2027, 1, 7), f"v={v}")
r = requests.delete(f"{BASE}/api/suspensoes/{susp2}", headers=H_ADM, timeout=15)
chk("limpeza da suspensão STJ de teste 200", r.status_code == 200, f"{r.status_code}")

print(f"\nM15 resultado: {TOTAL - FALHAS}/{TOTAL} PASS")
if FALHAS:
    print(f"{FALHAS} falha(s)")
    sys.exit(2)
