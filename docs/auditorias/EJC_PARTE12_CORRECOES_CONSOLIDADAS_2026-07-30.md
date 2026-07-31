# EJC — Parte 12: correções consolidadas

Data: 2026-07-30
Branch: `fix/parte10-inteligencia-conferencia-assinatura`

## Escopo tratado

1. Dashboard e listagem passam a compartilhar a definição canônica de casos ativos.
2. Casos arquivados não são contabilizados como ativos.
3. Peças de IA em rascunho e ainda não revisadas entram na fila HITL.
4. Peças vinculadas a caso excluído ficam ocultas das superfícies operacionais, preservando histórico e restauração.
5. Filtros de status/área são validados antes de alcançar ENUM nativo do PostgreSQL.
6. Clientes legados podem enviar `all`, `todos` ou `*`; esses valores se tornam predicados neutros e não causam 500 nem lista vazia.
7. Dashboard informa blocos degradados, evitando zero silencioso quando uma consulta falha.
8. Foram adicionados testes de regressão para filtros neutros, enums reais e agregado de ativos.

## Decisão sobre integridade referencial

Foi adotada herança de visibilidade, não exclusão destrutiva em cascata. Ao excluir logicamente um caso, peças e demais dependentes permanecem fisicamente preservados para auditoria e restauração, mas deixam de aparecer em listagens e métricas operacionais. Isso evita perda histórica e impede inflação de indicadores.

## Itens dependentes de ambiente

As etapas abaixo não podem ser certificadas apenas por inspeção estática do GitHub:

- executar `pytest` completo;
- executar testes DB-level com PostgreSQL e migrations (`RUN_DB_TESTS=1`);
- executar lint/typecheck/build do frontend;
- consultar dados reais para confirmar limpeza/ocultação dos 75 registros de teste;
- verificar rotas contra a instância em execução;
- validar captura de intimações e fontes de ingestão com credenciais reais;
- ativar e verificar embeddings/Ollama no servidor;
- conferir logs/telemetria e coletor de erros em produção.

Nenhuma dessas etapas foi declarada concluída sem execução no ambiente.

## Estado de entrega

- PR: não criado.
- Merge: não realizado.
- Deploy: não realizado.
- Banco de produção: não alterado.
- Branch preservada para revisão e execução dos gates.
