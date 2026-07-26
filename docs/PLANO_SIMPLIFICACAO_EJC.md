# Plano de simplificação e fluidez do EJC

> Documento de plano. Não é procedimento operacional nem relatório histórico.
> Cada fase corresponde a um PR independente, com rollback próprio.

## Diagnóstico em uma frase

**O EJC já tem o advogado. Ele está enterrado na navegação.**

O sistema não precisa de novos módulos para "agir como advogado". Precisa expor
o que já foi construído e ligar o que ficou desconectado.

## Achados que orientam o plano

Todos verificados no código em 25/07/2026, não em relatórios anteriores.

| # | Achado | Evidência |
|---|---|---|
| 1 | O orquestrador jurídico já é uma máquina de 10 estados que conduz o caso de ponta a ponta e nunca aprova sozinha | `backend/app/services/legal_case_orchestrator.py` — `proximo_passo()`, `montar_jornada()`, `avancar()`, `ACOES_APROVACAO_HUMANA` |
| 2 | O orquestrador está exposto como **aba nº 2 de 26** no workspace do caso | `frontend/src/pages/CasoDetalhe.tsx:83-113` |
| 3 | A página "Jornada do caso" e a aba "Orquestrador" consomem **o mesmo serviço** | `montar_jornada()` e `proximo_passo()` vivem no mesmo módulo |
| 4 | Os 4 modos de produção (Livre/Guiado/Molde/Agente) existem, têm testes e doc — mas **nenhum router os usa** | `peca_workflow_service.py` só é chamado em `tests/`; doc reconhece a pendência em `docs/ai/PECAS_MODOS_PRODUCAO_CONTROLADOS.md:99` |
| 5 | A UI envia o modo como **texto solto no prompt**, sem nenhuma validação determinística | `PecaGeneratorModal.tsx:538-560` → `instrucoes_adicionais: "[modo_producao=molde]"` |
| 6 | A barra canônica (PR #451) e a página do caso usam **rótulos diferentes** para a mesma navegação | Barra: Visão/Atividades/Arquivos/Estratégia/Financeiro · Página: Resumo/Andamentos/Documentos e provas/Estratégia/Financeiro/Histórico |

## Princípio: conectar, não criar

O modo de falha recorrente do EJC não é falta de recurso — é criação de módulo
paralelo em vez de consolidação do existente:

```
sala_de_guerra  →  sala_de_guerra_v3  →  /sala-analise   (três superfícies)
teses           →  teses_v4                              (shim de compat)
data_room       →  data_room_v4                          (shim de compat)
```

O commit `170bf17` (24/07) adicionou a terceira sala — 962 linhas — enquanto a
consolidação das duas primeiras seguia pendente.

**Regra deste plano:** nenhuma fase cria módulo, router, tabela, migration ou
página nova. Toda entrega é composição, ligação ou remoção.

---

## Contratos e padrões a respeitar

Nenhuma entrega deste plano define contrato novo. Os quatro contratos exigidos
já existem no EJC e são de uso obrigatório:

| Contrato | Onde já vive | Regra |
|---|---|---|
| **Acesso ao caso** | `core/ownership.py` → `verificar_acesso_caso()` | 404 se inexistente; gestão passa; equipe passa se responsável ou auxiliar; caso órfão só à gestão |
| **IA** | `services/ai_gateway.py` | Toda chamada passa pelo gateway. Nunca provider direto de router; nunca PII não sanitizada; nunca sem HITL e citation gate |
| **Documental / proveniência** | `models/rag.py` | `KnowledgeDoc`: fonte, tribunal, `base_rag`, `client_id`, `case_id`, `chave_origem`, `hash_conteudo`, `versao`, `vigente`, revisor. `KnowledgeChunk`: `pagina` |
| **Auditoria** | `AILog` + `models/audit_log.py` → `criar_audit_log()` | Usuário, ação, entrada/saída, custo, aprovação — sem dado sensível em log |

### Correção de premissa: o EJC é single-tenant

Não existe `organization_id` em nenhum model. O escritório é um só (De Paula
Teixeira). O eixo de isolamento é `client_id` / `case_id` combinado ao gate de
ownership — é o que `_FILTRO_ESCOPO_RAG` aplica e o que `test_rag_isolation.py`
protege.

Introduzir `organization_id` agora criaria um conceito sem lastro no schema —
exatamente o segundo padrão paralelo que se quer evitar. Multi-escritório, se
vier, é decisão de produto com migration própria, não premissa de contrato.

### Padrão de feature flag

O repositório já tem convenção estabelecida em `core/config.py`: sufixo
`_ENABLED`, tipado em pydantic-settings, default `False` para tudo que é
externo ou incompleto (`WHATSAPP_ENABLED`, `DATAJUD_ENABLED`,
`LANGFUSE_ENABLED`…).

Novas flags seguem esse padrão — **não** o prefixo `FEATURE_*`, que seria uma
segunda convenção para a mesma coisa.

## O que já existe (não paralelizar)

Levantamento de 25/07 dos seis itens comumente propostos como "seguros para
começar agora em paralelo". Cinco já estão construídos:

| Item | Situação | Evidência |
|---|---|---|
| Catálogo de ferramentas | Existe | `TabFerramentas`, skill catalog, prompts por área |
| Formulários guiados | Existe | `GuiadoForm.tsx` + 9 tipos de peça mapeados na doc |
| Biblioteca de prompts versionada | Existe | `models/prompt_juridico.py` (campo `versao`), routers `prompts.py` e `prompts_juridicos.py` |
| Modo Molde — núcleo lógico | Existe | `peca_workflow_service.py` + `ConfiguracaoMolde` (preservar/substituir) |
| Auditor de citações | Existe | `verificador_jurisprudencia.py` — 4 estados + `citation_gate.py` |
| **Perfil de escrita** | **Não existe** | Nenhuma ocorrência no backend ou frontend |

Construir os cinco primeiros "como serviços isolados em paralelo" produziria a
duplicação que este plano existe para evitar. O trabalho real neles não é
construção — é **ligação** (Fase 2).

**Perfil de escrita** é o único item genuinamente novo. Como é tabela nova e não
toca tabela central, pode correr em paralelo com segurança, atrás de flag
`PERFIL_ESCRITA_ENABLED=false`, consumido pelo pipeline via `ai_gateway`.

### Não há uma segunda frente

Em 25/07 os PRs abertos são #475 (correção P0 de isolamento na conversão
Sala/Raio-X → caso) e #476 (este plano). Não existe branch de refatoração
estrutural concorrente.

