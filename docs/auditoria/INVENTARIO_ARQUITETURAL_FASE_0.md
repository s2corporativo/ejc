# Fase 0 — Inventário Arquitetural Bloqueante do EJC

## 1. Regra de governança

Nenhuma refatoração ampla de organização, nomenclatura, rotas, fluxos, módulos, banco ou APIs poderá ser iniciada antes da geração e revisão do inventário arquitetural.

O inventário deve abranger, no mínimo:

- páginas e componentes de interface;
- rotas frontend e aliases históricos;
- routers e endpoints FastAPI;
- serviços, classes e funções Python;
- funções TypeScript/TSX;
- modelos e tabelas ORM;
- dependências por importação;
- consumidores frontend detectáveis;
- tabelas referenciadas em SQL;
- estado de montagem dos routers;
- famílias de versões ou responsabilidades potencialmente duplicadas.

## 2. Classificações obrigatórias

Todo item recebe exatamente uma classificação:

1. **manter** — componente canônico ou necessário, sem ação estrutural imediata;
2. **consolidar** — responsabilidade sobreposta, versão paralela ou experiência duplicada;
3. **renomear** — função correta com nomenclatura divergente do vocabulário canônico;
4. **redirecionar** — rota histórica preservada como alias para uma rota canônica;
5. **corrigir** — item necessário com acoplamento, contrato, segurança, fluxo ou modelagem a ajustar;
6. **desativar** — item não deve permanecer disponível, mas ainda exige verificação antes da remoção;
7. **excluir após migração** — candidato à remoção somente após migração, telemetria, testes e rollback.

A classificação não substitui revisão humana. O relatório distingue classificações explícitas, inferências por montagem, famílias duplicadas e manutenção conservadora.

## 3. Artefatos gerados

Executar:

```bash
python scripts/generate_architecture_inventory.py --check
```

Saída padrão: `docs/auditoria/inventory/`.

| Arquivo | Finalidade |
|---|---|
| `README.md` | relatório legível, contagens e tabelas completas |
| `architecture_inventory.json` | inventário integral estruturado |
| `architecture_inventory.csv` | triagem em planilha/filtros |
| `classification_review.csv` | itens que ainda exigem revisão humana |
| `duplicate_families.json` | famílias candidatas à consolidação |
| `manifest.json` | fingerprint, contagens e gate de classificação |

## 4. Fonte das classificações

As decisões explícitas ficam em:

```text
config/architecture_inventory_overrides.json
```

As regras são versionadas, auditáveis e avaliadas na ordem declarada. A primeira correspondência prevalece.

Classificações automáticas conservadoras:

- router ou endpoint não montado: `desativar`;
- família com versões paralelas: `consolidar`;
- nome histórico/legacy/old/backup: `excluir após migração`;
- alias declarado: `redirecionar`;
- ausência de evidência suficiente: `manter`, com revisão humana obrigatória.

## 5. Critério para exclusão

Nenhum item será removido somente porque não há chamada literal no frontend.

Antes de excluir, é obrigatório verificar:

- componentes filhos e imports dinâmicos;
- scripts, tarefas agendadas e workers;
- webhooks e integrações externas;
- portal do cliente e APIs públicas;
- favoritos e deep-links históricos;
- tabelas, dados e arquivos persistidos;
- logs de uso ou telemetria por período adequado;
- plano de migração, compatibilidade e rollback;
- testes de regressão específicos.

## 6. Sequência operacional após o inventário

1. revisar itens de maior risco: CasoDetalhe, `main.py`, `moduleRegistry`, IA/RAG, documentos/peças e Caso×Processo;
2. confirmar as classificações explícitas por domínio;
3. congelar contratos atuais de request/response antes de renomear ou consolidar;
4. criar aliases e adaptadores de compatibilidade;
5. migrar por lotes pequenos, com testes;
6. retirar aliases somente após telemetria e aprovação expressa.

## 7. Estado desta branch

A branch `agent/organizacao-padronizacao-rotas-fluxos` contém apenas ferramentas, regras e documentação de inventário. Não altera comportamento de produção, banco, rotas existentes, permissões ou integrações.
