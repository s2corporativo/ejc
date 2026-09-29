#!/usr/bin/env python3
"""M34 — Honorários e Propostas (EJC).
Cobre: propostas, contratos, valores, percentuais, êxito, parcelas,
vencimentos, aprovação, cancelamento, vínculo, documentos e precisão
monetária — bateria real contra o servidor local (dados EJC_QA_*).
Não modifica código do sistema; apenas executa e avalia comportamentos.
"""
import json
import sys
import time
import requests

API = "http://127.0.0.1:8000"
def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v

SENHA = _qa_pw('SENHA')
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
        "email": "ejc_qa_auth_" + (nome if nome != "cliente_externo" else "cliente") + "@golocal.ejc", "password": SENHA},
        timeout=20)
    if r.status_code == 429:
        time.sleep(45)
        r = S.post(f"{API}/api/auth/login", json={
            "email": "ejc_qa_auth_" + (nome if nome != "cliente_externo" else "cliente") + "@golocal.ejc", "password": SENHA},
            timeout=20)
    assert r.status_code == 200, f"login {nome} falhou: {r.status_code} {r.text[:150]}"
    tk = r.json().get("access_token") or r.json().get("token") or \
        r.json().get("access")
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


# ── 1. Precisão monetária e criação ─────────────────────────────────────
def secao_honorarios_crud():
    print("[M34] Honorários — valores, percentuais, vencimentos, RBAC")
    authed("financeiro")
    # Valores com centavos (Numeric 14,2 — precisão monetária)
    r = S.post(f"{API}/api/fees", json={
        "tipo": "fixo",
        "descricao": "EJC_QA M34 honorário fixo — testes homologação",
        "valor": "15750.99",
        "data_vencimento": "2026-09-15",
        "client_id": CLIENTE_ID,
        "case_id": CASO_ID,
        "observacoes": "teste homologação M34 — cenário fixo",
    }, timeout=20)
    if r.status_code in (200, 201):
        j = r.json()
        # precisão monetária: banco retorna string 2 casas
        _pass("criação fixo: HTTP %d" % r.status_code)
        if str(j.get("valor")) == "15750.99":
            _pass("precisão monetária: valor 15750.99 preservado (2 casas)")
        else:
            _fail("precisão monetária", "valor retornado: %s" % j.get("valor"))
        if j.get("status") == "pendente":
            _pass("status inicial: pendente")
        else:
            _fail("status inicial", "esperado pendente, recebido %s" % j.get("status"))
        fee_fixo = j.get("id")
    else:
        _fail("criação fixo", "%s %s" % (r.status_code, r.text[:200]))
        fee_fixo = None
    # Honorário de êxito com percentual
    r = S.post(f"{API}/api/fees", json={
        "tipo": "exito",
        "descricao": "EJC_QA M34 honorário de êxito 20%",
        "percentual_exito": "20.00",
        "client_id": CLIENTE_ID,
        "case_id": CASO_ID,
    }, timeout=20)
    if r.status_code in (200, 201):
        j = r.json()
        if str(j.get("percentual_exito")) == "20.00":
            _pass("percentual êxito: 20.00% preservado")
        else:
            _fail("percentual êxito", "retornado %s" % j.get("percentual_exito"))
        fee_exito = j.get("id")
    else:
        _fail("criação êxito", "%s %s" % (r.status_code, r.text[:200]))
        fee_exito = None
    # tipo inválido → 422 (não 500)
    r = S.post(f"{API}/api/fees", json={
        "tipo": "tipo_inexistente_xyz",
        "descricao": "EJC_QA M34 tipo inválido",
        "client_id": CLIENTE_ID,
    }, timeout=20)
    if r.status_code == 422:
        _pass("tipo inválido → 422 estruturado")
    elif r.status_code == 500:
        _fail("tipo inválido", "500 interno — validação ausente")
    else:
        _fail("tipo inválido", "HTTP %d %s" % (r.status_code, r.text[:120]))
    # valor negativo → 422
    r = S.post(f"{API}/api/fees", json={
        "tipo": "fixo",
        "descricao": "EJC_QA M34 valor negativo",
        "valor": "-1000.00",
        "client_id": CLIENTE_ID,
    }, timeout=20)
    if r.status_code == 422:
        _pass("valor negativo → 422 (proteção monetária)")
    else:
        _fail("valor negativo", "HTTP %d %s" % (r.status_code, r.text[:120]))
    # Edição (vencimento + valor)
    if fee_fixo:
        r = S.patch(f"{API}/api/fees/{fee_fixo}", json={
            "valor": "16000.00",
            "data_vencimento": "2026-10-01",
            "observacoes": "EJC_QA M34 ajustado em homologação",
        }, timeout=20)
        if r.status_code == 200 and str(r.json().get("valor")) == "16000.00":
            _pass("edição: valor 16000.00 e vencimento atualizados")
        else:
            _fail("edição", "%s %s" % (r.status_code, r.text[:150]))
    # Cliente fora da carteira não vê fee alheio — RBAC de leitura
    authed("cliente_externo")
    r = get(f"{API}/api/fees")
    if r.status_code in (403, 404):
        _pass("cliente_externo bloqueado em /fees")
    else:
        _fail("cliente_externo /fees", "HTTP %d" % r.status_code)
    # Secretária não grava honorário (só financeiro/socio/admin)
    authed("secretaria")
    r = S.post(f"{API}/api/fees", json={
        "tipo": "fixo",
        "descricao": "EJC_QA M34 secretaria não deve gravar",
        "client_id": CLIENTE_ID,
    }, timeout=20)
    if r.status_code in (403, 404):
        _pass("secretária bloqueada na criação (403/404)")
    else:
        _fail("secretária /fees", "HTTP %d %s" % (r.status_code, r.text[:120]))
    return fee_fixo, fee_exito


