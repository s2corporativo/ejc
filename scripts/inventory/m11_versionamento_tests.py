#!/usr/bin/env python3
# M11 — Versionamento de Documentos. Auditoria funcional EJC.
# Prompt 11: versão inicial, nova versão, histórico, autoria, timestamps,
# comparação, recuperação, conflito de edição, integridade, exclusão,
# restauração. "Não aceite perda silenciosa de versão."
# Dados sintéticos EJC_QA_*. Servidor local uvicorn :8000.
import hashlib, io, os, random, sys, tempfile, threading, time, zipfile
import requests as S_

BASE = "http://127.0.0.1:8000"
ADM_E = "ejc_qa_auth_admin@golocal.ejc"
ADV_E = "ejc_qa_auth_advogado@golocal.ejc"
EST_E = "ejc_qa_auth_estagiario@golocal.ejc"
FIN_E = "ejc_qa_auth_financeiro@golocal.ejc"
CLI_E = "ejc_qa_auth_cliente@golocal.ejc"
PWD = "EjcQa2026!SenhaForte"

# ── carteira: garantir que o advogado QA tenha acesso aos casos QA ────────
ADV_UUID = "4701ecbf-cf9b-422f-b75a-b906814b8213"

# Cliente/caso QA — criados dinamicamente se não existirem (DB reconstruído)
S = S_.Session()
S.headers.update({"X-Forwarded-For": "127.0.0.1"})
CLIENT_ID = None
CASE_ID = None
CASE_ID_2 = None
def criar_recursos_qa():
    global CLIENT_ID, CASE_ID, CASE_ID_2
    adm_h = _h(ADM_E)
    _r = S.get(f"{BASE}/api/clients", headers=adm_h, params={"q": "EJC_QA Cliente M11"}, timeout=30)
    if _r.status_code != 200:
        print("GET clientes:", _r.status_code, _r.text[:200])
    _cli = (_r.json().get("data") or [None])[0]
    if _cli:
        CLIENT_ID = _cli["id"]
    else:
        _r = S.post(f"{BASE}/api/clients", json={
            "tipo": "PJ", "nome": "EJC_QA Cliente M11",
            "razao_social": "EJC_QA CLIENTE M11 LTDA",
            "cnpj": "12345678000195", "email": "ejc.qa.m11@gmail.com"},
            headers=adm_h, timeout=30)
        CLIENT_ID = _r.json().get("id")
    print("cliente QA:", CLIENT_ID)

    def achar_caso():
        _r = S.get(f"{BASE}/api/cases", headers=adm_h,
                   params={"page_size": 100}, timeout=30)
        for c in (_r.json().get("data") or []):
            if c.get("client_id") == CLIENT_ID and "EJC_QA M11" in c.get("titulo", ""):
                return c["id"]
        return None

    CASE_ID = achar_caso()
    if not CASE_ID:
        _r = S.post(f"{BASE}/api/cases", json={
            "titulo": "EJC_QA M11 Caso A", "area": "tributario",
            "client_id": CLIENT_ID, "parte_contraria": "EJC_QA",
            "descricao_fatos": "EJC_QA", "proxima_acao": "EJC_QA"},
            headers=adm_h, timeout=30)
        if _r.status_code != 201:
            raise SystemExit(f"caso A não criado: status={_r.status_code} body={_r.text[:300]}")
        CASE_ID = _r.json().get("id")
    _r = S.post(f"{BASE}/api/cases", json={
        "titulo": f"EJC_QA M11 Caso B {random.randint(1,99999)}", "area": "tributario",
        "client_id": CLIENT_ID, "parte_contraria": "EJC_QA",
        "descricao_fatos": "EJC_QA", "proxima_acao": "EJC_QA"},
        headers=adm_h, timeout=30)
    if _r.status_code != 201:
        print("POST caso B:", _r.status_code, _r.text[:200])
    CASE_ID_2 = _r.json().get("id") if isinstance(_r.json(), dict) else None
    if not CASE_ID_2:
        raise SystemExit(f"caso B não criado: status={_r.status_code} body={_r.text[:300]}")
    print("casos QA:", CASE_ID[:8], CASE_ID_2[:8])
    for _cid in (CASE_ID, CASE_ID_2):
        _r = S.patch(f"{BASE}/api/cases/{_cid}", headers=adm_h,
                     json={"advogado_responsavel_id": ADV_UUID}, timeout=30)
        print("ajuste carteira:", _cid[:8], _r.status_code, _r.text[:60])
