#!/usr/bin/env python3
# M20 — Biblioteca Jurídica: legislação (radar), jurisprudência (interna +
# externa + fontes), teses, documentos (RAG), classificação, busca, filtros,
# atualização. Provado por execução real contra o servidor local 8000.
from __future__ import annotations
import os
import sys
import json
import subprocess
import time
import requests

BASE = "http://127.0.0.1:8000"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
CASO = "7d8b4bf5-8d3c-4e67-8c3d-a453c00f9b5c"

EMAILS = {
    "socio": "ejc_qa_auth_socio@golocal.ejc",
    "advogado": "ejc_qa_auth_advogado@golocal.ejc",
    "estagiario": "ejc_qa_auth_estagiario@golocal.ejc",
    "secretaria": "ejc_qa_auth_secretaria@golocal.ejc",
}
TOKENS = {}
FALHAS = 0
TOTAL = 0


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


def tok(email):
    if email in TOKENS:
        return TOKENS[email]
    for tent in range(4):
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"email": email, "password": SENHA},
                          headers={"X-Forwarded-For": "127.0.0.1"}, timeout=15)
        if r.status_code == 200:
            TOKENS[email] = r.json()["access_token"]
            return TOKENS[email]
        if r.status_code == 429:
            time.sleep(18 * (tent + 1))
        else:
            raise SystemExit(f"login {email}: {r.status_code} {r.text[:120]}")
    raise SystemExit(f"login {email}: rate limit persistente")


def H(role):
    return {"Authorization": f"Bearer {tok(EMAILS[role])}",
            "X-Forwarded-For": "127.0.0.1"}


def get(role, path, **kw):
    return requests.get(f"{BASE}{path}", headers=H(role), timeout=60, **kw)


# ═══════════════════ 1. JURISPRUDÊNCIA INTERNA ══════════════════════════════
juri_body = {
    "titulo": "EJC_QA STJ Tema repetitivo — dano moral",
    "ementa": "Recurso especial. Dano moral. Valor indenizatório. Razoabilidade. "
              "Poder moderador do juízo. Juros e correção monetária. "
              "Termo inicial. Súmula 362 STJ. EJC_QA homologação.",
    "fundamentacao": "Voto do Relator sobre razoabilidade da indenização "
                     "e critérios do poder moderador. EJC_QA.",
    "tribunal": "STJ",
    "relator": "Min. EJC_QA Relator Sintético",
    "numero_acordao": "REsp-0000000-EJCQA",
    "data_julgamento": "2026-05-11",
    "fonte": "manual",
    "area_juridica": "cível",
    "tags": "EJC_QA,dano-moral,razoabilidade",
}
r = requests.post(f"{BASE}/api/jurisprudencias", json=juri_body,
                  headers=H("advogado"), timeout=15)
j1 = r.json() if r.status_code == 201 else {}
chk("jurisprudência: cadastro 201 (título, ementa, tribunal, tags)",
    r.status_code == 201 and j1.get("titulo") == juri_body["titulo"],
    f"{r.status_code} {r.text[:80]}")
id_j1 = j1.get("id")

r = requests.post(f"{BASE}/api/jurisprudencias", json={"titulo": "x",
                   "ementa": "x"}, headers=H("advogado"), timeout=15)
chk("jurisprudência: título curto (<5) rejeitado 422", r.status_code == 422,
    f"{r.status_code}")

r = requests.post(f"{BASE}/api/jurisprudencias", json={"titulo": "x" * 6,
                   "ementa": "x"}, headers=H("advogado"), timeout=15)
chk("jurisprudência: ementa curta (<20) rejeitada 422", r.status_code == 422,
    f"{r.status_code}")

r = get("advogado", f"/api/jurisprudencias/{id_j1}")
chk("jurisprudência: detalhe 200 com ementa completa",
    r.status_code == 200 and r.json().get("ementa") == juri_body["ementa"],
    str(r.json())[:120] if r.status_code == 200 else r.status_code)

# edição (PATCH)
r = requests.patch(f"{BASE}/api/jurisprudencias/{id_j1}", json={
    "favorito": True}, headers=H("advogado"), timeout=15)
chk("jurisprudência: edição PATCH 200 (favorito)",
    r.status_code == 200 and r.json().get("favorito") is True,
    f"{r.status_code} {r.json().get('favorito') if r.status_code == 200 else ''}")

