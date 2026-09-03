"""
Análise estratégica de casos jurídicos com IA.
Atua como advogado sênior com 20 anos de experiência.
"""
import json
import logging
import re

from app.services.system_prompts.base import RESTRICOES

logger = logging.getLogger(__name__)

# Prompt blindado contra alucinação (auditoria 2026-06-30): herda as RESTRIÇÕES
# ABSOLUTAS (nunca inventar jurisprudência/lei/processo, nunca prometer êxito) e
# instrui a admitir lacuna (null) em vez de preencher campos sem base. A
# jurisprudência só pode vir da BASE DE CONHECIMENTO INTERNA (grounding RAG).
PROMPT_ANALISE = ("""Você é um advogado sênior brasileiro com 20 anos de experiência em todas as áreas do direito, especializado em estratégia processual e análise de risco jurídico.
""" + RESTRICOES + """
## REGRAS DESTA ANÁLISE (ANTI-ALUCINAÇÃO — PRIORIDADE MÁXIMA)
- Baseie-se EXCLUSIVAMENTE nos FATOS e na BASE DE CONHECIMENTO INTERNA fornecidos abaixo.
- NUNCA invente jurisprudência, número de acórdão, súmula, artigo de lei ou processo.
- Onde NÃO houver base suficiente, use null (campo) ou lista vazia. É obrigatório admitir a lacuna em vez de inventar.
- Jurisprudência só pode ser citada se constar da BASE DE CONHECIMENTO INTERNA; caso contrário use exatamente "verificar: [tema] no [tribunal]" ou null.
- Estimativas de jurimetria NÃO são promessa de resultado e dependem de validação humana; só preencha números se houver base_estimativa concreta.

## COMO LER (POSTURA DE ADVOGADO, NÃO DE EXTRATOR)
Você não está resumindo o documento: está formando o JUÍZO PROFISSIONAL que um
advogado forma ao lê-lo pela primeira vez, pensando no caso do SEU cliente.
- "provas_necessarias" é o que FALTA provar e como provar: para cada fato
  controvertido, diga qual prova o demonstra, quem a produz e se ela já existe
  nos autos (ja_disponivel=true) ou ainda precisa ser obtida (false).
- "brechas_preliminares" é a leitura defensiva/ofensiva do rito: prescrição,
  decadência, competência, legitimidade, vícios e falhas da parte contrária.
  Toda brecha é HIPÓTESE A VERIFICAR — escreva o indício concreto que a
  sustenta, nunca a conclusão de que algo "é nulo".
- "pontos_fortes"/"pontos_fracos" são do CASO como um todo, não do texto: o que
  sustenta a tese e o que a parte contrária vai atacar primeiro.
- Se o material lido não sustentar um item, use null ou lista vazia. Lacuna
  admitida vale mais para o advogado do que hipótese inventada.

Analise o caso jurídico abaixo. Retorne APENAS um objeto JSON válido, sem texto antes ou depois, sem markdown, sem cercas de código.

CASO:
{contexto}

Retorne este JSON (use null/listas vazias quando não houver base — NÃO invente):
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
      "fundamento_legal": "artigo/lei aplicável; se incerto, 'verificar: [tema]'",
      "jurisprudencia": "SOMENTE precedente presente na BASE DE CONHECIMENTO INTERNA; senão null ou 'verificar: [tema] no [tribunal]'",
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
  "brechas_preliminares": {{
    "prescricao": "indício concreto de prescrição no material lido, ou null",
    "decadencia": "indício concreto de decadência, ou null",
    "incompetencia": "indício de incompetência do juízo, ou null",
    "ilegitimidade": "indício de ilegitimidade de parte, ou null",
    "nulidades": ["vício processual concreto observado no material"],
    "falhas_da_parte_contraria": ["falha/contradição/omissão da outra parte"],
    "observacao": "cada item acima é HIPÓTESE A VERIFICAR, nunca afirmação de nulidade"
  }},
  "provas_necessarias": [
    {{
      "titulo": "prova a produzir ou obter (ex.: contrato assinado, laudo pericial)",
      "tipo": "documental|pericial|testemunhal|inspecao|depoimento_pessoal",
      "fato_probando": "QUAL fato controvertido esta prova demonstra",
      "ja_disponivel": true,
      "quem_produz": "cliente|escritorio|juizo|parte_contraria|terceiro",
      "urgencia": "alta|media|baixa"
    }}
  ],
  "jurimetria": {{
    "chance_sucesso_percent": null,
    "tempo_estimado_meses": null,
    "faixa_valor_min": null,
    "faixa_valor_max": null,
    "base_estimativa": "base CONCRETA da estimativa (tribunal, tipo de caso, histórico); se não houver, mantenha os números acima como null",
    "observacao": "estimativa NÃO é promessa de resultado; depende de prova e de validação humana"
  }},
  "proximos_passos": [
    {{"prazo": "imediato|7 dias|30 dias|60 dias", "acao": "descrição da ação", "prioridade": "alta|media|baixa"}}
  ],
  "alertas": ["alerta importante 1", "alerta importante 2"],
  "observacoes_finais": "observações finais do advogado sênior"
}}""")


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


