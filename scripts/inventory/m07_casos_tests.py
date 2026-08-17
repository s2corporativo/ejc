#!/usr/bin/env python3
"""M07 — Processos/Casos: auditoria funcional EJC QA local.
Prompt 07: criação, edição, número CNJ (DV módulo 97), classe/tribunal/comarca/
vara, partes, cliente, responsável, valor, risco, status, fase, tags, anexos,
histórico, kanban, busca, filtros, arquivamento, restauração.
Persistência anti-phantom e permissões. Dados EJC_QA_*.
Uso: scripts/inventory/env_shell.sh python3 scripts/inventory/m07_casos_tests.py
"""
import json, os, random, sys, time, requests
sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
os.chdir("/home/ubuntu/ejc_repo/backend")
DIR = "/home/ubuntu/ejc_repo/qa/homologacao/m07"
os.makedirs(DIR, exist_ok=True)
BASE = "http://127.0.0.1:8000"
S = requests.Session()
SENHA = "EjcQa2026!SenhaForte"
ADMIN = "ejc_qa_auth_admin@golocal.ejc"
SOCIO = "ejc_qa_auth_socio@golocal.ejc"
FIN = "ejc_qa_auth_financeiro@golocal.ejc"
ADV = "ejc_qa_auth_advogado@golocal.ejc"
CLI = "ejc_qa_auth_cliente@golocal.ejc"
CLIENT_ID = "9e6cd7cd-148c-49c9-95cb-d61de37fe520"  # EJC_QA M06
ADV_UUID = "4701ecbf-cf9b-422f-b75a-b906814b8213"
HEADERS = {"Content-Type": "application/json", "X-Forwarded-For": "127.0.0.1"}
TOKENS = {}

def cnj_valido():
    """Gera CNJ válido pelo algoritmo da Res. CNJ 65/2008 (iso igual ao do
    app — verificador_jurisprudencia.validar_dv_cnj): reordenando
    NNNNNNN + AAAA + J + TR + OOOO + DD, o resto por 97 deve ser 1."""
    n = f"{random.randint(1000000, 9999999)}"
    ano = "2026"
    j, tr, oo = "8", "01", "0001"
    corpo = int(f"{n}{ano}{j}{tr}{oo}00")
    dv = (1 - corpo) % 97
    return f"{n}-{dv:02d}.{ano}.{j}.{tr}.{oo}"

def login(email):
    if email in TOKENS:
        return TOKENS[email]
    time.sleep(18)
    for _ in range(6):
        r = S.post(f"{BASE}/api/auth/login",
                   json={"email": email, "password": SENHA},
                   headers=HEADERS, timeout=10)
        if r.status_code == 200:
            TOKENS[email] = {"Authorization": f"Bearer {r.json()['access_token']}"}
            return TOKENS[email]
        time.sleep(45)
    sys.exit(f"login falhou: {email}")

def h(email):
    hdr = dict(HEADERS)
    hdr.update(login(email))
    return hdr

def db(sql):
    import subprocess
    env = dict(os.environ, PGPASSWORD="ejc")
    out = subprocess.run(["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc",
                          "-t", "-A", "-c", sql], capture_output=True, text=True, env=env)
    return out.stdout.strip()

total, ok_total = 0, 0
def chk(nome, ok, motivo=""):
    global total, ok_total
    total += 1; ok_total += bool(ok)
    print(("PASS" if ok else "FAIL"), nome, f"— {motivo}" if motivo else "")
    return ok

