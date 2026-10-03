# Auditoria da jornada do caso e proposta de simplificação — 03/10/2026

**Escopo:** caminho completo de um caso, da entrada ao protocolo e acompanhamento,
lido no código da `main` em `4c03f86`.
**Natureza:** documento de diagnóstico. Não altera código, schema nem contrato.
**Referência anterior:** `docs/auditoria/reduzir-atrito.md`. Este documento
confere o que daquele plano foi entregue e o que ainda produz atrito.

**Restrição de projeto:** nenhuma proposta enfraquece os mecanismos de inteligência
e controle do EJC: HITL do snapshot e da peça, gate de citações, gates do Motor
de Peça (checklist bloqueante e termo inicial confirmado), `sigilo_reforcado`,
crítica adversarial, sanitização de PII, `ai_gateway`, RBAC e trilha de auditoria.
A simplificação vale para a **apresentação e a coordenação** do fluxo, não para o
**rigor** dele.

---

## 1. Sumário executivo

O plano de julho/agosto foi entregue em boa parte. Hoje existem uma porta de
entrada única (`/entrada`), quatro estados de caso, o caso tratado como espaço
de trabalho (5 seções), a rota `/jornada` reduzida a um redirecionamento e as
abas de Estratégia consolidadas.

O atrito que sobrou tem outra origem. O caso passou a ser descrito por
**seis taxonomias de progresso que convivem e não se conversam**. Duas delas
estão **dessincronizadas no código**, ou seja, o sistema mostra estados
contraditórios do mesmo caso. Na prática, o advogado vê ao mesmo tempo "Aberto"
(status), "Produção da peça" (orquestrador), "Honorários aprovados — bloqueada"
(jornada de 16 etapas) e "Peça" (barra de contexto).

**Tese central:** a próxima simplificação deve **unificar o modelo de
progresso**, e não cortar funcionalidades. Uma fonte de verdade (o estado
derivado dos artefatos) e uma única forma de apresentá-la: os 4 estados mais um
**checklist de "falta para avançar"** com os atos humanos. Toda a inteligência
continua no lugar. O que sai é a redundância.

---

## 2. Mapa da jornada atual (como o código está)

### 2.1 Entrada: cinco caminhos que criam `Case`

| # | Caminho | Ponto de criação | Snapshot de inteligência | Status automático |
|---|---|---|---|---|
| E1 | Entrada Jurídica (`/entrada`, IA) | `services/entrada_service.py:1028` | sim | sim |
| E2 | Cadastro manual (`/entrada?modo=manual` → `CadastroManual`) | `routers/cases.py:378` (`POST /cases/`) | não | não |
| E3 | Raio-X → "Abrir caso" | `services/raio_x_service.py:719` | sim | não |
| E4 | Sala Jurídica → "Converter em caso" | `services/legal_chat_service.py:1161` | sim | não |
| E5 | `NovoCasoWizard` (residual em `pages/Casos.tsx:886`) | `POST /cases/` | não | não |

Atalhos que ainda saem da "porta única": `DashboardUltra.tsx:666/686/759`
apontam para `/cadastro-manual?aba=caso` em vez de `/entrada?modo=manual`.
O `NovoCasoWizard` e o `FlowEnhancements.tsx:161` ainda navegam para
`/casos/:id/jornada`, um salto de redirecionamento desnecessário.

**Avaliação:** a interface já converge para uma porta única. No backend, porém,
seguem existindo quatro rotinas de montagem de `Case` com efeitos colaterais
diferentes: snapshot, auditoria e transição de status. É aqui que nasce a
divergência de estado descrita no §3.

### 2.2 Trabalho no caso: abas e seções

- `pages/CasoDetalhe.tsx:83`: **25 abas** em `TABS`.
- `config/caseNav.ts`: **5 seções** (Visão, Atividades, Documentos, Estratégia,
  Financeiro). Atividades sozinha agrupa 9 abas.
- `CasoDetalhe.tsx:929`: **7 abas primárias** (Visão geral, Timeline,
  Documentos, Estratégia, Peças, Prazos, Financeiro), mais um menu "Mais".
- Rotas irmãs: `/casos/:id/entrevista` (página separada) e `/ajuizamento`
  (módulo global, fora do caso).

### 2.3 Produção e protocolo: dois trilhos

- **Trilho A:** peça (`LegalDoc`) → revisão/aprovação → `PATCH /legal-docs/{id}/protocolo`
  (registro manual de protocolo). Dispara `peca_protocolada`
  (`routers/legal_docs.py:1152`).
