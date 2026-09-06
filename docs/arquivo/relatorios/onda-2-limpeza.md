# Onda 2 — Limpeza: o que se confirmou e o que não

Verificação item a item da **Onda 2** do Prompt Mestre de Refatoração Total contra
o código, em 2026-08-07 sobre `origin/main` (`8b11007`).

Vale a mesma advertência da Onda 1: a auditoria que originou o prompt foi feita
**sem acesso ao código-fonte** — só pela API de produção e pelos bundles publicados.
Três dos itens desta onda não sobreviveram à conferência no arquivo, e executá-los
ao pé da letra teria **removido funcionalidade em uso**.

---

## Feito

### Prefixo `/v1` duplicado — 27 call sites normalizados

**O que a auditoria viu:** `/api/v1/v1/despesas` respondendo 200 e
`/api/v1/despesas` dando 404, e concluiu que o backend tinha o prefixo duplicado.

**O que é:** o inverso. `lib/api.ts` usa `baseURL: "/api/v1"`, e o backend expõe
`/api/v1` pelo `APIVersionCompatibilityMiddleware`, que reescreve `/api/v1/X` →
`/api/X` (nenhum router é duplicado). O interceptor de request do cliente já
apara `/api/v1/`, `/api/` e `/v1/` — por isso as chamadas escritas como
`/v1/despesas` funcionavam: eram podadas para `/despesas` e chegavam certo.

**Por que mexer, então:** o próprio interceptor se declara *"compatibilidade
transitória"*. Havia **27 call sites em 9 arquivos** dependendo dessa poda; remover
o shim quebraria as 27 de uma vez, sem aviso.

**O que foi feito:** os 27 caminhos passam a ser escritos na forma canônica (sem
prefixo), e `src/lib/api.prefixo.test.ts` trava o padrão — varre a árvore e
reprova qualquer `api.<método>("/api/…"|"/v1/…"|"/api/v1/…")`. O guarda tem um
teste do próprio detector, para não passar por vacuidade, e isenta quem fala com
o backend por fora do cliente (`streamSSE`, `refreshAccessToken` e os
`backendPrefixes` do registry, que são metadado).

### Dois radares → uma porta, dois modos

**Confirmado.** `RadarCompliance` (`/compliance/radar`) e `RadarRegulatorio`
(`/radar-regulatorio`) respondiam à mesma pergunta — *"o que apareceu que me
afeta?"*. O feed de compliance já consolida Diário Oficial, monitoramento
regulatório e autos ambientais priorizados por risco; o regulatório é o **digest
agregado da mesma matéria-prima**.

Viraram `?modo=feed|digest` de `pages/Radar.tsx`, com as duas rotas antigas em
`LEGACY_REDIRECTS`. Os dois componentes originais foram **preservados** e são
renderizados embutidos (sem cabeçalho próprio) — reescrever 429 linhas já
testadas para unificar uma porta de entrada não pagaria o risco.

**RBAC:** a porta única herda `ROLES.compliance`, o gate **mais restritivo** dos
dois. A fusão não pode alargar quem enxerga o feed de risco, e há teste travando
isso.

---

## Não feito — a premissa não se sustenta

### "Ingestores duplicados: um por fonte"

`stj.py`, `tjmg.py` e `lexml.py` existem em `services/ingestors/` **e** em
`services/juris_import/`, mas não são cópias — são duas camadas com trabalhos
diferentes, documentadas como tais no próprio código:

| | `services/ingestors/` | `services/juris_import/` |
|---|---|---|
| Disparo | crawler **agendado** por temas curados (`scheduler.py`) | importação **on-demand** pelo advogado (`routers/juris_import.py`) |
| Destino | RAG | RAG **+** base de citações validadas do gate anti-alucinação |

E elas já compartilham o que dá: `juris_import/stj.py` importa `CKAN`, `ORGAOS` e
`_monta_conteudo` de `ingestors/stj.py`; o TJMG usa **o mesmo keyspace de dedup**
nos dois lados — explicitamente, "para o crawler agendado não reimportar o que o
advogado importou on-demand, e vice-versa". Os dois `lexml.py` não têm
sobreposição de código (federação por tema × parser SRU/CQL).

**Fundir removeria o crawler agendado ou a importação on-demand.** Não foi feito.

### "Ferramentas + Mapa de Módulos → um inventário"

Não são o mesmo inventário:

- **Ferramentas** (`/ferramentas`) — hub de **descoberta**, para o advogado
  chegar aos módulos que ficaram fora do menu principal.
- **Mapa de Módulos** (`/mapa-modulos`, `ROLES.gestores`) — inventário
  **técnico**, que cruza o manifesto de rotas do frontend com o registro de
  dependências e endpoints do backend e marca divergências.

Público e propósito diferentes. Some-se a isso que o `CLAUDE.md` já registra que
`GET /system-modules/mapa` **subdetecta rotas e documenta ao menos 5 caminhos
incorretos** — fundir levaria dado sabidamente não confiável para a navegação do
advogado. **Não foi feito.**

### "Descontinuar o AILog legado"

O nome do item é impreciso. `AILog` (`app/models/ai_log.py`, tabela `ai_logs`)
**não é legado** — é a trilha de auditoria obrigatória de LGPD/OAB, e a própria
auditoria a trata como fonte de verdade em outros pontos.

O que está marcado `DEPRECATED` no código é o **shim `app/core/ai_brain.py`**.
A docstring dele fala em "~16 consumidores legados"; a contagem real hoje é **4**
(`routers/clients.py`, `routers/cases.py`, `routers/intelligence_v3.py`,
`services/sentimento_magistrado.py`).

Migrar não é mecânico: `processar_demanda` tem contrato próprio (dict com
`status`/`resposta`/`modelo`) do qual a gravação do AILog depende em cada call
site. E o shim **não é furo de conformidade** — ele sanitiza PII antes de
qualquer envio e delega ao `ai_gateway` central, exatamente como a regra 4 do
`CLAUDE.md` exige. Mexer nos 4 pontos do núcleo de IA junto com uma fusão de
telas tornaria a revisão pior, sem ganho de segurança.

**Encaminhado para Issue própria.**

---

## Itens desta onda que não são código

| Item | Por quê |
|---|---|
| Excluir 13 clientes fictícios e correlatos via Lixeira | Operação no banco de **produção** — vedada ao executor (`CLAUDE.md`, regra 9) |
| Chamadas mortas do front (`produtividade/`, `workflow/`, `lead/`) | **Premissa desatualizada**: os routers existem e estão registrados em `main.py`; `Leads` é `CRMLeads.tsx` sobre `/clients/?status=lead` |
| Relógio + citação institucional no cabeçalho | **Não existem** — `Layout.tsx` não tem nenhum dos dois |
| Rótulo "PADRÃO VISUAL LAW EJC" vazando nas peças | **Não existe** em nenhum arquivo do repositório |
