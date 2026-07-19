# ── app/services/matriz_teses_service.py ─────────────────────────────────────
# FASE 3 do Orquestrador Jurídico — Matriz de Teses estruturada + pesquisa
# jurisprudencial por questões decompostas.
#
# Regras INVIOLÁVEIS deste módulo:
#   • AuthorityRecord NUNCA é inventado: só nasce de retorno REAL do RAG
#     (buscar_contexto_rag), sempre com trecho e referência. RAG vazio ⇒ zero
#     records. "verificada" só via verificador_jurisprudencia (grounding local
#     já existente) e SEMPRE com fonte_oficial.
#   • `forca` é DETERMINÍSTICO (calcular_forca, pesos fixos documentados) —
#     nunca nota dada por LLM.
#   • Favorável/contrário é heurística DETERMINÍSTICA por texto/metadados
#     (_classificar_favorabilidade) — nesta fase o LLM não rotula precedente.
#   • sanitizar_pii é aplicado pelo CHAMADOR (router) antes de qualquer prompt;
#     toda chamada de IA registra AILog.
#   • HITL: toda tese nasce "candidata"; aprovar/descartar é ato humano de
#     advogado+ com AuditLog (aprovar_tese).
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.core.config import get_settings
from app.models.ai_log import AILog, AIStatusHITL, AITipoUso
from app.models.audit_log import criar_audit_log
from app.models.matriz_teses import (
    AuthorityRecord, EvidenceLink, LegalIssue, STATUS_TESE, ThesisCandidate,
)
from app.models.prova import Prova
from app.models.tese import Tese, TeseStatus
from app.models.user import User
from app.services.ai_gateway import chat as gw_chat
from app.services.ai_service import buscar_contexto_rag
from app.services.verificador_jurisprudencia import verificar_jurisprudencia

logger = logging.getLogger("ejc.matriz_teses")

# ── Score determinístico (calcular_forca) — pesos FIXOS e documentados ───────
# forca = clamp 0..100 de:
#   +15  tem fundamento citável (texto não vazio)
#   +10  fundamento VERIFICADO: existe precedente com status "verificada"
#   + 5  por fato vinculado           (máx. 3 → até +15)
#   + 5  por prova vinculada          (máx. 3 → até +15)
#   +10  por ponto de SALDO de precedentes verificados (favoráveis − contrários,
#        saldo negativo vira 0; máx. 3 → até +30)
#   − 5  por vulnerabilidade listada  (máx. 3 → até −15)
# Nada aqui vem de LLM — só de contagens sobre os campos estruturados.
PESO_FUNDAMENTO = 15
PESO_FUNDAMENTO_VERIFICADO = 10
PESO_POR_FATO, MAX_FATOS = 5, 3
PESO_POR_PROVA, MAX_PROVAS = 5, 3
PESO_POR_SALDO_PRECEDENTE, MAX_SALDO = 10, 3
PENALIDADE_VULNERABILIDADE, MAX_VULNS = 5, 3

# Limite de questões decompostas por caso numa montagem (custo de RAG bounded).
MAX_QUESTOES = 8
# Top-k do RAG por questão.
RAG_LIMITE_POR_QUESTAO = 5
# Corte defensivo do trecho persistido no AuthorityRecord.
_TRUNC_TRECHO = 2_000

# Aviso obrigatório quando a decomposição responde mas o parse não extrai nada
# (falha NUNCA é silenciosa — matriz possivelmente incompleta).
AVISO_FALHA_PARSE = ("falha de parse da decomposição — matriz possivelmente "
                     "incompleta; repetir a montagem")

