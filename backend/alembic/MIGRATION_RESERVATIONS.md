# Reserva de numeração das migrations do EJC

Controle obrigatório para impedir que dois PRs escolham o mesmo número de migration ou
partam de heads diferentes. Regra canônica em `docs/GOVERNANCA_IA.md`, seção 8.

**Head da `main` em 2026-07-30:** `123_legal_doc_ai_log_vinculo`.

## Como reservar

Antes de escrever qualquer migration:

```bash
git checkout main && git pull --ff-only
cd backend && python -m alembic heads          # confirma o head atual
gh pr list --state open                        # confere quem já reservou número
```

1. Atualize a `main` local.
2. Consulte os PRs abertos (inclusive drafts) e esta tabela.
3. Verifique o head do Alembic — o `down_revision` da sua migration é **o head da `main`**.
   Nunca aponte para uma migration que ainda não foi mesclada: numa branch tirada da
   `main` esse arquivo não existe, o grafo fica órfão e a guarda de numeração reprova
   (`test_migration_numbering_guard.py`). Se o número anterior está reservado por um PR
   aberto, resolva ou revogue formalmente a reserva antes de prosseguir —
   `docs/GOVERNANCA_IA.md` exige frentes sequenciais e não suporta branches empilhadas.
4. Registre a reserva nesta tabela **no mesmo PR** que cria a migration.
5. Confirme as dependências: a cadeia precisa ficar linear e com head único.

Estados: `Reservada` (número tomado, migration em desenvolvimento) · `Em PR` (aberta,
aguardando revisão) · `Mesclada` (na `main`) · `Revogada` (branch ficou incompatível; a
migration precisa ser reconstruída e renumerada) · `Liberada` (PR fechado sem merge — o
número volta a ficar disponível).

## Tabela de reservas

| Número | `down_revision` | Branch | PR | Responsável | Estado | Observação |
|---|---|---|---|---|---|---|
| 122_route_usage_metrics | 121_sala_juridica_chat | main | mesclada | Claude Code | Mesclada | Telemetria agregada de uso de rotas. |
| 122_data_room_token_hash | 121_sala_juridica_chat | claude/new-session-4tyz91 | [#495](https://github.com/s2corporativo/ejc/pull/495) | Claude Code | Revogada | A `main` já usa o número 122. O conteúdo do PR só pode ser extraído para branch nova e renumerada. |
| 122_documentos_publicacao_hash | 121_sala_juridica_chat | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Colide com o head canônico e não pode ser integrado no estado atual. |
| 123_deadline_owner | 122_documentos_publicacao_hash | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Depende de migration inexistente na `main`; eventual extração deve receber nova numeração. |
| 124_data_room_token_hash | 123_deadline_owner | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Desenho antigo e cadeia inexistente; substituído pela reserva linear abaixo. |
| 125_legal_doc_revisao | 124_data_room_token_hash | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Não resolve a correlação estrutural LegalDoc ↔ AILog; eventual histórico será extraído separadamente. |
| 126_fee_valor_check | 125_legal_doc_revisao | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Eventual extração deve partir do head vigente e ser renumerada. |
| 127_audit_log_worm | 126_fee_valor_check | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Eventual extração deve partir do head vigente e ser renumerada. |
| 123_legal_doc_ai_log_vinculo | 122_route_usage_metrics | main | [#544](https://github.com/s2corporativo/ejc/pull/544) | ChatGPT | Mesclada | Head canônico atual; FK + hash do conteúdo + invalidação automática da validação ao editar a peça. |
| 124_data_room_public_link_hardening | 123_legal_doc_ai_log_vinculo | fix/dataroom-public-link-hardening | [#547](https://github.com/s2corporativo/ejc/issues/547) | ChatGPT | Reservada | Hash de links públicos em repouso e publicação externa explícita por arquivo. |

> **Decisão do titular em 2026-07-29.** A continuidade das correções foi autorizada após
> a integração dos PRs #535, #542 e #543. As reservas das branches antigas #495/#497
> foram revogadas porque partem de uma cadeia que não existe mais na `main`. Nenhuma
> de suas migrations pode ser mesclada ou reutilizada sem reconstrução e nova reserva.

## Guarda automática

`backend/tests/test_migration_numbering_guard.py` roda na suíte do CI e cobra, sem depender
de identificador fixo:

- número de prefixo único por migration — **é o teste que impede nova colisão**;
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
  irreversível e de qual é o procedimento de recuperação.