- **Trilho B:** `/ajuizamento` → `JudicialFiling` com **15 estados**
  (`services/ajuizamento/estados.py`) → `registro_protocolo.vincular_ao_caso`
  (`services/ajuizamento/registro_protocolo.py:62`). Marca a peça como
  `protocolada`, mas **não** dispara a transição de status do caso.

---

## 3. Achados

Severidade: **A** = estado contraditório ou dado incorreto; **M** = atrito
relevante; **B** = higiene.

### A1 — Seis taxonomias de progresso para o mesmo caso (A)

| # | Taxonomia | Fonte | Cardinalidade | Onde aparece |
|---|---|---|---|---|
| T1 | `CaseStatus` (persistido) | `models/case.py:42` | 4 + 2 terminais | listagem, kanban, dashboards |
| T2 | Estado do orquestrador (derivado) | `legal_case_orchestrator.py:252` | 10 | Visão (próxima ação) |
| T3 | Jornada linear | `legal_case_orchestrator.py:537` `montar_jornada` | **16 etapas** | `OrquestradorPanel.tsx:475` |
| T4 | Fluxo da barra de contexto | `CaseContextBar.tsx:31` | 7 | faixa persistente "Modo Caso" |
| T5 | Seções de navegação | `config/caseNav.ts` | 5 | página do caso e dock |
| T6 | Estados de `JudicialFiling` | `ajuizamento/estados.py` | 15 | `/ajuizamento` |

Além delas, há `PecaStatus` (6 estados, `models/legal_doc.py:24`), que é
legítimo por ser estado de outro objeto.

O modelo de "4 estados + tarefa opcional" (`models/case.py:42-55`, decisão do
Bloco 3) foi implementado em T1. A jornada de 16 marcos (T3) continua visível e
reintroduz exatamente o que aquela decisão queria eliminar: "marco não cumprido
gera culpa" (`reduzir-atrito.md` §5).

### A2 — Jornada de 16 etapas é estritamente linear e trava em etapas opcionais (A)

`montar_jornada` marca como etapa atual a **primeira não concluída**, sem
considerar o que já foi feito adiante. Exemplo reproduzível pela leitura de
`legal_case_orchestrator.py:582-590`: num caso com peça redigida e aprovada,
mas sem proposta de honorários aprovada (contratação feita fora do sistema ou
caso pro bono), a etapa atual aparece como **"Honorários aprovados pelo
advogado — bloqueada"**, enquanto o estado do orquestrador (T2, "mais avançado
vence") aponta "Revisão" ou "Protocolo". A mesma tela mostra duas respostas
diferentes à pergunta "onde está o caso?".

### A3 — `CaseStatus` não acompanha a produção feita pelo Motor de Peça (A)

`status_transicao.avancar_status_por_evento(..., "peca_criada")` só é chamado
em `routers/legal_docs.py:460` (criação manual de peça). O caminho principal de
IA, `peca_service.gerar_peca_pipeline` (`services/peca_service.py:771`, usado
por `/motor-peca/gerar`), cria o `LegalDoc` com `case_id` (`:1371`) **sem**
disparar a transição. Consequência: o caso continua "Aberto" ou "Em instrução"
na listagem e nos dashboards (`modules/dpt360/dashboard_service.py:42`,
`services/case_health.py:27`) enquanto o orquestrador já diz "Produção".

### A4 — Protocolo via Ajuizamento não leva o caso a "Protocolado" (A)

`registro_protocolo.vincular_ao_caso` atualiza o processo, a peça
(`PecaStatus.protocolada`) e a timeline, mas não chama
`avancar_status_por_evento(..., "peca_protocolada")`. O trilho A chama
(`legal_docs.py:1152`). O mesmo ato jurídico produz efeitos diferentes conforme
a tela usada.

### A5 — Caminhos de criação com efeitos colaterais divergentes (M)

Ver tabela do §2.1. E3 e E4 gravam snapshot, mas não passam por
`status_transicao`. E2 e E5 não gravam snapshot. Um caso aberto pelo Raio-X com
documentos já vinculados continua "Aberto" até alguém vincular outro documento
pela GED.

### M1 — Navegação dentro do caso ainda em três camadas (M)

São 7 passos na barra (T4), 5 seções (T5), 7 abas primárias e 25 abas no total.
Os 7 passos da barra **não** coincidem com as 5 seções: "Provas" aponta para
uma aba da seção Documentos, "Estratégia" para `dossie`, "Revisão" para
`pecas#revisao`, e "Ajuizamento" sai do caso. Para o mesmo destino há três
rótulos diferentes ("Estratégia", "Teses", "Dossiê Estratégico").

