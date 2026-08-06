# EJC — Prompt Mestre de Execução

**Companheiro operacional do `docs/PLANO_EXECUCAO_CONSOLIDADO.md`.** Aquele documento diz
*o que* fazer e em que ordem; este entrega os prompts prontos para colar numa sessão do
Claude Code, no mesmo formato do `plano-lancamento-v3.md`.

**Como usar:** uma sessão por item. Em toda sessão, cole primeiro o **Prompt Mestre** (Seção 1)
e, na sequência, o prompt do item da vez (Seções 2–5). Não execute dois itens na mesma sessão.

---

## 1. O PROMPT MESTRE — cole no início de TODA sessão

```
Você é o executor técnico do EJC. Antes de qualquer ação:

1. Leia CLAUDE.md por inteiro. Ele prevalece sobre o que você acha que sabe.
2. Leia docs/PLANO_EXECUCAO_CONSOLIDADO.md — é o mapa desta execução.
3. Verifique o estado real ANTES de agir (o plano é um retrato, o repositório é a verdade):
   - git log --oneline -20            (o que já entrou desde o plano)
   - cd backend && python -m alembic heads   (head real de migrations)
   - PRs e Issues abertos que tocam os mesmos arquivos do item da vez
4. Se o item da vez já foi executado por outro PR, NÃO refaça: registre no relatório
   e encerre.

REGRAS INEGOCIÁVEIS DESTA EXECUÇÃO:
- Uma Issue + um PR draft por item, com "Closes #NNN" no corpo (a trava governanca.yml
  reprova sem isso). Branch própria; nunca tocar a main.
- Migration nova só com head conferido e reserva em backend/alembic/MIGRATION_RESERVATIONS.md.
- Mudança em auth, RBAC, upload, portal ou config → rodar o agente security-auditor antes
  de finalizar.
- Toda correção entra com teste de regressão. Toda regra jurídica com fonte oficial e vigência.
- Jamais: push --force, reset --hard, rm -rf, downgrade de banco, deploy, acesso a produção,
  enfraquecer HITL / gate de citações / sanitização de PII / kill-switch.
- Em dúvida entre adicionar e remover: REMOVA.
- Achado fora do escopo não interrompe: termina o item, reporta o achado, vira Issue nova.

ENCERRAMENTO OBRIGATÓRIO de toda sessão: relatório com arquivos, comandos, testes
executados (números), evidências, riscos residuais e pontos que exigem decisão humana.
Merge e deploy são atos do titular — nunca seus.
```

---

## 2. TRILHA A — Convergir o que está aberto (semana 1)

### A1 — Reconciliar o merge train

```
Item A1 do plano consolidado. Referência: Issue #719 (P0).

Os PRs #703, #705, #706, #679 e #676 estão prontos ou quase, e há risco de conflito de
migrations entre eles e a main (head atual: conferir com alembic heads).

1. Para cada PR: estado do CI, arquivos tocados, migrations que carrega, conflitos com main.
2. Monte a ORDEM DE MERGE que minimiza rebases (migrations primeiro, depois quem depende).
3. Para cada PR fora de ordem ou conflitado: faça o rebase/merge da main NA BRANCH DO PR,
   renumere migrations se preciso (com reserva), e deixe o CI verde.
4. NÃO faça merge de nenhum PR — entregue ao titular a tabela: ordem, PR, o que contém,
   risco, e o comando/ato que ele executa.

Critério de aceite: todos os 5 PRs verdes, sem conflito entre si na ordem proposta,
head de migration único e documentado.
```

### A2 — Gate de release por SHA

```
Item A2. Referências: Issue #715 (P0) e PR #714.

Revise o PR #714 (gate bloqueante e runbook de certificação H01–H15) contra a Issue #715:
o que a Issue pede que o PR ainda não cobre? Complete NA BRANCH DO PR #714 (correção de
review vai no mesmo PR): vincular H01–H15, deploy, backup/restore e aprovações ao SHA
exato da release. Critério: o gate reprova release cujo SHA não tenha a certificação
completa registrada.
```

### A3 — Portal do Cliente: vazamento ético

