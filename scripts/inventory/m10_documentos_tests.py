#!/usr/bin/env python3
"""Bateria de homologação M10 — Documentos/GED.
Cobertura: upload (extensões, magic bytes, limite de tamanho, tipos,
vinculação a cliente/caso), listagem, metadados, download autenticado,
exclusão soft com lixeira/restauração, permissões e auditoria.
Executar com env_shell.sh para carregar o .env.
"""
import io
import os
import sys
import time
import random
import requests
from datetime import date

BASE = "http://127.0.0.1:8000"
ADMIN = "ejc_qa_auth_admin@golocal.ejc"
FIN = "ejc_qa_auth_financeiro@golocal.ejc"
CLI = "ejc_qa_auth_cliente@golocal.ejc"
SENHA = "EjcQa2026!SenhaForte"
HEADERS = {"X-Forwarded-For": "127.0.0.1"}
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


def q(sql):
    import subprocess
    r = subprocess.run(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc", "-t", "-A", "-c", sql],
        capture_output=True, text=True,
        env={**os.environ, "PGPASSWORD": "ejc"})
    return r.stdout.strip()


if __name__ != "__main__":
    sys.exit(0)

# ── recursos QA ────────────────────────────────────────────────────────────
print("== recursos QA ==")
r = requests.post(f"{BASE}/api/clients", json={
    "tipo": "PJ",
    "nome": f"EJC_QA Cliente Docs {random.randint(1,99999)}",
    "razao_social": "EJC_QA CLIENTE DOCS LTDA",
    "cnpj": "12345678000195",
    "email": "ejc.qa.docs@gmail.com"}, headers=h(ADMIN), timeout=15)
if r.status_code in (200, 201):
    CLIENTE = r.json().get("id")
else:
    r2 = requests.get(f"{BASE}/api/clients", headers=h(ADMIN),
                      params={"q": "EJC_QA Cliente Docs"}, timeout=15)
    d = r2.json().get("data")
    CLIENTE = d[0]["id"] if d else None
print("cliente QA:", CLIENTE)
r = requests.post(f"{BASE}/api/cases", json={
    "titulo": f"EJC_QA M10 Caso {random.randint(1,99999)}",
    "area": "tributario", "client_id": CLIENTE,
    "parte_contraria": "EJC_QA", "descricao_fatos": "EJC_QA",
    "proxima_acao": "EJC_QA"}, headers=h(ADMIN), timeout=15)
CASO = r.json().get("id") if r.status_code in (200, 201) else None
print("caso QA:", CASO)
if not CLIENTE or not CASO:
    print("ERRO: recursos QA faltantes"); sys.exit(2)

TXT = b"EJC_QA M10 documento de teste - homologacao de homologacao " * 50

# assinaturas de magic bytes reais (o GED valida o conteúdo pelo formato)
PDF_HEAD = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
            b"trailer\n<< /Root 1 0 R >>\n%%EOF\n" + TXT)
XLSX_HEAD = (b"PK\x03\x04\x14\x00\x00\x00\x00\x00\x00\x00\x00\x00" + TXT
             + b"PK\x05\x06\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00")
PNG_HEAD = (b"\x89PNG\r\n\x1a\n" + TXT)

def up(file_bytes, filename, **kwargs):
    return requests.post(f"{BASE}/api/documents/upload",
                         files={"file": (filename, file_bytes)},
                         data=kwargs, headers=h(ADMIN), timeout=60)

# ── 1. upload básico ───────────────────────────────────────────────────────
print("== 1. upload básico ==")
REAL_PDF = open("/tmp/ejc_qa_test.pdf", "rb").read()
REAL_XLSX = open("/tmp/ejc_qa_test.xlsx", "rb").read()
REAL_PNG = open("/tmp/ejc_qa_test.png", "rb").read()

r = up(REAL_PDF, "teste.pdf", titulo="EJC_QA Doc 1", tipo="peticao",
       case_id=CASO)
