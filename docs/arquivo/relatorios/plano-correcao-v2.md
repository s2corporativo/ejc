# PROMPT PARA CLAUDE CODE — Correções do EJC (v2)

> **Status canônico em `docs/PLANO_MESTRE_STATUS.md`.** Este documento não é mais
> atualizado com status de resolvido/pendente — ele continua valendo como
> *descrição* dos achados (reprodução, severidade, contexto), mas "o que já foi
> feito" só se confere na tabela verificável por máquina do checklist-mestre
> (`scripts/status_check.sh`). Desenho completo do plano de correção em
> `docs/estrategia/PLANO_MESTRE_EJC.md`.

> **Esta versão substitui integralmente a anterior.** Incorpora as Partes 11 e 12 da auditoria, reordena prioridades e **corrige um número usado na v1** (ver Nota de Retificação ao final).
>
> **Como usar:** cole o bloco inteiro para um plano completo, ou apenas a fase que quiser executar agora. Fases independentes entre si, salvo dependência explícita.
> **Sugestão de ordem real de execução:** Fase 0 (humano, hoje) → Fase 1 (meio dia de trabalho, resolve a percepção de "sistema confuso") → Fase 2 (desbloqueio) → demais.

---

## CONTEXTO DO SISTEMA

**EJC (Ecossistema Jurídico Clovis)** — sistema de gestão jurídica em produção do escritório De Paula Teixeira Advogados.

- **Stack:** FastAPI (Python) + React/TypeScript/Vite/Tailwind + PostgreSQL (pgvector) + Docker + Nginx
- **Produção:** `https://ejc.depaulateixeira.adv.br` — VPS `13.140.167.153`
- **Alembic head:** `122_route_usage_metrics` · **baseURL do frontend:** `/api/v1`
- **Escala real:** 34 módulos · 453 rotas distintas · 6 usuários · **8 casos ativos** · 17 clientes · **23 peças** · 19 documentos · **1 prazo** · base RAG com 4.489 docs / 47.359 chunks

**Origem:** auditoria externa de 12 rodadas, feita **apenas** por chamadas HTTPS à API de produção e análise estática dos bundles JS publicados. **Sem acesso ao código-fonte.** Cada item traz a evidência observável; a causa raiz no código precisa ser confirmada por você. Onde a auditoria não determinou a causa, está marcado `[INVESTIGAR]` — não presuma.

---

## REGRAS DE ENGAJAMENTO

1. **Produção com dados reais de clientes sob sigilo profissional.** Nenhuma migration destrutiva, `DROP`, `TRUNCATE` ou `DELETE` em massa sem confirmação explícita do usuário.
2. **Trabalhe em branch.** Um branch por fase. Nunca commite direto na principal.
3. **Diagnostique antes de corrigir.** Se a evidência da auditoria divergir do código, **reporte a divergência** em vez de forçar a correção sugerida.
4. **Não recrie do zero.** Correções cirúrgicas. Não refatore módulos inteiros.
5. **Escreva o teste antes do fix** quando a área não tiver cobertura.
6. **Não invente citação legal, jurisprudência ou dispositivo normativo** em nenhum texto que gerar.
7. Ao final de cada fase: o que mudou, arquivos tocados, como verificar, o que ficou pendente.

---

# FASE 0 — VERIFICAÇÃO HUMANA (hoje, não é trabalho de código)

## 0.1 — Prazo vencendo hoje, sem ciência confirmada

```
GET /deadlines/ → total: 1
{"titulo":"Impugnação","tipo":"processual","data_prazo":"2026-07-29",
 "dias_restantes":0,"urgencia":"critico","data_intimacao":"2026-07-15",
 "ciencia_confirmada":false,"status":"pendente","origem":"manual",
 "case_id":"e08e164b-e370-46a8-a5a1-b7255a913e15"}
```
Único prazo do sistema. Confirmar com o advogado responsável se já foi cumprido fora do EJC.

## 0.2 — A captura de intimações nunca capturou nada `[CRÍTICO]`

Cinco fatos, cada um verificado:

```
GET /ia-governanca/fontes → djen: {registros_total: 0, ultimo_status: "sucesso"}
GET /intimacoes/          → {"data":[],"total":0}
GET /deadlines/           → total: 1, origem "manual"  (zero prazos vindos de intimação)
GET /users/               → Administrador EJC: djen_oab_numero "251174"/MG
                            Clovis Soares (advogado):        djen_oab_numero null
                            Guilherme A. de Paula (sócio):   djen_oab_numero null
                            Joao Pedro Teixeira (advogado):  djen_oab_numero null
```

**Uma única OAB monitorada, cadastrada numa conta administrativa genérica. Os três advogados reais têm o campo vazio.**

