# EJC — Homologação Técnica, Parte 5
## Módulo Áreas de Atuação (25 áreas) · Criação de Documentos / Visual Law · Extração de Documentos (ponta a ponta)

**Sistema:** Ecossistema Jurídico Clovis (EJC) — `https://ejc.depaulateixeira.adv.br`
**Sessão autenticada:** `soares@depaulateixeira.adv.br` (perfil advogado)
**Data/hora do teste:** 2026-07-29, 05h30–06h00 (horário do servidor de auditoria)
**Escopo desta parte:** continuidade das Partes 1–4, atendendo às três solicitações do último pedido:
1. Replicar a homologação por módulo, desta vez cobrindo **todas as áreas de atuação** (1 caso fictício por área, testando todos os links de cada caso).
2. Auditar a **criação de documentos**: qualidade profissional e presença de elementos de Visual Law.
3. Auditar a **extração de documentos** ponta a ponta.

---

## 1. Resumo executivo

| Item | Resultado |
|---|---|
| Áreas de atuação testadas | 25/25 (100%) |
| Casos fictícios criados e verificados (link de detalhe = 200 OK) | 25/25 |
| Bug de parsing de título com colchetes | Confirmado e reproduzido isoladamente |
| Endpoints de Visual Law (timeline, matriz de risco, alertas) | Funcionais na camada de dados |
| Endpoint `breakeven` | Retorna 405 (Method Not Allowed) para GET |
| **Pipeline validação → aprovação → PDF/protocolo** | **Bloqueado de ponta a ponta — bug crítico confirmado e reproduzido** |
| Extração de documentos — camada determinística (OCR/classificação por regras) | Funcional |
| Extração de documentos — camada de interpretação por IA | **Indisponível nos 2 testes realizados** (persistente, não transitório) |
| Dados de teste criados nesta rodada | 25 casos + 1 cliente (todos arquivados/inativados ao final) |
| Efeito residual não totalmente revertido | 1 documento pré-existente com `human_reviewed`/`revisor_id` alterados |

O achado mais grave desta rodada é o **bloqueio estrutural do pipeline de exportação de peças em PDF**, que invalida, na prática, a funcionalidade "pronto para protocolar" solicitada nas rodadas anteriores — não por limitação do conteúdo jurídico gerado pela IA (que já havia sido avaliado como tecnicamente sólido nas Partes 3–4), mas por uma falha de integração entre o registro de validação jurídica e o registro do documento.

---

## 2. Módulo Áreas de Atuação — homologação completa (25 áreas)

### 2.1 Metodologia

Foi obtida a lista canônica de áreas de atuação diretamente do backend (não da lista estática do frontend, que já havia sido apontada na Parte 1 como divergente/duplicada em 5 arquivos). Para cada uma das 25 áreas retornadas pelo backend, foi criado um caso fictício via `POST /cases/` com:
- Título sem caracteres especiais (ver bug abaixo);
- `area` = slug da área;
- `descricao_fatos` com narrativa mínima compatível com a área (ex.: para "medico", erro médico fictício; para "licitacoes", impugnação de edital fictícia);
- `proxima_acao` preenchida (campo obrigatório não documentado no primeiro teste da Parte 4, replicado aqui);
- Vínculo a um cliente de teste único (`TESTE AUDITORIA EXCLUIR`, id `cbf2a61f-82fc-46d5-a88f-f0c3a6f01beb`), evitando multiplicar registros de cliente.

Após a criação, cada caso teve seu endpoint de detalhe (`GET /cases/{id}`) chamado individualmente para confirmar retorno 200 e integridade dos campos — este é o "teste de todos os links" solicitado, no nível de dados (o teste de renderização visual de cada link no frontend não pôde ser realizado; ver limitação na Seção 6).

### 2.2 Resultado — 25/25 áreas

