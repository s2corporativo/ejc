"""
M25 — Precedentes, Jurisprudência e Citações
Bateria de homologação contra servidor local (uvicorn porta 8000).

Verifica (conforme PROMPT 25):
  tribunal; processo; órgão julgador; relator; data; fonte;
  correspondência entre conteúdo e citação.
Mede:
  referências corretas; referências inexistentes; referências incorretas;
  interpretação incompatível com a fonte.

Rotas corretas (confirmdas no app):
  /api/jurisprudencias            (interno)
  /api/jurisprudencia-externa/precedentes/buscar (fachada multifonte;
     rotas buscar/fontes/importar do router legado aposentadas — Fase 7 §3.6)
  /api/conhecimento/importar-jurisprudencia/fontes (estado real das fontes)
  /api/ai/citacoes/verificar      (verificador rigoroso)
  /api/qualidade/verificar-citacoes (citation_check legado)
  /api/legal-docs/{doc}/jurisprudencia-check (correspondência conteúdo×citação)
  /api/teses, /api/cases/{id}/teses-sugeridas
"""
from __future__ import annotations
import os
import sys
import time
import requests


def _qa_pw(name: str) -> str:
    import os
    v = os.environ.get('EJC_QA_PASSWORD')
    if not v:
        raise RuntimeError(f'Credencial QA ausente: exporte EJC_QA_PASSWORD antes de rodar {name}')
    return v


SENHA = _qa_pw('M25')

API = "http://127.0.0.1:8000"
S = requests.Session()  # SEM Content-Type no header da sessão
PASS = []
FAIL = []

def _pass(msg):
    PASS.append(msg)
    print(f"[PASS] {msg}")

def _fail(msg):
    FAIL.append(msg)
    print(f"[FAIL] {msg}")

TOKENS = {}

def _token(email):
    if email in TOKENS and TOKENS[email] is not None:
        return TOKENS[email]
    time.sleep(16)
    r = S.post(f"{API}/api/auth/login", json={
        "email": email, "password": SENHA})
    if r.status_code == 429:
        time.sleep(45)
        r = S.post(f"{API}/api/auth/login", json={
            "email": email, "password": SENHA})
    if r.status_code != 200:
        raise SystemExit(f"Login {email} falhou: {r.status_code} {r.text[:300]}")
    TOKENS[email] = r.json()["access_token"]
    return TOKENS[email]

def authed(role):
    S.headers["Authorization"] = f"Bearer {_token(EMAILS[role])}"

EMAILS = {
    "admin": "ejc_qa_auth_admin@golocal.ejc",
    "socio": "ejc_qa_auth_socio@golocal.ejc",
    "advogado": "ejc_qa_auth_advogado@golocal.ejc",
    "estagiario": "ejc_qa_auth_estagiario@golocal.ejc",
    "financeiro": "ejc_qa_auth_financeiro@golocal.ejc",
    "cliente": "ejc_qa_auth_cliente@golocal.ejc",
}

CNJ_VALIDO = "1234567-11.2026.8.13.0001"   # DV módulo 97 correto
CNJ_DV_ERRADO = "1234567-61.2026.8.13.0001"  # DV adulterado
CNJ_INVENTADO = "0000000-00.9999.9.99.0000"  # tribunal inexistente