E o sistema reporta saudável em três lugares:
```
heartbeat: {"job_name":"djen_intimacoes","status":"ok","last_status":"ok"}
GET /intimacoes/status-captura → {"sucesso":true,"intimacoes_encontradas":0,"defasado":false}
GET /diagnostico/central → DJEN "ok — Coleta habilitada com ao menos uma OAB monitorada"
```

**Ação humana, antes de qualquer código:** confirmar de quem é a inscrição 251174/MG; cadastrar `djen_oab_numero`/`djen_oab_uf` dos três advogados; **abrir o portal DJEN/Comunica CNJ e conferir manualmente se há comunicações dos últimos 30 dias que não estejam no EJC**.

---

# FASE 1 — FALSOS POSITIVOS E CONFUSÃO DE INTERFACE
### *Baixo esforço, altíssimo impacto percebido. É o que faz o sistema parecer quebrado no uso diário. Comece por aqui.*

## 1.1 — Dashboard afirma "0 peças aguardando revisão" com 100% em rascunho `[CRÍTICO]`

```
GET /dashboard/               → "pecas_aguardando_revisao": 0
GET /legal-docs/              → total: 98, TODAS em status "rascunho"
GET /ia-governanca/guardrails → "pecas_ia_sem_revisao": 97
```

Dois painéis do mesmo sistema, no mesmo minuto, dizendo o oposto. A tela principal informa ao advogado que o trabalho está em dia quando nada foi processado.

**Hipótese `[INVESTIGAR]`:** o contador conta peças em status `aguardando_revisao` — estado que **nenhuma peça consegue atingir**, porque o pipeline trava antes (item 2.1). Contador tecnicamente correto, operacionalmente enganoso.

**Correção:** derivar o contador do dado que o usuário procura — peças em rascunho não revisadas (`status='rascunho' AND human_reviewed=false`) — e não de um status intermediário inalcançável.

## 1.2 — Contador de casos ativos conta o arquivado `[ALTO]`

```
GET /dashboard/ → casos: {total: 9, ativos: 9, encerrados: 0,
                          por_status: {triagem: 8, arquivado: 1}}
GET /cases/     → total: 8
```
O próprio dashboard declara 1 caso `arquivado` e ainda assim reporta `ativos: 9`. Deveria ser 8. Além disso, dashboard e listagem mostram números diferentes sem explicação ao usuário.

## 1.3 — Filtro de status quebra o servidor ou retorna vazio `[ALTO]`

```
GET /cases/?status=all    → 500  {"detail":"Erro interno. A equipe foi notificada."}
GET /cases/?status=ativo  → 200  total: 0     ← existem 8 casos
GET /cases/               → 200  total: 8
```

- **`status=all` → 500 reproduzível.** Já reportado na Parte 2 da auditoria; permanece idêntico.
- **`status=ativo` → zero.** Os status reais no banco são `triagem` e `arquivado`. `ativo` não existe. Se a interface oferece esse filtro, o advogado clica e vê **"nenhum caso"** com 8 casos cadastrados. **É a principal origem do relato de "rota errada".**

**Correção:** enum único de status compartilhado entre frontend e backend, com validação. `status=all` deve funcionar ou não ser oferecido.

## 1.4 — Mensagem falsa "A equipe foi notificada" `[MÉDIO]`

```
GET /analytics/roi-por-area → 500 {"detail":"Erro interno. A equipe foi notificada."}
```
Erro 500 reproduzível **e a mensagem é falsa**: `GET /diagnostico/central` confirma *"Sem coletor de erros persistido no banco"* e Sentry desabilitado. Ninguém foi notificado e não há registro histórico do erro.

**Correção:** corrigir o 500 **e** remover a afirmação até que o Sentry esteja ativo (item 6.2).

## 1.5 — Rotas retornando 404 `[MÉDIO]`

```
GET /workflow/   → 404      GET /crm/leads → 404
GET /assinaturas → 404      GET /anexos    → 404
GET /procuracoes → 307      GET /agenda-eventos → 307
```
Determinar, para cada uma, se o path mudou, se o módulo foi descontinuado, ou se o frontend chama o caminho errado. Os 307 são redirects de barra final do FastAPI — custam um round-trip extra por chamada; padronize `redirect_slashes` ou os paths no frontend.

**Critério de aceite da Fase 1:** abrir o dashboard e cada listagem principal e obter números coerentes entre si; nenhum filtro retornando vazio indevidamente ou 500.

---

# FASE 2 — DESBLOQUEIO FUNCIONAL

## 2.1 — Vínculo de validação que trava as peças `[CRÍTICO]`

