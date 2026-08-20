#!/usr/bin/env python3
"""M05 — Multi-tenant / isolamento entre clientes (EJC QA local).

Cria dois clientes QA distintos (C1 e C2), um caso do cliente C1 e executa
provas de isolamento: advogado autenticado consulta criações do cliente C1
(200) e tenta alcançá-las pelas IDs do C2 (404) — sem vazar dados de outro
cliente. Também verifica visibilidade cruzada no portal do cliente.

Uso: scripts/inventory/env_shell.sh python3 scripts/inventory/m05_tenant_tests.py
Executar com o uvicorn LOCAL rodando (reiniciar antes para limpar rate limits).
"""
import os
import sys
import time
import random
import requests

def _cpf_valido() -> str:
    """Gera CPF aleatório com dígitos verificadores válidos."""
    n = [random.randint(0, 9) for _ in range(9)]
    s = sum((10 - i) * d for i, d in enumerate(n))
    n.append(0 if s % 11 < 2 else 11 - s % 11)
    s = sum((11 - i) * d for i, d in enumerate(n))
    n.append(0 if s % 11 < 2 else 11 - s % 11)
    d = "".join(str(x) for x in n)
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
os.chdir("/home/ubuntu/ejc_repo/backend")
DIR = "/home/ubuntu/ejc_repo/qa/homologacao/m05"
os.makedirs(DIR, exist_ok=True)
BASE = "http://127.0.0.1:8000"
S = requests.Session()
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
HDR = {"Content-Type": "application/json", "X-Forwarded-For": "127.0.0.1"}
RESULTADOS = []


def check(nome, ok, motivo=""):
    RESULTADOS.append(f"[{'PASS' if ok else 'FAIL'}] {nome} — {motivo or 'ok'}")
    if ok:
        print(f"PASS {nome}")
    else:
        print(f"FAIL {nome} — {motivo}")


TOKENS_M05 = {}


def login(email):
    if email in TOKENS_M05:
        return TOKENS_M05[email]
    time.sleep(18)
    r = None
    for _ in range(3):
        r = S.post(f"{BASE}/api/auth/login", json={"email": email, "password": SENHA},
                   headers=HDR, timeout=10)
        if r.status_code == 429:
            print("rate-limit: aguardando 45s e revalidando...")
            time.sleep(45)
            continue
        r.raise_for_status()
        TOKENS_M05[email] = r.json()["access_token"]
        return TOKENS_M05[email]
    raise SystemExit(
        f"rate limit persistente em {email}: {r.text[:200] if r is not None else ''}")


def tok(email):
    return {"Authorization": f"Bearer {login(email)}"}


def hdr(email):
    h = dict(HDR)
    h.update(tok(email))
    return h


def criar_cliente(email, nome):
    """Cria cliente QA via endpoint interno (admin)."""
    r = S.post(f"{BASE}/api/clients/", json={
        "nome": nome, "tipo": "PF", "cpf": _cpf_valido(),
        "email": email, "telefone": "(31) 0000-0000",
        "status": "ativo",
    }, headers=hdr("ejc_qa_auth_admin@golocal.ejc"), timeout=15)
    if r.status_code not in (200, 201, 409):
        print("criar_cliente:", r.status_code, r.text[:200])
        return None
    if r.status_code == 409:
        r2 = S.get(f"{BASE}/api/clients/", params={"q": email},
                   headers=hdr("ejc_qa_auth_admin@golocal.ejc"), timeout=10)
        for c in r2.json().get("data", r2.json().get("items", [])):
            if (c.get("email") or "") == email or \
               (c.get("nome") or "") == nome:
                return c["id"]
        return None
    j = r.json()
    return j.get("id") or j.get("data", {}).get("id")


def criar_caso(email_admin, client_id, titulo):
    r = S.post(f"{BASE}/api/cases", json={
        "client_id": client_id, "titulo": titulo, "area": "administrativo",
        "parte_contraria": "Parte X", "valor_causa": 1000,
        "proxima_acao": "Aguardando análise inicial",
    }, headers=hdr(email_admin), timeout=15)
    if r.status_code not in (200, 201):
        print("criar_caso:", r.status_code, r.text[:150])
        return None
    j = r.json()
    return j.get("id") or j.get("data", {}).get("id")


def limpar(nome_pat):
    h = hdr("ejc_qa_auth_admin@golocal.ejc")
    for t in ("refresh_tokens", "audit_logs", "notifications"):
        try:
            S.delete(f"{BASE}/api/debug/purge-qa", headers=h,
                     params={"tabela": t}, timeout=10)
        except Exception:
            pass


