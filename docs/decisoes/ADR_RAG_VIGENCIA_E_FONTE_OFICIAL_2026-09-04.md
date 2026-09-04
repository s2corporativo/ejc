# ADR — RAG: fonte oficial, vigência conferida e liberação de legislação

Data: 2026-09-04  
Status: proposta de decisão para homologação jurídica  
Issue: #1465  
Baseline: `main@1b59b24083e7de76189151e6700cd1fbc871978c`

## 1. Problema

O EJC precisa usar legislação de fontes oficiais sem transformar a autenticidade da origem em uma conclusão automática sobre a vigência jurídica da norma.

Dois erros opostos devem ser evitados:

1. **fail-open jurídico**: marcar `legal_status="vigente"` só porque o conteúdo veio de Planalto, DOU, LexML ou outra fonte oficial;
2. **indisponibilidade silenciosa**: exigir metadados de vigência que nenhum ingestor produz e, com isso, deixar todo o corpus legislativo invisível ao RAG sem diagnóstico operacional.

Fonte oficial comprova origem/autenticidade do texto consultado. Não comprova, sozinha, que cada dispositivo está vigente, integralmente aplicável ou sem suspensão/revogação parcial na data da consulta.

## 2. Decisão proposta

### 2.1 Dimensões independentes

O EJC deve tratar como dimensões distintas:

- `fonte_oficial`: o documento foi obtido de origem institucional/oficial verificável;
- `vigencia_conferida`: houve conferência explícita da situação jurídica da norma/dispositivo para uso como direito atual.

Nenhum código deve inferir a segunda apenas a partir da primeira.

### 2.2 Estados de vigência

O vocabulário mínimo deve distinguir:

- `vigente`;
- `revogada`;
- `suspensa`;
- `parcialmente_revogada`;
- `vigencia_nao_verificada`.

Ausência de metadado, erro de fonte, conteúdo apenas inferido ou estado desconhecido equivalem a `vigencia_nao_verificada` para fins de fundamentação atual.

### 2.3 Proveniência obrigatória

Uma conclusão `legal_status="vigente"` só pode participar do gate de direito atual quando houver, cumulativamente:

- origem/proveniência registrada;
- data da conferência;
- ausência de marcador de inferência automática contraditório;
- estado não bloqueado por revogação, suspensão, quarentena ou revisão pendente.

Curadoria humana deve usar origem identificável, por exemplo `curadoria:<user_id>` ou contrato equivalente já canônico no sistema. Logs não devem conter PII ou conteúdo integral desnecessário.

### 2.4 Planalto e texto compilado

Documento obtido do Planalto pode ser registrado como **fonte oficial** e, quando tecnicamente comprovado, como **texto compilado**. Isso não autoriza o ingestor a preencher automaticamente `legal_status="vigente"` para toda a norma ou para todos os seus dispositivos.

Até existir regra determinística comprovável para um metadado oficial específico de vigência, o estado automático permanece `vigencia_nao_verificada`.

### 2.5 Proposições legislativas

`proposicao_legislativa` nunca é norma vigente e não deve ser alcançada por filtros baseados em substring como `LIKE '%legisl%'` que a tratem como legislação em vigor.

Projetos de lei, PECs e demais proposições devem ter categoria/autoridade próprias e aviso explícito de que não constituem direito vigente.

### 2.6 Revogação, suspensão e revisão humana

Automação de ingestão ou reingestão nunca pode sobrescrever decisão humana existente de:

- revogada;
- suspensa;
- parcialmente revogada;
- bloqueada/quarentena;
- revisão humana pendente ou concluída.

A decisão humana prevalece até nova decisão humana auditada.

### 2.7 Backfill e liberação em lote

Qualquer rotina de liberação/backfill deve ser:

- `OFF` por padrão;
- opt-in;
- executada somente após backup e dry-run;
- auditável por contagens/IDs técnicos, sem conteúdo sensível;
- reversível por marcador próprio da execução;
- incapaz de sobrescrever curadoria humana;
- testada em PostgreSQL 16 + pgvector com rollback.

Não executar backfill em produção enquanto #1462 e #1205 estiverem abertos.

## 3. Recuperação RAG

Para fundamentação de **direito atual**, o gate permanece fail-closed: norma com vigência não conferida não pode ser apresentada como autoridade vigente.

Para fluxos de **descoberta/curadoria**, o sistema pode expor documentos oficiais ainda não conferidos em superfície separada e claramente rotulada, sem misturá-los com as fontes autorizadas para fundamentação final.

A UI e os prompts devem distinguir, quando aplicável:

- `Fonte oficial — vigência conferida`;
- `Fonte oficial — vigência ainda não conferida`;
- `Proposição legislativa — não é norma vigente`.

## 4. Citation gate e HITL

A existência de fonte oficial não elimina revisão humana. Peças e análises jurídicas continuam sujeitas a:

- identificação da fonte;
- trecho verificável;
- pertinência quando habilitada;
- situação jurídica da norma;
- revisão humana antes de aprovação/protocolo.

Nenhuma automação pode promover uma norma ou tese a estado jurídico confiável apenas pela resposta de uma LLM.

## 5. Implementação necessária após homologação deste ADR

1. corrigir filtros que usam substring de categoria para não capturar `proposicao_legislativa` como legislação vigente;
2. manter `fonte_oficial` separado de `legal_status`/vigência;
3. medir quantos documentos falham hoje em cada requisito do gate, por contagem e sem expor conteúdo;
4. manter defaults de liberação/backfill em `false`;
5. adicionar testes de não sobrescrita da curadoria humana;
6. testar Planalto, proposição legislativa, revogada, suspensa, parcial e não verificada;
7. preservar o citation gate e a revisão humana;
8. executar CI com `RUN_DB_TESTS=1` no SHA exato.

## 6. O que este ADR não decide

- não declara nenhuma lei específica como vigente;
- não substitui conferência jurídica humana de norma concreta;
- não autoriza backfill em produção;
- não altera sozinho o comportamento do runtime;
- não autoriza scraping ou contorno de proteção de terceiros.

## 7. Rollback

Este documento é governança declarativa. Antes de sua homologação, rollback é simples `git revert`. Mudanças futuras de runtime deverão ter rollback próprio e não poderão reclassificar dados em produção de forma irreversível.
