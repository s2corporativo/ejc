"""Especialização empresarial do Núcleo Único de IA do EJC.

Não executa modelo, não cria gateway e não persiste chain-of-thought. Apenas
formaliza o contrato de saída do DPT 360 para o SingleAICoreOrchestrator.
"""
from __future__ import annotations

import json
import re
from typing import Any

DPT_ACTIONS = {"conselho", "preflight", "diagnostico"}

_JSON_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def build_dpt_instruction(
    *,
    action: str,
    company_context: dict[str, Any],
    question: str,
    area: str | None = None,
) -> str:
    if action not in DPT_ACTIONS:
        raise ValueError(f"Ação DPT não suportada: {action}")

    focus = area or "empresarial multidisciplinar"
    context = json.dumps(company_context, ensure_ascii=False, sort_keys=True)

    return f"""
Você está operando dentro do DPT Empresarial 360, usando o Núcleo Único de IA do EJC.
A tarefa é {action!r}; foco jurídico: {focus!r}.

REGRAS INEGOCIÁVEIS:
- produza somente produto jurídico estruturado; NÃO exponha raciocínio interno, cadeia de pensamento ou notas privadas;
- diferencie fato comprovado, fato narrado, inferência, contradição e desconhecido;
- todo fato relevante deve indicar a evidência disponível ou declarar que falta evidência;
- não trate ausência de registro como regularidade;
- não invente legislação, precedente, fonte, prazo, documento, obrigação ou irregularidade;
- norma/jurisprudência sem fonte verificável deve virar lacuna/alerta, não fundamento afirmativo;
- apresente argumentos contrários e fragilidades;
- nenhuma conclusão é definitiva: saída é rascunho para revisão humana;
- não recomende comunicação automática, abertura automática de caso ou alteração automática de cadastro.

PROTOCOLO JURÍDICO A COBRIR NO PRODUTO:
A) identificação: área, subárea, natureza, órgão, competência, rito, prazo e urgência quando identificáveis;
B) fatos classificados;
C) evidências ligadas aos fatos;
D) questões jurídicas;
E) fontes pesquisadas/necessárias;
F) tese principal, teses subsidiárias, argumentos contrários e fragilidades;
G) objeções/crítica adversarial do conteúdo;
H) conclusão preliminar, risco, lacunas e providências;
I) pontos que exigem decisão/revisão humana.

Responda APENAS em JSON válido com estas chaves:
{{
  "identificacao": {{"area": "", "subarea": "", "natureza": "", "orgao": "", "competencia": "", "rito": "", "prazo": "", "urgencia": ""}},
  "fatos": [{{"texto": "", "status": "comprovado|narrado|inferido|contraditorio|desconhecido", "evidencia": ""}}],
  "questoes": [""],
  "fontes": [{{"titulo": "", "referencia": "", "status": "confirmada|a_confirmar"}}],
  "teses": {{"principal": "", "subsidiarias": [""], "argumentos_contrarios": [""], "fragilidades": [""]}},
  "objecoes": [""],
  "riscos": [{{"nivel": "critico|alto|medio|baixo|nao_avaliado", "descricao": "", "base": ""}}],
  "conclusao": "",
  "providencias": [""],
  "lacunas": [""],
  "revisao_humana": [""]
}}

CONTEXTO EMPRESARIAL MINIMIZADO (projeção factual do Legal Twin):
{context}

PERGUNTA / MATERIAL SUBMETIDO PELO ADVOGADO:
{question.strip()}
""".strip()


def parse_structured_content(content: str) -> dict[str, Any] | None:
    """Parse conservador: falha vira alerta HITL; nunca 'conserta' JSON jurídico."""
    raw = (content or "").strip()
    if not raw:
        return None
    raw = _JSON_FENCE.sub("", raw).strip()
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None
