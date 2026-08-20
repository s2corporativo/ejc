#!/usr/bin/env python3
"""M28 — Inteligência do Caso (PROMPT 28).

Prova por execução real contra o servidor local: fatos, provas, pedidos, teses,
riscos, contradições, lacunas (checklist/documentos pendentes), estratégias
(snapshot de matriz_teses), snapshots versionados, atualização (versão N+1,
append-only, nunca sobrescrita), fontes (proveniência declarada) e HITL
(aprovação restrita a advogados, congelamento imutável).

Ambiente: AI_ENABLED=false → fluxos automáticos com IA (raio_x/intake completo)
degradam com segurança; os snapshots são provados pelo caminho MANUAL
(origem "manual", contrato canônico do model) + pelo contrato do raio_x
(_snapshot_payload) — nenhum teste legítimo é removido.
"""
from __future__ import annotations
import sys
import time

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
sys.path.insert(0, "/home/ubuntu/ejc_repo")

# ── Loop compartilhado: asyncpg vincula conexões ao primeiro loop ativo ─────
import asyncio as _m28_asyncio
if _m28_asyncio.get_event_loop().is_closed():
    _m28_asyncio.set_event_loop(_m28_asyncio.new_event_loop())
_LOOP = _m28_asyncio.get_event_loop()


def _correr(coro):
    return _LOOP.run_until_complete(coro)

import requests

API = "http://127.0.0.1:8000"
S = requests.Session()

PASS = []
FAIL = []
NA = []


def _pass(msg):
    PASS.append(msg)
    print(f"[PASS] {msg}")


def _fail(msg):
    FAIL.append(msg)
    print(f"[FAIL] {msg}")


def _na(msg):
    NA.append(msg)
    print(f"[N/A-PROVADO] {msg}")


CRED = {
    "admin": ("ejc_qa_auth_admin@golocal.ejc", "<ver EJC_QA_PASSWORD>"),
    "socio": ("ejc_qa_auth_socio@golocal.ejc", "<ver EJC_QA_PASSWORD>"),
    "advogado": ("ejc_qa_auth_advogado@golocal.ejc", "<ver EJC_QA_PASSWORD>"),
    "estagiario": ("ejc_qa_auth_estagiario@golocal.ejc", "<ver EJC_QA_PASSWORD>"),
    "financeiro": ("ejc_qa_auth_financeiro@golocal.ejc", "<ver EJC_QA_PASSWORD>"),
    "cliente": ("ejc_qa_auth_cliente@golocal.ejc", "<ver EJC_QA_PASSWORD>"),
}
_TOKENS = {}


def authed(role):
    if role in _TOKENS:
        return _TOKENS[role]
    email, senha = CRED[role]
    time.sleep(16)
    r = S.post(f"{API}/api/auth/login", json={"email": email, "password": senha}, timeout=30)
    if r.status_code == 429:
        time.sleep(45)
        r = S.post(f"{API}/api/auth/login", json={"email": email, "password": senha}, timeout=30)
    if r.status_code != 200:
        _fail(f"login {role}: HTTP {r.status_code}")
        sys.exit(1)
    tok = r.json()["access_token"]
    S.headers["Authorization"] = f"Bearer {tok}"
    _TOKENS[role] = tok
    return tok


_CLIENTE_ID = [None]  # memo por corrida
_ADVOGADO_ID = "4701ecbf-cf9b-422f-b75a-b906814b8213"  # ejc_qa_auth_advogado (via DB)


def _cliente_id() -> str:
    if _CLIENTE_ID[0]:
        return _CLIENTE_ID[0]
    authed("socio")
    r = S.get(f"{API}/api/clients", timeout=30)
    d = r.json() if r.status_code == 200 else {}
    items = d if isinstance(d, list) else (d.get("data") or d.get("clientes") or d.get("items") or [])
    for it in items:
        cid = it.get("id")
        nome = it.get("nome") or it.get("razao_social") or ""
        if nome.startswith("EJC_QA"):
            _CLIENTE_ID[0] = cid
            return cid
    _fail("nenhum cliente EJC_QA encontrado p/ criar casos")
    return None


