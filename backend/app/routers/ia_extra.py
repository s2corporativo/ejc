# ── app/routers/ia_extra.py ───────────────────────────────────────────────────
# Onda 2 — IA jurídica: tradução de andamento p/ cliente, geração de minuta com
# RAG e pesquisa jurídica. Mesma pipeline segura do ai_service: sanitiza PII
# (LGPD) → AI Gateway central (barreira anti-alucinação + pseudonimização +
# fallback de providers) → registra AILog → devolve como RASCUNHO (revisão OAB).
#
# FASE 1b (MAPA_PROMPTS_IA03 §5 Passo 2): todos os fluxos usam task_type coberto
# pela base central (legal_base._TASKS_COM_BASE) quando a saída é PROSA; fluxo de
# saída JSON (sugestao_honorarios) mantém o task e PREPENDE BASE_ESTRUTURADA no
# system (mesmo padrão das etapas intermediárias do peca_service). As regras
# inline de cada prompt são PRESERVADAS — a base central é aditiva.
from __future__ import annotations
import json
import logging
from uuid import uuid4
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.config import get_settings
from app.core.security import get_current_user
from app.models.user import User
from app.models.ai_log import AILog, AITipoUso, AIStatusHITL
from app.services.ai_service import (
    buscar_contexto_rag, _modelo_log, _tokens_input, _tokens_output,
)
from app.services.ai_gateway import chat as gw_chat, GatewayResponse
from app.services.legal_base import BASE_ESTRUTURADA
from app.services.sanitizer import sanitizar_pii
from app.services.ai_guard import sanitizar_ou_abortar
from app.core.rate_limit import rate_limit

settings = get_settings()
logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["IA — Assistente"])


async def _ia(system: str, user: str, task_type: str = "analise_juridica", temperature: float = 0.2, max_tokens: int = 1200, nivel: str = "alto") -> tuple[str, GatewayResponse]:
    resp = await gw_chat(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        task_type=task_type,
        temperature=temperature,
        max_tokens=max_tokens,
        nivel_inteligencia=nivel,
    )
    return resp.texto, resp


async def _log(db, user_id, tipo, case_id, prompt, pii, resposta, resp=None):
    # FASE 1b: o AILog registra o provedor/modelo REAL devolvido pelo gateway
    # (antes: settings.GROQ_MODEL hardcoded) e os tokens reais — mesma
    # rastreabilidade HITL do ai_service (_modelo_log/_tokens_*). Fallback
    # conservador: sem `resp`, mantém o comportamento anterior.
    log = AILog(
        id=str(uuid4()), user_id=user_id, case_id=case_id, tipo_uso=tipo,
        modelo=_modelo_log(resp) if resp is not None else settings.GROQ_MODEL,
        prompt_sanitizado=prompt[:8000],
        pii_removida=pii, resposta=resposta,
        tokens_input=_tokens_input(resp) if resp is not None else None,
        tokens_output=_tokens_output(resp) if resp is not None else None,
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log); await db.commit()
    return log.id


# ── Traduzir andamento para linguagem do cliente ──────────────────────────────
class TraduzirIn(BaseModel):
    texto: str = Field(min_length=5, max_length=8000)
    case_id: Optional[str] = None

SYS_TRADUZIR = (
    "Você é um advogado que explica o processo ao CLIENTE leigo. Reescreva o "
    "andamento processual abaixo em português claro e acolhedor, SEM jargão "
    "jurídico, em até 2 parágrafos curtos. Explique o que aconteceu e o que o "
    "cliente deve esperar. Não invente fatos nem dê garantias de resultado."
)