# ── Heurística determinística de favorabilidade (SEM LLM) ────────────────────
# Ordem importa: marcadores CONTRÁRIOS têm precedência ("improcedente" contém
# "procedente"; "desfavorável" contém "favorável"). Nenhum marcador ⇒ None.
_MARCADORES_CONTRARIOS: tuple[str, ...] = (
    "improceden", "nego provimento", "nega provimento", "negado provimento",
    "negou provimento", "nega-se provimento", "improvid",  # improvido/improvida
    "desprovido", "desprovimento", "indefer",
    "rejeit", "desfavor", "nao acolh", "não acolh",
)
_MARCADORES_FAVORAVEIS: tuple[str, ...] = (
    "proceden", "provido", "provimento", "defer", "acolh", "favor",
    "condena", "reconhece o direito",
)


def _classificar_favorabilidade(texto: str) -> bool | None:
    """True=favorável, False=contrário, None=indefinido. Determinística."""
    t = (texto or "").lower()
    if any(m in t for m in _MARCADORES_CONTRARIOS):
        return False
    if any(m in t for m in _MARCADORES_FAVORAVEIS):
        return True
    return None


# ── Decomposição de questões (UMA chamada de IA, AILog obrigatório) ──────────

SYS_QUESTOES = (
    "Você é um advogado sênior DECOMPONDO um caso em questões jurídicas a "
    "pesquisar (competência, prescrição/decadência, legitimidade, mérito, dano, "
    "prova, tutela provisória etc. — conforme o caso). Responda APENAS um objeto "
    "JSON válido (sem texto fora do JSON, sem markdown) com as chaves:\n"
    '{"questoes": [{"questao": "<questão jurídica objetiva, 1 frase>", '
    '"prioridade": <inteiro 1-5, 1=mais crítica>}, ...],'
    ' "teses_sugeridas": [{"tese": "<tese defensável, 1-2 frases>", '
    '"fundamento": "<dispositivos/princípios aplicáveis>", '
    '"questao_ref": <índice 1-based da questão de origem na lista "questoes", '
    "ou null se nenhuma>}, ...]}\n"
    "Baseie-se SÓ nos fatos. NÃO invente jurisprudência, súmula nem número de "
    "processo. Máximo de " + str(MAX_QUESTOES) + " questões."
)


def _parse_questoes(txt: str) -> dict:
    """Parse TOLERANTE do JSON da decomposição.

    Aceita cercas markdown, ruído em volta, lista crua de strings ou de dicts.
    Sempre devolve {"questoes": [{"questao","prioridade"}...],
    "teses_sugeridas": [{"tese","fundamento","questao_ref"}...]} (listas
    possivelmente vazias). `questao_ref` é o índice 1-based da questão de
    origem — inválido/fora do intervalo vira None (nunca chuta vínculo).
    """
    out: dict = {"questoes": [], "teses_sugeridas": []}
    if not txt:
        return out
    s = txt.strip()
    if s.startswith("```"):
        s = s.split("```")[1] if "```" in s[3:] else s[3:]
        s = s.lstrip("json").strip()
    i = min((k for k in (s.find("{"), s.find("[")) if k != -1), default=-1)
    j = max(s.rfind("}"), s.rfind("]"))
    if i == -1 or j == -1:
        return out
    try:
        data = json.loads(s[i:j + 1])
    except Exception:
        return out

    if isinstance(data, list):          # lista crua → trata como questões
        data = {"questoes": data}
    if not isinstance(data, dict):
        return out

    for q in (data.get("questoes") or [])[:MAX_QUESTOES]:
        if isinstance(q, str) and q.strip():
            out["questoes"].append({"questao": q.strip(), "prioridade": 3})
        elif isinstance(q, dict) and str(q.get("questao") or "").strip():
            try:
                pri = int(q.get("prioridade") or 3)
            except (TypeError, ValueError):
                pri = 3
            out["questoes"].append({
                "questao": str(q["questao"]).strip(),
                "prioridade": min(5, max(1, pri)),
            })
    for t in (data.get("teses_sugeridas") or []):
        if isinstance(t, str) and t.strip():
            out["teses_sugeridas"].append({"tese": t.strip(), "fundamento": None,
                                           "questao_ref": None})
        elif isinstance(t, dict) and str(t.get("tese") or "").strip():
            try:
                ref = int(t.get("questao_ref"))
            except (TypeError, ValueError):
                ref = None
            if ref is not None and not (1 <= ref <= len(out["questoes"])):
                ref = None      # fora do intervalo das questões parseadas
            out["teses_sugeridas"].append({
                "tese": str(t["tese"]).strip(),
                "fundamento": (str(t.get("fundamento") or "").strip() or None),
                "questao_ref": ref,
            })
    return out


