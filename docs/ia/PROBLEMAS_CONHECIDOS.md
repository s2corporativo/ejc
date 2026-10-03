# Problemas conhecidos - EJC

Este arquivo registra apenas problemas comprovados por código, teste, log sanitizado, issue, PR ou ambiente controlado. Não registre hipóteses soltas, dados reais de clientes, documentos jurídicos, tokens, senhas ou informações processuais sigilosas.

## Como usar

Antes de iniciar uma correção, consulte este arquivo para evitar retrabalho e para identificar regressões. Ao confirmar um problema novo, registre a evidência antes de alterar código. Ao resolver, mantenha o histórico resumido.

## Classificação

- `crítico`: interrompe operação essencial, expõe dado jurídico, causa perda de dados, quebra autorização ou indisponibilidade.
- `alto`: afeta processo importante, RBAC, documentos, financeiro, IA jurídica, prazos ou integridade de dados.
- `médio`: afeta uso normal com contorno viável.
- `baixo`: falha localizada, cosmética ou melhoria técnica sem impacto operacional imediato.

## Status permitidos

- `identificado`
- `em investigação`
- `correção preparada`
- `aguardando validação`
- `resolvido`
- `monitoramento`
- `aceito temporariamente`

## Problemas ativos

Nenhum problema comprovado registrado neste arquivo ainda.

## Modelo de registro

```md
### EJC-000 - Título objetivo

## Identificação

- Código: EJC-000
- Sistema: EJC
- Módulo:
- Ambiente:
- Severidade:
- Status:
- Data da identificação:
- Commit ou PR relacionado:

## Evidência

- Sintoma:
- Forma de reprodução:
- Logs relevantes, sem secrets ou PII:
- Arquivos relacionados:
- Testes que demonstram a falha:

## Análise

- Causa confirmada ou hipótese:
- Impacto:
- Risco de regressão:
- Dependências:
- Soluções já tentadas:
- Motivo de tentativa malsucedida:

## Tratamento

- Correção adotada:
- Validações:
- Rollback:
- Pendências:
- Condição para encerramento:
```

## Histórico resumido

Sem problemas encerrados registrados neste arquivo ainda.


## Migration 171 — homologação do cutover de preliminares

- **Severidade:** médio; **status:** correção preparada.
- **Escopo:** persistência única de Raio-X/Sala (item 24 da limpeza de redundâncias).
- **Evidência:** upgrade do zero em PostgreSQL 16 + pgvector; testes fictícios de backfill, contratos legados, isolamento, privilégios, RLS, cascatas e rollback. Quatro achados da revisão independente foram reproduzidos e corrigidos com testes.
- **Bloqueio:** `scripts/check_migration_compatibility.py` exige revisão humana para o corpo dinâmico de `171_preliminares_cutover.py`. A migration não foi incluída como aprovada em `MIGRATION_REVIEW_MANIFEST.json`.
- **Decisão necessária:** homologar o conteúdo exato da migration e registrar seu SHA-256; nenhum deploy foi feito. O SQL não apaga tabelas de dados; seis espelhos preservam rollback e as interfaces antigas tornam-se views.
- **Rollback:** reverter código do adicional e executar downgrade da 171 para 170 pelo procedimento de release. Os dados escritos durante o cutover são mantidos nos espelhos. Reupgrade após alterações no legado exige equivalência/reconciliação, verificada antes do backfill.