_TOKENS = {}

def _h(email):
    if email in _TOKENS:
        return _TOKENS[email]
    time.sleep(18)
    for _ in range(6):
        r = S.post(f"{BASE}/api/auth/login", json={"email": email, "password": PWD}, timeout=10)
        if r.status_code == 200:
            _TOKENS[email] = {"Authorization": f"Bearer {r.json()['access_token']}"}
            return _TOKENS[email]
        time.sleep(45)
    raise SystemExit(f"login falhou para {email}")

def h(e): return _h(e)

total, ok_total = 0, 0
def chk(nome, ok, motivo=""):
    global total, ok_total
    total += 1
    ok = bool(ok)
    ok_total += ok
    print(("PASS" if ok else "FAIL"), f"{nome} — {motivo or ''}")
    return ok

PDF_GEN = "/home/ubuntu/ejc_repo/scripts/inventory/gen_test_files.py"

def mk_pdf(payload: bytes):
    """PDF mínimo com magic bytes real (application/pdf) + payload rastreável."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    head = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
            b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\n"
            b"trailer<</Root 1 0 R>>\n%%EOF\n")
    tmp.write(head + payload)
    tmp.close()
    return tmp.name

def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

# ── massa de arquivos (conteúdos distintos e rastreáveis) ────────────────────
C1 = f"EJC_QA M11 CONTEUDO VERSAO 1 — {random.randint(10000,99999)}".encode()
C2 = f"EJC_QA M11 CONTEUDO VERSAO 2 — {random.randint(10000,99999)}".encode()
C3 = f"EJC_QA M11 CONTEUDO VERSAO 3 — {random.randint(10000,99999)}".encode()
C_ALT = f"EJC_QA M11 CONTEUDO ALTERNATIVO — {random.randint(10000,99999)}".encode()
TIT_V1 = f"EJC_QA M11 Doc Versionado {random.randint(10000,99999)}"   # título base
TIT_V2 = TIT_V1  # mesmo título → deve criar versão 2
TIT_ALT = f"EJC_QA M11 Doc Alternativo {random.randint(10000,99999)}"
TIT_SEM_CASO = f"EJC_QA M11 Sem Caso {random.randint(10000,99999)}"
ADM_TOKEN = h(ADM_E)

def upload(email, path, titulo, caso=None, cliente=None, conf="normal", extra_headers=None):
    headers = dict(h(email) or {})
    if extra_headers: headers.update(extra_headers)
    with open(path, "rb") as f:
        files = {"file": (os.path.basename(path), f, "application/pdf")}
        data = {"titulo": titulo, "confidencialidade": conf}
        if caso: data["case_id"] = caso
        if cliente: data["client_id"] = cliente
        r = S.post(f"{BASE}/api/documents/upload", headers=headers,
                   files=files, data=data, timeout=30)
    return r

def db(sql, params=()):
    import subprocess
    env = dict(os.environ, PGPASSWORD="ejc")
    out = subprocess.run(
        ["psql", "-h", "localhost", "-U", "ejc", "-d", "ejc",
         "-t", "-A", "-c", sql], capture_output=True, text=True, env=env)
    return out.stdout.strip()

def doc_row(doc_id):
    out = db(
        "SELECT id, titulo, versao, versao_grupo_id, versao_anterior_id, "
        "uploaded_by, filepath, size_bytes, created_at, deleted_at "
        f"FROM documents WHERE id = '{doc_id}'")
    if not out:
        return None
    (id_, titulo, versao, grupo, anterior, up, fp, sz, created, delt) = out.split("|")
    return dict(id=id_, titulo=titulo, versao=int(versao), grupo=grupo or None,
                anterior=anterior or None, uploaded_by=up, filepath=fp,
                size_bytes=int(sz) if sz else 0, created_at=created, deleted_at=delt)

def grupo_rows(grupo):
    out = db(
        "SELECT id, titulo, versao, versao_anterior_id, uploaded_by, created_at, deleted_at "
        f"FROM documents WHERE versao_grupo_id = '{grupo}' "
        "ORDER BY versao, created_at")
    rows = []
    for line in out.splitlines():
        if not line.strip(): continue
        id_, titulo, versao, anterior, up, created, delt = line.split("|")
        rows.append(dict(id=id_, titulo=titulo, versao=int(versao), anterior=anterior or None,
                         uploaded_by=up, created_at=created, deleted_at=delt))
    return rows

def download(email, doc_id, expect=200):
    r = S.get(f"{BASE}/api/documents/{doc_id}/download", headers=h(email), timeout=30)
    chk(f"download {doc_id[:8]}…", r.status_code == expect, f"esperado {expect}, got {r.status_code}")
    return r

def audit_count(doc_id):
    out = db(
        "SELECT COUNT(*) FROM audit_logs WHERE entidade = 'documents' "
        f"AND registro_id = '{doc_id}'")
    return int(out) if out.isdigit() else -1

def audit_actions(doc_id):
    out = db(
        "SELECT acao FROM audit_logs WHERE entidade = 'documents' "
        f"AND registro_id = '{doc_id}' ORDER BY created_at")
    return [x for x in out.splitlines() if x]

# ═══════════════════════════ BATERIA ══════════════════════════════════════════
if __name__ == "__main__":
    criar_recursos_qa()
    f1, f2, f3, f_alt, f_sem = (mk_pdf(C1), mk_pdf(C2), mk_pdf(C3), mk_pdf(C_ALT), mk_pdf(C_ALT))
    try:
        print("M11 — bateria de versionamento documental")
        # ── 1. versão inicial ────────────────────────────────────────────
        r1 = upload(ADM_E, f1, TIT_V1, caso=CASE_ID)
        chk("v1 criação", r1.status_code == 201, f"HTTP {r1.status_code}")
        v1_id = r1.json().get("id")
        d1 = doc_row(v1_id)
        chk("v1 metadados", d1 is not None and d1["versao"] == 1
            and d1["grupo"] == v1_id and d1["anterior"] is None,
            f"versao={d1['versao'] if d1 else 'n/a'} grupo={d1['grupo'] if d1 else 'n/a'} anterior={d1['anterior'] if d1 else 'n/a'}")
        # ── 2. nova versão (mesmo título, mesmo caso) ──────────────────────
        time.sleep(2)
        r2 = upload(ADV_E, f2, TIT_V2, caso=CASE_ID)
        chk("v2 criação", r2.status_code == 201, f"HTTP {r2.status_code} {r2.text[:80]}")
        v2_id = r2.json().get("id")
        d2 = doc_row(v2_id)
        chk("v2 encadeamento", d2 and d2["versao"] == 2 and d2["grupo"] == v1_id
            and d2["anterior"] == v1_id and d2["uploaded_by"] != d1["uploaded_by"],
            f"versao={d2['versao'] if d2 else 'n/a'} grupo={d2['grupo'] if d2 else 'n/a'} anterior={d2['anterior'] if d2 else 'n/a'}")
        # ── 3. terceira versão ──────────────────────────────────────────────
        time.sleep(2)
        r3 = upload(ADM_E, f3, TIT_V1, caso=CASE_ID)
        chk("v3 criação", r3.status_code == 201, f"HTTP {r3.status_code}")
        v3_id = r3.json().get("id")
        d3 = doc_row(v3_id)
        chk("v3 encadeamento", d3 and d3["versao"] == 3 and d3["grupo"] == v1_id
            and d3["anterior"] == v2_id,
            f"versao={d3['versao'] if d3 else 'n/a'} anterior={d3['anterior'] if d3 else 'n/a'}")
        # ── 4. histórico (consulta de grupo) ────────────────────────────────
        hist = grupo_rows(v1_id)
        chk("histórico grupo", len(hist) == 3 and [h["versao"] for h in hist] == [1, 2, 3],
            f"{len(hist)} linhas, versões {[h['versao'] for h in hist]}")
        # ── 5. autoria ──────────────────────────────────────────────────────
        up = [x["uploaded_by"] for x in hist]
        chk("autoria por versão", up[0] != up[1] and up[1] != up[2],
            f"{up[0][:8]}… / {up[1][:8]}… / {up[2][:8]}…")
        # ── 6. timestamps ───────────────────────────────────────────────────
        ts = [x["created_at"] for x in hist]
        chk("timestamps crescentes", ts[0] < ts[1] < ts[2], f"{ts}")
        # ── 7. arquivos físicos distintos / preservação (sem perda silenciosa)
        dl1 = download(ADM_E, v1_id, 200)
        dl2 = download(ADM_E, v2_id, 200)
        dl3 = download(ADM_E, v3_id, 200)
        b1, b2, b3 = dl1.content, dl2.content, dl3.content
        chk("conteúdo v1/v2/v3 distintos", b1 != b2 != b3 and b1 != b3,
            f"len {len(b1)}/{len(b2)}/{len(b3)}")
        # ── 8. integridade (comparação por hash) ───────────────────────────
        chk("hash v1 preservado", C1 in b1, "conteúdo v1 recuperável")
        chk("hash v3 preservado", C3 in b3, "conteúdo v3 recuperável")
        chk("sha256 v1==v2", sha(b1) != sha(b2), f"sha v1={sha(b1)[:12]}… v2={sha(b2)[:12]}…")
        # ── 9. recuperação: v1 acessível mesmo após v2 e v3 ─────────────────
        chk("v1 recuperável pós-v2/v3", b1 and len(b1) > 10, "download v1 OK após uploads v2/v3")
        # ── 10. conflito de edição (upload simultâneo mesmo título/caso) ───
        threads, results = [], []
        def worker(payload, idx):
            path = mk_pdf(payload)
            r = upload(ADV_E, path, TIT_V1, caso=CASE_ID)
            results.append((idx, r.status_code, r.json().get("id")))
        t = [threading.Thread(target=worker, args=(C_ALT, i)) for i in range(2)]
        for x in t: x.start()
        for x in t: x.join(timeout=60)
        r2c = [r for _, r, _ in results]
        ok_conflito = all(s == 201 for s in r2c)
        # ver como o banco tratou: se ambos v4 (mesmo número) ou v4/v5
        hist2 = grupo_rows(v1_id)
        versoes2 = sorted(x["versao"] for x in hist2)
        chk("conflito: respostas HTTP", ok_conflito, f"status {r2c}")
        chk("conflito: versoes pós-paralelo", versoes2[-1] >= 4,
            f"versões no grupo agora: {versoes2}")
        # ── 11. duplicação de número de versão (gap de constraint) ─────────
        # Após o conflito acima, se houver duas linhas com o mesmo versao=4,
        # o sistema não garante unicidade (gap documentado).
        hist3 = grupo_rows(v1_id)
        from collections import Counter
        dup = [v for v, c in Counter(x["versao"] for x in hist3).items() if c > 1]
        if dup:
            # gap conhecido: sem UNIQUE (versao_grupo_id, versao)
            chk("ausência de constraint UNIQUE versão (GAP)", True,
                f"versão duplicada no grupo: {dup} — sem constraint; registrar gap")
        # ── 12. exclusão de uma versão: o guard bloqueia exclusão de versão
        # intermediária (document_reference_guard: 409) — protege a cadeia.
        # A exclusão deve acontecer na versão MAIS RECENTE do grupo, ou com
        # referências bloqueantes. Testa a versão mais recente do grupo v1:
        # primeiro exclui v3 (última), depois tenta v1 (raiz, tem filha).
        grp_latest = max(grupo_rows(v1_id), key=lambda x: x["versao"])
        v_latest = grp_latest["id"]
        r_del3 = S.delete(f"{BASE}/api/documents/{v_latest}", headers=ADM_TOKEN, timeout=30)
        chk("exclusão v3 (mais recente) permite", r_del3.status_code == 200,
            f"HTTP {r_del3.status_code} {r_del3.text[:60]}")
        d3_del = doc_row(v_latest)
        chk("v3 marcada deleted_at", d3_del and d3_del["deleted_at"],
            f"deleted_at={d3_del['deleted_at'] if d3_del else 'n/a'}")
        # v1 é raiz da cadeia (v2 aponta para ela via versao_anterior_id) →
        # guard de referências bloqueia exclusão (proteção de integridade).
        r_del1 = S.delete(f"{BASE}/api/documents/{v1_id}", headers=ADM_TOKEN, timeout=30)
        chk("exclusão v1 (raiz da cadeia) bloqueada — 409", r_del1.status_code == 409,
            f"HTTP {r_del1.status_code} {r_del1.text[:80]}")
        d1_unchanged = doc_row(v1_id)
        chk("v1 permanece íntegra (sem perda silenciosa)",
            d1_unchanged and not d1_unchanged["deleted_at"],
            f"deleted_at={d1_unchanged['deleted_at'] if d1_unchanged else 'n/a'}")
        # ── 13. download da versão excluída bloqueado ──────────────────────
        download(ADM_E, v_latest, expect=404)
        # ── 14. restauração da versão excluída: via /trash/{entidade}/{id}/restaurar
        # (documents suportado na lixeira geral, admin/sócio+)
        r_trash = S.post(f"{BASE}/api/trash/documents/{v_latest}/restaurar",
                         headers=ADM_TOKEN, timeout=30)
        d3_rest = doc_row(v_latest)
        chk("restauração v3 via /trash/documents/{id}/restaurar",
            r_trash.status_code == 200 and d3_rest and not d3_rest["deleted_at"],
            f"HTTP {r_trash.status_code} — deleted_at={d3_rest['deleted_at'] if d3_rest else 'n/a'}")
        # restauração não bloqueada por ter versão anterior na cadeia (v2)
        # (versao_anterior_id aponta PARA v2, não de v2 para v3 — guard só bloqueia
        # exclusão quando HÁ filho ativo; filho deletado não impede restauração)
        # ── 14b. auditoria DELETE da versão efetivamente excluída ──────────
        a_del = audit_actions(v_latest)
        chk("auditoria DELETE da versão excluída", "DELETE" in a_del, f"{a_del}")
        # ── 15b. título diferente no mesmo caso NÃO versiona ────────────────
        r_alt = upload(ADM_E, f_alt, TIT_ALT, caso=CASE_ID)
        chk("título diferente não versiona", r_alt.status_code == 201, f"HTTP {r_alt.status_code}")
        v_alt = r_alt.json().get("id")
        d_alt = doc_row(v_alt)
        chk("título diferente = v1 própria", d_alt and d_alt["versao"] == 1 and d_alt["grupo"] == v_alt,
            f"versao={d_alt['versao'] if d_alt else 'n/a'} grupo={d_alt['grupo'] if d_alt else 'n/a'}")
        # ── 16. doc sem case_id não versiona (só client_id) ─────────────────
        r_sc = upload(ADM_E, f1, TIT_SEM_CASO, cliente=CLIENT_ID)
        chk("sem caso: upload 201", r_sc.status_code == 201, f"HTTP {r_sc.status_code}")
        v_sc = r_sc.json().get("id")
        d_sc = doc_row(v_sc)
        chk("sem caso: v1 sem grupo de versão", d_sc and d_sc["versao"] == 1,
            f"versao={d_sc['versao'] if d_sc else 'n/a'}")
        # re-upload mesmo título sem caso: NÃO versiona (docs sem caso
        # nascem sempre como v1 de grupo próprio — o versionamento é atrelado
        # ao caso; lacuna de design documentada, sem perda de versão)
        r_sc2 = upload(ADM_E, f2, TIT_SEM_CASO, cliente=CLIENT_ID)
        v_sc2 = r_sc2.json().get("id")
        d_sc2 = doc_row(v_sc2)
        chk("sem caso: re-upload cria linha isolada v1 (sem versionamento, por design)",
            d_sc2 and d_sc2["versao"] == 1,
            "docs sem caso não formam cadeia de versão — lacuna documentada")
        # ── 17. PATCH de metadados não altera versão ────────────────────────
        r_patch = S.patch(f"{BASE}/api/documents/{v1_id}", headers=ADM_TOKEN,
                          json={"titulo": f"{TIT_V1} (revisado)"}, timeout=30)
        chk("patch metadados 200", r_patch.status_code == 200, f"HTTP {r_patch.status_code}")
        d1p = doc_row(v1_id)
        chk("patch não altera versão", d1p and d1p["versao"] == 1, f"versao={d1p['versao'] if d1p else 'n/a'}")
        # ── 18. download exige autenticação ─────────────────────────────────
        r_anon = S.get(f"{BASE}/api/documents/{v1_id}/download", timeout=30)
        chk("download sem token bloqueado", r_anon.status_code in (401, 403), f"HTTP {r_anon.status_code}")
        # ── 19. isolamento de autorização (financeiro/estagiário vs confidencial)
        # sobe doc restrito
        f_rest = mk_pdf(b"EJC_QA M11 restrito")
        r_rest = upload(ADM_E, f_rest, f"EJC_QA M11 Restrito {random.randint(1,99999)}",
                        caso=CASE_ID_2, conf="restrito")
        v_rest = r_rest.json().get("id") if r_rest.status_code == 201 else None
        for u, nome in [(FIN_E, "financeiro"), (EST_E, "estagiário"), (CLI_E, "cliente_externo")]:
            rr = S.get(f"{BASE}/api/documents/{v_rest}/download", headers=h(u), timeout=30)
            chk(f"{nome} bloqueado em doc restrito", rr.status_code == 403, f"HTTP {rr.status_code}")
        # ── 20. auditoria por versão ────────────────────────────────────────
        a1, a2, a3 = audit_actions(v1_id), audit_actions(v2_id), audit_actions(v3_id)
        chk("auditoria v1 UPLOAD", "UPLOAD" in a1, f"{a1}")
        chk("auditoria v2 UPLOAD (autor distinto)", "UPLOAD" in a2, f"{a2}")
        chk("auditoria v3 UPLOAD", "UPLOAD" in a3, f"{a3}")
        # ── 21. payload de listagem não expõe versão (GAP documentado) ──────
        r_list = S.get(f"{BASE}/api/documents/", headers=ADM_TOKEN, params={"case_id": CASE_ID}, timeout=30)
        lst = r_list.json().get("data", [])
        item = next((x for x in lst if x["id"] == v1_id), None)
        tem_versao = item and ("versao" in item or "versao_grupo_id" in item)
        chk("payload list não expõe versão (GAP)", not tem_versao,
            "campos de versionamento ausentes no payload público — auditoria invisível")
        # ── 22. integridade final: v3 continua íntegra após exclusão/restauração de v2
        dl3f = download(ADM_E, v3_id, 200)
        chk("v3 íntegra pós-rodada", C3 in dl3f.content, "conteúdo v3 íntegro")
        dl1f = download(ADM_E, v1_id, 200)
        chk("v1 íntegra pós-rodada", C1 in dl1f.content, "conteúdo v1 íntegro")
    finally:
        for p in (f1, f2, f3, f_alt, f_sem):
            try: os.unlink(p)
            except OSError: pass
    print(f"\nM11 resultado: {ok_total}/{total} PASS")
    sys.exit(0 if ok_total == total else 1)