async def decompor_questoes(
    db, user_id: str, case_id: str, area: str | None, fatos_sanitizados: str,
) -> dict:
    """Decompõe o caso em questões jurídicas — UMA chamada de IA via gateway.

    Pré-condição (contrato): `fatos_sanitizados` JÁ passou por sanitizar_pii no
    chamador. Grava AILog SEMPRE que a IA responde e persiste LegalIssues
    origem="ia" (commit aqui). IA desligada/indisponível ⇒ nenhum issue e
    nenhuma invenção — devolve listas vazias.

    Retorna {"issues": [LegalIssue...], "teses_sugeridas": [...], "ai_log_id",
    "avisos"} — `avisos` carrega AVISO_FALHA_PARSE quando a IA respondeu texto
    não vazio e o parse não extraiu NADA (falha nunca é silenciosa).
    """
    settings = get_settings()
    if not settings.AI_ENABLED or len((fatos_sanitizados or "").strip()) < 20:
        return {"issues": [], "teses_sugeridas": [], "ai_log_id": None,
                "avisos": []}

    user_msg = (f"ÁREA: {area or 'não informada'}\n\n"
                f"FATOS (já sanitizados):\n{fatos_sanitizados[:6000]}")
    resp = await gw_chat(
        messages=[{"role": "system", "content": SYS_QUESTOES},
                  {"role": "user", "content": user_msg}],
        task_type="estrategia",          # prosa coberta pela base anti-alucinação
        temperature=0.1, max_tokens=1200, nivel_inteligencia="alto",
    )
    bruto = getattr(resp, "texto", "") or ""

    ai_log_id = str(uuid4())
    modelo = getattr(resp, "modelo", None) or "desconhecido"
    provedor = getattr(resp, "provedor", None)
    db.add(AILog(
        id=ai_log_id, user_id=user_id, case_id=case_id,
        tipo_uso=AITipoUso.analise_caso,
        modelo=f"{provedor}/{modelo}" if provedor else modelo,
        prompt_sanitizado=user_msg[:8000], pii_removida=True,
        resposta=bruto[:8000], status_hitl=AIStatusHITL.gerado,
    ))

    data = _parse_questoes(bruto)
    avisos: list[str] = []
    if bruto.strip() and not data["questoes"] and not data["teses_sugeridas"]:
        # Resposta não vazia da IA sem NADA extraível → aviso obrigatório.
        avisos.append(AVISO_FALHA_PARSE)
    issues: list[LegalIssue] = []
    for q in data["questoes"]:
        issue = LegalIssue(
            id=str(uuid4()), case_id=case_id, questao=q["questao"],
            area=area or None, prioridade=q["prioridade"], origem="ia",
            criado_por=user_id,
        )
        db.add(issue)
        issues.append(issue)
    await db.commit()
    return {"issues": issues, "teses_sugeridas": data["teses_sugeridas"],
            "ai_log_id": ai_log_id, "avisos": avisos}


# ── Pesquisa por questão (RAG real → AuthorityRecord; nunca inventa) ─────────