```
Item A3. Referências: Issues #678 e #698. O plano v3 marca isto como exceção não
negociável e imediata (Código de Ética OAB, art. 6º, § único, e art. 34, XXIX).

1. Varra TODOS os endpoints /portal/* e serializers usados por eles: nenhum pode expor
   chance/estimativa de êxito, anotações internas, campos de estratégia ou metadados de
   IA. Prove com teste que percorre os schemas de resposta.
2. Publicação de documento no portal deve ser ato explícito (quem, quando, o quê) com
   trilha — não efeito colateral de classificação (Issue #698; a migration
   127_publicacao_explicita já existe: confirme se o fluxo a usa de fato).
3. Teste de regressão para cada campo bloqueado.
4. Rode o security-auditor ao final (é portal).
```

### A4 — Segurança sem PR: mass assignment e integridade de uploads

```
Item A4. Duas Issues, DOIS PRs separados.

PR 1 — Issue #695: o PATCH do Raio-X aceita revisao_humana.identificacao e escreve
qualquer atributo do model, contornando o congelamento por conversão. Corrija com
allowlist explícita de campos editáveis; teste de regressão provando que atributo fora
da lista é rejeitado e que o congelamento resiste.

PR 2 — Issue #697: ingestão de documentos sem hash de integridade nem varredura de
malware, proteção de comprovante restrita a peças. Implemente hash SHA-256 gravado na
ingestão + verificação, e varredura opt-in via flag de env (default OFF, degradação
graciosa — padrão do repo). Estenda a proteção de comprovante às demais classes.

Rode o security-auditor nos dois (upload e RBAC).
```

### A5 — Dependabot em lote

```
Item A5. PRs #656–#671 (14 PRs de dependência).

Ordem: axios, uvicorn e vite primeiro (superfície de rede), depois o resto.
Para cada um: CI verde? breaking changes no changelog que toquem código nosso?
(atenção: langfuse 2.x→4.x e jsdom 24→30 são saltos grandes — leia os changelogs).
Entregue ao titular a lista em três colunas: merge direto / merge com ajuste (dizer qual) /
adiar (dizer por quê). Ajustes necessários vão na branch do respectivo PR.
```

---

## 3. TRILHA B — Fechar os blocos de lançamento (semanas 2–3)

### B1 — Conferência runtime dos números (Bloco 1 do v3)

```
Item B1. Leia também docs/auditoria/relatorios/parte-13-homologacao-dinamica.md.

Suba a stack local (docker compose) e repita o roteiro da Parte 13 sobre a main
pós-merge-train: dashboard × listagem de casos × filtros (status=ativo, all, triagem)
× analytics. Todo número que divergir ou der 500 é bug a corrigir NESTA sessão, com
teste de regressão. Entregue a tabela ANTES/DEPOIS de cada contador.
NÃO zere métrica para bater com outra — a métrica reflete a realidade.
```

### B2 — Desobstruir até o PDF (Bloco 2 do v3)

```
Item B2. Leia docs/auditoria/plano-correcao-v2.md itens 2.1 e 2.4, e a Parte 13.

Achado central da Parte 13: POST /legal-docs/{id}/validar retorna 500 quando não há
provedor de IA configurado, e é isso que trava /aprovar. O bloqueio_sem_validacao já
existe em legal_docs.py — o problema agora é o 500.

1. /validar sem provedor deve degradar graciosamente (padrão do repo): resposta clara
   de indisponibilidade + caminho manual de conferência, nunca 500.
2. Consolide validar → aprovar → PDF em UM ato de conferência e assinatura.
3. Libere exportação de PDF desde a minuta; rótulo "minuta final — conferir e assinar".
4. PRESERVE quem conferiu, quando, sobre qual versão (Lei 8.906/94, art. 32).
5. Backfill dos registros existentes: dry-run com relatório antes de aplicar.

Critério de aceite: criar peça → conferir → assinar → PDF ponta a ponta na stack Docker,
COM e SEM provedor de IA configurado. Grave a evidência dos dois cenários.
```

### B3 — Entrada única (Bloco 3.1 do v3)