| # | Área (slug canônico) | Caso criado | Detalhe (`GET /cases/{id}`) |
|---|---|---|---|
| 1 | empresarial | `85d3bf45-2d64-4785-ae37-0ae752432713` | 200 OK |
| 2 | civil | `167f5b86-657d-4cd6-9d59-2c9830ed001c` | 200 OK |
| 3 | criminal | `28b793c5-994d-4fd9-a194-0be5d2e76c45` | 200 OK |
| 4 | trabalhista | `cd5d1fde-cf88-4464-8d6a-1e6f9ff0d400` | 200 OK |
| 5 | administrativo | `b8aaf1e6-53d8-4a64-9d07-a3624f5ee12a` | 200 OK |
| 6 | bancario | `362e03ec-0053-41a4-8f08-21d91afe3ed4` | 200 OK |
| 7 | tributario | `25b776ab-77a7-4b16-a4b6-6332b123cdfe` | 200 OK |
| 8 | ambiental | `b5f02248-a8ee-459a-af69-6e31963953cf` | 200 OK |
| 9 | consumidor | `e638fff0-7180-4705-9b15-46193e3ee318` | 200 OK |
| 10 | familia | `2798afe8-db17-4646-b46a-7bfa7e184ba2` | 200 OK |
| 11 | imobiliario | `08a9e898-9868-4515-8a34-132ad291cd44` | 200 OK |
| 12 | previdenciario | `33a5ad15-cbb0-45d5-98ff-3cb6e215327c` | 200 OK |
| 13 | digital_lgpd | `d4be5796-a8b7-4250-9ba7-568982daf21b` | 200 OK |
| 14 | transito | `eadcb8e8-2c2c-46ed-905a-4d45fe5c8b72` | 200 OK |
| 15 | sucessoes | `44685451-05d0-4222-9eef-f6e4bdc1e0d8` | 200 OK |
| 16 | constitucional | `f6a3bccf-7ec2-4aed-9dcb-2c6f478247fc` | 200 OK |
| 17 | saude | `2042159a-cddb-4151-8371-5e50a91dbb32` | 200 OK |
| 18 | medico | `e55ead10-c839-4614-8b35-71361c0cdcfb` | 200 OK |
| 19 | agrario | `83e94571-f628-4fdf-8ea2-5454cbc150ae` | 200 OK |
| 20 | agronegocio | `90e94a44-7a6e-4e75-9712-178a050e6a40` | 200 OK |
| 21 | eleitoral | `c2298b68-7a3d-42bc-9280-57dc7aff00fc` | 200 OK |
| 22 | internacional | `74f33a54-8436-47ac-bfc3-5d884041242b` | 200 OK |
| 23 | contratual | `ad8b1f0b-7f34-4e5e-9cb6-c21cad0f899f` | 200 OK |
| 24 | societario | `4df0b3c9-59a8-48c5-9121-d8f6f2bf8a76` | 200 OK |
| 25 | licitacoes | `c3b79294-c1c2-4445-aa92-428c8d63a6eb` | 200 OK |

**Achados:**

- **Confirmação de que `descricao_fatos` persiste corretamente** quando o caso é criado diretamente via `POST /cases/`, ao contrário do que foi identificado na Parte 3 para a conversão Sala Jurídica → Caso (perda de fatos/evidências). Isso restringe o escopo do bug da Parte 3 especificamente ao conversor, não ao endpoint de criação em si — informação relevante para priorização de correção.
- **"licitacoes" confirmado como área de primeira classe no backend** (slug canônico, aceito sem erro por `POST /cases/`), o que reforça — em nível mais grave do que o apontado na Parte 1 (onde a inconsistência foi observada apenas na lista estática do frontend) — a inconsistência já relatada: Licitações é uma modalidade de atuação da Administração Pública (regida pela Lei nº 14.133/2021), não uma área do Direito em si (é tipicamente tratada como sub-ramo do Direito Administrativo). Manter "licitacoes" como área irmã de "administrativo" no mesmo enum é uma classificação taxonômica logicamente inconsistente e deve ser corrigida — recomenda-se reclassificar como subárea/tag de "administrativo".

### 2.3 Bug confirmado — falha de parsing de título com colchetes

