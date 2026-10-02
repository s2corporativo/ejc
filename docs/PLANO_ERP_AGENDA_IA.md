# Plano — EJC em três pilares: ERP, Agenda/Intimações e IA

> Documento de plano. Não é procedimento nem relatório histórico.
> Status de execução vive em `docs/PLANO_MESTRE_STATUS.md` (o PR que fechar um
> item cria/flipa a linha lá). Complementa — não substitui —
> `docs/PLANO_SIMPLIFICACAO_EJC.md` (foco no caso e na produção de peças).

## 1. Pedido e restrições

Pedido do titular (02/10/2026): melhorar a parte ERP para gestão completa do
escritório, organizando o sistema em três partes — **ERP**, **agendamento e
recebimento de notificações de processo** e **IA** — com três restrições:

1. **Nenhum módulo ou opção nova.**
2. **Nenhum campo novo para preencher** — o objetivo é preencher *menos*.
3. **Tudo continua funcionando** — sem perda de dado, sem rota quebrada
   (deep-links antigos redirecionam).

Regra derivada: toda entrega é **ligação, reagrupamento ou remoção** de algo
que já existe. Quando a ligação exigir coluna de banco, ela é técnica
(invisível ao usuário), aditiva e com backup prévio.

## 2. Base da análise

- Código lido em `main` @ `049fd6c` (02/10/2026). Achados abaixo citam arquivo.
- **Estado de produção não foi verificado**: a governança (§9, regra 9 do
  `CLAUDE.md`) veda acesso ao banco/`.env` da VPS. Itens que dependem disso
  estão marcados **[conferir em produção]** e entram na Fase 0.
- PRs abertos que tocam as mesmas áreas (não mexer nesses arquivos até o merge):
  #1985 (contrato de honorários → Financeiro/Dashboard), #1991 (parcelas
  contratuais 1-N), #1998 (prazo vencido DJEN), #1955 (saneamento estrutural).

## 3. Diagnóstico por pilar

### 3.1 ERP (financeiro e gestão do escritório)