async def pesquisar_por_questao(db, case_id: str, issue: LegalIssue) -> list[AuthorityRecord]:
    """Pesquisa RAG específica da questão e materializa AuthorityRecords.

    • Cada record nasce de UM retorno real do RAG (trecho + referência);
      RAG vazio ⇒ lista vazia (nunca inventa precedente).
    • favoravel: heurística determinística (_classificar_favorabilidade).
    • status_verificacao:
        "verificada"     — verificador_jurisprudencia confirmou ao menos uma
                           citação no grounding local ⇒ fonte_oficial preenchida;
        "nao_encontrada" — havia citação estruturada mas nada foi confirmado;
        "nao_verificada" — sem citação estruturada no trecho (ou verificador
                           indisponível — fail-safe).
    NÃO commita (o orquestrador montar_matriz commita ao final).
    """
    query = f"{issue.area or ''} {issue.questao}".strip()
    fontes = await buscar_contexto_rag(db, query, limite=RAG_LIMITE_POR_QUESTAO)
    records: list[AuthorityRecord] = []
    for f in fontes or []:
        trecho = (f.get("conteudo") or "").strip()
        if not trecho:
            continue  # sem trecho real não há record (invariante anti-invenção)

        status_verif, fonte_oficial = "nao_verificada", None
        tribunal = orgao = data_julg = None
        processo_ref = (f.get("titulo") or "")[:120] or None
        try:
            rel = await verificar_jurisprudencia(db, trecho)
            citacoes = rel.get("citacoes") or []
            estruturadas = [c for c in citacoes if c.get("tipo") != "generica"]
            verificadas = [c for c in estruturadas if c.get("status") == "verificada"]
            ref = (verificadas or estruturadas or [None])[0]
            if ref:
                tribunal = (ref.get("tribunal") or None)
                processo_ref = (ref.get("numero") or ref.get("citacao")
                                or processo_ref or "")[:120] or None
                orgao = (ref.get("orgao") or None)
                data_julg = (ref.get("data") or None)
            if verificadas:
                status_verif = "verificada"
                fonte_oficial = (verificadas[0].get("fonte_verificacao")
                                 or verificadas[0].get("fonte")
                                 or "base oficial interna/RAG")[:500]
            elif estruturadas:
                status_verif = "nao_encontrada"
        except Exception as e:  # verificador indisponível NUNCA inventa nem quebra
            logger.warning("[matriz_teses] verificador indisponível: %s", str(e)[:150])

        records.append(AuthorityRecord(
            id=str(uuid4()), case_id=case_id,
            tribunal=tribunal, processo_ref=processo_ref, orgao=orgao,
            data_julgamento=(data_julg or None),
            tema=issue.questao[:300],
            trecho=trecho[:_TRUNC_TRECHO],
            fonte_oficial=fonte_oficial,
            status_verificacao=status_verif,
            favoravel=_classificar_favorabilidade(trecho),
        ))
    for r in records:
        db.add(r)
    return records


# ── Score determinístico ─────────────────────────────────────────────────────

def calcular_forca(tese: ThesisCandidate | dict) -> int:
    """Score 0-100 DETERMINÍSTICO da tese (pesos fixos no topo do módulo)."""
    def _get(campo, default):
        if isinstance(tese, dict):
            return tese.get(campo) or default
        return getattr(tese, campo, None) or default

    fundamento = str(_get("fundamento", "") or "").strip()
    fatos = _get("fatos_relacionados", []) or []
    provas = _get("provas", []) or []
    precedentes = _get("precedentes", []) or []
    vulns = _get("vulnerabilidades", []) or []

    verificados = [p for p in precedentes
                   if isinstance(p, dict) and p.get("status_verificacao") == "verificada"]
    fav = sum(1 for p in verificados if p.get("favoravel") is True)
    contra = sum(1 for p in verificados if p.get("favoravel") is False)

    forca = 0
    if fundamento:
        forca += PESO_FUNDAMENTO
    if verificados:
        forca += PESO_FUNDAMENTO_VERIFICADO
    forca += min(len(fatos), MAX_FATOS) * PESO_POR_FATO
    forca += min(len(provas), MAX_PROVAS) * PESO_POR_PROVA
    forca += max(0, min(fav - contra, MAX_SALDO)) * PESO_POR_SALDO_PRECEDENTE
    forca -= min(len(vulns), MAX_VULNS) * PENALIDADE_VULNERABILIDADE
    return max(0, min(100, forca))


