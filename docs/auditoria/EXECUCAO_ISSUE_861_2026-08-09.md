# Execução da Issue #861 — Auditoria Operacional

Data: 2026-08-09
PR: #906
Branch: `fix/auditoria-operacional-financeiro-prazos-861`

## Escopo

Correções confirmadas da auditoria de Financeiro, Agenda/Prazos/DJEN, Assinaturas, Portal do Cliente e módulos operacionais auxiliares. O trabalho não autoriza inferência de regra jurídica não confirmada nem exposição de dados/segredos.

## Invariantes preservadas

- prazo sugerido por DJEN permanece assistivo e sujeito a validação humana;
- regime processual desconhecido falha fechado;
- disponibilização, publicação, termo inicial e vencimento são conceitos distintos;
- classificação documental interna não equivale a autorização externa no Portal;
- documento reclassificado como não-normal deixa de ser servido ao Portal mesmo se houver flag histórica de publicação;
- assinatura multiparte só conclui quando todos os signatários exigidos assinam;
- o hash físico do documento é revalidado no aceite;
- cancelamento registral local de NFS-e não é apresentado como cancelamento fiscal;
- despesa recorrente gerada não vira novo modelo recorrente;
- alterações societárias sensíveis exigem justificativa e trilha;
- criador de distribuição de lucros não aprova a própria distribuição;
- RBAC do frontend não substitui autorização/ownership do backend.

## Migration 143

A migration `143_auditoria_operacional_861` é expand-only no upgrade e usa `deployment_policy = "additive_data_backfill"` exclusivamente para o backfill idempotente da nova tabela `signature_signers`.

A idempotência de despesas recorrentes não depende de `UNIQUE` criado em tabela existente durante rolling deploy; o service serializa o par modelo+competência com advisory lock transacional e verifica existência antes da inserção.

O tipo `signaturesignerstatus` é criado por DDL idempotente no padrão aceito pelo gate do repositório (`duplicate_object`) e a tabela reutiliza o tipo com `create_type=False`.

O downgrade é recusado se já existir evidência operacional que o schema legado não consiga representar com segurança; nesse caso, o procedimento correto é backup + forward-fix.

## Trem de migrations

No momento desta execução, a `main` mantém `138_consolida_fontes_ingestao` como head canônico, enquanto os PRs concorrentes reservam 140, 141 e 142 e este PR reserva 143. Como esses PRs ainda partem de 138, a integração deve respeitar a serialização definida pela governança do repositório. O PR #906 permanece draft até essa reconciliação e não deve criar head Alembic paralelo.

## Validações

Rodadas anteriores já comprovaram, no mesmo escopo:

- Ruff e auditoria de dependências;
- `alembic upgrade head` em PostgreSQL 16;
- build frontend e ESLint;
- Chromium responsivo;
- backup cifrado e restauração em banco vazio;
- Release Gate, Architecture Inventory e Governance Gate.

A suíte backend completa encontrou regressões de compatibilidade nos primeiros ciclos; elas foram tratadas por causa raiz sem restaurar defaults juridicamente inseguros. A branch deve permanecer draft até a rodada limpa ficar integralmente verde e ser novamente reconciliada com a `main` atual.