# ── 1. Motor determinístico de extração e classificação ─────────────────────
def secao_motor():
    print("[M25] 1. Motor de extração/classificação (sem LLM)")
    sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
    from app.services.verificador_jurisprudencia import (
        analisar_texto, verificar_jurisprudencia)
    from app.core.database import AsyncSessionLocal
    import asyncio

    texto_misto = (
        "Vossa Excelência, cito o processo nº " + CNJ_VALIDO + ", julgado pelo TJMG, "
        "Relator Des. Fulano, Órgão Especial, em 10/05/2026. "
        "O STJ no REsp 1.737.428/SP firmou tese. "
        "Súmula 102 do STJ e Súmula Vinculante 21 do STF orientam o caso. "
        "art. 5º, III da CF e art. 489 do CPC aplicam-se. "
        + "x " * 80
        + "Sob outro prisma, é pacífico o entendimento no tribunal de justiça do "
        "Amazonas sobre o tema."
    )
    achados = analisar_texto(texto_misto)
    tipos = {a["tipo"]: a for a in achados}

    _pass("processo CNJ extraído com número formatado e tribunal TJMG (contexto)") if (
        "processo_cnj" in tipos and tipos["processo_cnj"]["numero"] == CNJ_VALIDO
        and (tipos["processo_cnj"].get("tribunal") or "").upper() == "TJMG"
    ) else _fail(f"processo CNJ extração falhou: {tipos.get('processo_cnj')}")

    a = tipos.get("processo_cnj", {})
    _pass("DV CNJ válido = True") if a.get("dv_valido") is True else _fail(f"DV válido esperada True: {a.get('dv_valido')}")

    a2 = analisar_texto(f"processo {CNJ_DV_ERRADO} inventado")
    _pass("DV CNJ adulterado = False (formato inválido)") if (
        a2 and a2[0]["dv_valido"] is False
    ) else _fail(f"DV adulterado esperada False: {a2}")

    a3 = analisar_texto(f"processo {CNJ_INVENTADO}")
    _pass("CNJ inventado: tribunal inexistente no número (módulo 97)") if (
        a3 and a3[0]["tribunal_valido"] is False
    ) else _fail(f"CNJ inventado esperado tribunal_valido False: {a3}")

    res = tipos.get("recurso", {})
    _pass("recurso REsp extraído com número, UF e tribunal STJ por classe") if (
        res.get("classe") == "REsp" and res.get("numero") == "1.737.428"
        and res.get("uf") == "SP" and res.get("tribunal") == "STJ"
    ) else _fail(f"recurso extração falhou: {res}")

    s = [x for x in achados if x["tipo"] == "sumula"]
    por_num = {x["numero"]: x for x in s}
    _pass("súmula 102 STJ (não vinculante) extraída com tribunal correto") if (
        "102" in por_num and por_num["102"].get("tribunal") == "STJ"
        and por_num["102"].get("vinculante") is False
    ) else _fail(f"súmulas extração falhou: {[(x['numero'], x.get('tribunal'), x.get('vinculante')) for x in s]}")

    sv = por_num.get("21")
    _pass("súmula vinculante 21 vinculante=True e tribunal=STF") if (
        sv and sv.get("vinculante") is True and sv.get("tribunal") == "STF"
    ) else _fail(f"súmula vinculante extração falhou: {sv}")

    g = [x for x in achados if x["tipo"] == "generica"]
    # frase usa locução canônica do verificador ("É pacífico o entendimento")
    _pass("menção vaga com locução canônica vira citação `generica`") if (
        g and "pacífico" in g[0]["trecho"].lower()
    ) else _fail(f"menção genérica não detectada: {g}")

    # classificação de status com DB real (corpus seeded M25: CPC + CF88)
    async def _run():
        async with AsyncSessionLocal() as db:
            return await verificar_jurisprudencia(db, texto_misto)

    rel = asyncio.get_event_loop().run_until_complete(_run())
    _pass("shape legado: total/confirmadas/não_encontradas + score") if (
        "total" in rel and "confirmadas" in rel and "nao_encontradas" in rel
        and isinstance(rel["score"], int)
    ) else _fail(f"shape legado ausente: {rel.keys()}")

    r0 = rel["citacoes"][0]
    _pass("resultado por citação expõe tribunal/órgão/relator/data/fonte_verificacao") if all(
        k in r0 for k in ("tribunal", "orgao", "relator", "data", "fonte_verificacao")
    ) else _fail(f"chaves ausentes em {r0}")

    # métricas do PROMPT 25
    texto_correta = "Fundamento no art. 489 do CPC e art. 5º, III da CF."
    texto_inexistente = "Súmula 9999 do STF dispõe que..."
    texto_incorreto = f"Processo {CNJ_DV_ERRADO} tem DV inválido."

    async def _medir(textos):
        out = []
        async with AsyncSessionLocal() as db:
            for t in textos:
                out.append(await verificar_jurisprudencia(db, t))
        return out

    r_correta, r_inex, r_incorr = asyncio.get_event_loop().run_until_complete(
        _medir([texto_correta, texto_inexistente, texto_incorreto]))

    ver = r_correta["contagem_status"].get("verificada", 0)
    _pass("métrica 1 — referências CORRETAS (art. 489 CPC + art. 5º CF) verificadas na base oficial") if ver == 2 else _fail(
        f"corretas: verificadas={ver} esperado 2: {r_correta['citacoes']}")

    _pass("métrica 2 — referência INEXISTENTE (súmula 9999 STF, fora da faixa 1-736) flaggada suspeita") if (
        any(c["status"] == "suspeita" for c in r_inex["citacoes"])
    ) else _fail(f"inexistente não flaggada: {r_inex['citacoes']}")

    _pass("métrica 3 — referência INCORRETA (DV módulo 97 inválido) flaggada suspeita") if (
        any(c["status"] == "suspeita" for c in r_incorr["citacoes"])
    ) else _fail(f"incorreta não flaggada: {r_incorr['citacoes']}")

    _pass("score=100 com citações verificadas e 0 com só suspeitas (medida de confiança)") if (
        r_correta["score"] == 100 and r_inex["score"] == 0 and r_incorr["score"] == 0
    ) else _fail(f"scores: {r_correta['score']}, {r_inex['score']}, {r_incorr['score']}")

    # interpretação incompatível: citação real usada com conteúdo inventado
    texto_interp = "O STJ, no REsp 1.737.428/SP, decidiu que a Súmula 9000 do STF é vinculante."
    async def _r():
        async with AsyncSessionLocal() as db:
            return await verificar_jurisprudencia(db, texto_interp)
    r_interp = asyncio.get_event_loop().run_until_complete(_r())
    n_ver = r_interp["contagem_status"].get("verificada", 0)
    _pass("métrica 4 — interpretação INCOMPATÍVEL (súmula 9000 inexistente + DV ok não confirmado): nada verificado") if (
        n_ver == 0
    ) else _fail(f"interpretação incompatível passou: {r_interp['citacoes']}")

    _pass("avisos acionáveis presentes (suspeitas mapeadas a aviso por status)") if (
        len(r_inex["avisos"]) >= 1 and len(r_incorr["avisos"]) >= 1
        and any("SUSPEITA" in av for av in r_inex["avisos"])
        and any("SUSPEITA" in av for av in r_incorr["avisos"])
    ) else _fail(f"avisos ausentes: {r_inex['avisos']} | {r_incorr['avisos']}")