# ── Montagem da matriz (orquestração) ────────────────────────────────────────

def _ref_precedente(r: AuthorityRecord) -> dict:
    return {
        "authority_id": r.id, "tribunal": r.tribunal,
        "processo_ref": r.processo_ref,
        "status_verificacao": r.status_verificacao,
        "favoravel": r.favoravel, "fonte_oficial": r.fonte_oficial,
    }


def _tokens_relevantes(texto: str) -> set[str]:
    """Tokens normalizados (minúsculos, sem acento, ≥5 chars) p/ vínculo lexical."""
    import re
    import unicodedata
    norm = unicodedata.normalize("NFKD", (texto or "").lower())
    norm = norm.encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]{5,}", norm))


def _vincular_questao(texto: str, issues: list[LegalIssue]) -> str | None:
    """Vínculo DETERMINÍSTICO tese↔questão por sobreposição lexical.

    Escolhe a questão com mais tokens relevantes em comum com o texto da tese
    (título + descrição + fundamento). Sem NENHUM token em comum ⇒ None — a
    tese fica sem precedentes (nunca chuta vínculo nem anexa o pool inteiro).
    """
    toks = _tokens_relevantes(texto)
    melhor_id, melhor_score = None, 0
    for issue in issues:
        score = len(toks & _tokens_relevantes(issue.questao))
        if score > melhor_score:
            melhor_id, melhor_score = issue.id, score
    return melhor_id


