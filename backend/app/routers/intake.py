# ── app/routers/intake.py ─────────────────────────────────────────────────────
# Orquestração de intake (Seção 7 do redesign — R5).
# POST /intake/casos/{case_id}/analise-completa:
#   caso + documentos (ocr_text) e/ou payload {texto|analise} →
#   1) área provável  2) teses do banco (nunca inventadas)  3) estratégia (IA,
#   pipeline LGPD)  4) honorários OAB/MG (tabela estruturada → RAG → null)
#   5) módulos sugeridos (AreaModuloMapping).
# Tudo RASCUNHO (HITL) + AILog por chamada de IA. Gate: verificar_acesso_caso.
# REGRAS (CLAUDE.md): nunca inventar tese/valor/item de tabela; nunca prometer
# resultado; nunca logar PII em texto plano (sanitizar_pii antes de IA/log).
from __future__ import annotations

import json
import logging
import re
from uuid import uuid4
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings

settings = get_settings()
from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.ai_log import AILog, AIStatusHITL, AITipoUso
from app.models.case import Case, CaseArea
from app.models.redesign import AreaModuloMapping, TabelaOABHonorario
from app.models.tese import Tese, TeseStatus
from app.models.user import User
from app.core.rate_limit import rate_limit

logger = logging.getLogger("ejc.intake")

router = APIRouter(prefix="/intake", tags=["Intake — Orquestração"])

AVISO_RASCUNHO = (
    "Sugestões geradas por IA — sujeitas a revisão do advogado responsável "
    "(OAB Prov. 205/2021)"
)
RESSALVA_OAB = (
    "Valor de referência mínimo da tabela OAB/MG — não vinculante, "
    "sujeito a negociação conforme complexidade"
)
AVISO_SEM_TABELA = "tabela OAB não disponível — cadastre em /area de administração"

_AREAS_VALIDAS = [a.value for a in CaseArea]


# ── Schemas ───────────────────────────────────────────────────────────────────

class AnaliseCompletaIn(BaseModel):
    """Payload opcional: texto bruto e/ou análise já produzida por
    documento_service.extrair_e_analisar (reuso — não reprocessar)."""
    texto:   Optional[str] = Field(None, max_length=30000)
    analise: Optional[dict] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _pode_usar_ia(cu: User) -> bool:
    """Sugestões de IA para intake: advogado+ (mesmo limiar de teses.py)."""
    return ROLE_LEVEL.get(cu.role.value, 0) >= ROLE_LEVEL["advogado"]


def _parse_json(txt: str) -> Optional[dict]:
    """Extrai o primeiro objeto JSON da resposta da IA (tolerante)."""
    if not txt:
        return None
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{.*\}", txt, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                return None
    return None


async def _log_ia(
    db: AsyncSession, user_id: str, case_id: str, tipo_uso: AITipoUso,
    resp: Any, prompt_sanitizado: str, fontes_rag: Optional[str] = None,
) -> str:
    """AILog para cada chamada de IA — mesmo padrão de ai_service (LGPD+HITL)."""
    log = AILog(
        id=str(uuid4()),
        user_id=user_id,
        case_id=case_id,
        tipo_uso=tipo_uso,
        modelo=f"{getattr(resp, 'provedor', '?')}/{getattr(resp, 'modelo', '?')}",
        prompt_sanitizado=prompt_sanitizado[:8000],
        pii_removida=True,
        resposta=(getattr(resp, "texto", None) or "")[:4000],
        fontes_rag=fontes_rag,
        tokens_input=getattr(resp, "input_tokens", None),
        tokens_output=getattr(resp, "output_tokens", None),
        status_hitl=AIStatusHITL.gerado,
    )
    db.add(log)
    await db.commit()
    return log.id


async def _texto_base(db: AsyncSession, case: Case, payload: AnaliseCompletaIn) -> str:
    """Fonte do texto: payload.texto > ocr_text dos documentos > descricao_fatos.
    Lógica extraída para motor_peca_service.texto_base_do_caso (P1 — Motor de
    Peça reutiliza a mesma fonte única; este wrapper preserva a API interna)."""
    from app.services.motor_peca_service import texto_base_do_caso
    return await texto_base_do_caso(db, case, payload.texto)