**Reprodução:**
```
1. POST /legal-docs/{id}/validar
   → 200 {"ai_log_id":"<uuid>","score_confianca":94,"veredito":"REVISAR ANTES DE USAR"}
2. PATCH /ai/logs/{ai_log_id}/hitl
   → 200, log passa a "aplicado"
3. GET /legal-docs/{id}
   → "validacao_juridica": {"status":"sem_validacao","ai_log_id":null, ...}
                                                     ^^^^^^^^^^^^^^^ nunca gravado
4. POST /legal-docs/{id}/aprovar → ERRO "Status atual: sem_validacao"
5. GET  /legal-docs/{id}/pdf     → 422 (bloqueado em cascata)
```
Confirmado que **não é permissão** — o campo permanece `null` mesmo como `superadmin`.

**Dimensão real:** **22 de 23 peças** do acervo real sem revisão. *(A v1 deste prompt dizia "97 de 98" — número inflado; ver Nota de Retificação.)*

**Correção — escolha a mais adequada à arquitetura real:**
- **(a)** gravar `validacao_juridica.ai_log_id`, `score` e `veredito` no `LegalDoc` logo após validação bem-sucedida; **ou**
- **(b)** fazer `/aprovar` resolver a validação consultando o AILog por `documento_id`, eliminando o campo denormalizado.

**Backfill:** script idempotente reconciliando os AILogs pendentes com seus documentos. Dry-run primeiro, reportando quantos registros seriam afetados.

**Critério:** criar peça → validar → aprovar → exportar PDF, ponta a ponta, sem intervenção no banco.

## 2.2 — Embeddings desligados: 0 de 47.359 chunks indexados `[CRÍTICO]`

```
GET /rag/stats            → {"total_chunks":51651,"chunks_indexados":0}
GET /rag/governanca/saude → {"total_chunks":47359,"embedded_chunks":0,"vectorized_percent":27.4}
GET /diagnostico/central  → "Embeddings / RAG": desligado, "EMBEDDINGS_ENABLED=false"
                             ação sugerida pelo próprio sistema: "Defina EMBEDDINGS_ENABLED=true"
GET /system-modules/integrations → embeddings: {enabled:false, configured:true, mode:"local"}
```

**Antes de habilitar:** confirmar que o serviço de embeddings (descrito nos guardrails como *"serviço interno isolado"*) está provisionado e acessível — ligar a flag sem o serviço quebra as buscas que hoje funcionam por fallback textual.

**Facilitador já existente:** o scheduler tem job `reembed_rag_orfaos` agendado (visto com próxima execução em 2026-07-29T12:20). Habilitada a flag, a reindexação provavelmente ocorrerá sozinha. Verificar antes de escrever script próprio.

**Atenção operacional:** 47 mil chunks em produção. Lotes, fora de pico, com log e retomada. Verificar índice do pgvector (HNSW/IVFFlat) para o volume.

## 2.3 — Modelo local para dados pessoais `[CRÍTICO]`

**Problema que resolve:** peças saem com `[PREENCHER]` na qualificação das partes porque o guardrail de PII bloqueia CPF/RG/nome — salvo com modelo local habilitado. É a causa real de "a IA não entrega documento pronto".

```
GET /ia-governanca/provedores → ollama: {modelo_configurado:"deepseek-r1:8b",
                                          elegivel:false, status:"desabilitado", tentativas:0}
```

**Por que é a solução correta e não um contorno:** processar PII localmente atende à **Resolução CNJ nº 615/2025, art. 19, § 3º, IV**, que veda inserir dados sigilosos em plataformas externas. Documento completo **e** dado pessoal nunca sai do servidor.

- Confirmar que o daemon Ollama roda e que `deepseek-r1:8b` está baixado (`configured:true` indica só configuração). Avaliar RAM/VRAM do VPS.
- `[INVESTIGAR]` Avaliar se um 8B serve. Recomendação: usá-lo para **preencher qualificação a partir de dados já cadastrados** (tarefa estruturada), mantendo argumentação nos modelos maiores. Não presuma que um 8B redige peça.

## 2.4 — Consolidar aprovação em um único ato `[ALTO]`

**Objetivo do usuário:** que a peça chegue pronta e a revisão seja conferência, não preenchimento.

Fluxo atual: `POST /validar` → `PATCH /ai/logs/{id}/hitl` → `POST /aprovar` → `GET /pdf` (4 chamadas).

