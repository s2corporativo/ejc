# 13 — UX e design (Fase 13)

> Avaliação sobre o código e a estrutura de navegação. **Sem stack de pé, não houve teste com
> usuário nem inspeção visual.** O que se avalia aqui é o que o código determina: quantos passos o
> fluxo exige, o que a interface informa quando algo falha, e se a IA aparece onde o trabalho
> acontece.

## 1. Fluxo ideal × fluxo atual

```
ideal:  Cliente → Caso → Estratégia → Produção → Prazo → Protocolo → Acompanhamento → Financeiro → Encerramento
```

Todas as nove etapas existem e são alcançáveis (ver `10-fluxo-juridico.md`). O problema **não é
ausência de etapa** — é dispersão, atrito e silêncio.

| Dimensão | Situação | Evidência |
|---|---|---|
| **Entrada unificada** | **construída e desligada** | `entrada_universal.py` (4 endpoints) + `entrada_universal_vinculo.py` existem, registrados por side-effect em `routers/__init__.py:24-25`, **sem nenhum consumidor no frontend**. A "entrada única" que o `docs/auditoria/reduzir-atrito.md` pede **já foi escrita** |
| **Cockpit do caso** | **existe** — `CasoDetalhe` com 8 abas + `CaseCommandDock` | ressalva grave: 6 abas falham em silêncio (§3) |
| **Dashboard acionável** | **PARCIAL** | `DashboardModern.tsx:394-428` monta `priorityItems` de dados reais (prazos críticos, do dia, solicitações pendentes) — é acionável. Mas `Promise.allSettled` (`:202-227`) descarta rejeições: **widget que falhou parece widget vazio** |
| **Clareza do menu** | **PARCIAL** | 42 rotas de staff em 8 grupos; **apenas 13 visíveis na navegação**, 29 ocultas. Descoberta depende de saber a URL |
| **Quantidade de módulos** | **excessiva** | 162 routers · 820 endpoints · **48 % sem consumidor localizável** (`03-mapa-dependencias.md` §5.2) |
| **Duplicidades** | 3 pares vivos | `/teses` vs `/teses-v4`, `/data-rooms` vs `/data-room-v4` (ambos já `deprecated=True`), `/bank-analysis` vs `/analise-bancaria` (**sem** `deprecated`) |
| **Navegação** | **FUNCIONAL** | registry único, 0 rotas duplicadas, 0 páginas órfãs, 35 redirects legados preservando URLs antigas |
| **Pesquisa** | **PARCIAL** | `search.py` (2 endpoints) **sem consumidor localizado** |
| **Filtros** | **FUNCIONAL** | `lib/list.ts` (43 dependentes) padroniza listagem/paginação |
| **Responsividade** | **[NÃO VERIFICADO]** | exige navegador |
| **Acessibilidade** | **[NÃO VERIFICADO]** | exige navegador e leitor de tela |
| **Consistência visual** | **FUNCIONAL** | design system próprio: `UI.tsx` (118 dependentes), `Toast.tsx` (86), Tailwind com paleta dourada em `tailwind.config.js`, `darkMode: "class"` |
| **Legibilidade** | **FUNCIONAL** | `Markdown.tsx` constrói elementos React em vez de `dangerouslySetInnerHTML` — decisão documentada (`:4`) |
| **Feedback** | **PARCIAL** | `Toast` bem distribuído, mas **41 pontos engolem o erro** (§3) |
| **Estados vazios** | **FUNCIONAL** | `EmptyState` presente em todas as páginas centrais |
| **Mensagens de erro** | **PARCIAL** | ver §3 |

## 2. Atrito medido

O `docs/auditoria/reduzir-atrito.md` descreve "15 passos × 8 módulos". O que o código confirma:

**Passos que já foram removidos** (crédito onde é devido):

- **PDF de leitura sem gate.** `legal_docs.py:1030+` — `GET /{doc_id}/pdf-minuta`. O comentário
  registra o raciocínio: *"até aqui o único PDF era o de protocolo, atrás dos gates de validação —
  ou seja, era preciso aprovar para poder ler, o que inverte a ordem do ato profissional"*.
  **É exatamente o tipo de correção que o critério de lançamento pede.**
- **Vocabulário de status unificado.** `core/status_caso.py` matou cinco definições incompatíveis de
  "caso ativo" — o Dashboard chegava a contar caso `arquivado` como ativo. O arquivo documenta:
  *"contador que discorda de listagem é falso positivo operacional: o titular vê 9 casos ativos e
  encontra 8"*.
- **Redirects legados** (35 entradas) preservam URLs antigas em vez de quebrar links salvos.

**Atrito que permanece:**

| # | Atrito | Custo para o advogado |
|---|---|---|
| 1 | **4 módulos com página morta** (Contratos, DataJud, Despesas, Kanban) | tenta, não funciona, **não sabe por quê** |
| 2 | **29 de 42 rotas ocultas da navegação** | funcionalidade existe e não é encontrada |
| 3 | **Entrada universal construída e não exposta** | o passo de unificação já pago não é usufruído |
| 4 | **Gate de citações sobre base possivelmente vazia** | peça não avança ao protocolo **sem mensagem que explique** |
| 5 | **6 abas do caso falham em silêncio** | conclui que não há parte/prova/prazo quando há |
| 6 | **`/produtividade` visível a todos, negada pelo backend** | clica, recebe "sem permissão", tela vazia |

## 3. A falha silenciosa é o maior problema de UX