```
Item B3. Redesenho de produto: PROPONHA ANTES DE IMPLEMENTAR — o titular revisa o desenho.

Tela única de entrada: o advogado cola o relato OU arrasta documentos; o sistema devolve
confirmação com cliente identificado (ou cadastro pré-preenchido), área sugerida, fatos
estruturados, documentos classificados E vinculados, prazo detectado, próxima ação.
Um clique para confirmar → caso pronto.

Não construa IA nova: encadeie entrada-universal/processar, entrevista-inteligente,
sala-juridica e a triagem automática. Corrija de passagem a conversão sala-jurídica →
caso que perde descricao_fatos e evidências.

Entregue primeiro: wireframe/fluxo das telas + contrato das chamadas. Código só depois
do OK do titular.
```

### B4 — O caso como espaço de trabalho (Bloco 3.2 do v3)

```
Item B4. Redesenho de produto: proponha antes de implementar. CONVERGE com a Issue #716
(Onda 2 — próxima ação, responsável, saúde, timeline, Dashboard do caso): leia a Issue
e não duplique o que ela já especifica.

Dentro da tela do caso, sem sair dela: anexar/vincular documento, criar prazo,
redigir/conferir/exportar peça, lançar hora e despesa, registrar andamento.
Módulos de Prazos/Documentos/Peças viram visões transversais (relatórios), não estações
de trabalho. Navegação reorganizada pelo ciclo de vida do caso.
```

### B5 — Enxugar navegação e expor calculadoras (Bloco 4 do v3)

```
Item B5. Leia docs/auditoria/plano-correcao-v2.md, itens 5.1 e 6.5.

1. REMOVER DA NAVEGAÇÃO (código fica): Notícias (moduleRegistry.tsx:697).
2. REMOVER DE VERDADE, incluindo código: diplomacia-v3 — router (main.py:350 e
   app/routers/diplomacia_v3.py), service, testes, seeds e qualquer referência.
   Decisão do escritório registrada no v3: risco reputacional e disciplinar.
3. EXPOR as 15 calculadoras jurídicas prontas no backend sem tela (dosimetria,
   prescrição penal, verificar-anpp, dano moral, partilha-divórcio, alimentos,
   usucapião, prescrição-consumidor, prazos-contestação, juros-mora e outras —
   item 5.1 da v2). ANTES de construir UI: teste as 15 e relate o que cada uma
   exige e retorna. UI mínima: um formulário por calculadora, dentro do design system.

Confira que os LEGACY_REDIRECTS de jurimetria/victory-vault/sociedade continuam íntegros.
```

### B6 — Corte do catálogo de skills

```
Item B6. Pré-requisito: contador de uso implantado (migration 130_ejc_skills_uso, PR #688)
com JANELA DE TELEMETRIA de pelo menos 2 semanas de operação — confirme a idade dos dados
antes de cortar; se a janela for insuficiente, PARE e reporte.

Mantenha no catálogo as skills com uso registrado; ARQUIVE (não delete) o resto —
flag de arquivamento reversível. Corrija antes de arquivar: o erro de decadência
(CPC art. 487, II — Issue #554/PR #703) precisa estar corrigido em toda skill que
permanecer. Relate: quantas ficaram, quantas arquivadas, top-10 por uso.
```

### B7 — Prazos: monitorar resultado e diagnosticar ingestão (Bloco 5 do v3)

```
Item B7. Leia docs/auditoria/plano-correcao-v2.md itens 0.2, 3.1 e 3.2. A migration
125_fonte_ingestao_execucoes_zeradas já existe — construa sobre ela.

1. Alertas ativos por RESULTADO: fonte historicamente produtiva que zera; fonte que
   nunca produziu nada; N execuções consecutivas em zero. Alerta visível no sistema,
   não só log.
2. Diagnostique os importadores juris_import_* (dormentes, zero registros, marcados ativos).
3. Fonte anpd: ultimo_erro fica null — corrija a captura da exceção e diagnostique.
4. Parser do TJMG: registre contagem de itens brutos ANTES do parsing ("nada veio"
   ≠ "veio e não parseou").

DEPENDÊNCIA HUMANA: o teste fim-a-fim precisa das OABs cadastradas (item C1, do titular).
Se ainda não foi feito, valide com fixture e deixe o teste real documentado como pendente.
```

---

## 4. TRILHA C — Suporte técnico aos atos do titular (semana 3)

Os cadastros e limpezas de produção são atos humanos. O executor prepara o ferramental:

### C-scripts — Limpeza de produção e homologação segura

