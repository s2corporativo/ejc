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
| 124_dataroom_public_hardening | 123_legal_doc_ai_log_vinculo | fix/dataroom-public-link-hardening | [#547](https://github.com/s2corporativo/ejc/issues/547) | ChatGPT | Mesclada | Hash de links públicos em repouso e publicação externa explícita por arquivo. |
| 125_fonte_execucoes_zeradas | 124_dataroom_public_hardening | claude/bloco5-monitorar-resultado | [#624](https://github.com/s2corporativo/ejc/pull/624) | Claude Code | Mesclada | Contador de execuções improdutivas + `ja_produziu` por fonte de ingestão (Bloco 5). |
| 126_case_status_quatro_estados | 125_fonte_execucoes_zeradas | claude/bloco3-quatro-estados | [#630](https://github.com/s2corporativo/ejc/pull/630) | Claude Code | Mesclada | Quatro estados de caso (Bloco 3, decisão do titular 2026-08-02). Nasceu encadeada na 124; com o merge do #624 o down_revision foi promovido para a 125, como planejado. **Head da `main`.** |
| 127_publicacao_explicita | 126_case_status_quatro_estados | claude/ejc-audit-redesign-7i7idc | [#684](https://github.com/s2corporativo/ejc/pull/684) | Claude Code | Mesclada | Fase 0: corrige vazamento de sigilo do portal — documentos publicados por omissão. Default confidencialidade "normal"→"confidencial"; usuário marca EXPLICITAMENTE para publicar (Auditoria 2026-07). |
| 130_ejc_skills_uso | 127_publicacao_explicita | claude/ejc-skills-uso-tracking | [#688](https://github.com/s2corporativo/ejc/pull/688) | Claude Code | Mesclada | Bloco 4 (enxugar catálogo): contador `vezes_executado`/`ultima_execucao` em `ejc_skills` — pré-requisito para "mantenha no catálogo só skills com uso registrado"; `AILog` não distingue qual skill gerou a chamada, não dava pra inferir uso retroativo. Não arquiva nada sozinho — só relatório (`scripts/relatorio_skills_sem_uso.py`). Número escolhido pulando 128/129 (reservados pelo #679, ainda não mesclado). |
| 131_audit_logs_worm | 130_ejc_skills_uso | claude/audit-worm-699 | [#707](https://github.com/s2corporativo/ejc/pull/707) | Claude Code | Mesclada | Issue #699: impõe WORM em `audit_logs` via trigger `BEFORE UPDATE OR DELETE` que levanta exceção, com via privilegiada de expurgo inativa (`SET LOCAL ejc.audit_logs_permitir_expurgo = 'on'`) reservada para a futura #582. |
| 132_case_parte_pii_encriptado | 131_audit_logs_worm | claude/auditoria-ejc-graphify-aoa2hi | [#652](https://github.com/s2corporativo/ejc/pull/652) | Claude Code | Em PR | P1-5 da auditoria integral: conclui o cutover C6/LGPD em `case_partes` (`cpf_cnpj` em texto puro → `cpf_cnpj_enc`/`_hash`/`_mascarado`, com backfill por keyset antes do DROP). **Renumerada de 131 para 132 em 2026-08-05** após PR #707 mergear com 131_audit_logs_worm. |
| 133_user_password_changed_at | 132_case_parte_pii_encriptado | claude/fixes-without-github-45v7ep | [#679](https://github.com/s2corporativo/ejc/pull/679) | Claude Code | Em PR | Marca de quando a senha atual foi definida, para `get_current_user` recusar access token anterior à troca. Renumerada de 128 em 2026-08-05. Coluna nullable, sem backfill: preencher com `now()` derrubaria toda sessão ativa no deploy. A proteção passa a valer a partir da próxima troca de cada usuário. |
| 134_processes_numero_cnj_index | 133_user_password_changed_at | claude/fixes-without-github-45v7ep | [#679](https://github.com/s2corporativo/ejc/pull/679) | Claude Code | Em PR | Índice NÃO ÚNICO em `processes.numero_cnj` (DADOS-003, parcial) — busca por número de processo. Renumerada de 129 em 2026-08-05. A parte UNIQUE ficou de fora: exige checar duplicata em produção antes, o que este ambiente não tem acesso para fazer. |

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
