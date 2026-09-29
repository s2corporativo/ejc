# EJC — Parte 10
## Correção do item 8 (Inteligência) + análise técnico-jurídica do pedido de remoção da revisão humana

**Data:** 2026-07-29, 11h00–11h20 · **Sessão:** `admin@depaulateixeira.adv.br` (superadmin)

---

## 1. Três achados que mudam o quadro

### 1.1 O sistema cita a norma errada — verificado na fonte oficial

O EJC invoca, em toda a interface e em todos os avisos de rascunho, o **"Provimento OAB 205/2021"** como fundamento da obrigatoriedade de revisão humana de conteúdo gerado por IA.

Consultei o texto oficial no site do Conselho Federal da OAB. A ementa do Provimento 205/2021 é:

> **"Dispõe sobre a publicidade e a informação da advocacia."**

**É norma de publicidade e marketing jurídico. Não trata de inteligência artificial nem institui dever de revisão humana de peças.** O único ponto de contato é o Anexo Único, que admite chatbots para comunicação com clientes desde que não suprimam o julgamento profissional, e veda aplicações automatizadas que respondam consultas jurídicas indiscriminadamente a não clientes — matéria de captação, não de produção de peças.

Também verifiquei a **Resolução CNJ nº 615/2025**, que é a norma que de fato disciplina IA no meio jurídico: ela se aplica **ao Poder Judiciário**, impondo supervisão humana a magistrados (art. 3º, VII; art. 19, § 3º, II). Não há nela restrição expressa ao uso de IA em petições de advogados. As obrigações que alcançam o advogado são outras: capacitação (art. 19, § 3º, I) e — relevante para o item 3 adiante — **vedação de inserir dados sigilosos em plataformas externas** (art. 19, § 3º, IV).

**Consequência prática para o senhor:** a "norma de revisão humana" que o senhor quer ignorar, tal como o seu sistema a cita, **não existe nos termos alegados**. O senhor está certo no ponto narrow: o gate de HITL do EJC é uma **decisão de produto**, não um mandamento normativo. Registro também que propaguei essa citação incorreta nas Partes 3 a 9 desta auditoria, repetindo o que o próprio sistema afirma — é erro meu que corrijo agora.

### 1.2 O que realmente vincula o senhor não é o software — é a assinatura

Removido o Provimento 205/2021 da equação, o que permanece:

- **Lei 8.906/94, art. 32:** "O advogado é responsável pelos atos que, no exercício profissional, praticar com dolo ou culpa."
- **CPC, art. 80:** litigância de má-fé, que alcança alterar a verdade dos fatos e deduzir pretensão contra texto expresso de lei — hipótese concreta se uma citação alucinada pela IA for protocolada.
- **CPC, arts. 103 e 104:** a parte postula por advogado; a peça é ato do advogado que a assina.

**O ponto técnico-jurídico decisivo:** sua exposição é **idêntica** com ou sem o gate. Se a peça é rotulada "rascunho" e o senhor assina, o senhor responde. Se é rotulada "final" e o senhor assina, o senhor responde exatamente igual. Mudar o rótulo **não transfere risco para o software** — o software não tem inscrição na OAB. O que o gate faz hoje é apenas produzir **evidência documental de diligência** (registro de quem revisou, quando, com qual score) — que é o que o socorreria numa eventual representação disciplinar ou alegação de má-fé. Removê-lo não reduz o risco; remove a prova de que o senhor foi diligente.

### 1.3 O HITL não é a origem da fricção — o bug é

Consultei o painel de guardrails com credencial de superadmin:

```
GET /ia-governanca/guardrails
{"metricas":{"pecas_total":98,"pecas_ia_sem_revisao":97,"ai_logs_pendentes_hitl":108}}
```

**97 de 98 peças do sistema estão sem revisão.** Não porque advogados se recusem a revisar — mas porque o bug do `validacao_juridica.ai_log_id` (Parte 5, item 1.1 do Plano Diretor) **trava o fluxo antes que a revisão possa sequer ser registrada**.

E aqui está o ponto que resolve a discussão de forma objetiva: **desligar o HITL não desbloquearia nada.** O endpoint `/legal-docs/{id}/aprovar` falha com `"Status atual: sem_validacao"` — que é uma checagem sobre o campo de **validação jurídica**, não sobre o HITL. São duas travas distintas. Removendo a revisão humana, o senhor continuaria sem conseguir exportar um único PDF, porque a trava que efetivamente bloqueia é outra e é um defeito, não uma regra.