async def _identificar_area(
    db: AsyncSession, cu: User, case: Case,
    payload: AnaliseCompletaIn, texto_limpo: str,
) -> dict:
    """1) Área provável: análise existente > classificação IA > área do caso."""
    # a) Reuso da classificação de documento_service.extrair_e_analisar
    if payload.analise:
        area_analise = ((payload.analise.get("classificacao") or {}).get("area") or "").strip().lower()
        if area_analise in _AREAS_VALIDAS:
            return {"valor": area_analise, "origem": "analise_documento", "ai_log_id": None}

    # b) Classificação via ai_gateway (texto já sanitizado — LGPD)
    if texto_limpo and len(texto_limpo) >= 40 and settings.AI_ENABLED:
        from app.services.ai_gateway import chat as gw_chat
        system = (
            "Você classifica casos jurídicos brasileiros em UMA área do direito. "
            f"Escolha EXATAMENTE uma de: {', '.join(_AREAS_VALIDAS)}. "
            "É PROIBIDO inventar área fora da lista. "
            'Responda APENAS JSON: {"area": "<uma da lista>", "justificativa": "<1 frase>"}'
        )
        user_msg = f"TEXTO DO CASO (sanitizado):\n{texto_limpo[:6000]}"
        try:
            resp = await gw_chat(
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": user_msg}],
                task_type="chat_rapido", temperature=0.1, max_tokens=200,
            )
            log_id = await _log_ia(
                db, cu.id, case.id, AITipoUso.outro, resp,
                f"[intake/classificar-area caso={case.id}] " + user_msg,
            )
            dados = _parse_json(resp.texto) or {}
            area_ia = str(dados.get("area") or "").strip().lower()
            if area_ia in _AREAS_VALIDAS:
                return {"valor": area_ia, "origem": "classificacao_ia", "ai_log_id": log_id}
        except Exception as e:
            logger.warning(f"Classificação de área via IA falhou: {e}")

    # c) Fallback: área já cadastrada no caso (campo NOT NULL)
    return {"valor": case.area.value, "origem": "area_do_caso", "ai_log_id": None}


async def _buscar_teses(db: AsyncSession, area: str) -> list[dict]:
    """2) Teses pertinentes — SOMENTE o que existe no banco de teses (teses.py).
    Nunca inventa: se não houver, retorna lista vazia."""
    teses = (await db.execute(
        select(Tese).where(
            Tese.deleted_at.is_(None),
            Tese.status == TeseStatus.ativa,
            Tese.area_juridica.ilike(f"%{area}%"),
        ).order_by(Tese.taxa_sucesso.desc().nullslast()).limit(8)
    )).scalars().all()
    return [
        {
            "id": t.id,
            "titulo": t.titulo,
            "taxa_sucesso": t.taxa_sucesso,
            "area_juridica": t.area_juridica,
            "tribunal": t.tribunal,
            "vezes_usada": t.vezes_usada,
            "fonte": "banco_teses_escritorio",
        }
        for t in teses
    ]


