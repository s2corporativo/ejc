# Auditoria E2E — Módulo Documentos / GED

Data: 2026-09-02
Base auditada: `main@5f89e5e3a5e72428fc1eee52b3e68a65caea4b19`
Issue canônica: #1019

## Escopo

Auditoria ponta a ponta do domínio Document/Documentos, incluindo router GED, storage local/Google Drive, lixeira, integridade SHA-256, versionamento, ingestão/OCR/IA, busca/paginação, frontend global e aba de documentos do caso, RBAC/ownership/cofre, auditoria e migrations.

## Estado confirmado

| Item | Estado na base auditada | Evidência / observação |
|---|---|---|
| PATCH apenas metadados | Implementado | `DocumentPatchRequest(extra="forbid")`; vínculo não é aceito no PATCH. |
| Gate de ownership/IDOR | Implementado | `_verificar_acesso_documento` e `verificar_acesso_caso`. |
| Cofre/confidencialidade | Implementado | `restrito/confidencial/segredo_justica` exigem sócio+. |
| Reference guard antes de excluir | Implementado | `exigir_documento_sem_referencias_bloqueantes`. |
| SHA-256 em novos uploads locais | Implementado | `documents.sha256` + persistência no upload; migration 149 reforça integridade. |
| Drive fora do event loop | Parcialmente implementado | operações principais usam `asyncio.to_thread`; legado ainda pode depender da resolução do service. |
| Path remoto persistido | Implementado para uploads novos | `filepath=drive://<remote_path>`. |
| Soft-delete realmente reversível | **Falha crítica** | DELETE Drive apagava o objeto físico antes de `deleted_at`; restauração da lixeira só limpa `deleted_at`. Corrigido nesta branch: storage é preservado no soft-delete. |
| Hard purge físico governado | **Não implementado** | lixeira remove a linha DB, mas não há outbox/retry de storage conectado ao purge. Requer migration expand-only e worker idempotente. |
| Ingestão streaming canônica no runtime | **Não implementado** | `ingerir_documento_local()` existe, mas `/documents/upload` ainda usa `await file.read()` e pipeline legado. |
| Política MIME canônica no router | **Parcial** | `document_content_policy` existe, porém `documents.py` mantém tabela/função duplicadas. |
| Antimalware runtime | **Não implementado** | service ClamAV/fail-closed existe; sem wiring/runtime comprovado e sem estado persistido no `Document`. |
| Versionamento explícito | **Parcial** | services suportam `documento_anterior_id`; endpoint real continua inferindo versão por `titulo + case_id`. |
| Unicidade `(versao_grupo_id, versao)` | **Não implementado por segurança** | depende de auditoria de duplicidades legadas antes de constraint. |
| Busca escalável | **Parcial** | migration 155 melhora índice de ordenação, mas OCR continua `ILIKE %...%`; `COUNT(*)` segue O(n). |
| Paginação determinística | Corrigido nesta branch | limite 100, busca limitada/escapada e desempate `created_at DESC, id DESC`. |
| Keyset/cursor | Não implementado | offset permanece por compatibilidade; precisa cutover dedicado. |
| Paginação frontend global | **Não implementado** | tela global trabalha com janela fixa do backend. |
| Tipos/extensões frontend | **Divergência** | backend aceita `.md`; ao menos a aba de documentos do caso não expõe `.md` no seletor. |
| Busca de candidatos/vínculo | Implementado | endpoint canônico de candidatos + vínculo do caso, com debounce e mensagens de erro. |
| Publicação Portal | Implementado | endpoint explícito, advogado+, documento normal, auditável e idempotente. |
| Serialização de versão/hash | Parcial | listagem pública não expõe metadados de versão/hash; avaliar necessidade de UI sem vazar path. |

## Correções aplicadas nesta branch

1. Soft-delete local/Drive preserva o arquivo físico e passa a ser restaurável.
2. Endpoint legado `DELETE /documents/drive/{file_id}` segue o mesmo lifecycle reversível.
3. AuditLog do soft-delete registra `storage_preservado=true`, sem conteúdo/PII.
4. `GET /documents/` reduz `page_size` máximo de 500 para 100.
5. Busca limitada a 200 caracteres e `%`, `_` e `\\` tratados como literais, evitando expansão acidental de wildcard.
6. Ordenação estável por `created_at DESC, id DESC`.
7. Teste estático de regressão protege os invariantes acima e valida sintaxe do router.

## Pendências que NÃO devem ser forçadas sem preflight

### Storage outbox / hard purge

A correção robusta exige tabela aditiva de operações de storage e worker idempotente. Não é seguro apagar o arquivo antes do hard-delete (pode perder evidência se o commit falhar) nem depois sem outbox (pode deixar órfão em crash). Implementar em migration expand-only após reconfirmar head Alembic e CI real.

### Versionamento concorrente

Não criar `UNIQUE(versao_grupo_id, versao)` sem relatório de duplicidades na base real. Primeiro: query de diagnóstico, correção dos grupos inválidos, testes de concorrência e somente então constraint.

### ClamAV

Não ativar scanner sem comprovar serviço/socket/configuração no Docker/VPS. Quando habilitado, manter fail-closed e teste EICAR; nunca registrar stderr, host, credencial, conteúdo ou nome sensível em audit log.

## Gates obrigatórios antes de merge

- backend importa/compila;
- testes Documentos/GED e regressão desta auditoria verdes;
- frontend compila;
- single Alembic head;
- RBAC/IDOR/cofre preservados;
- nenhum segredo versionado;
- nenhum log com conteúdo documental/PII;
- CI/Release/Governança/Continuity/Architecture executam steps reais e ficam verdes no mesmo SHA.

## Rollback

O primeiro commit desta branch é somente aplicação/teste, sem migration. Rollback imediato: reverter o commit de lifecycle/listagem. Não há alteração de schema nem operação sobre dados/produção.
