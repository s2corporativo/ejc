# ── app/services/triagem_entrevista_service.py ───────────────────────────────
# Núcleo compartilhado da Entrevista Inteligente (triagem por relato livre).
#
# Extraído de routers/triagem_entrevista.py (Bloco 3 — Entrada Única) para ser
# reutilizado por routers/entrada.py SEM duplicar o pipeline obrigatório:
#   sanitizar_ou_abortar (LGPD) → ai_gateway.chat(task_type="triagem") →
#   registrar_ai_log (AILog obrigatório / HITL).
# Toda saída é ESTIMATIVA PRELIMINAR / RASCUNHO — nunca parecer definitivo
# (OAB Prov. 205/2021). O router antigo continua com o MESMO comportamento:
# ele apenas delega para cá.
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai_log import AITipoUso
from app.models.user import User

logger = logging.getLogger("ejc.triagem.entrevista")

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


class TriagemIndisponivelError(RuntimeError):
    """Gateway de IA indisponível para a triagem — o chamador decide o desfecho
    (router da entrevista → 503; Entrada Única → resposta degradada)."""


# ── Helpers de parse defensivo (mesmo padrão de intake.py) ────────────────────

def _parse_json(txt: str) -> Optional[dict]:
    """Extrai o primeiro objeto JSON da resposta da IA."""
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


def normalizar_painel(dados: Optional[dict]) -> dict:
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


async def analisar_relato(
    db: AsyncSession,
    cu: User,
    relato: str,
    *,
    case_id: str | None = None,
    entidades: dict | None = None,
) -> dict[str, Any]:
    """Relato livre → painel de triagem preliminar (RASCUNHO, HITL obrigatório).

    Pipeline inegociável: sanitização LGPD → gateway (task_type="triagem") →
    AILog. Exceções:
      • sanitizar_ou_abortar pode abortar (HTTPException) — propaga como está;
      • gateway indisponível → TriagemIndisponivelError (o chamador decide);
      • falha do AILog propaga (auditoria é obrigatória — padrão ai_guard).
    """
    # Barreira LGPD de entrada (padrão ai_guard) — sanitiza e segue
    from app.services.ai_guard import registrar_ai_log, sanitizar_ou_abortar
    relato_limpo, houve_pii = sanitizar_ou_abortar(relato.strip())

    from app.services.ai_gateway import chat as gw_chat
    user_msg = f"RELATO DO OCORRIDO (sanitizado):\n{relato_limpo[:12000]}"
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
        raise TriagemIndisponivelError(str(e)[:300]) from e

    # AILog obrigatório — erro de auditoria propaga (padrão ai_guard)
    ai_log_id = await registrar_ai_log(
        db,
        user_id=cu.id,
        tipo_uso=AITipoUso.analise_caso,
        case_id=case_id,
        prompt_sanitizado=f"[triagem/entrevista caso={case_id or '-'}] " + user_msg,
        pii_removida=houve_pii,
        resposta=(resp.texto or "")[:4000],
        modelo=f"{resp.provedor}/{resp.modelo}",
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
    )

    dados = _parse_json(resp.texto)
    return {
        "analise": normalizar_painel(dados),
        "dados": dados,
        "parse_ok": dados is not None,
        "pii_removida": houve_pii,
        "modelo": f"{resp.provedor}/{resp.modelo}",
        "ai_log_id": ai_log_id,
    }