async def montar_matriz(
    db, user_id: str, case_id: str, area: str | None, fatos_sanitizados: str,
) -> dict:
    """Orquestra a matriz: decompor → pesquisar → teses candidatas → forca.

    Teses candidatas vêm do Banco de Teses (models/tese.py — ativas da área) e
    das sugeridas pela MESMA chamada de IA da decomposição — TODAS nascem
    status "candidata" (HITL). Precedentes são associados POR QUESTÃO: cada
    tese recebe SÓ os AuthorityRecords da questão a que se vincula (issue_id).
    O vínculo é: `questao_ref` devolvido pela própria decomposição (tese
    sugerida) e, na falta dele (inclusive teses do Banco), sobreposição
    lexical determinística (_vincular_questao). Tese sem questão vinculável
    fica com lista vazia (sem boost de forca), para calcular_forca
    discriminar de verdade. EvidenceLinks são
    derivados das Provas do caso (fato_probando/tese_id — determinístico).
    Grava snapshot origem "matriz_teses" via gravar_snapshot_seguro (fail-safe,
    nunca quebra o fluxo).
    """
    dec = await decompor_questoes(db, user_id, case_id, area, fatos_sanitizados)
    issues: list[LegalIssue] = dec["issues"]
    avisos: list[str] = list(dec.get("avisos") or [])

    records: list[AuthorityRecord] = []
    refs_por_questao: dict[str, list[dict]] = {}
    for issue in issues:
        try:
            recs = await pesquisar_por_questao(db, case_id, issue)
            records.extend(recs)
            refs_por_questao[issue.id] = [_ref_precedente(r) for r in recs]
        except Exception as e:  # uma questão falhar não derruba a matriz
            logger.warning("[matriz_teses] pesquisa falhou (%s): %s",
                           issue.questao[:60], str(e)[:150])

    def _refs_da_tese(issue_id: str | None) -> list[dict]:
        """Precedentes SÓ da questão vinculada — sem vínculo, lista vazia
        (nunca anexar o pool inteiro a todas as teses)."""
        return list(refs_por_questao.get(issue_id) or []) if issue_id else []

    # Banco de Teses institucional — ativas da área (soft delete respeitado).
    q_teses = select(Tese).where(Tese.status == TeseStatus.ativa,
                                 Tese.deleted_at.is_(None))
    if area:
        q_teses = q_teses.where(Tese.area_juridica == area)
    teses_banco = list((await db.execute(q_teses.limit(20))).scalars().all())

    # Provas do caso — vínculos determinísticos fato × prova × tese.
    provas_caso = list((await db.execute(
        select(Prova).where(Prova.case_id == case_id, Prova.deleted_at.is_(None))
    )).scalars().all())

    provas_por_tese: dict[str, list[Prova]] = {}
    for p in provas_caso:
        if p.tese_id:
            provas_por_tese.setdefault(p.tese_id, []).append(p)

    candidatas: list[ThesisCandidate] = []
    mapa_tese_banco: dict[str, ThesisCandidate] = {}
    for t in teses_banco:
        provas_t = provas_por_tese.get(t.id, [])
        # Tese do Banco: vínculo lexical determinístico com a questão de origem;
        # sem questão vinculável → SEM precedentes (sem boost indevido).
        issue_id = _vincular_questao(
            " ".join(x for x in (t.titulo, t.descricao, t.fundamentacao) if x),
            issues)
        cand = ThesisCandidate(
            id=str(uuid4()), case_id=case_id, issue_id=issue_id,
            tese=(t.descricao or t.titulo),
            fundamento=(t.fundamentacao or None),
            fatos_relacionados=[p.fato_probando for p in provas_t if p.fato_probando],
            provas=[p.id for p in provas_t],
            precedentes=_refs_da_tese(issue_id),
            vulnerabilidades=([t.contra_argumento] if t.contra_argumento else []),
            status="candidata", criado_por=user_id,
        )
        cand.forca = calcular_forca(cand)
        db.add(cand)
        candidatas.append(cand)
        mapa_tese_banco[t.id] = cand

    for s in dec["teses_sugeridas"]:
        # Tese sugerida: a própria decomposição indica a questão de origem
        # (questao_ref 1-based, já validado no parse); fallback lexical.
        ref = s.get("questao_ref")
        issue_id = (issues[ref - 1].id
                    if isinstance(ref, int) and 1 <= ref <= len(issues) else None)
        if issue_id is None:
            issue_id = _vincular_questao(
                " ".join(x for x in (s["tese"], s.get("fundamento")) if x), issues)
        cand = ThesisCandidate(
            id=str(uuid4()), case_id=case_id, issue_id=issue_id,
            tese=s["tese"], fundamento=s.get("fundamento"),
            fatos_relacionados=[], provas=[],
            precedentes=_refs_da_tese(issue_id), vulnerabilidades=[],
            status="candidata", criado_por=user_id,
        )
        cand.forca = calcular_forca(cand)
        db.add(cand)
        candidatas.append(cand)

    links: list[EvidenceLink] = []
    for p in provas_caso:
        cand = mapa_tese_banco.get(p.tese_id) if p.tese_id else None
        links.append(EvidenceLink(
            id=str(uuid4()), case_id=case_id,
            fato=(p.fato_probando or p.titulo),
            prova_id=p.id, tese_id=(cand.id if cand else None), pedido=None,
        ))
    for lk in links:
        db.add(lk)

    await db.commit()

    matriz = _serializar_matriz(case_id, issues, candidatas, records, links)
    matriz["avisos"] = avisos

    # FASE 1 — snapshot versionado (fail-safe: nunca quebra a montagem).
    from app.services.case_intelligence_service import compactar_payload, gravar_snapshot_seguro
    n_verif = sum(1 for r in records if r.status_verificacao == "verificada")
    await gravar_snapshot_seguro(
        db, case_id=case_id, origem="matriz_teses",
        payload=compactar_payload({
            "area": area or None,
            "avisos": avisos,
            "teses": {"candidatas": [{"id": c.id, "tese": c.tese[:300],
                                      "forca": c.forca} for c in candidatas]},
            "questoes": [{"id": i.id, "questao": i.questao[:300],
                          "prioridade": i.prioridade} for i in issues],
            "precedentes": {"total": len(records), "verificados": n_verif},
            "provas": [p.id for p in provas_caso],
            "fontes": ["matriz_teses", "banco_teses", "rag"],
        }, descartaveis=("questoes", "teses")),
        resumo=(f"Matriz de teses (rascunho): {len(candidatas)} candidata(s), "
                f"{len(issues)} questão(ões), {len(records)} precedente(s) "
                f"({n_verif} verificados). HITL: aprovação por advogado."),
        ai_log_ids=[i for i in [dec["ai_log_id"]] if i],
        criado_por=user_id,
    )
    return matriz


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _ser_issue(i: LegalIssue) -> dict:
    return {"id": i.id, "questao": i.questao, "area": i.area,
            "prioridade": i.prioridade, "origem": i.origem,
            "criado_por": i.criado_por, "criado_em": _iso(i.criado_em)}