O que está bom: o Financeiro já é um workspace único
(`frontend/src/pages/FinanceiroWorkspace.tsx` — Visão, Receber, Pagar,
Comissões, Sociedade, Estimador + "Mais": NFS-e, Contratos, Recorrentes), o
fechamento mensal existe (`services/finance_governance.py`) e o contrato do
cliente já gera cronograma de parcelas (#1988).

| # | Achado | Evidência | Impacto |
|---|---|---|---|
| E1 | **Custo do caso tem dois cadastros paralelos.** Aba "Centro de Custos" grava em `centro_custos`; aba "Timeline" grava em `case_despesas` (despesa processual, faturável ao cliente) | `CasoDetalhe.tsx:880` (`/centro-custos`); `CasoDetalhe/TabTimeline.tsx:114,199` (`/despesas-processuais`) | Digitação dupla ou dado faltando |
| E2 | **`case_despesas` não entra em nenhum relatório.** A tabela só é lida pelo próprio router; fechamento mensal, extrato do caso, relatório financeiro do cliente e comissões somam apenas `centro_custos` | `grep case_despesas` → só `routers/despesas_processuais.py`; `finance_governance.py:73`, `routers/extratos.py:32`, `routers/relatorio_cliente.py:72` | **Fechamento mensal subestima a despesa** quando a custa é lançada pela Timeline |
| E3 | Recebimento e NFS-e são passos desconectados: registrar pagamento (`POST /fees/{id}/pagamentos`) não oferece a emissão; NFS-e é lançada à parte | `routers/fees.py` sem referência a NFS-e; `routers/nfse.py` | Passo esquecido, retrabalho |
| E4 | Todo recebimento/despesa do escritório é digitado. Já existe parser de extrato OFX/CSV, porém usado só no litígio bancário de cliente | `services/bank_statement.py` (usado por `routers/bank_analysis.py`) | Maior fonte de digitação do ERP |
| E5 | Régua de cobrança ao cliente e NFS-e nascem desligadas (`COBRANCA_ENABLED`, `NFSE_ENABLED` = `False`) | `core/config.py`, `services/cobranca_cliente_service.py:273` | Funcionalidade pronta e inerte **[conferir em produção]** |

### 3.2 Agenda e notificações de processo

O que está bom: a Central `/atividades` já unifica prazos, tarefas,
intimações, suspensões e agenda; a escrita é única nela e as abas do caso são
só leitura. O aceite de prazo vindo do DJEN exige confirmação humana.

| # | Achado | Evidência | Impacto |
|---|---|---|---|
| A1 | **Captura do DJEN bloqueada por região** quando a saída da VPS é fora do Brasil (CloudFront responde 403). O código já detecta e interrompe o ciclo; a mitigação documentada é `DJEN_HTTP_PROXY_URL` com egress brasileiro | `services/djen_service.py:190-206`; commit `63b606a`; `docs/RUNBOOK_INGESTAO_RAG.md:36-59` | **Sem isso, o pilar "receber intimações" não funciona** **[conferir em produção]** |
| A2 | Duas fontes de OAB: a captura lê `DJEN_OABS_MONITORADAS` (env); o alerta itera `users.djen_oab_numero` | `PLANO_MESTRE_STATUS.md` item AUD27-P1-8 (pendente) | Intimação capturada sem alerta, ou vice-versa |
| A3 | Canais externos nascem desligados: `EMAIL_ENABLED`, `WHATSAPP_ENABLED`, `PUSH_ENABLED` = `False`; sem eles, só o sino interno | `core/config.py:449,465,865`; `services/notification_service.py` | Advogado fora do sistema não é avisado **[conferir em produção]** |
| A4 | **Audiência pode viver em dois lugares** (`deadlines` tipo `audiencia` e `agenda_eventos` tipo `audiencia`), e o feed de calendário (ICS → Google/celular) lê **apenas `deadlines`** | `routers/calendar_feed.py:188`; `routers/agenda_eventos.py:179`; `models/deadline.py:13` | Audiência lançada pela agenda **não aparece no celular** |
| A5 | ~12 jobs de aviso entre 06h55 e 09h30, cada um gera notificação própria; há dois briefings matinais que se sobrepõem em prazos: `briefing_adv` (06h55, por advogado) e `brief` (07h00, visão do escritório com prazos + financeiro, `scheduler_financeiro.py:82`) | `services/scheduler.py:1320-1333` | Ruído → aviso importante ignorado |

### 3.3 IA

O que está bom: núcleo único obrigatório (`services/ai_gateway.py`), HITL,
gate de citações, sanitização de PII e kill-switch — não serão tocados.

| # | Achado | Evidência | Impacto |
|---|---|---|---|
| I1 | Muitas portas de entrada de IA no menu: Sala Jurídica, Raio-X, Inteligência Jurídica (6 grupos internos), Banco de Teses, Radar, Entrada Jurídica, Peças, além de Áreas de Atuação/DPT360 por deep-link e o assistente contextual | `config/moduleRegistry.tsx`; `pages/InteligenciaWorkspace.tsx:60-110` | O usuário precisa saber "qual IA" usar |
| I2 | **Cliente e caso são criados por quatro caminhos de escrita distintos**, cada um com sua própria deduplicação por CPF/CNPJ | `Client(`/`Case(` em `routers/clients.py`, `routers/cases.py`, `services/raio_x_service.py:536`, `services/legal_chat_service.py:1152`, `services/entrada_service.py:1019` | Regra divergente entre caminhos (anti-padrão do `FLUXO_CANONICO_EJC.md` §7) |
| I3 | Routers sem nenhuma chamada no frontend: `cerebro`, `matriz_teses`, `advogado_estilo`, `processo_eletronico`, `radar_legislativo`, `consumidor_monitor`, `licitacao_auditoria`, `car` (podem ter uso por job/agente — exige medição antes de cortar) | busca por prefixo em `frontend/src` | Superfície de manutenção e de ataque |
| I4 | ~14 PRs abertos só de IA (Legal Brain LB*, Manus, aprendizado supervisionado, RAG) | lista de PRs abertos em 02/10 | Frente de IA crescendo enquanto ERP/agenda têm lacunas |

### 3.4 Transversal — navegação

- Menu visível para advogado: **17 entradas** em 5 grupos
  (`moduleRegistry.tsx`, módulos sem `status: "hidden"`).
- Página do caso: **25 abas** (7 principais + "Mais") — `CasoDetalhe.tsx:83-130`.
- Já existe liga/desliga administrativo de módulo
  (`/system-modules/settings` + `ModuleLifecycleGate`) e telemetria de uso de
  rota (`route_usage_metric`) — **as duas ferramentas permitem simplificar por
  configuração e com dado real, sem código novo.**

## 4. Desenho-alvo: três pilares sobre o que já existe

```
HOJE (tela inicial)  — prazos do dia, intimações novas, recebimentos vencidos, peças em revisão
│
├── 1. ESCRITÓRIO (ERP)        Clientes · Casos · Financeiro · Produtividade
├── 2. AGENDA E INTIMAÇÕES     Prazos e Agenda (Central /atividades)
└── 3. IA JURÍDICA             Sala Jurídica · Inteligência (Raio-X, Teses, Radar entram como abas/atalhos)

Configurações / Usuários / Diagnóstico — rodapé, só gestores
```

Nenhum item acima é módulo novo: é o reagrupamento dos grupos atuais
(`MODULE_GROUP_ORDER`) em três, com os demais virando aba, atalho contextual
ou "Mais Ferramentas". Rotas antigas viram `LEGACY_REDIRECTS`.

## 5. Fases

Cada fase = um PR independente, com rollback próprio e portão local do
`CLAUDE.md` proporcional ao diff.

### Fase 0 — Verificação operacional (titular; sem código) — PRIMEIRO

Sem isto, as fases seguintes podem otimizar algo que nem está ligado.

| Verificação | Onde conferir | Resultado esperado |
|---|---|---|
| DJEN capturando | `GET /api/intimacoes/status-captura` | `sucesso` ou `sucesso_sem_resultados` — nunca `geo_bloqueado` |
| Se `geo_bloqueado` | `.env` da VPS | configurar `DJEN_HTTP_PROXY_URL` conforme `RUNBOOK_INGESTAO_RAG.md` |
| OABs dos advogados | Configurações → usuário → OAB DJEN | todos os advogados com `djen_oab_numero` preenchido |
| Canais de aviso | `.env`: `EMAIL_ENABLED`, `WHATSAPP_ENABLED`, `PUSH_ENABLED` | ao menos um canal externo ligado e testado |
| Calendário no celular | Prazos e Agenda → link ICS | assinado no Google Agenda de cada advogado |
| NFS-e / cobrança | `.env`: `NFSE_ENABLED`, `COBRANCA_ENABLED` | decisão consciente de ligar ou não |
| Uso real das rotas | Central de Diagnóstico / `route_usage_metric` (30 dias) | lista de rotas com zero uso → insumo da Fase 4 |
| Backlog de PRs | #1985, #1991, #1998 | mesclados ou fechados antes das Fases 1–2 |

### Fase 1 — Agenda e intimações confiáveis

1. **Feed ICS completo**: incluir `agenda_eventos` (com hora/local) além de
   `deadlines` (`routers/calendar_feed.py`). Audiência passa a chegar ao
   celular venha de onde vier.
2. **Audiência com um lugar canônico**: `deadlines` (tipo `audiencia`) é o
   canônico — tem alerta 7/3/1 dias e cálculo; o formulário da agenda, ao
   escolher tipo "audiência", grava como prazo. Registros antigos de
   `agenda_eventos` continuam lidos (sem migração destrutiva).
3. **Fonte única de OAB** (fecha AUD27-P1-8): captura passa a ler
   `users.djen_oab_numero`; a env vira fallback.
4. **Um resumo diário por pessoa**: o `briefing_adv` (já personalizado por
   advogado) absorve prazos, audiências, intimações, solicitações e cobranças
   do dia; os alertas individuais ficam apenas para urgência (prazo de
   hoje/amanhã, prazo vencido). O `brief` deixa de repetir prazos e vira a
   seção "escritório/financeiro" do mesmo resumo, só para gestores.

Critérios: audiência criada pela agenda aparece no ICS; nenhum prazo
alertado em duplicidade; teste de regressão para cada item; nenhum campo novo.
Risco: baixo-médio (scheduler). Rollback: revert; sem migration.

### Fase 2 — ERP sem digitação dupla

1. **Custo do caso em um só lugar** (E1/E2): `centro_custos` é o canônico —
   já alimenta fechamento, extrato, relatório do cliente e comissões.
   - migration **aditiva**: coluna `fee_id` em `centro_custos` (preserva o
     faturamento ao cliente que hoje só `case_despesas` tem);
   - cópia dos lançamentos de `case_despesas` para `centro_custos`
     (idempotente, com backup prévio); `case_despesas` fica somente leitura —
     **sem DROP**;
   - aba Timeline e aba Centro de Custos passam a usar o mesmo endpoint;
     "Centro de Custos" é absorvida pela aba Financeiro do caso.
2. **Recebimento → NFS-e em um clique** (E3): ao registrar pagamento, com
   `NFSE_ENABLED`, a tela oferece emitir a nota já preenchida com os dados do
   honorário e do cliente. Nenhum campo novo.
3. **Financeiro mais curto**: Estimador, Comissões e Sociedade vão para o
   "Mais" do workspace (continuam a um clique; deep-links preservados).

Critérios: fechamento de um mês com custa lançada pela Timeline passa a
somá-la (teste de regressão do E2); faturamento de custas ao cliente
preservado; nenhum lançamento perdido (contagem antes/depois da cópia).
Risco: médio (migration + dado financeiro). Rollback: revert do código; a
coluna nova é nula e inofensiva; `case_despesas` intacta.

### Fase 3 — Navegação em três pilares

1. Menu reagrupado conforme §4 (de 17 para ~8 entradas por perfil), usando
   apenas `group`, `showInNav` e `essential` do registry.
2. Raio-X, Banco de Teses e Radar viram abas/atalhos da Inteligência e do
   caso; Ajuizamento vira ação dentro do caso.
3. Na página do caso, aplicar a Fase 1/3 do `PLANO_SIMPLIFICACAO_EJC.md` que
   segue pendente (abas viram filtros das cinco seções).
4. Módulos sem uso na medição da Fase 0 são desligados pelo liga/desliga
   administrativo — sem apagar código.

Critérios: todos os deep-links antigos resolvem (`routeIntegrity.test.ts`,
`moduleRegistry.test.ts`); RBAC inalterado. Risco: baixo (frontend).
Rollback: revert.

### Fase 4 — IA enxuta e coerente

1. **Um único serviço "obter ou criar cliente/caso"** usado pelos quatro
   caminhos (I2) — mesma deduplicação por hash, mesmo audit log, mesmo RBAC.
   Refatoração, não módulo.
2. **Corte por evidência** (I3): rotas com zero uso em 30 dias e sem
   chamador interno (job/agente) entram numa lista para confirmação do
   titular, no mesmo formato da decisão D3 da `PAUTA_DECISOES_TITULAR.md`.
   `licitacao_auditoria` é candidata natural (fora do escopo de escritório
   de advocacia).
3. **Congelar frentes novas de IA** até as Fases 1–2 estarem em produção;
   concluir ou fechar os PRs de IA abertos (I4).

Critérios: testes de isolamento (`test_rag_isolation.py`) e de criação de
cliente verdes nos quatro caminhos; HITL, gate de citações, PII e
kill-switch intactos. Risco: médio. Rollback: revert.

### Fase 5 (opcional) — Importação do extrato bancário do escritório

Reusar `services/bank_statement.py` (OFX/CSV) para o escritório: o usuário
envia o extrato, o sistema **sugere** a baixa de parcelas e despesas
correspondentes e o usuário confirma. Elimina a maior parte da digitação do
ERP (E4). É ação dentro do Financeiro, não módulo. Só após a Fase 2.

## 6. Sequência

```
Fase 0 (titular) ──> Fase 1 (agenda) ──┐
                 └─> Fase 2 (ERP) ─────┼──> Fase 3 (navegação) ──> Fase 4 (IA) ──> Fase 5 (opcional)
```

Fases 1 e 2 são independentes. A Fase 3 vem depois porque reagrupar a
navegação só vale com os fluxos corrigidos. Prioridade de risco: **A1 (DJEN)
e E2 (fechamento subestimado) primeiro** — o primeiro gera perda de prazo, o
segundo gera número financeiro errado.

## 7. O que este plano não faz

| Descartado | Motivo |
|---|---|
| Módulo/tela nova de ERP, agenda ou IA | Restrição do pedido; tudo já existe |
| Campo novo em formulário | Restrição do pedido |
| Gateway de pagamento/boleto pago, WhatsApp oficial pago | Custo recorrente; PIX estático (`routers/pix.py`) e Evolution já existem |
| Apagar tabelas (`case_despesas`, `agenda_eventos`) | Regra 2 do `CLAUDE.md`; contração só em migration futura, com backup |
| Mexer em HITL, gate de citações, PII, RBAC | Regra 3 do `CLAUDE.md` |

## 8. Decisões do titular

| # | Pergunta | Recomendação | Se não responder |
|---|---|---|---|
| P1 | Audiência canônica em `deadlines` (prazo) ou em `agenda_eventos`? | `deadlines` — tem alerta e cálculo | segue a recomendação |
| P2 | Canais de aviso externos: e-mail, WhatsApp (Evolution) ou ambos? | e-mail + WhatsApp | Fase 1 entrega só o sino + ICS |
| P3 | Ligar NFS-e e régua de cobrança ao cliente em produção? | sim, após homologação | ficam desligadas; Fase 2 item 2 fica inerte |
| P4 | Confirmar lista de cortes da Fase 4 (gerada pela medição) | — | Fase 4 item 2 não começa |

## 9. Riscos residuais

- Estado de produção não verificado por mim (§2); a Fase 0 pode revelar
  outros bloqueios.
- A cópia `case_despesas` → `centro_custos` toca dado financeiro: exige backup,
  contagem antes/depois e execução acompanhada.
- Consolidar avisos num resumo diário reduz ruído, mas exige manter os
  alertas urgentes individuais — critério explícito na Fase 1.
