# Reserva de numeração das migrations do EJC

Este arquivo é o ledger canônico de **reservas futuras** e do trecho recente da cadeia Alembic. O histórico detalhado de reservas antigas permanece preservado no Git.

**Head canônico atual da `main`:** `156_documentos_governanca_outbox`
**Próximo prefixo livre:** `157`
Após o merge desta PR, o próximo prefixo livre continuará `157` — a `156` ficará ocupada por `156_documentos_governanca_outbox` e **não poderá ser reutilizada**.

> Enquanto o PR #1368 estiver aberto, esta declaração acompanha o head efetivo da branch para que os gates Alembic validem a cadeia que está sendo promovida. No merge, a `main` passa a ter esse mesmo head.

> Nunca reutilize um número menor ou igual ao head atual, mesmo quando houver lacuna histórica. A ordem numérica precisa crescer junto com `down_revision`.

## Regra obrigatória

Antes de criar migration:

```bash
git checkout main && git pull --ff-only
cd backend
python -m alembic heads
gh pr list --state open
```

1. O `down_revision` deve ser o head efetivo da `main`, salvo merge revision explicitamente aprovada.
2. Confira este ledger e todos os PRs abertos/drafts antes de escolher o prefixo.
3. Reserve o novo número no mesmo PR que cria a migration.
4. Branches empilhadas não reservam uma sequência futura: só o próximo número após a `main` pode ser tomado.
5. Migration já aplicada/mesclada nunca é reescrita; correção posterior recebe novo número.
6. Migration destrutiva exige backup comprovado, plano de rollback e aprovação explícita.
7. `test_alembic_single_head.py`, `test_migration_numbering_guard.py` e `test_migration_reservations_head.py` são gates bloqueantes.

## Estados

- `Reservada`: número tomado por trabalho baseado no head atual.
- `Em PR`: migration existe em PR aberto e continua baseada no head atual.
- `Mesclada`: integra a `main`.
- `Revogada`: branch perdeu compatibilidade; conteúdo só pode ser reconstruído e renumerado.
- `Liberada`: PR fechado sem merge **somente se o número ainda for maior que o head atual**. Número já ultrapassado nunca volta a ser utilizável.

## Cadeia recente reconciliada

| Número | `down_revision` | Estado | Observação |
|---|---|---|---|
| `147_pendencia_impacto_providencia` | `146_case_sigilo_reforcado` | Mesclada | Head anterior do qual partiram as frentes de agosto. |
| `148_banco_teses_juridicas` | `147_pendencia_impacto_providencia` | **Revogada / aposentada** | Nunca integrou a `main`. A série antiga #1264/#1267 ficou incompatível depois que a cadeia avançou. Não reutilizar 148. |
| `149_documents_sha256_integridade` | `147_pendencia_impacto_providencia` | Mesclada | Integridade documental. A lacuna 148 é histórica e intencional. |
| `150_indices_fk_espinha_dominio` | `149_documents_sha256_integridade` | Mesclada | Índices da espinha do domínio. |
| `151_case_status_anterior` | `150_indices_fk_espinha_dominio` | Mesclada | Histórico de status de caso. |
| `152_thesis_candidate_tese_banco` | `151_case_status_anterior` | Mesclada | Ponte Matriz de Teses → Banco de Teses canônico. |
| `153_legal_doc_client_id` | `152_thesis_candidate_tese_banco` | Mesclada | Isolamento estável cliente → peça avulsa, reconstruído a partir do #1231 sem reutilizar a antiga migration 147. |
| `154_saneamento_schema` | `153_legal_doc_client_id` | Mesclada | Módulo de saneamento de base processual (PROMPT 1). Encadeada sobre 153 porque era o head real no momento (`alembic heads`) — não pressupõe que 153 já tenha sido mesclada; conferir o head real de novo antes do merge. 7 tabelas próprias, **prefixadas `saneamento_*` no schema `public`** — nenhuma alteração em tabela existente do EJC. Um schema Postgres dedicado (`CREATE SCHEMA`) foi cogitado e descartado: `scripts/check_migration_compatibility.py` (gate de deploy) e os testes de paridade schema↔ORM (`test_schema_dr_parity.py`, `test_schema_sync.py`) extraem nomes de tabela por regex/AST sem suporte a qualificação de schema — mudar essas ferramentas para um caso de uso isolado era desproporcional ao módulo. Prefixo de tabela entrega o mesmo isolamento prático. |
| `155_indices_listagem_espinha` | `154_saneamento_schema` | Mesclada | Índices parciais de listagem em `cases`/`clients`/`documents` (AUD27-P3-11). `deadlines` fora de propósito: já coberta por `ix_deadlines_data_prazo`, medido. |
| `156_documentos_governanca_outbox` | `155_indices_listagem_espinha` | **Em PR — #1368 / HEAD desta branch** | Governança documental expand-only: estados de malware/IA/integridade/RAG, retenção/legal hold e outbox durável de storage. Nenhum `DROP` no upgrade. |

## Banco de Teses — decisão canônica

A fonte de verdade é **`teses` + `tese_caso_links`**. Não criar `legal_theses`, `teses_juridicas`, `teses_v2`, `teses_v4` ou outro banco paralelo. Qualquer evolução deve estender a estrutura canônica de forma aditiva e preservar Jurimetria, Súmulas, matcher tese↔caso, Matriz de Teses e frontend existentes.

Os PRs antigos #1264, #1267, #1269 e #1275 são fontes históricas de requisitos/código, não unidades de merge. Qualquer conteúdo ainda útil deve ser reaplicado sobre a `main` vigente, com nova numeração e sem substituir arquivos que já evoluíram.

A reserva condicional que antes apontava `153` para uma extensão futura do Banco de Teses foi liberada porque não havia migration nem PR 153 em andamento. Como o isolamento cliente→documento corrige um risco concreto de ownership/homônimos, ele assume o próximo número canônico. Qualquer futura extensão de teses deverá usar o próximo número livre após a integração desta migration.

## Guarda automática

`backend/tests/test_migration_reservations_head.py` compara este head documentado com o head real lido pelo Alembic e verifica que o próximo prefixo é exatamente o sucessor numérico. Assim, o ledger não pode voltar a anunciar um head antigo sem quebrar a suíte.
