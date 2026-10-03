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
- **Revisão adicional:** tipos do definer qualificados e `pg_temp` explícito por último; espelhos isolados ao executor confiável, com ACL original preservada para restauração; triggers/regras legados incompatíveis abortam; permissões de escrita verificadas; `TRUNCATE` rejeitado e downgrade exige equivalência completa. A conferência não executa views editáveis; ACL delegada conserva grantor/grant option e exige executor autorizado a assumir os papéis originais. Esta revisão muda o SHA da migration preparada; a aprovação humana continua pendente.

## Jornada — inteligência da Entrada Única não reconhecida pelo orquestrador

- **Severidade:** P1; **status:** diagnóstico confirmado, proposta de correção.
- **Evidência fictícia:** um único snapshot aprovado com origem `intake` resulta em `classificacao`; o mesmo snapshot com origem `entrada_unica` resulta em `entrada`, com `tem_snapshot=false` e `tem_snapshot_congelado=false`.
- **Causa:** `entrada_juridica_service.gerar_dossie_juridico` persiste a origem permitida `entrada_unica`, ausente de `_ORIGENS_CONTEUDO` em `legal_case_orchestrator`. O dossiê não é perdido; deixa de orientar a recomendação.
- **Recomendação:** harmonizar o contrato de origens, mantendo aprovação explícita e isolamento; criar regressão de Entrada → aprovação → recomendação do caso. A auditoria da jornada não alterou esse comportamento.

## Jornada — recomendação mistura ciclos históricos e trabalho atual

- **Severidade:** P2; **status:** decisão de produto pendente.
- **Evidência fictícia:** peça protocolada anterior + minuta nova resulta em `acompanhamento`, oferecendo `analisar_peca`; snapshot novo não aprovado + snapshot antigo aprovado mantém `classificacao`, embora `snapshot_atual_congelado=false`.
- **Causa:** derivação deliberada por artefato mais avançado e flags agregadas (`any`), sem selecionar ciclo/versão vigente.
- **Recomendação:** orientar a próxima ação pela peça/versão atual e pelos prazos urgentes, preservando o histórico e todos os gates. Os endpoints de aprovação permanecem protegidos; o diagnóstico não demonstra bypass desses gates.

## Jornada — erro de carga pode parecer ausência de dados

- **Severidade:** P1; **status:** diagnóstico estático, correção proposta.
- **Evidência:** `CasoDetalhe.tsx` silencia falhas de carga em `TabLista`, cujo estado inicial é vazio, e redireciona falhas de carregar o caso para a listagem. Não distingue indisponibilidade de ausência/permissão; a auditoria não simulou HTTP 5xx na interface.
- **Recomendação:** reaproveitar o padrão de erro/repetição do `OrquestradorPanel`, preservar o último dado com indicação de desatualização e distinguir ausência de falha. Essa mudança de comportamento não foi implementada na auditoria.
