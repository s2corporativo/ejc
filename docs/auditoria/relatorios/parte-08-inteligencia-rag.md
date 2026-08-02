# EJC — Auditoria Técnica, Parte 8
## Auditoria minuciosa da camada de Inteligência (IA, RAG, Jurimetria, Ferramentas de Qualidade)

**Sistema:** Ecossistema Jurídico Clovis (EJC) — `https://ejc.depaulateixeira.adv.br`
**Sessão autenticada:** `admin@depaulateixeira.adv.br` (superadmin)
**Data/hora do teste:** 2026-07-29, 10h15–10h40
**Escopo:** os 10 módulos do grupo "Inteligência" identificados no Mapa de Módulos oficial (Parte 7) — Sala Jurídica, Núcleo de IA, Workspace de Inteligência, Ferramentas IA, Base de Conhecimento/RAG, Jurimetria, Victory Vault, Radar Regulatório, Diário Oficial, Notícias — que concentram a maior densidade de endpoints do sistema (340+ rotas mapeadas, com sobreposição no núcleo `/api/ai/*`) e não haviam sido objeto de auditoria dedicada nas Partes 1–7 (item 4.4 do Plano Diretor).

---

## 1. Resumo executivo

Esta rodada usou, sempre que possível, os próprios painéis internos de governança de IA do EJC (não inferência externa) — o que eleva significativamente o grau de confiança dos achados abaixo em relação às Partes 1–6.

| Achado | Severidade | Confirmado por |
|---|---|---|
| **Base de conhecimento RAG com 0 de 47.359 trechos (chunks) com embedding gerado** | **Crítica** | `GET /rag/governanca/saude` (dado oficial do sistema) |
| **Cobertura de conteúdo jurídico por área: 29 de 36 áreas em status "crítica" (score 20/100), média geral 26/100** | **Crítica** | `GET /rag/governanca/cobertura` (dado oficial) |
| Camada de "modelo complexo" configurada como idêntica ao "modelo rápido" (`modelo_complexo: "(=rapido)"`) | Alta | `GET /ai/status` |
| Contradição entre painéis sobre quantos provedores de IA estão configurados (2 vs. 3) | Média | `GET /diagnostico/central` (Parte 7) vs. `GET /ai/core/status` (esta rodada) |
| Três inventários de "skills" de IA não reconciliados (48 nativas / 76 no núcleo / 163 no catálogo) | Média | `GET /ai/core/native-skills/coverage`, `/ai/core/skills`, `/ai/skills/list` |
| Módulos de Jurimetria e Victory Vault (motor de teses) sem dados reais — arquitetura pronta, base vazia | Média (maturidade, não bug) | `GET /jurimetria/*`, `GET /teses/ranking` |
| Loop de feedback de qualidade da IA com **zero avaliações registradas** desde sempre | Média | `GET /ai/logs/feedback/resumo` |
| Alertas não lidos do Diário Oficial subiram de 262 (Parte 3, 03h) para **281** (10h40, mesmo dia) | Média (confirma tendência, não corrige) | `GET /diario-oficial/alertas/nao-lidos/count` |
| **Ferramentas de validação de citação e crítica adversarial funcionam corretamente e com framing ético adequado** | **Positivo** | Testes ao vivo (Seção 5) |
| Duplicação de taxonomia de áreas reaparece pela 4ª vez, agora na cobertura de RAG | Média | `GET /rag/governanca/cobertura` |

O achado mais importante desta rodada é a confirmação, com dado oficial e quantificado, de que **a IA jurídica do EJC hoje não tem, na prática, uma base de conhecimento pesquisável semanticamente** — não é uma limitação sutil, é uma condição binária (0 de 47.359 trechos indexados) que reduz a recuperação de contexto ao fallback textual em 100% das consultas.

---

## 2. Núcleo de IA — infraestrutura e configuração

### 2.1 `GET /ai/status`

```json
{
  "ai_enabled": true,
  "anthropic_configurado": true,
  "groq_configurado": true,
  "modelo_rapido": "claude-haiku-4-5-20251001",
  "modelo_complexo": "(=rapido)",
  ...
  "aviso": "Todos os resultados são rascunhos. Revisão humana obrigatória."
}
```

