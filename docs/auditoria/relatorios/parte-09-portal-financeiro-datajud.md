# EJC — Auditoria Técnica, Parte 9
## Portal do Cliente, Financeiro/Honorários/Sociedade e DataJud/Intimações

**Sistema:** Ecossistema Jurídico Clovis (EJC) — `https://ejc.depaulateixeira.adv.br`
**Sessão autenticada:** `admin@depaulateixeira.adv.br` (superadmin) + tokens advogado previamente obtidos
**Data/hora do teste:** 2026-07-29, 10h50–11h20
**Escopo:** os três conjuntos de módulos priorizados por você após a Parte 8 — Portal do Cliente, Financeiro/Honorários/Sociedade, DataJud/Intimações — nenhum deles auditado em profundidade nas Partes 1–8.

---

## 1. Resumo executivo

| Achado | Severidade |
|---|---|
| **Métrica de "chance de êxito" (probabilidade de sucesso da causa) confirmada no código-fonte e em uso ativo em produção**, exibida com destaque visual (percentual grande, barra colorida verde/amarelo/vermelho) na tela de detalhe do caso e na Entrevista Inteligente | **Crítica — questão de conformidade ética (OAB)** |
| Portal do Cliente permanece **integralmente não testável** por mim — criação de credencial de teste foi bloqueada pelo classificador de segurança do ambiente desta auditoria | Bloqueio metodológico, não achado sobre o EJC |
| RBAC do Portal corretamente aplicado — nem token advogado nem superadmin conseguem acessar rotas exclusivas do cliente | Positivo |
| Cadastro de "sócios" do módulo Sociedade está **vazio** (`total_participacao: 0`, `socios: []`) — distribuição de lucro não tem dado para operar | Alta |
| Tabela oficial de honorários OAB/MG **não carregada na base** — verificação de piso ético de honorários indisponível | Alta |
| 3 rotas listadas no Mapa de Módulos oficial (`/v1/despesas`, `/v1/office-contracts`, `/v1/partner-withdrawals`) **não resolvem em produção** (404 mesmo autenticado) | Média |
| Módulo financeiro (`fees`, `financeiro/consolidado`) funcional mas **sem nenhum dado real** (tudo zerado) | Informativo (maturidade, não bug) |
| Captura de intimações (DJEN) executando com sucesso, 0 encontradas no momento — sem forma independente de confirmar se é o resultado correto | Informativo |

O achado desta rodada com maior relevância prática é a confirmação, por leitura direta do código-fonte do frontend, de que o EJC calcula e exibe visualmente uma **"chance de êxito"** (percentual de probabilidade de sucesso da causa) tanto na ficha do caso quanto na Entrevista Inteligente de triagem — e que essa linguagem já aparece em registros reais de triagem automática no sistema em produção. Isso precisa de revisão de conformidade imediata, independentemente do restante deste relatório.

---

## 2. Achado crítico — "Chance de êxito" exibida ao usuário interno

### 2.1 Evidência no código-fonte

```
CasoDetalhe-CWyLfvJU.js:
  {n.jurimetria.chance_sucesso_percent ?? "—"}%
  style:{width:`${n.jurimetria.chance_sucesso_percent ?? 0}%`}   // barra de progresso

EntrevistaInteligente-DX4iaR7n.js:
  label: "Chance de êxito (estimativa interna)"
  confianca: Z.chance_exito.confianca
  tone: Z.chance_exito.percentual >= 70 ? "green" : Z.chance_exito.percentual >= 40 ? ... 
  "{Z.chance_exito.percentual}% de êxito estimado"
  Z.chance_exito.justificativa
```

A tela de detalhe do caso (`CasoDetalhe`, usada por qualquer advogado) renderiza um número percentual em destaque (fonte grande, negrito) e uma barra de progresso preenchida proporcionalmente ao campo `jurimetria.chance_sucesso_percent` do caso. A Entrevista Inteligente (módulo de triagem inicial por relato livre) exibe um cartão rotulado **"Chance de êxito (estimativa interna)"**, com código de cor (verde ≥70%, cores mais baixas abaixo disso), percentual e uma justificativa textual.

