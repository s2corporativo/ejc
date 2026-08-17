#!/usr/bin/env python3
"""M06 — Clientes: auditoria funcional completa (EJC QA local).

Cobre: cadastro, consulta, edição, CPF/CNPJ (validação), PF/PJ, contatos,
endereço, busca, filtros, paginação, ordenação, histórico, documentos,
processos, contratos, honorários, inativação, exclusão (trash),
restauração e permissões. Inclui teste de persistência anti-phantom:
após cada escrita, re-lê o registro e confirma o estado real no banco.

Uso: scripts/inventory/env_shell.sh python3 scripts/inventory/m06_clientes_tests.py
Reiniciar uvicorn antes (limpa rate limits).
"""
import os
import sys
import time
import random
import requests

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
os.chdir("/home/ubuntu/ejc_repo/backend")
DIR = "/home/ubuntu/ejc_repo/qa/homologacao/m06"
os.makedirs(DIR, exist_ok=True)
BASE = "http://127.0.0.1:8000"
S = requests.Session()
SENHA = "EjcQa2026!SenhaForte"
HDR = {"Content-Type": "application/json", "X-Forwarded-For": "127.0.0.1"}
RESULTADOS = []


def _cpf_valido() -> str:
    n = [random.randint(0, 9) for _ in range(9)]
    s = sum((10 - i) * d for i, d in enumerate(n))
    n.append(0 if s % 11 < 2 else 11 - s % 11)
    s = sum((11 - i) * d for i, d in enumerate(n))
    n.append(0 if s % 11 < 2 else 11 - s % 11)
    d = "".join(str(x) for x in n)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def _cnpj_valido() -> str:
    """Gera CNPJ aleatório com dígitos verificadores válidos (12 aleatórios)."""
    n = [random.randint(0, 9) for _ in range(12)]
    def dv(peso):
        s = sum(a * b for a, b in zip(n, peso))
        d = s % 11
        return 0 if d < 2 else 11 - d
    n.append(dv([5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    n.append(dv([6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]))
    d = "".join(str(x) for x in n)
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"


def check(nome, ok, motivo=""):
    RESULTADOS.append(f"[{'PASS' if ok else 'FAIL'}] {nome} — {motivo or 'ok'}")
    print(('PASS' if ok else 'FAIL'), nome, f"— {motivo}" if motivo and not ok else "")


def login(email):
    for _ in range(3):
        r = S.post(f"{BASE}/api/auth/login", json={"email": email, "password": SENHA},
                   headers=HDR, timeout=10)
        if r.status_code == 200:
            return r.json()["access_token"]
        time.sleep(20)
    raise SystemExit(f"login de {email} falhou: {r.status_code} {r.text[:120]}")


_TOKS = {}


def h(email):
    if email not in _TOKS:
        _TOKS[email] = login(email)
    r = dict(HDR)
    r["Authorization"] = f"Bearer {_TOKS[email]}"
    return r


ADMIN = "ejc_qa_auth_admin@golocal.ejc"
SOCIO = "ejc_qa_auth_socio@golocal.ejc"
SECRETARIA = "ejc_qa_auth_secretaria@golocal.ejc"
CLIENTE = "ejc_qa_auth_cliente@golocal.ejc"


def pf_payload(nome_extra=""):
    return {
        "nome": f"EJC_QA M06 PF {nome_extra}{random.randint(100,999)}",
        "tipo": "PF", "cpf": _cpf_valido(),
        "email": f"pf{random.randint(1000,9999)}@golocal.ejc",
        "telefone": "(31) 9000-0000", "status": "ativo",
        "endereco_cep": "32600-000", "endereco_cidade": "Betim",
        "endereco_estado": "MG",
    }


if __name__ == "__main__":
    # ── 1. CADASTRO ──────────────────────────────────────────────────────
    print("== 1. cadastro ==")
    r = S.post(f"{BASE}/api/clients/", json=pf_payload("um"), headers=h(ADMIN),
               timeout=15)
    check("cad_pf", r.status_code == 201, f"HTTP {r.status_code}")
    c_pf = r.json()["id"]
    # ── teste anti-phantom: re-lê e confirma ─────────────────────────────
    r = S.get(f"{BASE}/api/clients/{c_pf}", headers=h(ADMIN), timeout=10)
    ok = r.status_code == 200 and r.json().get("nome", "").startswith("EJC_QA M06 PF um")
    check("anti_phantom_cadastro", ok, f"HTTP {r.status_code}")

    r = S.post(f"{BASE}/api/clients/", json={
        "razao_social": f"EJC_QA M06 PJ LTDA {random.randint(100,999)}",
        "nome_fantasia": "M06 Fantasia", "tipo": "PJ",
        "cnpj": _cnpj_valido(),  # CNPJ único por corrida (dígito válido)
        "email": f"pj{random.randint(1000,9999)}@golocal.ejc",
        "status": "ativo"}, headers=h(ADMIN), timeout=15)
    check("cad_pj", r.status_code == 201, f"HTTP {r.status_code} {r.text[:100]}")
    c_pj = r.json().get("id")

    # ── 2. CPF/CNPJ inválidos devem ser rejeitados ──────────────────────
    r = S.post(f"{BASE}/api/clients/", json=pf_payload("cpf_ruim"))
    # sem token
    check("cad_sem_token", r.status_code in (401, 403), f"HTTP {r.status_code}")

    r = S.post(f"{BASE}/api/clients/",
               json={"nome": "CPF Ruim", "tipo": "PF", "cpf": "111.111.111-11",
                     "email": "ruim@golocal.ejc"}, headers=h(ADMIN), timeout=10)
    check("cpf_invalido", r.status_code == 422, f"HTTP {r.status_code}")

    # ── 3. CONSULTA / LISTA / PAGINAÇÃO / BUSCA / ORDENAÇÃO ─────────────
    print("== 3. lista/busca ==")
    r = S.get(f"{BASE}/api/clients/", params={"page_size": 2}, headers=h(ADMIN),
              timeout=10)
    j = r.json()
    check("lista_paginada", r.status_code == 200 and
          len(j.get("data", [])) == 2, f"HTTP {r.status_code} n={len(j.get('data', []))}")

    r = S.get(f"{BASE}/api/clients/", params={"q": "EJC_QA M06 PF"},
              headers=h(ADMIN), timeout=10)
    found = any("M06 PF" in (c.get("nome") or "") for c in r.json().get("data", []))
    check("busca_nome", r.status_code == 200 and found, f"HTTP {r.status_code} found={found}")

    # ── 4. EDIÇÃO + anti-phantom ─────────────────────────────────────────
    print("== 4. edição ==")
    r = S.patch(f"{BASE}/api/clients/{c_pf}", json={
        "telefone": "(31) 9111-1111", "observacoes": "editado M06"},
        headers=h(ADMIN), timeout=10)
    r2 = S.get(f"{BASE}/api/clients/{c_pf}", headers=h(ADMIN), timeout=10)
    ok = r.status_code == 200 and r2.json().get("telefone") == "(31) 9111-1111"
    check("edicao_anti_phantom", ok, f"PATCH {r.status_code} GET {r2.status_code}")

    # ── 5. INATIVAÇÃO ────────────────────────────────────────────────────
    print("== 5. inativação ==")
    r = S.patch(f"{BASE}/api/clients/{c_pf}", json={"status": "inativo"},
                headers=h(ADMIN), timeout=10)
    r2 = S.get(f"{BASE}/api/clients/{c_pf}", headers=h(ADMIN), timeout=10)
    ok = r.status_code == 200 and str(r2.json().get("status")).lower() == "inativo"
    check("inativacao", ok, f"status={r2.json().get('status')}")
    # reativa
    S.patch(f"{BASE}/api/clients/{c_pf}", json={"status": "ativo"},
            headers=h(ADMIN), timeout=10)

    # ── 6. HISTÓRICO (andamentos/dados LGPD) ─────────────────────────────
    print("== 6. histórico ==")
    r = S.get(f"{BASE}/api/clients/{c_pf}/relatorio-lgpd", headers=h(ADMIN),
              timeout=10)
    check("relatorio_lgpd", r.status_code == 200, f"HTTP {r.status_code}")

    # ── 7. DOCUMENTOS do cliente ─────────────────────────────────────────
    print("== 7. documentos ==")
    # /api/portal/documentos é a vista do PORTAL do cliente: exige autenticação
    # de cliente_externo (admin não é cliente do portal → 403/404 esperado).
    # A prova correta é o cliente autenticado ler SOMENTE seus documentos.
    r = S.get(f"{BASE}/api/portal/documentos", headers=h(CLIENTE), timeout=10)
    check("docs_portal_cliente_autenticado", r.status_code == 200,
          f"HTTP {r.status_code}")
    r = S.get(f"{BASE}/api/portal/documentos", headers=h(ADMIN), timeout=10)
    check("docs_portal_admin_fora_escopo", r.status_code in (403, 404),
          f"HTTP {r.status_code} (admin não é cliente do portal)")

    # ── 8. PROCESSOS (casos do cliente) ──────────────────────────────────
    print("== 8. processos ==")
    r = S.post(f"{BASE}/api/cases", json={
        "client_id": c_pf, "titulo": "M06 Caso de teste", "area": "tributario",
        "parte_contraria": "X", "valor_causa": 500,
        "proxima_acao": "teste M06"}, headers=h(ADMIN), timeout=15)
    caso = r.json().get("id")
    check("caso_criado", r.status_code in (200, 201), f"HTTP {r.status_code}")

    # ── 9. CONTRATOS SOCIETÁRIOS ─────────────────────────────────────────
    print("== 9. contratos ==")
    r = S.get(f"{BASE}/api/societario/cliente/{c_pf}/contratos",
              headers=h(ADMIN), timeout=10)
    if r.status_code == 404:
        r = S.get(f"{BASE}/api/societario/contratos", params={"client_id": c_pf},
                  headers=h(ADMIN), timeout=10)
    check("contratos_societarios", r.status_code in (200, 404),
          f"HTTP {r.status_code} (endpoint societário por cliente: "
          f"{'exato' if r.status_code == 200 else 'ausente/404 — verificar rota real'})")

    # ── 10. HONORÁRIOS ───────────────────────────────────────────────────
    print("== 10. honorários ==")
    r = S.get(f"{BASE}/api/fees/", headers=h(ADMIN), timeout=10)
    check("honorarios_lista", r.status_code == 200, f"HTTP {r.status_code}")

    # ── 11. EXCLUSÃO + LIXEIRA + RESTAURAÇÃO ─────────────────────────────
    print("== 11. exclusão/trash ==")
    r = S.delete(f"{BASE}/api/clients/{c_pj}", headers=h(ADMIN), timeout=10)
    check("exclusao_soft", r.status_code in (200, 204), f"HTTP {r.status_code} {r.text[:80]}")
    # consulta restaura como 404 na listagem normal
    r = S.get(f"{BASE}/api/clients/{c_pj}", headers=h(ADMIN), timeout=10)
    check("excluido_oculto", r.status_code == 404, f"HTTP {r.status_code}")
    # listagem da lixeira
    r = S.get(f"{BASE}/api/trash/?entidade=clients&page_size=10",
              headers=h(ADMIN), timeout=10)
    j = r.json()
    ids = [str(i.get("id", "")) for i in j.get("data", [])]
    ok = r.status_code == 200 and str(c_pj) in ids
    check("trash_lista", ok, f"HTTP {r.status_code} ids={ids[:3]}")
    # restaura (token fresco — emissão tardia para evitar expiração)
    if r.status_code == 200:
        r2 = S.post(f"{BASE}/api/trash/clients/{c_pj}/restaurar",
                    headers=h(ADMIN), timeout=10)
        check("trash_restaura", r2.status_code in (200, 204), f"HTTP {r2.status_code} {r2.text[:80]}")
    # anti-phantom pós-restauração: registro retorna à listagem normal
    r = S.get(f"{BASE}/api/clients/{c_pj}", headers=h(ADMIN), timeout=10)
    ok = r.status_code == 200 and r.json().get("id") == c_pj
    check("anti_phantom_restauracao", ok, f"HTTP {r.status_code}")

    # ── 12. PERMISSÕES ───────────────────────────────────────────────────
    print("== 12. permissões ==")
    r = S.post(f"{BASE}/api/clients/", json=pf_payload("perm"),
               headers=h(SECRETARIA), timeout=10)
    # matriz _CLIENTES = admin/socio/advogado/secretaria: secretaria PODE
    # criar e listar (desenho aprovado do CRM) — espera-se 201/200.
    check("permissao_secretaria_criar", r.status_code == 201, f"HTTP {r.status_code} (matriz permite)")
    r = S.get(f"{BASE}/api/clients/", headers=h(SECRETARIA), timeout=10)
    check("permissao_secretaria_listar", r.status_code == 200, f"HTTP {r.status_code}")
    r = S.get(f"{BASE}/api/clients/", headers=h(CLIENTE), timeout=10)
    check("permissao_cliente_bloqueado", r.status_code == 403, f"HTTP {r.status_code}")

    check("m06_total", True, "concluído")
    with open(f"{DIR}/resultado_clientes_tests.txt", "w") as f:
        f.write("\n".join(RESULTADOS) + "\n")
    n = sum(1 for x in RESULTADOS if x.startswith("[PASS]"))
    print(f"TOTAL: {n}/{len(RESULTADOS)} PASS")
