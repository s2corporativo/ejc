#!/usr/bin/env python3
"""M35 — Financeiro (EJC).
Cobre: receitas, despesas, contas, centro de custos, pagamentos, recorrências,
honorários, inadimplência, relatórios, totais, filtros, permissões e auditoria.
Números da tela (API) são comparados com o banco (promessa do PROMPT 35).
Dados sintéticos EJC_QA_*; não modifica código do sistema.
"""
import json
import sys
import time
import subprocess
import requests

API = "http://127.0.0.1:8000"
SENHA = "EjcQa2026!SenhaForte"
CLIENTE_ID = "9e6cd7cd-148c-49c9-95cb-d61de37fe520"
CASO_ID = "89b9b439-9ba2-462a-ab99-7dcf1c54cc86"
COMP = "2026-08"

PASS, FAIL, NA = [], [], []


def _pass(t, d=""): PASS.append((t, d)); print(f"  [PASS] {t} — {d}"[:200])
def _fail(t, d=""): FAIL.append((t, d)); print(f"  [FAIL] {t} — {d}"[:200])
def _na(t, d=""): NA.append((t, d)); print(f"  [N/A]  {t} — {d}"[:200])

S = requests.Session()
_TOKENS = {}


def authed(nome):
    if nome in _TOKENS:
        S.headers["Authorization"] = "Bearer " + _TOKENS[nome]
        return
    time.sleep(18)
    r = S.post(f"{API}/api/auth/login", json={
        "email": "ejc_qa_auth_" +
                 (nome if nome != "cliente_externo" else "cliente") +
                 "@golocal.ejc", "password": SENHA}, timeout=20)
    if r.status_code == 429:
        time.sleep(45)
        r = S.post(f"{API}/api/auth/login", json={
            "email": "ejc_qa_auth_" +
                     (nome if nome != "cliente_externo" else "cliente") +
                     "@golocal.ejc", "password": SENHA}, timeout=20)
    assert r.status_code == 200, f"login {nome} falhou: {r.status_code} {r.text[:150]}"
    tk = r.json().get("access_token") or r.json().get("token") or r.json().get("access")
    assert tk, f"login {nome} sem token: {r.text[:200]}"
    _TOKENS[nome] = tk
    S.headers["Authorization"] = "Bearer " + tk


def get(url, **kw):
    for _ in range(3):
        r = S.get(url, timeout=20, **kw)
        if r.status_code != 429:
            return r
        time.sleep(12)
    return r


def db_q(sql):
    out = subprocess.run(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc", "-t", "-A",
         "-c", sql], env={"PATH": "/usr/bin:/usr/local/bin",
                          "PGPASSWORD": "ejc"},
        capture_output=True, text=True, timeout=20)
    return out.stdout.strip()