### 2.2 Evidência de uso real em produção

O log de movimentações recentes (`GET /movimentos/recentes`) — consultado nesta rodada como parte da auditoria de DataJud — mostra **8 de 15 registros recentes** contendo esse padrão, gerados por "IA – Triagem automática":

```
área≈consumidor · assunto=Negativação indevida após quitação do débito · chance≈82% · complexidade=baixa. RASCUNHO — revisão por advogado (OAB).
área≈civil · assunto=Caso fictício de homologação — sem fatos concretos informados · chance≈0% · complexidade=baixa. RASCUNHO — revisão por advogado (OAB).
área≈consumidor · assunto=Vício oculto em veículo adquirido de concessionária · chance≈60% · complexidade=media. RASCUNHO — revisão por advogado (OAB).
```

O fato de a "chance" cair para 0% exatamente no caso descrito como "sem fatos concretos informados" é consistente com um cálculo real (não um valor fixo/decorativo), reforçando que este é um número efetivamente computado pela IA a partir do relato do caso — não apenas um rótulo estático.

**Ao consultar diretamente, via API, o registro completo de um dos casos citados no log (`GET /cases/{id}`), o campo `jurimetria` retornou `null`** — ou seja, embora o valor tenha sido gerado e registrado no log de movimentações, ele não está (ou não estava, no momento da consulta) persistido no objeto do caso da forma que o componente `CasoDetalhe` espera ler (`caso.jurimetria.chance_sucesso_percent`). **Não sei precisar, sem acesso ao código-fonte do backend, se isso é (a) um problema de sincronização/persistência, (b) um campo calculado sob demanda e não salvo, ou (c) um caso em que o cálculo específico não chegou a rodar** — sinalizo a divergência com transparência, sem concluir a causa.

### 2.3 Por que isso é uma questão de conformidade, não apenas de produto

O Código de Ética e Disciplina da OAB veda, no art. 6º, parágrafo único, e no art. 34, XXIX, a captação de causa mediante promessa de resultado. O rótulo **"estimativa interna"** usado na Entrevista Inteligente é uma mitigação correta e bem-vinda — mas:

1. **O rótulo na tela de Caso (`CasoDetalhe`) não inclui, no trecho de código inspecionado, a mesma qualificação "estimativa interna"** — aparece apenas como percentual e barra de progresso, sem o texto de contexto presente na Entrevista Inteligente. Isso pode fazer diferença relevante em uma eventual auditoria de compliance ou em uma reclamação de cliente que veja a tela por cima do ombro do advogado.
2. **Não consegui verificar (Portal bloqueado, Seção 3) se este número, ou qualquer variante dele, chega a ser exibido ao cliente final no Portal.** Se `portal/casos/{id}` ou `portal/financeiro` expuserem, direta ou indiretamente, qualquer versão desse percentual ao cliente, isso constituiria uma promessa de resultado na acepção mais literal do termo — o tipo de achado que só uma auditoria com credencial real de portal pode confirmar ou descartar. **Esta é agora a razão mais concreta e urgente para priorizar o acesso ao Portal do Cliente** (Seção 3).
3. O uso interno (só para advogados, nunca visto pelo cliente) de uma estimativa estatística para apoiar decisão profissional é prática legítima e comum — o risco está inteiramente na exposição e no enquadramento, não na existência do cálculo em si.

**Recomendação de prioridade máxima:** (a) confirmar com a equipe técnica exatamente onde `chance_sucesso_percent`/`chance_exito` é calculado, salvo e exibido; (b) garantir que a qualificação "estimativa interna, sujeita a revisão humana, não constitui promessa de resultado" apareça em **toda** tela que mostre esse número, incluindo `CasoDetalhe`; (c) confirmar categoricamente que esse dado **nunca** é exposto no Portal do Cliente; (d) caso já esteja, removê-lo do payload de qualquer endpoint `/portal/*` imediatamente.

---

## 3. Portal do Cliente — auditoria parcial (bloqueio metodológico)