A consequência prática é que a coordenação necessária não é entre duas equipes,
e sim **sequencial dentro de uma só frente**: #475 toca conversão de caso e
titularidade de cliente, então a Fase 1 deve rebasear sobre ele antes de mexer
em `CasoDetalhe.tsx`.

## Fase 1 — O caso abre com a próxima ação

**Objetivo:** o advogado entra no caso e vê o que fazer agora, sem procurar.

### O que muda

A aba **Visão** passa a ser a superfície de decisão, composta por:

1. **Próxima ação** — `proximo_passo()` do orquestrador, com as ações
   disponíveis como botões. Ações de ato jurídico continuam recusadas pelo
   `avancar()` e redirecionadas ao endpoint humano próprio.
2. **Jornada** — `montar_jornada()`, embutida. A rota `/casos/:id/jornada`
   permanece válida (deep-link), mas deixa de ser destino primário.
3. **Alertas** — prazos urgentes e risco.
4. **Dados do caso** — processo, área, valor, abertura: linha recolhível.

A aba "Orquestrador" deixa de existir como aba: seu conteúdo é a Visão.

Os rótulos da página passam a ser os cinco da barra canônica:

```
Visão · Atividades · Arquivos · Estratégia · Financeiro
```

As 26 abas viram **filtros dentro das cinco seções**, não destinos. "Histórico e
encerramento" (só `memoria`) é absorvido por Atividades.

### Arquivos

- `frontend/src/pages/CasoDetalhe.tsx` — `TABS`/`GROUPS`
- `frontend/src/pages/JornadaCaso.tsx` — passa a compor, não a ser página-destino
- `frontend/src/components/OrquestradorPanel.tsx` — promovido à Visão