- Após 2.1 corrigido, consolidar em **uma ação de conferência/assinatura** que execute validação, vinculação e aprovação atomicamente.
- Liberar PDF desde o estado de minuta — o advogado precisa ler antes de assinar.
- Rotular `"minuta final — conferir e assinar"` em vez de `"rascunho"`.
- **Preservar o registro do ato de conferência** (quem, quando, qual versão). Custa um clique e é o que evidencia a diligência do advogado sob a **Lei 8.906/94, art. 32**. Consolidar é o objetivo; apagar o rastro não é.

---

# FASE 3 — SINCRONIZAÇÃO E INTEGRIDADE REFERENCIAL

## 3.1 — Monitorar resultado, não apenas execução `[CRÍTICO]`

Causa comum por trás do DJEN (0.2), das fontes dormentes (3.2) e do `anpd`. Os 7 heartbeats aferem **cadência** (`idade_horas` vs `max_age_horas`) e **não** produtividade. Um job que roda pontualmente e entrega zero é indistinguível de um saudável.

**Correção estrutural, aplicável a todas as fontes:** além de `last_run_at`, monitorar `registros_total` e alertar quando (a) fonte historicamente produtiva zerar, (b) fonte nunca tiver produzido nada, ou (c) N execuções consecutivas retornarem 0. Baixo custo, resolve DJEN, os três `juris_import_*`, TJMG e LexML de uma vez.

## 3.2 — Fontes de ingestão dormentes ou silenciosas `[ALTO]`

| Fonte | Status | Idade | Total histórico |
|---|---|---|---|
| `juris_import_lexml` | sucesso | **164h** | **0** |
| `juris_import_stj` | sucesso | **164h** | **0** |
| `juris_import_tjmg` | sucesso | **164h** | **0** |
| `djen` | sucesso | 6,4h | **0** |
| `anpd` | **erro** | 0,3h | 0 |
| `stj` | sucesso | 104h | 2.595 |
| `planalto` | sucesso | 80h | 36 |

- **Três importadores de jurisprudência dormentes há ~7 dias e com zero registros em toda a história**, marcados `ativo: true`. Código morto em produção — e explicam parcialmente a cobertura zerada de jurisprudência no RAG (item 5.2).
- **`anpd` falha com `ultimo_erro: null`** — erro sem mensagem, impossível de diagnosticar pelo painel. Corrigir a captura da exceção **e** diagnosticar a falha real.
- **`[INVESTIGAR]` parser fail-safe:** `tjmg`, `lexml`, `normas_rfb` retornaram 0 quando disparados manualmente. A descrição da própria fonte TJMG diz *"parser tolerante fail-safe"* — um parser que retorna 0 sem erro é indistinguível de um que funcionou e nada achou. Instrumentar contagem de itens brutos recebidos **antes** do parsing.

## 3.3 — Exclusão de caso não cascateia `[ALTO]`

**Defeito confirmado:** ao excluir um caso (soft delete), suas peças **não** são cascateadas. Permanecem ativas, apontando para caso inexistente, e **seguem sendo contadas** em `/legal-docs/` e nas métricas de governança.

**Evidência:** o sistema reporta `pecas_total: 98`; o acervo real é **23**. As outras 75 são órfãs de casos já excluídos — inflação de **77%** em toda métrica de peças. Há **37 casos na lixeira**, cada um potencialmente deixando peças vivas.

**Implicação adicional:** peças de casos encerrados permanecem acessíveis e listáveis, o que tem efeito de retenção de dados (LGPD, art. 16).

**Correção:** cascatear (ou ao menos marcar como órfãs e excluir das métricas) peças, documentos e prazos ao arquivar/excluir um caso. Adicionar verificação de integridade que detecte filhos apontando para pais inexistentes.

## 3.4 — Vínculos ausentes entre registros `[ALTO]`

| Caso | Documentos | Prazos |
|---|---|---|
| DPT-2026-0021 / 0018 / 0016 / 0015 / 0014 / 0008 | **0** | **0** |
| DPT-2026-0007 | 2 | 1 |
| DPT-2026-0005 | 8 | **0** |

**6 de 8 casos sem nenhum documento. 7 de 8 sem nenhum prazo.** Adicionalmente, `GET /documents/` retorna 19 documentos, dos quais **7 (37%) sem `case_id`** — existem no GED mas não aparecem ao abrir o caso.

`[INVESTIGAR]` Determinar se é falha de vinculação no upload, comportamento esperado para documentos gerais do escritório, ou perda de vínculo. **Todos os 8 casos estão parados em `triagem`** — nenhum jamais progrediu na jornada de 9 etapas, o que é coerente com o pipeline travado (2.1).

## 3.5 — Padrão de gravação não transacional `[ALTO]`

Cinco vínculos que deveriam existir e não existem — **não são cinco bugs independentes, é uma classe de defeito**:

| Vínculo | Estado |
|---|---|
| `LegalDoc.validacao_juridica.ai_log_id` ← `/validar` | nunca gravado (2.1) |
| `Caso.jurimetria` ← chance calculada e registrada em movimentos | `null` no caso, presente no log |
| `Caso.descricao_fatos` ← conversão Sala Jurídica → Caso | perdida na conversão |
| Peças ← exclusão de caso | não cascateia (3.3) |
| `oab_number` × `djen_oab_numero` | dois campos de OAB inconsistentes |

Investigar como **classe de defeito** no código (gravação entre registros relacionados fora de transação), não caso a caso.

## 3.6 — Conversão Sala Jurídica → Caso perde fatos `[ALTO]`

`POST /sala-juridica/{id}/converter` não transfere `descricao_fatos` nem evidências levantadas na conversa. É o fluxo mais central do produto (conversa natural → caso estruturado) e está quebrado. Corrigir o mapeamento de campos.

---

# FASE 4 — SEGURANÇA E CONFORMIDADE

## 4.1 — Conta fictícia com privilégio superadmin em produção `[CRÍTICO]`
```
homolog.qa.30421305017@depaulateixeira.adv.br | "HOMOLOG-FICTICIO Advogado QA" | role: superadmin
homolog.portal.30421305017@depaulateixeira.adv.br | role: cliente_externo
```
Há também 12 casos `HOMOLOG-FICTICIO-*` (DPT-2026-0009 a 0021) criados e excluídos entre 22 e 29/07/2026 — **rotina automatizada de homologação rodando contra o banco de produção**. Identificar a origem, rebaixar/desativar a conta, e propor (não executar sem aprovação) ambiente de staging separado.

## 4.2 — Métrica de "chance de êxito" `[CRÍTICO]`
```js
// CasoDetalhe-CWyLfvJU.js
{n.jurimetria.chance_sucesso_percent ?? "—"}%    // percentual em destaque + barra de progresso
// EntrevistaInteligente-DX4iaR7n.js
label: "Chance de êxito (estimativa interna)"
tone: percentual >= 70 ? "green" : ...
```
Em uso ativo: `GET /movimentos/recentes` mostra 8 de 15 registros com `chance≈82%`, `chance≈60%`, `chance≈0%`.

**Risco:** o Código de Ética da OAB veda promessa de resultado (art. 6º, parágrafo único, e art. 34, XXIX).

1. **Urgente:** inspecionar o payload de todos os endpoints `/portal/*` (especialmente `/portal/casos/{id}` e `/portal/meus-casos`). **Se qualquer variante do percentual for serializada ao cliente externo, remover imediatamente.**
2. Padronizar a ressalva "(estimativa interna)" em **toda** superfície — `CasoDetalhe` hoje exibe só o número e a barra.
3. `[INVESTIGAR]` o log registra a chance calculada mas `GET /cases/{id}` retorna `"jurimetria": null`.

## 4.3 — Citação normativa incorreta na interface `[ALTO]`

O sistema cita o **"Provimento OAB 205/2021"** como fundamento da revisão humana de IA. **Verificado na fonte oficial: a ementa é "Dispõe sobre a publicidade e a informação da advocacia"** — norma de marketing jurídico, não trata de IA nem institui dever de revisão de peças.

Substituir por fundamento correto — **Lei 8.906/94, art. 32** (responsabilidade do advogado) e, quando aplicável, **Resolução CNJ nº 615/2025, art. 19, § 3º**. **Validar os dispositivos com o advogado responsável antes de aplicar.** Onde não houver norma aplicável, reescrever o aviso sem citação.

## 4.4 — Ausência de exclusão definitiva (LGPD) `[ALTO]`
```
GET  /trash/?entidade=cases      → 200
POST /trash/cases/{id}/restaurar → existe
DELETE /trash/cases/{id}         → 404
POST /trash/cases/{id}/purgar    → 404
```
Não há purga em nenhum nível, nem para `superadmin`. Sem caminho pela aplicação para atender pedido de eliminação (Lei 13.709/2018, art. 16 e art. 18, VI).

Implementar purga restrita a `superadmin`, auditável (motivo mínimo de 5 caracteres, seguindo o padrão do soft-delete; responsável e timestamp em trilha imutável), com salvaguarda de guarda obrigatória. **Peça a política de retenção ao advogado responsável antes de codificar prazos — não arbitre.**

---

# FASE 5 — VALOR JÁ CONSTRUÍDO E NÃO ENTREGUE

## 5.1 — Quinze calculadoras jurídicas sem interface `[ALTO — maior ganho rápido da auditoria]`

Rotas **implementadas e funcionais** (respondem 200, ou 422 pedindo parâmetros) que **nenhuma tela do sistema expõe**:

| Área | Endpoints órfãos |
|---|---|
| Cível | `/civel/ferramentas/` → `calculo-dano-moral`, `partilha-divorcio`, `alimentos-calcular`, `usucapiao-verificar`, `prescricao-consumidor`, `prazos-contestacao`, `rescisao-locacao` |
| Empresarial | `/empresarial/ferramentas/` → `juros-mora`, `prazos-rj`, `verificar-cade` |
| Penal | `/penal/ferramentas/` → `dosimetria`, `prescricao-penal`, `prescricao-punitiva`, `prazos-processuais`, `verificar-anpp` |

Dosimetria da pena, prescrição penal, verificação de ANPP, cálculo de dano moral, partilha de divórcio — ferramentas de uso diário. **Valor já construído e pago, a um trabalho de frontend de distância.** Priorizar acima de boa parte da Fase 6.

## 5.2 — Curadoria da base de conhecimento `[ALTO — trabalho contínuo]`

```
GET /rag/governanca/cobertura → 36 áreas: 29 "crítica" (score 20/100), 6 "atenção", 1 "boa"
                                 score médio 26,1/100
```
Nas áreas críticas, *súmulas*, *jurisprudência* e *doutrina* estão zeradas.

**Já tentado e insuficiente:** `POST /sumulas/ingerir-seed` funciona (27 súmulas, 24 indexadas) mas o seed nativo cobre só 2 áreas. Ampliar muito. Perguntar ao usuário quais áreas concentram o volume real de casos antes de priorizar.

## 5.3 — Higiene da base RAG `[MÉDIO]`
`GET /rag/governanca/saude`: **1.375 documentos com status legal não verificado**, 18 grupos de conflito, 14 de duplicidade, 525 fontes desatualizadas, 100 alertas `critical` de qualidade.
- Resolver os 1.375 **antes** de reindexar (2.2) — evita vetorizar norma revogada.
- `[INVESTIGAR]` um grupo de "duplicados" reúne três acórdãos do STJ com números distintos (REsp 2201422, 2200477, 2205262) sob o mesmo hash. Verificar se o hash é calculado sobre trecho insuficientemente específico.

## 5.4 — Erro jurídico recorrente nas skills — ✅ **RESOLVIDO em 2026-08-14 (PR #1015)**
Em ao menos 2 skills: decadência descrita como **"extinção sem julgamento de mérito"**. Incorreto — decadência e prescrição extinguem **com resolução de mérito** (CPC, art. 487, II).

**Corrigido, com defesa em profundidade** — verificado por execução em 2026-08-22 (35 testes e 54 subtestes passando; `tests/test_juridico_guardrails_decadencia.py`, `test_ai_logs_guardrail_leitura.py`, `test_skills_expansion_seed.py`):

- guardrail determinístico ligado na **geração** (`ai_skill_service.py`);
- e também na **leitura** (`routers/ai.py`) — resposta antiga e errada já gravada em log é corrigida ao ser lida, o que fecha o passivo e não só o fluxo novo;
- atualização forçada do prompt das duas skills afetadas (`seeds`).

A ressalva `[INVESTIGAR]` sobre citação conjunta de CC art. 206, § 3º, II com CDC art. 26 **não foi verificada** e segue aberta: é questão de conteúdo jurídico, não de guardrail.

> Este item ficou marcado `[ALTO]` em aberto por oito dias depois de resolvido. Quem o lesse nesse intervalo refazia trabalho pronto — ou mantinha represada a liberação do plano de lançamento que dependia dele.

## 5.5 — Camada de IA da extração de documentos indisponível `[ALTO]`
`POST /entrada-universal/processar` funciona na camada determinística (OCR, classificação, dedup), mas em 2 testes retornou `analise_ia.alertas: ["A interpretação por IA ficou indisponível..."]` com `partes`, `dados_pessoais`, `resumo_executivo`, `estrategia`, `datas_eventos` vazios.

**Pista importante:** a telemetria mostra **100% de sucesso e 0 falhas** em 30 dias — a falha **não está sendo registrada como tentativa**. Investigar se a rota chega a invocar o provider ou falha antes (ex.: guardrail de PII bloqueando silenciosamente — o documento de teste continha CPF). **Possível relação direta com 2.3.**

---

# FASE 6 — CONSISTÊNCIA TÉCNICA E DÍVIDA

