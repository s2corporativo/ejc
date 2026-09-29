# EJC — Auditoria Técnica, Parte 11
## APIs e Sincronização

**Data:** 2026-07-29, 11h20–11h35 · **Sessão:** `admin@depaulateixeira.adv.br` (superadmin)
**Método novo nesta rodada:** extração automatizada de **todas** as chamadas de API dos 68 bundles de frontend (358 chamadas distintas em 55 arquivos) e cruzamento com as rotas registradas no Mapa de Módulos oficial (453 rotas distintas após normalização). Cruzamento inédito — nenhuma rodada anterior fez isso.

---

## 1. ACHADO CRÍTICO — A captura de intimações nunca capturou nada

Este é o achado de maior consequência potencial de toda a auditoria, porque o modo de falha é **perda de prazo processual**.

### 1.1 Os cinco fatos, cada um verificado

| Fato | Evidência |
|---|---|
| A fonte DJEN nunca registrou **um único** documento em toda a sua história | `GET /ia-governanca/fontes` → `djen: {registros_total: 0, registros_novos: 0, ultimo_status: "sucesso"}` |
| Não há nenhuma intimação no sistema | `GET /intimacoes/` → `{"data":[],"total":0}` |
| Existe **1 único prazo** cadastrado no sistema inteiro, e ele é **manual** | `GET /deadlines/` → `total: 1`, campo `origem: "manual"` |
| **Uma única OAB está cadastrada para monitoramento**, e está na conta administrativa genérica | `GET /users/` → `Administrador EJC: djen_oab_numero "251174"/MG` |
| **Os três advogados reais têm o campo vazio** | Clovis Soares (advogado), Guilherme Alves de Paula (sócio), João Pedro Teixeira (advogado) → todos `djen_oab_numero: null, djen_oab_uf: null` |

### 1.2 Por que ninguém percebeu — o monitoramento afere execução, não resultado

```
GET /diagnostico/central → "Jobs monitorados (heartbeat)": status "ok"
  {"job_name":"djen_intimacoes","label":"Captura DJEN (intimações)",
   "cadencia":"diário 06h30","status":"ok","idade_horas":5.0,"last_status":"ok"}

GET /intimacoes/status-captura
  {"sucesso":true,"intimacoes_encontradas":0,"erro":null,"defasado":false}

GET /diagnostico/central → integração DJEN: "ok — Coleta habilitada com ao menos uma OAB monitorada."
```

Três indicadores verdes simultâneos sobre um pipeline que jamais entregou um registro. O heartbeat verifica **se o job rodou**, não **se ele produziu resultado**. É a definição exata de falha silenciosa — e no componente onde ela é mais cara.

### 1.3 O que eu sei e o que eu não sei

**Não afirmo que o senhor está perdendo prazos.** Não tenho como determinar, deste ambiente:

- se `251174/MG` é a sua própria inscrição, apenas cadastrada na conta administrativa em vez da conta `soares@`;
- se os processos do escritório estão efetivamente distribuídos sob essa inscrição ou sob as dos demais advogados;
- se realmente não houve nenhuma comunicação no período — o que é possível, ainda que improvável para um escritório com casos ativos.

O que afirmo é que **as três hipóteses são indistinguíveis pelos painéis do sistema**, e que a configuração atual monitora uma inscrição enquanto três advogados cadastrados não têm nenhuma.

### 1.4 Verificação que só o senhor pode fazer — recomendo hoje

1. Confirmar se `251174/MG` é a inscrição correta e de quem.
2. Cadastrar `djen_oab_numero`/`djen_oab_uf` para **Clovis Soares, Guilherme Alves de Paula e João Pedro Teixeira**.
3. Abrir o portal do DJEN/Comunica CNJ e conferir manualmente se há comunicações nos últimos 30 dias para as inscrições do escritório. **Se houver qualquer comunicação lá que não esteja no EJC, há intimação não capturada** — e isso precisa de tratamento imediato, não de correção de software.
4. Instrumentar alerta por resultado: notificar se a captura retornar 0 por N dias consecutivos, em vez de apenas confirmar que rodou.

---

## 2. AUDITORIA DE APIs

### 2.1 Prefixo `/v1/` duplicado — e retificação de dois achados meus

Confirmei que cinco grupos de rotas estão montados com **prefixo `/v1/` duplicado**:

```
GET /api/v1/despesas                     → 404
GET /api/v1/v1/despesas                  → 200   ← caminho real
GET /api/v1/v1/office-contracts          → 200
GET /api/v1/v1/office-contracts/expiring → 200
GET /api/v1/v1/partner-withdrawals       → 200
GET /api/v1/v1/regulatorio/digest-semanal→ 200
GET /api/v1/v1/kanban-columns            → 200
```

