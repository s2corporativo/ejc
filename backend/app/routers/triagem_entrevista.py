# ── app/routers/triagem_entrevista.py ────────────────────────────────────────
# Entrevista Inteligente (Jornada do Caso — etapa 2 / Triagem).
# POST /triagem/entrevista: o advogado descreve o ocorrido em texto livre e a
# IA devolve um painel estruturado de triagem preliminar (área, competência,
# possível ação, urgência, tutela, prescrição, valor da causa, pedidos, riscos,
# chance de êxito) — cada item com confiança 0-100.
#
# PADRÕES SEGUIDOS (mesmo pipeline de intake.py / ai_guard.py):
#   sanitizar_ou_abortar (LGPD) → ai_gateway.chat(task_type="triagem") →
#   parse JSON defensivo com fallback → registrar_ai_log (AILog obrigatório).
# Tudo é ESTIMATIVA PRELIMINAR / RASCUNHO (HITL) — nunca parecer definitivo,
# nunca promessa de resultado (OAB Prov. 205/2021; estimativa interna de
# triagem, mesmo padrão do veredito_ia/case_intel).
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.ownership import verificar_acesso_caso
from app.core.rate_limit import rate_limit
from app.core.security import get_current_user, ROLE_LEVEL
from app.models.ai_log import AITipoUso
from app.models.user import User

settings = get_settings()
logger = logging.getLogger("ejc.triagem.entrevista")

router = APIRouter(prefix="/triagem", tags=["Triagem — Entrevista Inteligente"])

AVISO_ESTIMATIVA = (
    "Estimativa preliminar gerada por IA a partir do relato — NÃO é parecer "
    "jurídico. Sujeita a revisão obrigatória do advogado responsável "
    "(OAB Prov. 205/2021)."
)

# Campos do painel: cada um vira {"valor"/..., "confianca": 0-100} na resposta.
_SYSTEM_PROMPT = """Você é assistente interno de TRIAGEM de um escritório de advocacia brasileiro (uso exclusivo por advogados — nunca resposta a cliente).
Receberá o relato livre de um ocorrido (já sanitizado de PII) e fará triagem técnica PRELIMINAR.

REGRAS:
- Baseie-se APENAS no relato. É PROIBIDO inventar lei, súmula, julgado ou fato.
- Os percentuais são estimativas técnicas internas de triagem, para priorização pelo advogado — nunca promessa de resultado a cliente.
- Se o relato não permitir avaliar um item, use valor null e confianca baixa (<40).
- Áreas válidas: civil, trabalhista, consumidor, familia, ambiental, criminal, previdenciario.

Responda APENAS com JSON estrito (sem markdown, sem texto fora do JSON), neste formato:
{
  "area_direito": {"valor": "<uma das áreas válidas>", "confianca": 0-100},
  "competencia": {"valor": "<ex.: JEC, Justiça Comum Estadual, Justiça do Trabalho, Justiça Federal>", "confianca": 0-100},
  "possivel_acao": {"valor": "<nome técnico da ação cabível>", "confianca": 0-100},
  "urgencia": {"valor": true|false, "justificativa": "<1 frase>", "confianca": 0-100},
  "tutela_liminar": {"valor": true|false, "justificativa": "<1 frase>", "confianca": 0-100},
  "prescricao": {"dentro_prazo": true|false|null, "alerta": "<prazo legal + base legal, ou o que falta para avaliar>", "confianca": 0-100},
  "valor_causa": {"valor": <número em reais ou null>, "faixa": "<ex.: R$ 5.000 a R$ 15.000>", "confianca": 0-100},
  "pedidos_possiveis": ["<pedido 1>", "<pedido 2>"],
  "riscos": ["<risco 1>", "<risco 2>"],
  "chance_exito": {"percentual": 0-100, "justificativa": "<1 frase>", "confianca": 0-100}
}"""


# ── Schemas ───────────────────────────────────────────────────────────────────