### M2 — Ajuizamento fora do caso (M)

O protocolo, último passo da jornada, é o único que obriga o advogado a sair do
caso (`/ajuizamento`, `CaseContextBar` `external: true`). Isso contraria a
diretriz "o caso é o sistema" (`reduzir-atrito.md` §3).

### M3 — Entrevista Inteligente como página separada (M)

`/casos/:id/entrevista` é uma rota própria, exposta como link na seção Visão.
Funcionalmente, é mais uma forma de alimentar a base fática do caso, o mesmo
papel da Entrada Jurídica.

### B1 — Resíduos de rotas históricas (B)

`NovoCasoWizard` (E5), atalhos para `/cadastro-manual` no dashboard e
navegações para `/casos/:id/jornada` (`FlowEnhancements.tsx:161`,
`NovoCasoWizard.tsx:213`, `DefesasRevisoesPanel.tsx:544`). Nada disso quebra o
uso, mas mantém portas e saltos que a decisão de porta única pretendia fechar.

---

## 4. O que está certo e deve ser preservado

- **Estado derivado de artefatos** (`legal_case_orchestrator.py`): fail-safe, sem
  flag mutável, sem chamada nova de LLM, e não aprova nada sozinho. É o melhor
  candidato a fonte única de verdade.
- **Transições de status "só para frente"** (`status_transicao.py`): têm a
  semântica correta. Falta apenas que todos os chamadores a usem.
- **Atos humanos explícitos:** aprovar snapshot, aprovar tese, aprovar
  proposta, confirmar termo inicial, aprovar peça, aprovar ajuizamento
  (`READY_FOR_REVIEW → APPROVED` só por advogado).
- **Gates do Motor de Peça** (checklist bloqueante e prazo criado só com termo
  confirmado) e o **gate de citações** (`citacoes_verificadas`, CR-15).
- **Máquina de estados do Ajuizamento** (T6): é estado técnico do
  peticionamento eletrônico, legítimo e auditável. Não deve ser fundida ao
  status do caso. Deve apenas **refletir** nele.

---

## 5. Proposta de simplificação

### Princípio

> **Uma verdade, uma régua, uma lista.** O estado é derivado dos artefatos
> (verdade). O caso mostra 4 estados (régua). O que falta para avançar aparece
> como lista de atos e pendências, nunca como trilho de marcos.

### S1 — Fonte única de progresso (resolve A1, A3, A4, A5)

1. Criar um único ponto de sincronização, por exemplo
   `status_transicao.sincronizar_com_artefatos(db, case)`, que mapeia o estado
   derivado (T2) para `CaseStatus` (T1) **só para frente**:

   | Estado do orquestrador (T2) | `CaseStatus` (T1) |
   |---|---|
   | entrada, compreensao, classificacao | `aberto` |
   | validacao_processual, estrategia, contratacao | `em_instrucao` |
   | producao, revisao, protocolo | `em_producao` |
   | acompanhamento | `protocolado` |

   Atenção: `aberto → em_instrucao` hoje ocorre por **documento vinculado**
   (`TRANSICOES_POR_EVENTO`). Esse evento deve ser mantido como gatilho
   adicional, para não regredir o comportamento atual.
2. Chamar essa função (na mesma transação) nos pontos que criam ou alteram
   artefatos: `gerar_peca_pipeline`, `registro_protocolo.vincular_ao_caso`,
   `raio_x_service` (converter), `legal_chat_service` (converter) e
   `entrada_service`.
3. Teste de regressão (regra 7 do `CLAUDE.md`): para cada caminho, o status
   esperado após o evento.

**Custo:** baixo, apenas backend. Sem migration e sem mudança de contrato.
**Risco:** baixo, porque a transição nunca regride e nunca toca estados
terminais.

### S2 — Substituir a jornada de 16 etapas por "falta para avançar" (resolve A2)

Manter `montar_jornada` no contrato da API por compatibilidade, mas parar de
exibi-la como trilho na Visão. No lugar, `OrquestradorPanel` mostra:

- **Régua de 4 estados** (T1, agora sincronizado pela S1), com o estado atual
  destacado;
- **"Para avançar"**: as `pendencias` que `proximo_passo` já calcula
  (`aprovacao_humana`, `checklist`, `prazo`, `ato_externo`), cada uma com o
  botão que leva ao ato;
- **"Opcional neste estado"**: as etapas da jornada ainda não concluídas que
  **não** bloqueiam o estado atual (honorários, kit, teses), sem rótulo de
  "bloqueada".

