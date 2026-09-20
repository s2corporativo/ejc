"""
Serviço de execução de AI Skills do EJC.
Usa ai_gateway.chat() para roteamento ao provedor e registra em ai_logs.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ai_skill import EjcSkill
from app.models.ai_log import AITipoUso, normalizar_modelo_ia
from app.services import ai_gateway
from app.services.ai import juridico_guardrails
from app.services.ai_document_chunking import dividir_documento_em_blocos
from app.services.ai_guard import sanitizar_ou_abortar, registrar_ai_log
from app.services.legal_base import garantir_identidade

logger = logging.getLogger("ejc.ai.skills")
settings = get_settings()

_ENGINE_PROVIDER = {"anthropic": "anthropic", "groq": "groq", "ollama": "ollama",
                    "maritaca": "maritaca"}


def _provider_override_skill(engine: str | None) -> str | None:
    """Converte o engine legado da skill em override somente quando necessário.

    Com ANTHROPIC_EXPLICIT_ONLY=true, skills não podem furar a política central
    por terem sido gravadas historicamente com engine=anthropic/groq. Deixamos
    Groq/Maritaca no roteamento automático por task_type e preservamos apenas
    Ollama como override explícito de soberania/local. Desligar a flag restaura
    o comportamento legado integral.
    """
    provider = _ENGINE_PROVIDER.get((engine or "").strip().lower(), "groq")
    if getattr(settings, "ANTHROPIC_EXPLICIT_ONLY", True):
        return "ollama" if provider == "ollama" else None
    return provider


_AREA_TASK = {
    "juridico": "elaboracao_peca",
    "financeiro": "analise_juridica",
    "operacional": "resumo",
    "administrativo": "elaboracao_peca",
    "civel": "elaboracao_peca",
    "consumidor": "elaboracao_peca",
    "estrategia": "analise_juridica",
    "familia": "elaboracao_peca",
    "imobiliario": "elaboracao_peca",
    "penal": "elaboracao_peca",
    "previdenciario": "elaboracao_peca",
    "saude": "elaboracao_peca",
    "trabalhista": "elaboracao_peca",
    "provas": "resumo",
    "tributario": "elaboracao_peca",
}

# Roles com credencial para executar skills marcadas oab_restricted (produção de
# trabalho jurídico sob responsabilidade OAB). cliente_externo já é bloqueado
# antes (não acessa IA interna); estagiário/secretaria/financeiro ficam de fora.
_ROLES_OAB = {"superadmin", "admin", "socio", "advogado", "advogado_auxiliar"}

# Metadado funcional do catálogo: fonte única para agrupamento da UI.
# Não exige coluna/migration porque é uma classificação de apresentação
# derivada dos metadados autorais já persistidos na skill.
_FUNCTIONAL_GROUP_KEYWORDS: dict[str, tuple[str, ...]] = {
    "analisar": (
        "raio-x", "raiox", "analise", "analisar", "resumo", "resumir",
        "cronologia", "extrair", "identificar", "localizar", "avaliar",
        "casador", "detector", "auditor", "provas", "inconsist", "risc",
        "dossie", "score", "checklist",
    ),
    "produzir": (
        "peticao", "contestacao", "replica", "recurso", "contrato", "parecer",
        "notificacao", "procuracao", "relatorio", "redigir", "gerar", "minuta",
        "peca", "embargos", "agravo", "apelacao", "mandado", "habeas",
        "cumprimento",
    ),
    "revisar": (
        "corrigir", "conferir", "revisar", "verificar", "coerenc",
        "fundament", "linguagem", "calculo", "valor", "ausente",
        "contradicao", "jurisprudenc",
    ),
    "preparar": (
        "audiencia", "reuniao", "negociacao", "sustentacao", "diligencia",
        "checklist", "preparar", "estrateg", "defesa", "orient",
    ),
}


def functional_group(skill: EjcSkill) -> str:
    """Agrupa a skill para navegação sem duplicar a regra no frontend.

    Mantém a semântica histórica: empate preserva o primeiro grupo com maior
    score e ausência de palavra-chave cai em produzir.
    """
    texto = f"{skill.name} {skill.description or ''}".lower()
    melhor = "produzir"
    melhor_score = 0
    for grupo, keywords in _FUNCTIONAL_GROUP_KEYWORDS.items():
        score = sum(1 for keyword in keywords if keyword in texto)
        if score > melhor_score:
            melhor = grupo
            melhor_score = score
    return melhor


def _aplicar_guardrails_juridicos(skill_name: str, texto: str) -> tuple[str, list[str]]:
    """Guardrail jurídico DETERMINÍSTICO (Issue #554) — não confia só no
    system_prompt gravado no banco (o texto vem da IA e a Issue reproduziu o
    erro mesmo com o prompt instruindo o contrário):

      1. Prescrição/decadência não pode ser qualificada como extinção SEM
         resolução de mérito (contraria CPC, art. 487, II) — corrigida.
      2. CDC arts. 26 (vício — decadência) e 27 (fato do produto/serviço —
         prescrição) não podem ser cumulados sem fundamentação separada por
         pretensão — alertado (HITL decide, pois depende dos fatos do caso).

    Escopo: só as duas skills reproduzidas na Issue (`NOME_SKILLS_DECADENCIA_
    PRESCRICAO`) — não altera o comportamento de nenhuma outra skill.

    O texto retornado (`texto_final`) é o que vai para `resultado["conteudo"]`
    E para `AILog.resposta` (mesma variável, ver `executar_skill`) — por isso
    o alerta de cumulação CDC também é ANEXADO ao texto, não só devolvido na
    lista `alertas` (achado de review, Codex, PR #703, P1): quando só
    `checar_cumulacao_vicio_fato_cdc` dispara (sem correção de mérito), sem
    anexar ao texto o alerta sumiria do log persistido, sobrevivendo só na
    resposta transiente da API.

    Retorna (texto_final, alertas_para_o_campo_'aviso').
    """
    if skill_name not in juridico_guardrails.NOME_SKILLS_DECADENCIA_PRESCRICAO:
        return texto, []
    alertas: list[str] = []
    texto_final, corrigido = juridico_guardrails.aplicar_guardrail_merito(texto)
    if corrigido:
        alertas.append(juridico_guardrails.ALERTA_MERITO_CORRIGIDO)
    alertas_cdc = juridico_guardrails.checar_cumulacao_vicio_fato_cdc(texto_final)
    if alertas_cdc:
        alertas += alertas_cdc
        texto_final = juridico_guardrails.anexar_alerta_cdc_ao_texto(texto_final, alertas_cdc)
    return texto_final, alertas


def _marcar_uso(skill: EjcSkill) -> None:
    """Incrementa o contador de uso da skill (Bloco 4 — enxugar catálogo,
    migration 130). Não commita — quem chama já commita junto do AILog na
    mesma transação (registrar_ai_log)."""
    skill.vezes_executado = (skill.vezes_executado or 0) + 1
    skill.ultima_execucao = datetime.now(timezone.utc)


async def skills_sem_uso(db: AsyncSession, dias_minimos: int = 90) -> list[EjcSkill]:
    """Skills ativas, criadas há mais de `dias_minimos` dias, nunca executadas
    (Bloco 4 — enxugar catálogo). Só relata — não arquiva nada; arquivar é
    decisão humana, feita com `PATCH /ai/skills/{id}` (active=False) depois
    de revisar esta lista. Skills recentes ficam de fora do relatório de
    propósito — nunca terem sido usadas ainda não significa que não serão."""
    from datetime import timedelta

    corte = datetime.now(timezone.utc) - timedelta(days=dias_minimos)
    result = await db.execute(
        select(EjcSkill)
        .where(
            EjcSkill.active == True,
            EjcSkill.vezes_executado == 0,
            EjcSkill.created_at < corte,
        )
        .order_by(EjcSkill.area, EjcSkill.display_name)
    )
    return result.scalars().all()


async def listar_skills(db: AsyncSession, area: str | None = None) -> list[EjcSkill]:
    q = select(EjcSkill).where(EjcSkill.active == True)
    if area:
        q = q.where(EjcSkill.area == area)
    result = await db.execute(q.order_by(EjcSkill.area, EjcSkill.display_name))
    return result.scalars().all()


async def executar_skill(
    db: AsyncSession,
    skill_name: str,
    query: str,
    user_id: str,
    case_id: str | None = None,
    contexto_rag: list[str] | None = None,
    user_role: str | None = None,
    entidades: dict[str, list[str]] | None = None,
) -> dict:
    result = await db.execute(
        select(EjcSkill).where(EjcSkill.name == skill_name, EjcSkill.active == True)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise ValueError(f"Skill '{skill_name}' não encontrada ou inativa.")

    # Enforcement de oab_restricted: skills que produzem trabalho jurídico sob
    # responsabilidade OAB só executam para roles com credencial. Antes esta
    # coluna era apenas descritiva (sem gate em runtime — achado de auditoria).
    if skill.oab_restricted and (user_role or "") not in _ROLES_OAB:
        raise PermissionError(
            f"Skill '{skill_name}' é restrita (OAB): seu perfil não tem permissão para executá-la."
        )

    # Guarda LGPD (auditoria 2026-07-02): query (texto digitado OU extraído via
    # OCR de documento de cliente em /execute-doc) ia direto ao provedor externo
    # sem sanitização — aborta se sobrar PII estrutural após a sanitização.
    query_limpa, pii = sanitizar_ou_abortar(query)
    nomes_entidades = [
        nome
        for nomes in (entidades or {}).values()
        for nome in nomes
    ]
    prompt_log, pii_nomes_prompt = sanitizar_ou_abortar(
        query_limpa, nomes_entidades
    )

    system_prompt = skill.system_prompt
    # ── ANTI-INJEÇÃO (pente fino 03/09) ──────────────────────────────────────
    # O RAG ia para o SYSTEM, cru. `system` é o papel de MÁXIMA confiança do
    # modelo, e o conteúdo vem da base de conhecimento, que aceita ingestão de
    # PDF e de URL — um documento envenenado ali passava a ditar regra de
    # sistema. É EXATAMENTE o achado que `ia_especializada.py` já corrigiu ("o
    # pior caso: RAG ia direto para system"), e cuja regressão
    # `test_ai_prompt_injection_delimitadores.py` trava lá; esta instância
    # ficou de fora. Agora o RAG vai no USER, em bloco com token aleatório.
    from app.services.ai import delimitador
    user_content = query_limpa
    if contexto_rag:
        _tok = delimitador.novo_token()
        system_prompt += delimitador.INSTRUCAO_SYSTEM
        user_content = delimitador.montar(
            delimitador.bloco(
                "BASE DE CONHECIMENTO INTERNA",
                "\n\n---\n\n".join(
                    f"Trecho {i+1}:\n{c}" for i, c in enumerate(contexto_rag)
                ),
                _tok,
            ),
            instrucao_final=query_limpa,
        )

    # Barreira anti-alucinação OBRIGATÓRIA: o system_prompt da skill é autoral
    # (gravado no banco) e o task_type derivado da área pode não passar por
    # aplicar_base no gateway — garantimos a identidade/regras OAB aqui.
    messages = garantir_identidade([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ])

    provider = _provider_override_skill(skill.engine)
    task_type = _AREA_TASK.get(skill.area, "analise_juridica")

    # ── PISO DE SIGILO (pente fino 03/09) ────────────────────────────────────
    # SÉTIMA ocorrência da classe que a Issue #1194 fechou seis vezes e este PR
    # mais cinco: função que recebe `case_id` e chama o gateway sem
    # `modo_sanitizacao`. Aqui era a pior variante — `provider_override` força
    # o engine da skill, cujo default é **groq** (externo). Numa skill rodada
    # sobre caso com `sigilo_reforcado=True`, o conteúdo ia para fora do VPS, e
    # o filtro `_restringir_cadeia_local_completo` do gateway não ajudava
    # porque só age quando o modo chega. O contrato automatizado que escrevi
    # (`test_piso_sigilo_rotas_vinculadas_a_caso.py`) varre `app/routers/` e não
    # alcançava `app/services/` — a varredura foi ampliada junto com esta correção.
    from app.services.ai.sanitization_policy import modo_sigilo_por_case_id
    modo_sigilo = await modo_sigilo_por_case_id(db, case_id)

    resp = await ai_gateway.chat(
        messages=messages,
        task_type=task_type,
        provider_override=provider,
        nivel_inteligencia="alto",
        entidades=entidades,
        modo_sanitizacao=modo_sigilo,
    )

    inp = resp.input_tokens or 0
    out = resp.output_tokens or 0
    custo = float(resp.custo_estimado_brl or 0.0)

    # Guardrail jurídico determinístico (Issue #554) — ANTES do log: corrige/
    # alerta sobre a qualificação de mérito e a cumulação CDC 26/27, para que
    # tanto a resposta devolvida quanto o AILog persistido já reflitam a
    # correção (não só a leitura futura).
    texto_corrigido, alertas_juridicos = _aplicar_guardrails_juridicos(
        skill.name, resp.texto
    )

    resposta_log, pii_resposta = sanitizar_ou_abortar(
        texto_corrigido, nomes_entidades
    )

    modelo_log = f"{resp.provedor}/{resp.modelo}" if resp.provedor else resp.modelo
    _marcar_uso(skill)
    # registrar_ai_log PROPAGA erro (não engole em try/except com só warning) —
    # log de uso de IA é parte da própria correção, não pode falhar em silêncio.
    log_id = await registrar_ai_log(
        db,
        user_id=user_id,
        tipo_uso=AITipoUso.outro,
        case_id=case_id,
        prompt_sanitizado=prompt_log,
        pii_removida=pii or pii_nomes_prompt or pii_resposta,
        resposta=resposta_log,
        modelo=normalizar_modelo_ia(modelo_log),
        tokens_input=inp,
        tokens_output=out,
        custo_estimado=custo,
    )

    resultado = {
        "conteudo": texto_corrigido,
        "skill": skill.display_name,
        "skill_name": skill.name,
        "engine": skill.engine,
        "provider": resp.provedor,
        "is_rascunho": True,
        "requer_revisao": skill.requires_human_review or bool(alertas_juridicos),
        "tokens_usados": inp + out,
        "custo_estimado_brl": custo,
        "ai_log_id": log_id,
    }
    if alertas_juridicos:
        resultado["aviso"] = (
            "RASCUNHO — revisão humana obrigatória antes de qualquer uso (OAB). "
            + " ".join(alertas_juridicos)
        )
    return resultado


def _bloco_documento(texto: str, indice: int, total: int) -> str:
    """Bloco de OCR delimitado com token aleatório por chamada.

    O texto vem de documento ENVIADO pelo usuário — na prática, escrito por
    terceiro (parte contrária, órgão, cliente). Ia cru na mensagem, exatamente
    o vetor que `documento_service` fechou.
    """
    from app.services.ai import delimitador
    tok = delimitador.novo_token()
    return delimitador.montar(
        delimitador.bloco(f"DOCUMENTO ENVIADO - BLOCO {indice} DE {total}", texto, tok),
        instrucao_final="Produza a ficha factual deste bloco.",
    )


async def executar_skill_documento_longo(
    *,
    db: AsyncSession,
    skill_name: str,
    texto_documento: str,
    instrucoes: str,
    user_id: str,
    case_id: str | None = None,
    contexto_rag: list[str] | None = None,
    user_role: str | None = None,
    entidades: dict[str, list[str]] | None = None,
) -> dict:
    """Executa uma skill sobre documento maior que a janela segura de 1 chamada.

    Usa map-reduce auditável: cada bloco gera uma ficha factual curta; apenas as
    fichas e as instruções seguem para a síntese final da skill. Um único AILog
    representa a operação lógica e soma tokens/custos de todas as chamadas.

    O limite é configurável para não prometer "centenas de páginas" em conta de
    provedor sem TPM suficiente. Acima dele a API falha de forma explícita, em
    vez de truncar e produzir uma conclusão aparentemente completa.
    """
    result = await db.execute(
        select(EjcSkill).where(EjcSkill.name == skill_name, EjcSkill.active == True)
    )
    skill = result.scalar_one_or_none()
    if not skill:
        raise ValueError(f"Skill '{skill_name}' não encontrada ou inativa.")
    if skill.oab_restricted and (user_role or "") not in _ROLES_OAB:
        raise PermissionError(
            f"Skill '{skill_name}' é restrita (OAB): seu perfil não tem permissão para executá-la."
        )

    limite = settings.AI_LONG_DOCUMENT_MAX_CHARS
    tamanho_bloco = settings.AI_LONG_DOCUMENT_CHUNK_CHARS
    max_blocos = settings.AI_LONG_DOCUMENT_MAX_CHUNKS
    texto_documento = (texto_documento or "").strip()
    if len(texto_documento) > limite:
        raise ValueError(
            "Documento excede o limite seguro desta análise imediata "
            f"({limite:,} caracteres). Importe-o em Documentos/Data Room para "
            "indexação integral ou aumente AI_LONG_DOCUMENT_MAX_CHARS junto com "
            "o limite de tokens do provedor."
        )

    blocos = dividir_documento_em_blocos(
        texto_documento,
        tamanho=tamanho_bloco,
    )
    if not blocos:
        raise ValueError("Documento sem texto útil para análise.")
    if len(blocos) > max_blocos:
        raise ValueError(
            f"Documento gerou {len(blocos)} blocos; o limite operacional é "
            f"{max_blocos}. Use a indexação integral em Documentos/Data Room."
        )

    instrucoes_limpas, pii_instrucoes = sanitizar_ou_abortar(
        (instrucoes or "").strip()[:4000]
    )
    nomes_entidades = [
        nome
        for nomes in (entidades or {}).values()
        for nome in nomes
    ]
    provider = _provider_override_skill(skill.engine)
    semaforo = asyncio.Semaphore(2)

    # PISO DE SIGILO resolvido UMA vez para as N+1 chamadas desta função
    # (pente fino 03/09): eram TRÊS caminhos ao gateway sem `modo_sanitizacao`
    # — o resumo de cada bloco e a síntese final —, todos com
    # `provider_override` forçando o engine da skill (default groq, externo).
    # Num caso `sigilo_reforcado=True`, o OCR inteiro do documento saía do VPS.
    from app.services.ai.sanitization_policy import modo_sigilo_por_case_id
    _modo_sigilo = await modo_sigilo_por_case_id(db, case_id)

    async def resumir_bloco(indice: int, bruto: str):
        limpo, pii = sanitizar_ou_abortar(bruto)
        mensagens = garantir_identidade([
            {
                "role": "system",
                "content": (
                    "Você faz EXTRAÇÃO FACTUAL PARCIAL de documento jurídico. "
                    "Analise somente o bloco recebido; não redija a peça final e "
                    "não complete lacunas. Entregue no máximo 12 itens curtos: "
                    "datas/atos, partes, alegações, pedidos, decisões, provas, "
                    "valores, prazos expressos, contradições e pontos inaudíveis/"
                    "ilegíveis. Preserve marcadores de página quando existirem."
                ),
            },
            {
                "role": "user",
                # OCR de documento ENVIADO — conteúdo de terceiro. Delimitado
                # com token aleatório, como em `documento_service`.
                "content": _bloco_documento(limpo, indice + 1, len(blocos)),
            },
        ])
        async with semaforo:
            resposta = await ai_gateway.chat(
                messages=mensagens,
                task_type="resumo",
                provider_override=provider,
                nivel_inteligencia="alto",
                max_tokens=500,
                entidades=entidades,
                modo_sanitizacao=_modo_sigilo,
            )
        return indice, resposta, pii

    parciais = await asyncio.gather(
        *(resumir_bloco(i, bloco) for i, bloco in enumerate(blocos))
    )
    parciais.sort(key=lambda item: item[0])

    fichas = "\n\n".join(
        f"### BLOCO {indice + 1}/{len(blocos)}\n{resposta.texto}"
        for indice, resposta, _ in parciais
    )
    system_prompt = skill.system_prompt
    from app.services.ai import delimitador
    _tok_final = delimitador.novo_token()
    _rag_bloco = ""
    if contexto_rag:
        # Mesma correção de `executar_skill`: a base interna sai do SYSTEM.
        system_prompt += delimitador.INSTRUCAO_SYSTEM
        _rag_bloco = delimitador.bloco(
            "BASE DE CONHECIMENTO INTERNA",
            "\n\n---\n\n".join(
                f"Trecho RAG {i + 1}:\n{c}" for i, c in enumerate(contexto_rag)
            ),
            _tok_final,
        )
    system_prompt += (
        "\n\nO documento foi lido em blocos. As fichas abaixo são intermediárias: "
        "não trate ausência na ficha como ausência nos autos; sinalize tudo o "
        "que exigir conferência no original. Não invente número de página."
    )
    # As FICHAS são resumo de documento de terceiro: entram como DADO
    # delimitado, não como texto solto colado à instrução do usuário.
    mensagem_final = delimitador.montar(
        _rag_bloco,
        delimitador.bloco(
            "FICHAS FACTUAIS DO DOCUMENTO ENVIADO", fichas, _tok_final),
        instrucao_final=(
            f"INSTRUÇÕES DO USUÁRIO:\n{instrucoes_limpas}"
            if instrucoes_limpas else
            "Produza a saída conforme a finalidade da skill."
        ),
    )
    final = await ai_gateway.chat(
        messages=garantir_identidade([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": mensagem_final},
        ]),
        task_type=_AREA_TASK.get(skill.area, "analise_juridica"),
        provider_override=provider,
        nivel_inteligencia="alto",
        max_tokens=3000,
        entidades=entidades,
        modo_sanitizacao=_modo_sigilo,
    )

    respostas = [item[1] for item in parciais] + [final]
    tokens_input = sum(r.input_tokens or 0 for r in respostas)
    tokens_output = sum(r.output_tokens or 0 for r in respostas)
    custo = sum(float(r.custo_estimado_brl or 0) for r in respostas)

    # Guardrail jurídico determinístico (Issue #554) — mesmo tratamento de
    # executar_skill(), aplicado à síntese final do documento longo.
    texto_final_corrigido, alertas_juridicos = _aplicar_guardrails_juridicos(
        skill.name, final.texto
    )

    resposta_log, pii_resposta = sanitizar_ou_abortar(
        texto_final_corrigido, nomes_entidades
    )
    prompt_log, pii_nomes_prompt = sanitizar_ou_abortar(
        instrucoes_limpas, nomes_entidades
    )
    pii_removida = (
        pii_instrucoes
        or pii_nomes_prompt
        or pii_resposta
        or any(item[2] for item in parciais)
    )
    modelo_log = f"{final.provedor}/{final.modelo}" if final.provedor else final.modelo
    _marcar_uso(skill)
    log_id = await registrar_ai_log(
        db,
        user_id=user_id,
        tipo_uso=AITipoUso.resumo_documento,
        case_id=case_id,
        prompt_sanitizado=(
            f"[DOCUMENTO LONGO; caracteres={len(texto_documento)}; "
            f"blocos={len(blocos)}]\n{prompt_log}"
        ),
        pii_removida=pii_removida,
        resposta=resposta_log,
        modelo=normalizar_modelo_ia(modelo_log),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        custo_estimado=custo,
    )
    resultado = {
        "conteudo": texto_final_corrigido,
        "skill": skill.display_name,
        "skill_name": skill.name,
        "engine": skill.engine,
        "provider": final.provedor,
        "is_rascunho": True,
        "requer_revisao": skill.requires_human_review or bool(alertas_juridicos),
        "tokens_usados": tokens_input + tokens_output,
        "custo_estimado_brl": custo,
        "ai_log_id": log_id,
        "processamento": {
            "modo": "map_reduce",
            "caracteres": len(texto_documento),
            "blocos": len(blocos),
            "truncado": False,
        },
    }
    if alertas_juridicos:
        resultado["aviso"] = (
            "RASCUNHO — revisão humana obrigatória antes de qualquer uso (OAB). "
            + " ".join(alertas_juridicos)
        )
    return resultado