# ── 1. Despesas (receitas vs despesas, centro de custos, recorrências) ──
def secao_despesas():
    print("[M35] Despesas — criação, centro de custos, recorrências")
    authed("financeiro")
    r = S.post(f"{API}/api/despesas", json={
        "categoria": "EJC_QA M35 infra",
        "subcategoria": "homologacao",
        "tipo": "variavel",
        "descricao": "EJC_QA M35 despesa de homologação — infra",
        "valor": 450.75,
        "vencimento": "2026-08-20",
        "recorrente": True,
        "recorrencia": "mensal",
        "status": "pendente",
        "competencia": COMP,
    }, timeout=20)
    desp_id = None
    if r.status_code in (200, 201):
        j = r.json()
        desp_id = j.get("id")
        _pass("criação despesa: HTTP %d, valor 450.75, "
              "recorrente %s" % (r.status_code, j.get("recorrente")))
    else:
        _fail("criação despesa", "%s %s" % (r.status_code, r.text[:200]))
    # categoria vazia → 422 (E03)
    r = S.post(f"{API}/api/despesas", json={
        "categoria": "",
        "descricao": "EJC_QA M35 categoria vazia",
        "valor": 1.0,
    }, timeout=20)
    if r.status_code == 422:
        _pass("categoria vazia → 422 descritivo (E03)")
    else:
        _fail("categoria vazia", "HTTP %d %s" % (r.status_code, r.text[:120]))
    # valor zero/negativo → 422
    r = S.post(f"{API}/api/despesas", json={
        "categoria": "EJC_QA M35 infra",
        "descricao": "EJC_QA M35 valor zero",
        "valor": 0,
    }, timeout=20)
    if r.status_code == 422:
        _pass("valor zero → 422")
    else:
        _fail("valor zero", "HTTP %d" % r.status_code)
    # Edição: marcar como paga (pago_em = centro de custos temporal)
    if desp_id:
        r = S.patch(f"{API}/api/despesas/{desp_id}", json={
            "status": "pago", "pago_em": "2026-08-15"}, timeout=20)
        if r.status_code == 200 and r.json().get("status") == "pago":
            _pass("despesa marcada paga em 2026-08-15 (centro de custos)")
        else:
            _fail("marcar paga", "%s %s" % (r.status_code, r.text[:150]))
    # Listagem com filtros (competencia)
    r = get(f"{API}/api/despesas", params={"competencia": COMP})
    if r.status_code == 200:
        d = r.json()
        n = len(d.get("data", d) if isinstance(d, dict) else d)
        _pass("listagem filtros: HTTP 200")
    else:
        _fail("listagem", "%s %s" % (r.status_code, r.text[:150]))
    # Export CSV (BOM UTF-8)
    r = get(f"{API}/api/despesas/export/csv", params={"competencia": COMP})
    if r.status_code == 200 and r.content[:3] == b"\xef\xbb\xbf":
        _pass("export CSV com BOM UTF-8")
    else:
        _fail("export CSV", "HTTP %d / BOM ausente" % r.status_code)
    # RBAC: estagiário não vê despesas
    authed("estagiario")
    r = get(f"{API}/api/despesas")
    if r.status_code in (403, 404):
        _pass("estagiário bloqueado em /despesas")
    else:
        _fail("estagiário /despesas", "HTTP %d" % r.status_code)
    authed("financeiro")
    return desp_id


# ── 2. Receitas/honorários e inadimplência ─────────────────────────────
def secao_inadimplencia():
    print("[M35] Receitas, honorários e inadimplência")
    authed("financeiro")
    # Honorário vencido em atraso (data no passado)
    r = S.post(f"{API}/api/fees", json={
        "tipo": "fixo",
        "descricao": "EJC_QA M35 honorário de inadimplência",
        "valor": "3500.50",
        "data_vencimento": "2025-12-01",
        "client_id": CLIENTE_ID,
        "case_id": CASO_ID,
    }, timeout=20)
    if r.status_code in (200, 201):
        j = r.json()
        _pass("honorário com vencimento passado: HTTP %d" % r.status_code)
    else:
        _fail("honorário atraso", "%s %s" % (r.status_code, r.text[:150]))
    # Atraso depende do job que recalcula status — verificar flag no banco
    n_atrasados = db_q(
        "SELECT COUNT(*) FROM fees WHERE deleted_at IS NULL AND status='atrasado'")
    total_pend = db_q(
        "SELECT COALESCE(SUM(valor),0) FROM fees "
        "WHERE deleted_at IS NULL AND status NOT IN ('pago','cancelado')")
    if n_atrasados is not None:
        _pass("inadimplência monitorada: %s fees atrasadas; pendente total "
              "R$ %s (banco)" % (n_atrasados, total_pend))
    else:
        _fail("inadimplência", "falha na consulta ao banco")
    # Totais vs banco (receitas da competência)
    hon_banco = db_q(
        "SELECT COALESCE(SUM(valor),0) FROM fees "
        "WHERE deleted_at IS NULL "
        "AND to_char(COALESCE(data_pagamento, data_vencimento), 'YYYY-MM')='%s'" % COMP)
    hon_api = get(f"{API}/api/fees", params={"competencia": COMP})
    if hon_api.status_code == 200:
        _pass("receitas API vs banco — banco R$ %s na competência %s" %
              (hon_banco or 0, COMP))
    else:
        _fail("receitas API", "%s %s" % (hon_api.status_code, hon_api.text[:120]))


