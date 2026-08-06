# EJC — Plano de Execução Consolidado até o Lançamento

**Data:** 2026-08-06
**O que este documento é:** a síntese executável de tudo que falta para o EJC atingir o
critério de lançamento — cruzando o `docs/auditoria/plano-lancamento-v3.md` (plano ativo),
o estado real do código verificado nesta data, os PRs e Issues abertos no GitHub, e o
plano de enxugamento/faxina discutido com o titular.
**O que ele não é:** substituto do v3. O v3 continua sendo o plano de lançamento; este
documento diz **o que de cada bloco já está feito, o que falta, em que ordem, e quem faz**
(executor técnico × titular).

**Critério de sucesso (inalterado, único, não negociável):**

> Um advogado do escritório abre um caso real, leva-o até o protocolo dentro do sistema,
> e ao final diz que foi **mais fácil** do que fazer fora do sistema.

---

## 1. Estado verificado em 2026-08-06

Verificação feita no repositório (branch `main`, commit `8b11007`) e na lista de
PRs/Issues abertos. Onde a confirmação exige runtime, está dito.

| Bloco do v3 | Estado | Evidência |
|---|---|---|
| 1 — Verdade | **Parcial** | Quatro estados no banco (migration `126_case_status_quatro_estados`); timeline canônica integrada (#735). Falta conferência em runtime dos contadores dashboard × listagem × filtros (a Parte 13 da auditoria já homologou em Docker — repetir após o merge train). |
| 2 — Desobstruir | **Parcial** | `legal_docs.py` já tem `_bloquear_sem_validacao` com mensagens explicativas; migration `127_publicacao_explicita`. **Achado novo (Parte 13):** `POST /legal-docs/{id}/validar` responde 500 sem provedor de IA configurado, e é isso que trava `/aprovar` em runtime. O critério de aceite do bloco (criar → conferir → assinar → PDF, ponta a ponta) ainda não foi demonstrado. |
| 3 — Encurtar | **Parcial** | Entrada universal em correção (P1s de classificação/rastreabilidade resolvidos, `bf0c295`); quatro estados feitos. Falta: o caso como espaço de trabalho (coberto pela Issue #716 — "Onda 2") e a tela de confirmação da entrada única terminando num caso pronto. |
| 4 — Enxugar | **Parcial** | Jurimetria, Victory Vault e Sociedade já viraram `LEGACY_REDIRECTS` no `moduleRegistry.tsx`. Contador de uso de skills implantado (migration `130_ejc_skills_uso`, #688) — pré-requisito do corte do catálogo. **Pendências:** Notícias ainda na navegação (`moduleRegistry.tsx:697`); `diplomacia_v3` ainda registrada no `main.py:350` — o v3 manda **remover o código**, não só esconder; 15 calculadoras prontas no backend sem tela; corte das 163 skills aguardando janela de telemetria. |
| 5 — Prazo | **Parcial** | Monitoração por resultado no banco (migration `125_fonte_ingestao_execucoes_zeradas`); runbook de reconciliação DJEN (#693). Falta: alertas ativos por "fonte zerada / nunca produziu / N execuções em zero", diagnóstico dos `juris_import_*` e da fonte `anpd`, e a **ação humana** de cadastrar as OABs. |
| 6 — Dados | **Pendente** | Inteiramente ações de cadastro/operação do titular (ver Trilha C). |
| 7 — Primeiro caso real | **Pendente** | É o gate final. Não começa antes de A+B+C concluídas. |

**Trabalho aberto que precisa convergir antes de qualquer bloco novo:**

- **P0 #719** — reconciliar merge train, migrations 131–134 e PRs paralelos. Head atual do
  repositório: `131_audit_logs_worm`. Enquanto isso não fechar, abrir migration nova é
  pedir conflito de numeração.
- **P0 #715** / **PR #714** — vincular homologação H01–H15, deploy e backup ao SHA da release.
- **PRs de correção abertos:** #706 (RBAC allowlist, Issue #694), #705 (demonstrativo com
  proveniência, #702), #703 (guardrail de decadência, #554 — o v3 diz que **bloqueia peça a
  protocolo com IA**), #679 (sete correções de segurança/LGPD), #676 (higienização da raiz).
- **14 PRs dependabot** (#656–#671) — atualizar em lote com CI verde, priorizando axios,
  uvicorn e vite.
- **Issues de segurança/ética sem PR:** #695 (mass assignment no Raio-X), #697 (hash de
  integridade/malware em uploads), #698 e #678 (Portal do Cliente publica registro interno
  e a estimativa de êxito — o v3 marca a checagem do êxito no portal como **exceção não
  negociável e imediata**; ética OAB, art. 6º, § único, e art. 34, XXIX).

---

## 2. O plano — quatro trilhas e um gate

A ordem de precedência entre trilhas é A → B → C → (gate) → D. Dentro de cada trilha os
itens já estão em ordem. **Uma Issue e um PR draft por item** — nada de PR guarda-chuva.
Merge é sempre ato humano do titular.

### Trilha A — Convergir o que já está aberto (1ª semana)

O sistema tem hoje mais trabalho *pronto esperando decisão* do que trabalho por fazer.
Nada de código novo enquanto o trem não passar.

| # | Item | Quem | Referência |
|---|---|---|---|
| A1 | Resolver o P0 de reconciliação: ordenar merges dos PRs #703, #705, #706, #679, #676, renumerar migrations em conflito, confirmar head único | Executor prepara a ordem + rebases; **titular merge** | #719 |
| A2 | Fechar o gate de release por SHA (H01–H15) | Executor + titular | #715, PR #714 |
| A3 | Confirmar que **nenhum** endpoint `/portal/*` serializa "chance de êxito" nem registro interno; corrigir o que expuser | Executor | #678, #698 |
| A4 | Fechar as Issues de segurança sem PR: mass assignment (#695) e integridade de uploads (#697) | Executor (+ `security-auditor`) | #695, #697 |
| A5 | Dependabot em lote (axios, uvicorn, vite primeiro), CI verde por PR | Executor; titular merge | #656–#671 |

**Critério de saída da trilha:** `main` com head de migration único, CI verde, zero PR de
correção aberto com mais de uma semana, portal sem vazamento ético.

### Trilha B — Fechar os blocos de lançamento (2ª e 3ª semanas)

O que resta dos blocos 1–5 do v3, na ordem do v3:

| # | Item | Bloco v3 | Detalhe |
|---|---|---|---|
| B1 | Conferência runtime dos números (dashboard × listagem × filtros × analytics) repetindo o roteiro da Parte 13 sobre a `main` pós-merge-train | 1 | Tabela antes/depois como evidência |
| B2 | **Desobstruir de verdade:** corrigir o 500 de `/validar` sem provedor (degradar graciosamente, não quebrar), consolidar validar→aprovar→PDF em um ato de conferência e assinatura, liberar PDF desde a minuta, rótulo "minuta final — conferir e assinar" | 2 | Critério de aceite: criar → conferir → assinar → PDF **demonstrado em stack Docker**, com registro de quem/quando/versão preservado |
| B3 | Entrada única terminando num caso pronto (encadear entrada-universal + entrevista + sala-jurídica + triagem; conversão sala→caso sem perder `descricao_fatos`) | 3.1 | Desenho de telas **antes** de codificar — decisão do titular |
| B4 | O caso como espaço de trabalho (tudo sem sair da tela do caso; módulos viram visões transversais) | 3.2 | Convergir com a Issue #716 (Onda 2) para não duplicar |
| B5 | Enxugar navegação: Notícias fora do menu; **remover o código** de diplomacia-v3 (router, service, testes, seeds); expor as 15 calculadoras (testar as 15 e relatar entrada/saída antes da UI) | 4 | Autorização do v3 já registra a decisão do escritório sobre diplomacia-v3 |
| B6 | Corte do catálogo de skills guiado pelo contador de uso (migration 130): manter as com uso, arquivar o resto | 4 | Precisa de 2+ semanas de telemetria — iniciar a janela **já**, cortar ao final da Trilha C |
| B7 | Prazos: alertas por resultado ativos (fonte zerada / nunca produziu / N zeros consecutivos), diagnóstico `juris_import_*` e `anpd`, contagem bruta pré-parsing no TJMG | 5 | Depende de B8 (OABs) para o teste de ponta a ponta |

### Trilha C — Dados e operação (3ª e 4ª semanas — majoritariamente do titular)

Checklist do Bloco 6 do v3, com responsável explícito. O executor prepara scripts e
runbooks; **a execução em produção é ato humano**.

| # | Ação | Quem executa |
|---|---|---|
| C1 | Cadastrar OAB dos 3 advogados no monitoramento DJEN + `oab_number` nos perfis | Titular |
| C2 | Desativar a conta `homolog.qa` (superadmin ativa em produção) e **rotacionar credenciais** (a auditoria registrou senha de root do VPS = senha de aplicação) | Titular (executor entrega script + runbook) |
| C3 | Limpar dados fictícios: casos `HOMOLOG-FICTICIO-*`, 37 casos na lixeira, peças órfãs, 2 contas de teste | Titular (executor entrega script de limpeza com dry-run) |
| C4 | Impedir que o smoke E2E rode contra produção: `run_fictitious_smoke.py` recusa a URL de produção; criar ambiente de homologação | Executor (código) + titular (ambiente) |
| C5 | Carregar tabela de honorários OAB/MG; cadastrar sócios/percentuais; definir categorias de despesa | Titular |
| C6 | RAG: cobrir **só consumidor e civil**, e bem (as áreas praticadas); carregar os 8 modelos de peça da casa | Executor + curadoria do titular (converge com #718/#701/#636) |

### Gate — Bloco 7: o teste do primeiro caso real

Inalterado em relação ao v3. É do titular, não do executor. Um caso real de complexidade
média, do início ao protocolo, sem consertar nada durante a passagem, anotando hesitação
além de erro. **A ordem em que os problemas aparecerem é a ordem do backlog seguinte.**
Só depois que esse teste passar a operação começa.

### Trilha D — Faxina profunda (pós-lançamento, uma tesourada por semana)

O enxugamento discutido em 2026-08-06, nas fases já acordadas — deliberadamente **depois**
do lançamento, exceto o que as trilhas A/B já cobrem (diplomacia-v3, Notícias, skills):

1. **Frontend morto:** páginas alcançáveis só por `LEGACY_REDIRECTS`, componentes e
   estilos da paleta antiga, dependências via `knip`.
2. **Limpeza mecânica:** código comentado, funções órfãs (`vulture`/análise de imports),
   arquivos temporários, `RELATORIO_*.md` da raiz para `docs/historico/`, testes de
   módulos removidos.
3. **Flags e env:** das 62 flags `ENABLE_*`/`*_ENABLED`, remover as de features cortadas;
   documentar as vivas no `.env.example`; conferência do `.env` de produção via runbook.
4. **Endpoints sem uso:** cruzar as 211 rotas órfãs com a telemetria
   `route_usage_metrics` (migration 122) após 2–4 semanas de operação real; remover só
   o que tiver zero tráfego confirmado.
5. **Superfície dupla `/api` + `/api/v1`:** escolher a canônica, logar acessos à outra,
   deprecar com aviso e só então desligar — é contrato público.
6. **Banco por último:** tabelas/colunas sem uso confirmado → backup → migration de drop
   escrita à mão (nunca autogenerate — ~30 tabelas raw-SQL enganam o Alembic) → aplicar.
7. **Também pós-lançamento (herdado do v3):** ciclo financeiro completo, peticionamento
   PJe/eproc, Portal do Cliente, acessibilidade (#592), paleta/tokens, Sentry, prefixo
   `/v1/` duplicado, taxonomia de áreas.

---

## 3. Ordem de grandeza e dependências

```
Semana 1  ─ Trilha A (merge train, portal ético, segurança)  ── destrava tudo
Semana 2  ─ B1, B2 (verdade + desobstruir)                   ── fluxo abre até o PDF
          └ B6 inicia janela de telemetria de skills
Semana 3  ─ B3, B4 (entrada única + caso como workspace)     ── resolve a "preguiça"
          └ B5, B7 (enxugar navegação + prazos)
          └ C1–C6 em paralelo (titular)
Semana 4  ─ Gate: Bloco 7 — primeiro caso real
Depois    ─ Trilha D (faxina), financeiro, peticionamento
```

Dependências duras: B2 antes de B3/B4 (não adianta encurtar caminho que termina em
parede); A1 antes de qualquer migration nova; C1 antes do teste fim-a-fim de B7;
C2/C3 antes do Bloco 7 (começar a operação sem saber o que é real é fatal).

## 4. Decisões que são do titular (e quando)

1. **Ordem e ato de merge** do trem da Trilha A — imediato.
2. **Desenho das telas** de entrada única e do caso-workspace (B3/B4) — antes de codificar.
3. **Lista final de módulos cortados** — o v3 já decide jurimetria, victory vault,
   notícias, sociedade e diplomacia-v3; confirmar se as **áreas de atuação** saem de 25
   para as praticadas (consumidor e civil).
4. **Cadastros e limpeza de produção** (Trilha C) — semana 3.
5. **Condução do Bloco 7** — semana 4.

## 5. Regras que atravessam o plano

- Uma Issue + um PR draft por item; `Closes #NNN` no corpo (a trava `governanca.yml`
  reprova sem isso); correção de review na mesma branch.
- Migration nova só depois do head reconciliado (A1) e com reserva em
  `MIGRATION_RESERVATIONS.md`.
- Mudança em auth/RBAC/upload/portal passa pelo `security-auditor` antes de finalizar.
- Nenhum merge, deploy ou acesso a produção pelo executor.
- Em dúvida entre adicionar e remover: **remova** (regra do v3).

---

*Consolidado por sessão de execução em 2026-08-06. Fontes: `docs/auditoria/plano-lancamento-v3.md`,
`docs/auditoria/plano-correcao-v2.md`, `docs/auditoria/parecer-arquitetural.md`, Parte 13
(homologação dinâmica), estado do repositório em `8b11007` e Issues/PRs abertos nesta data.*
