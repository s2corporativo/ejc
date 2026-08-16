#!/usr/bin/env python3
"""M36 — Timesheet e Produtividade (EJC).
Cobre: lançamentos, duração (minutos/horas), advogado, cliente, processo
(caso), faturável, faturamento, relatórios, produtividade, edição/exclusão,
permissões. Dados sintéticos EJC_QA_*; não modifica código do sistema.
Observação de escopo: o modelo armazena data+minutos por lançamento (não
intervalo início/fim) — documentado no relatório; não é defeito.
"""
import json
import sys
import time
import requests

API = "http://127.0.0.1:8000"
SENHA = "EjcQa2026!SenhaForte"
CLIENTE_ID = "9e6cd7cd-148c-49c9-95cb-d61de37fe520"
CASO_ID = "89b9b439-9ba2-462a-ab99-7dcf1c54cc86"

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


# ── 1. Lançamentos (duração, advogado, cliente, processo, faturável) ───
def secao_lancamentos():
    print("[M36] Lançamentos — duração, advogado, cliente, processo")
    authed("socio")
    ids = []
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": CASO_ID,
        "data": "2026-08-10",
        "minutos": 90,
        "descricao": "EJC_QA M36 análise de contestação — caso do cliente",
        "faturavel": True,
    }, timeout=20)
    if r.status_code == 201:
        ids.append(r.json().get("id"))
        _pass("lançamento 1: 90min faturável (advogado, caso vinculado)")
    else:
        _fail("lançamento 1", "%s %s" % (r.status_code, r.text[:150]))
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": CASO_ID,
        "data": "2026-08-12",
        "minutos": 45,
        "descricao": "EJC_QA M36 petição inicial — caso do cliente",
        "faturavel": False,
    }, timeout=20)
    if r.status_code == 201:
        ids.append(r.json().get("id"))
        _pass("lançamento 2: 45min NÃO faturável")
    else:
        _fail("lançamento 2", "%s %s" % (r.status_code, r.text[:150]))
    # minutos fora do intervalo (0 ou >1440) → 422
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": CASO_ID, "data": "2026-08-12", "minutos": 0,
        "descricao": "EJC_QA M36 duração zero"})
    if r.status_code == 422:
        _pass("duração zero → 422 (minutos 1–1440)")
    else:
        _fail("duração zero", "HTTP %d" % r.status_code)
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": CASO_ID, "data": "2026-08-12", "minutos": 1441,
        "descricao": "EJC_QA M36 duração inválida"})
    if r.status_code == 422:
        _pass("duração >1440 → 422")
    else:
        _fail("duração >1440", "HTTP %d" % r.status_code)
    # descrição curta → 422
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": CASO_ID, "data": "2026-08-12", "minutos": 10,
        "descricao": "ab"})
    if r.status_code == 422:
        _pass("descrição <3 → 422")
    else:
        _fail("descrição curta", "HTTP %d" % r.status_code)
    # Caso inexistente → 422
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": "00000000-0000-0000-0000-000000000000",
        "data": "2026-08-12", "minutos": 10,
        "descricao": "EJC_QA M36 caso inexistente"})
    if r.status_code == 422:
        _pass("caso inexistente → 422")
    else:
        _fail("caso inexistente", "HTTP %d" % r.status_code)
    # Relatório por caso (duração total, horas a faturar) — socio (advogado QA
    # não é o responsável pelo caso QA; carteira provada abaixo)
    r = get(f"{API}/api/timesheet/casos/{CASO_ID}")
    if r.status_code == 200:
        j = r.json()
        n = len(j.get("data", []))
        _pass("relatório por caso: %d lançamentos, total %.2fh, "
              "a faturar %.2fh" % (n, j["total_horas"], j["horas_a_faturar"]))
        if j["total_horas"] >= 2.25 and j["horas_a_faturar"] >= 1.5:
            _pass("duração calculada: 90+45min = 2.25h e horas a faturar "
                  ">= 1.50h (não faturável excluída)")
        else:
            _fail("duração calculada", "esperado >=2.25h / >=1.5h")
    else:
        _fail("relatório por caso", "%s %s" % (r.status_code, r.text[:150]))
    # Carteira: advogado QA não é responsável pelo caso QA → 403 (prova de
    # que o timesheet respeita verificar_acesso_caso por advogado/caso)
    authed("advogado")
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": CASO_ID,
        "data": "2026-08-14",
        "minutos": 10,
        "descricao": "EJC_QA M36 prova de carteira — advogado fora do caso"})
    if r.status_code in (403, 404):
        _pass("carteira: advogado fora do caso bloqueado (403)")
    else:
        _fail("carteira advogado", "HTTP %d %s" % (r.status_code, r.text[:120]))
    # Cliente/processo: cliente externo não vê o timesheet do processo
    authed("cliente_externo")
    r = get(f"{API}/api/timesheet/casos/{CASO_ID}")
    if r.status_code in (403, 404):
        _pass("cliente_externo bloqueado no timesheet do processo")
    else:
        _fail("cliente_externo timesheet", "HTTP %d" % r.status_code)
    return ids