## 6.1 — Prefixo `/v1/` duplicado `[ALTO]`
```
GET /api/v1/despesas                      → 404
GET /api/v1/v1/despesas                   → 200   ← caminho real
GET /api/v1/v1/office-contracts           → 200
GET /api/v1/v1/office-contracts/expiring  → 200
GET /api/v1/v1/partner-withdrawals        → 200
GET /api/v1/v1/regulatorio/digest-semanal → 200
GET /api/v1/v1/kanban-columns             → 200
```
`baseURL` do frontend é `/api/v1` e esses módulos chamam `/v1/despesas` por cima. Funciona por acidente. **O `Mapa de Módulos` registra `/api/v1/despesas` — documenta um caminho que não funciona.** Qualquer integração externa ou teste que siga o padrão documentado falha.

## 6.2 — Observabilidade `[MÉDIO]`
- Sem coletor de erros persistente. Habilitar **Sentry** (`SENTRY_DSN`) — recomendado pelo próprio painel. Pré-requisito do item 1.4.
- **Performance:** latência média 20,7s, chegando a **86s** em `auditoria_peca` e **71s** em `elaboracao_peca`. Custo total de IA: **R$ 15,14/mês** — custo não é restrição para melhorar qualidade ou latência.
- **502 intermitente:** `GET /analise-bancaria/modalidades` levou 30,5s (502) numa chamada e 18,7s (200) na seguinte. Ultrapassa o timeout do Nginx de forma instável.
- **Feedback com zero avaliações** desde sempre (`GET /ai/logs/feedback/resumo` → `{"util":0,"nao_util":0,"total_avaliados":0}`). Tornar o controle visível.

## 6.3 — Painéis de diagnóstico divergentes `[MÉDIO]`

| Fonte | Provedores | Modelo Anthropic |
|---|---|---|
| `/diagnostico/central` | "2: anthropic, groq" | — |
| `/ai/core/status` | 3 | — |
| `/ai/status` | — | `claude-haiku-4-5` |
| `/system-modules/integrations` | 3 + ollama | `claude-opus-4-8` |
| `/ia-governanca/provedores` (telemetria real) | 3 ativos | **`claude-opus-4-8`** (48 chamadas) |

**A telemetria é a fonte de verdade.** `/ai/status` e `/diagnostico/central` estão errados. Divergência também no modelo Groq (`openai/gpt-oss-120b` vs `llama-3.3-70b-versatile`).

**Bug relacionado:** `/diagnostico/central` reporta `backup_offsite` como **`desligado`** na lista de integrações e **`ok` / `BACKUP_ENABLED=true`** como subsistema, na mesma resposta. Gera incerteza real sobre se há backup. Corrigir **e confirmar manualmente o estado real do backup.**

## 6.4 — Superfície de API duplicada `[MÉDIO]`
Toda rota responde igualmente sob `/api/` e `/api/v1/`. Qualquer regra baseada em path (rate limiting, WAF, logging, cache Nginx, telemetria de rota) precisa cobrir as duas ou pode ser contornada. Eleger prefixo canônico e responder `301` no outro.

## 6.5 — Rotas órfãs e mapa incompleto `[MÉDIO]`
Cruzamento de 358 chamadas do frontend × 453 rotas do backend: **cobertura de 53,4%**, **211 rotas nunca chamadas** por nenhuma tela, **116 chamadas do frontend não registradas no mapa** (testadas, a maioria funciona — o `endpoints_detectados` **subdetecta**). Revisar as 211: expor, depreciar ou remover. Corrigir a subdetecção do mapa.

## 6.6 — Taxonomia de áreas duplicada (4 manifestações) `[ALTO]`
1. `areaCatalog` central existe, mas 5 módulos redefinem lista local: `CadastroManual`, `FinanceiroWorkspace`, `RaioXProcesso`, `RamoBase`, `RamosHub`.
2. Backend aceita `licitacoes` como área de primeiro nível.
3. `GET /rag/governanca/cobertura` retorna **36 "áreas"** contando `"Administrativo"` e `"administrativo"` como distintas — **distorce a métrica que orientaria investimento em conteúdo**.
4. Frontend e backend divergem.

Fonte única de verdade, com normalização case-insensitive na agregação de cobertura. **Decisão pendente do usuário:** reclassificar `licitacoes` como subárea de `administrativo` (Lei 14.133/2021 — procedimento da Administração, não ramo autônomo). **Confirmar antes de alterar.**