async def _estrategia_recomendada(
    db: AsyncSession, cu: User, case: Case, area: str,
    texto_limpo: str, teses: list[dict],
) -> dict:
    """3) Estratégia via pipeline LGPD completo (padrão ai_service.analisar_caso):
    sanitizar → RAG → gateway → AILog → resposta marcada rascunho."""
    opcoes = ["defesa_administrativa", "acao_judicial", "acordo",
              "arquivamento_prescricao", "outra"]

    if not settings.AI_ENABLED:
        return {"recomendada": None, "justificativa": "IA desabilitada na configuração",
                "ai_log_id": None}
    if not texto_limpo or len(texto_limpo) < 40:
        return {"recomendada": None,
                "justificativa": "Texto insuficiente para análise (envie documentos ou 'texto')",
                "ai_log_id": None}

    from app.services.ai_gateway import chat as gw_chat
    from app.services.ai_service import buscar_contexto_rag

    fontes = []
    try:
        fontes = await buscar_contexto_rag(db, f"{area} {texto_limpo[:400]}", limite=5, modo_or=True)
    except Exception as e:
        logger.warning(f"RAG indisponível na estratégia: {e}")

    ctx = ""
    if fontes:
        linhas = [f"- {f.get('titulo')}: {(f.get('conteudo') or '')[:220]}" for f in fontes]
        ctx = "[BASE DE CONHECIMENTO]\n" + "\n".join(linhas) + "\n\n"
    teses_txt = ""
    if teses:
        teses_txt = "[TESES DO ESCRITÓRIO NA ÁREA]\n" + "\n".join(
            f"- {t['titulo']} (sucesso: {t['taxa_sucesso'] if t['taxa_sucesso'] is not None else 'N/A'})"
            for t in teses
        ) + "\n\n"

    system = (
        "Você é consultor jurídico estratégico brasileiro. Recomende UMA estratégia "
        f"dentre: {', '.join(opcoes)}. Baseie-se APENAS nos fatos e no contexto "
        "fornecidos — é PROIBIDO inventar lei, súmula ou julgado. NUNCA prometa "
        "resultado. Toda saída é RASCUNHO sujeito a revisão do advogado (OAB). "
        'Responda APENAS JSON: {"estrategia": "<uma das opções>", '
        '"justificativa": "<3-5 frases objetivas, sem promessa de êxito>", '
        '"riscos": ["<risco 1>", "<risco 2>"]}'
    )
    user_msg = f"ÁREA: {area}\n\n{teses_txt}{ctx}FATOS (sanitizados):\n{texto_limpo[:6000]}"

    try:
        resp = await gw_chat(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user_msg}],
            task_type="estrategia", temperature=0.2, max_tokens=900,
        )
    except Exception as e:
        return {"recomendada": None,
                "justificativa": f"IA indisponível: {str(e)[:200]}", "ai_log_id": None}

    log_id = await _log_ia(
        db, cu.id, case.id, AITipoUso.analise_caso, resp,
        f"[intake/estrategia caso={case.id}] " + user_msg,
        fontes_rag="; ".join(str(f.get("chunk_id")) for f in fontes) or None,
    )

    dados = _parse_json(resp.texto) or {}
    estrategia = str(dados.get("estrategia") or "").strip().lower()
    if estrategia not in opcoes:
        # Guarda-corpo: nunca propagar valor fora do vocabulário controlado
        estrategia = "outra"
    return {
        "recomendada": estrategia,
        "justificativa": str(dados.get("justificativa") or resp.texto or "")[:1500],
        "riscos": dados.get("riscos") if isinstance(dados.get("riscos"), list) else [],
        "fontes_rag_usadas": len(fontes),
        "modelo": f"{resp.provedor}/{resp.modelo}",
        "ai_log_id": log_id,
    }


async def _honorarios_referencia(
    db: AsyncSession, cu: User, case: Case, area: str, payload: AnaliseCompletaIn,
) -> tuple[Optional[dict], str]:
    """4) Honorários OAB/MG: tabela estruturada → RAG existente → null.
    NUNCA inventa valor. Retorna (honorarios | None, aviso)."""
    # a) Tabela estruturada (TabelaOABHonorario) — fonte primária
    itens = (await db.execute(
        select(TabelaOABHonorario).where(
            TabelaOABHonorario.ativo.is_(True),
            TabelaOABHonorario.area_juridica.ilike(f"%{area}%"),
        ).order_by(TabelaOABHonorario.vigencia_inicio.desc(),
                   TabelaOABHonorario.item_codigo).limit(10)
    )).scalars().all()
    if itens:
        return {
            "origem": "tabela_oab_estruturada",
            "itens": [
                {
                    "item_codigo": i.item_codigo,
                    "descricao": i.descricao,
                    "valor_minimo": float(i.valor_minimo) if i.valor_minimo is not None else None,
                    "percentual": float(i.percentual) if i.percentual is not None else None,
                    "unidade": i.unidade,
                    "vigencia_inicio": i.vigencia_inicio.isoformat() if i.vigencia_inicio else None,
                    "vigencia_fim": i.vigencia_fim.isoformat() if i.vigencia_fim else None,
                    "fonte": i.fonte,
                    "observacoes": i.observacoes,
                }
                for i in itens
            ],
        }, RESSALVA_OAB

    # b) Fluxo existente via RAG (documento_service._sugerir_honorarios)
    if settings.AI_ENABLED:
        try:
            from app.services.documento_service import _sugerir_honorarios
            materia = ""
            valor_causa = float(case.valor_causa) if case.valor_causa is not None else None
            if payload.analise:
                materia = ((payload.analise.get("classificacao") or {}).get("materia") or "")
                valor_causa = payload.analise.get("valor_causa_estimado") or valor_causa
            dados = await _sugerir_honorarios(db, {
                "classificacao": {"area": area, "materia": materia},
                "valor_causa_estimado": valor_causa,
            })
            # AILog da chamada de IA feita dentro de _sugerir_honorarios
            # (tokens indisponíveis — o serviço não os expõe; resposta rastreada)
            log = AILog(
                id=str(uuid4()), user_id=cu.id, case_id=case.id,
                tipo_uso=AITipoUso.outro,
                modelo="ai_gateway/analise_juridica",
                prompt_sanitizado=(
                    f"[intake/honorarios-rag caso={case.id}] área={area} "
                    f"matéria={materia or '-'} valor_causa={valor_causa or '-'}"
                )[:8000],
                pii_removida=True,
                resposta=json.dumps(dados, ensure_ascii=False, default=str)[:4000],
                status_hitl=AIStatusHITL.gerado,
            )
            db.add(log)
            await db.commit()

            if dados and dados.get("tabela_oficial_disponivel"):
                dados["origem"] = "rag_tabela_oab"
                dados["ai_log_id"] = log.id
                return dados, RESSALVA_OAB
        except Exception as e:
            logger.warning(f"Fallback RAG de honorários falhou: {e}")

    # c) Nenhuma fonte confiável — NUNCA inventar valor
    return None, AVISO_SEM_TABELA


