# Pauta de Decisões do Titular — Plano-Mestre EJC

Documento único para minimizar o tempo do titular: cinco decisões, cada uma com
contexto, opção recomendada e o que destrava. Nenhuma delas exige ler código —
o executor já fez a leitura. Desenho completo do plano em
`docs/estrategia/PLANO_MESTRE_EJC.md`; status vivo em `docs/PLANO_MESTRE_STATUS.md`.

Custo total estimado desta pauta: 1–2 horas numa sessão só (T3), fora as ações
operacionais T1/T2 abaixo que não são decisão — são execução que só o titular
pode fazer.

---

## Ações operacionais (não são decisão — são execução que só o titular faz)

### T1 — Revisar e mesclar PR #1259; autorizar o 1º deploy manual

O PR #1259 (`s2corporativo/ejc`, branch `claude/ejc-strategic-evolution-2qqasi`)
constrói `scripts/deploy_manual.sh` e o `RUNBOOK_DEPLOY_MANUAL.md` — o caminho
para levar as migrations 127–147 (mescladas, **não** em produção) para o ar
enquanto a cota do Actions estiver esgotada. Está em draft de propósito: mexe
no procedimento de deploy e não há CI do HEAD exato (a própria cota é o assunto
do PR). Preservado no PR: backup obrigatório, mutex, bloqueio de migration
destrutiva, rollback automático — nenhuma trava foi afrouxada.

**Ação:** revisar o PR, mesclar, e autorizar a primeira execução real (o
executor já rodou `--dry-run`; a primeira execução de verdade deve ter alguém
acompanhando a saída). Isso destrava o gate de saída da F0.

**Custo:** 30–60 min.

### T2 — Regularizar a cota do GitHub Actions + reativar 3 workflows