## 6.7 — Itens menores
- **Título com colchetes:** `POST /cases/` com `[` ou `]` → `{"detail":"Título inválido — resposta de IA não parseada"}`. Confirmado por teste A/B. Sanitizar ou trocar por validação determinística.
- **Mensagens não localizadas:** `DELETE /checklists/templates/{id}` e `GET /sociedade/distribuicao` retornam `{"detail":"Forbidden"}` em inglês, enquanto o resto usa português específico.
- **Permissão assimétrica:** advogado cria prompt (que nasce `publico: true`) mas não pode excluir a própria publicação. Permitir ao autor excluir o próprio conteúdo.
- **Semântica HTTP:** ID não-UUID retorna `404`; deveria ser `422` (usar tipo `UUID` do Pydantic).
- **`robots.txt`** retorna o `index.html` do SPA. Servir estático com `Disallow: /`.
- **Acessibilidade:** 44 de 68 bundles sem nenhum `aria-*`. **Os 7 do Portal do Cliente têm zero.** Começar pelo Portal.
- **Design:** duas paletas coexistem (dourado `#d4af37`/`#fff5e6` e slate `#2563eb`/`#0f172a`) sem tokens nomeados. Confirmar a oficial com o usuário.
- **Descobribilidade:** Auditoria e Governança da IA só por atalhos no Dashboard. Existe enum `ativo/beta/legado/oculto` modelado e não usado na navegação.
- **Cadastros:** `/sociedade/socios` vazio (impede distribuição); `/honorarios-oab/tabela` → `{"disponivel":false}` (sem base para teto ético); `oab_number` null para os 3 advogados; `/noticias` retorna timestamp Unix em vez de ISO 8601.

---

# FASE 7 — VERIFICAÇÃO FINAL

1. Dashboard e listagens com números **coerentes entre si** (casos, peças, clientes, prazos)
2. Criar cliente → criar caso (**título com colchetes**) → anexar documento via `/entrada-universal/processar` → confirmar partes e datas preenchidas pela IA
3. Gerar peça → qualificação **sem `[PREENCHER]`**
4. Conferir e assinar em **uma** ação → exportar PDF
5. Excluir um caso de teste → confirmar que suas peças **não** continuam contadas
6. Portal do Cliente: caso aparece e **nenhuma métrica de chance de êxito** é exposta
7. `GET /rag/stats` → `chunks_indexados` > 47.000
8. `GET /diagnostico/central` → `status_geral: "ok"`, sem subsistema em alerta
9. Disparar uma fonte de ingestão e confirmar que retorno 0 **gera alerta**
10. Suíte de testes completa

---

# NÃO FAZER

- **Não remova o registro do ato de conferência humana** sobre peças. A consolidação do item 2.4 é de *etapas*, não de responsabilidade. O registro de quem conferiu, quando e sobre qual versão evidencia a diligência do advogado sob a **Lei 8.906/94, art. 32**.
- **Não desative os guardrails de PII.** Se bloquearem demais, a correção é habilitar o modelo local (2.3), não desligar a proteção.
- **Não "corrija" contadores mascarando o problema.** O item 1.1 se resolve fazendo o contador refletir a realidade — não zerando a outra métrica para que coincidam.
- Não invente citação legal, jurisprudência, provimento ou artigo em texto gerado.
- Não rode migration destrutiva sem dry-run e aprovação.
- Não faça deploy em produção sem aprovação do usuário.
- Não trate `[INVESTIGAR]` como diagnóstico fechado — a auditoria não teve acesso ao código-fonte.

---

## PRIORIDADE CONSOLIDADA

| # | Item | Efeito |
|---|---|---|
| 0 | 0.2 — verificar DJEN manualmente | Risco de prazo perdido (ação humana) |
| 1 | 1.1 a 1.3 — contadores e filtros | Elimina a percepção de "sistema confuso e rota errada" |
| 2 | 2.1 — vínculo `ai_log_id` | Destrava as peças e a exportação de PDF |
| 3 | 2.2 — embeddings + reindex | Melhora toda resposta de IA |
| 4 | 2.3 — modelo local | Elimina `[PREENCHER]`, atende CNJ 615/2025 |
| 5 | 3.1 — alertar por resultado | Impede que a próxima falha silenciosa passe 30 dias despercebida |
| 6 | 4.2 — chance de êxito no Portal | Risco ético/disciplinar |
| 7 | 5.1 — expor as 15 calculadoras | Maior ganho de valor por esforço |

---

## NOTA DE RETIFICAÇÃO (v1 → v2)

A v1 deste prompt afirmava, no item 1.1, que **"97 de 98 peças"** estavam travadas. **O número estava inflado.** A auditoria verificou depois que **75 daquelas peças eram órfãs geradas pela própria exclusão dos 25 casos de teste da auditoria** — o acervo real é de **23 peças, 22 sem revisão**.

O bug do `ai_log_id` (item 2.1) **permanece real e crítico**, mas com alcance uma ordem de grandeza menor. A investigação desse erro revelou, por sua vez, o defeito de **ausência de cascata na exclusão de casos** (item 3.3), que é legítimo e afeta permanentemente todas as métricas de peças do sistema.