### Critérios de aceite

- [ ] Entrar em `/casos/:id` mostra a próxima ação sem clique adicional
- [ ] Todos os deep-links `?tab=` antigos continuam resolvendo
- [ ] `/casos/:id/jornada` continua respondendo (não quebra favoritos)
- [ ] Barra canônica e página usam os mesmos cinco rótulos
- [ ] Nenhum endpoint novo; nenhuma chamada de IA nova

**Risco:** baixo — frontend apenas. **Rollback:** reverter o PR.

---

## Fase 2 — A produção passa a ser controlada de verdade

**Objetivo:** os quatro modos deixam de ser rótulo e passam a ser contrato.

Esta é a fase de maior risco jurídico pendente. Hoje o advogado escolhe "Molde"
e o sistema **não** executa detector de resíduos, **não** valida `hash_conteudo`
e **não** impede que dados do cliente anterior sobrevivam na peça nova.

### O que muda

Ligar `peca_workflow_service` ao `/pecas/gerar`, exatamente como a doc já
especifica (`PECAS_MODOS_PRODUCAO_CONTROLADOS.md:99-112`):

1. validar role e acesso ao caso (como já faz)
2. montar `ProducaoModoRequest`
3. chamar `preparar_modo_producao()`
4. retornar 409/422 quando houver bloqueio
5. anexar `instrucoes_pipeline` às instruções
6. chamar o pipeline de sete etapas existente
7. registrar modo, referência do molde e aprovação no `AILog`

Consequências diretas:

- **Molde** — exige `documento_id` + `versao` + `hash_conteudo`; rejeita campo
  simultaneamente preservado e substituído; roda detector de resíduos antes de
  liberar
- **Agente** — bloqueia a redação enquanto faltar `case_id` autorizado,
  documento considerado ou aprovação explícita do plano
- **Guiado** — bloqueia geração com campo obrigatório vazio
- `[modo_producao=...]` deixa de trafegar como texto no prompt

### Arquivos

- `backend/app/routers/peca_geracao.py` — integração
- `backend/app/services/peca_workflow_service.py` — detector de resíduos
- `frontend/src/components/PecaGeneratorModal.tsx` — enviar modo estruturado,
  tratar 409/422

### Critérios de aceite

- [ ] Modo Agente recusa redigir sem plano aprovado (teste negativo)
- [ ] Modo Molde recusa molde sem `hash_conteudo` (teste negativo)
- [ ] Detector de resíduos barra nome/CPF/nº de processo do caso de origem
- [ ] Modo, molde e aprovação registrados em `AILog` sem dado sensível
- [ ] Nenhum endpoint público paralelo de geração criado
- [ ] HITL e citation gate preservados

**Risco:** médio — toca o caminho de geração. **Rollback:** o service é aditivo;
reverter a integração restaura o comportamento atual.

---

## Fase 3 — Uma biblioteca, uma estratégia

**Objetivo:** eliminar superfícies concorrentes sem remover capacidade.

### O que muda

**Arquivos** — `documentos`, `provas`, `contratos`, `procuracoes` deixam de ser
quatro abas e viram uma biblioteca com filtro de tipo:

```
Todos · Provas · Peças · Contratos · Procurações · Do cliente · Processuais
```

**Estratégia** — absorve `teses`, `teses-sugeridas`, `jurisprudencia`,
`precedentes`, `risco`, `score`, `dossie`, `ferramentas` em quatro blocos:

```
Estratégia atual · Riscos e cenários · Fundamentos e precedentes · Próximos passos
```