Nenhum workflow roda hoje, nem no runner self-hosted — o bloqueio é da conta,
antes de alocar runner (verificado em 2026-08-23). Além disso, três workflows
estão `disabled_manually` independente da cota: `auto-integracao.yml`
(mesclava PRs automaticamente com gates verdes), `continuity-ui-gates.yml` e
`architecture-inventory.yml`. Eles ficaram desligados por semanas sem que
ninguém notasse (Issue #1235) — inclusive recebendo melhorias enquanto
desligados.

**Ação:** regularizar o faturamento do Actions; reativar os três workflows na
UI do GitHub (Settings → Actions → o workflow → "Enable workflow"). Só o
titular tem acesso administrativo para os dois.

**Custo:** 15 min de clique + o tempo do faturamento (fora do controle técnico).

**Destrava:** F6 (merge automático de volta); sem isso, o executor segue no
deploy manual indefinidamente.

---

## Decisões de produto (T3)

### D1 — Canônico do conceito "tese"

**O problema:** hoje "tese" tem 6 representações no banco (`teses`,
`tese_caso_links`, `thesis_candidates`, `teses_juridicas_v4`, `teses_vitoriosas`,
`cases.tese_principal`). Duas rotas emitem a mesma chave `tese_aprovada` com
fontes disjuntas — `conversao_caso.py` olha `tese_caso_links`,
`legal_case_orchestrator.py` (a Jornada do caso) olha `thesis_candidates`. É
por isso que a Jornada mostra "Teses pesquisadas: pendente" no mesmo caso em
que o Dossiê Estratégico mostra "1 tese vinculada".

**Opção recomendada:** `tese_caso_links` vira a única verdade do vínculo
caso↔tese. `thesis_candidates` (a matriz de trabalho, com fluxo HITL de
aprovação) passa a ser um **estágio**, não um destino: ao aprovar uma
candidata, o sistema cria automaticamente o link — hoje essa ponte não existe.
`cases.tese_principal` (texto livre, ~15 leitores) fica congelado como campo
exibicional, sem forçar migração de leitores agora.

**Pergunta ao titular:** a experiência que os advogados devem ver como
"primária" é a matriz de trabalho (`thesis_candidates`, com aprovação
explícita) ou o Banco de Teses institucional (`teses` + `tese_caso_links`,
vínculo direto)? A resposta muda qual tabela vira a fonte visível na tela —
a correção técnica da inconsistência (ponte automática) é a mesma nos dois
casos.

**Se não houver decisão:** o executor segue com a opção recomendada acima
(link como verdade, candidate como estágio) — é a hipótese default do plano,
não um bloqueio.

### D2 — Destino do `CaseLifecycleStatus` (11 valores não persistidos)

**O problema:** existe um enum de 11 valores (`triagem`, `em_analise`,
`aguardando_documentos`, `proposta_apresentada`...) em
`backend/app/core/domain_contracts.py` que não é gravado em lugar nenhum —
convive com o enum real de 6 valores (`aberto`, `em_instrucao`,
`em_producao`, `protocolado`, `encerrado`, `arquivado`) que É persistido e
tem teste de paridade com o frontend.

**Opção A (recomendada):** remover a declaração dos 11 valores com uma nota
explicando por quê — é vocabulário de uma fase de desenho anterior que nunca
foi implementada.

**Opção B:** se os 11 estados fazem falta na prática (granularidade maior no
funil pré-caso), vira trabalho de produto para depois da F5 — não um ajuste
cosmético.

**Pergunta ao titular:** algum desses 11 estados corresponde a algo que a
equipe hoje rastreia manualmente (planilha, memória) e sente falta no
sistema? Se não, Opção A.

### D3 — Lista final de cortes de módulo (34 → 10–12)

O parecer arquitetural recomenda cortar (você já aprovou incluir cortes no
plano-mestre; esta decisão é confirmar a lista item a item):

| Módulo | Motivo do corte | Reversível? |
|---|---|---|
| Jurimetria / predição de êxito | "Jurimetria com 8 casos é anedota" — precisa de ~300 casos encerrados para significar algo | Sim, git |
| `diplomacia-v3` (`/analisar-magistrado`, `/dossie-pressao`) | Risco reputacional e disciplinar (código, não só tela) | Sim, git |
| Victory Vault | Vazio (`/teses/ranking` → `[]`) | Sim, vira pasta de modelos até haver acervo |
| Radar de notícias / `/noticias` (ConJur, JOTA) | "Não é ERP" — fora do escopo de gestão de casos | Sim, git |
| Módulo sociedade / retiradas de sócio | `/sociedade/socios` vazio, sem uso | Sim, git |
| Skills de IA sem uso registrado em log | Superfície morta, custo de manutenção sem benefício | Sim, git |

**Pergunta ao titular:** confirma os 6 cortes acima, ou quer excluir algum da
lista (fica para depois, sem impedir os demais)?

**Se não houver resposta:** a F5 não começa sem essa confirmação — ela já
está no fim do plano (atrás do gate do primeiro caso real), então não há
pressa, mas a lista final precisa estar fechada antes do primeiro PR de
corte.

### D4 — Política da métrica "chance de êxito"

**O problema:** o sistema calcula e exibe um percentual de "chance de êxito"
por caso, com barra colorida na tela. Risco: Código de Ética da OAB, art. 6º,
parágrafo único, e art. 34, XXIX (vedação a captação/mercantilização
inadequada da expectativa do cliente). A auditoria marcou como `[CRÍTICO]`.

**Opções:**
1. **Remover** a métrica da interface do advogado e do cliente (mantém o
   cálculo interno, se útil para priorização interna, mas nunca exibido).
2. **Reformular**: trocar percentual por faixa qualitativa sem número
   ("favorável" / "incerto" / "desfavorável"), com nota metodológica visível.
3. **Manter como está**, com parecer jurídico formal registrado justificando
   a conformidade.

**Recomendação do executor:** Opção 1 ou 2 — a auditoria já achou o dado
estatisticamente frágil (poucos casos para calibrar) *além* do risco
regulatório; as duas razões apontam para o mesmo lado.

**Urgente e não negociável, independente da decisão acima:** confirmar que a
métrica **não é serializada em nenhuma rota `/portal/*`** — ela pode ser
aceitável como ferramenta interna do advogado e inaceitável se o cliente a
vê diretamente. Isso entra na F3 de qualquer forma.

---

## Resumo de para onde vai cada resposta

| Decisão | Se não responder agora | Bloqueia |
|---|---|---|
| T1 | F0 não fecha o gate de deploy | F0 |
| T2 | Deploy manual continua sendo o único caminho | F6 |
| D1 | Executor segue com a hipótese default (link=verdade) | 1º PR da Classe A (F2) |
| D2 | Executor remove a declaração morta com nota | Nenhum — decisão de baixo custo |
| D3 | F5 não começa até fechar | F5 (mas ela já está no fim do plano) |
| D4 | F3 não fecha o item 4.2 | F3 |
