# Issue de consolidação dos PRs P0 e prompt de execução

Dois artefatos prontos para uso. O primeiro cria a Issue; o segundo é colado no Claude Code.

> **Estado em 2026-07-29.** `docs/MATRIZ_CONSOLIDACAO_P0.md` já existe e contém o
> levantamento humano de 2026-07-27 sobre os PRs 493–497. Este documento serve à
> **próxima** rodada de consolidação — ou à reexecução da atual sobre evidência nova.
> Por isso `scripts/governanca/levantamento-pr-p0.sh` grava em
> `docs/MATRIZ_CONSOLIDACAO_P0_GERADA.md` e recusa sobrescrever a matriz existente
> sem `--forcar`.

---

## 1. Criar a Issue

```bash
gh issue create \
  --title "EJC-P0-000 — Consolidar PRs P0 abertos antes de qualquer nova frente" \
  --label "P0-bloqueador" \
  --body-file docs/ISSUE_CONSOLIDACAO_P0.md
```

## 2. Corpo da Issue (`docs/ISSUE_CONSOLIDACAO_P0.md`)

```markdown
## Prioridade
P0 — bloqueador. Congela novas funcionalidades até o encerramento.

## Domínio
infra · database · security · jurídico

## Problema
Há múltiplos PRs draft abertos tratando bloqueadores P0 em áreas potencialmente
sobrepostas: regras jurídicas, fluxo, IA, autenticação/RBAC e infraestrutura.
Enquanto a sobreposição não estiver mapeada por evidência, qualquer integração
corre risco de: branches incompatíveis, migrations concorrentes, correções
mutuamente anuladas e regressão silenciosa.

## Escopo (lista fechada)
- Executar `scripts/governanca/levantamento-pr-p0.sh` e versionar a evidência coletada
- Preencher as seções 5 e 6 da matriz gerada com referência explícita ao diff de cada PR
- Produzir a ordem de integração fundamentada
- Consolidar a numeração de migrations em `backend/alembic/MIGRATION_RESERVATIONS.md`
- Registrar a recomendação por PR: MANTER · ABSORVER PARCIALMENTE · SUBSTITUIR · FECHAR

## Fora do escopo (explícito)
- Qualquer alteração de código funcional
- Qualquer merge
- Qualquer correção de defeito identificado durante a análise
- Fechamento de PR (decisão humana, executada por Clovis)
- Criação de branch de consolidação (etapa seguinte, Issue própria)

## Arquivos prováveis
- `docs/MATRIZ_CONSOLIDACAO_P0_GERADA.md`
- `evidencias/**`
- `backend/alembic/MIGRATION_RESERVATIONS.md`

## Riscos
| Tipo | Descrição |
|---|---|
| Técnico | Conclusão por inferência em vez de leitura do diff |
| Jurídico | PRs alterando regra normativa sem fonte oficial declarada |
| LGPD/Segurança | PRs tocando autenticação/RBAC com efeito combinado não avaliado |
| Regressão | Ordem de integração incorreta anulando correção anterior |

## Critérios de aceite
1. Seções 1 a 4 da matriz geradas a partir de saída real de comando, com a
   evidência bruta preservada em `evidencias/`
2. Seção 5 preenchida com **uma referência a linha ou arquivo do diff por
   célula**; célula sem referência permanece vazia
3. Toda sobreposição de arquivo entre PRs identificada e classificada como
   duplicação, complemento ou conflito
4. Toda migration listada com número, head anterior e dependência, conferida
   contra `backend/alembic/MIGRATION_RESERVATIONS.md` e contra o head vigente
5. Ordem de integração proposta com justificativa por posição
6. Nenhuma alteração em `backend/app/`, `frontend/src/`, `docker-compose.yml`
   ou migrations existentes
7. Regras jurídicas encontradas nos PRs listadas com dispositivo e fonte; sem
   fonte oficial, registradas como pendência bloqueante em `docs/REGRAS_JURIDICAS.md`
8. Relatório final com limitações e pontos de decisão humana

## Responsável pela execução
Claude Code — executor único. Nenhum outro agente edita estes arquivos durante a tarefa.
```

---

## 3. Prompt operacional para o Claude Code

Abrir em modo de planejamento primeiro:

```bash
claude --permission-mode plan
```

Colar:

```
Leia integralmente, nesta ordem:
- CLAUDE.md
- AGENTS.md
- docs/GOVERNANCA_IA.md
- docs/FLUXO_DE_DESENVOLVIMENTO.md
- docs/CRITERIOS_DE_ACEITE.md
- docs/MATRIZ_CONSOLIDACAO_P0.md (levantamento anterior — contexto, não conclusão)
- a Issue EJC-P0-000

Tarefa: consolidação analítica dos PRs P0 abertos. Somente leitura nesta etapa.

Antes de qualquer análise:
1. Confirme que a evidência em evidencias/ foi coletada e informe a data.
2. Liste os PRs efetivamente acessíveis e os inacessíveis.
3. Informe o head atual do Alembic em main (backend/alembic/versions).

Depois, para cada PR:
1. Leia evidencias/pr-<N>.diff integralmente.
2. Liste as correções que aquele PR implementa, uma por linha, com o arquivo
   e o trecho que a comprova.
3. Marque cada correção como EXCLUSIVA ou DUPLICADA, indicando o PR concorrente.
4. Identifique regras jurídicas alteradas: dispositivo, fonte declarada,
   vigência. Sem fonte oficial no PR, registre como pendência bloqueante.
5. Identifique alterações em autenticação, RBAC ou isolamento de tenant.
6. Liste migrations com número e head anterior.

Restrições absolutas:
- Não presuma que o PR de maior escopo substitui os demais. Escopo amplo não é prova.
- Não preencha nenhuma célula sem referência a arquivo ou trecho do diff.
- Não conclua "provavelmente", "aparentemente" ou "deve ser". Sem evidência,
  a célula fica vazia e a lacuna é reportada.
- Não altere código funcional. Não faça merge. Não feche PR.
- Não amplie escopo. Defeitos encontrados viram sugestão de Issue, não correção.

Entregue o plano de preenchimento da matriz e a lista de lacunas de evidência.
Não implemente nada nesta etapa.
```

Após revisar o plano, sair (`Ctrl+C`), reabrir em modo normal (`claude`) e autorizar
o preenchimento da matriz na branch própria:

```bash
git checkout main && git pull --ff-only
git checkout -b chore/consolidacao-p0
```

---

## 4. Encerramento

A Issue só é encerrada quando:

- [ ] Matriz preenchida com evidência em todas as células não vazias
- [ ] Ordem de integração fundamentada
- [ ] Migrations consolidadas em `backend/alembic/MIGRATION_RESERVATIONS.md`
- [ ] Recomendação por PR registrada
- [ ] Decisão de Clovis registrada na seção 7 da matriz
- [ ] PRs a fechar efetivamente fechados **por humano**, com justificativa no PR

Somente após o encerramento é autorizada a retomada de novas frentes.