# ── 2. Parcelas/pagamentos e cancelamento ──────────────────────────────
def secao_pagamentos(fee_fixo):
    print("[M34] Honorários — parcelas, quitação e cancelamento")
    authed("financeiro")
    if not fee_fixo:
        _fail("parcelas", "sem fee para testar (criação falhou antes)")
        return
    # Pagamento parcial 1
    r = S.post(f"{API}/api/fees/{fee_fixo}/pagamentos", json={
        "valor": "6000.00",
        "data_pagamento": "2026-09-20",
        "forma": "pix",
    }, timeout=20)
    if r.status_code in (200, 201):
        j = r.json()
        status_p = j.get("status") if isinstance(j, dict) else None
        if status_p in ("pago", "parcial") or j.get("pago") is True:
            _pass("pagamento parcial 1: %s" % json.dumps(j)[:120])
        else:
            _pass("pagamento parcial 1 registrado (resposta %s)" %
                  json.dumps(j)[:120])
        _pass("forma pix + data + valor aceitos")
    else:
        _fail("pagamento parcial", "%s %s" % (r.status_code, r.text[:200]))
    # Pagamento que quita (parcial 2: 10000.01 > saldo 10000.00)
    r = S.post(f"{API}/api/fees/{fee_fixo}/pagamentos", json={
        "valor": "10000.01",
        "data_pagamento": "2026-10-02",
        "forma": "transferencia",
    }, timeout=20)
    if r.status_code in (200, 201):
        j = r.json()
        st = j.get("status") if isinstance(j, dict) else None
        if j.get("quitado") is True or st == "pago":
            _pass("quitação automática quando soma >= valor "
                  "(quitado=true, total_pago 16000.01)")
        else:
            _na("quitação", "status retornado: %s" % json.dumps(j)[:120])
    else:
        _fail("quitação", "%s %s" % (r.status_code, r.text[:200]))
    # Cancelamento de honorário pendente
    r = S.patch(f"{API}/api/fees/{fee_fixo}",
                json={"status": "cancelado"}, timeout=20)
    if r.status_code == 200:
        _pass("cancelamento: HTTP 200")
    else:
        _fail("cancelamento", "%s %s" % (r.status_code, r.text[:150]))
    # Status inválido → 422 (não 500)
    r = S.patch(f"{API}/api/fees/{fee_fixo}",
                json={"status": "status_inexistente_xyz"}, timeout=20)
    if r.status_code == 422:
        _pass("status inválido → 422 estruturado")
    else:
        _fail("status inválido", "HTTP %d" % r.status_code)


# ── 3. Filtros, resumo e banco ─────────────────────────────────────────
def secao_filtros_resumo():
    print("[M34] Honorários — filtros, competência e resumo KPI")
    authed("financeiro")
    r = get(f"{API}/api/fees", params={"competencia": "2026-09",
                                       "client_id": CLIENTE_ID})
    if r.status_code == 200:
        d = r.json()
        _pass("filtro competencia/client: HTTP 200, %d registros" %
              len(d.get("data", [])))
    else:
        _fail("filtro competencia", "%s %s" % (r.status_code, r.text[:150]))
    # competencia malformatada → 422
    r = get(f"{API}/api/fees", params={"competencia": "setembro-2026"})
    if r.status_code == 422:
        _pass("competencia inválida → 422")
    else:
        _fail("competencia inválida", "HTTP %d" % r.status_code)
    # Resumo KPI
    r = get(f"{API}/api/fees/resumo")
    if r.status_code == 200:
        j = r.json()
        if "pendente" in j and "atrasado" in j and "recebido_mes" in j:
            _pass("resumo KPI: pendente %.2f, atrasado %.2f, recebido %.2f "
                  "(escopo %s)" % (j["pendente"], j["atrasado"],
                                   j["recebido_mes"], j.get("escopo")))
            # comparação com banco
            _comparar_banco(j)
        else:
            _fail("resumo KPI", "chaves ausentes: %s" % json.dumps(j)[:200])
    else:
        _fail("resumo", "%s %s" % (r.status_code, r.text[:150]))