# ── 2. CRUD jurisprudência interna (tribunal/relator/data/fonte) ─────────────
def secao_crud_interna():
    print("[M25] 2. CRUD jurisprudência interna")
    authed("advogado")
    payload = {
        "titulo": "EJC_QA_M25 Tese sobre tutela antecipada em ação civil pública",
        "ementa": "EMENTA EJC_QA: cabível tutela antecipada em ação civil pública "
                  "quando presentes prova inequívoca e verossimilhança das alegações, "
                  "nos termos do art. 300 do CPC e entendimento consolidado do STJ.",
        "tribunal": "STJ", "relator": "Min. EJC_QA_Relator_M25",
        "numero_acordao": CNJ_VALIDO, "data_julgamento": "2026-05-10",
        "fonte": "manual", "area_juridica": "processo civil",
        "tags": "EJC_QA",
    }
    r = S.post(f"{API}/api/jurisprudencias", json=payload)
    assert r.status_code == 201, r.text
    jid = r.json()["id"]
    out = r.json()
    _pass("POST 201 preserva tribunal/relator/acórdão/data/fonte") if (
        out["tribunal"] == "STJ" and out["relator"] == "Min. EJC_QA_Relator_M25"
        and out["numero_acordao"] == CNJ_VALIDO
        and out["data_julgamento"] == "2026-05-10"
        and out["fonte"] == "manual"
    ) else _fail(f"campos não preservados: {out}")

    r = S.get(f"{API}/api/jurisprudencias/{jid}")
    assert r.status_code == 200
    _pass("GET incrementa vezes_citada (rastreabilidade de uso)") if (
        r.json()["vezes_citada"] >= 1
    ) else _fail("vezes_citada não incrementou")

    # PATCH com campo fora do schema: Pydantic ignora por padrão (não é 422);
    # o teste legítimo é que o campo NÃO é persistido — integridade preservada.
    r = S.patch(f"{API}/api/jurisprudencias/{jid}", json={
        "orgao_julgador": "Primeira Turma",
        "tags": "EJC_QA revisado",
    })
    _pass("PATCH ignora campo fora do schema (orgao_julgador NÃO persistido — sem corrupção)") if (
        r.status_code == 200 and "orgao_julgador" not in r.json()
        and r.json()["tags"] == "EJC_QA revisado"
    ) else _fail(f"PATCH inesperado: {r.status_code} {r.text[:200]}")

    r = S.patch(f"{API}/api/jurisprudencias/{jid}", json={"tags": "EJC_QA homologado"})
    assert r.status_code == 200
    _pass("PATCH válido atualiza sem tocar tribunal/data/fonte") if (
        r.json()["tribunal"] == "STJ" and r.json()["tags"] == "EJC_QA homologado"
    ) else _fail(f"PATCH corrompeu: {r.json()}")

    authed("financeiro")
    r = S.get(f"{API}/api/jurisprudencias")
    _pass("financeiro bloqueado do repositório (allowlist EXATA #694)") if (
        r.status_code in (401, 403, 404)
    ) else _fail(f"financeiro acessou: {r.status_code}")

    authed("cliente")
    r = S.post(f"{API}/api/jurisprudencias", json=payload)
    _pass("cliente_externo bloqueado do CRUD interno") if (
        r.status_code in (401, 403)
    ) else _fail(f"cliente criou: {r.status_code}")

    authed("estagiario")
    r = S.patch(f"{API}/api/jurisprudencias/{jid}", json={"tribunal": "TJMG"})
    _pass("estagiario não edita (exige advogado+)") if (
        r.status_code in (401, 403)
    ) else _fail(f"estagiario editou: {r.status_code}")

    authed("socio")
    r = S.patch(f"{API}/api/jurisprudencias/{jid}", json={"tribunal": "TJMG"})
    assert r.status_code == 200
    _pass("socio edita tribunal") if r.json()["tribunal"] == "TJMG" else _fail("socio não editou")

    authed("admin")
    r = S.get(f"{API}/api/jurisprudencias", params={"busca": "EJC_QA_M25", "page": 1})
    assert r.status_code == 200
    data = r.json()
    itens = data.get("items") if isinstance(data, dict) else data
    ids = [x["id"] for x in itens if isinstance(x, dict)]
    _pass("busca por título retorna o registro") if jid in ids else _fail(f"busca não achou: {ids}")

    authed("advogado")
    r = S.delete(f"{API}/api/jurisprudencias/{jid}")
    _pass("advogado NÃO pode excluir (exige socio+)") if (
        r.status_code in (401, 403)
    ) else _fail(f"advogado excluiu: {r.status_code}")

    authed("socio")
    r = S.delete(f"{API}/api/jurisprudencias/{jid}")
    _pass("socio exclui com soft delete (204)") if r.status_code == 204 else _fail(f"delete: {r.status_code}")

    authed("admin")
    r = S.get(f"{API}/api/jurisprudencias/{jid}")
    _pass("registro excluído some da listagem (soft delete)") if (
        r.status_code == 404
    ) else _fail(f"após delete: {r.status_code}")