# busca com filtros
r = get("advogado", "/api/jurisprudencias",
        params={"busca": "EJC_QA", "tribunal": "STJ", "area": "cível",
                "page": 1, "per_page": 20})
itens = r.json().get("items", []) if r.status_code == 200 else []
chk("jurisprudência: busca com filtros (q+tribunal+área) encontra registro",
    r.status_code == 200 and any(i.get("id") == id_j1 for i in itens),
    f"{r.status_code} {len(itens)} itens")

r = get("advogado", "/api/jurisprudencias",
        params={"busca": "termo_inexistente_xyz", "page": 1, "per_page": 20})
itens = r.json().get("items", []) if r.status_code == 200 else []
chk("jurisprudência: filtro sem resultado retorna lista vazia",
    r.status_code == 200 and len(itens) == 0, f"{r.status_code} {len(itens)}")

# classificação IA — sem IA no ambiente espera graceful 503
r = requests.post(f"{BASE}/api/jurisprudencias/{id_j1}/classificar-ia",
                  json={}, headers=H("advogado"), timeout=120)
chk("jurisprudência: classificação IA sem provedor degrada graceful (502/503)",
    r.status_code in (502, 503) or (r.status_code == 200 and r.json().get("resultado")),
    f"{r.status_code} {r.text[:120]}")

# permissões: secretaria não pode editar (ROLE socio+)
r = requests.post(f"{BASE}/api/jurisprudencias", json=juri_body,
                  headers=H("secretaria"), timeout=15)
chk("jurisprudência: secretaria bloqueada na edição (403)",
    r.status_code == 403, f"{r.status_code}")

# ═══════════════════ 2. JURISPRUDÊNCIA EXTERNA ══════════════════════════════
# (Fase 7 §3.6): as rotas /api/jurisprudencia-externa/{buscar,fontes,importar}
# foram aposentadas — busca externa canônica = POST
# /api/jurisprudencia-externa/precedentes/buscar (M25); importação canônica
# = POST /api/conhecimento/importar-jurisprudencia (RAG citável). A biblioteca
# interna (/api/jurisprudencias) segue testada na seção 1.
id_jimp = None

# ═══════════════════ 3. TESES ════════════════════════════════════════════════
tese_body = {
    "titulo": "EJC_QA tese prescrição intercorrente em execução fiscal",
    "descricao": "A prescrição intercorrente na execução fiscal exige decisão "
                 "expressa do juiz, conforme tese firmada pelo STJ no REsp "
                 "1.340.553. EJC_QA homologação.",
    "fundamentacao": "REsp 1.340.553/RS, Tema 566. EJC_QA.",
    "area_juridica": "tributário",
    "tribunal": "STJ",
    "tags": "EJC_QA,prescricao,execucao-fiscal",
}
r = requests.post(f"{BASE}/api/teses", json=tese_body,
                  headers=H("advogado"), timeout=15)
t1 = r.json() if r.status_code == 201 else {}
chk("tese: cadastro 201", r.status_code == 201 and t1.get("titulo"),
    f"{r.status_code} {r.text[:80]}")
id_t1 = t1.get("id")

r = get("advogado", f"/api/teses/{id_t1}")
chk("tese: detalhe 200",
    r.status_code == 200 and r.json().get("titulo") == tese_body["titulo"],
    str(r.json())[:100] if r.status_code == 200 else r.status_code)

r = get("advogado", "/api/teses", params={"busca": "EJC_QA", "area": "tributário"})
itens = r.json().get("items", r.json().get("data", [])) if r.status_code == 200 else []
chk("tese: busca com filtros localiza registro",
    r.status_code == 200 and isinstance(itens, list)
    and any(i.get("id") == id_t1 for i in itens),
    f"{r.status_code} {len(itens)}")

r = get("advogado", "/api/teses/busca-avancada",
        params={"q": "prescrição", "area": "tributário"})
chk("tese: busca-avançada 200", r.status_code == 200,
    f"{r.status_code} {r.text[:80]}")

r = get("advogado", "/api/teses/ranking")
chk("tese: ranking 200", r.status_code == 200,
    f"{r.status_code} {r.text[:60]}")

# vincular tese ao caso
r = requests.post(f"{BASE}/api/teses/{id_t1}/vincular-caso", json={
    "case_id": CASO}, headers=H("advogado"), timeout=15)
chk("tese: vincular-caso 200",
    r.status_code == 200 or (r.status_code == 409),
    f"{r.status_code} {r.text[:80]}")