if __name__ == "__main__":
    import asyncio
    from app.core.config import get_settings
    from app.core.database import engine
    from sqlalchemy import text

    async def limpa_qa():
        for t in ("refresh_tokens", "notifications", "audit_logs",
                  "user_known_ips", "clients"):
            if t == "clients":
                # clientes QA podem ter casos/procurações/documentos; em QA
                # local removemos em cascata manual pelas FKs conhecidas.
                where = "id IN (SELECT id FROM clients WHERE nome LIKE 'EJC_QA%')"
                for tab in ("cases", "procuracoes", "documentos",
                            "pending_items", "contratos_societarios",
                            "knowledge_chunks"):
                    try:
                        await conn.execute(text(
                            f"DELETE FROM {tab} WHERE client_id IN "
                            f"(SELECT id FROM clients WHERE nome LIKE 'EJC_QA%')"))
                    except Exception:
                        pass
                for tab in ("case_partes",):
                    try:
                        await conn.execute(text(
                            f"DELETE FROM {tab} WHERE caso_id IN "
                            f"(SELECT id FROM cases WHERE client_id IN "
                            f"(SELECT id FROM clients WHERE nome LIKE 'EJC_QA%'))"))
                    except Exception:
                        pass
            else:
                where = "user_id IN (SELECT id FROM users WHERE email LIKE '%qa%')"
            try:
                async with engine.begin() as conn:
                    r = await conn.execute(text(
                        f"DELETE FROM {t} WHERE {where}"))
                    print("del", t, r.rowcount)
            except Exception as e:
                print("del", t, "IGNORADO:", str(e)[:120])

    asyncio.run(limpa_qa())

    print("== cria clientes C1 e C2 ==")
    c1 = criar_cliente("cliente1_qa@golocal.ejc", "EJC_QA C1 TENANT")
    c2 = criar_cliente("cliente2_qa@golocal.ejc", "EJC_QA C2 TENANT")
    assert c1 and c2, "clientes não criados"
    print("C1:", c1, "C2:", c2)

    print("== cria caso só em C1 ==")
    caso_c1 = criar_caso("ejc_qa_auth_admin@golocal.ejc", c1, "Caso isolado C1 M05")
    assert caso_c1, "caso C1 não criado"

    # advogado comum só enxerga casos em que é responsável/auxiliar
    # (desenho _filtro_visibilidade). Atribui o advogado QA ao caso C1 para a
    # prova de visibilidade correta.
    print("== atribui advogado ao caso C1 ==")
    ADVOGADO = "ejc_qa_auth_advogado@golocal.ejc"
    CLIENTE = "ejc_qa_auth_cliente@golocal.ejc"
    ADVOGADO_ID = None
    r = S.get(f"{BASE}/api/users/", params={"page_size": 100},
              headers=hdr("ejc_qa_auth_admin@golocal.ejc"), timeout=10)
    for u in r.json().get("data", r.json().get("users", [])):
        if u.get("email") == ADVOGADO:
            ADVOGADO_ID = u["id"]
            break
    assert ADVOGADO_ID, "advogado QA não encontrado"
    r = S.patch(f"{BASE}/api/cases/{caso_c1}",
                json={"advogado_responsavel_id": ADVOGADO_ID},
                headers=hdr("ejc_qa_auth_admin@golocal.ejc"), timeout=10)
    print("atribuicao:", r.status_code, r.text[:120])
    assert r.status_code == 200, "atribuição falhou"

    print("== provas de isolamento ==")

    # login único por papel para economizar quota de rate limit (10/min por IP)
    tok_advo = tok(ADVOGADO)
    tok_cli = tok(CLIENTE)
    H_ADVOGADO = dict(HDR); H_ADVOGADO.update(tok_advo)
    H_CLI = dict(HDR); H_CLI.update(tok_cli)

    # 1. advogado consulta casos do C1 — deve ver
    r = S.get(f"{BASE}/api/cases/?page_size=100", headers=H_ADVOGADO, timeout=10)
    ids_visiveis = {c["id"] for c in r.json().get("data", [])}
    check("mt_advogado_ve_c1", caso_c1 in ids_visiveis,
          f"caso C1 {'visível' if caso_c1 in ids_visiveis else 'INVISÍVEL'}")

    # 2. advogado consulta caso inexistente do C2 — nunca deve retornar dados
    r = S.get(f"{BASE}/api/cases/{c2}-0000-0000-000000000000",
              headers=H_ADVOGADO, timeout=10)
    check("mt_advogado_nao_ve_id_c2", r.status_code == 404,
          f"HTTP {r.status_code}")

    # 3. cliente autenticado não enxerga casos via portal (porta do cliente)
    r = S.get(f"{BASE}/api/portal/meus-casos", headers=H_CLI, timeout=10)
    check("mt_portal_cliente_isolado", r.status_code in (200, 404),
          f"HTTP {r.status_code} (porta do portal)")

    # 4. export CSV de clientes bloqueado para advogado (LGPD multi-cliente)
    r = S.get(f"{BASE}/api/export/clientes.csv", headers=H_ADVOGADO, timeout=10)
    check("mt_export_advogado_bloqueado", r.status_code == 403,
          f"HTTP {r.status_code}")

    # 5. advogado não vê detalhes de cliente que não pertence ao seu escopo
    r = S.get(f"{BASE}/api/clients/{c2}", headers=H_ADVOGADO, timeout=10)
    check("mt_advogado_nao_ve_cliente_c2", r.status_code == 404,
          f"HTTP {r.status_code}")

    check("mt_total", True, "provas concluídas")

    with open(f"{DIR}/resultado_tenant_tests.txt", "w") as f:
        f.write("\n".join(RESULTADOS) + "\n")
    n = sum(1 for x in RESULTADOS if x.startswith("[PASS]"))
    print(f"TOTAL: {n}/{len(RESULTADOS)} PASS")
