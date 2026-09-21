# ── app/services/ai/core/orchestrator.py ─────────────────────────────────────
# NÚCLEO ÚNICO DE IA DO EJC — SingleAICoreOrchestrator ("Cérebro EJC").
#
# TODA tarefa de IA do sistema passa por aqui. Nenhum módulo tem IA própria;
# nenhuma tela chama modelo; nenhum router monta pipeline paralelo.
#
# Fluxo (imutável):
#   intenção → agente interno → permissão (RBAC/ABAC) → contexto (dossiê/RAG)
#   → sanitização LGPD → policy de provider → ai_gateway → validação de
#   resposta (citações/promessas/base verificável) → HITL → AILog → resposta.
#
# Regras rígidas (Etapa 12):
#   • cliente_externo NUNCA acessa o núcleo;
#   • provider externo só recebe conteúdo sanitizado (dupla barreira:
#     ai_guard aqui + barreira final no ai_gateway);
#   • toda resposta jurídica é rascunho HITL;
#   • interação com db+user SEM AILog gravado = falha (erro propaga);
#   • nenhum segredo em prompt, log ou resposta.
from __future__ import annotations
import logging

from fastapi import HTTPException

from app.services.system_prompts import SYSTEM_PROMPTS, TarefaIA, get_configuracao
from app.services.system_prompts.inventario import impressao as prompt_versao
from app.services.ai.provider_policy import AIProviderPolicy
from app.services.ai.sanitization_policy import rotulo_de_sigilo_reforcado, modo_sigilo_do_caso
from app.services.ai.core.intent_classifier import classify_intent
from app.services.ai.core.agent_registry import AGENT_REGISTRY
from app.services.ai.core.ejc_skill_catalog import resolve_native_skill_plan
from app.services.ai.core import (
    audit_logger,
    context_builder,
    hitl_policy,
    response_validator,
)

logger = logging.getLogger("ejc.ai.core")

# TarefaIA → task_type do ai_gateway (cadeia de modelos/fallback).
_TAREFA_PARA_GATEWAY: dict[TarefaIA, str] = {
    TarefaIA.ANALISE_CASO: "estrategia",
    TarefaIA.DOSSIE: "estrategia",
    TarefaIA.TRABALHISTA: "estrategia",
    # Criminal (decisão de produto 2026-07-06): o gateway_task "criminal" resolve
    # EXTERNO_PSEUDONIMIZADO na sanitization_policy — vai a provider externo APENAS
    # pseudonimizado (marcadores) e a resposta é reidratada localmente. O rótulo
    # "criminal" é mantido para que o escritório possa, se quiser, REFORÇAR essa
    # tarefa de volta a LOCAL_COMPLETO via AI_SANITIZATION_MODE_MAP.
    TarefaIA.CRIMINAL: "criminal",
    TarefaIA.FAMILIA: "estrategia",
    TarefaIA.ADMINISTRATIVO: "estrategia",
    TarefaIA.SUCESSOES: "estrategia",
    TarefaIA.IMOBILIARIO: "estrategia",
    TarefaIA.AMBIENTAL: "analise_juridica",
    TarefaIA.MINUTAS: "elaboracao_peca",
    TarefaIA.PRAZOS: "analise_juridica",
    TarefaIA.AUDIENCIA: "analise_juridica",
    TarefaIA.HONORARIOS: "honorarios",
    TarefaIA.PESQUISA_JURIDICA: "analise_juridica",
    TarefaIA.RAG_QUERY: "analise_juridica",
    TarefaIA.TRIAGEM: "resumo",
    TarefaIA.RESUMO: "resumo",
    TarefaIA.DEFAULT: "chat_rapido",
}

# Agentes com perfil de gateway próprio (independe da TarefaIA).
_AGENTE_GATEWAY_OVERRIDE: dict[str, str] = {
    "JurimetryAgent": "jurimetria",
    "BankForensicsAgent": "analise_contrato",
}