**41 ocorrências** de `.catch(() => {})` / `} catch {}` em código de produção
(`09-frontend.md` §5). Concentração nas abas de `CasoDetalhe`: `TabResumo.tsx:147,383,465`,
`TabPartes.tsx:35,45`, `TabScore.tsx:23,33`, `TabRisco.tsx:52`, `TabProcessos.tsx:50`,
`TabMemoria.tsx:39`, além de `CasoDetalhe.tsx:300,529,557,646,650`.

> **Num sistema jurídico isso não é detalhe de UX — é risco material.**
> O advogado não distingue *"este caso não tem partes cadastradas"* de *"a chamada falhou"*.
> Numa conferência pré-protocolo, concluir que não há prazo, parte ou prova quando há tem
> consequência processual.

Somado ao P0 do `/v1` — que também se manifesta como **lista vazia, não como erro** — o sistema
tem uma propriedade perversa: **quando quebra, parece apenas vazio.** É a explicação mais provável
para o defeito do `/v1` ter sobrevivido em produção sem ser reportado.

**Contraste interno:** o **portal do cliente** faz certo. `portal/PortalCasos`, `PortalDocumentos`
e `PortalFinanceiro` têm `ErrorState` **com botão de retry** — a melhor experiência de erro do
sistema está na área do cliente, não na do advogado.

## 4. A IA aparece de forma contextual?

**Sim, majoritariamente — e isso é um acerto.** A IA não está confinada a um chat isolado:

| Superfície | Onde | Contextual? |
|---|---|---|
| `CaseCommandDock` | dentro do caso | **sim** |
| `PecaGeneratorModal` | dentro da produção de peça (SSE) | **sim** |
| `DossieEstrategicoCaso` | dentro do caso | **sim** |
| `AnaliseEstrategica` | dentro do caso | **sim** |
| `RaioXProcesso` | módulo próprio, com contexto de caso | **sim** |
| `SalaJuridica` | atendimento | **sim** |
| `ProvasCaso` (sugerir faltantes) | dentro do caso | **sim** |
| `AgenteIA`, `InteligenciaWorkspace`, `/prompts` | chat/painel isolado | não |

O `Layout.tsx:683-691` trata corretamente o caso de IA indisponível: botão `disabled` com
`title={ROTULO_IA_NAO_ATIVADA}` e `cursor-not-allowed` — **informa em vez de falhar**.

**Ressalva de honestidade da interface:** com HITL universal (`is_rascunho=True` incondicional), a
UI **precisa** deixar claro que toda saída é rascunho. `Pecas.tsx:89` documenta a máquina de
estados (`rascunho → em_revisao → corrigida → aprovada → final → protocolada`) e `:111-112` rotula
"Versão final — pronta para protocolo" e "Protocolada — entregue ao juízo". **O vocabulário está
correto.**

## 5. Design system

**FUNCIONAL.** UI própria, sem biblioteca externa: `UI.tsx` (118 dependentes), `Toast.tsx` (86),
`Markdown.tsx`, `Dashboards.tsx`, `ErrorBoundary.tsx`. Tailwind 3 com `darkMode: "class"` e paleta
dourada "De Paula Teixeira". `npm run format:check` passa (Prettier), `tsc --noEmit` exit 0.

Consistência de nomenclatura tem **um desvio**: `/victory_vault` é o único path em `snake_case`
num sistema kebab-case (P3). E há **dois idiomas para a mesma entidade**: `/cases` (15 routers) e
`/casos` (7) — decisão de produto pendente, não defeito.

## 6. Recomendações de UX, priorizadas

| # | Recomendação | Custo | Efeito |
|---|---|---|---|
| 1 | **Corrigir o P0 `/v1`** | baixo | devolve 4 módulos ao advogado |
| 2 | **Substituir os 41 `.catch(() => {})` por estado de erro visível com retry** — o padrão já existe no portal | médio | acaba com "vazio que era falha" |
| 3 | **Quando o gate de citações bloquear, dizer o quê e por quê** (qual citação, o que falta) | baixo | destrava o protocolo ou explica o bloqueio |
| 4 | **Expor a entrada universal** (já construída) | baixo | remove o passo de unificação manual |
| 5 | **Sinalizar widget que falhou** no `DashboardModern` e `PortalDashboard` (`allSettled`) | baixo | dashboard deixa de mentir |
| 6 | **Revisar as 29 rotas ocultas**: promover, agrupar ou arquivar | médio | menu deixa de esconder o produto |
| 7 | **Alinhar `/produtividade`** — `roles: ROLES.gestores` no registry | trivial | some o clique que sempre falha |
| 8 | **Decidir `/cases` vs `/casos`** e remover `teses_v4`/`data_room_v4` (já deprecated) | médio | reduz superfície e ambiguidade |

## 7. Conclusão

**O design não é o gargalo do EJC.** O design system é consistente, a navegação é íntegra, não há
dado fabricado em tela, não há botão morto, e a IA aparece no contexto do trabalho — que é
exatamente o que um sistema jurídico assistido por IA precisa.

**O gargalo é que o sistema não conta a verdade quando falha.** Quatro módulos mortos que parecem
vazios, 41 pontos que engolem erro, um dashboard que descarta rejeições e um gate que bloqueia sem
explicar. Some-se a isso 48 % da API sem tela e 29 rotas ocultas, e o resultado é o que a auditoria
externa descreveu: um sistema que parece incompleto **sendo, em grande parte, apenas inacessível.**

Corrigir o P0 e tornar o erro visível muda mais a percepção de qualidade do que qualquer feature nova.