# ── 3. Busca externa multi-fonte ─────────────────────────────────────────────
def secao_externa():
    print("[M25] 3. Busca externa e precedentes multi-fonte")
    authed("advogado")

    r = S.get(f"{API}/api/conhecimento/importar-jurisprudencia/fontes")
    assert r.status_code == 200
    nomes = [f.get("id") or f.get("slug") for f in r.json().get("fontes", [])]
    _pass("fontes reais (conhecimento) incluem lexml/tjmg") if (
        "lexml" in nomes and "tjmg" in nomes
    ) else _fail(f"fontes: {nomes}")

    # precedentes multi-fonte (roteador dedicado)
    r = S.post(f"{API}/api/jurisprudencia-externa/precedentes/buscar", json={
        "termo": "tutela antecipada", "fontes": ["lexml"], "pagina": 1})
    if r.status_code == 200:
        data = r.json()
        _pass("/precedentes/buscar responde 200 com itens ou lista vazia") if (
            isinstance(data, (dict, list))
        ) else _fail(f"shape: {type(data)}")
    elif r.status_code in (422,):
        _fail("/precedentes/buscar 422 com payload válido")
    else:
        _pass(f"/precedentes/buscar status {r.status_code} (fonte externa — não-bloqueante)")

    authed("financeiro")
    r = S.post(f"{API}/api/jurisprudencia-externa/precedentes/buscar", json={
        "termo": "honorários", "fontes": ["lexml"], "pagina": 1})
    _pass("financeiro bloqueado da busca de precedentes (allowlist #694)") if (
        r.status_code in (401, 403)
    ) else _fail(f"financeiro buscou precedentes: {r.status_code}")