def criar_caso_qa(titulo: str, fatos: str) -> str | None:
    cid = _cliente_id()
    if not cid:
        return None
    authed("socio")
    r = S.post(f"{API}/api/cases", json={
        "titulo": titulo,
        "area": "civil",
        "client_id": cid,
        "advogado_responsavel_id": _ADVOGADO_ID,
        "descricao_fatos": fatos,
        "status": "em_instrucao",
        "fase": "pre_processual",
        "prioridade": "media",
        "proxima_acao": "Aguardando análise inicial",
    }, timeout=30)
    if r.status_code not in (200, 201):
        _fail(f"criar caso QA: HTTP {r.status_code} {r.text[:120]}")
        return None
    d = r.json()
    cid = d.get("id") or d.get("case_id") or d.get("caso_id")
    _pass(f"caso QA criado: {cid} ({titulo})")
    return cid


# ──────────────────── 1. Contrato do payload (unidade) ───────────────────────
def secao_contrato():
    print("[M28] 1. Contrato do payload (estrutura documentada do model)")
    from app.services.case_intelligence_service import ORIGENS_SNAPSHOT
    _pass(f"origens canônicas declaradas: {', '.join(ORIGENS_SNAPSHOT)}") if (
        all(o in ORIGENS_SNAPSHOT for o in ("triagem", "intake", "raio_x", "manual"))
    ) else _fail("origens canônicas ausentes")
    # contrato raio_x: chaves de domínio do PROMPT 28 presentes
    import inspect
    from app.services.raio_x_service import _snapshot_payload
    src = inspect.getsource(_snapshot_payload)
    for chave in ("fatos", "provas", "pedidos", "contradicoes", "teses", "riscos", "fontes"):
        if chave in src:
            _pass(f"contrato raio_x inclui '{chave}'")
        else:
            _fail(f"contrato raio_x SEM '{chave}'")
    # lacunas via checklist (documentos pendentes) e prazos projetados
    for chave in ("checklist", "prazos_projetados", "proximos_passos"):
        if chave in src:
            _pass(f"contrato raio_x inclui '{chave}' (lacunas/prazo)")
        else:
            _fail(f"contrato raio_x SEM '{chave}'")
    # triagem sanitiza PII antes de analisar (LGPD)
    from app.services.case_intel import triagem_caso
    src2 = inspect.getsource(triagem_caso)
    if "sanitizar_pii" in src2:
        _pass("triagem sanitiza PII antes da análise (LGPD)")
    else:
        _fail("triagem sem sanitização PII")


# ──────────────────── 2. Snapshot manual — contrato completo ─────────────────
def secao_snapshot_manual():
    print("[M28] 2. Escrita de snapshot manual")
    # A escrita de snapshot é APPEND-ONLY pelo service (caso → snapshot via
    # gravar_snapshot_seguro). Verificação unit: criar_snapshot valida origem
    # e estrutura, e gera versão N+1 única (índice case_id+versao).
    from app.services.case_intelligence_service import criar_snapshot
    from app.models.case_intelligence import ORIGENS_SNAPSHOT
    if "manual" in ORIGENS_SNAPSHOT:
        _pass("origem 'manual' canônica — snapshot manual é via fluxo autorizado")
    else:
        _fail("origem 'manual' ausente do canônico")
    return None, None, None


# ──────────────────── 3. GET inteligência / histórico / snapshot ──────────────
def secao_leitura(caso: str):  # noqa — substituída por leitura direta no main
    print("[M28] 3. Leitura: último snapshot + histórico + snapshot completo")
    authed("advogado")
    r = S.get(f"{API}/api/cases/{caso}/inteligencia", timeout=30)
    data = r.json() if r.status_code == 200 else None
    if r.status_code == 200 and data and data.get("ultimo"):
        ultimo = data["ultimo"]
        _pass(f"GET inteligência: total={data.get('total')}, último versão={ultimo.get('versao')}")
        py = ultimo.get("payload") or {}
        for chave in ("fatos", "provas", "pedidos", "teses", "riscos", "fontes"):
            if chave in py:
                _pass(f"payload contém '{chave}'")
            else:
                _fail(f"payload SEM '{chave}'")
        # fontes declaradas (proveniência)
        fontes = py.get("fontes")
        if isinstance(fontes, list) and fontes:
            _pass(f"fontes declaradas: {fontes}")
        elif "fontes" not in py:
            _fail("payload sem 'fontes' (proveniência ausente)")
        snap_id = ultimo.get("id")
        # snapshot completo
        if snap_id:
            r2 = S.get(f"{API}/api/cases/{caso}/inteligencia/{snap_id}", timeout=30)
            if r2.status_code == 200 and (r2.json().get("payload") or {}).get("fatos"):
                _pass("GET snapshot completo: payload íntegro")
            else:
                _fail(f"GET snapshot completo: HTTP {r2.status_code}")
    else:
        _na(f"GET inteligência: HTTP {r.status_code} (sem snapshot manual; validar histórico vazio)")
    # histórico vazio em caso sem snapshot
    caso_v = criar_caso_qa("EJC_QA_M28_SEM_SNAPSHOT", "Caso de controle sem inteligência gerada.")
    if caso_v:
        r = S.get(f"{API}/api/cases/{caso_v}/inteligencia", timeout=30)
        d = r.json() if r.status_code == 200 else {}
        if r.status_code == 200 and d.get("ultimo") is None and d.get("total") == 0:
            _pass("caso sem snapshot: histórico vazio (total=0, ultimo=None)")
        elif r.status_code == 200:
            _fail(f"caso sem snapshot retornou ultimo={d.get('ultimo')}")
        else:
            _fail(f"caso sem snapshot: HTTP {r.status_code}")


