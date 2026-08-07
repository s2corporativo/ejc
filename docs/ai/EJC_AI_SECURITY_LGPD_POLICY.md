# EJC — Política de Segurança da IA (LGPD / OAB)

Data: 2026-07-04.

## 1. Sanitização de PII — `services/sanitizer.py`

`sanitizar_pii(texto, nomes_proteger)` (sanitizer.py:42) substitui PII por placeholders. Padrões (sanitizer.py:13-39, ordem: mais específico primeiro):

| Padrão | Placeholder | Observação |
|---|---|---|
| CPF (com/sem pontuação) | `[CPF]` | |
| CNPJ | `[CNPJ]` | |
| Número de processo CNJ | `[PROCESSO]` | 0000000-00.0000.0.00.0000 |
| RG (padrão MG/SP, prefixo "RG") | `RG [RG]` | |
| E-mail | `[EMAIL]` | |
| Telefone BR (com/sem +55/DDD) | `[TELEFONE]` | |
| CEP | `[CEP]` | |
| Cartão de crédito (16 dígitos) | `[CARTAO]` | |
| Chave PIX aleatória (UUID) | `[CHAVE_PIX]` | |
| Data de nascimento contextual | `[DATA_NASC]` | gatilho "nascido em"/"data de nascimento" (sanitizer.py:35-39) |
| Nomes das partes (`nomes_proteger`) | `[PARTE_n]` | case-insensitive; boundary cobre "S.A.", "Ltda." (sanitizer.py:64-77) |

`validar_sem_pii` (sanitizer.py:82) é a checagem residual (CPF/CNPJ/PROCESSO/RG/EMAIL/TELEFONE/CEP) — retorna os TIPOS encontrados, nunca os valores.

## 2. Guarda com abort — `services/ai_guard.py`

`sanitizar_ou_abortar` (ai_guard.py:18) = sanitizar + segunda barreira com **HTTP 422** se sobrar PII estrutural ("não deixa passar 'quase limpo'"). Usada pelo orchestrator em TODO input (orchestrator.py:110-112). `registrar_ai_log` (ai_guard.py:38) é o caminho canônico de AILog: erro de gravação **propaga** — IA sem trilha de auditoria deve falhar, não seguir.

## 3. O que NUNCA vai a provider externo (Anthropic/Groq)

- **PII**: dupla barreira — policy no núcleo (provider_policy.py:95-110) remove externos da cadeia; gateway re-sanitiza cada mensagem e pula o externo com residual (ai_gateway.py:192-207, 333-347). Sem alternativa local → erro seguro sem ecoar conteúdo (ai_gateway.py:242-247).
- **Segredos/.env/tokens/chaves**: nunca entram em prompt, log ou resposta (regra do núcleo, orchestrator.py:18). Contexto técnico dos agentes de sistema é só o GRAPH_REPORT truncado (skill_registry.py:90-97) e os prompts técnicos proíbem segredos "nem parcialmente, nem mascarados" (system_prompts/__init__.py:21-29). `/ai/core/status` expõe só booleans (ai_core.py:179-199); erro do provider Anthropic sai como tipo+status, sem corpo/stack/chave (anthropic_provider.py:90-97).
- **Documentos de cofre**: `context_builder` só usa `ocr_text` com confidencialidade `normal`/`interno`; `restrito`/`sigiloso` NUNCA vira prompt — registra aviso "conteúdo NÃO enviado à IA por política de sigilo" (context_builder.py:62-85).
- **Número CNJ do processo**: omitido de propósito no contexto processual (context_builder.py:102-103).

## 4. AILog só com prompt sanitizado

`models/ai_log.py:56`: `prompt_sanitizado` é o ÚNICO prompt persistido (truncado a 8000 chars, orchestrator.py:161), com flag `pii_removida`. Fontes RAG gravadas como títulos/categorias, sem conteúdo (audit_logger.py:33-42).

## 5. Sigilo profissional e isolamento

- **Ownership por caso (ABAC)**: `verificar_acesso_caso` antes de montar qualquer contexto (orchestrator.py:94-96); dossiê montado pelo backend sob RBAC/ownership — o frontend envia apenas IDs (routers/ai_core.py:7-9).
- **RBAC por agente**: `roles_permitidos` (agentes técnicos restritos a superadmin/admin/socio, agent_registry.py:14, 133-153); violação → 403 (orchestrator.py:92-93).
- **`cliente_externo` bloqueado em dupla camada**: no router (`_staff_only`, ai_core.py:28-31) e revalidado no orchestrator (orchestrator.py:90-91). O portal do cliente não consome nenhum endpoint de IA.
- Históricos HITL filtram por dono/nível de role (ex.: ia_defensiva.py:110-112, 146-151).

## 6. Vedações éticas (OAB) na resposta

`response_validator.py`:
- **Promessa de resultado** (Código de Ética, art. 34): regexes (`_RE_PROMESSAS`, linhas 15-21) detectam "garantia de êxito", "100% de chance" etc.; geram ALERTA + `revisao_obrigatoria=True` — o texto nunca é reescrito, para não esconder o problema do revisor (linhas 76-84).
- **"Sem base verificável"**: tarefa que exige fonte sem NENHUMA fonte RAG nem citação confirmada → resposta prefixada com `SEM BASE VERIFICÁVEL` + revisão obrigatória (linhas 86-92).
- **Citações**: conferidas contra a base oficial por lookup exato (`citation_check.verificar_citacoes`, citation_check.py:64) — não confirmadas viram alerta de verificação manual obrigatória.
- Os próprios system prompts reforçam: nunca prometer êxito, citar fonte de toda afirmação jurídica, declarar "sem base verificável" (system_prompts/__init__.py:12-19).

## 7. Erros sem vazamento

- Provider Anthropic: `RuntimeError` curto (tipo + HTTP status), `from None` corta o stack original (anthropic_provider.py:90-97).
- Gateway: loga só os primeiros 200 chars do erro e os TIPOS de PII, nunca o conteúdo (ai_gateway.py:195, 203-207, 236-240).
- Bloqueios ao usuário: mensagens fixas e seguras (ai_guard.py:29-34; provider_policy.py:131-135) — instruem a remover dados pessoais, sem ecoá-los.

## 8. Resumo das flags de governança (core/config.py:83-92)

`AI_EXTERNAL_PROVIDERS_ALLOWED` (desliga todos os externos — sem provider local no EJC, IA fica indisponível), `AI_REQUIRE_SANITIZATION_FOR_EXTERNAL` (barreiras obrigatórias), `AI_REQUIRE_HITL` (revisão formal), `AI_PROVIDER_PRIORITY` (ordem). Em produção todas permanecem nos defaults seguros (`true`/`anthropic,maritaca,groq`).
