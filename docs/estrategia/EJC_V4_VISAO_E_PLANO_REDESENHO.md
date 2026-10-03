# EJC v4 — Visão-alvo e Plano de Redesenho

> **Natureza:** documento de visão e plano (não é procedimento operacional nem
> relatório de status). Status vivo continua exclusivamente em
> `docs/PLANO_MESTRE_STATUS.md`; governança canônica em `docs/GOVERNANCA_IA.md`.
> Em divergência, os documentos canônicos prevalecem sobre este.
>
> **Base de evidência:** `main@4c03f86` (2026-10-03). Números do §2 foram medidos
> no repositório nesta data; afirmações sobre o EJC v3 citam o arquivo de origem.
>
> **Escopo:** como seria o EJC "ideal" — um ERP jurídico inteligente, com RAG de
> conhecimento jurídico amplo e IA de alta confiabilidade — **construído a partir
> do EJC atual**, e o roteiro para chegar lá.

---

## Sumário

0. [Sumário executivo](#0-sumário-executivo)
1. [Premissas e correções de premissa](#1-premissas-e-correções-de-premissa)
2. [Diagnóstico do EJC v3 (ponto de partida)](#2-diagnóstico-do-ejc-v3-ponto-de-partida)
3. [Visão do EJC v4 — princípios de produto](#3-visão-do-ejc-v4--princípios-de-produto)
4. [Arquitetura-alvo](#4-arquitetura-alvo)
5. [Módulos do ERP jurídico (EJC Core)](#5-módulos-do-erp-jurídico-ejc-core)
6. [RAG jurídico amplo — "Corpus Juris EJC"](#6-rag-jurídico-amplo--corpus-juris-ejc)
7. [Núcleo de IA — definição operacional de "IA perfeita"](#7-núcleo-de-ia--definição-operacional-de-ia-perfeita)
8. [Redesenho de experiência (UX/UI)](#8-redesenho-de-experiência-uxui)
9. [Modelo de dados e conceitos canônicos](#9-modelo-de-dados-e-conceitos-canônicos)
10. [Segurança, LGPD e ética profissional](#10-segurança-lgpd-e-ética-profissional)
11. [Infraestrutura, operação e continuidade](#11-infraestrutura-operação-e-continuidade)
12. [Roteiro de execução em ondas](#12-roteiro-de-execução-em-ondas)
13. [Indicadores e critérios de aceite](#13-indicadores-e-critérios-de-aceite)
14. [Riscos e mitigação](#14-riscos-e-mitigação)
15. [Decisões que dependem do titular](#15-decisões-que-dependem-do-titular)
16. [O que não fazer](#16-o-que-não-fazer)
17. [Anexo — rastreabilidade](#17-anexo--rastreabilidade)

---

## 0. Sumário executivo

**Tese central.** O EJC "perfeito" não é um sistema novo. O v3 já contém os
componentes difíceis — orquestrador de caso com HITL, núcleo único de IA,
gateway com barreira de PII, citation gate, RAG com pgvector e proveniência,
captura DJEN/DataJud, motor de prazos, RBAC/ownership e trilha de auditoria.
O que falta é **consolidação, ligação e confiabilidade mensurável**. Uma
reescrita do zero destruiria esse ativo e reabriria riscos já fechados
(5 IDORs, PII para provedor externo, vigência inferida).

**Recomendação.** Evolução incremental por estrangulamento (*strangler pattern*):
o v4 nasce dentro do v3, módulo a módulo, atrás de flags `*_ENABLED`, com
paridade comprovada antes de cada remoção.

**O v4 em cinco frases:**

1. **O caso é o centro.** Tudo (prazo, peça, documento, honorário, conversa com
   o cliente, pesquisa) existe *em relação a um caso*, e o caso abre mostrando
   a próxima ação.
2. **Uma IA, muitas competências.** Um único orquestrador, agentes como
   metadado, skills versionadas, roteamento por risco e por sensibilidade de
   dado — nunca IA paralela por tela.
3. **Nenhuma afirmação jurídica sem fonte verificável e vigência conferida.**
   O que não tem base aparece como lacuna, nunca como conclusão.
4. **O advogado decide; a IA prepara.** Todo ato jurídico (protocolo, envio ao
   cliente, prazo, aprovação de tese) é humano, registrado e reversível.
5. **Menos superfície, mais profundidade.** De ~34 áreas de navegação para
   10–12 módulos Core; de 26 abas no caso para 5 seções.

**Critério de lançamento (mantido do v3):** um advogado leva um caso real do
início ao protocolo dentro do sistema e acha **mais fácil que fazer fora dele**.

---

## 1. Premissas e correções de premissa

O pedido usa o termo "IA perfeita". Tecnicamente, isso não existe e não pode
ser prometido: modelos de linguagem erram, inclusive com fonte disponível.
Prometer "perfeição" num produto jurídico gera dois riscos concretos:

- **Risco ético-disciplinar:** delegar juízo profissional a sistema que não
  responde por ele (Lei 8.906/1994 — EOAB; Código de Ética e Disciplina da OAB).
- **Risco de responsabilidade civil:** peça com citação inexistente ou norma
  revogada é erro do advogado, não do software.

**Correção adotada neste plano:** "IA perfeita" passa a significar **IA com
desempenho medido, limites declarados e falha segura** — metas numéricas no
§13, verificadas por bancada de avaliação (`app/eval/legal_bench.py`), e
comportamento *fail-closed* quando a meta não é atingida.

Demais premissas (todas herdadas de decisões vigentes do repositório):

| # | Premissa | Fonte |
|---|---|---|
| P1 | Single-tenant (um escritório); isolamento por `client_id`/`case_id` + ownership | `docs/PLANO_SIMPLIFICACAO_EJC.md` §"Correção de premissa" |
| P2 | EJC Core × Verticais: DPT360, Áreas de Atuação, Ambiental e Tributário especializados saem progressivamente do Core | `docs/decisoes/ADR_EJC_CORE_VERTICAIS_2026-09-25.md` |
| P3 | Toda chamada de IA passa por `services/ai_gateway.py` / `SingleAICoreOrchestrator` | `docs/ai/EJC_SINGLE_AI_CORE_ARCHITECTURE.md` |
| P4 | Fonte oficial ≠ vigência conferida | `docs/decisoes/ADR_RAG_VIGENCIA_E_FONTE_OFICIAL_2026-09-04.md` |
| P5 | Flags novas seguem sufixo `_ENABLED`, default OFF para externo/incompleto | `docs/PLANO_SIMPLIFICACAO_EJC.md` §"Padrão de feature flag" |
| P6 | Local-first para dado pessoal (Ollama); provedor externo só com sanitização | `docs/GOVERNANCA_IA_ADDENDUM_LOCAL_FIRST.md`, `services/ai/sanitization_policy.py` |
| P7 | Deploy só pela esteira (`scripts/deploy_manual.sh` enquanto o Actions estiver indisponível) | `CLAUDE.md` regra 9, `RUNBOOK_DEPLOY_MANUAL.md` |
| P8 | Princípio "conectar, não criar": nenhuma superfície paralela à existente | `docs/PLANO_SIMPLIFICACAO_EJC.md` |

---

## 2. Diagnóstico do EJC v3 (ponto de partida)

### 2.1 Dimensão medida (2026-10-03, `main@4c03f86`)

| Indicador | Valor | Como foi medido |
|---|---|---|
| Arquivos de router (`backend/app/routers`) | 163 | `ls \| wc -l` |
| Arquivos de service (`backend/app/services`) | 219 | `ls \| wc -l` |
| Arquivos de model (`backend/app/models`) | 73 | `ls \| wc -l` |
| Páginas React (`frontend/src/pages`) | 123 | `ls \| wc -l` |
| Migrations Alembic | 161 arquivos, última numerada `170_djen_remove_unicidade_global` | `ls backend/alembic/versions` |
| Arquivos em `backend/tests` | 745 | `ls \| wc -l` |
| Ingestores oficiais | 8 (Câmara, DJEN, LexML, Planalto, Senado, STJ, TJMG + init) | `backend/app/services/ingestors/` |
| Embedding | `intfloat/multilingual-e5-large`, 1024d, HNSW | `RUNBOOK_MIGRACAO_EMBEDDING_1024.md` |
| Agentes / skills do núcleo de IA | 14 agentes, 28 skills (doc de 2026-07-04; conferir no registry antes de citar) | `docs/ai/EJC_SINGLE_AI_CORE_ARCHITECTURE.md` |

> A contagem de arquivos não é inventário de rotas; para rotas, usar
> `backend/scripts/ledger_rotas.py`.

### 2.2 O que funciona e deve ser preservado

| Ativo | Onde vive | Por que é valioso |
|---|---|---|
| Orquestrador do caso (máquina de 10 estados, nunca aprova sozinho) | `services/legal_case_orchestrator.py` | É o "advogado guia" — só está mal exposto |
| Núcleo único de IA (classificação → RBAC → contexto → sanitização → política → gateway → validação → auditoria → HITL) | `services/ai/core/orchestrator.py` | Pipeline correto; base do v4 |
| Barreira final de PII para provedor externo | `ai_gateway.py`, `sanitization_policy.py` | Requisito LGPD já cumprido |
| Citation gate e verificador de jurisprudência (4 estados) | `citation_gate.py`, `verificador_jurisprudencia.py` | Anti-alucinação |
| Proveniência documental (`KnowledgeDoc`/`KnowledgeChunk`) | `models/rag.py` | Rastreabilidade de fonte |
| Legal Brain (estado probatório, issue engine, research loop, validade de precedente) | `services/legal_brain/` | Fundação do raciocínio jurídico estruturado |
| Saúde de ingestão por **resultado** | `services/ingestao_saude.py` | Evita "job verde, dado vazio" |
| Ownership de caso | `core/ownership.py::verificar_acesso_caso` | Sigilo entre clientes |
| Design system canônico | `docs/DESIGN_SYSTEM_EJC.md`, `styles/ejc-tokens.css` | Identidade já decidida |

### 2.3 O que dói (causas estruturais, não sintomas)

| # | Problema | Evidência | Consequência |
|---|---|---|---|
| D1 | **Superfície excessiva** — módulos paralelos para o mesmo conceito (`sala_de_guerra` → `_v3` → `/sala-analise`; `teses` → `teses_v4`; `data_room` → `_v4`) | `docs/PLANO_SIMPLIFICACAO_EJC.md` | Navegação confusa, manutenção duplicada |
| D2 | **Caso com 26 abas**; orquestrador escondido como aba 2 | `PLANO_SIMPLIFICACAO_EJC.md` achados 1–2 | O advogado não acha a próxima ação |
| D3 | **Representações concorrentes** de status, saúde do caso, tese e jornada (Classes A–D) | `docs/estrategia/PLANO_MESTRE_EJC.md` F2 | Números que discordam entre telas |
| D4 | **Gravação não transacional** em fluxos que tocam duas tabelas | `PLANO_MESTRE_STATUS.md` V2-3.5 | Estados órfãos |
| D5 | **Quatro superfícies de IA** (`/ia`, `/assistente-ia`, `/inteligencia`, `/ferramentas-ia`) | `docs/redesign-relatorio-final.md` §9 | Usuário não sabe onde perguntar |
| D6 | **Corpus RAG com vigência majoritariamente não verificada** e histórico de chunks sem embedding | ADR de vigência; `PLANO_MESTRE_STATUS.md` V2-2.2 | Pesquisa fraca ou bloqueada |
| D7 | **Esteira de CI indisponível** (Actions da conta) | `CLAUDE.md` §Verificação | Verificação depende de disciplina local |
| D8 | **Fila não persistente** em parte do processamento (`BackgroundTasks`) | `redesign-relatorio-final.md` §8.4 | Perda de tarefa em restart |
| D9 | **Premissa de worker único** (rate-limit em memória, APScheduler) | `CLAUDE.md` §Arquitetura | Teto de escala e ponto único de falha |

---

## 3. Visão do EJC v4 — princípios de produto

| # | Princípio | Regra verificável |
|---|---|---|
| PR1 | **Caso-cêntrico** | Toda entidade operacional tem `case_id` ou justificativa documentada para não ter |
| PR2 | **Próxima ação primeiro** | Abrir caso → primeira dobra mostra `proximo_passo()` com botões |
| PR3 | **Uma IA** | Zero chamadas a provider fora de `providers/` (grep-test no gate) |
| PR4 | **Fonte ou lacuna** | Resposta jurídica sem fonte rastreável sai prefixada "SEM BASE VERIFICÁVEL" e não pode ser exportada como peça |
| PR5 | **Direito na data certa** | Toda consulta normativa carrega data de referência (fato ou atual); vigência resolvida para essa data |
| PR6 | **Humano no ato** | Ato com efeito externo exige ação humana identificada + AILog/AuditLog |
| PR7 | **Local por padrão** | Dado pessoal identificado só processa em modelo local; externo recebe texto pseudonimizado |
| PR8 | **Verdade única** | Cada conceito tem uma fonte canônica + teste de paridade + grep-test contra writer paralelo |
| PR9 | **Medido, não declarado** | Qualidade da IA expressa em métricas de bancada, publicadas no painel de governança |
| PR10 | **Simples por padrão, profundo sob demanda** | Funções avançadas atrás de "mais", não na navegação primária |

---

## 4. Arquitetura-alvo

### 4.1 Estilo: monólito modular com fronteiras explícitas

Microserviços **não** são recomendados: um escritório, uma VPS, equipe reduzida.
O ganho de isolamento não paga o custo operacional. O alvo é um **monólito
modular** em que cada módulo Core tem pacote próprio, contrato público e
proibição testada de importar internals de outro módulo.

```
┌──────────────────────────────────────────────────────────────────────┐
│ FRONTEND (React 19 + TS + Vite)                                      │
│  AppShell · moduleRegistry (RBAC por rota) · Command Palette         │
│  Workspace do Caso (5 seções) · Painel IA lateral único              │
└───────────────▲──────────────────────────────────────────────────────┘
                │ /api/v1 (REST + SSE para streaming de IA)
┌───────────────┴──────────────────────────────────────────────────────┐
│ API (FastAPI) — routers finos, AuthMiddleware + RBAC + ownership     │
├──────────────────────────────────────────────────────────────────────┤
│ MÓDULOS CORE (app/modules/<nome>/{api,service,domain,repo,events})   │
│  entrada · clientes · casos · processos · prazos · documentos        │
│  producao · conhecimento · financeiro · portal · gestao · admin      │
├──────────────────────────────────────────────────────────────────────┤
│ PLATAFORMA (compartilhada)                                           │
│  identidade/RBAC · auditoria · eventos (outbox) · arquivos/GED       │
│  notificações · busca (híbrida) · integrações · jobs (Celery)        │
├──────────────────────────────────────────────────────────────────────┤
│ NÚCLEO DE IA (services/ai/core) — único                              │
│  intent → policy → contexto/RAG → sanitização → gateway → validação  │
│  → citation gate → HITL → AILog        Legal Brain · Legal Bench     │
├──────────────────────────────────────────────────────────────────────┤
│ DADOS: PostgreSQL 16 + pgvector + tsvector(pt) · Redis · Volumes     │
│ MODELOS: Ollama (local, PII) · Anthropic/Groq (externo, sanitizado)  │
└──────────────────────────────────────────────────────────────────────┘
        VERTICAIS (fora do Core, via contrato): DPT360, Ambiental,
        Tributário — consomem eventos/APIs do Core, nunca o contrário.
```

### 4.2 Decisões de arquitetura propostas

| ID | Decisão | Motivo | Substitui/estende |
|---|---|---|---|
| A1 | Pacote por módulo em `app/modules/` (a pasta já existe) com teste de fronteira (import-linter ou grep-test) | Conter D1/D3 | Camadas horizontais atuais (`routers/`, `services/`) migram gradualmente |
| A2 | **Outbox transacional** (`eventos_dominio`) gravado na mesma transação do agregado | Resolver D4 e alimentar jobs/notificações/IA sem acoplamento | Chamadas diretas entre services |
| A3 | **Celery + Redis** como executor único de trabalho assíncrono e agendado (Celery beat) | D8 e D9 | `BackgroundTasks` e APScheduler (migração por job, com paridade) |
| A4 | Rate-limit e locks em Redis | Remover premissa de worker único | Rate-limit em memória |
| A5 | **SSE** para streaming de respostas de IA longas | UX de geração de peças | Polling/espera bloqueante |
| A6 | Busca híbrida única (vetor + `tsvector` português + reranker) exposta por um serviço de busca | D6 e busca global | Buscas por módulo |
| A7 | Verticais só consomem o Core por API/evento | ADR Core × Verticais, Onda 2 | Imports diretos de models verticais |

Cada decisão A1–A7 vira ADR própria em `docs/decisoes/` antes do primeiro PR
que a implementa.

---

## 5. Módulos do ERP jurídico (EJC Core)

Doze módulos, alinhados à lista canônica da ADR Core × Verticais. Para cada um:
função ERP, inteligência embarcada e limite de automação.

### M1 — Entrada Única (intake) e conflito de interesses

- **ERP:** recepção de demanda (formulário, WhatsApp, e-mail, portal), triagem,
  checagem de conflito, proposta de honorários, conversão em cliente + caso.
- **IA:** classificação de área e urgência; extração estruturada dos fatos com
  `{valor, trecho_origem, confianca}` (padrão já existente em `campos_v2`);
  sugestão de teses **somente do banco curado**; checklist documental por tipo
  de demanda.
- **Limite:** aceitar cliente, declarar ausência de conflito e enviar proposta
  são atos humanos.

### M2 — Clientes (ficha mestra / CRM)

- **ERP:** ficha única PF/PJ (ADR ficha mestra canônica), contatos, consentimentos
  LGPD, documentos pessoais no cofre, histórico de relacionamento.
- **IA:** resumo do relacionamento; alerta de documentação vencida; detecção de
  duplicidade (HMAC cego de CPF/CNPJ já existente).
- **Limite:** nenhum dado de cliente entra em prompt externo sem pseudonimização.

### M3 — Casos (workspace)

- **ERP:** o agregado central — partes, área (metadado), fase, responsáveis,
  estratégia, valor, vínculos.
- **IA:** "Próxima ação" (orquestrador), saúde do caso com limiares únicos,
  linha do tempo fática com estado probatório (fato documentado × alegação ×
  controvérsia × inferência × validação humana — invariante 1 do Legal Brain).
- **Limite:** jornada só avança por evento verificável (Classe D).

### M4 — Processos e monitoramento

- **ERP:** processos judiciais/administrativos vinculados ao caso; movimentações;
  publicações e intimações.
- **Integrações:** DataJud (base nacional instituída pela Res. CNJ 331/2020),
  DJEN e Domicílio Judicial Eletrônico (Res. CNJ 455/2022), tribunais via
  ingestores. Todas com flag `*_ENABLED`, degradação graciosa e monitoramento
  **por resultado**.
- **IA:** tradução de andamento para linguagem do cliente; vinculação
  publicação → caso por número CNJ (marcada para conferência humana).
- **Limite:** movimentação **nunca** cria prazo sozinha (invariante 5 do Legal Brain).

### M5 — Prazos, agenda e tarefas

- **ERP:** motor de prazos determinístico, agenda de audiências, tarefas com SLA,
  distribuição por responsável.
- **Regras de cômputo** (devem estar codificadas com teste e fonte):
  dias úteis em prazos processuais (CPC, art. 219), exclusão do dia do começo
  e inclusão do vencimento (CPC, art. 224), suspensão de 20/12 a 20/01
  (CPC, art. 220), termo inicial (CPC, art. 231), intimação eletrônica e
  prazo de consulta (Lei 11.419/2006, art. 5º), calendário de feriados
  forenses por tribunal com fonte oficial.
- **IA:** sugestão de prazo a partir da intimação, citando o dispositivo **só
  quando a heurística casou** (comportamento atual) — nunca cria o prazo.
- **Limite:** criação/alteração de prazo é ato humano com dupla conferência
  configurável para prazos fatais.

### M6 — Documentos / GED

- **ERP:** upload, versionamento, classificação, OCR, vínculo obrigatório a
  cliente/caso, cofre de documentos sensíveis, integração Google Drive.
- **IA:** classificação sugerida (confirmação humana), extração de entidades,
  sumarização longa por *chunking*, detecção de PII para roteamento local.
- **Limite:** OCR e extração de documento com PII só em modelo local
  (comportamento atual de `documento_service`).

### M7 — Produção jurídica (peças)

- **ERP:** modelos institucionais, os 4 modos de produção (Livre, Guiado, Molde,
  Agente) **ligados de fato aos routers** (pendência registrada em
  `docs/ai/PECAS_MODOS_PRODUCAO_CONTROLADOS.md`), versionamento, revisão,
  "conferir e assinar" em ato único, exportação DOCX/PDF (Visual Law).
- **IA:** pipeline Legal Brain completo (§7.3); perfil de escrita do escritório
  (item novo do Plano de Simplificação, flag `PERFIL_ESCRITA_ENABLED`);
  revisão adversarial ("o que o juiz/parte contrária atacaria").
- **Limite:** peça com citação não verificada não pode ser marcada "pronta para
  protocolo".

### M8 — Conhecimento jurídico (RAG, teses, jurisprudência)

Detalhado no §6. Inclui banco de teses canônico (ADR 2026-08-24), biblioteca,
pesquisa e curadoria.

### M9 — Financeiro e honorários

- **ERP:** contrato de honorários, propostas, parcelas, êxito, despesas
  reembolsáveis, conciliação, NFS-e (ADR NFS-e Simples Nacional), extrato por
  cliente/caso.
- **IA:** referência da tabela OAB/MG já estruturada (sem inventar valor);
  previsão de fluxo de caixa **descritiva**; cobrança sugerida.
- **Limite:** emissão fiscal, cobrança e baixa são atos humanos auditados.

### M10 — Portal do cliente

- **ERP:** acompanhamento do caso, envio de documentos, mensagens, assinatura,
  pagamentos.
- **IA:** andamento traduzido, **sempre revisado** antes de publicar ao cliente.
- **Limite:** nenhuma resposta automática de IA ao cliente (aconselhamento
  jurídico é ato privativo — EOAB, art. 1º, II).

### M11 — Gestão e jurimetria

- **ERP:** produtividade, carteira, receita, prazos cumpridos, SLA.
- **IA:** jurimetria **descritiva** (invariante 7 do Legal Brain: não é
  probabilidade de êxito do caso).
- **Limite:** qualquer métrica de "chance de êxito" depende de decisão do
  titular (pauta T3 do Plano-Mestre) por risco ético.

### M12 — Administração, auditoria e governança

- **ERP:** usuários, papéis, RBAC por rota (`moduleRegistry.tsx`), 2FA,
  auditoria, retenção LGPD, configurações, kill-switch de IA, painel de
  provedores (`GET /ia-governanca/provedores`), saúde de fontes e do corpus.

---

## 6. RAG jurídico amplo — "Corpus Juris EJC"

### 6.1 Camadas do corpus

| Camada | Conteúdo | Fonte-alvo | Autoridade | Isolamento |
|---|---|---|---|---|
| C1 — Constituição e legislação federal | CF/88, códigos, leis, MPs, decretos | Planalto, LexML, Senado, Câmara | Primária | Global |
| C2 — Legislação estadual/municipal | MG e municípios de atuação | Portais oficiais dos entes | Primária | Global |
| C3 — Normas infralegais | Resoluções CNJ, ANPD, OAB; instruções normativas | Portais institucionais | Primária (escopo restrito) | Global |
| C4 — Precedentes qualificados | Súmulas vinculantes, súmulas, repetitivos, repercussão geral, IRDR/IAC (CPC, art. 927) | STF, STJ, TST, TJMG | Vinculante/persuasiva conforme tipo | Global |
| C5 — Jurisprudência | Acórdãos e decisões | Tribunais, DJEN | Persuasiva | Global |
| C6 — Doutrina | Apenas obras com licença de uso ou de domínio público | Acervo licenciado | Secundária | Global |
| C7 — Acervo do escritório | Peças aprovadas, pareceres, teses vencedoras | EJC | Interna | Global interno (sem PII) |
| C8 — Caso | Documentos e fatos do caso | EJC | Fato | `client_id` + `case_id` + ownership |

**Proposições legislativas** (PL, PEC) ficam em categoria própria, com aviso
explícito de que não são direito vigente (ADR de vigência, §2.5).

### 6.2 Pipeline de ingestão

```
fonte oficial
  → coleta (ingestor com flag, retry, hash de conteúdo, chave_origem)
  → normalização (texto limpo, encoding, remoção de boilerplate)
  → segmentação ESTRUTURAL
       lei: artigo / parágrafo / inciso / alínea, com caminho hierárquico
       acórdão: ementa / relatório / voto / dispositivo / tese fixada
  → metadados: tipo, órgão, data, número, fonte_oficial, legal_status,
               vigencia_conferida (data + origem), versão compilada
  → grafo normativo: "altera", "revoga", "regulamenta", "supera",
               "aplica tema X" — só relações explícitas com proveniência
  → embeddings (e5-large 1024d) + tsvector português
  → quarentena → curadoria (humana ou regra determinística comprovável)
  → publicação no índice
  → monitoramento por resultado (ingestao_saude)
```

### 6.3 Recuperação (retrieval)

1. **Pré-filtro de escopo** (`_FILTRO_ESCOPO_RAG`): caso/cliente + ownership.
2. **Pré-filtro de autoridade e vigência**: para "direito atual", só
   `vigencia_conferida`; para fatos passados, resolução temporal pela data de
   referência (versão compilada vigente na data).
3. **Busca híbrida**: denso (pgvector HNSW) + lexical (`tsvector` pt, essencial
   para números de lei, artigos e súmulas) com fusão por *Reciprocal Rank Fusion*.
4. **Reranking** (`services/ai/reranker.py`, com tratamento de categoria normativa).
5. **Expansão por grafo**: puxa dispositivo alterador/regulamentador e precedente
   que aplica a norma.
6. **Montagem de contexto** com orçamento de tokens e citação por identidade
   (`doc_id#trecho`), nunca texto solto.
7. **Citation gate** pós-geração: toda citação na resposta precisa casar com um
   trecho recuperado; o que não casa é removido ou marcado.

### 6.4 Avaliação contínua do RAG

| Métrica | Definição | Meta inicial (§13) |
|---|---|---|
| Recall@10 normativo | Fração de perguntas do golden set cujo dispositivo correto aparece no top-10 | ≥ 0,90 |
| Precisão de citação | Citações da resposta que existem e dizem o que a resposta afirma | ≥ 0,98 |
| Taxa de alucinação de fonte | Citações inexistentes na resposta final (após gate) | 0 |
| Uso indevido de norma revogada | Respostas que tratam norma revogada como vigente | 0 |
| Cobertura de vigência | % de chunks de legislação com `vigencia_conferida` | crescimento mensal medido |
| Frescor | Atraso entre publicação oficial e disponibilidade no índice | ≤ 24h para DJEN/DOU |

Golden sets por ramo, versionados em `app/eval/`, construídos e validados por
advogado — sem isso, as metas não têm lastro.

---

## 7. Núcleo de IA — definição operacional de "IA perfeita"

### 7.1 Arquitetura (evolução do núcleo único existente)

```
pedido (tela / atalho / evento de domínio)
  │
  ├─ 1. Intenção (determinística primeiro; LLM só como desempate)
  ├─ 2. Política: RBAC + ownership + kill-switch + orçamento
  ├─ 3. Classificação de sensibilidade do dado → rota LOCAL ou EXTERNA
  ├─ 4. Contexto: dossiê do caso + estado probatório + RAG (§6.3)
  ├─ 5. Sanitização/pseudonimização (obrigatória para EXTERNA)
  ├─ 6. Seleção de modelo por tarefa e risco (model_router)
  ├─ 7. Execução: chamada simples OU loop agêntico com ferramentas
  │        (pesquisa RAG, consulta processual, cálculo de prazo, leitura de doc)
  │        com limite de passos/tokens (AI_AGENT_MAX_STEPS / _MAX_TOKENS)
  ├─ 8. Validação: citation gate, promessa de resultado, sem base, formato
  ├─ 9. Revisão adversarial (tarefas de mérito)
  ├─ 10. AILog (falha de log = falha da resposta)
  └─ 11. HITL: rascunho → revisão → aprovação humana → efeito
```

### 7.2 Roteamento de modelos

| Classe de tarefa | Dado | Modelo | Justificativa |
|---|---|---|---|
| Extração/OCR/classificação com PII | Identificado | Local (Ollama) | LGPD — minimização (Lei 13.709/2018, art. 6º, III) |
| Resumo, tradução de andamento | Pseudonimizado | Rápido/econômico | Custo |
| Raciocínio de mérito, estratégia, peça complexa | Pseudonimizado | Modelo de maior capacidade disponível no provedor contratado | Qualidade |
| Classificação de intenção | — | Determinístico | Previsibilidade |

Modelos concretos ficam em configuração (`ANTHROPIC_MODEL_COMPLEXO`,
`ANTHROPIC_MODEL_RAPIDO`, `AI_PROVIDER_PRIORITY`), nunca hard-coded, e a fonte
de verdade do que está ativo é `GET /ia-governanca/provedores`.

### 7.3 Pipeline de raciocínio jurídico (Legal Brain ligado ao runtime)

```
caso/documentos → estado probatório → questões jurídicas (issue engine)
→ plano de pesquisa (fonte primária + validade temporal + precedente de apoio
  + entendimento adverso + aderência fática) → RAG → validade de precedente
→ tese + contratese + prova necessária → revisão adversarial
→ redação → citation gate → HITL → AILog
```

Rollout conforme `docs/ia/LEGAL_BRAIN_ARCHITECTURE.md`: modo *shadow* (sem
alterar resposta), comparação no Legal Bench, promoção só ao superar baseline.

### 7.4 Níveis de autonomia (HITL graduado)

| Nível | Exemplo | Regra |
|---|---|---|
| N0 — Informativo | Resumo interno, busca | Exibe com fontes; sem efeito externo |
| N1 — Rascunho | Minuta, sugestão de prazo, tradução de andamento | Carimbo `is_rascunho=True`; só humano promove |
| N2 — Ato interno | Criar tarefa, classificar documento | Confirmação de um clique, auditada |
| N3 — Ato com efeito externo | Protocolo, envio ao cliente, prazo fatal, emissão fiscal | Ação humana identificada; IA nunca executa |

Não existe N4 (autônomo com efeito externo) no v4.

### 7.5 Agentes por competência (metadado sobre o mesmo núcleo)

Mantém-se o `agent_registry`; o v4 organiza os agentes por **competência
jurídica e processual**, não por tela: triagem, pesquisa, estratégia, redação,
revisão adversarial, prazos, documentos, financeiro, comunicação com cliente
(sempre N1), e um agente por ramo apenas quando o ramo exigir prompt e
golden set próprios. Nenhum agente tem código de execução próprio.

### 7.6 Custos, observabilidade e kill-switch

- Orçamento por usuário/mês e alerta (`AI_BUDGET_ALERTA_BRL`), cache de prompt
  e de resposta já configuráveis.
- Rastreamento por chamada (Langfuse, perfil `observability` do Compose).
- Kill-switch global e por provedor preservado; falha fecha (sem IA) em vez
  de degradar para provedor não autorizado.

---

## 8. Redesenho de experiência (UX/UI)

### 8.1 Navegação global (de ~34 áreas para 7 entradas)

```
┌─────────────────────────────────────────────────────────────────────┐
│ [≡] EJC     🔍 Buscar ou comandar (Ctrl+K)            🔔  ✦IA  [👤] │
├──────────┬──────────────────────────────────────────────────────────┤
│ Início   │                                                          │
│ Entrada  │                                                          │
│ Casos    │             (conteúdo do módulo)                         │
│ Agenda   │                                                          │
│ Clientes │                                                          │
│ Conhecim.│                                                          │
│ Finanças │                                                          │
│ ──────── │                                                          │
│ Gestão   │  (só papéis de gestão)                                   │
│ Admin    │                                                          │
└──────────┴──────────────────────────────────────────────────────────┘
```

- **Início:** "Meu dia" — prazos de hoje/amanhã, intimações não lidas,
  peças aguardando minha revisão, próximas ações dos meus casos.
- **Command palette (Ctrl+K):** busca global híbrida + comandos ("novo prazo
  no caso X", "gerar contestação", "abrir processo 0000000-00…").
- **✦IA:** painel lateral **único**, contextual à tela, que substitui as
  quatro superfícies de IA (D5). As rotas antigas viram redirecionamento.

### 8.2 Workspace do caso (de 26 abas para 5 seções)

```
┌─────────────────────────────────────────────────────────────────────┐
│ ‹ Casos   Silva × Banco X — Revisional       ● Em andamento  ⚑ Alta │
│ Cliente: J. Silva · Proc. 5000000-00.2026.8.13.0000 · Resp.: Dr. A  │
├─────────────────────────────────────────────────────────────────────┤
│ Visão │ Atividades │ Arquivos │ Estratégia │ Financeiro             │
├─────────────────────────────────────────────────────────────────────┤
│ ▶ PRÓXIMA AÇÃO                                                      │
│   Contestação — prazo fatal 15/10 (D-8)                             │
│   [Gerar minuta guiada]  [Abrir modelo]  [Delegar]                  │
├─────────────────────────────────────────────────────────────────────┤
│ JORNADA  ●──●──●──◐──○──○──○   (etapa só conclui por evento)        │
├──────────────────────────────┬──────────────────────────────────────┤
│ ALERTAS                      │ SAÚDE DO CASO                        │
│ ⚠ 2 documentos pendentes     │ Atenção — 2 fatores (ver)            │
│ ⚠ Intimação não vinculada    │                                      │
├──────────────────────────────┴──────────────────────────────────────┤
│ ▸ Dados do caso (recolhível)                                        │
└─────────────────────────────────────────────────────────────────────┘
```

| Seção | Absorve (exemplos das abas atuais) |
|---|---|
| Visão | Resumo, orquestrador, jornada, alertas, saúde |
| Atividades | Andamentos, intimações, prazos, tarefas, histórico/memória |
| Arquivos | Documentos e provas, peças, data room |
| Estratégia | Teses, pesquisa, sala de análise, riscos, partes |
| Financeiro | Honorários, despesas, parcelas, notas |

As antigas abas viram **filtros** dentro das seções; deep-links antigos
continuam válidos por redirecionamento.

### 8.3 Padrões de interação da IA

- Toda resposta de IA mostra: **fontes clicáveis** (abrem o trecho), selo de
  **vigência**, selo **RASCUNHO**, modelo/provedor usado e botão
  "por que isso?" (plano de pesquisa resumido).
- Lacunas são exibidas como lista de pendências acionáveis ("falta comprovante
  de residência — solicitar ao cliente").
- Diferença visual entre **fato documentado**, **alegação** e **inferência**
  (estado probatório) com ícone + rótulo, nunca só cor.

### 8.4 Design system

Mantém-se integralmente a identidade canônica de 28/09/2026
(`docs/DESIGN_SYSTEM_EJC.md`): base neutra, um azul de ação, ouro DPT só para
marca, violeta exclusivo de IA, Playfair Display em títulos editoriais, Inter
na interface, algarismos tabulares. O redesenho é de **estrutura e fluxo**,
não de paleta.

Requisitos não funcionais de UI:

- Acessibilidade WCAG 2.2 nível AA (contraste, foco visível, navegação por teclado).
- Responsivo em 375 / 768 / 1280 px, sem rolagem horizontal.
- Tempo até interação da tela de caso ≤ 2 s em conexão comum (medir no build).

---

## 9. Modelo de dados e conceitos canônicos

### 9.1 Agregados

| Agregado | Raiz | Entidades internas | Invariante transacional |
|---|---|---|---|
| Cliente | `clients` | contatos, consentimentos, documentos pessoais | CPF/CNPJ cifrado + HMAC cego único |
| Caso | `cases` | partes, jornada, checklist, vínculo de tese, estado probatório | Mudança de etapa + evento outbox na mesma transação |
| Processo | `processos` | movimentações, intimações | Vínculo a caso conferido por humano |
| Prazo | `prazos` | origem (intimação/manual), conferências | Prazo fatal exige conferência registrada |
| Peça | `legal_docs` | versões, validação (`ai_log_id`, hash) | Aprovação = ato único "conferir e assinar" |
| Conhecimento | `knowledge_docs` | chunks, relações normativas, curadoria | Curadoria humana nunca sobrescrita por ingestão |
| Honorário | contratos/propostas | parcelas, lançamentos, notas | Baixa e emissão auditadas |

### 9.2 Fonte canônica por conceito (fecha as Classes A–D)

| Conceito | Fonte canônica | Guarda |
|---|---|---|
| Status do caso | `core/status_caso.py` ↔ `frontend/src/types/caseStatus.ts` | Teste de paridade existente + grep-test |
| Saúde do caso | `core/health_thresholds.py` — **a criar** (proposto na F2/Classe C do Plano-Mestre; não existe em `main@4c03f86`) | Teste de paridade |
| Tese do caso | `tese_caso_links` (candidates = estágio HITL que materializa link na aprovação) | Decisão T3 + teste de paridade |
| Jornada | Eventos verificáveis do outbox | Golden test das 16 etapas |
| Provedores de IA ativos | `GET /ia-governanca/provedores` | — |
| Saúde do corpus | `knowledge_governance.health_snapshot` | Sem métrica concorrente |
| Status do backlog | `docs/PLANO_MESTRE_STATUS.md` | `scripts/status_check.sh` |

### 9.3 Regras de migração (inalteradas)

Head real via `alembic heads`; reserva em `MIGRATION_RESERVATIONS.md`;
*expand → backfill → contract* em PRs separados; revisão manual do
autogenerate (tabelas raw-SQL sem model); nunca editar migration aplicada;
backup antes de qualquer passo destrutivo.

---

## 10. Segurança, LGPD e ética profissional

### 10.1 Base normativa de referência

> Conferir vigência e redação na data de uso, conforme a própria ADR de
> vigência do EJC. Esta tabela indica onde o requisito se apoia; não é parecer.

| Requisito do sistema | Base | Implementação no v4 |
|---|---|---|
| Finalidade, necessidade, segurança, prevenção | Lei 13.709/2018 (LGPD), art. 6º | Minimização no contexto de IA; roteamento local |
| Base legal de tratamento | LGPD, arts. 7º e 11 (dados sensíveis) | Registro de base legal por finalidade na ficha do cliente |
| Registro das operações | LGPD, art. 37 | AILog + AuditLog sem PII |
| Medidas de segurança | LGPD, art. 46 | Cifra de CPF/CNPJ, RBAC, 2FA, backup cifrado |
| Comunicação de incidente | LGPD, art. 48; Res. CD/ANPD 15/2024 | Runbook de incidente com prazos e responsáveis |
| Agente de pequeno porte | Res. CD/ANPD 2/2022 | Verificar enquadramento (decisão do titular) |
| Inviolabilidade e sigilo | Lei 8.906/1994 (EOAB), art. 7º, II; CED-OAB, capítulo do sigilo profissional | Ownership por caso; nenhum dado de cliente em corpus global |
| Atividade privativa de advocacia | EOAB, art. 1º | IA nunca responde ao cliente sem revisão (N3) |
| Publicidade | Provimento CFOAB 205/2021 | Conteúdo externo gerado por IA sempre revisado |
| Fundamentação e precedentes | CPC (Lei 13.105/2015), arts. 489, §1º, e 927 | Citation gate + distinção de precedente vinculante |
| Processo eletrônico | Lei 11.419/2006 | Regras de intimação eletrônica no motor de prazos |
| Assinatura digital | MP 2.200-2/2001 (ICP-Brasil) | Assinatura de peças com certificado do advogado |
| Marco legal de IA | PL 2338/2023 — **proposição, não vigente** na data deste documento; acompanhar | Arquitetura já compatível com transparência, registro e supervisão humana |

### 10.2 Controles técnicos

- Autenticação: JWT HS256 + refresh httpOnly + 2FA TOTP + bcrypt (manter;
  não reintroduzir passlib/python-jose).
- Rotas novas nascem protegidas; endpoint público é exceção documentada.
- Segredos fora do repositório; cofre de credenciais (`PLANO_COFRE_CREDENCIAIS.md`).
- Isolamento RAG testado (`test_rag_isolation.py`) e estendido ao grafo normativo.
- Revisão `security-auditor` obrigatória em auth, permissões, uploads e config.
- Credenciais de acesso à VPS nunca em texto puro em documentos, prompts ou
  preferências; acesso por chave SSH e usuário não-root.

---

## 11. Infraestrutura, operação e continuidade

| Tema | Estado v3 | Alvo v4 |
|---|---|---|
| Topologia | Docker Compose na VPS, Nginx no host | Mantida; separar `worker` Celery e `beat`; perfil `ia-local` dimensionado |
| Staging | `docker-compose.staging.yml` | Staging obrigatório para migration e deploy com smoke automatizado |
| CI | Actions indisponível; gate local + hooks | Restaurar Actions **ou** runner self-hosted (`infra/woodpecker`); gate local continua como pré-push |
| Deploy | `scripts/deploy_manual.sh` | Mesmo script chamado pela esteira; dry-run + backup + migration + smoke + rollback |
| Backup | Diário cifrado, offsite | Teste de restauração mensal registrado (RPO/RTO de `POLITICA_CONTINUIDADE_RPO_RTO_EJC.md`) |
| Observabilidade | Healthcheck, Langfuse opcional | Erros (Sentry ou equivalente self-hosted), uptime externo, métricas de IA e de ingestão no painel |
| Escala | Worker único | Redis para rate-limit/locks; possibilidade de 2 réplicas da API |

---

## 12. Roteiro de execução em ondas

**Relação com o Plano-Mestre vigente:** as fases F0–F6 de
`docs/estrategia/PLANO_MESTRE_EJC.md` **continuam** e têm precedência. O v4 não
abre frente concorrente (WIP 1 estrutural + 1 funcional,
`docs/engineering/WIP_AND_RELEASE_POLICY.md`). As ondas abaixo descrevem o que
vem depois ou o que se encaixa em fases já previstas.

| Onda | Objetivo | Entregas principais | Depende de | Gate de saída |
|---|---|---|---|---|
| **V0 — Fundação** | Verdade operacional | Conclusão de F0–F2 do Plano-Mestre (status canônico, deploy manual, Classes A–D) | Titular: T1–T3 | Testes de paridade verdes; números iguais em SQL × API × tela |
| **V1 — Caso como centro** | O advogado acha a próxima ação | Fase 1 do Plano de Simplificação (Visão = próxima ação; 26 abas → 5 seções); "Meu dia" no Início | V0 | Teste de usabilidade com 1 advogado real em caso real |
| **V2 — Produção jurídica ligada** | Peça do início ao protocolo | Modos de produção ligados aos routers; conferir-e-assinar; DOCX/PDF; perfil de escrita (flag) | V1 | E2E redação → validação → aprovação → PDF |
| **V3 — Corpus Juris** | RAG amplo e confiável | Segmentação estrutural; vigência conferida por lote curado; busca híbrida (A6); grafo normativo; golden sets por ramo | V0; curadoria do titular (T5) | Métricas do §6.4 publicadas e dentro da meta para os ramos ativos |
| **V4 — Legal Brain em produção** | Raciocínio estruturado | Legal Brain em *shadow* → promoção; revisão adversarial; painel IA único (fim das 4 superfícies) | V3 | Legal Bench acima do baseline por 2 ciclos |
| **V5 — Plataforma** | Robustez e escala | Outbox (A2), Celery único (A3), Redis (A4), SSE (A5), observabilidade | Pode intercalar com V2–V4 respeitando WIP | Restore drill + zero tarefa perdida em teste de restart |
| **V6 — Módulos e verticais** | Fronteiras definitivas | `app/modules/` por módulo Core (A1); verticais por contrato (A7); remoção dos legados com paridade | V5 | Teste de fronteira de import verde; rotas legadas redirecionadas |
| **V7 — Portal e financeiro completos** | Relação com cliente | Portal com andamento revisado, pagamentos, assinatura; NFS-e | V2, V6 | Cliente real acompanha um caso pelo portal |

**Estimativa:** não é possível estimar calendário com rigor sem saber a
capacidade semanal de execução e a disponibilidade do titular para curadoria
e decisões. Recomenda-se medir a vazão real das ondas V0–V1 e só então
projetar as demais.

---

## 13. Indicadores e critérios de aceite

| Dimensão | Indicador | Meta |
|---|---|---|
| Produto | Caso real do intake ao protocolo dentro do EJC | Atingido e repetido por ≥ 2 advogados |
| Produto | Cliques da abertura do caso até iniciar a próxima ação | ≤ 2 |
| Prazos | Prazos fatais perdidos por falha do sistema | 0 |
| Prazos | Intimações capturadas e vinculadas em ≤ 24 h | ≥ 99% |
| IA | Citações inexistentes em saída final | 0 |
| IA | Norma revogada tratada como vigente | 0 |
| IA | Respostas de mérito com fontes rastreáveis | 100% (ou marcadas "sem base") |
| IA | Aceitação de minutas (editadas < 30%) | Medir baseline em V2; meta definida depois |
| RAG | Recall@10 normativo / precisão de citação | ≥ 0,90 / ≥ 0,98 |
| LGPD | PII identificada enviada a provedor externo | 0 (teste automatizado + auditoria de logs) |
| Segurança | IDOR/escala de privilégio em auditoria | 0 críticos abertos |
| Operação | Restauração de backup testada | Mensal, registrada |
| Engenharia | Conceitos com mais de uma fonte de verdade | 0 (grep-tests) |

---

## 14. Riscos e mitigação

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| Reescrever em vez de evoluir | Média | Alto | Regra "conectar, não criar"; nenhuma onda cria módulo paralelo |
| Curadoria de vigência não acompanha o volume | Alta | Alto | Priorizar por ramo ativo; regra determinística só com metadado oficial comprovável; RAG mostra "vigência não verificada" em vez de esconder |
| Excesso de confiança do usuário na IA | Média | Alto | Selos RASCUNHO/vigência; N3 sempre humano; treinamento interno |
| Custo de provedor externo | Média | Médio | Roteamento por tarefa, cache, orçamento e alerta |
| VPS única como ponto de falha | Média | Alto | Backup offsite testado; runbook de reconstrução; RTO declarado |
| CI indisponível prolongado | Alta | Médio | Gate local obrigatório + runner self-hosted |
| Licenciamento de doutrina | Média | Médio | Só obras licenciadas ou de domínio público em C6 |
| Concorrência entre agentes de desenvolvimento | Média | Médio | WIP 1+1; Issue por PR; checagem de PRs que tocam os mesmos arquivos |
| Exposição de credenciais operacionais | Média | Alto | Cofre; rotação; SSH por chave; nunca senha em texto em prompt/documento |

---

## 15. Decisões que dependem do titular

| # | Decisão | Por que é do titular | Default proposto |
|---|---|---|---|
| T-v4-1 | Aprovar a lista final dos 12 módulos Core e a navegação de 7 entradas | Produto | Conforme §5 e §8.1 |
| T-v4-2 | Política de "chance de êxito" (exibir, não exibir, ou só jurimetria descritiva) | Ético (EOAB/CED) | Só descritiva |
| T-v4-3 | Ramos prioritários para golden sets e curadoria de vigência | Conhecimento jurídico | Ramos com mais casos ativos |
| T-v4-4 | Orçamento mensal de IA externa | Financeiro | Manter `AI_BUDGET_ALERTA_BRL` atual |
| T-v4-5 | Aquisição/licença de base doutrinária | Contratual | Adiar até V3 medido |
| T-v4-6 | Restaurar Actions ou adotar runner self-hosted | Infra/custo | Self-hosted se a conta continuar indisponível |
| T-v4-7 | Dupla conferência obrigatória para prazo fatal | Processo do escritório | Ativar |

---

## 16. O que não fazer

1. Reescrever o EJC do zero ou trocar a stack (FastAPI/React/PostgreSQL atendem).
2. Criar nova tela/serviço de IA paralelo ao núcleo único.
3. Marcar legislação como vigente só por vir de fonte oficial.
4. Permitir que movimentação processual crie prazo sem humano.
5. Exibir "probabilidade de vitória" sem decisão do titular.
6. Migrar para microserviços.
7. Ingerir doutrina sem licença.
8. Usar dados de clientes em corpus global ou em treinamento de modelo.
9. Remover módulo legado sem paridade comprovada e redirecionamento de rota.
10. Fazer deploy fora da esteira ou acessar banco/diretório de produção diretamente.

---

## 17. Anexo — rastreabilidade

Documentos do repositório que fundamentam este plano:

- `CLAUDE.md`, `docs/GOVERNANCA_IA.md`, `docs/GOVERNANCA_IA_ADDENDUM_LOCAL_FIRST.md`
- `docs/estrategia/PLANO_MESTRE_EJC.md`, `docs/PLANO_MESTRE_STATUS.md`
- `docs/PLANO_SIMPLIFICACAO_EJC.md`
- `docs/decisoes/ADR_EJC_CORE_VERTICAIS_2026-09-25.md`
- `docs/decisoes/ADR_RAG_VIGENCIA_E_FONTE_OFICIAL_2026-09-04.md`
- `docs/decisoes/ADR_BANCO_TESES_CANONICO_2026-08-24.md`
- `docs/decisoes/ADR_CLIENTES_FICHA_MESTRA_CANONICA_2026-09-02.md`
- `docs/decisoes/ADR_NFSE_SIMPLES_NACIONAL_2026-08-15.md`
- `docs/ai/EJC_SINGLE_AI_CORE_ARCHITECTURE.md`, `docs/ai/PECAS_MODOS_PRODUCAO_CONTROLADOS.md`
- `docs/ia/LEGAL_BRAIN_ARCHITECTURE.md`
- `docs/DESIGN_SYSTEM_EJC.md`, `docs/redesign-relatorio-final.md`
- `docs/ARQUITETURA_ATUAL.md`, `RUNBOOK_MIGRACAO_EMBEDDING_1024.md`

Código citado: `backend/app/services/legal_case_orchestrator.py`,
`backend/app/services/ai/core/`, `backend/app/services/ai_gateway.py`,
`backend/app/services/ai/sanitization_policy.py`,
`backend/app/services/ai/reranker.py`, `backend/app/services/legal_brain/`,
`backend/app/services/ingestors/`, `backend/app/services/ingestao_saude.py`,
`backend/app/core/ownership.py`, `backend/app/models/rag.py`,
`frontend/src/config/moduleRegistry.tsx`.

Normas citadas no §5 e §10 devem ter vigência e redação conferidas em fonte
oficial (Planalto, CNJ, ANPD, CFOAB) antes de uso em peça ou parecer.