class EntrevistaIn(BaseModel):
    relato: str = Field(..., min_length=40, max_length=15000,
                        description="Relato livre do ocorrido ('Conte o ocorrido')")
    case_id: Optional[str] = Field(None, max_length=36)


# ── Helpers (parse defensivo) ─────────────────────────────────────────────────

def _parse_json(txt: str) -> Optional[dict]:
    """Extrai o primeiro objeto JSON da resposta da IA (mesmo padrão de intake.py)."""
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


def _conf(v: Any) -> Optional[int]:
    """Confiança 0-100 ou None — nunca propaga lixo da IA."""
    try:
        return max(0, min(100, int(float(v))))
    except (TypeError, ValueError):
        return None


def _item(bruto: Any, campos_extras: tuple[str, ...] = ()) -> dict:
    """Normaliza um item {valor, confianca, ...extras} com fallback nulo."""
    d = bruto if isinstance(bruto, dict) else {}
    out: dict[str, Any] = {"valor": d.get("valor"), "confianca": _conf(d.get("confianca"))}
    for c in campos_extras:
        v = d.get(c)
        out[c] = str(v)[:600] if isinstance(v, str) else v
    return out


def _lista_str(bruto: Any, limite: int = 10) -> list[str]:
    if not isinstance(bruto, list):
        return []
    return [str(x)[:400] for x in bruto if isinstance(x, (str, int, float))][:limite]


def _normalizar(dados: Optional[dict]) -> dict:
    """Painel sempre com TODOS os campos — itens ausentes viram null (fallback)."""
    d = dados or {}
    prescricao = d.get("prescricao") if isinstance(d.get("prescricao"), dict) else {}
    exito = d.get("chance_exito") if isinstance(d.get("chance_exito"), dict) else {}
    return {
        "area_direito": _item(d.get("area_direito")),
        "competencia": _item(d.get("competencia")),
        "possivel_acao": _item(d.get("possivel_acao")),
        "urgencia": _item(d.get("urgencia"), ("justificativa",)),
        "tutela_liminar": _item(d.get("tutela_liminar"), ("justificativa",)),
        "prescricao": {
            "dentro_prazo": prescricao.get("dentro_prazo")
            if isinstance(prescricao.get("dentro_prazo"), bool) else None,
            "alerta": (str(prescricao.get("alerta"))[:600]
                       if prescricao.get("alerta") is not None else None),
            "confianca": _conf(prescricao.get("confianca")),
        },
        "valor_causa": _item(d.get("valor_causa"), ("faixa",)),
        "pedidos_possiveis": _lista_str(d.get("pedidos_possiveis")),
        "riscos": _lista_str(d.get("riscos")),
        "chance_exito": {
            "percentual": _conf(exito.get("percentual")),
            "justificativa": (str(exito.get("justificativa"))[:600]
                              if exito.get("justificativa") is not None else None),
            "confianca": _conf(exito.get("confianca")),
        },
    }


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post("/entrevista",
             dependencies=[Depends(rate_limit("triagem-entrevista", 10))])