```
Itens C2, C3 e C4 do plano consolidado. Você NÃO acessa produção — prepara o ferramental
para o titular executar.

1. Script de DESATIVAÇÃO da conta homolog.qa + runbook de rotação de credenciais
   (a auditoria registrou senha de root do VPS idêntica à da aplicação). O script roda
   em dry-run por padrão e exige flag explícita para aplicar.
2. Script de LIMPEZA de dados fictícios: casos HOMOLOG-FICTICIO-*, 37 casos da lixeira,
   peças órfãs, contas de teste. Dry-run primeiro com relatório do que seria afetado;
   backup obrigatório antes (scripts/backup.sh) — escreva isso no runbook.
3. CÓDIGO: qa/e2e/run_fictitious_smoke.py e qa/homologacao/* devem RECUSAR execução
   contra a URL de produção (fail-closed, override explícito impossível por engano).
4. Runbook final em docs/: passo a passo dos itens C1–C6 para o titular, com checklist.
```

---

## 5. TRILHA D — Faxina profunda (PÓS-lançamento, uma tesourada por semana)

Só começa depois do Bloco 7 (primeiro caso real) aprovado. Uma sessão por fase:

### D1 — Frontend morto

```
Remova páginas alcançáveis apenas por LEGACY_REDIRECTS (confirme com o registry e com
busca de imports), componentes sem referência e estilos da paleta pré-shell-premium.
Rode knip (ou análise equivalente) para dependências npm sem uso. Critério: build e
testes verdes, bundle menor (relate a diferença), zero rota quebrada no teste de
integridade de rotas de src/config/.
```

### D2 — Limpeza mecânica

```
Código comentado, funções órfãs (vulture no backend; tsc + análise de imports no front),
arquivos temporários. Mova RELATORIO_*.md e PLANO_*.md históricos da raiz para
docs/historico/ ATUALIZANDO referências (a Issue #677 registra o precedente de quebrar
o CLAUDE.md — não repita). Remova testes de módulos já removidos. Ferramenta sugere,
você confere à mão — nada sai só porque a ferramenta disse.
```

### D3 — Flags e env

```
Das ~62 flags ENABLE_*/_ENABLED em config.py: remova as de features cortadas, documente
TODAS as vivas no .env.example. Para cada remoção, confira o que o boot de produção exige
(o boot FALHA com config inválida — é proposital). Entregue ao titular a lista de chaves
que ele deve remover do .env de produção via runbook.
```

### D4 — Endpoints sem uso

```
Cruze as 211 rotas órfãs (auditoria) com a telemetria route_usage_metrics (migration 122)
de PELO MENOS 2–4 semanas de operação real. Remova só o que tiver zero tráfego confirmado
E não pertencer a integração opt-in desligada por flag. Em lotes pequenos, um PR por
domínio, testes verdes a cada lote.
```

### D5 — Superfície dupla /api + /api/v1

```
É contrato público — NUNCA desligue de uma vez. Fase 1: escolha a superfície canônica,
logue todo acesso à outra (contador por rota). Fase 2 (após janela sem tráfego):
redirecione com aviso de depreciação. Fase 3: desligue. Corrija na mesma passada o
prefixo /v1/v1/ duplicado — comece pelo interceptor de src/lib/api.ts, não pelo baseURL
(ver CLAUDE.md, armadilhas confirmadas).
```

### D6 — Banco, por último

```
Tabelas/colunas candidatas a remoção: prove zero leitura/escrita (grep no código + logs +
telemetria), registre a prova na Issue. Backup antes (scripts/backup.sh). Migration de
drop escrita À MÃO — jamais autogenerate: ~30 tabelas raw-SQL enganam o Alembic e o
include_name() existe por isso. Rollback documentado. Uma tabela por PR.
```

---

## 6. Depois de cada sessão

O relatório final da sessão alimenta o `PLANO_EXECUCAO_CONSOLIDADO.md`: marque o item
como concluído (com nº do PR) na tabela de estado. Quando a Trilha A fechar, atualize a
seção "Estado verificado" inteira — o retrato de 2026-08-06 terá envelhecido.

---

*Companheiro do `docs/PLANO_EXECUCAO_CONSOLIDADO.md` (Issue #737). Formato herdado do
`docs/auditoria/plano-lancamento-v3.md`.*