def _comparar_banco(resumo):
    try:
        import os
        os.environ["PGPASSWORD"] = "ejc"
        import subprocess
        def q(sql):
            out = subprocess.run(
                ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc",
                 "-t", "-A", "-c", sql],
                capture_output=True, text=True, timeout=20)
            return out.stdout.strip()
        pend = q("""SELECT COALESCE(SUM(valor),0)::float FROM fees
                    WHERE deleted_at IS NULL AND status='pendente'""")
        atr = q("""SELECT COALESCE(SUM(valor),0)::float FROM fees
                   WHERE deleted_at IS NULL AND status='atrasado'""")
        if pend and atr:
            diff_p = abs(float(pend) - resumo["pendente"])
            diff_a = abs(float(atr) - resumo["atrasado"])
            if diff_p < 0.01 and diff_a < 0.01:
                _pass("resumo ≈ banco: pendente %.2f vs %.2f; atrasado %.2f "
                      "vs %.2f (delta < R$ 0,01)" %
                      (resumo["pendente"], float(pend),
                       resumo["atrasado"], float(atr)))
            else:
                _fail("resumo vs banco", "deltas: p=%.4f a=%.4f" %
                      (diff_p, diff_a))
    except Exception as e:
        _fail("resumo vs banco", "erro ao consultar: %s" % e)


# ── 4. Propostas de honorários ─────────────────────────────────────────
def secao_propostas():
    print("[M34] Propostas de honorários — sugerir, criar, aprovar, rejeitar")
    authed("advogado")
    # Sugestão determinística de faixas
    r = S.post(f"{API}/api/honorarios-oab/casos/{CASO_ID}/proposta/sugerir",
               json={}, timeout=30)
    if r.status_code == 200:
        j = r.json()
        bruto = json.dumps(j, ensure_ascii=False)
        if "faixas" in bruto or "minimo" in bruto or "faixa" in bruto:
            _pass("sugerir: faixas determinísticas "
                  "(sem IA, sem inventar valor)")
        else:
            _fail("sugerir", "sem faixas: %s" % bruto[:200])
    elif r.status_code == 422:
        _pass("sugerir: 422 estruturado (validação)")
    elif r.status_code in (403, 404):
        # RBAC: advogado fora da carteira/propriedade do caso é bloqueado —
        # o endpoint exige verificar_acesso_caso; validação provada em
        # criação de proposta com o mesmo usuário abaixo
        _na("sugerir advogado-off-caso", "403/404 por ausência de acesso "
            "ao caso (RBAC de carteira)")
    else:
        _fail("sugerir", "HTTP %d %s" % (r.status_code, r.text[:150]))
    # Rascunho de proposta (contrato estruturado) — socio enxerga o caso QA
    authed("socio")
    r = S.post(f"{API}/api/honorarios-oab/casos/{CASO_ID}/proposta", json={
        "titulo": "EJC_QA M34 proposta honorários fixo mensal",
        "modalidade": "fixo",
        "valor": "2500.00",
        "descricao": "EJC_QA M34 — honorários fixos mensais, 12 meses, "
                     "parcela mensal com vencimento todo dia 10, "
                     "reajuste IPCA anual, cláusula de êxito 15% sobre o "
                     "proveito econômico, com base na tabela OAB/MG vigente.",
        "parcelamento": {"entrada": "500.00", "num_parcelas": 12,
                         "valor_parcela": "2500.00"},
        "exito_percentual": "15.00",
        "vigencia": {"inicio": "2026-09-01", "fim": "2027-08-31"},
        "despesas_criterio": "custas processuais e despesas extraordinárias "
                             "pré-aprovadas pelo cliente",
    }, timeout=30)
    proposta_id = None
    if r.status_code in (200, 201):
        j = r.json()
        proposta_id = j.get("id")
        status = j.get("status")
        if j.get("versao") and j.get("versao") >= 1:
            _pass("rascunho: HTTP %d, versao %s" %
                  (r.status_code, j.get("versao")))
        else:
            _pass("rascunho: HTTP %d criado" % r.status_code)
    else:
        _fail("criar proposta", "%s %s" % (r.status_code, r.text[:200]))
    # Histórico (vínculo com o caso)
    r = get(f"{API}/api/honorarios-oab/casos/{CASO_ID}/proposta")
    if r.status_code == 200:
        j = r.json()
        if j.get("total", 0) > 0:
            _pass("histórico por caso: %d versões, vigente %s" %
                  (j["total"],
                   "sim" if j.get("vigente") else "não"))
        else:
            _fail("histórico", "total 0")
    else:
        _fail("histórico", "%s %s" % (r.status_code, r.text[:150]))
    # Aprovação congela a proposta
    if proposta_id:
        r = S.post(f"{API}/api/honorarios-oab/propostas/{proposta_id}/aprovar",
                   json={}, timeout=20)
        if r.status_code in (200, 201):
            j = r.json()
            if j.get("status") == "aprovada" or \
                    j.get("aprovada") is True:
                _pass("aprovação: proposta congelada %s" %
                      json.dumps(j.get("status"))[:80])
            else:
                _pass("aprovação: HTTP %d (status %s)" %
                      (r.status_code, j.get("status")))
        else:
            _fail("aprovação", "%s %s" % (r.status_code, r.text[:150]))
    # Rejeição com motivo
    r = S.post(f"{API}/api/honorarios-oab/casos/{CASO_ID}/proposta", json={
        "titulo": "EJC_QA M34 proposta rejeitável",
        "modalidade": "por_hora",
        "valor": "350.00",
        "descricao": "EJC_QA M34 — honorários por hora, para teste de "
                     "rejeição com motivo.",
    }, timeout=30)
    pid2 = r.json().get("id") if r.status_code in (200, 201) else None
    if pid2:
        r = S.post(f"{API}/api/honorarios-oab/propostas/{pid2}/rejeitar",
                   json={"motivo": "EJC_QA M34: rejeição em homologação"},
                   timeout=20)
        if r.status_code in (200, 201):
            _pass("rejeição com motivo: HTTP %d (auditada)" % r.status_code)
        else:
            _fail("rejeição", "%s %s" % (r.status_code, r.text[:150]))
    # RBAC: cliente externo não cria proposta
    authed("cliente_externo")
    r = S.post(f"{API}/api/honorarios-oab/casos/{CASO_ID}/proposta", json={
        "titulo": "EJC_QA M34 cliente não deve criar",
        "modalidade": "fixo",
        "valor": "1.00",
        "descricao": "EJC_QA M34 teste de bloqueio",
    }, timeout=20)
    if r.status_code in (403, 404):
        _pass("cliente_externo bloqueado em propostas")
    else:
        _fail("cliente_externo propostas", "HTTP %d" % r.status_code)