**Achado:** o campo `modelo_complexo` está literalmente configurado como `"(=rapido)"` — ou seja, o sistema não usa um modelo mais capaz para tarefas complexas; usa o mesmo modelo rápido (`claude-haiku-4-5`) para tudo, apesar de existirem 4 "níveis de inteligência" declarados na mesma resposta (`padrao`, `alto`, `maximo`, `executivo`). Isso levanta uma questão técnica direta: **os níveis de inteligência mais altos oferecem, hoje, algum ganho real de qualidade, ou são apenas rótulos sobre o mesmo modelo?** Isso é relevante para a análise da Parte 4 (erro de CPC art. 487, II repetido em múltiplas skills) — um modelo mais robusto para tarefas de "nível máximo" poderia, em tese, reduzir esse tipo de erro. **Recomendação:** confirmar com a equipe técnica se essa configuração é temporária (ex.: contenção de custo) ou definitiva, e documentar a real diferença entre os 4 níveis de inteligência oferecidos ao usuário — se não há diferença de modelo, a interface não deveria sugerir que há.

### 2.2 `GET /ai/core/status` — Orquestrador Central

```json
{
  "nucleo": "SingleAICoreOrchestrator",
  "agente_coordenador": "EJCCoordinatorAgent",
  "agentes": 37,
  "skills": 76,
  "skills_nativas": {"legal_areas": {"expected":14,"covered":14}, "modules": {"expected":34,"covered":34}, "total_native_skills":48, "complete": true},
  "providers": {"ollama": false, "anthropic": true, "groq": true, "maritaca": true},
  "policy": {"externos_permitidos": true, "sanitizacao_para_externo": true, "hitl_obrigatorio": true, "prioridade": "anthropic,maritaca,groq,ollama"}
}
```

**Ponto positivo confirmado:** cobertura de skills nativas é 100% completa (14/14 áreas jurídicas, 34/34 módulos) — a arquitetura de roteamento de IA por área/módulo está bem constituída, sem lacunas de cobertura estrutural.

**Achado — contradição entre painéis:** este endpoint reporta `providers: {anthropic: true, groq: true, maritaca: true}` (**3 provedores configurados**), enquanto a Central de Diagnóstico (Parte 7, Seção 3) reportou explicitamente **"2 provedor(es) configurado(s): anthropic, groq"**, sem mencionar Maritaca. Dois painéis oficiais do mesmo sistema, consultados na mesma sessão de auditoria, divergem sobre um dado objetivo e verificável (quantos provedores de IA estão configurados). Isso é o **segundo caso confirmado** de inconsistência interna entre painéis de diagnóstico do EJC (o primeiro foi o status contraditório de "Backup offsite" na Parte 7). **Recomendação:** identificar qual painel lê a fonte de verdade correta (provavelmente variáveis de ambiente distintas ou lógicas de verificação diferentes) e corrigir o painel divergente — a essa altura, nenhum dos dois painéis de status deveria ser tomado como автoritativo sem checagem cruzada.

### 2.3 Inventários de "skills" não reconciliados

| Fonte | Contagem | Escopo declarado |
|---|---|---|
| `GET /ai/core/native-skills/coverage` | 48 | "skills nativas" (auto-geradas por área × módulo) |
| `GET /ai/core/skills` | 76 | skills registradas no orquestrador central |
| `GET /ai/skills/list` | 163 | catálogo completo executável via `/ai/skills/execute` (confirmado nesta rodada — mesma contagem da Parte 4) |

Três números diferentes para "quantas skills de IA o sistema tem", sem relação documentada entre eles (é 48 nativas + 28 outras = 76? E os 163 do catálogo incluem os 76, mais variantes por contexto/área?). **Não é necessariamente um bug** — pode ser arquitetura legítima em camadas — mas é uma lacuna de documentação que dificulta qualquer auditoria de cobertura ou de custo (quantas chamadas de IA distintas o sistema realmente pode disparar). **Recomendação:** documentar explicitamente a relação entre os três inventários.

---

## 3. Base de Conhecimento e RAG — o achado mais grave desta rodada

### 3.1 `GET /rag/status` e `GET /rag/stats`

```json
{"vetorizado": 1208, "sem_vetor": 3281, "erro": 0, "total": 4489}
```
```json
{"total_docs": 4489, "total_chunks": 51651, "chunks_indexados": 0, ...}
```