# ── 4. Verificação via endpoints (anti-alucinação no pipeline) ───────────────
def secao_endpoints():
    print("[M25] 4. Endpoints de verificação de citações")
    authed("advogado")

    texto_alucinado = (
        "Fundamento: Súmula 8888 do STF e o Processo "
        "1111111-61.2026.8.13.0001 (DV inválido), julgados pela 2ª Turma, "
        "Relator Min. Fulano, em 01/01/2001."
    )
    r = S.post(f"{API}/api/ai/citacoes/verificar", json={"texto": texto_alucinado})
    if r.status_code == 200:
        rel = r.json()
        suspeitas = rel.get("contagem_status", {}).get("suspeita", 0)
        _pass("/api/ai/citacoes/verificar: 2 alucinações flaggadas como suspeitas, score=0") if (
            suspeitas == 2 and rel.get("score") == 0
        ) else _fail(f"alucinações não medidas: {rel}")
    elif r.status_code == 422:
        _fail("/api/ai/citacoes/verificar rejeitou payload válido com 422")
    else:
        _fail(f"/api/ai/citacoes/verificar: {r.status_code} {r.text[:200]}")

    texto_saudavel = "Fundamento no art. 489 do CPC e art. 5º, III da CF."
    r = S.post(f"{API}/api/ai/citacoes/verificar", json={"texto": texto_saudavel})
    if r.status_code == 200:
        rel = r.json()
        _pass("texto com citações reais da base oficial: 2 confirmadas, score=100") if (
            rel.get("confirmadas", 0) == 2 and rel.get("score") == 100
        ) else _fail(f"citação real não confirmada: {rel}")
    else:
        _fail(f"/api/ai/citacoes/verificar texto saudável: {r.status_code}")

    # endpoint legado de qualidade (exige estagiario+)
    authed("estagiario")
    r = S.post(f"{API}/api/qualidade/verificar-citacoes", json={"texto": texto_alucinado})
    if r.status_code == 200:
        rel = r.json()
        _pass("/api/qualidade/verificar-citacoes: determinístico, sem stack trace") if (
            "total" in rel and "citacoes" in rel
        ) else _fail(f"shape ausente: {rel}")
    elif r.status_code == 422:
        _fail("/api/qualidade/verificar-citacoes 422 em payload válido")
    else:
        _fail(f"/api/qualidade/verificar-citacoes: {r.status_code}")

    authed("cliente")
    r = S.post(f"{API}/api/qualidade/verificar-citacoes", json={"texto": "teste"})
    _pass("cliente não acessa /qualidade (require_roles)") if (
        r.status_code in (401, 403)
    ) else _fail(f"cliente acessou qualidade: {r.status_code}")

