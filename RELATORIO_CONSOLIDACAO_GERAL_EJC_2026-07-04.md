# Relatório de Consolidação Geral do EJC — 2026-07-04

Branch: `claude/ejc-consolidation-audit-ifdkdd`
Objetivo: unificar o trabalho pendente espalhado entre os dois computadores (9 PRs
abertos + branches sem PR), verificar bugs/rotas/erros, e mapear o wishlist da
plataforma jurídica operacional contra o estado real do código.

---

## 1. O que foi consolidado neste branch

| Origem | Conteúdo | Situação |
|---|---|---|
| PR #21 (`graphify-activation-1ktu02`) | 22 correções da auditoria Graphify (IDOR no Drive, CPF/CNPJ exposto, 9 rotas 404 `/v1`, race na numeração, jurimetria corrompida), redesign SaaS (indigo/violet + Inter), 11 features por domínio, guarda de contrato HTTP frontend↔backend, migration 067 | ✅ Integrado sem conflitos |
| PR #26 (`ejc-legal-ai-architecture-s2ctes`) | Fix do Deploy VPS: chave SSH ou senha + probe de conexão com diagnóstico | ✅ Integrado |
| Branch `ejc-design-overhaul-2t4pb1` (sem PR) | Compose de produção (pgvector, migrations+seed no boot), script deploy 1 comando, suíte verde em Postgres real | ✅ Integrado (conflito em test_smoke resolvido a favor do head 067) |
| PR #25 (`anthropic-api-key-integration`) | Cérebro Único no AI Gateway, Opus 4.8 como modelo complexo, ANTHROPIC_EFFORT, correção do bug de `temperature` (HTTP 400 nos modelos modernos), prompt caching, preços corrigidos | ✅ Integrado — conflitos resolvidos unindo endurecimento do Núcleo Único (main) + superfície moderna da API (PR #25); degradação graciosa de provider forçado inelegível incorporada |
| PR #18 (`ejc-native-ai-opinion`) | Documento Único de Anexos (capa+índice+separadores+merge de PDFs), razões jurídicas com raciocínio adversarial, endpoints `/api/anexos` | ✅ Integrado — feature de anexos completa; mudanças duplicadas de gateway/provider descartadas em favor da versão consolidada; teste do gateway reescrito para o contrato atual |
| PR #19 (`install-technical-skills`) | 32 skills técnicas em `.claude/skills/` | ✅ Integrado |
| PR #20 (`agents-available-skills`) | 6 subagentes (code-reviewer, verifier, simplifier, app-runner, researcher, ci-triage) + orquestrador | ✅ Integrado |
| PR #16 (`ejc-system-mapping`) | Relatório da análise multi-agente do grafo | ✅ Integrado |

### Pulados de propósito (decidir depois)

| Origem | Motivo |
|---|---|
| PR #15 (remove módulo de licitação) | **Contradiz o pedido atual** de ampliar contratos públicos/licitações. Recomendo FECHAR o PR #15 e manter o módulo, evoluindo-o conforme o roadmap (seção 4). |
| PR #9 (instala graphify) | Superado pelo PR #14 já mesclado na main (graphify automático + agentes). Recomendo fechar. |
| Branch `inspiring-shannon-wwvnog` | Contém apenas um `.zip` de upload manual (snapshot antigo do backend, 52 commits atrás). O fix de scheduler citado já existe na main atual. Recomendo apagar o branch. |

### Correções e melhorias adicionais feitas nesta consolidação

- `_resolver_cadeia` (ai_gateway): provider forçado sem chave/desabilitado agora cai
  na cadeia automática com warning, em vez de tentar um provider inelegível.
- `anthropic_provider`: teto de custo `ANTHROPIC_MAX_TOKENS` respeitado também no
  caminho moderno (piso 8192 quando thinking ativo), erros seguros mantidos.
- `config.py`: bloco Anthropic duplicado removido (a segunda declaração sobrescreveria
  a primeira no pydantic); `ANTHROPIC_MODEL_COMPLEXO=claude-opus-4-8` + `ANTHROPIC_EFFORT=high`.
- `GET /cases` e `GET /cases/stats`: novo filtro `?advogado_id=` — sócio+ vê os
  processos de um advogado específico (a visibilidade RBAC/LGPD continua aplicada antes).
- UI: aba **Provas** no detalhe do caso, ação **Excluir caso** (soft delete com motivo,
  reversível pela lixeira) e **seletor de advogado** na lista de casos.
