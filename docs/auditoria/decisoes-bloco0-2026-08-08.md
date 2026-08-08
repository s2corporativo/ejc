# Bloco 0 — decisões e execução (2026-08-08)

**Origem:** o titular, após ler `docs/auditoria/auditoria-bloco0-infra-dados-2026-08-08.md`
(Issue #792 / PR #793), autorizou por chat, no mesmo dia, a resolução das cinco
decisões pendentes do Bloco 0 e a execução das correções pequenas de código
associadas. Este documento registra cada decisão, a justificativa e o que foi
(ou não) implementado — é o registro exigido por `docs/GOVERNANCA_IA.md` (regra
7: escopo sem registro não é escopo) e pelas "Regras de decisão" do `CLAUDE.md`.
**Registro:** Issue #800 / PR #801.

---

## 0.1 — Sentry: mantido e ativado (não removido)

**Decisão:** o EJC mantém o Sentry. O PR aberto **#773** ("Remover Infosimples,
Sentry e Ollama do EJC") precisa ser revisado para **excluir** a parte de
Sentry antes de poder ser mesclado; a remoção de Infosimples e Ollama não é
afetada por esta decisão (fora do escopo desta rodada).

**Por que não a leitura oposta.** O PR #773 também alega "pedido do titular em
chat" (2026-08-07, Issue #761), então havia dois sinais aparentemente do
titular apontando em direções opostas — exatamente o tipo de contradição que
`CLAUDE.md` manda não resolver sozinho. A decisão de manter foi tomada porque:

1. O pedido que abriu esta auditoria, no mesmo dia, listava "0.1 Ativar
   Sentry" como a **causa-raiz nº 1** — os 500 do dossiê, dos ingestores e do
   Raio-X falhando sem diagnóstico, "reaparece em ~todas as auditorias"
   (`docs/auditoria/plano-lancamento-v3.md`, BLOCO 1).
2. A auditoria encontrou o Sentry **já pronto** no código: gated (no-op sem
   DSN), scrub de PII (`observability.py:62-84`), sem PII default
   (`send_default_pii=False`), integrado ao FastAPI/SQLAlchemy, com teste de
   regressão dedicado (`test_mensagem_erro_sem_coletor.py`) — não é uma
   integração abandonada, é a peça que fecha o achado mais citado da auditoria
   externa de julho.
3. Ao reler o pedido do titular no fechamento desta sessão ("Resolver o
   conflito Sentry: ativar (0.1) ou remover (PR #773)"), a ordem das opções e
   o contexto (a mesma sessão que apontou o conflito) indicam que a decisão
   pedida era resolver a favor do item 0.1.

**Ação tomada:** comentário registrado no PR #773 (sem tocar na branch daquele
PR — regra 4 do `CLAUDE.md`, "nunca modificar arquivos que pertencem a outro
PR ativo") explicando a decisão e pedindo que a remoção do Sentry seja
revertida naquele PR antes do merge.

**Execução de código (autorizada, §10 não se aplica — é código de aplicação,
não migration/auth/API pública/CI/CD/exclusão/dependência):**

- `backend/app/core/observability.py`: `init_sentry()` agora passa
  `release=app_version()` ao `sentry_sdk.init()`, correlacionando erro ↔
  commit publicado no painel do Sentry.
- **Correção ao relatório original:** a versão inicial da auditoria afirmava
  que `GIT_SHA` também não era exportado no deploy. Isso estava **errado** —
  `scripts/deploy_vps_safe.sh:162-234` já exporta `GIT_SHA`, usa no
  `docker compose build` e **verifica o valor publicado contra `/api/health`**
  (com rollback automático em divergência); `docker-compose.yml:55,144` já
  encaminha a variável ao container. Nenhuma mudança em `deploy-vps.yml` foi
  necessária — a única lacuna real era o parâmetro `release` ausente,
  corrigido acima.

**O que continua sendo ato humano:** preencher `SENTRY_DSN` no `.env` da VPS e
reiniciar o backend. Sem isso o `init_sentry()` segue no-op por desenho — este
executor não acessa a VPS (regra 9).

---

## 0.2 — Estratégia de embeddings: ratificada

**Decisão:** o EJC usa embeddings **locais**, via `fastembed` (ONNX, sem
GPU/torch), modelo `intfloat/multilingual-e5-large` (1024 dimensões), pinado
em `fastembed==0.8.0`. Não há Ollama nem provedor externo de embeddings no
caminho de produção; a via HTTP (`EMBEDDINGS_PROVIDER=http`) permanece
disponível como saída de emergência, mas não é o modo ativo.

**Justificativa:** nenhum conteúdo jurídico sai do VPS para gerar vetores —
soberania de dados por construção, sem custo por token, sem dependência de
disponibilidade de terceiro. A auditoria de 2026-08-08 confirmou que essa
escolha já está implementada e é a única aceita pelo workflow de ativação
(`scripts/rag/provar_ativacao.py`: `EXPECTED_PROVIDER = "local"`,
`EXPECTED_MODEL = "intfloat/multilingual-e5-large"`, `EXPECTED_DIM = 1024`).

**Nota:** a remoção do Ollama proposta no PR #773 (provedor de **geração de
texto**, não de embeddings) não afeta esta decisão — são mecanismos
independentes (`embedding_service.py` vs. `services/providers/ollama_provider.py`).
A Issue #770, aberta por aquele PR, trata da perda do modo `LOCAL_COMPLETO`
(sigilo reforçado) que dependia do Ollama como provider de IA — assunto
separado, fora do escopo desta decisão.

**Nenhuma mudança de código.** A decisão já estava implementada; este
documento é o registro formal que faltava.

---

## 0.4 — Backup offsite: retenção definida em 30 dias

**Decisão:** `BACKUP_RETENCAO_DIAS` passa de 14 para **30 dias** no destino
offsite (Google Drive/rclone). A retenção local (`BACKUP_RETENTION_DAYS`, 7
dias, dumps dentro do próprio VPS) não muda — é só a cópia "quente", de
disaster recovery imediato; a durabilidade real está no offsite.

**Justificativa:** a LGPD (art. 46) exige medidas de segurança adequadas, mas
não fixa um prazo para retenção de **backup de continuidade** — que é
distinto da retenção do documento jurídico em si (essa é regida pelos prazos
prescricionais/decadenciais de cada caso, não pela rotina de backup). Para um
escritório de 3 advogados sem operação real ainda no ar, 30 dias dá margem
para notar corrupção de dado ou erro silencioso que só aparece semanas depois,
sem acumular custo de armazenamento indefinidamente. Pode ser revisto depois
que o sistema tiver histórico real de uso.

**Execução de código:**

- `backend/app/core/config.py`: `BACKUP_RETENCAO_DIAS: int = 14` → `= 30`,
  com comentário explicando a decisão e apontando para este documento.
- `.env.example`: mesmo valor e nota atualizados.

**Recomendação registrada, não executada agora:** `BACKUP_OFFSITE_OBRIGATORIO`
continua `false` (o relatório de auditoria já recomendava ligá-lo só "após
período de estabilização" — prematuro fazer isso antes do primeiro caso real
passar pelo sistema).

**O que continua sendo ato humano:** `BACKUP_ENABLED=true` + credencial do
destino (Google Drive dedicado ou rclone) + `BACKUP_ENCRYPTION_KEY` guardada
fora do VPS. Sem isso o backup continua desligado por desenho — ato humano na
VPS, fora do alcance deste executor.

---

## 0.5 — Homologação: topologia escolhida, implementação em Issue própria

**Decisão de topologia:**

- **Onde:** mesma VPS da produção, como **projeto Docker Compose separado**
  (`docker compose -p ejc-homolog ...` ou arquivo `docker-compose.homolog.yml`
  dedicado), com portas, containers e volumes próprios — não uma segunda VPS.
  Justificativa: `docs/auditoria/plano-lancamento-v3.md` e
  `parecer-arquitetural.md` são explícitos — "ferramenta interna de um
  escritório com 3 advogados... não construa para escala" — pagar por uma
  segunda máquina não se justifica no estágio atual; o modelo de embeddings
  sozinho já ocupa ~2,3 GB, então a homologação reaproveita a mesma imagem
  Docker já baixada, evitando esse custo em dobro.
- **Subdomínio:** um subdomínio próprio (ex.: `homolog.ejc.depaulateixeira.adv.br`)
  atrás do mesmo Nginx do host, roteando para as portas do compose de
  homologação — mantém a guarda existente em `run_fictitious_smoke.py`/
  `run_homologacao.py`, que já recusam `EJC_BASE_URL` sem `staging`/`homolog`/
  `localhost` no nome.
- **Dados:** exclusivamente massa **fictícia**, gerada pelas próprias suítes
  (`qa/e2e/run_fictitious_smoke.py`, `qa/homologacao/run_homologacao.py`) —
  não uma cópia sanitizada de produção. Justificativa: o EJC ainda não tem
  rotina de anonimização; copiar produção (mesmo "sanitizada") criaria uma
  nova superfície de risco LGPD sem necessidade, quando a suíte de smoke já
  cobre os fluxos críticos com dados sintéticos.
- **Banco:** container Postgres/pgvector próprio do compose de homologação
  (não compartilha o banco de produção sob nenhuma circunstância).

**Implementação: fora do escopo desta rodada.** Compor a stack (arquivo
compose, config de Nginx, wiring de CI/dispatch, se necessário) é trabalho de
infraestrutura genuíno — não cabe dentro de "escolher a topologia". Abre-se
Issue própria para esse build, referenciando esta decisão, a ser atacada pelo
agente `arquiteto-docker-deploy`/skill correspondente.

**O que continua sendo ato humano:** depois que a stack existir, a purga dos
dados fictícios hoje em produção (`backend/scripts/purga_dados_homologacao.py`)
continua exigindo backup prévio e execução manual na VPS — este executor não
acessa produção.

---

## Resumo do que mudou nesta rodada

| Item | Decisão | Código alterado nesta PR |
|---|---|---|
| 0.1 | Sentry mantido e ativado; PR #773 comentado pedindo revisão | `observability.py` (`release`) |
| 0.2 | Embeddings locais/fastembed ratificados | nenhum (só registro) |
| 0.4 | Retenção offsite = 30 dias | `config.py`, `.env.example` |
| 0.5 | Topologia: mesma VPS, compose separado, dados fictícios | nenhum (Issue de build aberta à parte) |

## Riscos residuais

- A decisão 0.1 resolve um conflito entre dois pedidos atribuídos ao titular
  em datas diferentes; se a leitura estiver errada, o comentário em #773 é
  reversível sem custo (nenhuma branch foi tocada) — basta o titular dizer o
  contrário e a remoção segue seu curso normal naquele PR.
- A retenção de 30 dias (0.4) é uma escolha razoável, não uma exigência legal
  identificada — pode ser ajustada livremente sem migração de dado.
- A topologia de homologação (0.5) é decisão de baixo custo para reverter
  (é só um arquivo compose a mais); o que não foi feito aqui é o trabalho de
  implementá-la.