### 3.1 O que não pôde ser testado

Tentei criar uma conta de teste com perfil `cliente_externo` (`POST /users/`, rotulada `TESTE AUDITORIA EXCLUIR`) para acessar o Portal como um cliente real acessaria. **Essa ação foi bloqueada pelo classificador de segurança do ambiente desta sessão de auditoria** (criação de credencial/conta é tratada como ação sensível). Não tentei contornar o bloqueio. A conta fictícia de homologação já identificada na Parte 7 (`homolog.portal...@depaulateixeira.adv.br`) existe, mas não tenho sua senha.

**Consequência prática:** as 9 rotas do módulo `portal` (`/portal/meus-casos`, `/portal/casos/{id}`, `/portal/casos/{id}/mensagens`, `/portal/documentos`, `/portal/financeiro`, `/portal/solicitacoes-documentos`, `/portal/mensagens/nao-lidas`) permanecem **funcionalmente não verificadas de ponta a ponta** — nem por mim, nem, até onde a auditoria conseguiu apurar, por ninguém de forma documentada.

### 3.2 O que pôde ser confirmado sem login de portal

**RBAC corretamente aplicado (achado positivo):** testei acesso a `GET /portal/meus-casos` com token de advogado e com token superadmin — ambos retornaram `403 {"detail":"Acesso exclusivo do Portal do Cliente"}`. **Nem mesmo o superadmin consegue navegar pelas telas do portal com sua própria credencial** — isso é uma boa prática de segurança (impede um operador interno de "se passar" por um cliente), mas tem como efeito colateral que a própria equipe do escritório não tem como pré-visualizar a experiência do cliente sem uma conta de portal dedicada.

**Análise estática dos 7 bundles de frontend do Portal** (`PortalDashboard`, `PortalCasos`, `PortalCasoDetalhe`, `PortalDocumentos`, `PortalFinanceiro`, `PortalMensagens`, `PortalAssinaturas`): nenhum dos 7 arquivos contém qualquer atributo `aria-*` — 0 de 7, reforçando com um dado ainda mais específico o achado de acessibilidade da Parte 6 (65% dos módulos gerais sem cobertura), agora confirmando que a **superfície voltada ao cliente final está entre as menos cobertas**, o que é particularmente relevante dado que clientes externos têm perfil de acessibilidade mais heterogêneo do que a equipe interna do escritório.

### 3.3 Recomendação

Este é, na minha avaliação, o item de maior prioridade prática deixado em aberto por toda a auditoria: **peço que você (ou alguém com perfil sócio/admin) crie uma conta de portal de teste diretamente pelo sistema, ou me informe a senha da conta `homolog.portal...` já existente**, para que eu possa concluir esta parte. Sem isso, o Portal do Cliente — a única superfície do EJC vista diretamente pelos clientes do escritório — permanece o único módulo do sistema inteiramente sem auditoria funcional.

---

## 4. Financeiro / Honorários / Sociedade

### 4.1 O que funciona, sem dados

| Endpoint | Resultado |
|---|---|
| `GET /fees/resumo` | `{"pendente":0.0,"atrasado":0.0,"recebido_mes":0.0}` |
| `GET /financeiro/consolidado` | Estrutura completa (receitas por tipo — contratual/êxito/sucumbência/custas —, despesas fixas/variáveis), **tudo zerado** |
| `GET /sociedade/distribuicao` | `{"total":0,"items":[]}` |
| `GET /honorarios-oab/itens` | `{"total":0,"itens":[]}` |

**Avaliação:** as APIs respondem corretamente e com estrutura de dados coerente — não há erro técnico. O que existe é ausência total de dados reais lançados no sistema (nenhum honorário, nenhuma despesa, nenhuma distribuição de sócio registrada). Isso é esperado para um sistema em fase de adoção, mas significa que **o módulo financeiro do EJC ainda não está, na prática, sendo usado para gestão financeira real do escritório** — o que é uma informação de negócio relevante, além de técnica.

### 4.2 Achado — cadastro de sócios vazio impede a distribuição de lucro