**Achado crítico:** dos 51.651 trechos (chunks) de texto que compõem a base de conhecimento jurídico, **0 (zero) estão indexados para busca**. No nível de documento inteiro, apenas 26,9% (1.208 de 4.489) têm algum vetor gerado — número que, combinado com "chunks_indexados: 0", sugere que essa vetorização parcial é resíduo de uma janela anterior à desativação de `EMBEDDINGS_ENABLED` (achado da Parte 7), e não está sendo usada em buscas atuais.

### 3.2 `GET /rag/governanca/saude` — painel de saúde do RAG

```json
{
  "summary": {
    "total_docs": 4399, "usable_docs": 3832, "usable_percent": 87.1,
    "vectorized_docs": 1207, "vectorized_percent": 27.4,
    "total_chunks": 47359, "embedded_chunks": 0, "chunks_without_embedding": 47359,
    "duplicate_groups": 14, "conflict_groups": 18,
    "stale_sources": 525, "legal_status_unverified": 1375
  }
}
```

Este é o painel de governança que o próprio EJC mantém para monitorar a qualidade da sua base RAG — e ele já sinaliza, com **100 alertas de severidade "critical"** retornados (provavelmente truncados pela paginação, dado que 1.375 documentos estão com status legal não verificado), os seguintes problemas:

- **`embedded_chunks: 0`** — confirma, por uma segunda via independente, o achado da Seção 3.1.
- **1.375 documentos com "status legal não verificado"** — isto é especialmente sensível para uma base jurídica: um documento de legislação ou jurisprudência cujo status (vigente/revogado/superado) não foi confirmado pode ser citado pela IA como se estivesse em vigor sem sê-lo. É o tipo de falha que se manifesta exatamente como o erro de CPC art. 487, II identificado na Parte 4.
- **18 grupos de conflito** — por exemplo, duas versões distintas (hashes diferentes) da mesma proposição legislativa (`PL 1552/2026`) coexistindo na base sem resolução.
- **14 grupos de "duplicados"** — ao inspecionar um exemplo, encontrei um agrupamento que reúne **três acórdãos do STJ com números de processo diferentes** (REsp 2201422, REsp 2200477, REsp 2205262) sob o mesmo hash de "duplicado". Três decisões com números de processo distintos raramente deveriam compartilhar hash de conteúdo idêntico — **isso é um indício (não uma confirmação) de possível falha na lógica de deduplicação** (hash calculado sobre um trecho insuficientemente específico do documento, por exemplo). Recomendo que a equipe técnica verifique manualmente esse agrupamento específico antes de aceitar a governança de duplicidade como confiável.
- **525 fontes desatualizadas ("stale_sources")**.

### 3.3 `GET /rag/governanca/cobertura` — cobertura de conteúdo por área jurídica

Resultado agregado (36 entradas de área, refletindo múltiplas convenções de nomenclatura coexistindo — ver Seção 6):

| Métrica | Valor |
|---|---|
| Áreas em status "crítica" (score 20/100) | 29 de 36 |
| Áreas em status "atenção" (score 40–60/100) | 6 de 36 |
| Áreas em status "boa" (score 100/100) | 1 de 36 (**apenas "Geral"**) |
| Score médio entre todas as áreas | **26,1/100** |

Para praticamente todas as áreas de atuação do escritório, as dimensões **súmulas, jurisprudência e doutrina estão em 0** (a única dimensão com algum conteúdo, na maioria das áreas, é "modelos" — modelos de documento). Isto quer dizer que, hoje, quando a IA responde sobre uma questão de Direito Bancário, Ambiental, Empresarial etc., ela **não tem, na prática, súmulas nem doutrina na própria base para consultar** — depende inteiramente do conhecimento geral do modelo de linguagem subjacente, não de uma base curada e verificada pelo escritório. **Esta é a explicação técnica mais concreta e completa, encontrada em toda a auditoria, para a origem plausível do erro jurídico identificado na Parte 4** (uso do dispositivo legal incorreto para decadência): a IA não estava (e ainda não está) apoiada por uma base RAG funcional na área em questão.

**Recomendação de prioridade máxima:** (a) reabilitar `EMBEDDINGS_ENABLED=true` (já recomendado na Parte 7); (b) priorizar ingestão de súmulas e doutrina para as áreas de maior volume de casos do escritório antes de qualquer alegação de que a IA "conhece" a área; (c) resolver os 1.375 documentos de status legal não verificado antes de reindexar, para não vetorizar conteúdo potencialmente revogado.