O `baseURL` do frontend é `/api/v1` (confirmado no bundle `api-DXsXndG1.js`), e esses módulos chamam `/v1/despesas` por cima dele — resultando em `/api/v1/v1/...`. Funciona por acidente: o frontend compensa o erro de montagem do backend.

**Retificação:** na **Parte 8 (item I13)** e na **Parte 9 (item 4.4)** eu reportei essas rotas como "não resolvem em produção / 404". Estava incorreto — elas resolvem, num caminho malformado. O defeito é de montagem de router, não de rota inexistente. Corrijo aqui.

**Risco prático:** qualquer integração externa, documentação ou teste que siga o padrão `/api/v1/despesas` falhará. E o `Mapa de Módulos` as registra como `/api/v1/despesas` — ou seja, **o mapa oficial documenta um caminho que não funciona**.

### 2.2 Superfície de API duplicada em dois prefixos

Toda rota testada responde **igualmente** sob `/api/` e sob `/api/v1/`:

| Rota | `/api/` | `/api/v1/` |
|---|---|---|
| `cases/?page_size=1` | 200 | 200 |
| `ai/status` | 200 | 200 |
| `rag/status` | 200 | 200 |
| `clients/?page_size=1` | 200 | 200 |

Cada endpoint tem dois endereços válidos. Implicações: qualquer regra baseada em path (rate limiting, WAF, logging, cache do Nginx, métricas de telemetria de rota) precisa cobrir os dois, ou pode ser contornada usando o prefixo não coberto. Recomendo eleger um prefixo canônico e responder `301` no outro.

### 2.3 Cruzamento frontend × backend

| Métrica | Valor |
|---|---|
| Chamadas de API distintas no frontend | 358 (em 55 bundles) |
| Rotas distintas registradas no Mapa de Módulos | 453 |
| Chamadas do frontend **sem** rota correspondente no mapa | **116** |
| Rotas do backend **nunca chamadas** pelo frontend | **211** |
| Cobertura | **53,4%** |

**Sobre os 116 "ghosts":** testei 34 deles ao vivo. A esmagadora maioria **funciona** (`/etiquetas`, `/ia-governanca/provedores`, `/ia/status`, `/cofre-credenciais`, `/indices/series`, `/nfse`, `/prompts-juridicos`, `/memoria-institucional`, `/raio-x/stats`, `/relatorio/mensal` — todos 200). Conclusão: **o `endpoints_detectados` do Mapa de Módulos é incompleto.**

Isso é relevante porque eu recomendei o Mapa de Módulos, nas Partes 6 e 7, como "fonte de maior confiança do que qualquer inferência externa". Mantenho que é a melhor fonte disponível, mas agora com ressalva documentada: **ele subdetecta rotas e documenta ao menos cinco caminhos incorretos** (item 2.1).

**Sobre as 211 rotas órfãs:** quase metade da superfície de API não é consumida por nenhuma tela. Distribuição principal: `/ai` (23), `/rag` (15), `/cases` (14), `/civel` (9), `/analytics` (7), `/clients` (7), `/empresarial` (7), `/penal` (7), `/honorarios-oab` (7), `/jurisprudencia-externa` (7). Cada rota órfã é superfície de ataque e custo de manutenção sem contrapartida de uso.

### 2.4 Quinze calculadoras jurídicas construídas e invisíveis

Entre as rotas órfãs, identifiquei **15 ferramentas de cálculo jurídico funcionais que nenhuma tela do sistema expõe**:

| Área | Ferramentas sem interface |
|---|---|
| Cível | `calculo-dano-moral`, `partilha-divorcio`, `alimentos-calcular`, `usucapiao-verificar`, `prescricao-consumidor`, `prazos-contestacao`, `rescisao-locacao` |
| Empresarial | `juros-mora`, `prazos-rj`, `verificar-cade` |
| Penal | `dosimetria`, `prescricao-penal`, `prescricao-punitiva`, `prazos-processuais`, `verificar-anpp` |

Testadas: retornam `200` (quando sem parâmetro obrigatório) ou `422` pedindo os parâmetros — ou seja, **estão implementadas e operantes**. Dosimetria da pena, prescrição penal, verificação de ANPP, cálculo de dano moral e partilha de divórcio são exatamente o tipo de ferramenta que economiza tempo diário de advogado.

