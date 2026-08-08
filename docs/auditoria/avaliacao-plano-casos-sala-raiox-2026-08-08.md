# Avaliação do relatório "Casos × Raio-X × Sala Jurídica" (2026-08-08) e plano de implementação consolidado

**Origem**: relatório de auditoria externa (somente leitura) entregue pelo titular via chat em
2026-08-08, avaliado contra o código do `main` (commit `50cb9c4`) e contra os PRs abertos do
repositório. Issue desta tarefa: #815.

**Método**: cada achado P0/P1 do relatório foi conferido diretamente no arquivo, na data desta
avaliação. Nenhuma afirmação abaixo depende só do relatório — onde o código diz outra coisa, o
código prevalece e a divergência está registrada.

---

## 1. Veredicto sobre o relatório

**O relatório é tecnicamente correto no essencial.** Todos os achados P0/P1 foram confirmados no
`main` atual (evidências na seção 2). A tese arquitetural — Caso como núcleo, Entrada como porta
única, Sala e Raio-X como modos contextuais, sem fusão física de tabelas agora — é sólida e
coincide com a direção que o repositório já tomou.

**O ponto cego do relatório é não ter visto o trabalho em voo.** Ele propõe uma sequência de 8
etapas (§21) como se nada tivesse começado, mas o plano de fusão já existe
(`docs/PLANO_FUSAO_CASO_UNICO.md`, PR #788) e **7 das 8 etapas propostas já têm PR aberto**
(seção 3). O valor real deste relatório está em:

1. **Revalidação independente** — dois auditores distintos, sem se verem, chegaram aos mesmos
   P0/P1 com a mesma priorização. Isso eleva a confiança no plano em execução.
2. **Detalhamento de UX que os PRs ainda não cobrem** — consolidação da Estratégia (§12),
   timeline única de Atividades (§10), Arquivos em dois destinos (§11), navegação de menu (§20),
   painel de governança por resposta (§17) e a Matriz Fato × Prova (§15.3).
3. **Nomear a tensão do serviço canônico de criação** (§15.1) — que o PR #795 adiou
   deliberadamente e que precisa de um critério objetivo de decisão (seção 4, Fase C).

**Correções e nuances ao relatório** (o veredicto dos achados não muda, mas o registro precisa
ser preciso):

- **Mass assignment (P0)**: o laço de `setattr` de nível superior do `PATCH /raio-x/{id}`
  (`routers/raio_x.py:386-387`) itera um schema Pydantic fechado (`RaioXUpdate`,
  `schemas/raio_x.py:26-46`) — é allowlist por construção. O vetor real é o dict livre
  `revisao_humana: dict[str, Any]`: o laço de `revisao_humana.identificacao`
  (`raio_x.py:394-399`) faz `hasattr`/`setattr` em **qualquer** atributo do model (`status`,
  `created_by`, `deleted_at`, `id`...). O PR #757 documenta e corrige exatamente isso.
- **`retention_until` (§18)**: não é gatilho de expurgo — é **piso de retenção**
  (`routers/raio_x.py:786-787` bloqueia exclusão *antes* do prazo, salvo gestão). O relatório
  acerta que não há job de expurgo no `main`, mas a política correta é a do PR #803: purga por
  **inatividade**, sempre respeitando o piso.
- **Área "civil" e fallback `??` da Sala (P1)**: confirmados no `main`, mas ambos já corrigidos
  no PR #791 (F1a), ainda não integrado.
- **`proxima_acao` na conversão do Raio-X (P0)**: confirmado no `main`, já corrigido no PR #795
  (F1b), ainda não integrado. Detalhe que reforça a tese das quatro portas: a porta da Sala
  (`legal_chat_service.py:910-913`) **já** tem a guarda G1 com default; só a do Raio-X ficou
  para trás.

**Conclusão da avaliação**: não criar um plano paralelo. O plano de implementação correto é
**(a) destravar e integrar o trem de PRs existente, (b) fechar as lacunas que nenhum PR cobre,
(c) transformar as recomendações de UX do relatório em Issues sequenciadas após a fusão F3**.

---

## 2. Mapa achado → evidência → estado

Verificação feita em 2026-08-08 sobre o `main` (`50cb9c4`). "PR aberto" significa: correção
existe, mas **não** está no `main`.

| # | Achado do relatório | Evidência no `main` | Estado |
|---|---|---|---|
| P0-1 | Mass assignment via `revisao_humana.identificacao` no PATCH do Raio-X | `routers/raio_x.py:394-399` (`hasattr`→`setattr` sobre dict livre) | **PR #757 aberto — em conflito (`mergeable_state: dirty`), precisa rebase** |
| P0-2 | Caso convertido do Raio-X nasce sem `proxima_acao` → primeiro PATCH legítimo dá 422 | `services/raio_x_service.py:700-720` (construtor sem o campo) × `routers/cases.py:440-447` (guarda G1) | **PR #795 aberto (F1b)** |
| P0-3 | `PATCH /cases/{id}` aceita `status=encerrado/arquivado` contornando gates dedicados (RBAC do `/arquivar`, pós-mortem do `/encerrar`, aprendizado institucional) | `routers/cases.py:449-467`; o próprio código admite em `cases.py:497-498` que o aprendizado só dispara no fluxo canônico | **PR #791 aberto (F1a)** |
| P1-1 | `prazos_pendentes` sempre 0: `DeadlineStatus(Deadline.status)` falha na construção da query e o `except` devolve 0 | `routers/cases.py:401-409` | **LACUNA — nenhum PR aberto corrige** |
| P1-2 | Conversão da Sala inicia área fixa em `"civil"`; `area_sugerida` nunca aplicada | `SalaJuridica.tsx:264` (`useState("civil")`); `abrirWizard()` em `:487-504` não seta área | **PR #791 aberto (F1a)** |
| P1-3 | Fallback de fatos usa `??`: `resumo === ""` bloqueia o workspace | `SalaJuridica.tsx:493-495` | **PR #791 aberto (F1a)** |
| §15.1 | Quatro portas de criação de `Case` com efeitos divergentes | `cases.py::criar`, `entrada_service.py`, `legal_chat_service.py:902`, `raio_x_service.py:700` | **Parcial**: F1a+F1b igualam o comportamento essencial; unificação estrutural adiada pelo #795 — ver Fase C |
| §15.2 | Pipeline documental duplicado; Raio-X copia arquivo fisicamente na conversão | `raio_x_service.py:11,576` (`shutil.copy2`) | **Parcial**: PR #797 (F2) unifica validação/gravação de upload; a cópia física na conversão **permanece** — ver Fase B |
| §17 | Sinais de governança (crítica/citações/HITL) invisíveis na UI da Sala | Backend devolve `aviso_hitl`/`critica_adversarial`/`citacoes`; frontend descartava | **PR #791 aberto (item 5)**; painel consolidado por resposta segue como evolução — Fase D |
| §18 | Sem job de expurgo LGPD **para Sala e Raio-X** | `retention_until` só em model/router/service do Raio-X; Sala sem campo equivalente. **Correção a este documento** (achado do review Codex, conferido em 2026-08-08): o expurgo canônico de pré-caso **existe** — `services/entrada_expurgo_service.py:41::expurgar_rascunhos_entrada_unica`, agendado em `scheduler.py:484-490`, com salvaguardas de conversão e ownership. Minha varredura só olhou `app/tasks/` e por isso a conclusão original ("sem job de expurgo para pré-casos") era ampla demais. A lacuna real é específica de Sala/Raio-X, e a F4 deve **reusar ou estender** esse serviço, nunca criar purga paralela que duplique ou perca aquelas salvaguardas | **PR #803 aberto (F4)** — purga por inatividade + paridade de retenção na Sala |
| §5/§13 | Sala e Raio-X como modos da Entrada, saída do menu, redirects | — | **PRs #805 (F3), #807/#810 (F3.2) abertos** |
| §12/§10/§11/§20 | Consolidação de Estratégia, Atividades, Arquivos e navegação | — | **LACUNA — sem PR; vira Fase D** |
| §15.3 | Matriz Fato × Prova | — | **LACUNA — funcionalidade nova; vira Fase D** |
| §22 | Não fundir tabelas agora | PR #812 (F5 fase 1) cria schema unificado `preliminares` **aditivo**, sem migrar dado nem mudar UI | **Tensão a decidir pelo titular** — #812 depende das 4 respostas da Issue #799 |

---

## 3. Estado do trem de PRs (2026-08-08)

| PR | Fase | Conteúdo | Estado |
|---|---|---|---|
| #757 | P0 segurança | Allowlist em `revisao_humana.identificacao` | Draft, **em conflito com `main`** (base antiga) |
| #788 | Plano | `docs/PLANO_FUSAO_CASO_UNICO.md` | Draft, **atrás do `main`** (`behind`) |
| #791 | F1a | Gates arquivar/encerrar, área/fatos da Sala, HITL visível, FK `ai_log_id`, poda de código morto | Draft |
| #795 | F1b | `proxima_acao` na conversão do Raio-X | Draft |
| #797 | F2 | Serviço único de upload em lote (`upload_lote_service.py`) | Draft |
| #803 | F4 | Purga LGPD de preliminares abandonadas + retenção na Sala (migration 140) | Draft |
| #805 | F3 | Sala/Raio-X como modos de `/entrada`, redirects, saída do menu | Draft |
| #807, #810 | F3.2 | Caso como espaço de trabalho; despesas processuais | Draft |
| #812 | F5 fase 1 | Schema unificado `preliminares` (migration 142, aditiva) | Draft, **aguarda decisões da Issue #799** |

Observação de risco: quase todos tocam `raio_x.py`/`legal_chat.py`/`cases.py` — **cada merge
pode gerar conflito em cascata nos seguintes**. O sequenciamento abaixo minimiza isso.

---

## 4. Plano de implementação

A mudança visual vem **depois** dos defeitos estruturais — o relatório (§21) e o plano do #788
concordam nisso. Merge é automático pela esteira (`auto-integracao.yml`) com gates verdes; o ato
do executor é deixar cada PR pronto (rebase, conflitos, CI) e tirá-lo de draft na ordem; o
titular intervém apenas nas exceções do §6-A da governança e nas decisões da seção 5.

### Fase A — destravar e integrar o trem existente (semana 1)

Ordem **aprovada pelo titular em 2026-08-08** e já em execução. A revisão da sobreposição real de
arquivos (feita ao executar) mostrou que a fila **não precisa ser inteiramente serial**: só há
dependência onde dois PRs tocam o mesmo arquivo de produção.

| PR | Arquivos de produção | Conflita com |
|---|---|---|
| #757 | `routers/raio_x.py`, `schemas/raio_x.py` | #797 |
| #791 | `routers/cases.py`, `kanban.py`, `legal_chat_service.py`, `models/legal_chat.py`, migration 139 | #803 |
| #795 | `services/raio_x_service.py` | #803 |
| #805 | **só frontend** | ninguém |
| #797 | `routers/raio_x.py`, `routers/legal_chat.py`, `upload_lote_service.py` | #757, #803 |
| #803 | `legal_chat*`, `raio_x_service.py`, `scheduler.py`, migration 140 | #791, #795, #797 |

**Onda 1 — em paralelo** (nenhum arquivo em comum): **#757** (P0 segurança) · **#791** (F1a) ·
**#795** (F1b) · **#805** (F3, frontend puro). Executado: #757 teve o conflito com a `main`
resolvido por merge (não rebase — força não é usada), os quatro foram atualizados e tirados de
draft para a esteira integrar com gates verdes.

**Onda 2 — depois da onda 1** (dependência real de arquivo): **#797** (F2, espera `raio_x.py` do
#757) → **#803** (F4, espera #791/#795/#797) → **#807/#810** (F3.2).

**Fora do trem**: **#788** (documental, integra a qualquer momento) e **#812** (F5) — este
permanece retido até a decisão da Issue #799, conforme §22 do relatório e a própria ressalva do
PR.

**Migrations**: #791 traz a 139 e #803 a 140 sobre o head 138 — encadeamento consistente, mas o
head muda a cada merge da onda. Reconferir `python -m alembic heads` e
`MIGRATION_RESERVATIONS.md` imediatamente antes de cada integração da onda 2, renumerando se
necessário.

Critério de pronto da Fase A: `main` com **#757 e F1a–F4** (#791, #795, #797, #803) integrados,
CI verde, e os três P0 do relatório irreproduzíveis via API.

### Fase B — lacunas que nenhum PR cobre (semana 1–2, em paralelo com o fim da Fase A)

- **B1 — contador `prazos_pendentes` (P1-1)**: Issue + PR pequeno, em duas mudanças distintas e
  independentes dentro do mesmo PR:

  **(i) A correção do defeito**: trocar `DeadlineStatus(Deadline.status) == DeadlineStatus.pendente`
  por comparação SQL direta (`Deadline.status == DeadlineStatus.pendente`) em `cases.py:403-405`,
  **somada a `Deadline.deleted_at.is_(None)`** — `Deadline` tem soft-delete
  (`models/deadline.py:84`) e o laço geral de contadores (`cases.py:380-383`) já exclui excluídos;
  sem essa cláusula o contador consertado passaria a contar prazo apagado (achado do review Codex,
  conferido). Isso, somado, já faz o contador voltar a contar certo — o `except` deixa de ser
  alcançado no caminho normal.

  **(ii) O contrato de erro** (decisão fixada aqui para não ficar em aberto): em
  `GET /cases/{case_id}/resumo`, para **todos** os contadores — `prazos_pendentes`, os ~12 do laço
  de `cases.py:377-388` e `honorarios_valor_total` —, **`null` significa "contador indisponível" e
  `0`/`0.0` significa "contei e não há nenhum"**. Erro nunca mais vira `0`. O `except` permanece
  como rede para falha genuína de banco (um contador quebrado não pode derrubar um resumo que
  agrega ~14 contadores), mas passa a **registrar mensagem em nível `warning` e atribuir `None`**.
  Propagar 500 foi descartado justamente por esse motivo de robustez; `null` preserva a
  disponibilidade do resumo sem mentir sobre o dado. O contrato vale por inteiro a partir do PR do
  B1 — não se declara a uniformização concluída enquanto houver contador convertendo falha em zero.

  **Consumidores**: verificado em 2026-08-08 que **nenhum consumidor interno de `prazos_pendentes`
  foi encontrado** (`grep` em todo o repositório: só `routers/cases.py` e este documento; o
  `prazos_pendentes` de `services/visual_law_core.py:74` é outro parâmetro, sem relação). Isso
  cobre o repositório, **não** clientes externos, integrações ou scripts fora dele — antes de
  trocar `0` por `null`, levantar esse inventário; havendo consumidor numérico, versionar o
  contrato ou planejar migração em vez de mudar em silêncio. Onde `null` for adotado, a UI mostra
  "—", nunca zero.

  **Escopo do contrato**: uniformizar os três grupos de contadores no mesmo PR e **declarar os
  campos no `response_model`** (a rota hoje devolve dict solto, sem tipo declarado), tornando o
  `Optional` explícito no contrato.

  **Testes**: regressão cobrindo, **para cada contador**, (a) sucesso — inclusive prazo pendente
  soft-deleted, que não pode ser contado, em teste que falha contra o código atual; (b) falha —
  erro de banco simulado devolve `null` e não `0`, com o resumo ainda respondendo 200.
- **B2 — cópia física na conversão do Raio-X (§15.2)**: após F2 integrada, substituir
  `shutil.copy2` (`raio_x_service.py:576`) por movimentação/referência controlada no pipeline
  canônico, eliminando duplicação de conteúdo sensível em disco. Risco médio (transferência
  documental); exige `security-auditor` e teste do fluxo de conversão ponta a ponta.
- **B4 — completar a derivação do estado do caso** (pedido do titular, 2026-08-08: "vocabulário
  de estado fragmentado; definir um ciclo de vida único e cada módulo derivar dele"):

  **Verificação no `main` `50cb9c4` — o diagnóstico precisa de duas correções.** Primeira: o
  vocabulário de Casos não é "Aberto/Ativo/Arquivado". Desde a migration 126 são **seis** estados
  (`models/case.py:42-56`): `aberto` → `em_instrucao` → `em_producao` → `protocolado`, mais
  `encerrado` (desfecho) e `arquivado` (guarda). O trio "ativos/arquivados/todos" que aparece na
  tela (`Casos.tsx:317`) é o **filtro de arquivo**, não o status — e casa com o parâmetro do
  backend (`cases.py:93`). Segunda, e mais relevante: **o acoplamento já existe**.
  `services/status_transicao.py` deriva o estado do caso de eventos dos módulos —
  `documento_vinculado → em_instrucao`, `peca_criada → em_producao`,
  `peca_protocolada → protocolado` — sempre para frente, nunca regredindo, sem tocar terminais e
  registrando `CaseMovimento` na mesma transação. É exatamente a arquitetura pedida, e na direção
  certa: **quem sabe o fato é o módulo; o caso projeta**.

  **A lacuna real, então, não é vocabulário — é cobertura.** Só três eventos estão ligados, e só
  de documentos e peças: `avancar_status_por_evento` é chamado de `entrada_service.py:643`,
  `routers/legal_docs.py` e `routers/documents.py`, e **de mais nenhum lugar**. Prazos
  (`DeadlineStatus`: pendente/concluído/vencido/cancelado) e Atividades (`TaskStatus`:
  a_fazer/fazendo/concluida) não emitem nada — um caso com prazo vencido ou com todas as tarefas
  concluídas não move um milímetro. É por isso que "em que pé está o caso X" não se responde numa
  tela só, e não porque as três máquinas de estado existam.

  **Decisão de desenho: não unificar os três vocabulários.** Eles descrevem objetos diferentes e
  o de peças carrega o gate de HITL — `STATUS_EXIGE_REVISAO`/`STATUS_EXIGE_VALIDACAO`
  (`routers/legal_docs.py:39-40`) impedem peça gerada por IA de chegar a
  `aprovada`/`final`/`protocolada` sem revisão humana. Colapsar esse vocabulário no do caso
  destruiria a trava. O ciclo de vida único é o **do caso**, e ele é a **projeção** dos fatos dos
  módulos, cada um mantendo o vocabulário do seu domínio.

  **Trabalho**: (a) ligar os eventos que faltam ao `status_transicao` (prazo criado/cumprido,
  audiência marcada, tarefa concluída), mantendo os invariantes de nunca regredir e nunca tocar
  terminal; (b) expor a projeção em **uma** leitura — o cartão "Estado da instrução" da Visão
  (§9 do relatório), respondendo "o que falta" a partir dos mesmos fatos. Teste de regressão por
  evento, e nenhum evento novo pode regredir estado. Precede D1 e alimenta o D5.

- **B3 — painel de governança por resposta (§17)**: verificar o que resta após o item 5 do #791
  (que já expõe `aviso_hitl`, crítica e citações). O painel consolidado
  (fontes/verificadas/pendentes/confiança + "ver validações") vira Issue de UX na Fase D se
  ainda fizer sentido após o #791.

### Fase C — serviço canônico de criação de caso (§15.1) — decidir com critério, não por impulso

O relatório pede `CasoCreationService`; o PR #795 adiou deliberadamente ("refatoração
especulativa sem um segundo achado concreto"). O critério de gatilhos foi aprovado pelo titular
em 2026-08-08 — **e a verificação mostra que ele já disparou**.

**O gatilho já está satisfeito** (achado do review Codex, conferido no `main` `50cb9c4`): a
divergência entre as portas não se resume a `proxima_acao`. Confirmado lendo as quatro
implementações lado a lado:

| Porta | `CaseMovimento` inicial | Evento `caso.criado` |
|---|---|---|
| `cases.py::criar` (manual) | sim (`cases.py:297-300`) | sim (`cases.py:322`, `emitir_caso_criado`) |
| `entrada_service.py` (Entrada Única) | sim (`:630`) | **não** |
| `legal_chat_service.py` (Sala) | **não** | **não** |
| `raio_x_service.py` (Raio-X) | **não** | **não** |

São dois defeitos adicionais além do `proxima_acao`, não um: caso nascido de IA não entra na
linha do tempo e não aciona nenhum assinante do event bus (automação, triagem, kit documental).
Portanto **a Fase C deixa de ser condicional e passa a ser trabalho programado**, imediatamente
após a Fase A — que é justamente quando `raio_x_service.py`/`legal_chat_service.py` param de
estar sob PR ativo. O gatilho 2 (F3.2 tocar os conversores) continua valendo como reforço, não
como alternativa.

**Ordem dentro da Fase C**: primeiro **alinhar os invariantes** nas quatro portas (movimento e
evento nas que não têm), depois extrair o `CasoCreationService` — alinhar sem extrair já elimina
o defeito visível ao advogado; extrair sem alinhar só moveria a divergência de lugar.

O **teste de contrato** (quatro portas → mesmo conjunto de invariantes: cliente, `proxima_acao`,
movimento inicial, auditoria, snapshot quando IA, documentos vinculados, evento emitido) entra
**junto** com o alinhamento, não antes: escrito hoje ele reprovaria de saída, o que é o
diagnóstico correto mas não um CI utilizável. Escrito junto, transforma "as quatro portas
divergem" de risco silencioso em quebra de CI permanente.

### Fase D — consolidações de UX do relatório (após F3 integrada; uma Issue por item)

Pré-requisito comum: **extração de componentes antes de mover** (§19 do relatório) — o padrão do
#805 (prop `embutido`, componentes preservados) é o correto; não reescrever.

- **D1 — Estratégia como workspace único (§12)**: Teses sugeridas dentro de Teses;
  Jurisprudência+Precedentes → Pesquisa; Score+Índice de Risco → um card "Risco e Prognóstico"
  (metodologias internas preservadas); Dossiê → síntese do workspace; IA Defensiva → modo
  "atacar minha tese"; Ferramentas → menu contextual. Maior redução de superfície do relatório.
- **D2 — Atividades como timeline única com filtros (§10)**: Tudo · Processo · Prazo ·
  Audiência · Tarefa · Comunicação · Nota; tela especializada de Processos permanece.
- **D3 — Arquivos em dois destinos (§11)**: Documentos (filtros Provas/Contratos/Procurações/
  Outros) + Peças (workflow próprio).
- **D4 — Navegação do menu (§20)**: Sala/Raio-X já saem no #805; reorganização dos grupos
  (TRABALHO/INTELIGÊNCIA/GESTÃO/ADMINISTRAÇÃO) é mudança de `moduleRegistry.tsx` com redirects,
  só depois de D1–D3 estabilizarem os destinos.
- **D5 — Matriz Fato × Prova (§15.3)**: funcionalidade **nova**, não correção — aprovada para
  execução **após a Fase C** (seção 5, decisão 3). Substrato: o Estado Jurídico Canônico do caso
  (§16 do relatório), a partir do estado jurídico da Sala, que já versiona
  fatos/provas/contradições — **não** depende da F5. Regra de produto que a torna útil em vez de
  mais uma tela: cada linha carrega estado do fato (comprovado/alegado/inferência), prova que o
  sustenta, força, fonte e contestação previsível, e a IA **sugere** enquanto o advogado
  **aceita, rejeita ou corrige** — o aceito vira memória oficial do caso. Issue própria com
  proposta de design antes de código.
- **D6 — Painel de governança consolidado (§17)**: componente único de resposta de IA
  (fontes · verificadas · pendentes · confiança · aviso de revisão obrigatória), reutilizado pela
  Sala, pela Estratégia e pela Entrada. Entra **junto de D1** (seção 5, decisão 4), reaproveitando
  o que o #791 já expõe, em vez de criar um segundo componente de governança.

### Fase E — poda final e telemetria (última)

Redirects já nascem no #805; manter. Antes de apagar qualquer rota/endpoint legado, medir uso
real por um ciclo e podar só o que estiver comprovadamente morto — mesmo critério que o #791
aplicou ao código sem consumidor.

**Ressalva de medição** (achado do review Codex, conferido): a infra `route_usage_metrics` **não
serve, como está, para provar que as telas de Sala/Raio-X ficaram ociosas**. Ela monitora uma
allowlist fixa de endpoints (`services/route_usage.py:60-89`) e o próprio módulo documenta o
limite (`:29-36`): quando a mesma ação passa a existir também na tela consolidada, o contador
soma as duas origens e deixa de provar que a tela legada está parada. Como a F3 preserva os
componentes e só muda a navegação, os endpoints da Sala e do Raio-X continuarão sendo chamados
**pelos modos da Entrada** — contador alto não significa uso da rota legada. Para a Fase E valer,
é preciso primeiro **distinguir origem**: cabeçalho `X-EJC-Origem: entrada|legado` enviado pelo
frontend (o próprio módulo sugere esse desenho) ou analytics de navegação, e só então abrir a
janela de medição. Sem isso, o critério "comprovadamente morto" não é satisfazível para essas
rotas e a poda vira suposição.

---

## 5. Decisões — registro

Decisões do titular em **2026-08-08**, com o que foi delegado ao executor já resolvido aqui.

1. **Ordem de integração da Fase A** — **aprovada**. Executada na mesma data (ondas 1 e 2 da
   Fase A); a paralelização por sobreposição de arquivos foi decisão de execução, dentro da
   ordem aprovada, e reduz a espera sem criar conflito.
2. **Fase C / `CasoCreationService`** — critério de gatilhos **aceito**. Como a verificação
   mostrou que o gatilho **já disparou** (movimento e evento ausentes em Sala/Raio-X), a Fase C
   entra como trabalho programado logo após a Fase A, com o alinhamento dos invariantes antes
   da extração do serviço.
3. **Matriz Fato × Prova (D5)** — **delegada ao executor**. Decisão: **fazer, mas depois da
   Fase C**, e sobre o Estado Jurídico Canônico (§16 do relatório), não como tela nova. A razão
   é o próprio critério de lançamento: a matriz só entrega valor se os fatos e provas que ela
   cruza já forem os do caso oficial — construí-la antes de as quatro portas produzirem caso
   equivalente significaria alimentá-la com dado que a Fase C ainda vai mudar. Não depende da
   F5: o substrato é o estado jurídico da Sala, que já existe e já é versionado.
4. **Painel de governança (B3)** — **delegada ao executor**. Decisão: **o #791 basta para a
   Fase A** (ele já leva `aviso_hitl`, crítica adversarial e citações à UI da Sala, que era a
   lacuna real — governança produzida pelo backend e invisível ao advogado). O painel
   consolidado por resposta (fontes/verificadas/pendentes/confiança) entra na Fase D como
   componente único reutilizável, junto de D1, e **não** como trabalho separado: fazê-lo antes
   criaria um segundo componente de governança para reconciliar depois com a Estratégia.
5. **F5/#812** — **permanece com o titular**: as 4 perguntas da Issue #799 (vale o esforço
   agora? abordagem A/B? volume real? discriminador na UI?). Recomendação mantida, alinhada ao
   §22 do relatório e à própria ressalva do #812: **não integrar F5 antes de F1–F4 estáveis em
   produção**. É a única decisão que continua bloqueando trabalho.

## 6. Riscos do plano

- **Cascata de conflitos no trem** (alto): os PRs tocam os mesmos arquivos; mitigação é a
  integração estritamente sequencial da Fase A, com rebase imediatamente antes de cada merge.
- **Migrations concorrentes** (médio): 140 (#803) e 142 (#812) citam heads diferentes;
  reconferir `python -m alembic heads` e `MIGRATION_RESERVATIONS.md` a cada rebase.
- **Redesign antes da estabilização** (médio): D1–D4 só após Fase A completa — regra já
  acordada entre relatório e plano; não antecipar.
- **F5 sem decisão** (baixo enquanto #812 ficar em draft): risco só existe se integrar antes
  das respostas da #799.

## 7. Critério de pronto (herda o do repositório)

Um advogado leva um caso real do início ao protocolo dentro do sistema e considera que foi mais
fácil do que fazer fora dele — com **uma** porta de entrada, **um** caso como espaço de
trabalho, e Sala/Raio-X como ferramentas que ele não precisa nomear para usar.