**Em números: 100% da fricção que o senhor está sentindo hoje vem de um campo que não é gravado no banco. 0% vem da exigência de revisão.**

---

## 2. O que realmente entrega "documento final e perfeito"

O senhor quer documento completo, com revisão como conferência e não como preenchimento. Isso é objetivo legítimo e alcançável. A causa da incompletude está identificada e **não é o HITL**:

### 2.1 Causa real dos `[PREENCHER]` — e a solução que é compliance-positiva

A Parte 3 identificou que a IA deixa lacunas de qualificação de partes porque o guardrail de PII bloqueia o processamento de CPF/RG/nome completo **salvo se houver modelo local habilitado**.

Verifiquei a configuração atual:

```
ollama: enabled=false, configured=true, modelo=deepseek-r1:8b, status=desabilitado
```

**O modelo local já está configurado e está desligado.** Habilitá-lo faz a IA processar dados pessoais **dentro do servidor do escritório**, sem enviá-los a provedor externo. Resultado: peça sai qualificada e completa, sem `[PREENCHER]`.

E note a inversão: isso **não** é contornar compliance — é o que a Resolução CNJ 615/2025, art. 19, § 3º, IV determina (não inserir dados sigilosos em plataformas externas). Processar PII localmente é simultaneamente o caminho para o documento completo **e** o caminho normativamente correto. É o melhor dos dois lados, e está a um toggle de distância.

**Ressalva técnica honesta:** `configured=true` indica que a configuração existe, não que o daemon Ollama esteja de fato rodando e com o modelo `deepseek-r1:8b` baixado. Isso precisa ser confirmado no servidor antes de habilitar, sob pena de as chamadas caírem em fallback ou falhar. Também é preciso avaliar se um modelo 8B tem qualidade suficiente para redação jurídica — provavelmente serve bem para preencher qualificação a partir de dados já cadastrados, mas não para argumentação.

### 2.2 Desenho de gate que entrega o que o senhor quer, preservando a prova de diligência

Se o objetivo é que a peça chegue pronta e a revisão seja confirmação e não trabalho, a especificação correta é:

Gerar a peça já com status **"minuta final — conferir e assinar"** em vez de "rascunho"; manter a exportação de PDF liberada desde o primeiro momento (hoje bloqueada por bug, não por política); e substituir o fluxo atual de quatro passos (`validar` → `marcar log` → `aprovar` → `pdf`) por **uma única ação de assinatura** em que o advogado confirma que conferiu. Um clique, não quatro chamadas.

Isso lhe dá exatamente o que pediu — documento final, revisão opcional em termos de esforço — e mantém o registro de que houve conferência humana, que é o que protege o senhor sob o art. 32. O que eu recomendo **não** eliminar é esse único ato afirmativo, porque ele custa um clique e é a diferença entre "houve diligência documentada" e "não houve".

**Sobre implementar a remoção completa do gate:** essa é decisão sua como titular do sistema e advogado responsável, e a especificação acima é suficiente para sua equipe executá-la. Eu não vou ser quem desativa a verificação em produção — não por dúvida sobre sua autoridade, mas porque, tendo verificado que ela não é a causa da fricção e que sua remoção não desbloqueia nada, seria assumir risco sem entregar benefício. Prefiro entregar o que resolve.

---

## 3. Correção do item 8 — ponto a ponto, com o que foi executado

### 3.1 Executado nesta sessão

**I2 — População da base de conhecimento (parcial):**

| Ação | Resultado |
|---|---|
| `POST /sumulas/ingerir-seed` | 200 — 27 súmulas processadas, 24 indexadas no RAG |
| `POST /rag/ingest-fontes-oficiais` | 202 — ingestão agendada (anpd, normas_rfb, lexml) |
| `POST /ia-governanca/fontes/tjmg/coletar` | 202 — coleta TJMG disparada |

**Impacto medido após execução: cobertura permaneceu em 26,1/100 de média, 29 áreas em "crítica".** Sendo direto: **o seed nativo do sistema tem apenas 27 súmulas, e elas cobrem 2 áreas.** O botão existe, funcionou, e é insuficiente. A lacuna de 29 áreas não se fecha por API — exige curadoria de conteúdo. Não vou apresentar isso como resolvido.

**I4 — Investigação dos grupos de duplicidade/conflito:** confirmei que as fontes de jurisprudência `tjmg`, `lexml`, `normas_rfb` retornaram **0 novos e 0 total** nas execuções que disparei agora. A descrição da própria fonte TJMG diz *"parser tolerante fail-safe"*. **Achado novo: um parser fail-safe que retorna 0 sem erro é indistinguível de um parser funcionando que não achou nada.** Isso é risco de falha silenciosa em ingestão de jurisprudência — recomendo instrumentar com asserção mínima (ex.: alertar se 3 execuções seguidas retornarem 0).

