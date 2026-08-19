#!/usr/bin/env python3
# Bateria de homologação — Geração documental no cadastro de cliente
# (procuração ad judicia + contrato de honorários, padrão OAB/MG).
# Executar via env_shell.sh; banco ejc local (PostgreSQL 16).
from __future__ import annotations
import json
import random
import sys
import time
import requests
from random import randint

BASE = "http://localhost:8000/api/v1"

USERS = {
    "admin": {"email": "ejc_qa_auth_admin@golocal.ejc", "senha": "EjcQa2026!SenhaForte"},
    "advogado": {"email": "ejc_qa_auth_advogado@golocal.ejc", "senha": "EjcQa2026!SenhaForte"},
}

def cpf_valido() -> str:
    n = [randint(0, 9) for _ in range(9)]
    s = sum((10 - i) * d for i, d in enumerate(n))
    n.append(0 if s % 11 < 2 else 11 - s % 11)
    s = sum((11 - i) * d for i, d in enumerate(n))
    n.append(0 if s % 11 < 2 else 11 - s % 11)
    d = "".join(str(x) for x in n)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"

def token_of(role: str) -> str:
    u = USERS[role]
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": u["email"], "password": u["senha"]}, timeout=10)
    assert r.status_code == 200, f"login {role} falhou: {r.status_code} {r.text[:200]}"
    return r.json()["access_token"]

PASS = FAIL = 0

def check(nome: str, cond: bool, motivo: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"[BATERIA] OK    {nome}")
    else:
        FAIL += 1
        print(f"[BATERIA] FAIL  {nome} {motivo}")