async def _modulos_sugeridos(db: AsyncSession, area: str) -> list[dict]:
    """6) Matriz área → módulos/ferramentas (AreaModuloMapping — já existente)."""
    rows = (await db.execute(
        select(AreaModuloMapping).where(
            AreaModuloMapping.area_juridica == area.strip().lower(),
            AreaModuloMapping.habilitado.is_(True),
        ).order_by(AreaModuloMapping.ordem, AreaModuloMapping.module_key)
    )).scalars().all()
    return [
        {
            "module_key": m.module_key,
            "ordem": m.ordem,
            "ferramentas": m.ferramentas or [],
            "workflow_template_id": m.workflow_template_id,
            "checklist_template_id": m.checklist_template_id,
        }
        for m in rows
    ]


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/casos/{case_id}/analise-completa", dependencies=[Depends(rate_limit("intake-analise-completa", 10))])
async def analise_completa(
    case_id: str,
    payload: AnaliseCompletaIn | None = None,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Orquestra a análise completa de intake de um caso:
    área provável → teses do banco → estratégia (IA) → honorários OAB/MG →
    módulos sugeridos. Resposta inteira é RASCUNHO (HITL obrigatório).
    """
    if not _pode_usar_ia(cu):
        raise HTTPException(403, "Sugestões de IA restritas a advogados")

    # Gate canônico de ownership (RBAC + ABAC) — 404/403 conforme o caso
    case = await verificar_acesso_caso(db, cu, case_id)
    payload = payload or AnaliseCompletaIn()

    # Fonte de texto + sanitização LGPD (obrigatória antes de QUALQUER IA/log)
    from app.services.sanitizer import sanitizar_pii
    texto_bruto = await _texto_base(db, case, payload)
    texto_limpo, houve_pii = sanitizar_pii(texto_bruto[:18000], [])

    # 1) Área provável
    area_info = await _identificar_area(db, cu, case, payload, texto_limpo)
    area = area_info["valor"]

    # 2) Teses do banco (nunca inventadas)
    teses = await _buscar_teses(db, area)

    # 3) Estratégia recomendada (pipeline LGPD completo)
    estrategia = await _estrategia_recomendada(
        db, cu, case, area, texto_limpo, teses)

    # 4) Honorários de referência OAB/MG
    honorarios, honorarios_aviso = await _honorarios_referencia(db, cu, case, area, payload)

    # 6) Módulos sugeridos (matriz área → módulos)
    modulos = await _modulos_sugeridos(db, area)

    ai_logs = [x for x in (area_info.get("ai_log_id"),
                           estrategia.get("ai_log_id"),
                           (honorarios or {}).get("ai_log_id")) if x]

    # 5) Envelope — tudo rascunho
    return {
        "status": "rascunho",
        "aviso": AVISO_RASCUNHO,
        "case_id": case.id,
        "area": {"valor": area, "origem": area_info["origem"]},
        "teses": teses,
        "teses_aviso": (None if teses else
                        "Nenhuma tese cadastrada no banco para esta área — "
                        "nada foi inventado (cadastre em /teses)"),
        "estrategia": estrategia,
        "honorarios": honorarios,
        "honorarios_aviso": honorarios_aviso,
        "modulos_sugeridos": modulos,
        "pii_removida": houve_pii,
        "ai_log_ids": ai_logs,
    }