async def _recuperar_ocr_completo_se_truncado(
    *,
    db,
    texto_documento: str,
    titulo: str,
    numero_processo: str,
    scope_client_id: str | None,
) -> str:
    """Recupera OCR completo quando chamadores legados passaram só o prefixo.

    O hook de upload antigo enviava `ocr_text[:4000]` para esta análise. Enquanto
    todos os chamadores não forem migrados, este fallback procura o documento
    recém-salvo do mesmo caso e substitui o prefixo pelo OCR completo. Fail-safe:
    em qualquer dúvida, devolve o texto recebido.
    """
    if not db or not texto_documento or len(texto_documento) > 4_500:
        return texto_documento
    if len(texto_documento.strip()) < 180:
        return texto_documento

    try:
        from sqlalchemy import desc, or_, select
        from app.models.case import Case
        from app.models.document import Document

        filtros = []
        if numero_processo:
            filtros.append(Case.numero_processo == numero_processo)
        if titulo:
            filtros.append(Case.titulo == titulo)
        if not filtros:
            return texto_documento

        q_case = select(Case.id).where(Case.deleted_at.is_(None), or_(*filtros))
        if scope_client_id:
            q_case = q_case.where(Case.client_id == scope_client_id)
        case_ids = [row[0] for row in (await db.execute(q_case.limit(5))).all()]
        if not case_ids:
            return texto_documento

        q_docs = (
            select(Document.ocr_text)
            .where(
                Document.deleted_at.is_(None),
                Document.case_id.in_(case_ids),
                Document.ocr_text.is_not(None),
            )
            .order_by(desc(Document.created_at))
            .limit(8)
        )
        docs = (await db.execute(q_docs)).scalars().all()
        prefixo = texto_documento[:300].strip()
        assinatura = prefixo[:120]
        for ocr in docs:
            if not ocr or len(ocr) <= len(texto_documento):
                continue
            if ocr.startswith(prefixo) or (assinatura and assinatura in ocr[:1_500]):
                logger.info(
                    "OCR completo recuperado para análise estratégica (%s → %s chars)",
                    len(texto_documento), len(ocr),
                )
                return ocr
    except Exception as exc:
        logger.warning("Recuperação de OCR completo indisponível: %s", exc)

    return texto_documento


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
    scope_client_id: str | None = None,
    case_id: str | None = None,
    db=None,
    user_id: str | None = None,
) -> dict:
    """
    Análise estratégica completa do caso.
    Combina dados do caso + texto extraído de documento (opcional).
    Usa ai_gateway.chat com task_type='estrategia'.
    Se `db` for fornecido, ancora a análise na base RAG (anti-alucinação).
    """
    from app.services.ai_gateway import chat
    from app.services.document_intake_service import montar_dossie_documental
    from app.services.sanitizer import sanitizar_pii, validar_sem_pii

    texto_documento = await _recuperar_ocr_completo_se_truncado(
        db=db,
        texto_documento=texto_documento,
        titulo=titulo,
        numero_processo=numero_processo,
        scope_client_id=scope_client_id,
    )

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
        # Não cortar mais em 4.000 chars. Documento longo vira DOSSIÊ jurídico
        # com início, trechos relevantes do meio/fim e sinais estruturados.
        trecho = montar_dossie_documental(texto_documento, titulo=titulo)
        partes_ctx.append(f"TEXTO EXTRAÍDO DO DOCUMENTO / DOSSIÊ DE INTAKE:\n{trecho}")

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
            _chunks = await buscar_contexto_rag(
                db, _q, limite=6, modo_or=True, scope_client_id=scope_client_id,
                # Comunicação processual de OUTRO caso do mesmo cliente não é
                # contexto desta análise (auditoria, dívida 5.5).
                scope_case_id=case_id,
            )
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

    # Pseudonimização REVERSÍVEL de nomes próprios (PR #85): com case_id+db,
    # deriva as ENTIDADES do caso e deixa o gateway pseudonimizar/reidratar — a
    # resposta volta com o NOME REAL (não [PARTE_n] irreversível). Sem case_id/db
    # (ou helper sem entidades), cai no mascaramento IRREVERSÍVEL legado via
    # nomes_proteger. entidades_do_caso é fail-safe (nunca levanta).
    entidades = None
    modo_sigilo = None
    if db is not None and case_id:
        from app.services.ai.entidades_caso import entidades_do_caso
        entidades = await entidades_do_caso(db, case_id) or None
        # Achado do security-auditor (Issue #1194): esta função é chamada por
        # /cases/{id}/analisar (botão "Análise estratégica com IA" na ficha do
        # caso) E pelo hook automático de upload de documento
        # (document_analysis_hook.py) — nenhum dos dois passava por
        # orchestrator.py/agent/loop.py, que já consultam Case.sigilo_reforcado.
        # Um caso de crime sexual/menor ia pseudonimizado ao externo mesmo com
        # a flag marcada.
        from app.services.ai.sanitization_policy import modo_sigilo_por_case_id
        modo_sigilo = await modo_sigilo_por_case_id(db, case_id)

    # LGPD — sanitiza a PII ESTRUTURAL (CPF/CNPJ/processo/e-mail…) e aplica a
    # SEGUNDA BARREIRA (validar_sem_pii) ANTES de qualquer envio ao LLM. Quando há
    # `entidades`, os NOMES não são pré-mascarados aqui: o gateway os troca por
    # marcadores consistentes (reversíveis) e reidrata a resposta. Sem entidades,
    # mantém o mascaramento IRREVERSÍVEL dos nomes via nomes_proteger.
    resultado_sanitizacao = sanitizar_pii(contexto, None if entidades else nomes_proteger)
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
            nivel_inteligencia="alto",  # FIRAC + fonte por premissa (auditoria 18/08, A-1)
            temperature=0.3,
            max_tokens=3000,
            entidades=entidades,
            modo_sanitizacao=modo_sigilo,
        )
        # I9: AILog quando há db+user_id (routers/documento_ia.py já informa;
        # routers/ai.py, cases.py e document_analysis_hook.py passam a informar
        # quando integrarem — arquivos fora deste pacote/em PR aberto).
        if db is not None and user_id:
            from app.models.ai_log import AITipoUso
            from app.services.ai.core.audit_logger import _fontes_str
            from app.services.ai_gateway import registrar_log_resposta
            await registrar_log_resposta(
                db, user_id=user_id, tipo_uso=AITipoUso.analise_caso, resp=resp,
                prompt_sanitizado="[ANALISE_ESTRATEGICA]\n" + contexto_sanitizado,
                pii_removida=bool(
                    resultado_sanitizacao[1]
                    if isinstance(resultado_sanitizacao, tuple) and len(resultado_sanitizacao) > 1
                    else False
                ) or bool(entidades),
                case_id=case_id, fontes_rag=_fontes_str(_fontes_rag),
            )
        resultado = _parse_json_robusto(resp.texto)
        if not resultado:
            logger.warning("Análise estratégica retornou JSON inválido: %s", resp.texto[:200])
            return {"erro": "Falha ao parsear resposta da IA"}
        if isinstance(resultado, dict):
            resultado["_fontes_rag"] = _fontes_rag
            # A3 (auditoria 2026-06-30) + dívida 5.2 (auditoria 2026-08-18): a
            # análise passa pela validação canônica do núcleo — citações contra a
            # base oficial (anti-alucinação), grounding, promessa de resultado
            # (vedação OAB) e ausência de âncora verificável. Fail-safe: falha na
            # validação não derruba a análise, vira alerta ao revisor humano.
            alertas_validacao: list[str] = []
            if db is not None:
                try:
                    from app.services.ai.core import response_validator
                    validacao = await response_validator.validar(
                        db,
                        json.dumps(resultado, ensure_ascii=False),
                        exige_fonte=True,
                        fontes=_fontes_rag,
                    )
                    resultado["_verificacao_citacoes"] = validacao["citacoes"]
                    resultado["sem_base_verificavel"] = validacao["sem_base_verificavel"]
                    resultado["revisao_obrigatoria"] = validacao["revisao_obrigatoria"]
                    alertas_validacao = list(validacao["alertas"])
                except Exception as _e:
                    logger.warning("validação da análise falhou: %s", _e)
                    alertas_validacao = [
                        "Validação automática indisponível — confira manualmente "
                        "as citações e a ausência de promessa de resultado (OAB)."
                    ]
                    resultado["revisao_obrigatoria"] = True
            # Os alertas do validador entram na MESMA lista que a interface já
            # renderiza; a análise não tem corpo de texto para prefixar.
            if alertas_validacao:
                atuais = resultado.get("alertas")
                atuais = list(atuais) if isinstance(atuais, list) else (
                    [atuais] if isinstance(atuais, str) and atuais.strip() else []
                )
                resultado["alertas"] = atuais + alertas_validacao
            # Carimbo HITL canônico: análise estratégica é rascunho como
            # qualquer outra saída do núcleo de IA.
            from app.services.ai.core import hitl_policy
            resultado = hitl_policy.aplicar(resultado)
        return resultado
    except Exception as e:
        logger.error(f"Erro na análise estratégica: {e}")
        return {"erro": str(e)}