Nenhum ato humano deixa de ser exigido. Muda apenas a apresentação: em vez de
16 marcos em sequência, o advogado vê a pendência real.

### S3 — Uma navegação no caso (resolve M1)

- **Remover os 7 passos de `CASE_WORKFLOW`** da `CaseContextBar` e usar nela a
  régua de 4 estados mais a próxima ação. As 5 seções de `caseNav.ts` passam a
  ser a única navegação.
- Padronizar os rótulos: "Estratégia" é a seção; dentro dela ficam "Teses",
  "Indicadores", "Dossiê" e "Ferramentas".
- As 25 abas e os deep-links ficam como estão (`LEGACY_CASE_TAB_REDIRECTS` já
  resolve os antigos).

### S4 — Ajuizamento como aba do caso (resolve M2)

Adicionar a aba `ajuizamento` na seção **Documentos**, ao lado de Peças,
reutilizando o componente `Ajuizamento` filtrado pelo `case_id`. Esse é o mesmo
padrão já usado para `pecas`, que reaproveita o componente canônico. A página
global `/ajuizamento` continua existindo como visão transversal ("todos os
ajuizamentos pendentes"). Para não exigir deploy em caso de rollback, a aba
entra atrás de flag, no padrão de `config/w3Tabs.ts`.

### S5 — Entrevista como modo da Entrada (resolve M3)

A Entrevista Inteligente passa a abrir dentro do caso, como painel da seção
Visão ("Complementar fatos"), em vez de rota separada. A rota
`/casos/:id/entrevista` vira redirecionamento, no mesmo padrão da `/jornada`.

### S6 — Higiene de portas (resolve B1)

- `DashboardUltra`: atalhos `/cadastro-manual?aba=caso` → `NOVO_CASO_MANUAL_PATH`.
- Navegações para `/casos/:id/jornada` → `/casos/:id?tab=resumo`.
- Avaliar a remoção do `NovoCasoWizard` depois de confirmar que
  `resolverModoNovoCaso` não tem outro consumidor.

---

## 6. Resultado esperado

| Medida | Hoje | Após S1–S6 |
|---|---|---|
| Taxonomias de progresso visíveis ao advogado | 4 (T1, T2, T3, T4) | 1 régua (T1, sincronizada com T2) |
| Estados contraditórios possíveis na mesma tela | sim (A2, A3, A4) | não, por construção (S1) |
| Telas fora do caso entre a entrada e o protocolo | 2 (`/entrevista`, `/ajuizamento`) | 0 |
| Navegações paralelas no caso | 3 (passos, seções, abas) | 1 (seções → abas) |
| Atos humanos obrigatórios (HITL) | 6 | 6, sem alteração |
| Gates (citações, checklist, termo inicial, sigilo) | todos | todos, sem alteração |

---

## 7. Ordem recomendada e portões

| Ordem | Item | Camada | Portão (CLAUDE.md) | Depende de |
|---|---|---|---|---|
| 1 | S1 (sincronização de status) + testes de regressão | backend | `ruff` + `pytest` da área + suíte completa | — |
| 2 | S2 (painel "para avançar") | frontend | lint + test + build | S1 |
| 3 | S3 (barra de contexto com 4 estados) | frontend | lint + test + build | S1 |
| 4 | S6 (higiene de portas) | frontend | lint + test + build | — |
| 5 | S4 (aba Ajuizamento, atrás de flag) | frontend | lint + test + build; **security-auditor** (RBAC da aba) | — |
| 6 | S5 (Entrevista embutida) | frontend | lint + test + build | — |

S1 é pré-requisito real: sem ele, qualquer simplificação visual apenas mostra
um estado incorreto de forma mais limpa.

---

## 8. Limitações desta auditoria

- **Análise estática.** Os achados A2, A3 e A4 foram derivados da leitura do
  código, não de execução contra banco. Os testes de regressão da S1 devem
  reproduzi-los antes da correção.
- **Uso real não medido.** Não houve passagem de caso real pelo método de
  `reduzir-atrito.md` §8, e as hesitações de interface não foram observadas.
  Recomenda-se fazer essa passagem depois da S1–S3.
- **Ramos especializados fora do escopo.** As tabelas satélite 1:1 com `cases`
  (`empresarial_cases`, `civel_cases`, `penal_cases`, `trabalhista_cases`,
  `admin_cases`, `bancario_cases`, além de `EnvironmentalCase`) não foram
  avaliadas. A decisão #1900 já trata ramo como metadado e é revisável em
  15/12/2026.