def main() -> int:
    global PASS, FAIL
    token_admin = token_of("admin")
    token_adv = token_of("advogado")
    h_admin = {"Authorization": f"Bearer {token_admin}"}
    h_adv = {"Authorization": f"Bearer {token_adv}"}

    # ── C1: criar cliente PF + gerar documentos no fluxo de cadastro ──────
    cpf = cpf_valido()
    payload = {
        "tipo": "PF",
        "nome": f"Cliente Bateria GerarDocs {randint(10000, 99999)}",
        "cpf": cpf,
        "email": f"cliente-bateria-{randint(1000,9999)}@exemplo.com",
        "telefone": "31999990000",
        "cidade": "Betim",
        "estado": "MG",
        "status": "ativo",
        "area_interesse": "Trabalhista",
    }
    r = requests.post(f"{BASE}/clients/", json=payload, headers=h_admin, timeout=15)
    check("C1 criar cliente: 201", r.status_code == 201,
          f"{r.status_code} {r.text[:300]}")
    assert r.status_code == 201, "cliente não criado; bateria interrompida"
    cliente_id = r.json()["id"]

    r = requests.post(f"{BASE}/clients/{cliente_id}/gerar-documentos",
                      json={}, headers=h_admin, timeout=15)
    if r.status_code == 429:  # quota kit-documental 5/min esgotada — espera e retoma
        time.sleep(62)
        r = requests.post(f"{BASE}/clients/{cliente_id}/gerar-documentos",
                          json={}, headers=h_admin, timeout=15)
    check("C1 gerar documentos: 201", r.status_code == 201, str(r.status_code))
    kit = r.json()
    print("    [C1] aviso repr:", repr(kit.get("aviso")))
    print("    [C1] ja_existia repr:", repr(kit.get("ja_existia")))
    check("C1 procuracao com conteúdo", "OUTORGANTE" in (kit["procuracao"]["conteudo"] or "")
          and "ad judicia" in (kit["procuracao"]["conteudo"] or "").lower())
    check("C1 contrato com OAB/MG", "OAB/MG" in (kit["contrato"]["conteudo"] or ""))
    check("C1 contrato com LGPD", "LGPD" in (kit["contrato"]["conteudo"] or ""))
    check("C1 status rascunho", kit["status"] == "rascunho")
    check("C1 avisa rascunho", "RASCUNHO" in kit.get("aviso", ""))
    check("C1 ja_existia=false", kit.get("ja_existia") is False)

    # ── C2: idempotência (reaproveita rascunhos) ──────────────────────────
    r = requests.post(f"{BASE}/clients/{cliente_id}/gerar-documentos",
                      json={}, headers=h_admin, timeout=15)
    check("C2 idempotência: 200/201", r.status_code in (200, 201), str(r.status_code))
    kit2 = r.json()
    check("C2 ja_existia=true", kit2.get("ja_existia") is True)
    check("C2 mesmo doc procuracao", kit2["procuracao"]["legal_doc_id"] == kit["procuracao"]["legal_doc_id"])

    # ── C3: forcar_novo regenera ──────────────────────────────────────────
    r = requests.post(f"{BASE}/clients/{cliente_id}/gerar-documentos",
                      json={"forcar_novo": True}, headers=h_admin, timeout=15)
    kit3 = r.json()
    check("C3 forcar_novo: novo doc", kit3.get("ja_existia") is False
          and kit3["procuracao"]["legal_doc_id"] != kit["procuracao"]["legal_doc_id"])

    # ── C4: poderes et extra explícitos ───────────────────────────────────
    r = requests.post(f"{BASE}/clients/{cliente_id}/gerar-documentos",
                      json={"tipo_poderes": "ad_judicia_et_extra", "forcar_novo": True},
                      headers=h_admin, timeout=15)
    kit4 = r.json()
    cont = kit4["procuracao"]["conteudo"] or ""
    check("C4 et extra: poderes gerais", "EXTRA" in cont.upper()
          and "RENUNCIAR" in cont.upper())

    # ── C5: tipo_poderes inválido → 422 ───────────────────────────────────
    r = requests.post(f"{BASE}/clients/{cliente_id}/gerar-documentos",
                      json={"tipo_poderes": "inexistente"}, headers=h_admin, timeout=15)
    check("C5 powers inválido: 422", r.status_code == 422, str(r.status_code))

    # ── C6: advogado só gera na própria carteira (LGPD/EOAB — titularidade).
    #     O cliente foi criado pelo admin: advogado não o vê (404 esperado,
    #     não vaza existência). Para validar o gate de advogado, cria-se um
    #     cliente vinculado ao advogado (responsavel_id = advogado).
    time.sleep(1.2)  # rate limit kit-documental 5/min
    cpf_adv = cpf_valido()
    r = requests.post(f"{BASE}/clients/", json={
        **payload, "cpf": cpf_adv, "nome": "Cliente Carteira Advogado"},
        headers=h_adv, timeout=15)
    check("C6 advogado cria na própria carteira: 201", r.status_code == 201,
          f"{r.status_code} {r.text[:200]}")
    if r.status_code == 201:
        cid_adv = r.json()["id"]
        r = requests.post(f"{BASE}/clients/{cid_adv}/gerar-documentos",
                          json={"forcar_novo": True}, headers=h_adv, timeout=15)
        check("C6 advogado gera em carteira própria: 201",
              r.status_code == 201, str(r.status_code))
    r = requests.post(f"{BASE}/clients/{cliente_id}/gerar-documentos",
                      json={"forcar_novo": True}, headers=h_adv, timeout=15)
    check("C6 404 em carteira alheia (não vaza existência)",
          r.status_code == 404, str(r.status_code))

    # ── C7: perfil abaixo de advogado (não testável sem user específico) —
    #     coberto por testes unitários; aqui valida apenas 401 sem token ─────
    r = requests.post(f"{BASE}/clients/{cliente_id}/gerar-documentos",
                      json={}, timeout=15)
    check("C7 sem token: 401", r.status_code == 401, str(r.status_code))

    # ── C8: auditoria GERAR_DOCS_CLIENTE persistida ────────────────────────
    # usa GET /audit-logs do módulo audit (token admin)
    time.sleep(0.5)
    time.sleep(0.5)
    r = requests.get(f"{BASE}/audit/", params={"acao": "GERAR_DOCS_CLIENTE"},
                     headers=h_admin, timeout=15)
    data = r.json()
    rows = data.get("data", data) if isinstance(data, dict) else data
    achou = any(
        (l.get("acao") == "GERAR_DOCS_CLIENTE" for l in (rows or []))
        if isinstance(rows, list) else False)
    check("C8 auditoria persistida", achou, f"resp={r.status_code}")

    print(f"\n=== RESUMO: {PASS} PASS, {FAIL} FAIL ===")
    return 1 if FAIL else 0

if __name__ == "__main__":
    sys.exit(main())