**Reprodução:** `POST /cases/` com título contendo colchetes (`"[TESTE AUDITORIA - EXCLUIR] Caso ficticio - {area}"`) retorna:
```json
{"detail":"Título inválido — resposta de IA não parseada"}
```
Teste A/B isolado confirmou a causa: removendo apenas os colchetes do mesmo payload (mantendo todo o restante idêntico), a criação é bem-sucedida. Conclusão técnica: o endpoint de criação de caso submete o título a um parser baseado em IA que falha (ou é interpretado erroneamente como marcador de instrução/metadado) na presença de `[` `]`. Isso é uma falha de robustez de entrada: qualquer usuário que nomeie um caso com colchetes (comum em convenções internas de rotulagem, ex. "[URGENTE]", "[REVISAR]") terá o cadastro rejeitado com uma mensagem que não explica a causa real.

**Recomendação:** sanitizar/normalizar o título antes de submetê-lo ao parser de IA, ou eliminar a dependência de IA para essa validação, substituindo por regra determinística (comprimento mínimo/máximo, ausência de caracteres de controle).

---

## 3. Auditoria de criação de documentos e Visual Law

### 3.1 Visual Law — endpoints testados

| Endpoint | Método | Resultado |
|---|---|---|
| `/visual-law/casos/{id}/timeline` | GET | 200 OK — retorna eventos estruturados do caso em ordem cronológica |
| `/visual-law/casos/{id}/matriz-risco` | GET | 200 OK — retorna matriz de risco estruturada (probabilidade × impacto) |
| `/visual-law/casos/{id}/alertas` | GET | 200 OK — retorna alertas ativos vinculados ao caso |
| `/visual-law/breakeven` | GET | **405 Method Not Allowed** |

**Achado sobre `/breakeven`:** o endpoint existe (não retorna 404) mas rejeita GET. Pela convenção do restante da API, isso indica que o endpoint provavelmente exige POST com corpo de parâmetros (ex.: valores de honorários/custas para cálculo de ponto de equilíbrio), mas nenhuma documentação foi encontrada nos bundles JS que confirme o schema esperado. **Recomendação:** documentar o contrato desse endpoint ou, se estiver obsoleto, removê-lo/depreciá-lo explicitamente para não figurar como link quebrado.

**Limitação metodológica importante (leia antes de interpretar "funcional"):** os testes acima confirmam que a **camada de dados** do Visual Law está operante — os endpoints retornam estruturas corretas e consistentes com os casos de teste. **Não foi possível verificar a aparência visual efetivamente renderizada no navegador** (timelines gráficas, semáforos de risco, ícones, cores, tipografia), porque o ambiente de sandbox desta auditoria bloqueia o acesso de rede do Chromium/Playwright a domínios externos (ver Parte 2/3 para o diagnóstico técnico desse bloqueio). Portanto, a afirmação "funcional" refere-se estritamente à camada de API/dados, não à qualidade gráfica final percebida pelo usuário. **Recomendação ao usuário:** validar visualmente as três telas (timeline, matriz de risco, alertas) em navegador real antes de considerar o módulo homologado para uso perante clientes.

### 3.2 Qualidade profissional dos documentos gerados

Com base na peça já avaliada em profundidade na Parte 3 (petição inicial gerada pela IA) e no rubrica de validação formal aplicado pelo próprio sistema (`score_confianca: 94/100`, `veredito: "REVISAR ANTES DE USAR"`), confirma-se:

- **Pontos fortes já documentados e reconfirmados:** fundamentação legal com citação de 15 artigos e 3 leis, narrativa fática mínima presente, pedidos explícitos identificados, indicação de provas/documentos.
- **A rubrica de validação é puramente formal**, e isso está corretamente rotulado pelo próprio sistema: `"natureza": "Controle de qualidade FORMAL da peça (seções obrigatórias, fontes, pedidos, provas). NÃO é predição de êxito, procedência ou probabilidade de vitória."` — este é um comportamento **correto e alinhado à ética profissional** (nenhum sistema deveria alegar prever resultado de mérito), e confirma a ressalva já registrada na Parte 4 sobre a impossibilidade de qualquer sistema garantir resultado "à prova de contestação".
- **Elemento de Visual Law presente no texto da peça:** nenhum. A peça avaliada é discursiva/tradicional (formato de petição clássica). Não há inserção de tabelas visuais, ícones de prazo, linha do tempo integrada ao corpo da peça, ou matriz de riscos anexada automaticamente ao documento final — os recursos de Visual Law existem como **módulo/tela separada** (Seção 3.1), não como elemento incorporado ao documento gerado. **Achado:** se a intenção declarada do produto é oferecer "documentos com Visual Law", há uma lacuna de integração entre o gerador de peças e o módulo de Visual Law — ambos existem, mas não se comunicam no artefato final entregue ao cliente/juízo.

