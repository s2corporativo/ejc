# Reserva de numeração das migrations do EJC

Controle obrigatório para impedir que dois PRs escolham o mesmo número de migration ou
partam de heads diferentes. Regra canônica em `docs/GOVERNANCA_IA.md`, seção 8.

**Head da `main` em 2026-07-27:** `121_sala_juridica_chat`.

## Como reservar

Antes de escrever qualquer migration:

```bash
git checkout main && git pull --ff-only
cd backend && python -m alembic heads          # confirma o head atual
gh pr list --state open                        # confere quem já reservou número
```

1. Atualize a `main` local.
2. Consulte os PRs abertos (inclusive drafts) e esta tabela.
3. Verifique o head do Alembic — o `down_revision` da sua migration é o head **ou** a
   migration imediatamente anterior já reservada e ainda não mesclada.
4. Registre a reserva nesta tabela **no mesmo PR** que cria a migration.
5. Confirme as dependências: a cadeia precisa ficar linear e com head único.

Estados: `Reservada` (número tomado, migration em desenvolvimento) · `Em PR` (aberta,
aguardando revisão) · `Mesclada` (na `main`) · `Liberada` (PR fechado sem merge — o número
volta a ficar disponível).

## Tabela de reservas

| Número | `down_revision` | Branch | PR | Responsável | Estado | Observação |
|---|---|---|---|---|---|---|
| 122_data_room_token_hash | 121_sala_juridica_chat | claude/new-session-4tyz91 | [#495](https://github.com/s2corporativo/ejc/pull/495) | Claude Code | Em PR | **Colisão com o #497** — mesmo número 122, conteúdo diferente. Converte `data_room_links.token` em hash no lugar (sem coluna nova). |
| 122_documentos_publicacao_hash | 121_sala_juridica_chat | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Em PR | **Colisão com o #495** — mesmo número 122. Publicação explícita + hash de documento. |
| 123_deadline_owner | 122_documentos_publicacao_hash | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Em PR | Depende da 122 do próprio #497. |
| 124_data_room_token_hash | 123_deadline_owner | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Em PR | **Duplica o objetivo da 122 do #495**, com desenho oposto (coluna `token_hash` nova, `token` em claro preservado). Ver `docs/MATRIZ_CONSOLIDACAO_P0.md`. |
| 125_legal_doc_revisao | 124_data_room_token_hash | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Em PR | Histórico imutável de peças. |
| 126_fee_valor_check | 125_legal_doc_revisao | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Em PR | CHECK de valores financeiros. |
| 127_audit_log_worm | 126_fee_valor_check | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Em PR | Trigger WORM em `audit_logs`. |

> **Pendência de decisão humana.** A colisão no número 122 entre os PRs #495 e #497 precisa
> ser resolvida antes de qualquer merge: um dos dois renumera e as duas abordagens do
> Data Room precisam convergir para **uma** (ver `docs/MATRIZ_CONSOLIDACAO_P0.md`, seção 4).
> Enquanto isso não acontecer, o número 128 **não** deve ser reservado por ninguém.

## Guarda automática

`backend/tests/test_migration_numbering_guard.py` roda na suíte do CI e cobra, sem depender
de identificador fixo (ou seja, sem precisar ser editado a cada migration nova):

- número de prefixo único por migration — **é o teste que pega a colisão do 122**;
- todo `down_revision` aponta para uma revisão existente;
- o número do filho é sempre maior que o do pai;
- head único;
- nenhuma revisão de merge nova.

`test_alembic_single_head.py` continua valendo para o encadeamento nominal já registrado,
mas fixa o head à mão — por isso todo PR com migration precisa editá-lo, e dois PRs com
migration conflitam ali por construção.

## Regras que valem sempre

- **Head único.** O repositório nunca tem dois heads; guardado pelos dois testes acima.
- **Migration aplicada em produção não se edita** — corrige-se com uma nova.
- **Autogenerate se revisa à mão.** Dezenas de tabelas do EJC existem apenas em SQL bruto e
  não têm model ORM; `alembic/env.py` tem guarda `include_name()`. Nunca aceite um
  `drop_table` proposto pelo autogenerate sem conferir a tabela.
- **Migration destrutiva** exige backup comprovado e plano de rollback aprovados antes.
- Toda migration precisa de `downgrade()` — ou de uma explicação no cabeçalho de por que é
  irreversível (ex.: hash) e de qual é o procedimento de recuperação.
