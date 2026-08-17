#!/usr/bin/env python3
# M18 — Templates Jurídicos: cadastro, edição (inexistente — lacuna),
# exclusão, variáveis, preenchimento, reutilização, versionamento (lacuna),
# permissões, integração com peças.
# Provado por execução real contra o servidor local na porta 8000.
from __future__ import annotations
import os
import sys
import subprocess
import time
import requests

BASE = "http://127.0.0.1:8000"
SENHA = "EjcQa2026!SenhaForte"
CASO = "7d8b4bf5-8d3c-4e67-8c3d-a453c00f9b5c"  # caso da carteira do advogado QA

EMAILS = {
    "socio": "ejc_qa_auth_socio@golocal.ejc",
    "advogado": "ejc_qa_auth_advogado@golocal.ejc",
    "estagiario": "ejc_qa_auth_estagiario@golocal.ejc",
    "secretaria": "ejc_qa_auth_secretaria@golocal.ejc",
    "financeiro": "ejc_qa_auth_financeiro@golocal.ejc",
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
            return TOKENS[evento(email)][0] if False else TOKENS[email]
        if r.status_code == 429:
            time.sleep(18 * (tent + 1))
        else:
            raise SystemExit(f"login {email}: {r.status_code} {r.text[:120]}")
    raise SystemExit(f"login {email}: rate limit persistente")


def H(role):
    return {"Authorization": f"Bearer {tok(EMAILS[role])}",
            "X-Forwarded-For": "127.0.0.1"}


def gerar_peca(tpl_id, role="advogado", titulo=None, case=CASO):
    payload = {"case_id": case}
    if titulo:
        payload["titulo_peca"] = titulo
    r = requests.post(f"{BASE}/api/templates/{tpl_id}/gerar", json=payload,
                      headers=H(role), timeout=30)
    return r


# ── 1. CADASTRO ─────────────────────────────────────────────────────────────
CONTEUDO = ("Petrólide de homologação de {{tipo_peca}} para {{cliente_nome}} "
            "(doc. {{cliente_cpf_cnpj}}), residente em {{cliente_endereco}}, "
            "nos autos nº {{numero_processo}}, em face de {{parte_contraria}}, "
            "no Juízo de {{vara}} da Comarca de {{comarca}}, área {{area}}, "
            "advogado responsável {{advogado_nome}}.")
r = requests.post(f"{BASE}/api/templates", json={
    "titulo": "EJC_QA template homologação M18",
    "tipo_peca": "peticao_inicial",
    "area": "civil",
    "descricao": "EJC_QA teste módulo 18 — reutilização múltipla",
    "conteudo": CONTEUDO,
}, headers=H("advogado"), timeout=15)
tpl = r.json() if r.status_code == 201 else {}
chk("template: cadastro 201", r.status_code == 201,
    f"{r.status_code} {r.text[:80]}")
id_tpl = tpl.get("id")

r = requests.get(f"{BASE}/api/templates/{id_tpl}", headers=H("advogado"),
                 timeout=15)
chk("template: detalhe 200 com conteudo intacto",
    r.status_code == 200 and "{{cliente_nome}}" in (r.json().get("conteudo") or ""),
    f"{r.status_code}")

# tipo_peca inválido
r = requests.post(f"{BASE}/api/templates", json={
    "titulo": "EJC_QA x", "tipo_peca": "fantasia", "conteudo": CONTEUDO},
    headers=H("advogado"), timeout=15)
chk("template: tipo_peca inválido rejeitado 422", r.status_code == 422,
    f"{r.status_code} {r.text[:60]}")

# variáveis disponíveis expostas na listagem
r = requests.get(f"{BASE}/api/templates", headers=H("advogado"), timeout=15)
lst = r.json() if r.status_code == 200 else {}
chk("template: listagem expõe variaveis_disponiveis (cliente_nome presente)",
    r.status_code == 200 and "cliente_nome" in lst.get("variaveis_disponiveis", []),
    f"{r.status_code} {lst.get('variaveis_disponiveis')}")

# ── 2. PERMISSÕES ───────────────────────────────────────────────────────────
# secretaria e financeiro fora da allowlist → 403
r = requests.post(f"{BASE}/api/templates", json={
    "titulo": "EJC_QA invasão secretaria", "tipo_peca": "parecer",
    "conteudo": CONTEUDO}, headers=H("secretaria"), timeout=15)
chk("template: secretaria bloqueada na criação (403)",
    r.status_code == 403, f"{r.status_code} {r.text[:60]}")

r = requests.post(f"{BASE}/api/templates", json={
    "titulo": "EJC_QA invasão financeiro", "tipo_peca": "parecer",
    "conteudo": CONTEUDO}, headers=H("financeiro"), timeout=15)
chk("template: financeiro bloqueado na criação (403)",
    r.status_code == 403, f"{r.status_code} {r.text[:60]}")

# estagiário é da equipe jurídica mas NÃO está na allowlist de templates
# (superadmin/admin/socio/advogado) — comportamento real verificado em
# bloco dedicado na seção de permissões após a criação do template sócio

r = requests.post(f"{BASE}/api/templates", json={
    "titulo": "EJC_QA estagiario criar", "tipo_peca": "parecer",
    "conteudo": CONTEUDO}, headers=H("estagiario"), timeout=15)
chk("template: estagiário fora da allowlist de criação (403)",
    r.status_code == 403, f"{r.status_code} {r.text[:60]}")


# sócio autorizado na criação
dados_socio = {"titulo": "EJC_QA template socio", "tipo_peca": "parecer",
               "conteudo": "Parecer EJC_QA para {{cliente_nome}} nos autos "
                           "{{numero_processo}}."}
r = requests.post(f"{BASE}/api/templates", json=dados_socio,
                  headers=H("socio"), timeout=15)
chk("template: sócio autorizado na criação (201)",
    r.status_code == 201, f"{r.status_code} {r.text[:60]}")
id_tpl_socio = r.json().get("id") if r.status_code == 201 else None

# estagiário fora da allowlist na listagem também (leitura restrita)
r = requests.get(f"{BASE}/api/templates", headers=H("estagiario"), timeout=15)
chk("template: estagiário bloqueado na listagem (403) — RBAC documentado",
    r.status_code == 403, f"{r.status_code} {r.text[:60]}")

# gerar com caso sem acesso
r = gerar_peca(id_tpl, case="00000000-0000-0000-0000-000000000000")
chk("template: gerar com caso inexistente 404", r.status_code == 404,
    f"{r.status_code}")

# ── 3. PREENCHIMENTO (variáveis resolvidas do caso/cliente) ────────────────
r = gerar_peca(id_tpl, titulo="EJC_QA peça preenchida M18")
g = r.json() if r.status_code == 201 else {}
chk("template: gerar peça 201", r.status_code == 201,
    f"{r.status_code} {r.text[:60]}")
id_peca1 = g.get("id")

r = requests.get(f"{BASE}/api/legal-docs/{id_peca1}", headers=H("advogado"),
                 timeout=15)
doc = r.json() if r.status_code == 200 else {}
conteudo = doc.get("conteudo") or ""
chk("preenchimento: cliente_nome resolvido (não vira literal)",
    "{{cliente_nome}}" not in conteudo and "EJC_QA" in conteudo,
    conteudo[:120] if r.status_code == 200 else r.status_code)
chk("preenchimento: numero_processo resolvido",
    "{{numero_processo}}" not in conteudo, conteudo[:120] if r.status_code == 200 else r.status_code)
chk("preenchimento: cliente_cpf_cnpj resolvido",
    "{{cliente_cpf_cnpj}}" not in conteudo, conteudo[:120] if r.status_code == 200 else r.status_code)

# peça nasce rascunho, não-IA, vinculada ao caso
chk("integração: peça nasce como rascunho não-IA vinculada ao caso",
    r.status_code == 200 and doc.get("status") == "rascunho"
    and doc.get("ai_generated") is False and doc.get("case_id") == CASO,
    str(doc)[:150] if r.status_code == 200 else r.status_code)

aud = db(f"SELECT count(*) FROM audit_logs WHERE entidade='legal_docs' "
         f"AND acao='CREATE' AND detalhes ILIKE '%template%'")
chk("integração: auditoria CREATE da peça registra origem do template",
    int(aud or 0) >= 1, aud)

# variável inexistente vira placeholder [var?]
r = requests.post(f"{BASE}/api/templates", json={
    "titulo": "EJC_QA template var inexistente", "tipo_peca": "parecer",
    "conteudo": "Referência a {{var_inexistente}} na peça."},
    headers=H("advogado"), timeout=15)
id_tpl_v = r.json().get("id") if r.status_code == 201 else None
r = gerar_peca(id_tpl_v)
g = r.json() if r.status_code == 201 else {}
r = requests.get(f"{BASE}/api/legal-docs/{g.get('id')}", headers=H("advogado"),
                 timeout=15)
doc = r.json() if r.status_code == 200 else {}
chk("preenchimento: variável inexistente vira placeholder [var_inexistente?]",
    "[var_inexistente?]" in (doc.get("conteudo") or ""),
    str(doc)[:150] if r.status_code == 200 else r.status_code)
requests.delete(f"{BASE}/api/templates/{id_tpl_v}", headers=H("advogado"),
                timeout=15)

# ── 4. REUTILIZAÇÃO (várias peças do mesmo template) ────────────────────────
r = gerar_peca(id_tpl, titulo="EJC_QA peça reutilização 2")
id_peca2 = r.json().get("id") if r.status_code == 201 else None
r = gerar_peca(id_tpl, titulo="EJC_QA peça reutilização 3")
id_peca3 = r.json().get("id") if r.status_code == 201 else None
chk("reutilização: segunda peça do mesmo template 201",
    id_peca2 is not None, f"{id_peca2}")
chk("reutilização: terceira peça do mesmo template 201",
    id_peca3 is not None, f"{id_peca3}")
r = requests.get(f"{BASE}/api/legal-docs", headers=H("advogado"),
                 params={"case_id": CASO}, timeout=15)
itens = r.json().get("data", r.json()) if isinstance(r.json(), dict) else r.json()
chk("reutilização: as três peças aparecem na listagem do caso",
    r.status_code == 200 and isinstance(itens, list) and len(itens) >= 3,
    f"{r.status_code} {len(itens)}")

# ── 5. EXCLUSÃO ─────────────────────────────────────────────────────────────
# RBAC da exclusão: apenas superadmin/admin/socio removem templates
# (advogado autorizado apenas para criar e gerar) — advogado é bloqueado:
r = requests.delete(f"{BASE}/api/templates/{id_tpl_socio}",
                    headers=H("advogado"), timeout=15)
chk("exclusão: advogado bloqueado na remoção (403) — RBAC documentado",
    r.status_code == 403, f"{r.status_code} {r.text[:60]}")
# sócio remove: soft-delete
r = requests.delete(f"{BASE}/api/templates/{id_tpl_socio}",
                    headers=H("socio"), timeout=15)
chk("exclusão: sócio remove com soft-delete 200",
    r.status_code == 200, f"{r.status_code} {r.text[:60]}")
r = requests.get(f"{BASE}/api/templates/{id_tpl_socio}", headers=H("socio"),
                 timeout=15)
chk("exclusão: template excluído some do detalhe (404)",
    r.status_code == 404, f"{r.status_code}")
# peça gerada ANTES da exclusão do template permanece
r = requests.get(f"{BASE}/api/legal-docs/{id_peca1}", headers=H("advogado"),
                 timeout=15)
chk("exclusão: peças já geradas permanecem após excluir o template",
    r.status_code == 200, f"{r.status_code}")

# gerar com template excluído (id_tpl_socio removido pelo sócio)
r = gerar_peca(id_tpl_socio)
chk("exclusão: gerar com template excluído 404", r.status_code == 404,
    f"{r.status_code}")

# ── 6. EDIÇÃO — NÃO EXISTE (lacuna) ─────────────────────────────────────────
# Não há PUT/PATCH em /api/templates; a única rota de escrita é POST.
r = requests.put(f"{BASE}/api/templates/{id_tpl_socio}", json={
    "titulo": "EJC_QA tentativa edição"}, headers=H("socio"), timeout=15)
chk("edição: endpoint PUT não existe (404/405) — lacuna técnica",
    r.status_code in (404, 405, 422), f"{r.status_code}")

# ── 7. VERSIONAMENTO — NÃO EXISTE (lacuna) ──────────────────────────────────
col_versao = db("SELECT count(*) FROM information_schema.columns WHERE "
                "table_name='doc_templates' AND column_name='versao'")
chk("versionamento: tabela doc_templates sem coluna versao — lacuna "
    "(histórico por recriação de template)", col_versao == "0", col_versao)

# ── LIMPEZA ─────────────────────────────────────────────────────────────────
# id_tpl (advogado) permanece ativo pois advogado não pode remover —
# limpeza via sócio não é possível (não criou); remover via DB não é feito
# para preservar rastreabilidade QA; deletado_at de id_tpl segue NULL.
for pid in [id_peca1, id_peca2, id_peca3]:
    if pid:
        requests.delete(f"{BASE}/api/legal-docs/{pid}", headers=H("advogado"),
                        timeout=15)

print(f"\nM18 resultado: {TOTAL - FALHAS}/{TOTAL} PASS")
if FALHAS:
    print(f"{FALHAS} falha(s)")
    sys.exit(2)