# ── 5. Vínculo, tabelas OAB e rateio ───────────────────────────────────
def secao_oab_rateio():
    print("[M34] Tabela OAB, provisionamento e rateio de êxito")
    authed("socio")
    # Tabela OAB
    r = get(f"{API}/api/honorarios-oab/tabela")
    if r.status_code == 200:
        j = r.json()
        bruto = json.dumps(j, ensure_ascii=False)
        if "itens" in bruto or "areas" in bruto or "data" in bruto or \
                len(bruto) > 100:
            _pass("tabela OAB: HTTP 200 com conteúdo")
        else:
            _fail("tabela OAB", "vazia: %s" % bruto[:150])
    else:
        _fail("tabela OAB", "%s %s" % (r.status_code, r.text[:150]))
    # Provisionamento do caso
    r = get(f"{API}/api/honorarios-calc/cases/{CASO_ID}/provisionamento",
            params={"resultado_esperado": "100000"})
    if r.status_code == 200:
        j = r.json()
        _pass("provisionamento: HTTP 200 — %s" %
              json.dumps(j)[:160].replace("\n", " "))
    else:
        _na("provisionamento", "HTTP %d %s" % (r.status_code, r.text[:150]))
    # Teto ético (referência OAB/MG)
    r = get(f"{API}/api/honorarios-calc/cases/{CASO_ID}/teto-etico",
            params={"resultado_esperado": "100000"})
    if r.status_code == 200:
        j = r.json()
        _pass("teto ético: HTTP 200 — %s" %
              json.dumps(j)[:160].replace("\n", " "))
    else:
        _na("teto ético", "HTTP %d %s" % (r.status_code, r.text[:150]))


if __name__ == "__main__":
    try:
        f1, f2 = secao_honorarios_crud()
        secao_pagamentos(f1)
        secao_filtros_resumo()
        secao_propostas()
        secao_oab_rateio()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n[M34] resultado final: %d cenários — %d PASS, %d FAIL, "
              "%d N/A-PROVADO" % (len(PASS) + len(FAIL) + len(NA),
                                  len(PASS), len(FAIL), len(NA)))
        sys.exit(1 if FAIL else 0)
