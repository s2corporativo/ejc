# ADR — EJC Core e separação progressiva de verticais

**Data:** 2026-09-25  
**Status:** Aceito — execução incremental  
**Issue canônica:** #1843  
**Base inicial:** `main@663836d0d6f21a23365f3ebbdce5f11b86430d82`

## Contexto

O EJC acumulou, além do núcleo de operação jurídica do escritório, workspaces e regras de negócio especializados por área. Entre as superfícies verificadas na `main` estão DPT Empresarial 360, Áreas de Atuação, Ambiental especializado e Tributário especializado.

Essa coexistência aumenta a superfície de navegação, o acoplamento entre `Case` e modelos satélites, o raio de explosão de mudanças e a probabilidade de trabalho concorrente entre agentes de desenvolvimento.

A decisão desta ADR é simplificar o produto sem executar uma reescrita ou remoção destrutiva.

## Decisão

O **EJC** passa a ser definido como o sistema jurídico geral do escritório.

### EJC Core

Permanecem como capacidades canônicas:

- Dashboard;
- Entrada Única;
- Clientes;
- Casos;
- Partes;
- Processos;
- Documentos/GED;
- Peças e produção jurídica;
- Prazos, agenda e tarefas;
- Ajuizamento e encerramento;
- Honorários e financeiro ligado ao caso;
- Pesquisa e conhecimento jurídico;
- Teses;
- IA Jurídica/RAG;
- DataJud/DJEN e integrações processuais;
- Portal do Cliente;
- RBAC/ownership;
- Auditoria, LGPD e administração.

### Verticais a separar

Deixam progressivamente de ser módulos internos do EJC:

- DPT Empresarial 360 / Empresa 360;
- Áreas de Atuação como workspaces especializados;
- Ambiental especializado;
- Tributário especializado.

Outras especializações por ramo devem ser avaliadas pelo mesmo critério antes de qualquer extração.

## Área jurídica continua existindo

Esta decisão **não elimina** `CaseArea`, `CasoArea` nem a classificação por ramo.

Área jurídica passa a ser tratada como:

- metadado do caso;
- contexto para pesquisa/RAG;
- filtro operacional;
- contexto de skills e prompts;
- dimensão de jurimetria e relatórios.

Ela deixa de ser, por padrão, justificativa para um sistema ou workspace próprio dentro do EJC.

## Estratégia de migração

### Onda 0 — governança

- registrar esta ADR;
- definir EJC Core × Vertical × Shared × Legacy Compatibility;
- considerar a `main` vigente como fonte de verdade;
- branches antigas divergentes são material de consulta, não base automática de merge.

### Onda 1 — navegação

- retirar DPT360 e Áreas de Atuação da navegação efetiva;
- manter rotas e RBAC existentes;
- manter Tributário especializado oculto;
- manter compatibilidade de deep-links;
- nenhuma migration.

### Onda 2 — congelamento de acoplamento

- impedir novas dependências do EJC Core em código vertical;
- inventariar consumidores de models, routers, services, jobs e schemas verticais;
- definir contratos de integração futuros.

### Onda 3 — desacoplamento

- remover dependências do Core em models especializados somente após substituição dos consumidores;
- preservar prazos, documentos, AuditLog, ownership e contexto jurídico.

### Onda 4 — extração

Criar aplicações verticais independentes quando houver domínio suficiente, sem copiar o EJC inteiro.

### Onda 5 — dados

- exportar;
- validar;
- importar;
- reconciliar;
- manter legado read-only quando necessário;
- somente então realizar cutover.

### Onda 6 — expurgo

Excluir código/tabelas apenas após:

- telemetria de uso;
- ausência comprovada de consumidores;
- backup;
- migration reversível quando tecnicamente possível;
- teste de restauração;
- rollback documentado.

## Regras de coexistência com outras IAs

1. Trabalho já incorporado à `main` é preservado salvo defeito comprovado.
2. PR divergente não prevalece sobre a `main`.
3. Mudança concorrente sem conflito pode ser incorporada.
4. Mudança concorrente que reintroduza verticalização deve ser reconciliada com esta ADR.
5. Nenhum agente deve criar nova dependência do EJC Core em DPT360, Ambiental especializado ou Tributário especializado sem decisão arquitetural explícita.
6. Alterações recentes da #1841 em Case/Financeiro/Encerramento são parte do Core e não devem ser reimplementadas.

## Segurança e LGPD

A separação não pode:

- ampliar RBAC;
- remover ownership;
- expor PII;
- remover pseudonimização;
- remover AuditLog;
- reduzir HITL;
- mover dados para uma vertical sem necessidade e finalidade definidas.

## Rollback

A Onda 1 é reversível por commit: restaurar `showInNav`/`essential` no registry.

Nenhuma tabela, migration histórica, endpoint ou dado é removido nesta onda.

## Critérios de aceite da Onda 1

- DPT360 ausente da navegação e dos atalhos derivados de `getNavigationModules`;
- Áreas de Atuação ausente da navegação;
- deep-links continuam válidos para papéis autorizados;
- RBAC inalterado;
- Tributário especializado permanece oculto;
- nenhum DROP;
- nenhum dado alterado;
- testes de registry atualizados;
- build/testes frontend verdes antes do merge.