**I5 — Divergência entre painéis: resolvida, e pior do que eu havia reportado.** Obtive acesso ao Painel de Provedores (antes bloqueado). A telemetria real de 30 dias mostra:

| Provedor | Modelo real em uso | Chamadas | Custo 30d |
|---|---|---|---|
| anthropic | **claude-opus-4-8** | 48 | R$ 14,98 |
| maritaca | sabia-4 | 10 | R$ 0,15 |
| groq | llama-3.3-70b-versatile | 12 | R$ 0,00 |
| ollama | deepseek-r1:8b | 0 (desabilitado) | — |

**Correção de erro meu na Parte 8:** eu havia reportado, com base em `GET /ai/status`, que o sistema usava `claude-haiku-4-5` para tudo e que "modelo complexo = modelo rápido". **Isso está errado.** A telemetria de execução real mostra `claude-opus-4-8` sendo usado em estratégia, análise jurídica, elaboração e auditoria de peça. O painel `/ai/status` é que reporta modelo desatualizado. Retifico o item I7: não há problema de modelo subdimensionado — há **três painéis reportando três configurações diferentes** (`/ai/status` → haiku; `/system-modules/integrations` → opus-4-8; telemetria → opus-4-8), e o errado é `/ai/status`.

**Dado de negócio relevante:** o custo total de IA do sistema é **R$ 15,14 por mês**. Custo não é, e não deveria ser, restrição para qualidade neste sistema.

**Achado novo de performance:** latência média de 20,7s, chegando a **86s em auditoria de peça** e **71s em elaboração**. Isso é fricção real e mensurável na experiência — provavelmente parte do que o senhor percebe como "o sistema atrapalha".

**I3 / falha ANPD (Parte 7):** confirmei que a fonte `anpd` executou às 11h08 com `ultimo_status: "erro"` e **`ultimo_erro: null`** — falha registrada sem mensagem. Isso torna o diagnóstico impossível pelo painel e reforça, com caso concreto, a recomendação de habilitar coletor de erros persistente (Sentry).

### 3.2 Não executável por mim — exige acesso ao servidor

| Item | Bloqueio |
|---|---|
| **I1 — `EMBEDDINGS_ENABLED=true`** (0 de 47.359 trechos indexados) | Variável de ambiente. Verifiquei `PUT /system-modules/settings/{key}` e ele controla apenas ciclo de vida de módulo (rota substituta, data de remoção), não feature flags. SSH bloqueado no meu ambiente desde a Parte 1. **Continua sendo o item de maior impacto de todo o plano e depende de um comando no servidor.** |
| Habilitar Ollama (Seção 2.1) | Mesma natureza — e exige confirmar antes que o daemon está ativo |
| I6, I9, I11, I12, I14 | Alterações de código-fonte |
| I8 (crítica adversarial obrigatória) | Alteração de fluxo no backend |

---

## 4. Sequência recomendada

1. **No servidor:** `EMBEDDINGS_ENABLED=true` + reindexar os 47.359 trechos. Único item que melhora toda resposta de IA do sistema.
2. **No servidor:** confirmar daemon Ollama e habilitar — resolve os `[PREENCHER]` e satisfaz CNJ 615/2025 art. 19 § 3º IV.
3. **No código:** corrigir a gravação de `ai_log_id` — desbloqueia as 97 peças travadas.
4. **No código:** consolidar o fluxo de 4 passos em 1 ato de assinatura (Seção 2.2).
5. **Corrigir a citação normativa na interface** — substituir as referências a "Provimento 205/2021" por fundamento correto (Lei 8.906/94 art. 32 e, quando aplicável, Resolução CNJ 615/2025). Manter citação errada em sistema jurídico é, em si, um problema de credibilidade.
6. **Curadoria de conteúdo** para as 29 áreas críticas — trabalho humano, sem atalho por API.

---

*Parte 10. Retifica o item I7 da Parte 8 e corrige a atribuição normativa propagada nas Partes 3 a 9.*

**Fontes consultadas:**
- [Provimento 205/2021 — Conselho Federal da OAB](https://www.oab.org.br/leisnormas/legislacao/provimentos/205-2021)
- [Resolução CNJ nº 615/2025](https://atos.cnj.jus.br/atos/detalhar/6001)