**Esta é a maior oportunidade de ganho rápido encontrada em toda a auditoria:** valor já construído e pago, a um trabalho de frontend de distância. Recomendo priorizar a exposição dessas 15 rotas acima de várias correções da Fase 3 do Plano Diretor.

### 2.5 Erros e performance encontrados na varredura

**`GET /analytics/roi-por-area` → 500, reproduzível:**
```json
{"detail":"Erro interno. A equipe foi notificada."}
```
A mensagem é **falsa**. A Parte 7 estabeleceu, pelo próprio painel de diagnóstico, que não há coletor de erros persistente (`"Sem coletor de erros persistido no banco"`, Sentry desabilitado). Ninguém foi notificado, e não há registro histórico desse erro. Além do bug em si, recomendo remover a afirmação até que o Sentry esteja ativo — informar ao usuário que a equipe foi notificada quando não foi é pior do que não informar nada.

**`GET /analise-bancaria/modalidades` → 502 intermitente:**
```
1ª chamada: 502 Bad Gateway em 30,5s
2ª chamada: 200 OK        em 18,7s
```
O endpoint leva entre 19 e 30 segundos e ultrapassa intermitentemente o timeout do Nginx. Falha instável é operacionalmente pior que falha determinística: o usuário vê erro, tenta de novo, funciona, e o problema nunca é reportado.

**Redirects 307 em rotas de coleção:** `/agenda-eventos`, `/bank-analysis`, `/environmental`, `/raio-x`, `/module-help` retornam 307 (redirect de barra final do FastAPI). Custa um round-trip extra em cada chamada. Padronizar `redirect_slashes` ou os paths no frontend.

---

## 3. AUDITORIA DE SINCRONIZAÇÃO

### 3.1 Frescor das 14 fontes de ingestão

| Fonte | Status | Última execução | Novos | Total histórico |
|---|---|---|---|---|
| `juris_import_lexml` | sucesso | **164h (6,8 dias)** | 0 | **0** |
| `juris_import_stj` | sucesso | **164h (6,8 dias)** | 0 | **0** |
| `juris_import_tjmg` | sucesso | **164h (6,8 dias)** | 0 | **0** |
| `stj` | sucesso | 104h (4,3 dias) | 51 | 2.595 |
| `planalto` | sucesso | 80h (3,3 dias) | 35 | 36 |
| `datajud_processos` | sucesso | 8,2h | 0 | 1 |
| `camara` | sucesso | 7,4h | 11 | 242 |
| `senado` | sucesso | 7,1h | 0 | 299 |
| **`djen`** | sucesso | 6,4h | 0 | **0** ← Seção 1 |
| `biblia_ejc` | sucesso | 1,6h | 0 | 398 |
| **`anpd`** | **erro** | 0,3h | 0 | 0 |
| `normas_rfb` | sucesso | 0,3h | 0 | 0 |
| `tjmg` | sucesso | 0,3h | 0 | 0 |
| `lexml` | sucesso | 0,3h | 0 | 0 |

**Achados:**

- **Três importadores de jurisprudência (`juris_import_*`) estão dormentes há quase 7 dias e nunca importaram um único registro** (`registros_total: 0`). Estão marcados `ativo: true`. São, na prática, código morto em produção — e explicam parcialmente por que a cobertura de jurisprudência do RAG está zerada em 29 das 36 áreas (Parte 8).
- **`anpd` falha com `ultimo_erro: null`** — erro registrado sem mensagem, impossível de diagnosticar pelo painel. Já reportado na Parte 10; reconfirmado.
- **Quatro fontes que disparei manualmente (`normas_rfb`, `tjmg`, `lexml`, `anpd`) retornaram 0 registros.** A descrição da própria fonte TJMG declara *"parser tolerante fail-safe"*. Um parser fail-safe que retorna 0 sem erro é indistinguível de um que funcionou e nada encontrou — mesmo padrão de falha silenciosa da Seção 1.

### 3.2 Falha sistêmica de observabilidade: monitora-se execução, não resultado

Esta é a causa comum por trás dos achados 1.2, 3.1 e do `anpd`. Os 7 heartbeats monitorados aferem **cadência** (`idade_horas` vs `max_age_horas`) e **não** produtividade. Um job que roda pontualmente todos os dias e entrega zero é indistinguível de um job saudável.

**Correção estrutural recomendada, aplicável a todas as fontes:** além de `last_run_at`, monitorar `registros_total` e alertar quando (a) uma fonte historicamente produtiva zerar, ou (b) uma fonte nunca tiver produzido nada, ou (c) N execuções consecutivas retornarem 0. É correção de baixo custo e alta cobertura — resolve simultaneamente DJEN, os três `juris_import_*`, TJMG e LexML.