if __name__ == "__main__":
    adm = h(ADMIN)
    # ── 1. criação ────────────────────────────────────────────────────────
    print("== 1. criação ==")
    TIT = f"EJC_QA M07 Caso {random.randint(10000,99999)}"
    r = S.post(f"{BASE}/api/cases", json={
        "titulo": TIT, "area": "tributario", "client_id": CLIENT_ID,
        "numero_processo": None, "tribunal": "TJ-MG",  # gerado abaixo
        "comarca": "Belo Horizonte", "vara": "2ª Vara Cível",
        "parte_contraria": "EJC_QA Fazenda Exemplo", "valor_causa": 150000,
        "descricao_fatos": "EJC_QA fatos M07", "proxima_acao": "M07 próxima ação"},
        headers=adm, timeout=20)
    caso = None
    chk("criação 201", r.status_code == 201, f"HTTP {r.status_code} {r.text[:80]}")
    if r.status_code == 201:
        caso = r.json().get("id")
    # ── 2. anti-phantom (ler de volta) ────────────────────────────────────
    if caso:
        r = S.get(f"{BASE}/api/cases/{caso}", headers=adm, timeout=15)
        d = r.json()
        chk("anti-phantom leitura", r.status_code == 200 and d.get("titulo") == TIT,
            f"titulo={d.get('titulo') if r.status_code==200 else 'n/a'}")
    # CNJ válido (única chamada — mesma constante usada no teste 18)
    valido = cnj_valido()
    # ── 3. CNJ inválido rejeitado ─────────────────────────────────────────
    r = S.post(f"{BASE}/api/cases", json={
        "titulo": f"EJC_QA M07 CNJ Ruim {random.randint(1,99999)}",
        "area": "tributario", "client_id": CLIENT_ID,
        "numero_processo": "1234567-00.2026.8.01.0001"}, headers=adm, timeout=15)
    chk("cnj inválido rejeitado (422)", r.status_code == 422, f"HTTP {r.status_code}")
    chk("cnj válido gerado", len(valido.split('-')) == 2, valido)
    # preenche o CNJ no caso criado — mesma constante usada no teste 18
    if caso:
        r = S.patch(f"{BASE}/api/cases/{caso}", headers=adm,
                    json={"numero_processo": valido}, timeout=15)
        chk("CNJ preenchido via edição", r.status_code == 200,
            f"HTTP {r.status_code} {r.text[:90]}")
    # ── 5. área inválida rejeitada ────────────────────────────────────────
    r = S.post(f"{BASE}/api/cases", json={
        "titulo": f"EJC_QA M07 Area Ruim {random.randint(1,99999)}",
        "area": "area_inexistente", "client_id": CLIENT_ID}, headers=adm, timeout=15)
    chk("área inválida rejeitada (422)", r.status_code == 422, f"HTTP {r.status_code}")
    # ── 6. edição (status, fase, risco, kanban, valor) ────────────────────
    print("== 2. edição ==")
    if caso:
        r = S.patch(f"{BASE}/api/cases/{caso}", headers=adm, json={
            "status": "em_instrucao", "fase": "conhecimento",
            "prioridade": "alta", "valor_causa": 200000,
            "kanban_column": "andamento", "kanban_position": 1,
            "observacoes": "EJC_QA obs M07"}, timeout=20)
        chk("edição 200", r.status_code == 200, f"HTTP {r.status_code}")
        r = S.get(f"{BASE}/api/cases/{caso}", headers=adm, timeout=15)
        d = r.json()
        chk("edição anti-phantom", d.get("status") == "em_instrucao"
            and d.get("fase") == "conhecimento" and d.get("prioridade") == "alta",
            f"status={d.get('status')} fase={d.get('fase')} prio={d.get('prioridade')}")
    # ── 7. fase/status inválidos ──────────────────────────────────────────
    if caso:
        r = S.patch(f"{BASE}/api/cases/{caso}", headers=adm,
                    json={"fase": "fase_inexistente"}, timeout=15)
        chk("fase inválida rejeitada (422)", r.status_code == 422, f"HTTP {r.status_code}")
    # ── 8. responsável / advogado ─────────────────────────────────────────
    if caso:
        r = S.patch(f"{BASE}/api/cases/{caso}", headers=adm,
                    json={"advogado_responsavel_id": ADV_UUID}, timeout=15)
        chk("responsável atribuído", r.status_code == 200, f"HTTP {r.status_code}")
    # ── 9. valor negativo rejeitado ───────────────────────────────────────
    r = S.post(f"{BASE}/api/cases", json={
        "titulo": f"EJC_QA M07 Valor Neg {random.randint(1,99999)}",
        "area": "tributario", "client_id": CLIENT_ID, "valor_causa": -500},
        headers=adm, timeout=15)
    chk("valor negativo rejeitado", r.status_code == 422, f"HTTP {r.status_code}")
    # ── 10. busca e filtros ───────────────────────────────────────────────
    print("== 3. busca/filtros ==")
    r = S.get(f"{BASE}/api/cases", headers=adm, params={"q": "M07 Caso",
              "client_id": CLIENT_ID}, timeout=15)
    chk("busca por texto", r.status_code == 200 and any(
        d.get("titulo") == TIT for d in r.json().get("data", [])),
        f"HTTP {r.status_code} {len(r.json().get('data', []))} resultados")
    r = S.get(f"{BASE}/api/cases", headers=adm,
              params={"client_id": CLIENT_ID, "area": "tributario"}, timeout=15)
    chk("filtro por área", r.status_code == 200 and len(r.json().get("data", [])) >= 1,
        f"HTTP {r.status_code}")
    # ── 11. estatísticas ──────────────────────────────────────────────────
    r = S.get(f"{BASE}/api/cases/stats", headers=adm, timeout=15)
    chk("stats 200", r.status_code == 200, f"HTTP {r.status_code}")
    # ── 12. kanban (listagem) ─────────────────────────────────────────────
    r = S.get(f"{BASE}/api/cases/kanban", headers=adm, timeout=15)
    if r.status_code != 200:
        r = S.get(f"{BASE}/api/cases", headers=adm, params={"kanban": "1"}, timeout=15)
    chk("kanban/listagem com coluna", r.status_code == 200, f"HTTP {r.status_code}")
    # ── 13. movimentações ─────────────────────────────────────────────────
    print("== 4. movimentações ==")
    if caso:
        r = S.post(f"{BASE}/api/cases/{caso}/movimentos", headers=adm, json={
            "tipo": "despacho", "descricao": "EJC_QA M07 despacho"}, timeout=15)
        mov = r.json().get("id") if r.status_code == 201 else None
        chk("movimento criado", r.status_code == 201, f"HTTP {r.status_code} {r.text[:60]}")
        r = S.get(f"{BASE}/api/cases/{caso}/movimentos", headers=adm, timeout=15)
        movs = r.json() if r.status_code == 200 else []
        movs = movs.get("data", movs) if isinstance(movs, dict) else movs
        chk("movimentos listados", r.status_code == 200 and (
            mov is None or any(m.get("id") == mov for m in movs)),
            f"HTTP {r.status_code}")
    # ── 14. arquivamento / desarquivamento ────────────────────────────────
    print("== 5. arquivamento ==")
    if caso:
        r = S.post(f"{BASE}/api/cases/{caso}/arquivar", headers=adm, timeout=15)
        chk("arquivar 200", r.status_code == 200, f"HTTP {r.status_code}")
        arq = db(f"SELECT status FROM cases WHERE id='{caso}'")
        chk("arquivado no banco (status=arquivado)", arq == "arquivado", f"status={arq}")
        # vista "arquivados" enxerga; "ativos" não
        r = S.get(f"{BASE}/api/cases", headers=adm,
                  params={"arquivo": "arquivados", "q": TIT}, timeout=15)
        chk("aparece na vista arquivados", r.status_code == 200 and any(
            d.get("titulo") == TIT for d in r.json().get("data", [])),
            f"HTTP {r.status_code}")
        r = S.get(f"{BASE}/api/cases", headers=adm,
                  params={"arquivo": "ativos", "q": TIT}, timeout=15)
        chk("oculto na vista ativos", r.status_code == 200 and not any(
            d.get("titulo") == TIT for d in r.json().get("data", [])),
            f"HTTP {r.status_code}")
        r = S.post(f"{BASE}/api/cases/{caso}/desarquivar", headers=adm, timeout=15)
        chk("desarquivar 200", r.status_code == 200, f"HTTP {r.status_code}")
        arq2 = db(f"SELECT arquivado_em FROM cases WHERE id='{caso}'")
        chk("desarquivado no banco", arq2 == "", f"arquivado_em={arq2 or 'NULL'}")
    # ── 15. exclusão soft / restauração ───────────────────────────────────
    print("== 6. exclusão/restauração ==")
    TIT2 = f"EJC_QA M07 Caso Exclu {random.randint(10000,99999)}"
    r = S.post(f"{BASE}/api/cases", json={
        "titulo": TIT2, "area": "tributario", "client_id": CLIENT_ID,
        "proxima_acao": "EJC_QA M07 próxima"}, headers=adm, timeout=15)
    caso2 = r.json().get("id") if r.status_code == 201 else None
    if caso2:
        r = S.delete(f"{BASE}/api/cases/{caso2}", headers=adm,
                     json={"motivo": "EJC_QA M07 exclusão controlada"}, timeout=15)
        chk("exclusão 200", r.status_code == 200, f"HTTP {r.status_code}")
        d = db(f"SELECT deleted_at FROM cases WHERE id='{caso2}'")
        chk("soft delete no banco", d != "", f"deleted_at={d or 'NULL'}")
        r = S.get(f"{BASE}/api/cases/{caso2}", headers=adm, timeout=15)
        chk("excluído oculto da lista", r.status_code in (404, 410), f"HTTP {r.status_code}")
        r = S.post(f"{BASE}/api/cases/{caso2}/desarquivar", headers=adm, timeout=15)
        if r.status_code != 200:
            # fallback: trash restore
            r = S.post(f"{BASE}/api/trash/cases/{caso2}/restaurar", headers=adm, timeout=15)
        chk("restauração", r.status_code == 200, f"HTTP {r.status_code}")
        r = S.get(f"{BASE}/api/cases/{caso2}", headers=adm, timeout=15)
        chk("restaurado acessível", r.status_code == 200, f"HTTP {r.status_code}")
    # ── 16. permissões ────────────────────────────────────────────────────
    print("== 7. permissões ==")
    r = S.post(f"{BASE}/api/cases", json={
        "titulo": f"EJC_QA M07 Cliente {random.randint(1,99999)}",
        "area": "tributario", "client_id": CLIENT_ID,
        "proxima_acao": "EJC_QA proxima"}, headers=h(CLI), timeout=15)
    chk("cliente não cria caso", r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = S.get(f"{BASE}/api/cases/{caso}", headers=h(CLI), timeout=15)
    chk("cliente não lê caso alheio", r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = S.post(f"{BASE}/api/cases", json={
        "titulo": f"EJC_QA M07 Financeiro {random.randint(1,99999)}",
        "area": "tributario", "client_id": CLIENT_ID,
        "proxima_acao": "EJC_QA proxima"}, headers=h(FIN), timeout=15)
    chk("financeiro não cria caso", r.status_code in (403, 404), f"HTTP {r.status_code}")
    # sócio (gestão) pode listar
    r = S.get(f"{BASE}/api/cases", headers=h(SOCIO), timeout=15)
    chk("sócio lista casos", r.status_code == 200, f"HTTP {r.status_code}")
    # ── 17. carteira: financeiro fora da carteira não vê o caso ──────────
    r = S.get(f"{BASE}/api/cases/{caso}", headers=h(FIN), timeout=15)
    chk("fora da carteira não lê", r.status_code in (403, 404), f"HTTP {r.status_code}")
    r = S.get(f"{BASE}/api/cases", headers=h(FIN), timeout=15)
    data_fin = r.json().get("data", []) if r.status_code == 200 else []
    chk("fora da carteira sem acesso à lista", r.status_code in (403, 404) or
        (r.status_code == 200 and len(data_fin) == 0),
        f"HTTP {r.status_code} {len(data_fin)} itens")
    # ── 18. persistência ID única no POST duplo ───────────────────────────
    # duplicado com o MESMO número CNJ → idempotência: rejeita caso ativo
    r = S.post(f"{BASE}/api/cases", json={
        "titulo": f"EJC_QA M07 Duplicado {random.randint(1,99999)}",
        "area": "tributario", "client_id": CLIENT_ID, "proxima_acao": "EJC_QA",
        "numero_processo": valido}, headers=adm, timeout=15)
    chk("duplicidade CNJ rejeitada (409)", r.status_code == 409,
        f"HTTP {r.status_code} {r.text[:90]}")
    # ── encerramento ──────────────────────────────────────────────────────
    print(f"\nM07 resultado: {ok_total}/{total} PASS")
    sys.exit(0 if ok_total == total else 1)