---

## 4. Jurimetria e Victory Vault — arquitetura presente, dados ausentes

| Endpoint | Resultado |
|---|---|
| `GET /jurimetria/overview` | `{"total_vinculos":0,"venceu":0,"perdeu":0,"acordo":0,"pendente":0,"taxa_sucesso_geral":null,"total_teses_ativas":24,"total_casos":9}` |
| `GET /jurimetria/por-area`, `/por-tribunal`, `/por-tese`, `/tendencias` | Todos retornam lista vazia `[]` |
| `GET /jurimetria/desfechos` | `{"total_encerrados":0,"por_resultado":[],"licoes_aprendidas":[]}` |
| `GET /jurimetria/ext/stats` | Apenas 1 registro (TJMG), oriundo de ingestão externa (DataJud) |
| `GET /teses/ranking` (Victory Vault) | `[]` |

**Avaliação:** os módulos de Jurimetria e Victory Vault (motor de teses, matriz de provas) têm arquitetura de API completa — incluindo endpoints de **predição de êxito** (`/jurimetria/predicao-exito`, `/jurimetria/ext/predicao/provimento`) — mas **nenhum dado histórico real para operar**. Isso não é, em si, um bug: reflete a maturidade natural de um escritório cujos casos no sistema ainda não se encerraram em volume suficiente para gerar estatística. Notei também que os endpoints de predição não são chamados por nenhum bundle de frontend identificado (`InteligenciaWorkspace` usa apenas `overview`, `desfechos`, `por-area`, `por-tese`, `por-tribunal`, `ext/benchmarks`, `ext/stats`) — ou seja, **a funcionalidade de predição de êxito existe no backend mas não está conectada a nenhuma tela hoje**.

**Recomendação preventiva, a ser tratada antes de qualquer ativação futura dessa funcionalidade:** quando o volume de dados permitir popular `/jurimetria/predicao-exito`, a resposta e sua apresentação na interface devem ser revisadas quanto à conformidade com o art. 6º, parágrafo único, e art. 34, XXIX do Código de Ética da OAB — que vedam a promessa de resultado. Uma funcionalidade de "predição de êxito" é legítima como ferramenta de análise estatística interna (ex.: para orientar decisão sobre acordo), mas a linguagem exposta ao usuário (e, principalmente, a um cliente, caso venha a ser exposta no portal) precisa deixar claro que é estimativa histórica, não previsão do caso concreto. Como a funcionalidade está hoje sem dados e sem tela, não há o que testar diretamente — este é um alerta preventivo para quando ela for ativada.

---

## 5. Ferramentas de qualidade e segurança da IA — achados positivos

Testadas ao vivo nesta rodada, com conteúdo de teste deliberadamente problemático para verificar se as ferramentas identificam os problemas.

### 5.1 `POST /ia/validar-citacoes` — funciona corretamente

Enviado texto com uma citação real mas sem dados verificáveis ("Súmula 331 TST") e uma citação de recurso **inventada deliberadamente** ("REsp 999999/SP"). Resultado:

- Classificou ambas como "identificada" mas **"NÃO confirmada em fonte externa"**.
- Para a citação inventada, sinalizou explicitamente: *"possível alucinação ou julgado sem tribunal+data verificáveis"*.
- Retornou `"bloqueia_aprovacao": true` e `"politica": "bloquear"`.
- Incluiu o aviso: *"Verificação automática NÃO substitui a conferência humana: toda citação deve ser confirmada na fonte oficial antes do protocolo (responsabilidade do advogado — OAB)."*

**Avaliação: ferramenta bem projetada e com framing ético correto.** Erra para o lado seguro (bloqueia por padrão citações não confirmadas) e atribui corretamente a responsabilidade final ao advogado.

### 5.2 `POST /ia/critica-adversarial` — funciona corretamente

Enviado um texto de teste deliberadamente frágil ("consumidor tem direito absoluto e garantido a indenização em qualquer caso... dano moral em toda e qualquer hipótese... triplo do valor do produto"). A ferramenta:

- Identificou corretamente a **incoerência interna** (alegar dano moral automático e ao mesmo tempo um critério de cálculo tarifado incompatível com jurisprudência de arbitramento).
- Listou lacunas fáticas e probatórias reais (ausência de partes, contrato, provas, nexo causal).
- Gerou **5 teses defensivas prováveis em ordem de risco**, incluindo corretamente a tese de "mero dissabor não gera dano moral" — posição consolidada na jurisprudência dos tribunais superiores.
- Atribuiu **nota de robustez 3** (em escala, presumivelmente, de 0–10) — avaliação coerente com a fragilidade proposital do texto de teste.
- Recomendou verificar fontes de jurisprudência antes de afirmá-las, em vez de inventar precedentes.

**Avaliação: esta é a evidência mais forte, em toda a auditoria, de que o sistema tem um mecanismo de autocrítica jurídica funcional e tecnicamente sólido — inclusive mais confiável, neste teste específico, do que a geração de peças avaliada na Parte 3.** Recomendo que o uso desta ferramenta (`critica-adversarial`) seja **promovido a etapa obrigatória** no fluxo de revisão de qualquer peça antes da aprovação, dado que seu desempenho neste teste foi superior ao que se observou na geração de conteúdo.

### 5.3 Loop de feedback de qualidade — não adotado

`GET /ai/logs/feedback/resumo` retornou `{"util":0,"nao_util":0,"total_avaliados":0,"escopo":"global"}`. **Nenhuma resposta de IA gerada pelo sistema, em toda sua história de uso — incluindo os múltiplos testes das Partes 3 a 5 desta própria auditoria — foi avaliada como útil ou não útil por nenhum usuário.** Isso indica que a interface de feedback (se existe na tela) não está sendo usada, ou não está suficientemente visível. Sem esse dado, o sistema não tem como identificar automaticamente quais skills/respostas têm pior desempenho percebido pelos próprios advogados. **Recomendação:** tornar o botão de feedback mais proeminente na interface (ex.: obrigatório antes de fechar um resultado de IA) e revisar periodicamente `GET /ai/logs/feedback/resumo` como métrica de saúde do produto.

---

## 6. Reincidência do achado de taxonomia de áreas duplicada (4ª ocorrência)

A resposta de `GET /rag/governanca/cobertura` lista **36 "áreas"**, mas várias são a mesma área jurídica representada em convenções diferentes — por exemplo, `"Administrativo"` (maiúscula, com `lacunas: [legislacao, sumulas, jurisprudencia, doutrina]`) e `"administrativo"` (minúscula, com `lacunas: [sumulas, jurisprudencia, modelos, doutrina]`) aparecem como duas entradas distintas, com estruturas de lacunas até diferentes entre si. O mesmo padrão se repete para praticamente todas as áreas (Bancário/bancário, Ambiental/ambiental, Empresarial/empresarial etc.).

Esta é a **quarta vez**, ao longo de toda a auditoria, que a ausência de um catálogo único de áreas se manifesta como problema real (as três anteriores: duplicação do catálogo em 5 módulos de frontend — Parte 1; "licitações" como área de primeiro nível — Partes 1 e 5; e agora fragmentação da própria métrica de cobertura de conhecimento, que deveria ser a ferramenta mais confiável para decidir onde investir em conteúdo, mas está contando a mesma área duas vezes com números diferentes). **Isso eleva a prioridade da correção 3.1 do Plano Diretor (unificar o catálogo de áreas) — não é mais apenas uma inconsistência cosmética, está distorcendo a própria métrica de saúde da base de conhecimento que orientaria os investimentos de conteúdo.**

---

## 7. Diário Oficial, Notícias e Radar Regulatório

| Item | Resultado |
|---|---|
| Alertas não lidos do Diário Oficial | **281**, ante 262 registrados na Parte 3 (mesma manhã, ~7h de intervalo) — confirma tendência de acúmulo contínuo sem tratamento, aumentando o risco de fadiga de alerta já apontado |
| `GET /noticias` | Funcional — 25 itens, fontes `ConJur` e `JOTA`. Achado menor: campo `atualizado_em` retorna timestamp Unix bruto (`1785321059.17`) em vez de formato ISO 8601 usado no restante da API — inconsistência de formatação, baixo impacto |
| `GET /v1/regulatorio/digest-semanal` | 404 — rota mapeada no Mapa de Módulos mas não respondeu nesta chamada; possível diferença de prefixo de versão (`/v1/` vs. padrão `/api/`) não confirmada, requer verificação direta no código-fonte antes de classificar como bug |