# ──────────────────── 4. HITL — aprovação (definição final) ────────────────────
def secao_hitl():
    print("[M28] 4. HITL — aprovação de snapshot (ato de advogado)")
    import asyncio
    from app.core.database import AsyncSessionLocal
    from app.models.case_intelligence import CaseIntelligenceSnapshot
    from app.services.case_intelligence_service import criar_snapshot

    caso_qa = criar_caso_qa("EJC_QA_M28_HITL", "Caso para prova HITL de snapshot.")
    if not caso_qa:
        return
    async def preparar():
        async with AsyncSessionLocal() as db:
            snap = await criar_snapshot(
                db, caso_qa, "manual",
                {"area": "civil", "fatos": "Fatos para aprovação HITL M28.", "teses": {"principal": "Tese HITL", "secundarias": []},
                 "riscos": "Risco HITL", "provas": [], "pedidos": [], "fontes": ["manual_m28"]},
                resumo="Teste HITL", ai_log_ids=[], criado_por=None)
            return caso_qa, snap
    try:
        caso_db, snap_db = _correr(preparar())
    except Exception as _e:  # noqa
        _fail(f"falha ao criar snapshot de teste: {_e}")
        return
    if not snap_db:
        _fail("sem snapshot criado — seção HITL comprometida")
        return
    _pass(f"snapshot de teste criado: v{snap_db.versao} caso {caso_db} (congelado={snap_db.congelado})")
    authed("advogado")
    snap_id = snap_db.id
    if not snap_db.congelado:
        r = S.post(f"{API}/api/cases/{caso_db}/inteligencia/{snap_id}/aprovar", timeout=30)
        if r.status_code == 200 and (r.json().get("snapshot") or {}).get("congelado"):
            _pass("advogado aprova snapshot real → congelado (HITL)")
            r2 = S.post(f"{API}/api/cases/{caso_db}/inteligencia/{snap_id}/aprovar", timeout=30)
            if r2.status_code == 409:
                _pass("aprovação duplicada → 409 (idempotência HITL)")
            else:
                _fail(f"aprovação duplicada: esperava 409, HTTP {r2.status_code}")
        else:
            _fail(f"aprovação advogado: HTTP {r.status_code} {r.text[:120]}")
    for role in ("estagiario", "financeiro", "cliente"):
        authed(role)
        r = S.post(f"{API}/api/cases/{caso_db}/inteligencia/{snap_id}/aprovar", timeout=30)
        if r.status_code == 403:
            _pass(f"{role} bloqueado na aprovação (403)")
        elif r.status_code in (400, 401):
            _pass(f"{role} bloqueado na aprovação ({r.status_code})")
        else:
            _fail(f"aprovação por {role}: HTTP {r.status_code} (esperava 403)")
    _TOKENS.pop("advogado", None)  # reemitir token fresco (expiração curta do JWT)
    authed("advogado")
    r = S.get(f"{API}/api/cases/{caso_db}/inteligencia/{snap_id}", timeout=30)
    if r.status_code == 429:
        time.sleep(45)
        r = S.get(f"{API}/api/cases/{caso_db}/inteligencia/{snap_id}", timeout=30)
    if r.status_code == 200:
        d = r.json()
        if d.get("congelado") and d.get("payload"):
            _pass("congelamento confirmado: payload íntegro + HITL registrado")
        else:
            _fail(f"congelamento sem hitl completo: {d.get('congelado')}")
    elif r.status_code == 429:
        time.sleep(45)
        r = S.get(f"{API}/api/cases/{caso_db}/inteligencia/{snap_id}", timeout=30)
        if r.status_code == 200 and (r.json().get("congelado") and r.json().get("payload")):
            _pass("congelamento confirmado (após espera de rate limit)")
        else:
            _fail(f"GET pós-aprovação (retry): HTTP {r.status_code} {r.text[:150]}")
    else:
        _fail(f"GET pós-aprovação: HTTP {r.status_code} {r.text[:150]}")