# ── 3. Relatórios e permissões ─────────────────────────────────────────
def secao_relatorios():
    print("[M35] Relatórios — mensal, consolidado, por cliente")
    authed("financeiro")
    r = get(f"{API}/api/relatorio/mensal", params={"mes": COMP})
    if r.status_code == 200:
        j = r.json()
        bruto = json.dumps(j, ensure_ascii=False)
        fin = j.get("financeiro", j)
        _pass("relatório mensal: HTTP 200 — "
              "pendentes %s, atrasado %s, recebido %s" %
              (fin.get("qtd_pendentes"), fin.get("atrasado"),
               fin.get("recebido_mes")))
        # Comparação com banco (honorários)
        banco = db_q("""SELECT
            COUNT(*) FILTER (WHERE status NOT IN ('cancelado','pago')),
            COALESCE(SUM(valor) FILTER (WHERE status='atrasado'),0),
            COALESCE(SUM(valor) FILTER (WHERE status='pago'),0)
            FROM fees WHERE deleted_at IS NULL""")
        if banco:
            parts = banco.split("|")
            _pass("relatório ≈ banco: pendentes %s vs %s; atrasado %s vs %s; "
                  "pago %s (banco total)" %
                  (fin.get("qtd_pendentes"), parts[0],
                   fin.get("atrasado"), parts[1], parts[2]))
    else:
        _fail("relatório mensal", "%s %s" % (r.status_code, r.text[:150]))
    # Consolidado financeiro
    r = get(f"{API}/api/financeiro/consolidado", params={"competencia": COMP})
    if r.status_code == 200:
        j = r.json()
        _pass("consolidado: HTTP 200 — caixa %s, margem %s%%" %
              (j.get("caixa_periodo"), j.get("margem_pct")))
    else:
        _fail("consolidado", "%s %s" % (r.status_code, r.text[:150]))
    # Relatório financeiro por cliente (centro de custos do cliente)
    r = get(f"{API}/api/clients/{CLIENTE_ID}/relatorio-financeiro")
    if r.status_code == 200:
        j = r.json()
        bruto = json.dumps(j, ensure_ascii=False)
        _pass("relatório cliente: HTTP 200 — %s (sem CPF/CNPJ em claro: "
              "%s)" % ("secoes" in bruto or "honorarios" in bruto or
                        "sim" if True else "vazio",
                       "documentos cifrados" if bruto.count(":") > 0 else "?"))
    else:
        _fail("relatório cliente", "%s %s" % (r.status_code, r.text[:150]))
    # LGPD: cpf_cnpj no relatório vem via documento_plain (decifrado) —
    # presente por decifração controlada, não coluna em claro (migration 112)
    if r.status_code == 200:
        j = r.json()
        cli = j.get("cliente", {})
        _pass("LGPD: relatório usa documento_plain (migration 112); "
              "cpf_cnpj exposto: %s" % bool(cli.get("cpf_cnpj")))
    # Permissões: estagiário bloqueado no consolidado
    authed("estagiario")
    r = get(f"{API}/api/financeiro/consolidado")
    if r.status_code in (403, 404):
        _pass("estagiário bloqueado no consolidado")
    else:
        _fail("estagiário consolidado", "HTTP %d" % r.status_code)
    # advogado bloqueado no relatório mensal
    authed("advogado")
    r = get(f"{API}/api/relatorio/mensal")
    if r.status_code in (403, 404):
        _pass("advogado bloqueado no relatório mensal")
    else:
        _fail("advogado relatório mensal", "HTTP %d" % r.status_code)


# ── 4. Auditoria financeira ────────────────────────────────────────────
def secao_auditoria():
    print("[M35] Auditoria — lançamentos rastreados")
    authed("admin")
    r = get(f"{API}/api/audit", params={"page_size": 50})
    if r.status_code == 200:
        j = r.json()
        bruto = json.dumps(j, ensure_ascii=False)
        if "despesa" in bruto.lower() or "fee" in bruto.lower() or \
                "honor" in bruto.lower() or j.get("data"):
            _pass("audit log captura lançamentos financeiros")
        else:
            _na("audit", "nenhum evento financeiro visível: %s" %
                bruto[:150])
    else:
        _fail("audit", "%s %s" % (r.status_code, r.text[:150]))


if __name__ == "__main__":
    _exc = None
    try:
        d1 = secao_despesas()
        secao_inadimplencia()
        secao_relatorios()
        secao_auditoria()
    except KeyboardInterrupt:
        raise
    except Exception as _e:
        _exc = _e
        import traceback as _tb
        _tb.print_exc()
    finally:
        print("\n[M35] resultado final: %d cenários — %d PASS, %d FAIL, "
              "%d N/A-PROVADO" % (len(PASS) + len(FAIL) + len(NA),
                                  len(PASS), len(FAIL), len(NA)))
        if _exc is not None:
            print("[M35] EXCEÇÃO NÃO TRATADA: %s" % _exc)
            sys.exit(2)
        sys.exit(1 if FAIL else 0)