### 3.3 Job de reindexação agendado sobre feature desligada

O scheduler (41 jobs ativos) inclui `reembed_rag_orfaos`, com próxima execução para hoje às 12h20. Como `EMBEDDINGS_ENABLED=false` (Parte 8, item I1, ainda pendente), esse job roda periodicamente sem efeito útil. Não é prejudicial, mas confirma que a infraestrutura de reindexação já existe e está agendada — **quando a flag for habilitada, a reindexação dos 47.359 chunks provavelmente ocorrerá sozinha**, o que reduz o esforço estimado do item 1.2 do prompt de correção.

### 3.4 Sincronização de dados internos — falhas já mapeadas, reconfirmadas

| Vínculo que deveria existir | Estado |
|---|---|
| `LegalDoc.validacao_juridica.ai_log_id` ← resultado de `/validar` | **Nunca gravado.** 97 de 98 peças travadas (Parte 5/10) |
| `Caso.jurimetria` ← chance de êxito calculada e registrada em movimentos | `null` no caso, presente no log (Parte 9) |
| `Caso.descricao_fatos` ← conversão Sala Jurídica → Caso | Perdida na conversão (Parte 3) |
| Painéis de diagnóstico entre si | 3 divergências confirmadas (provedores, modelo, backup) (Partes 8/10) |
| `oab_number` × `djen_oab_numero` no cadastro de usuário | Dois campos de OAB, ambos inconsistentes (Seção 1) |

**Padrão comum:** o sistema calcula e registra o dado em um lugar, mas não o propaga ao registro que o consome. Não são cinco bugs independentes — é um padrão arquitetural de gravação não transacional entre registros relacionados, que vale investigar como classe de defeito no código, não caso a caso.

---

## 4. PRIORIDADES DESTA RODADA

| # | Item | Severidade | Ação |
|---|---|---|---|
| 1 | Verificar manualmente no DJEN se há intimações não capturadas; cadastrar OAB dos 3 advogados | **Crítica — hoje** | Você + equipe |
| 2 | Alertar por resultado (não só por execução) em todas as fontes de ingestão | **Crítica** | Dev |
| 3 | Corrigir prefixo `/v1/` duplicado em 5 grupos de rotas | Alta | Dev |
| 4 | Investigar os 3 `juris_import_*` dormentes com 0 registros históricos | Alta | Dev |
| 5 | Expor as 15 calculadoras jurídicas órfãs na interface | **Alta — maior ganho rápido** | Dev frontend |
| 6 | Corrigir 500 em `/analytics/roi-por-area` e remover a mensagem falsa "a equipe foi notificada" | Alta | Dev |
| 7 | Investigar latência de 19–30s em `/analise-bancaria/modalidades` (502 intermitente) | Média | Dev |
| 8 | Eleger prefixo canônico (`/api` ou `/api/v1`) e redirecionar o outro | Média | Dev/Infra |
| 9 | Revisar as 211 rotas órfãs: expor, depreciar ou remover | Média | Dev + você |
| 10 | Corrigir subdetecção de rotas do Mapa de Módulos | Média | Dev |

---

## 5. NOTA METODOLÓGICA E RETIFICAÇÕES

Método: extração por expressão regular das chamadas `.get/.post/.put/.patch/.delete` com template literal nos 68 bundles publicados, normalização de parâmetros de path, e cruzamento com `endpoints_detectados` de `GET /system-modules/mapa`. Chamadas construídas dinamicamente (concatenação de variáveis) não são capturadas por esse método — **o número real de chamadas do frontend é igual ou maior que 358**, e a taxa de rotas órfãs pode ser ligeiramente menor que a apurada.

**Retificações a relatórios anteriores desta auditoria:**
- **Parte 8, item I13** e **Parte 9, item 4.4**: as rotas `despesas`, `office-contracts`, `partner-withdrawals` e `regulatorio/digest-semanal` **não são inexistentes** — estão montadas com prefixo `/v1/` duplicado (Seção 2.1).
- **Partes 6 e 7**: a recomendação do Mapa de Módulos como fonte de maior confiança permanece, agora com a ressalva de que ele subdetecta rotas e documenta caminhos incorretos (Seção 2.3).

---

*Parte 11. Os itens 1, 2 e 5 desta rodada devem ser incorporados ao prompt de correção do Claude Code, o item 1 com precedência sobre tudo que já estava na Fase 1.*
