# P0 — Woodpecker: lock do SQLite bloqueando pipeline da `main`

Data da verificação operacional: 2026-09-07.

## Evidência observada

Durante inspeção direta da VPS, o status do commit `3c4f938d30ea7916e213e1473e7750406e097000` estava publicado como `failure` pelo contexto Woodpecker. No `woodpecker-server`, na janela do webhook do merge, foram observados:

- `database is locked`;
- `failed to save pipeline for s2corporativo/ejc`;
- `POST /api/hook` com HTTP 500.

A instância roda Woodpecker v3.18.0 com SQLite padrão no volume `woodpecker-server-data`. O agente está limitado a um workflow por vez, mas o servidor mantém os defaults do pool de banco se nada for configurado.

## Diagnóstico

Camada: CI/CD e infraestrutura.

Impacto: o GitHub pode receber status `failure` ou deixar de receber um pipeline válido mesmo quando o código do EJC não falhou nos testes. Enquanto isso ocorrer, o gate de deploy aprovado por SHA não deve promover a `main`.

Risco jurídico/LGPD: não toca dados jurídicos ou pessoais. O banco do Woodpecker contém metadados operacionais e deve continuar protegido e copiado apenas pelo backup controlado já existente.

## Mitigação escolhida

Serializar o pool SQLite do servidor nesta instância single-server:

- `WOODPECKER_DATABASE_MAX_CONNECTIONS=1`;
- `WOODPECKER_DATABASE_IDLE_CONNECTIONS=1`.

A mudança é pequena, reversível e compatível com o fato de o agente já executar um workflow por vez. Ela reduz concorrência de escrita no SQLite sem exigir migração imediata do banco administrativo do CI.

## Critérios de aceite

- teste versionado do Compose exige os dois limites;
- `docker compose config` renderiza os valores esperados;
- backup consistente do Woodpecker executado antes da recriação;
- somente `woodpecker-server` recriado para aplicar a configuração;
- `/healthz` responde após a recriação;
- logs novos não mostram `database is locked` durante o teste;
- pipeline da `main` é reexecutado e o status publicado no GitHub deixa de refletir a falha de persistência.

## Próximo nível

Se o lock reaparecer depois desta mitigação, abrir migração controlada do banco administrativo do Woodpecker para PostgreSQL. A documentação oficial informa suporte a PostgreSQL e migrações de schema automáticas, mas a transferência dos dados existentes do SQLite exige um plano explícito de exportação/importação, validação e rollback; não deve ser improvisada em produção.

## Rollback

Reverter o commit, restaurar os defaults do pool e recriar somente `woodpecker-server`. Não remover volumes e nunca usar `docker compose down -v`.