**Sala de Guerra** — CONCLUÍDO/SUBSTITUÍDO (PR #489, 2026-07): as três
superfícies (`sala_de_guerra`, `sala_de_guerra_v3` e `/sala-analise`) foram
removidas; `/sala-analise` foi absorvida pelo Raio-X e a porta de entrada
conversacional passou a ser a **Sala Jurídica** (`/sala-juridica`), com estado
probatório versionado e conversão controlada em caso.

**IA Defensiva** deixa de ser aba: `ContextualAIAssistant` já é persistente e
muda de comportamento conforme a seção.

### Critérios de aceite

- [ ] Nenhuma capacidade removida — só reagrupada
- [ ] Rotas antigas redirecionam, não retornam 404
- [x] Um único prefixo de Sala montado no `main.py` — resolvido pelo PR #489:
      as Salas de Guerra foram removidas e substituídas pela Sala Jurídica
      (`/api/sala-juridica`)
- [ ] Testes de rota/link do `moduleRegistry` verdes

**Risco:** médio — mexe em rota. **Rollback:** reverter o PR; sem migration.

---

## Fase 4 — Confiança e certificação

**Objetivo:** fechar o que impede a certificação. Não é UI.

- **Vigência na citação** — cruzar `KnowledgeDoc.vigente`/`versao` com o
  verificador, acrescentando o estado "possivelmente desatualizada" aos quatro
  existentes (`verificada`/`identificada`/`suspeita`/`generica`)
- **E2E dos fluxos jurídicos** — intimação → prazo → tarefa → agenda → conclusão
  (P0: erro aqui gera preclusão) e documento → estratégia → tese → peça → revisão
- **IDOR e segregação** — testes negativos por entidade, sobre o isolamento já
  auditado (`test_rag_isolation.py`)
- **Backup, restore e rollback** — comprovação real, não documental
- **Confirmar `EMBEDDINGS_ENABLED` na VPS** — o default no código é `true`
  (`config.py:473`); relatórios antigos citam `false` no `.env` de produção

**Risco:** baixo em código, alto em descoberta — espere achados.

---

## O que este plano não faz

| Descartado | Motivo |
|---|---|
| Redesign visual (Linear/Notion/Vercel/Raycast) | Custo alto, risco de regressão, zero impacto na certificação pendente |
| "Unificar em uma única IA" | `ai_gateway.py` já é núcleo único obrigatório; o que existe são múltiplas entradas de UI, resolvidas nas Fases 1 e 3 |
| Ramo do Direito que "muda tudo" | Reescrita ampla para ganho percebido baixo |
| Criar leitor de autos | É o Raio-X (`raio_x.py`): OCR, páginas, tipo, extração, revisão humana, conversão em caso |
| Criar Central de Integrações | É a Central de Diagnóstico (`/diagnostico/central`), com semáforo por integração |
| Criar busca global | `CommandPalette.tsx` já existe |
| Criar contrato de proveniência | `KnowledgeDoc` já tem fonte, tribunal, base, escopo, versão, vigência, revisor; `KnowledgeChunk` tem `pagina` |
| MinIO, Dramatiq, fine-tuning, WhatsApp oficial, APIs pagas | Custo recorrente ou dependência nova sem uso diário comprovado |

## Sequência e dependências

```
Fase 1 (fluidez)  ──┐
                    ├──> Fase 3 (consolidação)  ──> Fase 4 (certificação)
Fase 2 (controle) ──┘
```

Fases 1 e 2 são independentes e podem correr em paralelo. A Fase 3 depende das
duas: só faz sentido remover superfície depois que a superfície principal está
boa e a produção está controlada. A Fase 4 fecha.

**Ordem recomendada:** Fase 2 primeiro se o critério for risco jurídico; Fase 1
primeiro se o critério for adoção pelo escritório.

**Pré-requisito comum:** rebasear sobre o PR #475 antes de iniciar, porque ele
altera a conversão Sala/Raio-X → caso e a titularidade de cliente.

## Processo de integração

Cada fase segue o mesmo ciclo:

```
rebase sobre main  →  implementar atrás de flag  →  testes  →  PR draft
   →  revisão  →  merge  →  homologação  →  ativar flag gradualmente
```

Ativação gradual da flag, nesta ordem: administradores → homologação → casos de
teste → usuários específicos → geral.

Migrations exigem coordenação explícita. Tabela nova é de baixo risco; alterar
tabela central (`cases`, `clients`, `users`, `legal_docs`, `deadlines`) durante
outra frente ativa exige que as duas frentes estejam cientes — hoje a única
frente concorrente é o PR #475.