class SingleAICoreOrchestrator:
    """Orquestrador único: recebe a tarefa, devolve resposta governada."""

    async def run(
        self,
        *,
        db=None,
        user=None,
        task_type: str,
        domain: str | None = None,
        mensagem: str,
        case_id: str | None = None,
        document_id: str | None = None,
        process_id: str | None = None,
        params: dict | None = None,
        usar_rag: bool = True,
        # I2: None → o gateway aplica o piso da TAREFA (_nivel_piso). Informar
        # "alto" aqui anulava AI_NIVEL_INTELIGENCIA_MERITO=maximo para todo o
        # núcleo (o piso só vale quando o chamador não pede nível).
        nivel_inteligencia: str | None = None,
    ) -> dict:
        params = params or {}

        # 1) Intenção → agente interno ────────────────────────────────────────
        intent = classify_intent(task_type, domain, mensagem)
        agente = AGENT_REGISTRY[intent.agente]
        coordenador = AGENT_REGISTRY["EJCCoordinatorAgent"]
        native_plan = resolve_native_skill_plan(
            task_type=task_type,
            domain=domain,
            message=mensagem,
            module_key=str(params.get("module_key") or "") or None,
            surface=str(params.get("surface") or "") or None,
        )
        skill_pipeline: list[str] = []
        for skill_name in agente.skills:
            if skill_name not in skill_pipeline:
                skill_pipeline.append(skill_name)
            if skill_name == "classify_intent":
                for native_name in (
                    "resolve_native_skills",
                    *native_plan.skill_names,
                ):
                    if native_name not in skill_pipeline:
                        skill_pipeline.append(native_name)

        # 2) Permissão (RBAC/ABAC) ────────────────────────────────────────────
        raw_role = getattr(user, "role", "")
        role = getattr(raw_role, "value", raw_role) or ""
        if user is not None and role == "cliente_externo":
            raise HTTPException(403, "Funções de IA internas não estão disponíveis no portal do cliente.")
        if agente.roles_permitidos and (user is None or role not in agente.roles_permitidos):
            raise HTTPException(403, f"Agente {agente.nome} restrito a: {', '.join(agente.roles_permitidos)}.")
        # O caso é CAPTURADO (não descartado): `Case.area` é a fonte autoritativa
        # do sigilo. Os rótulos da requisição (task_type/domain) vêm do cliente e
        # podem simplesmente não mencionar a área — o caminho agêntico já fazia
        # certo em ai/agent/loop.py, este não.
        caso = None
        if case_id and db is not None and user is not None:
            from app.core.ownership import verificar_acesso_caso
            caso = await verificar_acesso_caso(db, user, case_id)  # 403/404 se indevido

        # 3) Contexto real (backend monta; frontend só envia IDs) ─────────────
        # `user` repassado ao builder: ownership de document_id/process_id é
        # validado LÁ (fail-closed) — não basta o gate de case_id acima, pois
        # doc/processo chegam por IDs independentes do corpo e poderiam pertencer
        # a OUTRO caso/cliente (IDOR/vazamento cross-tenant, risco LGPD).
        ctx = await context_builder.montar_contexto(
            db,
            mensagem=mensagem,
            case_id=case_id,
            document_id=document_id,
            process_id=process_id,
            user=user,
            usar_rag=usar_rag,
            exige_fonte=intent.exige_fonte,
        )

        # 4) Sanitização LGPD do input ("sanitiza e segue" — 2026-07-06; não
        #    aborta mais em PII residual, apenas registra). Os nomes do caso são
        #    protegidos DE FORMA REVERSÍVEL na barreira final do gateway (passo 6,
        #    via `entidades`); aqui a limpeza de entrada é defesa em profundidade.
        from app.services.ai_guard import sanitizar_ou_abortar
        nomes = list(ctx.nomes_proteger) + list(params.get("nomes_proteger") or [])
        mensagem_sana, pii_removida = sanitizar_ou_abortar(mensagem, nomes or None)

        # 5) Policy central de providers ──────────────────────────────────────
        provider_solicitado = str(params.get("provider") or "").strip().lower() or None
        if provider_solicitado == "auto":
            provider_solicitado = None
        if provider_solicitado not in {None, "groq", "maritaca", "anthropic", "ollama"}:
            raise HTTPException(422, "Provedor de IA inválido.")

        decisao = AIProviderPolicy().avaliar(
            f"{mensagem_sana}\n{ctx.texto}",
            intent.tarefa.value,
            ja_sanitizado=True,
            exige_fonte=intent.exige_fonte,
            provider_solicitado=provider_solicitado,
        )
        if not decisao.permitido:
            # V2-5.5 (auditoria): esta rejeição acontece ANTES do gateway —
            # sem registro aqui, o painel /ia-governanca/provedores reporta
            # "0 falhas" mesmo quando 100% das chamadas de uma rota são
            # bloqueadas (caso típico: PII residual sem provider local
            # elegível). Ver provider_metrics_runtime.registrar_bloqueio_politica.
            from app.services.ai.provider_metrics_runtime import registrar_bloqueio_politica
            await registrar_bloqueio_politica(
                task_type=intent.tarefa.value, motivo=decisao.bloqueio_motivo or "",
            )
            raise HTTPException(422, decisao.bloqueio_motivo or "Chamada de IA bloqueada pela política de segurança.")

        # 6) Chamada via ai_gateway (barreira final de PII lá dentro) ─────────
        from app.services import ai_gateway
        cfg = get_configuracao(intent.tarefa)
        system_prompt = SYSTEM_PROMPTS.get(agente.prompt_key, SYSTEM_PROMPTS["default"])
        if native_plan.prompt_blocks:
            system_prompt += (
                "\n\n## MÉTODOS NATIVOS ATIVOS DO EJC\n"
                + "\n\n".join(native_plan.prompt_blocks)
            )
        # Bloco aditivo por superfície (ex.: padrão obrigatório da Sala
        # Jurídica). Opt-in via params["prompt_extra"]; chave desconhecida é
        # ignorada — jamais derruba a chamada.
        from app.services.system_prompts import PROMPT_EXTRAS
        extra = PROMPT_EXTRAS.get((params or {}).get("prompt_extra") or "")
        if extra:
            system_prompt += extra
        if agente.nome == "SystemHealthAgent" or agente.nome == "RepairAgent":
            # Contexto técnico (grafo de código) — nunca contém segredos.
            from app.services.ai.core.skill_registry import SKILL_REGISTRY
            ctx.texto = (ctx.texto + "\n\n" if ctx.texto else "") + \
                "[CONTEXTO TÉCNICO — GRAPH_REPORT]\n" + SKILL_REGISTRY["diagnose_system_module"].handler()
        # Anti-injection: conteúdo de terceiros (OCR/RAG/dossiê) NUNCA entra no
        # system prompt — vai delimitado na mensagem do usuário, como DADO.
        # O delimitador era FIXO (`[CONTEXTO]…[/CONTEXTO]`): a string está no
        # código-fonte, então bastava o OCR da peça da parte contrária — ou um
        # documento envenenado na base interna — conter `[/CONTEXTO]` para
        # "sair" do bloco de dados e emendar instruções como se fossem do
        # backend. Agora o par carrega TOKEN ALEATÓRIO por chamada (ponto único
        # em `ai/delimitador.py`), que o autor do conteúdo não conhece.
        user_content = mensagem_sana
        if ctx.texto:
            from app.services.ai import delimitador
            system_prompt += delimitador.INSTRUCAO_SYSTEM
            _tok = delimitador.novo_token()
            user_content = delimitador.montar(
                delimitador.bloco("CONTEXTO", ctx.texto, _tok),
                instrucao_final=mensagem_sana,
            )

        gateway_task = _AGENTE_GATEWAY_OVERRIDE.get(agente.nome) or \
            _TAREFA_PARA_GATEWAY.get(intent.tarefa, "analise_juridica")

        # ── PISO DE SIGILO POR ÁREA (AI-019 + review do Codex no PR #496) ────
        # O mapeamento acima é genérico: família, saúde e médico caem em
        # "estrategia"/"analise_caso" e PERDEM o rótulo da área antes do
        # gateway — que resolve o modo de sanitização justamente pelo
        # `task_type`. Sem esta correção, um caso de família ou saúde seguia
        # como EXTERNO_PSEUDONIMIZADO e podia deixar o VPS, apesar do default
        # LOCAL_COMPLETO. Se o rótulo ORIGINAL (task_type recebido, domínio do
        # agente ou tarefa classificada) exigir LOCAL_COMPLETO, ele é o
        # task_type entregue ao gateway — o piso nunca é rebaixado.
        #
        # A resolução vive em sanitization_policy (ponto único da política) e
        # canoniza o rótulo antes de comparar: `domain` chega de campo livre, e
        # "família"/"Direito de Família"/"familia_analysis" precisam bater com a
        # mesma regra que "familia". Sem `try/except`: se a política não puder
        # ser avaliada, a chamada falha em vez de seguir com o rótulo rebaixado.
        # A ÁREA REAL DO CASO vem primeiro: é a única fonte que o cliente não
        # controla. `task_type` e `domain` chegam do corpo da requisição, então
        # um caso de família consultado sem `domain` (ou com "civel") escapava do
        # piso e levava dossiê, documentos e RAG do caso ao provider externo.
        area_do_caso = (getattr(getattr(caso, "area", None), "value", None)
                        or str(getattr(caso, "area", "") or ""))
        rotulo_sigiloso = rotulo_de_sigilo_reforcado(
            area_do_caso,
            task_type,
            domain,
            getattr(intent.tarefa, "value", intent.tarefa),
        )
        # O sigilo viaja em PARÂMETRO PRÓPRIO, não no `task_type`. Sobrescrever
        # o task_type levava junto o roteamento: `gateway_task` também decide a
        # cadeia de modelos (TASK_ROUTING) e se a crítica adversarial do Modo
        # Duas IAs roda (DUAS_IAS_TASK_TYPES = elaboracao_peca,auditoria_peca).
        # Uma minuta num caso de família virava task_type "familia" e saía da
        # crítica — justamente a peça de maior risco jurídico ficava sem a
        # segunda leitura. O gateway aplica `reforcar_sigilo`, então o modo aqui
        # só pode ELEVAR o piso, nunca rebaixá-lo.
        #
        # `caso.sigilo_reforcado` vem ANTES da área/rótulo — ver docstring de
        # `modo_sigilo_do_caso` para o porquê (área sozinha não tem granularidade
        # para crimes sexuais/menores desde a redução do piso do AI-019).
        modo_sigilo = modo_sigilo_do_caso(caso)
        if modo_sigilo:
            logger.info(
                "[sigilo] caso %s marcado sigilo_reforcado=True → modo "
                "LOCAL_COMPLETO no gateway; roteamento segue como '%s'",
                getattr(caso, "id", None), gateway_task,
            )
        elif rotulo_sigiloso:
            from app.services.ai.sanitization_policy import modo_para_task
            modo_sigilo = modo_para_task(rotulo_sigiloso)
            logger.info(
                "[sigilo] área sensível '%s' → modo %s no gateway; roteamento "
                "segue como '%s'", rotulo_sigiloso, modo_sigilo.value, gateway_task,
            )

        # ── Nomes do caso → pseudonimização REVERSÍVEL no gateway (LGPD 2026-07-06)
        # Passa as ENTIDADES NOMEADAS (cliente/empresa/advogado/parte contrária) ao
        # gateway: no modo EXTERNO_PSEUDONIMIZADO ele troca cada nome por um marcador
        # consistente ([CLIENTE_1]…) ANTES do provider externo e REIDRATA a resposta
        # localmente. Sem isto, um nome próprio que chegue não mascarado ao gateway
        # VAZARIA — `validar_sem_pii` (2ª barreira) detecta PII estrutural, não nomes.
        # Fail-safe: entidades_do_caso NUNCA levanta (retorna {} em qualquer falha).
        entidades: dict[str, list[str]] = {}
        if case_id and db is not None:
            from app.services.ai.entidades_caso import entidades_do_caso
            entidades = await entidades_do_caso(db, case_id)
        # Nomes avulsos informados pelo chamador (ex.: testemunha) entram como
        # parte_contraria — basta que sejam pseudonimizados; o rótulo é indiferente.
        _nomes_extra = [n for n in (params.get("nomes_proteger") or []) if (n or "").strip()]
        if _nomes_extra:
            entidades = {
                **entidades,
                "parte_contraria": list(entidades.get("parte_contraria", [])) + _nomes_extra,
            }

        resp = await ai_gateway.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_content}],
            task_type=gateway_task,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
            nivel_inteligencia=nivel_inteligencia,
            entidades=entidades or None,
            modo_sanitizacao=modo_sigilo,
            provider_override=provider_solicitado,
        )

        # 7) Validação da resposta (citações, promessas, base verificável) ────
        validacao = await response_validator.validar(
            db, resp.texto, exige_fonte=intent.exige_fonte, fontes=ctx.fontes,
        )

        # 8-9) Custo + AILog (erro de log PROPAGA — sem trilha, sem resposta) ─
        # Custo do PRÓPRIO gateway (ai_cost, ciente do provedor): cobre também
        # Maritaca — provider pago que, com o antigo "só anthropic", entraria
        # como R$ 0 na trilha de auditoria (sub-relato de gasto).
        custo = float(resp.custo_estimado_brl or 0.0)
        modelo_canonico = f"{resp.provedor}/{resp.modelo}"
        log_id = await audit_logger.registrar(
            db,
            user=user,
            tarefa=intent.tarefa,
            case_id=case_id,
            prompt_sanitizado=mensagem_sana[:8000],
            pii_removida=pii_removida,
            resposta=validacao["conteudo"],
            modelo=modelo_canonico,
            fontes=ctx.fontes,
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
            custo_estimado=custo,
        )

        # 9.5) MODO DUAS IAS (Fase 5) — crítica adversarial pós-geração ───────
        # Roda DEPOIS da validação/gate de citações da peça e do AILog.
        # Prefere provider DIFERENTE do proponente; NUNCA bloqueia a entrega
        # (falha → aviso "crítica indisponível" e o revisor HITL segue).
        critica_dict: dict | None = None
        from app.services.ai import adversarial
        if adversarial.critica_automatica_habilitada(gateway_task):
            try:
                critica = await adversarial.criticar_peca(
                    db,
                    texto_peca=validacao["conteudo"],
                    contexto_caso=ctx.texto or None,
                    task_type_origem=gateway_task,
                    provedor_origem=resp.provedor,
                    # Reaproveita as ENTIDADES NOMEADAS já montadas para a peça
                    # (cliente/parte contrária) — evita reconsultar o banco e
                    # garante que a crítica pseudonimize os mesmos nomes antes
                    # do provider externo (LGPD). Inclui `nomes_proteger` extras.
                    entidades=entidades or None,
                    # PISO DE SIGILO — sem estes dois argumentos, a crítica
                    # herdava só a política do task_type `critica_adversarial`
                    # (EXTERNO_PSEUDONIMIZADO) e, preferindo provider externo
                    # por diversidade, levava a peça + o contexto do caso
                    # (dossiê/OCR/RAG) para fora do VPS logo DEPOIS de a
                    # geração ter rodado corretamente em local. `modo_sigilo` é
                    # o piso já resolvido acima (caso.sigilo_reforcado ou área
                    # sensível); `case_id` deixa a própria `criticar_peca`
                    # reconferir o piso do caso — os demais chamadores
                    # (peca_service, raio_x, /ia-adversarial) já passam case_id
                    # e passam a herdar a mesma proteção pelo ponto único.
                    case_id=case_id,
                    modo_sanitizacao=modo_sigilo,
                )
                await adversarial.anexar_critica_ao_log(db, log_id, critica)
                critica_dict = critica.model_dump()
            except Exception as e:  # cinto e suspensório: jamais bloquear a peça
                logger.warning(
                    "[DuasIAs] Falha inesperada no pipeline de crítica "
                    "(peça entregue normalmente): %s", str(e)[:200],
                )
                critica_dict = adversarial.CriticaAdversarial(
                    disponivel=False,
                    provedor_origem=resp.provedor,
                    task_type_origem=gateway_task,
                    aviso=adversarial.AVISO_INDISPONIVEL,
                ).model_dump()

        # 10) Resposta padronizada + carimbo HITL ─────────────────────────────
        resultado = {
            "conteudo": validacao["conteudo"],
            # Compatibilidade: "agente" continua sendo o especialista executor.
            "agente": agente.nome,
            "agente_coordenador": coordenador.nome,
            "agente_especialista": agente.nome,
            "skill_pipeline": skill_pipeline,
            "skills_nativas": list(native_plan.skill_names),
            "ramo_juridico": native_plan.legal_area,
            "modulo_ejc": native_plan.module_key,
            "task_type": task_type,
            "domain": domain,
            "tarefa": intent.tarefa.value,
            # Rastreabilidade do prompt (dívida 5.3): impressão digital do texto
            # que foi injetado como `system`. Sem isso, um erro jurídico na saída
            # não é rastreável até a instrução que o produziu.
            "prompt_key": agente.prompt_key,
            "prompt_versao": prompt_versao(system_prompt),
            "modelo": modelo_canonico,
            "provider": resp.provedor,
            "fallback_ativado": bool(getattr(resp, "fallback_ativado", False)),
            "fallback_motivo": getattr(resp, "fallback_motivo", None),
            "fontes": [
                {"titulo": f.get("titulo"), "categoria": f.get("categoria"),
                 "fonte": f.get("fonte")} for f in ctx.fontes
            ],
            "citacoes": validacao["citacoes"],
            "alertas": validacao["alertas"] + ctx.avisos,
            "sem_base_verificavel": validacao["sem_base_verificavel"],
            "revisao_obrigatoria": validacao["revisao_obrigatoria"],
            "custo_estimado_brl": custo,
            "tokens_input": resp.input_tokens,
            "tokens_output": resp.output_tokens,
            "log_id": log_id,
            # Modo Duas IAs: None quando desligado/task inelegível.
            "critica_adversarial": critica_dict,
        }
        return hitl_policy.aplicar(resultado)


orchestrator = SingleAICoreOrchestrator()


async def run_ai_task(**kwargs) -> dict:
    """Atalho para wrappers legados: SingleAICoreOrchestrator.run(**kwargs)."""
    return await orchestrator.run(**kwargs)