async def entrevista_inteligente(
    payload: EntrevistaIn,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    """
    Entrevista Inteligente: relato livre → painel de triagem preliminar com
    confiança por item. Toda a resposta é RASCUNHO (HITL obrigatório).
    """
    # Mesmo limiar de intake.py: sugestões de IA restritas a advogado+
    if ROLE_LEVEL.get(cu.role.value, 0) < ROLE_LEVEL["advogado"]:
        raise HTTPException(403, "Sugestões de IA restritas a advogados")
    if not settings.AI_ENABLED:
        raise HTTPException(503, "IA desabilitada na configuração")

    # Gate canônico de ownership quando a entrevista está vinculada a um caso
    case = None
    if payload.case_id:
        case = await verificar_acesso_caso(db, cu, payload.case_id)

    # Barreira LGPD de entrada (padrão ai_guard) — sanitiza e segue
    from app.services.ai_guard import registrar_ai_log, sanitizar_ou_abortar
    relato_limpo, houve_pii = sanitizar_ou_abortar(payload.relato.strip())

    from app.services.ai_gateway import chat as gw_chat
    user_msg = f"RELATO DO OCORRIDO (sanitizado):\n{relato_limpo[:12000]}"
    # Com caso conhecido, os nomes das partes ganham pseudonimização REVERSÍVEL
    # no gateway (mesmo padrão de provas.sugerir-faltantes) — sem isso, nomes
    # digitados no relato iam em claro ao provedor externo.
    entidades = None
    if case is not None:
        from app.services.ai.entidades_caso import entidades_do_caso
        entidades = await entidades_do_caso(db, case.id) or None
    try:
        resp = await gw_chat(
            messages=[{"role": "system", "content": _SYSTEM_PROMPT},
                      {"role": "user", "content": user_msg}],
            task_type="triagem", temperature=0.1, max_tokens=1200,
            entidades=entidades,
        )
    except Exception as e:
        # Detalhe do provider só no log — mensagem ao usuário é genérica.
        logger.warning(f"Entrevista inteligente: gateway indisponível: {e}")
        raise HTTPException(503, "IA indisponível no momento. Tente novamente.")

    # AILog obrigatório — erro de auditoria propaga (padrão ai_guard)
    ai_log_id = await registrar_ai_log(
        db,
        user_id=cu.id,
        tipo_uso=AITipoUso.analise_caso,
        case_id=case.id if case else None,
        prompt_sanitizado=f"[triagem/entrevista caso={case.id if case else '-'}] " + user_msg,
        pii_removida=houve_pii,
        resposta=(resp.texto or "")[:4000],
        modelo=f"{resp.provedor}/{resp.modelo}",
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
    )

    dados = _parse_json(resp.texto)
    analise = _normalizar(dados)

    # Ponte Entrevista → Ficha de Triagem: o painel alimenta a ficha do caso
    # como RASCUNHO (HITL preservado), preenchendo APENAS campos ainda vazios
    # e jamais tocando ficha já CONFIRMADA. Fail-soft: falha aqui não derruba
    # a resposta da entrevista.
    ficha_atualizada = False
    if case is not None and dados is not None:
        try:
            ficha_atualizada = await _alimentar_ficha(db, case.id, analise, cu)
        except Exception as e:
            logger.warning(f"Entrevista→Ficha: falha ao alimentar rascunho: {e}")

    return {
        "status": "rascunho",
        "aviso": AVISO_ESTIMATIVA,
        "case_id": case.id if case else None,
        "analise": analise,
        "parse_ok": dados is not None,
        "ficha_atualizada": ficha_atualizada,
        "pii_removida": houve_pii,
        "modelo": f"{resp.provedor}/{resp.modelo}",
        "ai_log_id": ai_log_id,
    }


async def _alimentar_ficha(db: AsyncSession, case_id: str,
                           analise: dict, cu: User) -> bool:
    """Grava o painel na ficha do caso (rascunho). Regras:
    • ficha CONFIRMADA nunca é tocada (o gate da peça é do advogado);
    • em ficha existente, só campos VAZIOS são preenchidos (não sobrescreve
      trabalho humano); a confiança nova é MESCLADA à existente."""
    from app.services import ficha_triagem_service as fts

    ficha = await fts.obter(db, case_id)
    if ficha is not None and ficha.status == "confirmada":
        return False

    campos = fts.dados_do_painel_entrevista(analise)
    conf = campos.pop("confianca", {})
    if ficha is not None:
        campos = {
            k: v for k, v in campos.items()
            if getattr(ficha, k, None) in (None, "")
        }
        conf = {k: v for k, v in conf.items() if k in campos}
        conf = {**(ficha.confianca or {}), **conf}
    if not campos:
        return False
    if conf:
        campos["confianca"] = conf
    await fts.salvar(db, case_id, campos, confirmar=False,
                     user_id=cu.id, user_role=cu.role.value)
    return True
