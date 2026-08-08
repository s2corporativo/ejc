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
| §18 | Sem job de expurgo LGPD para pré-casos | `retention_until` só em model/router/service do Raio-X; nada em `app/tasks/`; Sala sem campo equivalente | **PR #803 aberto (F4)** — purga por inatividade + paridade de retenção na Sala |
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

Ordem de integração proposta, um PR por vez, resolvendo conflito em cascata a cada merge:

1. **#757** (P0 segurança) — rebase sobre `main` (está `dirty`; o conflito provável é com o
   merge do #786 em `raio_x.py`). Primeiro da fila por ser o único P0 de segurança.
2. **#791** (F1a) — fecha P0-3 e os P1 da Sala.
3. **#795** (F1b) — fecha P0-2. Pequeno e independente de arquivo do #757 (router × service).
4. **#797** (F2) — depende de `raio_x.py`/`legal_chat.py` estáveis pós 1–2.
5. **#803** (F4) — traz migration 140; conferir `alembic heads` no momento do rebase (o
   encadeamento citado nos PRs já divergiu ao longo da semana: 131 → 138 → 140/142).
6. **#805** (F3) → **#807/#810** (F3.2) — a fusão de UX só depois de tudo acima verde.
7. **#788** (plano) — atualizar a branch e integrar a qualquer momento; é referência documental.
8. **#812** (F5) — **não** entra no trem até o titular responder a Issue #799 (seção 5).

Critério de pronto da Fase A: `main` com F1a–F4 integradas, CI verde, e os três P0 do relatório
irreproduzíveis via API.

### Fase B — lacunas que nenhum PR cobre (semana 1–2, em paralelo com o fim da Fase A)

- **B1 — contador `prazos_pendentes` (P1-1)**: Issue + PR pequeno. Trocar
  `DeadlineStatus(Deadline.status) == DeadlineStatus.pendente` por comparação SQL direta
  (`Deadline.status == DeadlineStatus.pendente`), **remover o `except` que converte erro em 0**
  (logar e propagar, ou devolver `null` explícito — "erro" ≠ "nenhum prazo") e cobrir com teste
  de regressão que falharia contra o código atual. Auditar no mesmo PR os `except Exception → 0`
  vizinhos do mesmo bloco de resumo (`cases.py:398-399` idem para honorários).
- **B2 — cópia física na conversão do Raio-X (§15.2)**: após F2 integrada, substituir
  `shutil.copy2` (`raio_x_service.py:576`) por movimentação/referência controlada no pipeline
  canônico, eliminando duplicação de conteúdo sensível em disco. Risco médio (transferência
  documental); exige `security-auditor` e teste do fluxo de conversão ponta a ponta.
- **B3 — painel de governança por resposta (§17)**: verificar o que resta após o item 5 do #791
  (que já expõe `aviso_hitl`, crítica e citações). O painel consolidado
  (fontes/verificadas/pendentes/confiança + "ver validações") vira Issue de UX na Fase D se
  ainda fizer sentido após o #791.

### Fase C — serviço canônico de criação de caso (§15.1) — decidir com critério, não por impulso

O relatório pede `CasoCreationService`; o PR #795 adiou deliberadamente ("refatoração
especulativa sem um segundo achado concreto"). Os dois têm razão em tempos diferentes.
Proposta de critério objetivo para resolver a tensão:

- **Gatilho 1**: surgir o **segundo** defeito de divergência entre portas *após* F1a+F1b
  integradas (o primeiro foi `proxima_acao`).
- **Gatilho 2**: a F3.2 precisar mexer nos conversores de qualquer forma — nesse caso a
  extração do serviço único entra na mesma janela, pagando o custo uma vez só.

Enquanto nenhum gatilho dispara, a equivalência entre portas é garantida por **teste de
contrato**: um teste que cria caso pelas quatro portas e afirma o mesmo conjunto de invariantes
(cliente, `proxima_acao`, movimento inicial, auditoria, snapshot quando IA, documentos
vinculados, evento emitido). Esse teste é barato, entra na Fase B e transforma "as quatro portas
divergem" de risco silencioso em quebra de CI.

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
- **D5 — Matriz Fato × Prova (§15.3)**: funcionalidade **nova**, não correção. O substrato certo
  é o estado jurídico da Sala (fatos/provas/contradições já versionados) e, se o titular aprovar
  a F5, o schema `preliminares`. Issue própria com proposta de design antes de código.

### Fase E — poda final e telemetria (última)

Redirects já nascem no #805; manter. Antes de apagar qualquer rota/endpoint legado, medir uso
real (a infra `route_usage_metrics` existe desde a migration 122) por um ciclo de uso e podar
só o que estiver comprovadamente morto — mesmo critério que o #791 aplicou ao código sem
consumidor.

---

## 5. Decisões que cabem ao titular

1. **Ordem de integração da Fase A** — aprovar a fila proposta (ou reordenar). Sem isso os 9
   PRs continuam em draft se acumulando conflito entre si.
2. **F5/#812** — responder as 4 perguntas da Issue #799 (vale o esforço agora? abordagem A/B?
   volume real? discriminador na UI?). Recomendação desta avaliação, alinhada ao relatório
   (§22) e ao próprio #812: **não integrar F5 antes de F1–F4 estarem em produção estáveis**.
3. **Fase C** — aceitar o critério de gatilhos para o `CasoCreationService` ou mandar executar
   já (custo maior agora, com F3 ainda em voo).
4. **Matriz Fato × Prova (D5)** — prioridade relativa: é a única peça do relatório que é
   feature nova, e concorre por janela com o critério de lançamento ("um advogado leva um caso
   real ao protocolo").
5. **Painel de governança (B3/D-UX)** — validar se a exposição do #791 basta ou se quer o
   painel consolidado por resposta.

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