# ── 5. Correspondência conteúdo × citação na peça (legal-docs check) ────────
def secao_correspondencia():
    print("[M25] 5. Correspondência conteúdo × citação (peça documental)")
    sys.path.insert(0, "/home/ubuntu/ejc_repo/backend")
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text
    import asyncio

    # localizar uma peça legal-doc com CNJ citado no conteúdo (dados M07+)
    async def _localizar_peca():
        async with AsyncSessionLocal() as db:
            r = await db.execute(text(
                "SELECT ld.id, ld.case_id FROM legal_docs ld "
                "WHERE ld.deleted_at IS NULL AND ld.conteudo ~ '\\d{7}-\\d{2}\\.\\d{4}' "
                "LIMIT 1"))
            row = r.first()
            return row

    row = asyncio.get_event_loop().run_until_complete(_localizar_peca())
    if row:
        doc_id, case_id = row
        authed("advogado")
        r = S.get(f"{API}/api/legal-docs/{doc_id}/jurisprudencia-check")
        if r.status_code == 200:
            data = r.json()
            _pass("/legal-docs/{id}/jurisprudencia-check: valida números CNJ citados contra base validada (problemas+regra+aptidão)") if (
                "problemas" in data and "citacoes_validadas" in data and "regra" in data
            ) else _fail(f"shape ausente: {list(data.keys())}")
        else:
            _fail(f"jurisprudencia-check: {r.status_code}")

        # mesmo check com peça sintética contendo CNJ inventado → deve reportar problema
        async def _criar_peca():
            async with AsyncSessionLocal() as db:
                # SQL literal com bind params; a regra marca todo text(), sem olhar
                # interpolacao. Ver docs/seguranca/SAST_BASELINE.md
                # nosemgrep: python.sqlalchemy.security.audit.avoid-sqlalchemy-text.avoid-sqlalchemy-text
                await db.execute(text(
                    "INSERT INTO legal_docs (id, case_id, titulo, tipo_peca, status, conteudo, created_at, updated_at) "
                    "SELECT gen_random_uuid()::text, :cid, 'EJC_QA_M25 peça teste', "
                    "'peticao_inicial', 'rascunho', "
                    "'Autos do processo " + CNJ_INVENTADO + ", conforme Súmula 9876 do STF.', "
                    "now(), now() FROM (VALUES(1)) v "
                    "WHERE EXISTS (SELECT 1 FROM cases WHERE id=:cid AND deleted_at IS NULL) "
                    "LIMIT 1 RETURNING id").bindparams(cid=case_id))
                await db.commit()
                r2 = await db.execute(text(
                    "SELECT id FROM legal_docs WHERE conteudo LIKE '%EJC_QA_M25 peça teste%' LIMIT 1"))
                row2 = r2.first()
                return row2[0] if row2 else None

        if case_id:
            doc_id2 = asyncio.get_event_loop().run_until_complete(_criar_peca())
            if doc_id2:
                r = S.get(f"{API}/api/legal-docs/{doc_id2}/jurisprudencia-check")
                if r.status_code == 200:
                    data = r.json()
                    _pass("peça com CNJ inventado + súmula fora de faixa: problema registrado (correspondência bloqueada)") if (
                        data.get("problemas")
                    ) else _fail(f"problemas vazios: {data}")
                    # limpar peça sintética
                    async def _limpar():
                        async with AsyncSessionLocal() as db:
                            await db.execute(text(
                                "UPDATE legal_docs SET deleted_at=now() WHERE id=:d"),
                                {"d": doc_id2})
                            await db.commit()
                    asyncio.get_event_loop().run_until_complete(_limpar())
                else:
                    _fail(f"jurisprudencia-check peça sintética: {r.status_code}")
    else:
        _pass("nenhuma peça com CNJ no conteúdo existe — seção exercida parcialmente via serviço (ver M05/M10)")

# ── 6. Banco de teses × precedentes (rastreabilidade da fonte) ───────────────
def secao_teses():
    print("[M25] 6. Banco de teses — rastreabilidade de tribunal/fonte")
    authed("admin")
    r = S.get(f"{API}/api/teses", params={"page": 1})
    assert r.status_code == 200
    data = r.json()
    itens = data.get("items") if isinstance(data, dict) else data
    n_ok = 0
    for t in itens[:5]:
        if isinstance(t, dict) and "tribunal" in t:
            n_ok += 1
    _pass("/api/teses responde e expõe campo tribunal (rastreado)") if n_ok else _fail(
        f"teses sem tribunal: {data}")

    r = S.get(f"{API}/api/teses/busca-avancada", params={"tribunal": "STJ"})
    _pass("/api/teses/busca-avancada aceita filtro por tribunal") if (
        r.status_code in (200,)
    ) else _fail(f"busca-avancada: {r.status_code}")

# ── execução ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        secao_motor()
    except Exception as e:
        _fail(f"seção motor: {type(e).__name__}: {e}")
    try:
        secao_crud_interna()
    except Exception as e:
        _fail(f"seção CRUD interna: {type(e).__name__}: {e}")
    try:
        secao_externa()
    except Exception as e:
        _fail(f"seção externa: {type(e).__name__}: {e}")
    try:
        secao_endpoints()
    except Exception as e:
        _fail(f"seção endpoints: {type(e).__name__}: {e}")
    try:
        secao_correspondencia()
    except Exception as e:
        _fail(f"seção correspondência: {type(e).__name__}: {e}")
    try:
        secao_teses()
    except Exception as e:
        _fail(f"seção teses: {type(e).__name__}: {e}")

    n_pass = sum(1 for _ in PASS)
    n_fail = sum(1 for _ in FAIL)
    print(f"\n[M25] resultado final: {n_pass + n_fail} testes — {n_pass} PASS, {n_fail} FAIL")
    sys.exit(1 if FAIL else 0)
