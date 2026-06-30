"""
Análise estratégica de casos jurídicos com IA.
Atua como advogado sênior com 20 anos de experiência.
"""
import json
import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

PROMPT_ANALISE = """Você é um advogado sênior brasileiro com 20 anos de experiência em todas as áreas do direito, especializado em estratégia processual e análise de risco jurídico. Você domina a jurisprudência do STJ, STF, TST, TRTs e dos tribunais estaduais.

Analise o caso jurídico abaixo com profundidade e precisão. Retorne APENAS um objeto JSON válido, sem texto antes ou depois, sem markdown, sem cercas de código.

CASO:
{contexto}

Retorne este JSON exato (preencha com conteúdo real, não deixe campos vazios):
{{
  "partes": [
    {{"nome": "nome da parte", "polo": "ativo|passivo|neutro|interveniente", "tipo": "PF|PJ|Ente Público", "qualificacao": "breve qualificação relevante"}}
  ],
  "ramo": "ramo principal do direito (ex: Direito Trabalhista)",
  "subramo": "especialidade (ex: Vínculo empregatício / Horas extras)",
  "sumario_fatos": "resumo objetivo dos fatos em 3-5 linhas",
  "pontos_fortes": ["ponto forte 1", "ponto forte 2", "ponto forte 3"],
  "pontos_fracos": ["ponto fraco 1", "ponto fraco 2"],
  "estrategia": {{
    "cenario_agressivo": {{
      "descricao": "descrição da estratégia agressiva",
      "vantagem": "vantagem principal",
      "risco": "risco principal",
      "acoes": ["ação 1", "ação 2"]
    }},
    "cenario_moderado": {{
      "descricao": "descrição da estratégia moderada",
      "vantagem": "vantagem principal",
      "risco": "risco principal",
      "acoes": ["ação 1", "ação 2"]
    }},
    "cenario_defensivo": {{
      "descricao": "descrição da estratégia defensiva",
      "vantagem": "vantagem principal",
      "risco": "risco principal",
      "acoes": ["ação 1", "ação 2"]
    }},
    "recomendacao": "agressivo|moderado|defensivo",
    "justificativa_recomendacao": "por que este cenário é o recomendado"
  }},
  "teses_campeas": [
    {{
      "titulo": "nome da tese",
      "fundamento_legal": "artigo/lei/súmula base",
      "jurisprudencia": "precedente STJ/STF/TST relevante",
      "aplicabilidade": "como se aplica ao caso concreto",
      "forca": "alta|media|baixa"
    }}
  ],
  "riscos": [
    {{
      "descricao": "descrição do risco",
      "probabilidade": "alta|media|baixa",
      "impacto": "alto|medio|baixo",
      "mitigacao": "como mitigar este risco"
    }}
  ],
  "jurimetria": {{
    "chance_sucesso_percent": 70,
    "tempo_estimado_meses": 18,
    "faixa_valor_min": 15000,
    "faixa_valor_max": 45000,
    "base_estimativa": "base da estimativa (tribunal, tipo de caso, histórico)",
    "observacao": "observação relevante sobre a estimativa"
  }},
  "proximos_passos": [
    {{"prazo": "imediato|7 dias|30 dias|60 dias", "acao": "descrição da ação", "prioridade": "alta|media|baixa"}}
  ],
  "alertas": ["alerta importante 1", "alerta importante 2"],
  "observacoes_finais": "observações finais do advogado sênior"
}}"""


def _parse_json_robusto(text: str) -> dict:
    """Extrai JSON mesmo que a IA retorne texto ao redor."""
    text = text.strip()
    # remover markdown code blocks
    text = re.sub(r"```(?:json)?", "", text).strip()
    # encontrar primeiro { e último }
    start = text.find("{")
    end = text.rfind("}") + 1
    if start == -1 or end == 0:
        return {}
    try:
        return json.loads(text[start:end])
    except Exception:
        return {}