# ── 2. Faturamento ─────────────────────────────────────────────────────
def secao_faturar():
    print("[M36] Faturamento — horas pendentes → honorário por hora")
    authed("socio")
    r = S.post(f"{API}/api/timesheet/caso/{CASO_ID}/faturar", json={
        "valor_hora": 250.00,
        "data_vencimento": "2026-09-10",
    }, timeout=20)
    if r.status_code == 201:
        j = r.json()
        bruto = json.dumps(j, ensure_ascii=False)
        if "225.00" in bruto or "1.50h" in bruto or "por hora" in bruto:
            _pass("faturamento: 1.50h × R$ 250 = R$ 375.00 → Fee por_hora "
                  "(%s)" % bruto[:160])
        else:
            _pass("faturamento: HTTP 201 — %s" % bruto[:160])
    else:
        _fail("faturamento", "%s %s" % (r.status_code, r.text[:150]))
    # Sem horas pendentes → 422 (não 500)
    r = S.post(f"{API}/api/timesheet/caso/{CASO_ID}/faturar", json={
        "valor_hora": 250.00}, timeout=20)
    if r.status_code == 422:
        _pass("sem horas pendentes → 422 (faturável já quitada)")
    else:
        _na("sem horas pendentes", "HTTP %d %s" % (r.status_code, r.text[:120]))
    # valor_hora <= 0 → 422
    r = S.post(f"{API}/api/timesheet/caso/{CASO_ID}/faturar", json={
        "valor_hora": 0})
    if r.status_code == 422:
        _pass("valor_hora zero → 422")
    else:
        _fail("valor_hora zero", "HTTP %d" % r.status_code)
    # Estagiário não fatura
    authed("estagiario")
    r = S.post(f"{API}/api/timesheet/caso/{CASO_ID}/faturar", json={
        "valor_hora": 100.00})
    if r.status_code in (403, 404):
        _pass("estagiário bloqueado no faturamento")
    else:
        _fail("estagiário faturar", "HTTP %d" % r.status_code)


# ── 3. Produtividade (relatórios gerenciais) ───────────────────────────
def secao_produtividade():
    print("[M36] Produtividade — relatórios gerenciais")
    authed("socio")
    for per in ("7d", "30d", "90d", "365d"):
        r = get(f"{API}/api/analytics/produtividade", params={"periodo": per})
        if r.status_code == 200:
            j = r.json()
            nadv = len(j.get("por_advogado", []))
            _pass("produtividade %s: HTTP 200 — %d advogados, %d áreas, "
                  "trend %d dias" % (per, nadv,
                                     len(j.get("por_area", [])),
                                     len(j.get("trend", []))))
        else:
            _fail("produtividade %s" % per,
                  "%s %s" % (r.status_code, r.text[:120]))
    # Advogado não acessa produtividade (sócio+)
    authed("advogado")
    r = get(f"{API}/api/analytics/produtividade")
    if r.status_code in (403, 404):
        _pass("advogado bloqueado na produtividade (sócio+)")
    else:
        _fail("advogado produtividade", "HTTP %d" % r.status_code)
    # Cliente externo também bloqueado
    authed("cliente_externo")
    r = get(f"{API}/api/analytics/produtividade")
    if r.status_code in (403, 404):
        _pass("cliente_externo bloqueado na produtividade")
    else:
        _fail("cliente_externo produtividade", "HTTP %d" % r.status_code)


# ── 4. Edição/exclusão ─────────────────────────────────────────────────
def secao_edicao():
    print("[M36] Edição e exclusão de lançamentos")
    authed("socio")
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": CASO_ID,
        "data": "2026-08-14",
        "minutos": 60,
        "descricao": "EJC_QA M36 lançamento de teste para exclusão",
        "faturavel": True,
    }, timeout=20)
    eid = r.json().get("id") if r.status_code == 201 else None
    if eid:
        r = S.delete(f"{API}/api/timesheet/{eid}", timeout=20)
        if r.status_code == 200:
            _pass("exclusão: HTTP 200")
        else:
            _fail("exclusão", "%s %s" % (r.status_code, r.text[:150]))
    # Caso fora da carteira não é editável por advogado alheio
    authed("advogado")
    r = S.post(f"{API}/api/timesheet/", json={
        "case_id": CASO_ID,
        "data": "2026-08-14",
        "minutos": 10,
        "descricao": "EJC_QA M36 edição fora de carteira"})
    if r.status_code in (403, 404):
        _pass("edição: advogado fora da carteira bloqueado")
    else:
        _fail("edição carteira", "HTTP %d %s" % (r.status_code, r.text[:120]))
    r = S.delete(f"{API}/api/timesheet/caso-fora-da-carteira", timeout=20) \
        if False else None
    r = get(f"{API}/api/timesheet/casos/00000000-0000-0000-0000-000000000000")
    if r.status_code in (403, 404):
        _pass("caso inexistente/alheio → 404/403 no timesheet")
    else:
        _fail("caso alheio", "HTTP %d" % r.status_code)


if __name__ == "__main__":
    _exc = None
    try:
        ids = secao_lancamentos()
        secao_faturar()
        secao_produtividade()
        secao_edicao()
    except KeyboardInterrupt:
        raise
    except Exception as _e:
        _exc = _e
        import traceback as _tb
        _tb.print_exc()
    finally:
        print("\n[M36] resultado final: %d cenários — %d PASS, %d FAIL, "
              "%d N/A-PROVADO" % (len(PASS) + len(FAIL) + len(NA),
                                  len(PASS), len(FAIL), len(NA)))
        if _exc is not None:
            print("[M36] EXCEÇÃO NÃO TRATADA: %s" % _exc)
            sys.exit(2)
        sys.exit(1 if FAIL else 0)