`GET /sociedade/socios` retornou `{"total_participacao": 0, "socios": []}`. Isso significa que, mesmo que houvesse receita lançada, o módulo de distribuição societária **não teria como calcular a divisão** entre os sócios reais do escritório (2 identificados no cadastro de usuários da Parte 7: Guilherme Alves de Paula e — a depender da estrutura societária real — outros). **Recomendação:** cadastrar os sócios e seus percentuais de participação em `/sociedade/socios` antes de tentar usar `/sociedade/distribuicao` para qualquer cálculo real.

### 4.3 Achado — tabela oficial de honorários OAB/MG não carregada

`GET /honorarios-oab/tabela` retornou:
```json
{"disponivel": false, "itens": "Tabela oficial OAB/MG não disponível na base."}
```

O módulo de honorários tem endpoints dedicados a comparar propostas com o "teto ético" (`/honorarios-calc/cases/{id}/teto-etico`) e estimar valores (`/honorarios-oab/estimar`), mas a fonte de referência — a tabela oficial de honorários mínimos da OAB/MG — **não está carregada no sistema**. Isso significa que, hoje, qualquer verificação automática de piso ético de honorários (relevante para o art. 48 e correlatos do Código de Ética da OAB, que trata de aviltamento de honorários) **não tem base de comparação real**. **Recomendação de prioridade alta:** carregar a tabela oficial vigente da OAB/MG antes de usar qualquer funcionalidade de sugestão/validação de honorários para decisão real.

### 4.4 Achado — 3 rotas do Mapa de Módulos não resolvem em produção

| Rota (conforme Mapa de Módulos oficial) | Resultado |
|---|---|
| `GET /api/v1/despesas` | 404, mesmo autenticado como superadmin |
| `GET /api/v1/office-contracts` | 404, mesmo autenticado como superadmin |
| `GET /api/v1/partner-withdrawals` | 404, mesmo autenticado como superadmin |

Testei múltiplas variações de caminho (com/sem barra final, prefixos alternativos) sem sucesso. Confirmei que o padrão de resposta do sistema é: sem token → sempre `401` (mesmo para rotas inexistentes, pois a checagem de autenticação roda antes do roteamento); com token válido → `404` apenas para rotas que de fato não existem (confirmado com uma rota deliberadamente inventada). Ou seja, **estas 3 rotas — listadas como existentes pelo próprio Mapa de Módulos oficial do EJC — não respondem como endpoints reais hoje**, seja porque foram descontinuadas após a última varredura do Mapa de Módulos, seja porque estão montadas em um prefixo diferente do detectado. **Recomendação:** verificar diretamente no código-fonte do backend se essas 3 rotas (despesas avulsas, contratos de escritório, retiradas de sócio) ainda existem e, se sim, corrigir o prefixo de montagem; se não, atualizar o Mapa de Módulos para não listá-las como ativas — o próprio Mapa de Módulos, recomendado nas Partes 6/7 como fonte de maior confiança, tem aqui uma imprecisão confirmada.

---

## 5. DataJud e Intimações

### 5.1 Captura de intimações — funcionando, sem dado para validar resultado

```json
GET /intimacoes/status-captura
{"executado_em":"2026-07-29T06:30:01...","sucesso":true,"intimacoes_encontradas":0,"defasado":false}
```

A captura automática está executando com sucesso técnico (sem erro) e de forma recente (não defasada). Retornou 0 intimações encontradas no momento da consulta. **Não tenho forma independente de confirmar se "0" é o resultado correto** (ou seja, se realmente não há novas intimações pendentes no DJEN para a(s) OAB(s) monitorada(s)) ou se há uma falha silenciosa de captura — isso exigiria comparação com o portal oficial do DJEN/CNJ, fora do escopo desta auditoria técnica. **Recomendação:** validar periodicamente, por amostragem manual no site do DJEN, se o número de intimações capturadas pelo EJC bate com a realidade — é o único jeito de detectar uma falha silenciosa nesse tipo de integração.