async def analisar_caso(
    *,
    titulo: str = "",
    objeto: str = "",
    fatos: str = "",
    texto_documento: str = "",
    partes_existentes: str = "",
    numero_processo: str = "",
    area: str = "",
    nomes_proteger: list[str] | None = None,
    db=None,
) -> dict:
    """
    Análise estratégica completa do caso.
    Combina dados do caso + texto extraído de documento (opcional).
    Usa ai_gateway.chat com task_type='estrategia'.
    Se `db` for fornecido, ancora a análise na base RAG (anti-alucinação).
    """
    from app.services.ai_gateway import chat
    from app.services.sanitizer import sanitizar_pii, validar_sem_pii

    # Montar contexto
    partes_ctx = []
    if titulo:
        partes_ctx.append(f"TÍTULO: {titulo}")
    if numero_processo:
        partes_ctx.append(f"NÚMERO DO PROCESSO: {numero_processo}")
    if area:
        partes_ctx.append(f"ÁREA JURÍDICA INFORMADA: {area}")
    if partes_existentes:
        partes_ctx.append(f"PARTES JÁ CADASTRADAS: {partes_existentes}")
    if objeto:
        partes_ctx.append(f"OBJETO DA AÇÃO: {objeto}")
    if fatos:
        partes_ctx.append(f"FATOS:\n{fatos}")
    if texto_documento:
        # Limitar a 4000 chars para não estourar contexto
        trecho = texto_documento[:4000]
        partes_ctx.append(f"TEXTO EXTRAÍDO DO DOCUMENTO:\n{trecho}")

    if not partes_ctx:
        return {"erro": "Dados insuficientes para análise"}

    contexto = "\n\n".join(partes_ctx)

    # Grounding RAG (P0): ancora a análise na base interna — evita inventar
    # jurisprudência (regra absoluta). Fail-safe: indisponível → segue sem.
    _fontes_rag: list = []
    if db is not None:
        try:
            from app.services.ai_service import buscar_contexto_rag
            _q = " ".join(x for x in [area, titulo, (fatos or objeto or texto_documento or "")[:300]] if x)
            _chunks = await buscar_contexto_rag(db, _q, limite=6, modo_or=True)
            if _chunks:
                _blocos = []
                for _c in _chunks:
                    _f = _c.get("fonte") or _c.get("titulo") or "fonte interna"
                    _blocos.append(f"[{_f}] {(_c.get('conteudo') or '')[:600]}")
                    _fontes_rag.append({"fonte": _f, "titulo": _c.get("titulo")})
                contexto += ("\n\nBASE DE CONHECIMENTO INTERNA (baseie-se SOMENTE "
                             "nestes precedentes/normas; NAO invente jurisprudencia "
                             "fora daqui):\n" + "\n".join(_blocos))
        except Exception as _e:
            logger.warning("RAG grounding indisponivel: %s", _e)

    # LGPD — sanitiza (inclui nomes do caso via nomes_proteger) e aplica a
    # SEGUNDA BARREIRA (validar_sem_pii) ANTES de qualquer envio ao LLM. Se sobrar
    # PII estrutural (CPF/CNPJ/processo/e-mail), aborta — não vaza pra nuvem.
    resultado_sanitizacao = sanitizar_pii(contexto, nomes_proteger)
    contexto_sanitizado = (
        resultado_sanitizacao[0] if isinstance(resultado_sanitizacao, tuple)
        else resultado_sanitizacao
    )

    residual = validar_sem_pii(contexto_sanitizado)
    if residual:
        logger.error("PII residual na analise estrategica: %s", residual)
        return {
            "erro": f"Dados pessoais detectados ({', '.join(residual)}). "
                    "Remova CPF/CNPJ/numero de processo do texto e tente novamente."
        }

    prompt_final = PROMPT_ANALISE.format(contexto=contexto_sanitizado)

    try:
        resp = await chat(
            messages=[
                {"role": "system", "content": prompt_final},
                {"role": "user", "content": "Faça a análise completa agora."},
            ],
            task_type="estrategia",
            temperature=0.3,
            max_tokens=3000,
        )
        resultado = _parse_json_robusto(resp.texto)
        if not resultado:
            logger.warning("Análise estratégica retornou JSON inválido: %s", resp.texto[:200])
            return {"erro": "Falha ao parsear resposta da IA"}
        if isinstance(resultado, dict):
            resultado["_fontes_rag"] = _fontes_rag
        return resultado
    except Exception as e:
        logger.error(f"Erro na análise estratégica: {e}")
        return {"erro": str(e)}