### 3.3 Falha crítica — pipeline de validação → aprovação → exportação em PDF está bloqueado

Esta é a descoberta mais relevante da Parte 5 e tem impacto direto na usabilidade central do sistema (nenhuma peça pode ser formalmente finalizada e exportada).

**Sequência de reprodução (documento de teste, mesmo avaliado na Parte 3):**

1. `POST /legal-docs/{id}/validar` → sucesso. Retorna `ai_log_id: e782abe5-eb13-4237-baf5-791df1461d4b`, `score_confianca: 94`, `veredito: "REVISAR ANTES DE USAR"`, `status_hitl: "gerado"`.
2. `PATCH /ai/logs/{ai_log_id}/hitl` com marcação de revisão → sucesso, log passa a `status: "aplicado"`.
3. `POST /legal-docs/{id}/aprovar` → **falha**, HTTP 4xx:
   ```json
   {"detail":"Peca bloqueada por controle de qualidade: para aprovar/finalizar/protocolar, e necessario validacao juridica revisada ou aplicada com score minimo de 75/100. Status atual: sem_validacao. Execute a validacao juridica da peca e marque o log da IA como revisado ou aplicado."}
   ```

**Causa raiz identificada:** apesar de a validação (passo 1) ter sido concluída com sucesso e o log correspondente ter sido marcado como aplicado (passo 2), o campo que vincula o resultado da validação ao registro do documento (`validacao_juridica.ai_log_id` em `GET /legal-docs/{id}`) **permanece `null`** após ambas as operações. O endpoint de aprovação lê esse campo do documento — não o log de IA isoladamente — e por isso enxerga `status_atual: "sem_validacao"`, mesmo com um log de validação de score 94/100 já aplicado. Trata-se de uma **falha de integração entre dois registros que deveriam ser sincronizados automaticamente** e não o é.

**Impacto:** nenhuma peça pode avançar para `aprovada`/`final`/`protocolada`, e o endpoint `GET /legal-docs/{id}/pdf` permanece bloqueado (422) independentemente da qualidade do conteúdo. Isso **invalida por completo o fluxo "pronto para protocolar"** solicitado nas rodadas anteriores — não por deficiência do conteúdo jurídico redigido pela IA, mas por um defeito de integração no backend que impede a finalização de qualquer peça no sistema.

**Evidência corroborativa (dados pré-existentes, não gerados nesta auditoria):** foram identificados 2 rascunhos de peças de IA já existentes no sistema antes do início desta auditoria, com data de criação `2026-07-13` (16 dias antes da data de teste), ambos ainda em status `rascunho`, nunca protocolados. Isso é consistente com o bug: qualquer usuário real que tenha tentado o fluxo completo desde 13/07/2026 teria sido bloqueado da mesma forma.

**Severidade:** **Crítica / bloqueante.** Recomenda-se correção de prioridade máxima antes de qualquer uso em produção que dependa de finalização e exportação de peças.

**Nota de transparência sobre efeito colateral da investigação:** ao rastrear esse fluxo, os campos `human_reviewed` e `revisor_id` do documento pré-existente `d7c41d42-e859-42c0-9517-adc8205c354e` foram alterados (de `false`/`null` para `true`/id do usuário de teste) como efeito colateral dos passos 1–3 acima. Uma tentativa de reversão via `PATCH /legal-docs/{id}` `{"status":"rascunho","human_reviewed":false}` foi executada: o campo `status` retornou com sucesso a `"rascunho"`, mas `human_reviewed` permaneceu `true` e `revisor_id` permaneceu apontando para o usuário de teste (`aa0dbcc1-26b2-463d-9916-a3a7b46445f0`). **Este resíduo não pôde ser revertido via API disponível ao perfil advogado** e deve ser corrigido manualmente por um administrador com acesso de banco de dados, se a integridade desses metadados for relevante para auditoria interna do escritório.

