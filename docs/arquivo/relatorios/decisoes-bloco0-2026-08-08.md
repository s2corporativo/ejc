# Bloco 0 — decisões e execução (2026-08-08)

**Origem:** o titular, após ler `docs/auditoria/auditoria-bloco0-infra-dados-2026-08-08.md`
(Issue #792 / PR #793), autorizou por chat, no mesmo dia, a resolução das cinco
decisões pendentes do Bloco 0 e a execução das correções pequenas de código
associadas. Este documento registra cada decisão, a justificativa e o que foi
(ou não) implementado — é o registro exigido por `docs/GOVERNANCA_IA.md` (regra
7: escopo sem registro não é escopo) e pelas "Regras de decisão" do `CLAUDE.md`.
**Registro:** Issue #800 / PR #801.

---

## 0.1 — Sentry: decisão revista — REMOVIDO (PR #773 segue como estava)

> **Histórico da decisão, para quem ler isto depois:** esta seção foi escrita
> duas vezes no mesmo dia. A primeira versão (preservada em
> `git log -p` deste arquivo) decidiu **manter e ativar** o Sentry, resolvendo
> a favor do item 0.1 do plano de lançamento. Ao apresentar os comandos de
> shell para ativação, o titular perguntou diretamente se o Sentry teria custo
> — a resposta correta é "só acima da cota gratuita, sem cobrança automática",
> mas isso reabriu a pergunta de fundo por completo. Perguntado se aceitava
> ficar **sem nenhuma ferramenta de rastreamento de erro** (nem Sentry SaaS,
> nem self-hosted como GlitchTip — só log manual do container), o titular
> confirmou que sim. **Esta segunda versão é a que vale.**

**Decisão final:** o EJC **não terá** rastreamento de erro automatizado por
enquanto — nem Sentry, nem alternativa self-hosted. O PR **#773** ("Remover
Infosimples, Sentry e Ollama do EJC") pode prosseguir **exatamente como estava
proposto**, incluindo a remoção do Sentry. O comentário anterior desta sessão
naquele PR (pedindo para excluir a remoção do Sentry) foi **retratado** com um
comentário de acompanhamento.

**Consequência aceita conscientemente:** a causa-raiz nº 1 do plano de
lançamento — "os 500 do dossiê, dos ingestores e do Raio-X falham sem
diagnóstico" — **continua sem solução automatizada**. Sem Sentry (ou
equivalente), um erro em produção só é percebido de duas formas: alguém
reclama, ou alguém entra na VPS e roda `docker compose logs backend`. A
mensagem de erro já não promete mais uma notificação que não existe
(`coletor_erros_ativo()`, corrigido em rodada anterior) — isso permanece
correto e não é revertido — mas a lacuna de fundo (ninguém é avisado
proativamente) fica aberta por decisão consciente, registrada aqui, não por
omissão.

**Por que a primeira leitura (manter) foi razoável e ainda assim trocada.**
Não foi erro de leitura do pedido — foi informação nova chegando depois: só ao
ser questionado diretamente sobre custo e sobre a alternativa self-hosted
(GlitchTip) o titular esclareceu a preferência real, mais restritiva do que
qualquer um dos dois PRs (#773 removia o Sentry mas cogitava reintroduzir
alguma observabilidade depois; a auditoria original pedia ativação). Nenhuma
das duas leituras anteriores previa "nenhuma ferramenta, nunca".

**Ações tomadas nesta revisão:**

1. `backend/app/core/observability.py`: revertido o `release=app_version()`
   adicionado na primeira versão desta decisão — sem sentido manter parâmetro
   de uma integração que nunca vai rodar (a limpeza completa de
   `core/observability.py` fica a cargo do PR #773, que já a propõe).
2. Comentário de acompanhamento postado no PR #773 retratando o pedido
   anterior desta sessão.
3. Este documento e a adenda em
   `docs/auditoria/auditoria-bloco0-infra-dados-2026-08-08.md` corrigidos.

**Se a decisão mudar no futuro:** GlitchTip self-hosted continua sendo a
opção que resolve o problema de fundo sem custo recorrente e sem dado saindo
do VPS (mesmo código `sentry_sdk`, só aponta o DSN para um servidor próprio em
vez do sentry.io) — não implementado agora, só registrado como alternativa
válida caso a lacuna volte a incomodar.

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
infraestrutura genuíno — não cabe dentro de "escolher a topologia". Aberta a
**Issue #802** para esse build, referenciando esta decisão, a ser atacada pelo
agente `arquiteto-docker-deploy`/skill correspondente.

**O que continua sendo ato humano:** depois que a stack existir, a purga dos
dados fictícios hoje em produção (`backend/scripts/purga_dados_homologacao.py`)
continua exigindo backup prévio e execução manual na VPS — este executor não
acessa produção.

---

## Resumo do que mudou nesta rodada

| Item | Decisão | Código alterado nesta PR |
|---|---|---|
| 0.1 | **Revisado**: sem ferramenta de erro (nem Sentry nem self-hosted); PR #773 segue como estava, comentário anterior retratado | `observability.py` (`release` revertido — nenhuma mudança líquida) |
| 0.2 | Embeddings locais/fastembed ratificados | nenhum (só registro) |
| 0.4 | Retenção offsite = 30 dias | `config.py`, `.env.example` |
| 0.5 | Topologia: mesma VPS, compose separado, dados fictícios | nenhum (Issue de build aberta à parte) |

## Revisão de segurança

`security-auditor: executado` sobre o diff de código original
(`observability.py` + `config.py`): nenhum achado crítico ou alto. O scrub de
PII do Sentry (`_before_send`, `_SCRUB_KEYS`) e `send_default_pii=False`
seguem intactos. A retenção maior do backup cifrado é característica inerente
a qualquer retenção >0, não um problema introduzido — nota de acompanhamento
não bloqueante: reavaliar a rotação de `BACKUP_ENCRYPTION_KEY` quando o
sistema tiver histórico real de uso. Veredito: seguro para prosseguir.
*(Nota pós-revisão: `observability.py` voltou ao estado original — sem `release`
— após a decisão 0.1 ser revista; a parte do parecer sobre `config.py`/retenção
continua valendo integralmente.)*

## Riscos residuais

- **0.1 é agora um risco aceito, não um problema resolvido**: sem coletor de
  erro, o EJC volta a depender de reclamação de usuário ou checagem manual de
  log para saber que algo quebrou em produção. Se isso se tornar doloroso na
  operação real, o caminho de volta mais barato é o GlitchTip self-hosted
  (mesmo código, sem custo recorrente, sem dado saindo do VPS) — não o Sentry
  SaaS nem reabrir o PR #773.
- A retenção de 30 dias (0.4) é uma escolha razoável, não uma exigência legal
  identificada — pode ser ajustada livremente sem migração de dado.
- A topologia de homologação (0.5) é decisão de baixo custo para reverter
  (é só um arquivo compose a mais); o que não foi feito aqui é o trabalho de
  implementá-la.