@router.post("/traduzir-andamento", dependencies=[Depends(rate_limit("ia-traduzir", 15))])
async def traduzir_andamento(body: TraduzirIn, db: AsyncSession = Depends(get_db),
                             cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    if body.case_id:
        from app.core.ownership import verificar_acesso_caso
        await verificar_acesso_caso(db, cu, body.case_id)  # não polui AILog de caso alheio
    limpo, pii = sanitizar_ou_abortar(body.texto)
    try:
        # Prosa p/ o cliente → task coberto pela base ("resumo" fica FORA de
        # _TASKS_COM_BASE); "chat_rapido" preserva o tier leve.
        resposta, resp = await _ia(SYS_TRADUZIR, limpo, task_type="chat_rapido", temperature=0.25, max_tokens=900, nivel="alto")
    except Exception:
        logger.exception("Falha na chamada de IA")
        raise HTTPException(502, "Falha ao processar a solicitação de IA")
    log_id = await _log(db, cu.id, AITipoUso.outro, body.case_id, limpo, pii, resposta, resp)
    return {"ai_log_id": log_id, "resposta": resposta,
            "aviso": "⚠️ Texto gerado por IA — revise antes de enviar ao cliente."}


# ── Resumir texto (peça/decisão/processo longo) ───────────────────────────────
class ResumirIn(BaseModel):
    texto: str = Field(min_length=20, max_length=12000)
    case_id: Optional[str] = None

SYS_RESUMIR = (
    "Você é assistente jurídico. Resuma o texto abaixo em tópicos objetivos "
    "(pontos-chave, decisão/pedido, prazos e próximos passos, se houver). "
    "Não invente nada que não esteja no texto."
)

@router.post("/resumir-texto", dependencies=[Depends(rate_limit("ia-resumir", 15))])
async def resumir_texto(body: ResumirIn, db: AsyncSession = Depends(get_db),
                        cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    if body.case_id:
        from app.core.ownership import verificar_acesso_caso
        await verificar_acesso_caso(db, cu, body.case_id)  # não polui AILog de caso alheio
    limpo, pii = sanitizar_ou_abortar(body.texto)
    try:
        # MAPA: resumo de texto jurídico é PROSA → task coberto pela base
        # ("resumo" não recebe aplicar_base); "chat_rapido" mantém o tier leve.
        resposta, resp = await _ia(SYS_RESUMIR, limpo, task_type="chat_rapido", temperature=0.1, max_tokens=1400, nivel="alto")
    except Exception:
        logger.exception("Falha na chamada de IA")
        raise HTTPException(502, "Falha ao processar a solicitação de IA")
    log_id = await _log(db, cu.id, AITipoUso.resumo_documento, body.case_id, limpo, pii, resposta, resp)
    return {"ai_log_id": log_id, "resposta": resposta,
            "aviso": "⚠️ Resumo gerado por IA — confira com o original."}


# ── Gerar minuta de peça com apoio do RAG ─────────────────────────────────────
class MinutaIn(BaseModel):
    tema: str = Field(min_length=5, max_length=2000)
    tipo_peca: str = "petição inicial"
    area: Optional[str] = None
    fatos: Optional[str] = None
    case_id: Optional[str] = None

SYS_MINUTA = (
    "Você é advogado redator. Produza um RASCUNHO de {tipo} na área de {area}, "
    "estruturado (endereçamento, qualificação [deixe placeholders], dos fatos, "
    "do direito, dos pedidos). Use a base de jurisprudência/teses fornecida como "
    "CONTEXTO quando pertinente, citando-a. NÃO invente jurisprudência nem números "
    "de processo. Deixe claro onde faltam dados com [COLCHETES]."
)

@router.post("/gerar-minuta", dependencies=[Depends(rate_limit("ia-gerar-minuta", 10))])
async def gerar_minuta(body: MinutaIn, db: AsyncSession = Depends(get_db),
                       cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    # Bloco 5 (continuação): case_id existia mas sem checagem de ownership.
    escopo_cli = None
    if body.case_id:
        from app.core.ownership import verificar_acesso_caso
        from app.services.ai_service import _escopo_cliente_do_caso
        await verificar_acesso_caso(db, cu, body.case_id)
        escopo_cli = await _escopo_cliente_do_caso(db, body.case_id)
    contexto = await buscar_contexto_rag(db, body.tema, limite=5, scope_client_id=escopo_cli)
    # Conteúdo vindo do RAG (base do escritório) é só sanitizado (sem abort) —
    # é conteúdo interno já existente, não texto digitado agora; abortar aqui
    # bloquearia peças legítimas por PII residual em precedentes antigos.
    ctx_txt, _ = sanitizar_pii(
        "\n\n".join(f"- {c.get('titulo','')}: {(c.get('conteudo') or '')[:500]}"
                    for c in contexto) or "(sem contexto relevante)"
    )
    fatos_limpo, pii = sanitizar_ou_abortar(body.fatos or body.tema)
    system = SYS_MINUTA.format(tipo=body.tipo_peca, area=body.area or "geral")
    user = f"TEMA: {body.tema}\n\nFATOS: {fatos_limpo}\n\nCONTEXTO (base do escritório):\n{ctx_txt}"
    try:
        # "elaboracao_peca" ∈ _TASKS_COM_BASE — redação de minuta já coberta.
        resposta, resp = await _ia(system, user, task_type="elaboracao_peca", temperature=0.18, max_tokens=3200, nivel="alto")
    except Exception:
        logger.exception("Falha na chamada de IA")
        raise HTTPException(502, "Falha ao processar a solicitação de IA")
    log_id = await _log(db, cu.id, AITipoUso.redacao_peca, body.case_id, user, pii, resposta, resp)
    return {"ai_log_id": log_id, "resposta": resposta,
            "fontes": [{"titulo": c.get("titulo"), "categoria": c.get("categoria")} for c in contexto],
            "aviso": "⚠️ RASCUNHO gerado por IA — revisão humana obrigatória (OAB)."}


# ── Pesquisa jurídica (RAG + IA) ──────────────────────────────────────────────
class PesquisaIn(BaseModel):
    pergunta: str = Field(min_length=5, max_length=2000)

SYS_PESQUISA = (
    "Você é assistente de pesquisa jurídica do escritório. Responda à pergunta "
    "usando PRINCIPALMENTE o contexto fornecido (base interna). Seja objetivo, cite "
    "as fontes do contexto e, se a base não cobrir, diga isso explicitamente em vez "
    "de inventar. Não dê garantias de resultado."
)

@router.post("/pesquisar", dependencies=[Depends(rate_limit("ia-pesquisar", 15))])
async def pesquisar(body: PesquisaIn, db: AsyncSession = Depends(get_db),
                    cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    pergunta_limpa, pii = sanitizar_ou_abortar(body.pergunta)
    contexto = await buscar_contexto_rag(db, pergunta_limpa, limite=6)
    ctx_txt, _ = sanitizar_pii(
        "\n\n".join(f"- {c.get('titulo','')}: {(c.get('conteudo') or '')[:600]}"
                    for c in contexto) or "(base sem resultados relevantes)"
    )
    user = f"PERGUNTA: {pergunta_limpa}\n\nCONTEXTO:\n{ctx_txt}"
    try:
        # Pesquisa jurídica é PROSA grounded no RAG → "estrategia" (∈
        # _TASKS_COM_BASE); a cadeia de modelos é IDÊNTICA à de
        # "analise_juridica" (ollama ANALISE → anthropic COMPLEXO → groq),
        # então o roteamento não muda — só ganha a base anti-alucinação.
        resposta, resp = await _ia(SYS_PESQUISA, user, task_type="estrategia", temperature=0.12, max_tokens=2200, nivel="alto")
    except Exception:
        logger.exception("Falha na chamada de IA")
        raise HTTPException(502, "Falha ao processar a solicitação de IA")
    log_id = await _log(db, cu.id, AITipoUso.consulta_rag, None, user, pii, resposta, resp)
    return {"ai_log_id": log_id, "resposta": resposta,
            "fontes": [{"titulo": c.get("titulo"), "categoria": c.get("categoria")} for c in contexto],
            "aviso": "⚠️ Resposta gerada por IA — confira as fontes antes de usar em peça ou orientar o cliente."}


# ── ETAPA 4 — Motor de honorários (tabela OAB/MG via RAG) ─────────────────────
def _pj(txt: str) -> Optional[dict]:
    if not txt:
        return None
    i, j = txt.find("{"), txt.rfind("}")
    try:
        return json.loads(txt[i:j + 1]) if i != -1 and j != -1 else None
    except Exception:
        return None


class HonorariosIn(BaseModel):
    area: str = Field(min_length=2, max_length=60)
    descricao: str = Field(min_length=3, max_length=600)   # o serviço/ato
    valor_causa: Optional[float] = None


SYS_HONORARIOS = (
    "Você é especialista em honorários advocatícios. Com base APENAS nos TRECHOS da "
    "Tabela de Honorários da OAB/MG fornecidos, sugira honorários para o serviço descrito. "
    "Responda APENAS JSON válido: "
    '{"honorario_minimo_oab": "<valor/regra da tabela, ex: R$ X ou 10% do valor da causa>",'
    ' "honorario_recomendado": "<sugestão prática, pode ser faixa>",'
    ' "percentual_exito": "<faixa, ex: 20-30%>",'
    ' "fundamento": "<qual item da tabela OAB embasa>",'
    ' "observacao": "<nota relevante>"}\n'
    "Use SOMENTE valores presentes nos trechos. Se não houver o item exato, use o mais "
    "próximo e diga isso no fundamento. NUNCA invente valores."
)


@router.post("/sugestao-honorarios", dependencies=[Depends(rate_limit("ia-sugestao-honorarios", 15))])
async def sugestao_honorarios(body: HonorariosIn, db: AsyncSession = Depends(get_db),
                              cu: User = Depends(get_current_user)):
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada")
    descricao_limpa, pii = sanitizar_ou_abortar(body.descricao)
    consulta = f"honorários {body.area} {descricao_limpa}"
    ctx = await buscar_contexto_rag(db, consulta, limite=6, categorias=["tabela_honorarios_oab"])
    ctx_txt = "\n\n".join(f"- {(c.get('conteudo') or '')[:600]}" for c in ctx) or "(tabela OAB não localizada na base)"
    vc = f"\nValor da causa: R$ {body.valor_causa:.2f}" if body.valor_causa else ""
    user = (f"ÁREA: {body.area}\nSERVIÇO/ATO: {descricao_limpa}{vc}\n\n"
            f"TRECHOS DA TABELA DE HONORÁRIOS OAB/MG:\n{ctx_txt}")
    try:
        # Saída JSON parseada (_pj) → mantém "analise_juridica" (fora da base
        # por design) e PREPENDE BASE_ESTRUTURADA no system — padrão das etapas
        # intermediárias do peca_service (barreira anti-alucinação compatível
        # com JSON, sem poluir o parse).
        bruto, resp = await _ia(BASE_ESTRUTURADA + "\n\n" + SYS_HONORARIOS, user, task_type="analise_juridica", temperature=0.05, max_tokens=1000, nivel="alto")
    except Exception:
        logger.exception("Falha na chamada de IA")
        raise HTTPException(502, "Falha ao processar a solicitação de IA")
    log_id = await _log(db, cu.id, AITipoUso.outro, None, user, pii, bruto, resp)
    return {
        "ai_log_id": log_id,
        "sugestao": _pj(bruto) or {"texto": bruto},
        "fonte": "Tabela de Honorários OAB/MG (referencial)",
        "trechos_consultados": len(ctx),
        "aviso": "⚠️ Valores REFERENCIAIS da OAB/MG. Honorário é livremente pactuado — "
                 "o advogado define o valor final. Confira na tabela oficial.",
    }