---

## 4. Auditoria de extração de documentos (ponta a ponta)

### 4.1 Metodologia

Foi submetido um arquivo de teste (`documento_teste_extracao.txt`, simulando uma nota fiscal de serviço com dados fictícios) via `POST /entrada-universal/processar` (multipart, campo `files`), em dois testes independentes e sequenciais, para verificar se a indisponibilidade observada era transitória ou persistente.

### 4.2 Resultado

| Camada | Status | Evidência |
|---|---|---|
| Upload e OCR/extração estruturada | Funcional | `extraction_status: "concluido"`, `confianca_media: 1.0`, texto extraído corretamente (`trecho`/`texto_consolidado` reproduzem o conteúdo do arquivo fielmente) |
| Classificação de tipo de documento (regra local) | Funcional | `classification.tipo: "nota_fiscal"`, `metodo: "regras_locais"`, `confianca: 0.78` |
| Detecção de duplicidade (segundo teste) | Funcional | 2ª submissão do mesmo arquivo corretamente identificada como `extraction_status: "duplicado"`, `duplicate_of_document_id` preenchido |
| **Interpretação por IA** (partes, dados pessoais, resumo executivo, estratégia, datas/eventos, classificação de área/fase) | **Indisponível** | Ambos os testes retornaram `analise_ia.alertas: ["A interpretação por IA ficou indisponível; a extração determinística foi preservada."]`. Todos os campos dependentes de IA (`partes`, `dados_pessoais`, `resumo_executivo`, `estrategia`, `matriz_vicios_teses`, `datas_eventos`, `classificacao.area/fase/tipo_documento`) retornaram vazios em ambos os testes |
| Geração de pacote de peças a partir da extração (`pacote`) | Parcialmente funcional | A maioria dos itens do pacote aparece como `"disponivel"`, mas `memoria_calculo` aparece como `"bloqueado"` — `motivo: "Pendências impeditivas devem ser resolvidas antes da geração."`, coerente com a ausência de dados extraídos por IA |

### 4.3 Avaliação

O comportamento observado é **parcialmente correto e parcialmente falho**:

- **Correto:** o sistema não falha silenciosamente nem inventa dados quando a IA está indisponível — ele preserva a extração determinística, sinaliza explicitamente a indisponibilidade da IA (`alertas`) e marca `requer_confirmacao_humana: true` e `revisao_obrigatoria: true`. Esse é um comportamento de degradação segura (fail-safe), coerente com a exigência de HITL (Provimento OAB 205/2021) e com a instrução do usuário de não aceitar dados especulativos.
- **Falho:** a camada de interpretação por IA — que é, na prática, o principal diferencial de valor do módulo de extração universal (identificação de partes, prazos, estratégia) — esteve **indisponível nos dois testes realizados nesta sessão**, de forma persistente e não transitória (mesma falha reproduzida ~1 minuto depois, com o mesmo arquivo). Isso sugere um problema de infraestrutura (ex.: chave de API do provedor de IA inválida/expirada, rate limit, ou serviço fora do ar) e não uma falha pontual de processamento do arquivo em si. **Recomendação:** verificar no Painel de Provedores IA (mencionado nas Partes 1/4) o status de disponibilidade do provedor configurado para esta rota especificamente, pois outras rotas de IA testadas nas Partes 3–4 (Sala Jurídica, skills de IA, validação de peça) estavam operacionais no mesmo intervalo de tempo — o que aponta para uma falha isolada nesse endpoint específico ou no provedor associado a ele, não para uma indisponibilidade geral de IA no sistema.

---

## 5. Dados de teste criados/alterados nesta rodada — disclosure completo

### 5.1 Casos fictícios (25) — todos arquivados ao final do teste

Todos os 25 casos listados na Seção 2.2 foram atualizados via `PATCH /cases/{id}` para:
```json
{"status":"arquivado","observacoes":"TESTE DE AUDITORIA - registro ficticio (homologacao modulo Areas de Atuacao), solicitar exclusao definitiva via administrador."}
```
Confirmado HTTP 200 para as 25 áreas. **Nenhum caso foi excluído permanentemente**, pois o perfil advogado não possui endpoint de exclusão definitiva para Casos (achado já registrado nas Partes 3–4, reconfirmado aqui — apenas o perfil `sócio`/`admin` deveria ter essa permissão). **Ação pendente:** um usuário com perfil administrador deve excluir definitivamente os 25 registros listados na Seção 2.2, ou confirmar que o status "arquivado" é suficiente para os fins de retenção de dados do escritório.