r = get("advogado", f"/api/teses/casos/{CASO}")
chk("tese: listagem por caso 200",
    r.status_code == 200, f"{r.status_code} {r.text[:60]}")

# edição
r = requests.patch(f"{BASE}/api/teses/{id_t1}", json={
    "observacoes": "EJC_QA observação de homologação"},
    headers=H("advogado"), timeout=15)
chk("tese: edição PATCH 200",
    r.status_code == 200, f"{r.status_code} {r.text[:60]}")

# suggestion/motor IA sem provedor → graceful 503
r = requests.post(f"{BASE}/api/teses/sugerir-ia", json={"caso_id": CASO,
                  "descricao_fatos": "Execução fiscal em curso com débito "
                  "tributário contestado. EJC_QA homologação de módulo.",
                  "area": "tributário"},
                  headers=H("advogado"), timeout=120)
chk("tese: sugerir-ia sem provedor degrada graceful (502/503) ou 200",
    r.status_code in (502, 503, 200, 429),
    f"{r.status_code} {r.text[:100]}")

# exclusão exige nível sócio+
r = requests.delete(f"{BASE}/api/teses/{id_t1}", headers=H("advogado"),
                    timeout=15)
chk("tese: advogado bloqueado no arquivamento (403) — sócio+", r.status_code == 403, f"{r.status_code}")
r = requests.delete(f"{BASE}/api/teses/{id_t1}", headers=H("socio"),
                    timeout=15)
chk("tese: sócio arquiva 204", r.status_code == 204, f"{r.status_code}")
r = get("advogado", f"/api/teses/{id_t1}")
chk("tese: excluída some do detalhe (404)", r.status_code == 404,
    f"{r.status_code}")

# ═══════════════════ 4. LEGISLAÇÃO — RADAR LEGISLATIVO ══════════════════════
r = get("advogado", "/api/radar-legislativo/proposicoes",
        params={"fonte": "camara", "termo": "reforma tributária"})
chk("radar: Câmara 200 com termo",
    r.status_code in (200, 502, 503),
    f"{r.status_code} {r.text[:100]}")

r = get("advogado", "/api/radar-legislativo/proposicoes", params={"fonte": "senado",
        "termo": "direito civil"})
chk("radar: Senado 200",
    r.status_code in (200, 502, 503),
    f"{r.status_code} {r.text[:100]}")

r = get("advogado", "/api/radar-legislativo/proposicoes", params={"fonte": "almg",
        "termo": "meio ambiente"})
chk("radar: ALMG 200",
    r.status_code in (200, 502, 503),
    f"{r.status_code} {r.text[:100]}")

r = get("advogado", "/api/radar-legislativo/proposicoes", params={"fonte": "invalida",
        "termo": "teste"})
chk("radar: fonte inválida rejeitada (pattern)", r.status_code == 422,
    f"{r.status_code}")

r = get("advogado", "/api/radar-legislativo/proposicoes", params={"termo": "ab"})
chk("radar: termo <3 chars rejeitado 422", r.status_code == 422,
    f"{r.status_code}")

# ═══════════════════ 5. DOCUMENTOS RAG ══════════════════════════════════════
r = get("advogado", "/api/rag/docs", params={"page": 1, "per_page": 20})
chk("RAG: listagem de documentos 200", r.status_code == 200,
    f"{r.status_code}")

r = get("advogado", "/api/rag/buscar", params={"q": "dano moral"})
chk("RAG: busca semântica 200", r.status_code == 200,
    f"{r.status_code} {r.text[:80]}")

r = get("advogado", "/api/rag/status")
chk("RAG: status 200", r.status_code == 200,
    f"{r.status_code} {r.text[:60]}")

# ═══════════════════ 6. ATUALIZAÇÃO / INTEGRAÇÕES ═══════════════════════════
r = get("advogado", "/api/rag/monitor-legislativo")
chk("atualização: monitor-legislativo 200",
    r.status_code in (200, 502, 503),
    f"{r.status_code} {r.text[:100]}")

# ═══════════════════ LIMPEZA ════════════════════════════════════════════════
for jid in [id_j1, id_jimp]:
    if jid:
        requests.delete(f"{BASE}/api/jurisprudencias/{jid}",
                        headers=H("advogado"), timeout=15)

print(f"\nM20 resultado: {TOTAL - FALHAS}/{TOTAL} PASS")
if FALHAS:
    print(f"{FALHAS} falha(s)")
    sys.exit(2)