---

## 8. Plano de correção específico da camada de Inteligência — priorizado

| # | Ação | Prioridade | Esforço |
|---|---|---|---|
| I1 | Reabilitar `EMBEDDINGS_ENABLED=true` e reindexar os 47.359 chunks (0% embedded hoje) | **Crítica** | Baixo (config) + Médio (tempo de reindexação) |
| I2 | Priorizar ingestão de súmulas, jurisprudência e doutrina nas áreas de maior volume do escritório — hoje 29/36 áreas em cobertura "crítica" (score 20/100) | **Crítica** | Alto (curadoria de conteúdo, contínuo) |
| I3 | Resolver os 1.375 documentos com status legal não verificado antes de reindexar (risco de citar norma revogada) | Alta | Médio |
| I4 | Investigar os 18 grupos de conflito e, em especial, verificar manualmente o agrupamento de "duplicados" que reúne 3 acórdãos STJ com números de processo distintos sob o mesmo hash — possível falha na lógica de deduplicação | Alta | Baixo (investigação) |
| I5 | Reconciliar e documentar a divergência entre painéis sobre provedores de IA configurados (2 vs. 3) | Média | Baixo |
| I6 | Documentar a relação entre os 3 inventários de skills (48/76/163) | Baixa | Baixo |
| I7 | Esclarecer se `modelo_complexo = modelo_rapido` é intencional/temporário; se não houver diferença real, ajustar a interface para não sugerir 4 níveis de inteligência distintos | Média | Baixo (decisão) + Médio (se exigir mudança de modelo) |
| I8 | Promover `POST /ia/critica-adversarial` a etapa obrigatória no fluxo de revisão de peças, dado o desempenho superior observado neste teste | Média | Baixo (fluxo) |
| I9 | Tornar o mecanismo de feedback de IA mais visível/obrigatório na interface — hoje zero avaliações registradas desde sempre | Média | Baixo |
| I10 | Endereçar o crescimento contínuo de alertas não lidos do Diário Oficial (281 e subindo) — já recomendado na Parte 3, ainda não tratado | Média | Médio (processo) |
| I11 | Unificar taxonomia de áreas com prioridade elevada — agora confirmado que distorce também a métrica de cobertura de RAG (4ª ocorrência do mesmo problema-raiz) | Alta (reclassificada) | Médio |
| I12 | Padronizar formato de timestamp em `/noticias` (Unix → ISO 8601) para consistência com o restante da API | Baixa | Baixo |
| I13 | Confirmar se `/v1/regulatorio/digest-semanal` é rota ativa; corrigir prefixo de versão se for divergência de roteamento | Baixa | Baixo (investigação) |
| I14 | Antes de qualquer ativação de `/jurimetria/predicao-exito` com dados reais, revisar framing da resposta quanto à vedação de promessa de resultado (art. 6º, parágrafo único, e art. 34, XXIX do Código de Ética da OAB) | Preventiva (sem prazo definido — depende de quando houver dados) | Baixo |

---

## 9. Nota metodológica

Todos os achados desta parte foram obtidos por chamadas diretas aos próprios painéis de governança e diagnóstico de IA do EJC (`/rag/governanca/*`, `/ai/core/*`, `/ai/status`, `/jurimetria/*`) com token JWT de sessão superadmin, complementadas por dois testes ao vivo das ferramentas de qualidade (`/ia/validar-citacoes`, `/ia/critica-adversarial`) com conteúdo de teste deliberadamente problemático, elaborado para verificar se essas ferramentas identificam erros — não para gerar conteúdo real. Nenhum dado de cliente real foi usado nesta rodada. Os números de cobertura, saúde do RAG e contagem de skills são leitura direta da resposta da API, sem transformação ou interpretação além da apresentada.

---

*Documento produzido como Parte 8 da auditoria técnica do EJC, com foco exclusivo na camada de Inteligência (IA/RAG/Jurimetria), item 4.4 do Plano Diretor de Correção. Deve ser lido em conjunto com as Partes 1 a 7 e com o Plano Diretor, cujos itens 1.3, 1.4, 1.5 e 1.6 (relacionados a RAG e raciocínio jurídico da IA) ganham aqui evidência quantificada adicional que reforça sua prioridade.*