def _ser_tese(c: ThesisCandidate) -> dict:
    return {"id": c.id, "issue_id": c.issue_id, "tese": c.tese,
            "fundamento": c.fundamento,
            "fatos_relacionados": c.fatos_relacionados or [],
            "provas": c.provas or [], "precedentes": c.precedentes or [],
            "vulnerabilidades": c.vulnerabilidades or [],
            "forca": c.forca, "status": c.status,
            "aprovado_por": c.aprovado_por, "aprovado_em": _iso(c.aprovado_em)}


def _ser_authority(r: AuthorityRecord) -> dict:
    return {"id": r.id, "tribunal": r.tribunal, "processo_ref": r.processo_ref,
            "orgao": r.orgao, "data_julgamento": r.data_julgamento,
            "tema": r.tema, "trecho": r.trecho,
            "fonte_oficial": r.fonte_oficial,
            "status_verificacao": r.status_verificacao, "favoravel": r.favoravel}


def _ser_link(lk: EvidenceLink) -> dict:
    return {"id": lk.id, "fato": lk.fato, "prova_id": lk.prova_id,
            "tese_id": lk.tese_id, "pedido": lk.pedido}


def _serializar_matriz(case_id, issues, candidatas, records, links) -> dict:
    return {
        "case_id": case_id,
        "status": "rascunho",   # matriz inteira é rascunho até aprovação humana
        "questoes": [_ser_issue(i) for i in issues],
        "teses": [_ser_tese(c) for c in candidatas],
        "precedentes": [_ser_authority(r) for r in records],
        "vinculos": [_ser_link(lk) for lk in links],
    }


async def obter_matriz(db, case_id: str) -> dict:
    """Matriz persistida do caso (issues, teses, precedentes, vínculos)."""
    issues = list((await db.execute(
        select(LegalIssue).where(LegalIssue.case_id == case_id)
        .order_by(LegalIssue.prioridade))).scalars().all())
    teses = list((await db.execute(
        select(ThesisCandidate).where(ThesisCandidate.case_id == case_id)
        .order_by(ThesisCandidate.forca.desc()))).scalars().all())
    records = list((await db.execute(
        select(AuthorityRecord).where(AuthorityRecord.case_id == case_id)
    )).scalars().all())
    links = list((await db.execute(
        select(EvidenceLink).where(EvidenceLink.case_id == case_id)
    )).scalars().all())
    return _serializar_matriz(case_id, issues, teses, records, links)


# ── HITL — aprovação/descartes humanos com auditoria ─────────────────────────

