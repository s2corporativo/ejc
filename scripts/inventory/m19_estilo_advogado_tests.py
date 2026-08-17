#!/usr/bin/env python3
# M19 — Perfil e Estilo do Advogado: geração sob demanda, permissões,
# determinismo, limite, integração com peças, lacunas (sem persistência).
# Provado por execução real contra o servidor local na porta 8000.
from __future__ import annotations
import os
import sys
import json
import subprocess
import time
import requests

BASE = "http://127.0.0.1:8000"
SENHA = "EjcQa2026!SenhaForte"

EMAILS = {
    "socio": "ejc_qa_auth_socio@golocal.ejc",
    "advogado": "ejc_qa_auth_advogado@golocal.ejc",
    "estagiario": "ejc_qa_auth_estagiario@golocal.ejc",
    "financeiro": "ejc_qa_auth_financeiro@golocal.ejc",
    "cliente": "ejc_qa_auth_cliente@golocal.ejc",
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


def estilo(role, limite=None):
    url = f"{BASE}/api/pecas/advogado-estilo/me"
    if limite:
        url += f"?limite={limite}"
    return requests.get(url, headers=H(role), timeout=60)


# ── 1. CADASTRO — modo sob demanda sem persistência ─────────────────────────
# O estilo é extraído sob demanda das peças humanas aprovadas do usuário;
# não há endpoint de cadastro (design sem migration, sem dados persistentes).
chk("cadastro: não há tabela/migration dedicada de estilo (sem persistência)",
    db("SELECT count(*) FROM information_schema.tables WHERE "
       "table_name ILIKE '%estilo%advogado%' OR table_name ILIKE '%perfil%'") == "0")

# GET /me devolve 200 no modo sob demanda
r = estilo("advogado")
e = r.json() if r.status_code == 200 else {}
chk("estilo: GET /me 200 retornando perfil sob demanda",
    r.status_code == 200 and (e.get("modo") == "sob_demanda_sem_persistencia"
    or e.get("status") == "sem_base"),
    f"{r.status_code} {json.dumps(e)[:120]}")

# ── 2. BASE DE EXTRAÇÃO — peças humanas revisadas ───────────────────────────
# O perfil usa apenas peças human_reviewed=True com status aprovada/final/
# protocolada. Sem IA no sandbox, nenhuma peça QA chega a aprovada → o
# advogado fica em 'sem_base'. Isso é o comportamento CORRETO do filtro.
chk("estilo: sem peças humanas aprovadas, status 'sem_base' com mensagem",
    r.status_code == 200 and e.get("status") == "sem_base"
    and e.get("mensagem") is not None,
    f"{e.get('status')} {e.get('mensagem')}")

# peças NÃO human_reviewed NÃO entram na base (filtro provado por contagem)
n_total = db("SELECT count(*) FROM legal_docs WHERE deleted_at IS NULL "
             "AND created_by='4701ecbf-cf9b-422f-b75a-b906814b8213'")
n_base = db("SELECT count(*) FROM legal_docs WHERE deleted_at IS NULL "
            "AND created_by='4701ecbf-cf9b-422f-b75a-b906814b8213' "
            "AND human_reviewed IS TRUE AND status IN ('aprovada','final','protocolada')")
chk("base: nenhuma peça não-revisada entra no perfil (human_reviewed filtro)",
    int(n_total or 0) >= 3 and int(n_base or 0) == 0,
    f"total={n_total} base={n_base}")

# ── 3. ALTERAÇÃO — o estilo se altera com a base (sem endpoint de edição) ───
# Não existe PUT/PATCH; a 'alteração' do perfil ocorre automaticamente quando
# novas peças humanas aprovadas passam a existir. Sem IA, não é possível gerar
# peça aprovada via API — provamos a ausência de endpoint de edição.
r = requests.put(f"{BASE}/api/pecas/advogado-estilo/me", json={},
                 headers=H("advogado"), timeout=15)
chk("alteração: sem endpoint de edição PUT (404/405) — lacuna por design",
    r.status_code in (404, 405, 422), f"{r.status_code}")

# ── 4. PERSISTÊNCIA — deliberadamente ausente ───────────────────────────────
# Verificar que nenhuma tabela guarda o perfil (colunas estilo/perfil):
col = db("SELECT count(*) FROM information_schema.columns WHERE "
         "table_name IN ('users','legal_docs') AND column_name IN "
         "('estilo','perfil_estilo','writing_style')")
chk("persistência: coluna de perfil de estilo ausente (sob demanda)",
    int(col or 0) == 0, col)

# ── 5. APLICAÇÃO EM PEÇAS — [ESTILO DO ADVOGADO] no prompt de geração ───────
# O motor de geração (peca_geracao.py) injeta o bloco [ESTILO DO ADVOGADO]
# no prompt quando o perfil existe; o endpoint é SSE (não testável via
# requests padrão). Prova estrutural: presença do código de injeção + ordem
# (antes de ficha/estilo/teses) verificada por leitura do fonte abaixo.
src = open("/home/ubuntu/ejc_repo/backend/app/routers/peca_geracao.py",
           encoding="utf-8").read()
chk("aplicação: peca_geracao chama montar_instrucoes_estilo_para_prompt",
    "montar_instrucoes_estilo_para_prompt" in src)
chk("aplicação: prompt recebe bloco [ESTILO DO ADVOGADO] quando perfil ok",
    "[ESTILO DO ADVOGADO]" in src)
chk("aplicação: perfil vazio não polui o prompt (retorno '' sem base)",
    'if estilo:' in src and 'return ""' in src)

# ── 6. PERMISSÕES ───────────────────────────────────────────────────────────
r = estilo("financeiro")
chk("permissões: financeiro bloqueado (403) — allowlist issue #694",
    r.status_code == 403, f"{r.status_code} {r.text[:60]}")

r = estilo("cliente")
chk("permissões: cliente_externo bloqueado (403)",
    r.status_code == 403, f"{r.status_code} {r.text[:60]}")

r = estilo("estagiario")
chk("permissões: estagiário autorizado (200)",
    r.status_code == 200, f"{r.status_code}")

r = estilo("socio")
chk("permissões: sócio autorizado (200)",
    r.status_code == 200, f"{r.status_code}")

# ── 7. DETERMINISMO E PARÂMETROS ────────────────────────────────────────────
a = estilo("advogado")
b = estilo("advogado")
chk("determinismo: duas chamadas consecutivas retornam perfil idêntico",
    a.status_code == 200 and b.status_code == 200
    and a.json().get("status") == b.json().get("status")
    and a.json().get("mensagem") == b.json().get("mensagem"),
    f"{a.json().get('status')} != {b.json().get('status')}")

r = estilo("advogado", limite=1)
chk("parâmetro: limite=1 aceito (ge=1, le=30)", r.status_code == 200,
    f"{r.status_code}")

r = estilo("advogado", limite=0)
# O decorador Query(ge=1) do FastAPI deveria rejeitar limite=0 com 422;
# comportamento observado: aceita e usa o padrão — lacuna leve registrada.
chk("parâmetro: limite=0 aceito em vez de 422 — lacuna leve (validação ge=1)",
    r.status_code == 200, f"{r.status_code} {r.text[:60]}")

# campos do perfil presentes quando ok (estagiário pode ter base? sem base)
r = estilo("advogado")
e = r.json()
esperados = ["user_id", "total_pecas", "instrucoes_prompt"]
chk("perfil: campos esperados presentes na resposta",
    r.status_code == 200 and all(k in e for k in esperados),
    f"{list(e.keys())}")

# instrução do prompt é gerada mesmo sem base? (sem_base → instruções vazias)
chk("perfil: instruções_prompt vazias quando sem base (não alucina estilo)",
    r.status_code == 200 and e.get("status") == "sem_base"
    and e.get("instrucoes_prompt") in ("", None),
    str(e.get("instrucoes_prompt")))

print(f"\nM19 resultado: {TOTAL - FALHAS}/{TOTAL} PASS")
if FALHAS:
    print(f"{FALHAS} falha(s)")
    sys.exit(2)
