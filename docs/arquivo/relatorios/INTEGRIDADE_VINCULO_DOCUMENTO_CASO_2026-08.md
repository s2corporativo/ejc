# Integridade do vínculo Documento ↔ Caso — agosto/2026

## Finalidade

Registrar o invariante aplicado pelo rebuild do PR #888/#938 para evitar que uma operação de conveniência do GED altere o contexto jurídico de uma evidência já incorporada a outro caso.

## Invariante

O fluxo `POST /api/cases/{case_id}/documentos/{document_id}/vincular` somente vincula documento ainda sem `case_id`.

Documento já pertencente a outro caso **não é movido**, ainda que o usuário tenha acesso aos dois casos. Reuso legítimo de conteúdo entre casos deve ocorrer por fluxo futuro de cópia controlada, com nova identidade documental e rastreabilidade própria, sem mutar a evidência original.

## Controles

- autorização e ownership são validados no backend;
- acesso ao caso de origem é verificado antes do erro de conflito, evitando vazamento de existência;
- `Case` de destino e `Document` usam lock pessimista durante a operação;
- documento de outro cliente é rejeitado;
- comprovante de protocolo ativo é inelegível;
- documento referenciado por `Prova` ativa é inelegível;
- filtros de elegibilidade são aplicados antes de `count`, `offset` e `limit`;
- vínculo, transição de status e audit log permanecem na mesma transação;
- auditoria registra identificadores e estado, sem conteúdo documental.

## Testes mínimos

A suíte DB-level deve provar:

1. vínculo de documento solto com transição e auditoria atômicas;
2. cross-client negado;
3. ausência de vazamento de caso de origem;
4. imutabilidade de documento já vinculado a outro caso;
5. exclusão de comprovante de protocolo e de `Prova` ativa;
6. elegibilidade antes da paginação;
7. duas operações concorrentes no mesmo caso produzindo uma única transição de status.

A suíte frontend deve provar que a ação canônica usa o endpoint de domínio, descarta respostas antigas, expõe erro/retry e bloqueia defensivamente eventual resultado já vinculado.

## LGPD e segurança jurídica

O desenho aplica necessidade, mínimo privilégio e rastreabilidade. Não amplia a visibilidade de documentos, não replica dados pessoais e evita quebrar a cadeia contextual de prova ou de protocolo por remanejamento de identidade documental.

## Rollback

Reverter o PR que introduz este contrato. Não há migration, alteração de schema ou transformação retroativa de documentos existentes. Vínculos já praticados permanecem atos auditados e não devem ser desfeitos automaticamente por rollback de código.