async def aprovar_tese(
    db, tese_id: str, user: User, decisao: str = "aprovada",
    case_id: str | None = None,
) -> ThesisCandidate:
    """Advogado+ marca a tese candidata como aprovada/descartada (AuditLog).

    404 se não existe (ou não pertence ao case_id); 409 se já decidida.
    A decisão estratégica fica implícita no status + AuditLog (sem tabela extra).
    """
    if decisao not in ("aprovada", "descartada"):
        raise ValueError(f"decisão inválida: {decisao!r}")
    if not set(("aprovada", "descartada")) <= set(STATUS_TESE):
        # Invariante de vocabulário do model — exceção REAL (assert some com -O).
        raise RuntimeError(
            "STATUS_TESE não contém as decisões 'aprovada'/'descartada' — "
            "vocabulário do model inconsistente com o service")

    q = select(ThesisCandidate).where(ThesisCandidate.id == tese_id)
    if case_id is not None:
        q = q.where(ThesisCandidate.case_id == case_id)
    cand = (await db.execute(q)).scalar_one_or_none()
    if cand is None:
        raise HTTPException(status_code=404, detail="Tese não encontrada")
    if cand.status != "candidata":
        raise HTTPException(status_code=409,
                            detail=f"Tese já decidida (status={cand.status})")

    cand.status = decisao
    cand.aprovado_por = user.id
    cand.aprovado_em = datetime.now(timezone.utc)
    # Corrida (auditoria 8c): check-then-set mantido. Limite documentado:
    # re-select na MESMA transação devolve o próprio objeto do identity map,
    # então decisão dupla SIMULTÂNEA sobre a mesma tese não é detectável sem
    # SELECT ... FOR UPDATE; a janela é mínima, o 409 acima cobre o caso
    # sequencial e o AuditLog registra toda decisão (rastreável).

    role = getattr(user.role, "value", None) or str(getattr(user, "role", "") or "")
    await criar_audit_log(
        db, user_id=user.id, user_role=role,
        acao="UPDATE", entidade="thesis_candidates", registro_id=cand.id,
        detalhes=(f"Tese da matriz do caso {cand.case_id} marcada como "
                  f"'{decisao}' (HITL, forca={cand.forca})"),
    )
    await db.commit()
    return cand


# ── Bloco estruturado por questão p/ o pipeline de peças (flag-gated) ────────

async def bloco_pesquisa_estruturada(db, case_id: str) -> str:
    """Bloco textual FAVORÁVEIS/CONTRÁRIAS VERIFICADAS agrupado por questão.

    Consumido pela etapa de jurisprudência do peca_service quando
    PECAS_PESQUISA_QUESTOES_ENABLED=true E existe matriz montada. Sem matriz
    (nenhuma questão) devolve "" — o pipeline segue byte-idêntico.
    Só entram precedentes com status "verificada" (nunca material não conferido
    como se fosse fonte).
    """
    issues = list((await db.execute(
        select(LegalIssue).where(LegalIssue.case_id == case_id)
        .order_by(LegalIssue.prioridade))).scalars().all())
    if not issues:
        return ""
    records = list((await db.execute(
        select(AuthorityRecord).where(
            AuthorityRecord.case_id == case_id,
            AuthorityRecord.status_verificacao == "verificada")
    )).scalars().all())

    por_tema: dict[str, list[AuthorityRecord]] = {}
    for r in records:
        por_tema.setdefault(r.tema or "", []).append(r)

    linhas = ["\n\n[PESQUISA JURISPRUDENCIAL POR QUESTÃO — PRECEDENTES VERIFICADOS]"]
    for i in issues:
        linhas.append(f"Questão: {i.questao}")
        regs = por_tema.get((i.questao or "")[:300], [])
        fav = [r for r in regs if r.favoravel is True]
        contra = [r for r in regs if r.favoravel is False]
        indef = [r for r in regs if r.favoravel is None]
        for rotulo, grupo in (("Favoráveis", fav), ("Contrárias", contra),
                              ("Indefinidas", indef)):
            if not grupo:
                continue
            linhas.append(f"  {rotulo} (verificadas):")
            for r in grupo[:3]:
                ref = " ".join(x for x in (r.tribunal, r.processo_ref) if x)
                linhas.append(f"    - [{ref or 'ref. interna'}] "
                              f"{(r.trecho or '')[:280]} (fonte: {r.fonte_oficial})")
        if not regs:
            linhas.append("  (sem precedente verificado para esta questão)")
    return "\n".join(linhas)
