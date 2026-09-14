# EJC Legal Brain — Arquitetura canônica

## Objetivo

Evoluir o núcleo jurídico existente sem criar um segundo gateway, segundo RAG,
segunda memória de caso ou novo cadastro paralelo de teses/fontes.

A fonte de execução de IA continua sendo `SingleAICoreOrchestrator` e o catálogo
nativo continua em `app/services/ai/core/ejc_skill_catalog.py`.

## Invariantes

1. Fato documentado, alegação, controvérsia, inferência de IA e validação humana
   são estados distintos.
2. Skill referencia fonte, precedente e tese por identidade/proveniência; não
   copia silenciosamente o Direito para dentro do prompt.
3. Ausência de evidência gera lacuna, nunca conclusão.
4. Fonte oficial não equivale automaticamente a vigência conferida.
5. DataJud e outras fontes de movimentação não criam prazo jurídico sem o motor
   canônico e revisão humana.
6. Toda saída jurídica destinada a uso profissional continua sujeita a HITL,
   citation gate, RBAC/ownership, sanitização e AILog já existentes.
7. Jurimetria é estatística descritiva e não probabilidade de êxito do caso.
8. Saúde do corpus continua tendo fonte única em
   `app.services.knowledge_governance.health_snapshot`; o Legal Brain não cria
   métrica concorrente.

## Componentes desta fundação

`app/services/legal_brain/contracts.py`
: contratos de estado probatório, skill versionada, pesquisa e validade de
  precedente.

`app/services/legal_brain/issue_engine.py`
: identificação determinística de questões candidatas. Não decide mérito.

`app/services/legal_brain/research_loop.py`
: plano de pesquisa que exige fonte primária, validade temporal, precedente de
  apoio, entendimento adverso e aderência fática.

`app/services/legal_brain/precedent_validity.py`
: validade proposicional baseada somente em relações explícitas e com
  proveniência.

`app/services/legal_brain/skill_contracts.py`
: transforma o catálogo canônico já existente em contratos versionáveis sem
  manter um segundo registry.

`app/services/legal_brain/brain.py`
: compõe questões + skills nativas + pesquisa sem criar novo orquestrador.

`app/eval/legal_bench.py`
: baseline reproduzível e barato para issue recall, precisão de fontes,
  grounding fático, pesquisa adversa e respeito à incerteza.

Para saúde do corpus, usar `knowledge_governance.health_snapshot` e
`backend/scripts/relatorio_vigencia_legislacao.py`; nenhuma lógica paralela deve
ser adicionada.

## Pipeline alvo

```text
caso/documentos
      ↓
estado probatório
      ↓
Legal Issue Engine
      ↓
skills nativas versionadas
      ↓
Research Plan
      ↓
RAG/fontes oficiais existentes
      ↓
validade temporal/proposicional
      ↓
tese + contratese + prova
      ↓
revisão judicial/adversarial
      ↓
redação
      ↓
citation gate + HITL + AILog
```

## Rollout

A fundação nasce sem migration, endpoint ou chamada nova de modelo. Primeiro ela
é validada por testes determinísticos e Legal Bench. A ligação ao runtime deve
entrar em modo shadow, sem alterar resposta ao usuário, e só depois de superar o
baseline pode participar da montagem de contexto do orquestrador.

## Dados e LGPD

O Legal Brain não deve persistir conteúdo sensível novo apenas para observar a
IA. Quando métricas exigirem exemplos, usar IDs e dados sintéticos/pseudonimizados.
Contexto case-scoped sempre herda ownership do caso e nunca pode ser promovido a
memória transversal sem ato humano auditável.