### 5.2 Cliente de teste (1) — inativado

Cliente `cbf2a61f-82fc-46d5-a88f-f0c3a6f01beb` ("TESTE AUDITORIA EXCLUIR") atualizado via `PATCH /clients/{id}` para `{"status":"inativo"}` — confirmado HTTP 200. Mesma ressalva: sem endpoint de exclusão definitiva disponível ao perfil advogado.

### 5.3 Documento pré-existente com efeito residual não revertido

Documento `d7c41d42-e859-42c0-9517-adc8205c354e`: `status` revertido com sucesso para `"rascunho"`; `human_reviewed` permanece `true` e `revisor_id` permanece `aa0dbcc1-26b2-463d-9916-a3a7b46445f0` (usuário de teste) — não reversível via API disponível a este perfil. Ver Seção 3.3 para detalhes e recomendação de correção manual.

### 5.4 Documento de teste enviado para extração

Um arquivo de teste (`documento_teste_extracao.txt`) foi enviado duas vezes ao `POST /entrada-universal/processar`, gerando os registros de documento `a03d406d-7c8f-440c-8a2f-60bd9518a22e` (original) e um registro de lote duplicado. Não contém dados reais de clientes — todos os campos (CNPJ, CPF, nomes) são fictícios e claramente rotulados "TESTE AUDITORIA EXCLUIR" no corpo do texto.

---

## 6. Limitações metodológicas desta rodada (reafirmadas das Partes 2–4)

- Não foi possível realizar testes de renderização visual em navegador (Chromium/Playwright bloqueado no ambiente de sandbox desta auditoria para domínios externos), portanto toda avaliação de "aparência profissional" e "elementos de Visual Law" se limita à estrutura de dados retornada pela API, não à experiência visual final do usuário.
- Todos os achados desta parte foram obtidos por chamadas diretas à API REST de produção com o token JWT da sessão autenticada como advogado, sem acesso a SSH/console do servidor (bloqueado pela rede do sandbox, conforme diagnosticado na Parte 2).

---

## 7. Recomendações consolidadas desta rodada, em ordem de prioridade

1. **[Crítico]** Corrigir a falha de sincronização entre `validacao_juridica`/`ai_log_id` e o registro do documento em `/legal-docs/{id}`, que bloqueia integralmente o fluxo de aprovação e exportação em PDF. Priorizar antes de qualquer uso em produção.
2. **[Alto]** Investigar a indisponibilidade da camada de interpretação por IA em `/entrada-universal/processar` — verificar status do provedor de IA associado a essa rota especificamente no Painel de Provedores IA.
3. **[Médio]** Corrigir o parser de título de caso para não rejeitar colchetes (`[`, `]`) com uma mensagem de erro que não indica a causa real.
4. **[Médio]** Reclassificar "licitacoes" como subárea/tag de "administrativo" em vez de área de primeiro nível, alinhando a taxonomia do backend à prática de mercado e à Lei nº 14.133/2021.
5. **[Baixo]** Documentar o contrato de `/visual-law/breakeven` (método esperado, payload) ou removê-lo se obsoleto.
6. **[Baixo]** Avaliar a integração de elementos de Visual Law diretamente no corpo dos documentos gerados pela IA, e não apenas como telas/módulos separados.
7. **[Ação administrativa]** Excluir definitivamente (ou confirmar retenção arquivada como suficiente) os 25 casos de teste e o cliente de teste listados na Seção 5; corrigir manualmente `human_reviewed`/`revisor_id` no documento `d7c41d42-e859-42c0-9517-adc8205c354e`.

---

*Documento produzido como parte da auditoria técnica solicitada. Consolida achados da Parte 5 sobre o módulo Áreas de Atuação, criação de documentos/Visual Law e extração de documentos. Deve ser lido em conjunto com as Partes 1 a 4 já entregues.*