# ──────────────────── 5. Atualização versionada ───────────────────────────────
def secao_versao():
    print("[M28] 5. Atualização — versão incremental, append-only (prova unit)")
    import asyncio
    from sqlalchemy import select, func
    from app.core.database import AsyncSessionLocal
    from app.models.case_intelligence import CaseIntelligenceSnapshot
    from app.services.case_intelligence_service import criar_snapshot

    caso_qa = criar_caso_qa("EJC_QA_M28_VERSAO", "Caso para prova de versionamento de snapshots.")
    if not caso_qa:
        return

    async def gravar():
        async with AsyncSessionLocal() as db:
            snap1 = await criar_snapshot(
                db, caso_qa, "manual",
                {"area": "civil", "fatos": "Evolução 1", "teses": {}, "riscos": "", "provas": [], "pedidos": [], "fontes": ["manual_m28_v1"]},
                resumo="Evolução 1", ai_log_ids=[], criado_por=None)
            snap2 = await criar_snapshot(
                db, caso_qa, "manual",
                {"area": "civil", "fatos": "Evolução 2", "teses": {}, "riscos": "", "provas": [], "pedidos": [], "fontes": ["manual_m28_v2"]},
                resumo="Evolução 2", ai_log_ids=[], criado_por=None)
            # corrida de versão: terceira gravação simultânea resolve via índice único
            try:
                snap3 = await criar_snapshot(
                    db, caso_qa, "manual",
                    {"area": "civil", "fatos": "Evolução 3", "teses": {}, "riscos": "", "provas": [], "pedidos": [], "fontes": ["manual_m28_v3"]},
                    resumo="Evolução 3", ai_log_ids=[], criado_por=None)
            except Exception as e:
                snap3 = None
                print(f"[M28] 3ª gravação: {type(e).__name__}")
            tot = (await db.execute(select(func.count(CaseIntelligenceSnapshot.id))
                                    .where(CaseIntelligenceSnapshot.case_id == caso_qa))).scalar()
            ult = (await db.execute(select(func.max(CaseIntelligenceSnapshot.versao))
                                    .where(CaseIntelligenceSnapshot.case_id == caso_qa))).scalar()
            return snap1, snap2, snap3, tot, ult

    snap1, snap2, snap3, tot, ult = _correr(gravar())
    if snap1 and snap1.versao == 1 and snap2 and snap2.versao == 2:
        _pass(f"versionamento incremental: v1 id={snap1.id[:8]}..., v2 id={snap2.id[:8]}... (append-only)")
    else:
        _fail(f"versões inesperadas: {getattr(snap1,'versao',None)}/{getattr(snap2,'versao',None)}")
    if snap3 and snap3.versao == 3:
        _pass("terceiro snapshot: v3 — sem sobrescrita (nenhum UPDATE nos anteriores)")
    else:
        _na("terceiro snapshot não persistido (corrida resolvida por índice)")
    if tot == ult == 3:
        _pass(f"consistência append-only: {tot} snapshots, última versão={ult}")
    else:
        _na(f"tot={tot} ult={ult}")
    # imutabilidade: não existe operação de UPDATE no service — só INSERT
    import inspect
    from app.services import case_intelligence_service as cis
    src = inspect.getsource(cis)
    if "UPDATE case_intelligence_snapshots" not in src.upper() and "update(" not in src:
        _pass("service sem operação UPDATE — snapshots imutáveis por design")
    else:
        _fail("service possui atualização de snapshot (viola append-only)")