- Logo em grande formato: ampliada no login (h-28/360px no hero, h-20 no mobile) e na
  sidebar (h-14/220px).

---

## 2. Verificação (build, testes, segurança)

_(preenchido ao final da rodada de verificação)_

---

## 3. Wishlist × Estado real do sistema

Legenda: ✅ existe e integrado · 🟡 parcial · ⭕ não iniciado (roadmap)

### IA central
| Item | Status | Onde |
|---|---|---|
| Cérebro Único / AI Gateway central | ✅ | `services/ai_gateway.py` + `services/ai/core/orchestrator` (PR #23/#25); `core/ai_brain.py` virou shim |
| Modo Duas IAs (análise + contra-análise) | ✅ | `AIGateway.modo_duas_ias` |
| Roteamento multi-modelo por tarefa | ✅ | `TASK_ROUTING` (8 tipos de tarefa, cadeia ollama→anthropic→groq) |
| Claude/Anthropic como provider opcional | ✅ | `providers/anthropic_provider.py`, Opus 4.8 p/ tarefas complexas, fallback sem chave |
| IA contextual por caso/processo | ✅ | gates de ownership + RAG por caso |
| Cliente 360º | 🟡 | dossiê do cliente existe; visão consolidada 360º é evolução |
| Trilha de auditoria da IA | ✅ | `AILog` (quem, modelo, custo, HITL) + feedback 👍/👎 (migration 066) |
| HITL — saída de IA como rascunho | ✅ | `AI_REQUIRE_HITL=true` na policy central |
| Anti-alucinação / verificador de citações | 🟡 | `legal_base` + instruções anti-invenção + validador nos anexos; verificador dedicado de jurisprudência (nº processo/tribunal/data) é evolução |

### Produção jurídica
| Item | Status | Onde |
|---|---|---|
| Gerador de peças | ✅ | `peca_service` + `Pecas.tsx` + PecaGeneratorModal |
| Geradores específicos (contestação, apelação, contrarrazões, réplica, agravo) | 🟡 | gerador genérico com tipos; presets dedicados por peça são evolução da UI |
| Documento Único de Anexos + razões jurídicas | ✅ | `/api/anexos` (preview/gerar/razoes) — PR #18 |
| Auditor de peças / auditoria pré-protocolo | 🟡 | task_type `auditoria_peca` roteada; checklist pré-protocolo estruturado é roadmap |
| Banco de Teses | ✅ | teses_v4 + aba Teses/Teses sugeridas no caso |
| Biblioteca de modelos | 🟡 | modelos internos existem; **importar modelos do Jusbrasil/STJ exige atenção a licenciamento/direitos autorais — não automatizado de propósito**; STJ Jurisprudência em Teses/Informativos são públicos e podem alimentar o RAG (roadmap) |
| Escrita assistida | ✅ | assistente de IA + níveis de inteligência |
| RAG jurídico | ✅ | pgvector + `buscar_contexto_rag` |
| OCR + extração estruturada + classificação de documento | ✅/🟡 | upload+extração+classificação por IA (PR #21); extração de TODOS os campos com preenchimento automático nos módulos abas/processos é evolução em andamento |
| GED / Data Room | ✅ | documents + `DataRoom.tsx` |

### Jurimetria & estratégia
| Item | Status |
|---|---|
| Jurimetria preditiva | ✅ (`case_intel`, vocabulário de resultados corrigido no PR #21) |
| Motor estratégico (cenários) | ✅ (`motor_estrategico`) |
| Minerador de sucesso | ✅ (`minerador_sucesso`) |
| Matriz probabilidade × impacto | ✅ (aba Índice de Risco/Score) |
| Precificação inteligente / honorários | ✅ (honorários + centro de custos por processo) |

### Sala de Guerra & Diplomacia
| Item | Status |
|---|---|
| IA Sentinela (processos parados 60d / clientes sem reporte 30d) | ✅ (`IASentinela` + scheduler) |
| War Room (simular parte contrária, nulidades) | ✅ (`war_room` + `SalaDeGuerra.tsx` + aba IA Defensiva) |
| Visual Law PDF | ✅ (gerador de PDF/relatórios; weasyprint nos anexos) |
| Diplomacia Digital (ponto de equilíbrio, VPL c/ Selic, dossiê de pressão) | ✅ (`diplomacia_v3` + `calcular_acordo`) |
| Análise de sentimento de magistrados / tom da petição | 🟡 (base pronta no gateway; modelo dedicado é roadmap) |

### Inteligência externa
| Item | Status |
|---|---|
| DataJud/DJEN (movimentações + prazo assistido) | ✅ (migration 065 + intimações) |
| Radar de Poder / monitor legislativo / DOU / STF-STJ | 🟡 (`intelligence_v3` cobre parte; monitores dedicados são roadmap) |

### Gestão do escritório
Dashboard executivo ✅ · CRM leads ✅ · Clientes ✅ (com criptografia de PII/LGPD) ·
Casos/Processos ✅ · Agenda ✅ · Prazos/Tarefas ✅ · Kanban ✅ · Workflow/SLA ✅ ·
Financeiro ✅ · Centro de custos ✅ · Relatórios ✅ · Portal do cliente ✅.

### Pedidos pontuais desta rodada
| Pedido | Status |
|---|---|
| Aba Provas dentro do caso | ✅ adicionada |
| Excluir caso | ✅ backend já tinha (soft delete + lixeira); botão adicionado na UI |
| Processos separados por advogado | ✅ visibilidade RBAC já limitava advogado comum aos seus casos; agora sócio+ tem filtro `advogado_id` na lista e no dashboard |
| Checklist na aba casos, personalizado por ramo, IA identifica | ✅ aba Checklists com geração por IA por legislação/gatilho |
| Remover markdown bruto das respostas de IA | ✅ `Markdown.tsx` renderiza |
| Logo aparente e grande formato | ✅ ampliada (login + sidebar) |
| Design SaaS moderno | ✅ redesign do PR #21 (tokens, Inter, indigo/violet) consolidado |

### Ramos do direito (verticais)
| Módulo | Status |
|---|---|
| Guias operacionais por ramo (começando pelo Empresarial) | ✅ existem (`RamoBase` + guias); manter e aprofundar |
| Bancário inteligente | 🟡 análise bancária + minuta revisional (PR #21); CET/BACEN/superendividamento roadmap |
| Tributário (XML, PIS/COFINS, PER/DCOMP…) | ⭕ roadmap |
| Licitações/contratos públicos (atas, empenhos, sanções, reequilíbrio) | 🟡 módulo de licitação existe e **não será removido** (fechar PR #15); ampliação roadmap |
| Ambiental / LGPD / Societário 360º | 🟡 societário existe (alertas de vencimento); ambiental e LGPD-como-produto roadmap |

---

## 4. Roadmap recomendado (ordem de implantação)

Mantida a recomendação registrada: **estabilizar → essencial → premium → verticais.**

1. **Agora (este branch)**: consolidação + verificação verde + deploy VPS com o
   workflow corrigido (#26) e compose de produção.
2. **Curto prazo**: verificador dedicado de jurisprudência (nº/tribunal/órgão/data
   verificáveis), presets de peças por tipo (contestação/apelação/contrarrazões/
   réplica/agravo) sobre o gerador atual, ingestão dos materiais públicos do STJ
   (Jurisprudência em Teses, Informativos) no RAG.
3. **Médio prazo**: Cliente 360º consolidado, análise de sentimento de magistrados,
   Radar de Poder (monitor legislativo/DOU/STF-STJ), extração estruturada com
   preenchimento automático completo no intake.
4. **Verticais**: Tributário IA (XML fiscal) → Licitações ampliado → Bancário
   completo → Ambiental → LGPD como produto.

## 5. Ações pendentes fora do código

- **Fechar PRs #9, #15, #16, #18, #19, #20, #25, #26** após o merge deste branch
  (o conteúdo deles está todo aqui, exceto #15/#9 que devem ser fechados sem merge).
- **Branch `inspiring-shannon-wwvnog`**: apagar (só zip antigo).
- **Secrets do deploy**: configurar `VPS_SSH_KEY` (ou `VPS_PASSWORD`) + `VPS_HOST`/
  `VPS_USER` no GitHub para o workflow Deploy VPS funcionar.
- **`ANTHROPIC_API_KEY`** no `.env` de produção para ativar o Claude na cadeia
  (sem ela o sistema segue em Groq/Ollama normalmente).
- Custo: tarefas complexas passam a usar Opus 4.8 ($5/$25 por 1M tokens, com prompt
  caching ≈10% em leituras repetidas). Para reduzir: `ANTHROPIC_MODEL_COMPLEXO=claude-sonnet-5`.
