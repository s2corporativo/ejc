# Triagem de PRs legadas — consolidação EJC — 02/09/2026

Baseline: `main@802c8edd39dd30fc18a4396b6013ff3317fd0e15`.

## Critério

Uma PR antiga só pode ser encerrada automaticamente por absorção quando `ahead_by=0` em comparação com a `main`, ou quando existe sucessor explícito confirmado e a PR antiga já está fechada/sem função exclusiva. PR divergente com commits exclusivos não é apagada: deve ser reconstruída sobre a `main` atual, incorporada seletivamente por uma frente canônica ou arquivada por decisão explícita.

## Sucessões já saneadas

| PR antiga | Estado | Sucessor/canônico |
|---:|---|---|
| #1292 | fechada sem merge | #1306 |
| #1293 | fechada sem merge | #1307 / novas frentes RAG |
| #1355 | fechada sem merge | #1376 |
| #1373 | fechada sem merge | #1376 |
| #1370 | fechada sem merge | #1380 |
| #1372 | fechada sem merge | #1380 |
| #1364 | fechada sem merge | #1378 |

Nenhuma ação adicional nesses PRs.

## PRs antigas ainda abertas com commits exclusivos

### #1307 — RAG normativo fail-closed

Comparação com `main`: `ahead_by=5`, `behind_by=26`.

Arquivos exclusivos incluem `reranker.py`, `citation_check.py`, `knowledge_governance.py`, contrato administrativo e testes. Não mesclar a branch antiga diretamente. Reconciliar semanticamente com #1382/#1383 e fechar #1307 somente quando a cobertura equivalente estiver provada no código atual.

### #1306 — coletor de fontes/gold

Comparação: `ahead_by=5`, `behind_by=26`.

Mudanças exclusivas no coletor e testes. Não pertence à mesma finalidade da #1386 (atestação externa do gold set). Rebase/reconstrução própria ou incorporação seletiva após restaurar CI.

### #1284 — auditoria global multirrepositório

Comparação: `ahead_by=14`, `behind_by=40`; conteúdo predominantemente documental (`docs/auditoria-global/*`).

Não afeta runtime, mas ainda não está contida na `main`. Decidir depois da consolidação se o material histórico deve ser arquivado em `docs/arquivo` ou incorporado ao acervo de auditoria; não misturar com release funcional.

### #1283 — calculadoras jurídicas

Comparação: `ahead_by=2`, `behind_by=67`.

Possui implementação exclusiva de `CalculadorasJuridicas` e configuração declarativa. Não mesclar cru. Revalidar contra `Ferramentas.tsx` e routers atuais; se o produto ainda for desejado, reconstruir em PR nova baseada no SHA consolidado.

### #1252 — piloto de jurisprudência TJMG

Comparação: `ahead_by=1`, `behind_by=134`.

Seed/documentação exclusivos. Por envolver corpus jurídico e RAG, não transportar automaticamente: revisar fontes, quarentena, governança atual e compatibilidade com #1382/#1383/#1386 antes de reconstruir.

### #1249 — toolkit de acesso VPS

Comparação: `ahead_by=1`, `behind_by=134`.

Contém runbook e suporte a chave/rotação de senha. Não usar a branch antiga diretamente no incidente #1295. A recuperação Woodpecker deve seguir o runbook canônico já mesclado pela #1296 e a Issue #1295. Avaliar depois quais hardenings de `vps-tools` ainda agregam valor sem criar rota operacional paralela.

### #1242 — fontes jurídicas P0

Comparação: `ahead_by=1`, `behind_by=135`.

Inclui novas fontes Planalto e documentação. Antes de reaplicar, confirmar se as fontes já não entraram por outra frente e submeter ao contrato atual de governança/vigência; não fazer ingestão persistente sem HITL.

### #1327 — alertas jurisprudenciais estáticos no Dashboard

Comparação: `ahead_by=3`, `behind_by=10`.

Funcionalidade exclusiva, mas o próprio PR descreve os dados como bootstrap estático a ser substituído por Radar canônico. Antes de mergear, preferir fonte dinâmica/rastreável do Radar. Não colocar snapshot jurisprudencial estático como verdade operacional sem rotina de atualização.

### #1325 — infraestrutura self-hosted CI/CD

Comparação: `ahead_by=31`, `behind_by=21`.

Altera `.woodpecker.yml` e adiciona deploy host-level, Renovate e Uptime Kuma. **Conflita conceitualmente e em arquivo com #1367**, que também altera `.woodpecker.yml` e política de gates. Não mesclar nenhuma das duas cru enquanto #1295 estiver aberto. Após recuperação do CI:

1. comparar #1325, #1367 e a `.woodpecker.yml` da `main` resultante;
2. construir uma única PR de infraestrutura a partir da `main` atual;
3. preservar fail-fast, segurança, deploy por SHA e ausência de GitHub Actions;
4. validar no runner real antes de ativar timer/deploy.

### #1367 — política de entrega rápida/fast gate

Comparação: `ahead_by=3`, `behind_by=2`; Woodpecker `failure`.

A política é compatível com o trem #909, mas precisa ser rebaseada e reconciliada com #1325. Não alterar a esteira antes de o executor voltar a executar.

## PR temporária

### #1374 — validação isolada de Atividades

O próprio PR declara: **não mesclar, não publicar, fechar após a validação**. Como o Woodpecker continua indisponível/vermelho, o propósito ainda não foi cumprido. Manter draft até a recuperação; executar o teste e então encerrar sem merge.

## Regra de limpeza após CI

Para cada PR antiga restante:

1. reexecutar `compare main...head`;
2. se `ahead_by=0`, fechar como absorvida;
3. se houver commits exclusivos, classificar por domínio e comparar com a frente canônica atual;
4. reconstruir em branch nova sobre a `main` consolidada somente o delta ainda útil;
5. fechar a branch histórica como supersedida depois que a nova PR preservar testes/rastreabilidade;
6. não carregar documentos, seeds ou integrações antigas por simples cherry-pick sem revalidar contratos atuais.

## Resultado

Não foi encontrada, no recorte comparado, PR antiga aberta que pudesse ser encerrada automaticamente por estar integralmente contida na `main`. A limpeza correta é **consolidação seletiva**, não fechamento em massa.