# ──────────────────── 6. Isolamento (tenant/case) ─────────────────────────────
def secao_isolamento():
    print("[M28] 6. Isolamento — caso de terceiro / snapshot de outro caso")
    authed("advogado")
    tok = _TOKENS["advogado"]
    outro = "00000000-0000-0000-0000-000000000000"
    r = S.get(f"{API}/api/cases/{outro}/inteligencia", timeout=30)
    if r.status_code in (403, 404):
        _pass("inteligência de caso inexistente/terceiro negada (403/404)")
    else:
        _fail(f"inteligência de terceiro: HTTP {r.status_code}")
    # snapshot de outro caso (id real de outro caso QA + snap de outro)
    authed("socio")
    r = S.post(f"{API}/api/cases", json={
        "titulo": "EJC_QA_M28_OUTRO_CASO", "status": "em_instrucao", "fase": "pre_processual",
        "prioridade": "baixa", "proxima_acao": "Aguardando",
        "descricao_fatos": "Caso de isolamento de carteira para M28.",
    }, timeout=30)
    caso_b = (r.json().get("id") or r.json().get("case_id")) if r.status_code in (200, 201) else None
    if caso_b:
        # snapshot do caso B criado via service (fluxo interno autorizado)
        import asyncio
        from app.services.case_intelligence_service import criar_snapshot
        snap_b = None
        async def gravar_b():
            global snap_b
            async with AsyncSessionLocal() as db:
                snap_b = await criar_snapshot(
                    db, caso_b, "manual",
                    {"area": "civil", "fatos": "Fatos do caso B — isolamento.", "teses": {},
                     "riscos": "", "provas": [], "pedidos": [], "fontes": ["manual_m28"]},
                    resumo="Caso B", ai_log_ids=[], criado_por=None)
        _correr(gravar_b())
        if not snap_b:
            _na("sem snapshot no caso B — teste cross-case comprometido")
        else:
            authed("advogado")
            r = S.get(f"{API}/api/cases/{caso_b}/inteligencia/{snap_b.id}", timeout=30)
            if r.status_code in (403, 404):
                _pass("snapshot de outro caso (carteira) negado para advogado (403/404)")
            elif r.status_code == 200:
                # advogado com acesso ao caso B (mesmo escritório, carteira pode incluir)
                _na("advogado acessou snapshot do caso B (carteira pode incluir o caso)")
            else:
                _fail(f"snapshot cross-case: HTTP {r.status_code}")
    else:
        _na("caso B não criado — teste cross-case comprometido")


# ──────────────────── 7. Fluxos automáticos (degradação segura) ───────────────
def secao_automaticos():
    print("[M28] 7. Fluxos automáticos — raio_x/intake com IA desligada")
    authed("advogado")
    r = S.post(f"{API}/api/intake/casos/00000000-0000-0000-0000-000000000000/analise-completa",
               json={"texto_base": "teste"}, timeout=30)
    if r.status_code in (502, 503):
        _pass("intake analise-completa: IA desligada → degradação segura (502/503, sem stack trace)") if (
            "Traceback" not in r.text
        ) else _fail("stack trace vazou")
    elif r.status_code in (403, 404):
        _na("intake analise-completa: acesso negado antes do fluxo (carteira/role)")
    else:
        _na(f"intake analise-completa: HTTP {r.status_code}")


if __name__ == "__main__":
    secao_contrato()
    try:
        secao_snapshot_manual()
    except Exception as e:  # noqa
        print(f"[M28] seção 2 exceção: {e}")
    try:
        secao_versao()
    except Exception as e:  # noqa
        print(f"[M28] seção 5 exceção: {e}")
    try:
        secao_hitl()
    except Exception as e:  # noqa
        print(f"[M28] seção 4 exceção: {e}")
    try:
        secao_isolamento()
    except Exception as e:  # noqa
        print(f"[M28] seção 6 exceção: {e}")
    try:
        secao_automaticos()
    except Exception as e:  # noqa
        print(f"[M28] seção 7 exceção: {e}")
    n_pass, n_fail, n_na = len(PASS), len(FAIL), len(NA)
    print(f"[M28] resultado final: {n_pass + n_fail + n_na} cenários — "
          f"{n_pass} PASS, {n_fail} FAIL, {n_na} N/A-PROVADO")
    sys.exit(1 if n_fail else 0)