DOC1 = r.json().get("id") if r.status_code == 201 else None
chk("upload PDF válido 201", r.status_code == 201, f"HTTP {r.status_code} {r.text[:80]}")

r = up(REAL_XLSX, "planilha.xlsx", titulo="EJC_QA Doc 2", tipo="prova",
       case_id=CASO)
DOC2 = r.json().get("id") if r.status_code == 201 else None
chk("upload XLSX válido 201", r.status_code == 201, f"HTTP {r.status_code}")

r = up(TXT, "imagens.png", titulo="EJC_QA Doc 3", tipo="outro",
       client_id=CLIENTE)
DOC3 = r.json().get("id") if r.status_code == 201 else None
chk("upload TXT com extensão PNG rejeitado 415 (MIME falso)", r.status_code == 415,
    f"HTTP {r.status_code} {r.text[:60]}")

# ── 2. extensões bloqueadas ────────────────────────────────────────────────
print("== 2. extensões ==")
for ext, nome in ((".exe", "malware"), (".svg", "img"), (".html", "pag")):
    r = up(TXT, f"{nome}{ext}", titulo="EJC_QA Bloqueado", case_id=CASO)
    chk(f"extensão {ext} rejeitada (422)", r.status_code == 422,
        f"HTTP {r.status_code} {r.text[:50]}")

# ── 3. limite de tamanho ───────────────────────────────────────────────────
print("== 3. limite ==")
BIG = b"X" * (51 * 1024 * 1024)
r = up(BIG, "grande.pdf", titulo="EJC_QA Grande", case_id=CASO)
chk("arquivo >50MB rejeitado (413)", r.status_code == 413, f"HTTP {r.status_code}")

# ── 4. vínculo e validação ─────────────────────────────────────────────────
print("== 4. vínculo ==")
if DOC1:
    n = q(f"SELECT count(*) FROM documents WHERE id='{DOC1}' AND case_id='{CASO}' AND client_id='{CLIENTE}'")
    chk("documento vinculado a caso E cliente", int(n or 0) == 1, f"n={n}")
r = up(TXT, "ok.txt", titulo="EJC_QA Vinculo", case_id=CASO,
       client_id="00000000-0000-0000-0000-000000000000")
chk("client_id divergente do caso rejeitado (422)", r.status_code == 422,
    f"HTTP {r.status_code}")
r = up(TXT, "ok2.txt", titulo="EJC_QA Sem Caso", client_id=CLIENTE)
DOC_SEM = r.json().get("id") if r.status_code == 201 else None
chk("upload sem caso (só cliente) aceito 201", r.status_code == 201,
    f"HTTP {r.status_code}")

# ── 5. listagem e metadados ────────────────────────────────────────────────
print("== 5. listagem/metadados ==")
r = requests.get(f"{BASE}/api/documents", headers=h(ADMIN),
                 params={"case_id": CASO, "page_size": 50}, timeout=15)
ids = [x["id"] for x in r.json().get("data", [])]
chk("listagem por caso traz os docs", DOC1 in ids and DOC2 in ids,
    f"DOC1={DOC1 in ids} DOC2={DOC2 in ids}")

if DOC1:
    r = requests.patch(f"{BASE}/api/documents/{DOC1}",
                       json={"titulo": "EJC_QA Doc 1 editado",
                             "tipo": "procuracao"},
                       headers=h(ADMIN), timeout=15)
    chk("patch metadados 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:60]}")
    n = q(f"SELECT count(*) FROM documents WHERE id='{DOC1}' AND titulo='EJC_QA Doc 1 editado' AND tipo='procuracao'")
    chk("metadados persistidos no banco", int(n or 0) == 1, f"n={n}")

r = requests.patch(f"{BASE}/api/documents/00000000-0000-0000-0000-000000000001",
                   json={"titulo": "x"}, headers=h(ADMIN), timeout=15)
chk("patch inexistente 404", r.status_code == 404, f"HTTP {r.status_code}")

