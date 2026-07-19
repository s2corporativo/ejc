# Agente e skills nativos do EJC

## Resultado

O EJC possui um único coordenador interno, `EJCCoordinatorAgent`, executado pelo
`SingleAICoreOrchestrator`. Ele não cria outro provider ou pipeline. Em cada
solicitação, o núcleo combina:

1. o agente especialista selecionado pela intenção;
2. no máximo uma skill nativa do ramo jurídico;
3. no máximo uma skill nativa do módulo do EJC;
4. as barreiras existentes de RBAC/ABAC, LGPD, fontes, AILog e HITL.

A seleção é determinística e auditável; não consome uma chamada de modelo.

## Cobertura canônica

- 14 ramos jurídicos do frontend;
- 35 módulos do `MODULE_REGISTRY`;
- 49 skills nativas no total;
- especialistas dedicados para Ambiental, Digital/LGPD e Trânsito, além dos
  agentes jurídicos já existentes.

A fonte canônica é
`backend/app/services/ai/core/ejc_skill_catalog.py`. O endpoint
`GET /api/ai/core/native-skills/coverage` falha visivelmente no teste caso um
módulo novo seja criado sem método nativo correspondente.

## Contexto enviado pelo frontend

Os endpoints `/api/ai/core/chat`, `task`, `analyze`, `generate` e
`report` aceitam `module_key` e `surface`. `domain` identifica o ramo.

Exemplo:

```json
{
  "task_type": "case_analysis",
  "domain": "ambiental",
  "module_key": "casos",
  "surface": "processos",
  "mensagem": "Analise os documentos e indique pendências."
}
```

A resposta informa `agente_coordenador`, `agente_especialista`,
`skills_nativas`, `ramo_juridico`, `modulo_ejc` e o
`skill_pipeline` efetivamente aplicado.

## Persistência e operação

O seed idempotente `skills_native_ejc_seed.py` publica as mesmas 49 definições
na tabela `ejc_skills`, permitindo descoberta e execução pelo assistente
contextual. O `seed_all.py` o executa no pós-deploy e atualiza a versão apenas
quando o conteúdo mudou.

Skills de ramo são restritas aos perfis jurídicos internos e sempre retornam
rascunho sujeito a revisão humana. Skills de módulo não confirmam mutação,
protocolo, envio, cálculo ou sincronização sem retorno da ferramenta e
confirmação humana correspondente.
