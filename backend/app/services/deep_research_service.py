"""
deep_research_service.py — Deep Research jurídica (pesquisa multi-etapa).

Pipeline que roda em BACKGROUND (fastapi.BackgroundTasks) por minutos, não
segundos, gravando o andamento num job persistido (DeepResearchJob). O cliente
faz POLLING. SEM Celery/Redis.

Etapas:
  1. Decompõe a pergunta/tese em sub-questões (via AI Gateway).
  2. Para cada sub-questão: busca na base interna (RAG/pgvector) e, quando faz
     sentido, aciona o crawler externo (STJ/SCON). Falha do crawler é tratada
     graciosamente (não derruba o job).
  3. Sintetiza um relatório final com FONTES RASTREÁVEIS.
  4. Verifica as citações do relatório contra a base oficial (anti-alucinação).

Toda chamada de IA passa pelo AI Gateway central (nunca provider direto) e grava
AILog (trilha HITL/LGPD). Todo resultado é RASCUNHO — exige revisão do advogado.

Limites de segurança: teto de sub-questões e de chamadas de IA, além de timeout
por etapa. Falha real → status "erro" com mensagem honesta (nunca "success" vazio).
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.core.database import AsyncSessionLocal
from app.models.ai_log import AITipoUso
from app.models.deep_research import DeepResearchJob, DeepResearchStatus
from app.services import ai_gateway, ai_service, citation_check, crawler_precedentes
from app.services.ai_guard import registrar_ai_log
from app.services.sanitizer import sanitizar_pii

logger = logging.getLogger("ejc.deep_research")

# ── Limites de segurança (evitam rodar indefinidamente / custo descontrolado) ──
MAX_SUBQUESTOES = 8           # teto de sub-questões investigadas
MAX_CHAMADAS_IA = 12          # teto de chamadas ao gateway por job
RAG_LIMITE_POR_SUBQUESTAO = 5  # trechos recuperados por sub-questão
TIMEOUT_ETAPA_S = 90.0        # timeout por chamada de IA / crawler

_AVISO_RASCUNHO = (
    "RASCUNHO gerado por IA em pesquisa multi-etapa — revisão obrigatória do "
    "advogado responsável (OAB). Não substitui a análise humana. Fontes NÃO "
    "verificadas devem ser conferidas manualmente."
)

_SYS_DECOMPOR = (
    "Você é um pesquisador jurídico sênior. Decomponha a questão/tese abaixo em "
    "sub-questões objetivas e independentes que precisam ser investigadas para "
    "responder com rigor. Devolva APENAS um array JSON de strings (sem comentários, "
    "sem numeração), no máximo 8 itens. Não invente fontes."
)

_SYS_SINTESE = (
    "Você é um pesquisador jurídico sênior. Com base EXCLUSIVAMENTE no conhecimento "
    "recuperado (base interna e precedentes), redija um relatório estruturado que "
    "responda à questão. Para cada afirmação relevante, cite a fonte entre colchetes "
    "no formato [Fonte N]. Se algo NÃO tiver base no material fornecido, marque "
    "explicitamente como 'SEM BASE VERIFICÁVEL — conferir manualmente'. NÃO invente "
    "jurisprudência, súmula ou legislação. Toda a saída é rascunho para revisão humana."
)

# Sinais de que a sub-questão pede busca de jurisprudência externa (crawler STJ).
_GATILHOS_CRAWLER = (
    "jurisprud", "precedent", "súmula", "sumula", "stj", "stf", "entendimento",
    "tribunal", "acórdão", "acordao", "decisão", "decisao", "julgado",
)


# ══════════════════════════════════════════════════════════════════════════════
# Criação do job (chamado pelo endpoint, dentro da request)
# ══════════════════════════════════════════════════════════════════════════════
async def criar_job(
    db, *, user_id: str, pergunta: str, tese: str | None,
    case_id: str | None, nivel_inteligencia: str = "alto",
) -> DeepResearchJob:
    """Cria o job em status 'em_andamento' e persiste. O worker é disparado
    separadamente (BackgroundTasks) com o job.id."""
    job = DeepResearchJob(
        id=str(uuid4()),
        user_id=user_id,
        case_id=case_id,
        pergunta=pergunta,
        tese=tese,
        nivel_inteligencia=nivel_inteligencia,
        status=DeepResearchStatus.em_andamento,
        progresso=0,
        etapa_atual="Na fila",
        etapas_json=json.dumps([], ensure_ascii=False),
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


# ══════════════════════════════════════════════════════════════════════════════
# Entrypoint do worker em background (abre a PRÓPRIA sessão — a da request já
# foi fechada quando a resposta retornou)
# ══════════════════════════════════════════════════════════════════════════════
async def executar_deep_research(job_id: str) -> None:
    """Alvo de BackgroundTasks.add_task. Abre sessão própria, carrega o job e
    roda o pipeline. Qualquer exceção → status 'erro' com mensagem honesta."""
    async with AsyncSessionLocal() as db:
        job = await db.get(DeepResearchJob, job_id)
        if job is None:
            logger.error("[DeepResearch] job %s não encontrado no worker", job_id)
            return
        try:
            await run_pipeline(db, job)
        except Exception as e:  # noqa: BLE001 — precisamos marcar erro honesto
            logger.exception("[DeepResearch] job %s falhou", job_id)
            await _marcar_erro(db, job, str(e)[:500])


# ══════════════════════════════════════════════════════════════════════════════
# Pipeline (testável — recebe db + job já carregados)
# ══════════════════════════════════════════════════════════════════════════════
async def run_pipeline(db, job: DeepResearchJob) -> DeepResearchJob:
    etapas: list[dict] = []

    await _progresso(db, job, 5, "Decompondo a questão em sub-questões", etapas)

    # ── Etapa 1: decomposição ────────────────────────────────────────────────
    subquestoes = await _decompor(db, job)
    subquestoes = subquestoes[:MAX_SUBQUESTOES]
    job.total_subquestoes = len(subquestoes)
    _reg(etapas, "decomposicao", f"{len(subquestoes)} sub-questões geradas")
    await _progresso(db, job, 15, f"{len(subquestoes)} sub-questões a investigar", etapas)

    if not subquestoes:
        raise RuntimeError("Não foi possível decompor a questão em sub-questões.")

    # ── Etapa 2: fan-out de buscas (RAG interno + crawler externo) ────────────
    achados: list[dict] = []   # {subquestao, fontes:[{titulo,categoria,fonte,trecho}], precedentes:[...]}
    n = len(subquestoes)
    for i, sq in enumerate(subquestoes):
        rag_fontes = await _buscar_rag(db, sq)
        precedentes = await _buscar_crawler(sq)
        achados.append({"subquestao": sq, "fontes": rag_fontes, "precedentes": precedentes})
        _reg(etapas, "busca",
             f"[{i+1}/{n}] {sq[:80]} → {len(rag_fontes)} trecho(s) RAG, "
             f"{len(precedentes)} precedente(s)")
        # 15 → 70% distribuído entre as sub-questões
        prog = 15 + int(55 * (i + 1) / n)
        await _progresso(db, job, prog, f"Investigando sub-questão {i+1}/{n}", etapas)

    # ── Etapa 3: síntese com fontes rastreáveis ──────────────────────────────
    await _progresso(db, job, 72, "Sintetizando relatório final", etapas)
    fontes_catalogo = _catalogar_fontes(achados)
    relatorio_texto = await _sintetizar(db, job, achados, fontes_catalogo)
    _reg(etapas, "sintese", f"Relatório gerado ({len(relatorio_texto)} caracteres)")
    await _progresso(db, job, 85, "Verificando citações do relatório", etapas)

    # ── Etapa 4: verificação de citações (anti-alucinação) ───────────────────
    try:
        verificacao = await asyncio.wait_for(
            citation_check.verificar_citacoes(db, relatorio_texto),
            timeout=TIMEOUT_ETAPA_S,
        )
    except Exception as e:  # noqa: BLE001 — verificação é best-effort, não derruba o job
        logger.warning("[DeepResearch] verificação de citações falhou: %s", e)
        verificacao = {"erro": f"verificação indisponível: {str(e)[:160]}"}
    _reg(etapas, "verificacao_citacoes",
         f"{verificacao.get('confirmadas', 0)}/{verificacao.get('total', 0)} citações confirmadas")

    # ── Finalização ──────────────────────────────────────────────────────────
    resultado = {
        "aviso": _AVISO_RASCUNHO,
        "is_rascunho": True,
        "pergunta": job.pergunta,
        "tese": job.tese,
        "subquestoes": subquestoes,
        "relatorio": relatorio_texto,
        "fontes": fontes_catalogo,
        "verificacao_citacoes": verificacao,
        "total_chamadas_ia": job.total_chamadas_ia,
    }
    job.resultado_json = json.dumps(resultado, ensure_ascii=False)
    job.status = DeepResearchStatus.concluido
    job.concluido_em = datetime.now(timezone.utc)
    await _progresso(db, job, 100, "Concluído", etapas)
    return job


# ══════════════════════════════════════════════════════════════════════════════
# Etapas internas
# ══════════════════════════════════════════════════════════════════════════════
async def _decompor(db, job: DeepResearchJob) -> list[str]:
    base = f"QUESTÃO: {job.pergunta}"
    if job.tese:
        base += f"\n\nTESE A INVESTIGAR: {job.tese}"
    limpo, houve_pii = sanitizar_pii(base)
    resp = await _chamar_ia(
        db, job,
        messages=[{"role": "system", "content": _SYS_DECOMPOR},
                  {"role": "user", "content": limpo}],
        task_type="analise_juridica",
        tipo_uso=AITipoUso.analise_caso,
        pii_removida=houve_pii,
    )
    return _parse_subquestoes(resp.texto, fallback=job.pergunta)


async def _buscar_rag(db, subquestao: str) -> list[dict]:
    """Busca semântica na base interna (pgvector). Retorna fontes normalizadas."""
    try:
        resultados = await asyncio.wait_for(
            ai_service.buscar_contexto_rag(
                db, subquestao, limite=RAG_LIMITE_POR_SUBQUESTAO, modo_or=True,
            ),
            timeout=TIMEOUT_ETAPA_S,
        )
    except Exception as e:  # noqa: BLE001 — RAG indisponível não derruba o job
        logger.warning("[DeepResearch] RAG falhou para %r: %s", subquestao[:60], e)
        return []
    fontes = []
    for r in resultados or []:
        fontes.append({
            "titulo": r.get("titulo"),
            "categoria": r.get("categoria"),
            "fonte": r.get("fonte"),
            "trecho": (r.get("conteudo") or "")[:1200],
            "score": r.get("score"),
        })
    return fontes


async def _buscar_crawler(subquestao: str) -> list[dict]:
    """Aciona o crawler externo (STJ/SCON) apenas quando a sub-questão pede
    jurisprudência. Falha de rede/HTTP é tratada graciosamente."""
    if not _deve_consultar_crawler(subquestao):
        return []
    try:
        res = await asyncio.wait_for(
            crawler_precedentes.crawler.buscar_precedentes_magistrado("", subquestao),
            timeout=TIMEOUT_ETAPA_S,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("[DeepResearch] crawler falhou para %r: %s", subquestao[:60], e)
        return []
    if not isinstance(res, dict) or res.get("status") != "success":
        # Erro honesto do crawler (rede/layout) → simplesmente sem precedentes.
        return []
    precedentes = []
    for p in (res.get("precedentes") or [])[:5]:
        precedentes.append({
            "ementa": (p.get("ementa") or "")[:1200],
            "tribunal": p.get("tribunal", "STJ"),
            "fonte": p.get("fonte", res.get("fonte", "STJ/SCON")),
            "url": res.get("url"),
        })
    return precedentes


async def _sintetizar(db, job: DeepResearchJob, achados: list[dict],
                      fontes_catalogo: list[dict]) -> str:
    """Monta o contexto rastreável e pede a síntese ao gateway."""
    if not fontes_catalogo:
        return (
            "SEM BASE VERIFICÁVEL — a pesquisa não recuperou fontes internas nem "
            "precedentes externos para as sub-questões investigadas. "
            "Recomenda-se pesquisa manual. " + _AVISO_RASCUNHO
        )
    linhas = []
    for f in fontes_catalogo:
        rot = f"[Fonte {f['n']}] ({f.get('categoria') or f.get('tribunal') or 'fonte'} · {f.get('fonte') or ''})"
        linhas.append(f"{rot} {f.get('titulo') or ''}\n{f.get('trecho') or f.get('ementa') or ''}")
    contexto = "\n\n---\n\n".join(linhas)

    pergunta = f"QUESTÃO: {job.pergunta}"
    if job.tese:
        pergunta += f"\nTESE: {job.tese}"
    sub = "\n".join(f"- {a['subquestao']}" for a in achados)
    user_msg = (
        f"{pergunta}\n\nSUB-QUESTÕES INVESTIGADAS:\n{sub}\n\n"
        f"## CONHECIMENTO RECUPERADO (use SOMENTE isto e cite [Fonte N]):\n{contexto}"
    )
    limpo, houve_pii = sanitizar_pii(user_msg)
    resp = await _chamar_ia(
        db, job,
        messages=[{"role": "system", "content": _SYS_SINTESE},
                  {"role": "user", "content": limpo[:24000]}],
        task_type="analise_juridica",
        tipo_uso=AITipoUso.consulta_rag,
        pii_removida=houve_pii,
        max_tokens=3000,
        fontes_rag=json.dumps(
            [f.get("titulo") or f.get("tribunal") or f.get("fonte") for f in fontes_catalogo],
            ensure_ascii=False)[:4000],
    )
    return resp.texto


# ── Helpers ───────────────────────────────────────────────────────────────────
async def _chamar_ia(db, job: DeepResearchJob, *, messages, task_type, tipo_uso,
                     pii_removida: bool, max_tokens: int = 2048,
                     fontes_rag: str | None = None):
    """Chama o gateway respeitando o teto de chamadas e gravando AILog (HITL)."""
    if job.total_chamadas_ia >= MAX_CHAMADAS_IA:
        raise RuntimeError(
            f"Limite de {MAX_CHAMADAS_IA} chamadas de IA atingido para este job."
        )
    resp = await asyncio.wait_for(
        ai_gateway.chat(
            messages=messages, task_type=task_type, max_tokens=max_tokens,
            nivel_inteligencia=job.nivel_inteligencia,
        ),
        timeout=TIMEOUT_ETAPA_S,
    )
    job.total_chamadas_ia += 1
    await registrar_ai_log(
        db, user_id=job.user_id, tipo_uso=tipo_uso, case_id=job.case_id,
        prompt_sanitizado=messages[-1]["content"][:8000], pii_removida=pii_removida,
        resposta=resp.texto, modelo=f"{resp.provedor}/{resp.modelo}",
        fontes_rag=fontes_rag,
        tokens_input=resp.input_tokens, tokens_output=resp.output_tokens,
    )
    return resp


def _deve_consultar_crawler(texto: str) -> bool:
    t = (texto or "").lower()
    return any(g in t for g in _GATILHOS_CRAWLER)


def _catalogar_fontes(achados: list[dict]) -> list[dict]:
    """Achata todas as fontes num catálogo numerado [Fonte N] rastreável."""
    catalogo: list[dict] = []
    n = 0
    for a in achados:
        for f in a.get("fontes", []):
            n += 1
            catalogo.append({"n": n, "tipo": "rag", **f})
        for p in a.get("precedentes", []):
            n += 1
            catalogo.append({"n": n, "tipo": "precedente", **p})
    return catalogo


def _parse_subquestoes(texto: str, fallback: str) -> list[str]:
    """Extrai o array JSON de sub-questões; degrada para linhas/pergunta original."""
    if not texto:
        return [fallback]
    inicio, fim = texto.find("["), texto.rfind("]")
    if inicio != -1 and fim > inicio:
        try:
            arr = json.loads(texto[inicio:fim + 1])
            itens = [str(x).strip() for x in arr if str(x).strip()]
            if itens:
                return itens
        except (json.JSONDecodeError, ValueError):
            pass
    # Fallback: linhas não vazias, limpando marcadores comuns.
    linhas = [l.strip(" -*0123456789.").strip() for l in texto.splitlines()]
    itens = [l for l in linhas if len(l) > 8]
    return itens or [fallback]


def _reg(etapas: list[dict], etapa: str, detalhe: str) -> None:
    etapas.append({
        "etapa": etapa, "detalhe": detalhe,
        "ts": datetime.now(timezone.utc).isoformat(),
    })


async def _progresso(db, job: DeepResearchJob, progresso: int, etapa_atual: str,
                     etapas: list[dict]) -> None:
    """Persiste o andamento para o polling do cliente enxergar em tempo real."""
    job.progresso = progresso
    job.etapa_atual = etapa_atual
    job.etapas_json = json.dumps(etapas, ensure_ascii=False)
    await db.commit()


async def _marcar_erro(db, job: DeepResearchJob, mensagem: str) -> None:
    job.status = DeepResearchStatus.erro
    job.erro_mensagem = mensagem
    job.concluido_em = datetime.now(timezone.utc)
    try:
        await db.commit()
    except Exception:  # noqa: BLE001 — não mascarar o erro original
        await db.rollback()