# ── 6. download autenticado ────────────────────────────────────────────────
print("== 6. download ==")
if DOC1:
    r = requests.get(f"{BASE}/api/documents/{DOC1}/download",
                     headers=h(ADMIN), timeout=15)
    chk("download autenticado 200", r.status_code == 200, f"HTTP {r.status_code}")
r = requests.get(f"{BASE}/api/documents/{DOC1}/download" if DOC1
                 else f"{BASE}/api/documents/00000000-0000-0000-0000-000000000001/download",
                 headers=HEADERS, timeout=15)
chk("download sem token 401", r.status_code == 401, f"HTTP {r.status_code}")

# ── 7. exclusão soft + lixeira/restauração ─────────────────────────────────
print("== 7. lixeira ==")
if DOC3 and DOC3 in [x["id"] for x in requests.get(
        f"{BASE}/api/documents", headers=h(ADMIN),
        params={"case_id": CASO}, timeout=15).json().get("data", [])]:
    # DOC3 foi 415 (não criado); usar DOC_SEM para exclusão
    pass
if DOC_SEM:
    n0 = q(f"SELECT count(*) FROM documents WHERE id='{DOC_SEM}' AND deleted_at IS NULL")
    if int(n0 or 0) == 0:
        DOC_SEM = None
if DOC_SEM:
    r = requests.delete(f"{BASE}/api/documents/{DOC_SEM}", headers=h(ADMIN),
                        timeout=15)
    chk("exclusão soft 200", r.status_code == 200, f"HTTP {r.status_code} {r.text[:50]}")
    n = q(f"SELECT count(*) FROM documents WHERE id='{DOC_SEM}' AND deleted_at IS NULL")
    chk("sai da listagem ativa (deleted_at preenchido)", int(n or 0) == 0, f"n={n}")
    r = requests.post(f"{BASE}/api/trash/documents/{DOC_SEM}/restaurar",
                      headers=h(ADMIN), timeout=15)
    chk("restauração da lixeira 200", r.status_code == 200,
        f"HTTP {r.status_code} {r.text[:50]}")
    n = q(f"SELECT count(*) FROM documents WHERE id='{DOC_SEM}' AND deleted_at IS NULL")
    chk("restaurado volta à listagem ativa", int(n or 0) == 1, f"n={n}")

r = requests.delete(f"{BASE}/api/documents/00000000-0000-0000-0000-000000000001",
                    headers=h(ADMIN), timeout=15)
chk("exclusão inexistente 404", r.status_code == 404, f"HTTP {r.status_code}")

# ── 8. permissões ──────────────────────────────────────────────────────────
print("== 8. permissões ==")
r = requests.post(f"{BASE}/api/documents/upload",
                  files={"file": ("x.pdf", TXT)},
                  data={"titulo": "EJC_QA Bloqueado", "case_id": CASO},
                  headers=h(FIN), timeout=15)
chk("financeiro não faz upload", r.status_code in (401, 403),
    f"HTTP {r.status_code}")
r = requests.get(f"{BASE}/api/documents", headers=h(CLI), timeout=15)
chk("cliente externo não lista GED interno", r.status_code in (401, 403),
    f"HTTP {r.status_code}")

# ── 9. auditoria ───────────────────────────────────────────────────────────
print("== 9. auditoria ==")
DELETED_ID = DOC_SEM
for d_id, acao in ((DOC1, "UPLOAD"), (DOC1, "UPDATE"),
                   (DELETED_ID, "DELETE"), (DOC1, "DOWNLOAD")):
    if not d_id:
        chk(f"auditoria {acao} registrada (doc ausente)", False,
            "documento não criado")
        continue
    n = q("SELECT count(*) FROM audit_logs WHERE registro_id='" + d_id
          + "' AND entidade='documents' AND acao='" + acao + "'")
    chk(f"auditoria {acao} registrada ({d_id[:8]})", int(n or 0) > 0,
        f"n={n}")

# ── resumo ─────────────────────────────────────────────────────────────────
print(f"\nM10 resultado: {OK}/{TOTAL} PASS")
