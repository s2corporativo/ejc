# Reserva de numeração das migrations do EJC

Controle obrigatório para impedir que dois PRs escolham o mesmo número de migration ou
partam de heads diferentes. Regra canônica em `docs/GOVERNANCA_IA.md`, seção 8.

**Head canônico da `main` em 2026-08-09:** `138_consolida_fontes_ingestao`.

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
4. Registre a reserva nesta tabela **no mesmo PR** que cria ou altera a migration.
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
| 132_processo_eletronico_mni | 131_audit_logs_worm | main | [#763](https://github.com/s2corporativo/ejc/pull/763) / [#819](https://github.com/s2corporativo/ejc/pull/819) | Claude Code / ChatGPT | Mesclada; correção em PR | Fase A MNI/TJMG já integra a `main`. O PR #819 corrige, antes de aplicação automática em produção, o seed que usava `op.bulk_insert`/`uuid4()` e reprovava no gate de deploy: passa a backfill aditivo, idempotente e determinístico. Se for comprovado que a revisão 132 já foi aplicada em produção fora da esteira registrada, esta edição deve ser abandonada e substituída por migration corretiva posterior. |
| 123_deadline_owner | 122_documentos_publicacao_hash | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Depende de migration inexistente na `main`; eventual extração deve receber nova numeração. |
| 124_data_room_token_hash | 123_deadline_owner | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Desenho antigo e cadeia inexistente; substituído pela reserva linear abaixo. |
| 125_legal_doc_revisao | 124_data_room_token_hash | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Não resolve a correlação estrutural LegalDoc ↔ AILog; eventual histórico será extraído separadamente. |
| 126_fee_valor_check | 125_legal_doc_revisao | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Eventual extração deve partir do head vigente e ser renumerada. |
| 127_audit_log_worm | 126_fee_valor_check | claude/new-session-bhbv06 | [#497](https://github.com/s2corporativo/ejc/pull/497) | Claude Code | Revogada | Eventual extração deve partir do head vigente e ser renumerada. |
| 123_legal_doc_ai_log_vinculo | 122_route_usage_metrics | main | [#544](https://github.com/s2corporativo/ejc/pull/544) | ChatGPT | Mesclada | FK + hash do conteúdo + invalidação automática da validação ao editar a peça. |
| 124_dataroom_public_hardening | 123_legal_doc_ai_log_vinculo | fix/dataroom-public-link-hardening | [#547](https://github.com/s2corporativo/ejc/issues/547) | ChatGPT | Mesclada | Hash de links públicos em repouso e publicação externa explícita por arquivo. |
| 125_fonte_execucoes_zeradas | 124_dataroom_public_hardening | claude/bloco5-monitorar-resultado | [#624](https://github.com/s2corporativo/ejc/pull/624) | Claude Code | Mesclada | Contador de execuções improdutivas + `ja_produziu` por fonte de ingestão (Bloco 5). |
| 126_case_status_quatro_estados | 125_fonte_execucoes_zeradas | claude/bloco3-quatro-estados | [#630](https://github.com/s2corporativo/ejc/pull/630) | Claude Code | Mesclada | Quatro estados de caso (Bloco 3, decisão do titular 2026-08-02). Nasceu encadeada na 124; com o merge do #624 o down_revision foi promovido para a 125, como planejado. |
| 127_publicacao_explicita | 126_case_status_quatro_estados | claude/ejc-audit-redesign-7i7idc | [#684](https://github.com/s2corporativo/ejc/pull/684) | Claude Code | Mesclada | Fase 0: corrige vazamento de sigilo do portal — documentos publicados por omissão. Default confidencialidade "normal"→"confidencial"; usuário marca EXPLICITAMENTE para publicar. Nota histórica: PR #679 reservou 128/129 a partir de head anterior e exige reconciliação antes de eventual integração. |
| 130_ejc_skills_uso | 127_publicacao_explicita | claude/ejc-skills-uso-tracking | (a abrir) | Claude Code | Reservada | Bloco 4 (enxugar catálogo): contador `vezes_executado`/`ultima_execucao` em `ejc_skills`; não arquiva nada sozinho. |
| 131_audit_logs_worm | 130_ejc_skills_uso | claude/audit-worm-699 | (a abrir) | Claude Code | Mesclada | Impõe WORM em `audit_logs` via trigger `BEFORE UPDATE OR DELETE`, com via privilegiada de expurgo inativa reservada para política futura. |
| 138_consolida_fontes_ingestao | 132_processo_eletronico_mni | main | [#786](https://github.com/s2corporativo/ejc/pull/786) / [#819](https://github.com/s2corporativo/ejc/pull/819) | Claude Code / ChatGPT | Mesclada; correção em PR | **Head canônico atual da `main`.** A versão inicial consolidava as métricas por lógica dinâmica e removia as linhas `juris_import_*`, o que reprovava no classificador expand-only. O #819 preserva o histórico: promove a linha antiga quando não há canônica; quando coexistem, mescla métricas por UPDATE estático e arquiva a antiga como `legacy_138_*`, inativa, sem DELETE. Se houver prova de que a 138 já foi aplicada em produção fora da esteira registrada, esta edição deve ser abandonada e substituída por migration corretiva posterior. |
| 140_preliminares_fundacao_schema | 138_consolida_fontes_ingestao | feat/964-preliminares-schema-139 | [#965](https://github.com/s2corporativo/ejc/pull/965) | ChatGPT | Mesclada | Fase 1 da fusão física Sala Jurídica + Raio-X: somente quatro tabelas unificadas novas; sem backfill, dual-write, ALTER ou DROP nas tabelas legadas. **Re-ancorada na `139_dpt360_ciclo_vida_lgpd`** para eliminar fork de heads (a `139` LGPD foi mesclada em main antes deste PR). |
| 141_dpt360_diagnostico | 140_preliminares_fundacao_schema | Manus | (a abrir) | Manus | Em PR | Persistência de resultados do Diagnóstico Empresarial 360: tabela `dpt_diagnosticos` (evidências por área, HITL e auditoria OAB). Habilita o campo `persistencia` do readiness; integra-se à action `diagnostico` e ao contador `diagnosticos_pendentes` do dashboard. |
| 143_signature_documento_visualizado | 142_document_hash_rescan | fix/signatura-visualizacao-previa | [#1149](https://github.com/s2corporativo/ejc/pull/1149) | Manus | Mesclada | Issue #1081 (ASS-01): coluna `documento_visualizado_em` em `signature_requests` para o servidor exigir e REGISTRAR a visualização prévia do documento antes de `POST /signatures/{sig_id}/assinar` (MP 2.200-2/2001, art. 10 §2º). Puramente aditiva (timestamp nullable).
| 144_alembic_version_varchar128 | 143_signature_documento_visualizado | fix/migration-alembic-version-varchar128 | (a abrir) | Manus | Reservada | Padroniza `alembic_version.version_num` em `varchar(128)`: o upgrade da 143 estourava o `varchar(32)` original em ambientes novos (deploy em produção exigiu ALTER manual em 15/08/2026). Idempotente (pula se já >= 128) com downgrade protegido contra truncamento.
| 146_case_sigilo_reforcado | 145_drop_orphan_db_only_columns | claude/auditoria-ia-juridica-c2tbf2 | [#1195](https://github.com/s2corporativo/ejc/pull/1195) | Claude Code | Em PR | Issue #1194: coluna `sigilo_reforcado boolean not null default false` em `cases` — achado do `security-auditor` provou que o piso `LOCAL_COMPLETO` de crimes sexuais/menores (redução do AI-019 pedida pelo titular) era inalcançável via `Case.area` (sem granularidade) e via `task_type` (nenhuma rota passa texto livre com a palavra certa). Campo explícito, marcado pelo advogado na triagem, consultado com prioridade em `orchestrator.py`/`agent/loop.py`. Puramente aditiva.

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
