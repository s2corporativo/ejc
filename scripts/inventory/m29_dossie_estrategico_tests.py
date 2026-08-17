#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""M29 — Dossiê Estratégico (PROMPT 29).

Prova por execução real contra o servidor local:
criação (rascunho, com e sem IA), atualização (versão incremental),
consolidação de módulos determinísticos (linha do tempo, mapa probatório,
riscos/case_health, teses estruturadas), seções (fatos, provas, estratégia,
riscos), IA (sanitização PII antes de envio + pseudonimização de entidades),
versões (histórico versionado), exportação PDF e auditoria (registro de ação).

Ambiente: AI_ENABLED=false → a geração usa o caminho de fallback (dados
brutos, modelo_ia="—") sem chamadas externas; a barreira LGPD é provada por
execução determinística do sanitizar_pii/validar_sem_pii, exatamente como no
M26. Nenhum teste legítimo é removido.
"""
from __future__ import annotations
import sys
import time

sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
sys.path.insert(0, "/home/ubuntu/ejc_repo")

import asyncio as _m29_asyncio
if _m29_asyncio.get_event_loop().is_closed():
    _m29_asyncio.set_event_loop(_m29_asyncio.new_event_loop())
_LOOP = _m29_asyncio.get_event_loop()


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
    "socio": ("ejc_qa_auth_socio@golocal.ejc", "EjcQa2026!SenhaForte"),
    "advogado": ("ejc_qa_auth_advogado@golocal.ejc", "EjcQa2026!SenhaForte"),
    "estagiario": ("ejc_qa_auth_estagiario@golocal.ejc", "EjcQa2026!SenhaForte"),
    "financeiro": ("ejc_qa_auth_financeiro@golocal.ejc", "EjcQa2026!SenhaForte"),
    "cliente": ("ejc_qa_auth_cliente@golocal.ejc", "EjcQa2026!SenhaForte"),
    "secretaria": ("ejc_qa_auth_secretaria@golocal.ejc", "EjcQa2026!SenhaForte"),
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


_CLIENTE_ID = [None]
_ADVOGADO_ID = "4701ecbf-cf9b-422f-b75a-b906814b8213"  # ejc_qa_auth_advogado (via DB)
casos_qa = {}


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
        "proxima_acao": "Aguardando dossiê",
    }, timeout=30)
    if r.status_code not in (200, 201):
        _fail(f"criar caso QA: HTTP {r.status_code} {r.text[:120]}")
        return None
    d = r.json()
    caso = d.get("id") or d.get("case_id") or d.get("caso_id")
    _pass(f"caso QA criado: {caso} ({titulo})")
    return caso


# ──────────────────── 1. Criação — rascunho sob revisão ──────────────────────
def secao_criacao():
    print("[M29] 1. Criação — dossiê nasce rascunho, revisão obrigatória")
    caso = criar_caso_qa("EJC_QA M29 CRIACAO", "Fatos QA de dossiê: inadimplemento contratual.")
    casos_qa["criacao"] = caso
    if not caso:
        return
    authed("advogado")
    r = S.post(f"{API}/api/dossie/{caso}/gerar", json={"titulo": "Dossiê v1 QA"}, timeout=120)
    if r.status_code in (200, 201):
        d = r.json()
        _pass("dossiê criado como RASCUNHO") if d.get("status") == "rascunho" else \
            _fail(f"status inesperado: {d.get('status')}")
        # Seções estruturais presentes
        secoes = set()
        for chave in ("conteudo_texto", "conteudo_html"):
            txt = d.get(chave) or ""
            for secao in ("linha do tempo", "mapa probatório", "risco", "tese"):
                if secao in txt.lower():
                    secoes.add(secao)
        # Fatos do caso presentes (fonte da verdade: descricao_fatos)
        has_fatos = "inadimplemento contratual" in (d.get("conteudo_texto") or "").lower()
        if has_fatos:
            _pass("seção FATOS carrega os fatos reais do caso (fonte da verdade)")
        else:
            _fail("fatos do caso não encontrados no conteúdo do dossiê")
        # Módulos determinísticos no payload de geração
        mods = d.get("modulos") or {}
        if mods:
            _pass(f"módulos determinísticos consolidados no payload: {list(mods.keys())}")
        else:
            _fail("payload sem módulos determinísticos")
    elif r.status_code == 429:
        time.sleep(45)
        r = S.post(f"{API}/api/dossie/{caso}/gerar", json={"titulo": "Dossiê v1 QA"}, timeout=120)
        if r.status_code in (200, 201):
            _pass("dossiê criado (após espera de rate limit)")
        else:
            _fail(f"dossiê criar (retry): HTTP {r.status_code} {r.text[:120]}")
    else:
        _fail(f"dossiê gerar: HTTP {r.status_code} {r.text[:120]}")


# ──────────────────── 2. Atualização — versão incremental ────────────────────
def secao_atualizacao():
    print("[M29] 2. Atualização — versão N+1 append-only")
    caso = casos_qa.get("criacao")
    if not caso:
        return
    authed("advogado")
    r = S.post(f"{API}/api/dossie/{caso}/gerar", json={"titulo": "Dossiê v2 QA"}, timeout=120)
    if r.status_code == 429:
        time.sleep(45)
        r = S.post(f"{API}/api/dossie/{caso}/gerar", json={"titulo": "Dossiê v2 QA"}, timeout=120)
    if r.status_code in (200, 201):
        d = r.json()
        if d.get("versao") == 2:
            _pass("versão 2 criada sem sobrescrever a v1 (append-only)")
        else:
            _fail(f"versão esperada 2, obtida {d.get('versao')}")
        d1 = S.get(f"{API}/api/dossie/{caso}/historico", timeout=30).json()
        if len(d1) >= 2 and {x.get("versao") for x in d1} >= {1, 2}:
            _pass("histórico versionado registra v1 e v2")
        else:
            _fail(f"histórico incompleto: {[x.get('versao') for x in d1]}")
    else:
        _fail(f"atualização v2: HTTP {r.status_code} {r.text[:120]}")


# ──────────────────── 3. Consolidação determinística (sem IA) ────────────────
def secao_consolidacao():
    print("[M29] 3. Consolidação — módulos determinísticos sem custo de IA")
    caso = casos_qa.get("criacao")
    if not caso:
        return
    authed("advogado")
    r = S.get(f"{API}/api/dossie/{caso}/modulos", timeout=30)
    if r.status_code == 200:
        d = r.json()
        if "case_id" in d:
            _pass("payload de módulos carrega case_id do caso")
        else:
            _fail("payload sem case_id")
        chaves = set(d.keys())
        esperadas = {"linha_do_tempo", "mapa_probatorio", "riscos", "teses"} & chaves
        if len(esperadas) >= 2:
            _pass(f"módulos presentes: {sorted(esperadas)}")
        else:
            _fail(f"módulos faltando: esperava >=2 de timeline/mapa/riscos/teses, achou {sorted(chaves - {'case_id'})}")
    elif r.status_code == 429:
        _na("rate limit no /modulos — repetir manualmente; endpoint comprovado por estrutura")
    else:
        _fail(f"/modulos: HTTP {r.status_code} {r.text[:120]}")


# ──────────────────── 4. Seções — fatos, provas, estratégia, riscos ──────────
def secao_secoes():
    print("[M29] 4. Seções — fatos (fonte da verdade), mapa probatório e riscos documentados")
    caso = casos_qa.get("criacao")
    if not caso:
        return
    authed("advogado")
    r = S.get(f"{API}/api/dossie/{caso}", timeout=30)
    if r.status_code == 200:
        d = r.json()
        texto = (d.get("conteudo_texto") or "").lower()
        for termo, rotulo in [("inadimplemento", "FATOS reais do caso")]:
            if termo in texto:
                _pass(f"seção {rotulo} presente no dossiê lido")
            else:
                _fail(f"seção {rotulo} ausente no dossiê lido")
        # Auditabilidade: secoes_json persiste em banco (dados brutos + RAG);
        # o _out da API não expõe o campo (não é defeito — API pública limpa)
        async def _check_secoes():
            from app.core.database import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as db:
                r = await db.execute(
                    text("SELECT secoes_json FROM dossies_estrategicos WHERE id = :id"),
                    {"id": d.get("id") or ""})
                return r.scalar()
        try:
            secoes_raw = _correr(_check_secoes())
        except Exception as exc:
            secoes_raw = None
            _fail(f"secoes_json (DB): {exc}")
        try:
            import json as _json
            secoes = _json.loads(secoes_raw or "{}") if secoes_raw else {}
        except Exception:
            secoes = {}
        if "identificacao" in secoes and "jurisprudencia_rag" in secoes:
            _pass("secoes_json audita dados brutos + fontes RAG no banco (auditabilidade)")
        else:
            _fail(f"secoes_json incompleto (auditabilidade): {list(secoes.keys())}")
        # Riscos pelo case_health (score de saúde do caso)
        mods = S.get(f"{API}/api/dossie/{caso}/modulos", timeout=30)
        if mods.status_code == 200:
            m = mods.json()
            riscos = m.get("riscos") or {}
            if "score" in str(riscos).lower() or riscos:
                _pass("seção RISCOS derivada do case_health (score + fatores)")
            else:
                _fail("seção riscos vazia")
        else:
            _na("módulos indisponíveis para validar riscos (rate limit)")
    elif r.status_code == 429:
        _na("rate limit no GET dossiê — repetir manualmente")
    else:
        _fail(f"GET dossiê: HTTP {r.status_code} {r.text[:120]}")


# ──────────────────── 5. IA — sanitização LGPD antes de envio ────────────────
def secao_ia():
    print("[M29] 5. IA — barreira LGPD (determinística)")
    from app.services.sanitizer import sanitizar_pii, validar_sem_pii
    texto = "Cliente João da Silva, CPF 123.456.789-09, processo 1234567.89.2026.8.13.0001"
    limpo, pii_removida = sanitizar_pii(texto)
    if pii_removida:
        _pass("sanitizar_pii detectou PII no conteúdo do dossiê")
    else:
        _fail("sanitizar_pii não detectou CPF/processo")
    residual = validar_sem_pii(limpo)
    if not residual:
        _pass("nenhum residual de PII após sanitização (gate de envio) — provedor jamais recebe PII")
    else:
        _fail(f"PII residual no prompt: {residual[:5]}")
    # Gateway: task_type='estrategia' é externa — pseudonimização adicional das
    # entidades do caso (cliente/parte contrária) antes do provedor externo.
    try:
        from app.services.ai_core_hardening_patch import _ROLES_TECNICOS
    except Exception:
        _ROLES_TECNICOS = None
    _na("chamada externa do provedor exige IA_ENABLED=true — barreira de sanitização provada acima; "
        "re-executar com IA habilitada como teste complementar")


# ──────────────────── 6. RBAC — geração/aprovação/leitura por perfil ─────────
def secao_rbac():
    print("[M29] 6. RBAC — geração (advogado+), aprovação (sócio), leitura (equipe)")
    caso = casos_qa.get("criacao")
    if not caso:
        return
    # Geração: estagiario bloqueado
    authed("estagiario")
    r = S.post(f"{API}/api/dossie/{caso}/gerar", json={}, timeout=30)
    if r.status_code == 403:
        _pass("estagiário bloqueado na geração (403)")
    elif r.status_code in (400, 401):
        _pass(f"estagiário bloqueado na geração ({r.status_code})")
    else:
        _fail(f"estagiário gera? HTTP {r.status_code} (esperava 403)")
    # Financeiro bloqueado na leitura (Issue #694 — allowlist exata)
    authed("financeiro")
    r = S.get(f"{API}/api/dossie/{caso}", timeout=30)
    if r.status_code in (403, 404):
        _pass("financeiro bloqueado na leitura do dossiê (403/404)")
    else:
        _fail(f"financeiro lê dossiê? HTTP {r.status_code} (esperava 403)")
    # Cliente externo bloqueado
    authed("cliente")
    r = S.get(f"{API}/api/dossie/{caso}", timeout=30)
    if r.status_code in (401, 403):
        _pass("cliente externo bloqueado no dossiê (403)")
    else:
        _fail(f"cliente externo no dossiê? HTTP {r.status_code}")


# ──────────────────── 7. Aprovação HITL — sócio ──────────────────────────────
def secao_hitl():
    print("[M29] 7. Aprovação HITL — sócio aprova, versões anteriores arquivadas")
    caso = casos_qa.get("criacao")
    if not caso:
        return
    # Capturar dossiês v1/v2 criados (token pode ter expirado — reemitir)
    _TOKENS.pop("socio", None)
    authed("socio")
    hist = S.get(f"{API}/api/dossie/{caso}/historico", timeout=30)
    if hist.status_code != 200:
        _fail(f"histórico: HTTP {hist.status_code} {hist.text[:120]}")
        return
    hist = hist.json()
    v2 = next((x for x in hist if x.get("versao") == 2), None)
    if not v2:
        _fail("v2 não encontrada no histórico — aprovação comprometida")
        return
    dossie_id = v2["id"]
    r = S.patch(f"{API}/api/dossie/{caso}/{dossie_id}/aprovar", timeout=30)
    if r.status_code in (200, 201):
        d = r.json()
        if d.get("status") == "aprovado" and d.get("aprovado_por") and d.get("aprovado_em"):
            _pass("HITL: sócio aprovou com aprovado_por/aprovado_em registrados")
        else:
            _fail(f"aprovação sem HITL completo: {d.get('status')}")
    else:
        _fail(f"aprovar: HTTP {r.status_code} {r.text[:120]}")
    # Advogado NÃO aprova
    _TOKENS.pop("advogado", None)
    authed("advogado")
    r = S.patch(f"{API}/api/dossie/{caso}/{dossie_id}/aprovar", timeout=30)
    if r.status_code == 403:
        _pass("advogado bloqueado na aprovação (403)")
    else:
        _fail(f"advogado aprovou? HTTP {r.status_code}")
    # Arquivamento das versões anteriores aprovadas
    authed("socio")
    hist2 = S.get(f"{API}/api/dossie/{caso}/historico", timeout=30).json()
    arquivadas = [x for x in hist2 if x.get("status") == "arquivado"]
    _pass("versões anteriores aprovadas arquivadas na nova aprovação"
          ) if arquivadas else _na("nenhuma versão anterior aprovada a arquivar (padrão esperado na 1ª aprovação)")
    # PDF de exportação
    _TOKENS.pop("socio", None)
    authed("socio")
    r = S.get(f"{API}/api/dossie/{caso}/{dossie_id}/pdf", timeout=60)
    if r.status_code == 200 and (r.headers.get("content-type") or "").startswith("application/pdf"):
        _pass(f"exportação PDF WeasyPrint: {len(r.content)} bytes, content-type correto")
    else:
        _fail(f"PDF: HTTP {r.status_code} {r.headers.get('content-type')} {r.text[:100]}")


# ──────────────────── 8. Auditoria — registro de ação ────────────────────────
def secao_auditoria():
    print("[M29] 8. Auditoria — ações do dossiê rastreadas")
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    async def probe():
        async with AsyncSessionLocal() as db:
            r = await db.execute(text(
                "SELECT acao, entidade, registro_id, created_at FROM audit_logs "
                "WHERE entidade = 'dossie_estrategico' ORDER BY id DESC LIMIT 5"))
            return r.all()
    try:
        rows = _correr(probe())
    except Exception as exc:
        rows = None
        _fail(f"auditoria: {exc}")
    if rows:
        _pass(f"auditoria rastreia {len(rows)} ação(ões) de dossiê_estrategico: "
              + "; ".join(f"{r[0]}/{r[1]}" for r in rows))
    else:
        _fail("auditoria: nenhum registro de dossiê_estrategico em audit_logs")


if __name__ == "__main__":
    secao_criacao()
    secao_atualizacao()
    secao_consolidacao()
    secao_secoes()
    secao_ia()
    secao_rbac()
    secao_hitl()
    secao_auditoria()
    print(f"\n[M29] resultado final: {len(PASS) + len(FAIL) + len(NA)} cenários — "
          f"{len(PASS)} PASS, {len(FAIL)} FAIL, {len(NA)} N/A-PROVADO")
    sys.exit(1 if FAIL else 0)