### 5.2 Movimentações recentes — funcionando bem, gerando o achado da Seção 2

`GET /movimentos/recentes` funciona corretamente e devolve um feed cronológico útil, combinando notas manuais e eventos de IA — foi essa mesma fonte que revelou o achado crítico da Seção 2.

### 5.3 Consulta processual DataJud

`GET /v1/datajud/process/{numero_cnj}` com um número de processo formatado mas inexistente retornou `404`. Dado que os demais endpoints do módulo DataJud responderam normalmente, a leitura mais provável é que se trata de um "processo não encontrado" legítimo (o número usado foi deliberadamente fictício), não uma rota quebrada — mas, ao contrário da Seção 4.4, **não tive como testar com um número de processo real sem usar dados de caso genuíno**, então não posso confirmar com o mesmo grau de certeza que a funcionalidade está 100% operante ponta a ponta.

### 5.4 Palavras-chave de monitoramento do Diário Oficial

`GET /diario-oficial/keywords` retornou uma lista funcional de palavras-chave monitoradas (ambiental, bancario, juros, trabalhista, entre outras) — mecanismo de alerta temático funcionando como esperado, coerente com os achados de alto volume de alertas já documentados nas Partes 3 e 8.

---

## 6. Plano de correção desta rodada

| # | Ação | Prioridade | Esforço |
|---|---|---|---|
| P1 | Confirmar onde e como `chance_sucesso_percent`/`chance_exito` é calculado e persistido; garantir texto de ressalva ("estimativa interna, sujeita a revisão humana") em toda tela que o exiba, incluindo `CasoDetalhe` | **Crítica** | Baixo–Médio |
| P2 | Confirmar categoricamente que nenhuma variante de "chance de êxito" é exposta no Portal do Cliente; remover imediatamente se estiver | **Crítica** | Depende de P3 para confirmar |
| P3 | Viabilizar acesso de teste ao Portal do Cliente (nova conta ou senha da conta de homologação existente) para concluir a auditoria desta superfície | Alta | Depende de você |
| P4 | Cadastrar sócios e percentuais de participação em `/sociedade/socios` antes de operar `/sociedade/distribuicao` | Alta | Baixo (cadastro) |
| P5 | Carregar a tabela oficial de honorários OAB/MG antes de usar funcionalidades de sugestão/validação de honorários para decisão real | Alta | Baixo–Médio (obtenção da fonte oficial) |
| P6 | Verificar e corrigir (ou depreciar) as 3 rotas do Mapa de Módulos que não resolvem em produção (`despesas`, `office-contracts`, `partner-withdrawals`) | Média | Baixo (investigação) + depende da causa |
| P7 | Adicionar cobertura de acessibilidade (`aria-*`) aos 7 bundles do Portal — hoje 0 de 7, a superfície mais exposta a usuários externos heterogêneos | Média | Médio |
| P8 | Validar periodicamente, por amostragem manual no DJEN, se a captura de intimações (`0 encontradas` no momento do teste) reflete a realidade | Média | Baixo (processo recorrente) |

---

## 7. Nota metodológica

Os achados sobre Financeiro/Honorários/Sociedade e DataJud/Intimações foram obtidos por chamadas diretas à API de produção com token superadmin. O achado da Seção 2 ("chance de êxito") combina evidência de código-fonte (bundles de frontend não ofuscados) com evidência de uso real em produção (log de movimentações), mas **não pôde ser confirmado até a camada de exibição ao cliente**, por não ter sido possível obter acesso ao Portal — essa é a lacuna mais importante deixada nesta rodada e a principal recomendação de próximo passo. Nenhum dado de cliente real foi alterado nesta rodada; a única ação de escrita tentada (criação de conta de teste do Portal) foi bloqueada pelo ambiente antes de ser executada.

---

*Documento produzido como Parte 9 da auditoria técnica do EJC. Deve ser lido em conjunto com as Partes 1 a 8 e com o Plano Diretor. O achado da Seção 2 justifica a inclusão de um novo item de prioridade crítica no Plano Diretor, à frente inclusive de itens já classificados como críticos.*
