# ── app/services/visual_law.py ─────────────────────────────────────────────────
# Visual Law — geração de diagramas Mermaid.js a partir do dossiê do caso.
# A IA produz o código Mermaid; o frontend renderiza (biblioteca mermaid.js).
# Todo output é RASCUNHO (HITL obrigatório).
from __future__ import annotations
import logging
from typing import Literal

from app.services.visual_law_theme import OURO, OURO_CLARO, OURO_PALHA, OURO_PROFUNDO

logger = logging.getLogger(__name__)

DiagramaTipo = Literal["timeline", "fluxo_status", "partes", "prazos"]

# Diretiva de init do Mermaid com o tema dourado central — prefixada de forma
# DETERMINÍSTICA no código gerado (a IA não escolhe as cores do escritório).
_MERMAID_INIT_TEMA = (
    "%%{init: {'theme': 'base', 'themeVariables': {"
    f"'primaryColor': '{OURO_PALHA}', 'primaryBorderColor': '{OURO}', "
    "'primaryTextColor': '#111827', "
    f"'lineColor': '{OURO}', 'titleColor': '{OURO_PROFUNDO}', "
    f"'cScale0': '{OURO_PROFUNDO}', 'cScale1': '{OURO}', 'cScale2': '{OURO_CLARO}'"
    "}}}%%"
)


def aplicar_tema_dourado(codigo: str) -> str:
    """Prefixa o diagrama Mermaid com o init do tema dourado (idempotente)."""
    codigo = (codigo or "").strip()
    if not codigo or codigo.startswith("%%{init"):
        return codigo
    return f"{_MERMAID_INIT_TEMA}\n{codigo}"

SYSTEM_VISUAL_LAW = """Você é especialista em Visual Law e gera EXCLUSIVAMENTE código Mermaid.js.
Regras absolutas:
1. Responda APENAS com o bloco de código Mermaid — sem explicações, sem markdown extra.
2. Não invente datas, partes ou fatos. Use SOMENTE o que está no dossiê fornecido.
3. O código deve ser válido e renderizável pelo mermaid.js v10+.
4. Substitua nomes de pessoas por iniciais ou "[PARTE A]" / "[PARTE B]" (LGPD).
5. Use português do Brasil em todos os rótulos."""

_INSTRUCOES: dict[DiagramaTipo, str] = {
    "timeline": (
        "Gere um diagrama TIMELINE do Mermaid.js com as movimentações processuais do caso. "
        "Use o tipo 'timeline'. Inclua datas e eventos principais em ordem cronológica. "
        "Exemplo de sintaxe:\n"
        "timeline\n"
        "    title Linha do Tempo Processual\n"
        "    section 2024\n"
        "        Distribuição : 15 Jan\n"
        "        Citação : 20 Fev"
    ),
    "fluxo_status": (
        "Gere um flowchart LR do Mermaid.js mostrando o fluxo de status do processo "
        "desde a distribuição até o estado atual, com os próximos passos prováveis. "
        "Use formas diferentes: retângulo para concluído, losango para decisão, "
        "hexágono para o estado atual. Limite a 12 nós."
    ),
    "partes": (
        "Gere um graph LR do Mermaid.js mostrando as partes do processo e suas relações "
        "(autor, réu, advogados, magistrado, MP se houver). "
        "Use classes CSS para diferenciar: autor (verde), réu (vermelho), "
        "advogado (azul), juiz (roxo). Substitua nomes por iniciais ou cargos."
    ),
    "prazos": (
        "Gere um gantt chart do Mermaid.js com os prazos processuais do caso. "
        "Seções por tipo: Prazos Vencidos, Prazos Ativos, Prazos Futuros. "
        "Use dateFormat YYYY-MM-DD. Inclua apenas os prazos do dossiê fornecido."
    ),
}


async def gerar_diagrama(
    dossie_txt: str,
    tipo: DiagramaTipo = "timeline",
    model_override: str | None = None,
) -> dict:
    """
    Recebe o texto do dossiê (já sanitizado LGPD) e gera código Mermaid.js.
    Retorna: { tipo, mermaid_code, modelo, provedor, fallback }
    """
    from app.services.ai_gateway import chat as gw_chat

    instrucao = _INSTRUCOES.get(tipo, _INSTRUCOES["timeline"])
    user_msg = f"{instrucao}\n\n[DOSSIÊ DO CASO]\n{dossie_txt[:6000]}"

    resp = await gw_chat(
        messages=[
            {"role": "system", "content": SYSTEM_VISUAL_LAW},
            {"role": "user",   "content": user_msg},
        ],
        task_type="resumo",
        temperature=0.1,   # determinístico — diagrama deve ser consistente
        max_tokens=1500,
        model_override=model_override,
    )

    # Remove eventuais fences de markdown do output
    codigo = resp.texto.strip()
    for prefix in ("```mermaid", "```"):
        if codigo.startswith(prefix):
            codigo = codigo[len(prefix):]
    if codigo.endswith("```"):
        codigo = codigo[:-3]
    codigo = aplicar_tema_dourado(codigo.strip())

    return {
        "tipo":         tipo,
        "mermaid_code": codigo,
        "modelo":       resp.modelo,
        "provedor":     resp.provedor,
        "fallback":     resp.fallback_ativado,
        "aviso":        "⚠️ RASCUNHO — verifique os dados antes de usar o diagrama.",
    }
