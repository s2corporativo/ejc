# Fluxo de desenvolvimento do EJC

Ciclo obrigatório de qualquer alteração no repositório. Regras canônicas em
`docs/GOVERNANCA_IA.md`.

## Visão geral

```
Clovis define o resultado
  ↓
ChatGPT escreve a Issue (escopo, exclusões, critérios de aceite)
  ↓
Claude Code implementa em branch exclusiva, com testes
  ↓
PR draft vinculado à Issue
  ↓
ChatGPT revisa (técnico, segurança, jurídico, funcional, regressão)
  ↓
Claude Code corrige na mesma branch
  ↓
CI verde + homologação
  ↓
Autorização do titular → merge → deploy
```

## Etapa 1 — a Issue

Nenhum trabalho começa sem Issue. Ela contém:

- código único (ex.: `EJC-P0-014`) e título;
- problema e origem (auditoria, relato, incidente);
- prioridade (P0/P1/P2/P3) e domínio;
- arquivos prováveis;
- escopo e **fora do escopo** (explícito);
- critérios de aceite verificáveis;
- testes esperados;
- risco jurídico e risco LGPD;
- dependências (Issues e PRs);
- responsável.

Labels: `P0-bloqueador`, `P1-alto`, `P2-medio`, `P3-evolucao`, `backend`, `frontend`,
`database`, `security`, `lgpd`, `juridico`, `infra`, `ux`, `rag`, `ia`.

### Exemplo

```
EJC-P0-014 — Corrigir contagem de prazo trabalhista

Problema: a calculadora usa dias corridos.
Regra:    art. 775 da CLT — contagem em dias úteis.

Escopo:            service da calculadora; endpoint; componente frontend; testes.
Fora do escopo:    redesign da tela; outras calculadoras.

Critérios de aceite:
1. Contagem em dias úteis.
2. Exclusão do dia inicial, inclusão do dia final.
3. Tratamento de suspensão (inclusive recesso).
4. Fonte normativa e vigência exibidas no resultado.
5. Testes cobrindo fim de semana, feriado e suspensão.
6. Nenhuma regressão nas demais calculadoras.
```

## Etapa 2 — antes de tocar em código

1. `git checkout main && git pull --ff-only`
2. Listar PRs abertos e verificar sobreposição de arquivos:
   `git diff --name-only origin/main...origin/<branch-do-PR>`
3. Se a tarefa mexe em banco: conferir o head (`python -m alembic heads`) e reservar o
   número em `backend/alembic/MIGRATION_RESERVATIONS.md`.
4. Reproduzir o problema e registrar o diagnóstico na Issue.
5. Criar a branch: `git checkout -b fix/014-prazo-trabalhista`.

Se outro PR aberto já altera os mesmos arquivos, **a tarefa não começa**: ou espera o merge
do outro, ou o titular decide qual das duas frentes segue (`docs/GOVERNANCA_IA.md`, seção 5).

## Etapa 3 — implementação

- Somente o escopo da Issue. Achado fora do escopo vira Issue nova.
- Teste de regressão junto com a correção, no mesmo commit ou no seguinte.
- Regra jurídica com fonte, vigência, versão e aviso de revisão humana.
- Commits em português, descritivos, no formato `tipo(escopo): descrição`.

Validações locais mínimas:

```bash
cd backend  && pytest && ruff check app
cd frontend && npm run lint && npm test && npm run build
```

## Etapa 4 — Pull Request

- Sempre **draft**, sempre contra `main`, sempre vinculado à Issue (`Closes #NNN`).
- Corpo preenchido conforme `.github/pull_request_template.md` — inclusive migrations,
  impacto jurídico, impacto LGPD, riscos residuais e rollback.
- Evidências anexadas: saída de teste, capturas quando houver mudança de UI, logs de
  reprodução do 4xx/5xx corrigido.
- Nenhum merge pelo executor.

## Etapa 5 — revisão

O revisor aplica as cinco camadas de `docs/CRITERIOS_DE_ACEITE.md`: correção técnica,
segurança, validade jurídica, fluxo funcional e regressão. Os apontamentos ficam
registrados no PR — não em chat.

## Etapa 6 — correções

Na **mesma branch** e no **mesmo PR**. Nada de abrir um PR novo para corrigir o anterior.
Cada apontamento é respondido com o commit que o resolve ou com a justificativa técnica de
por que não se aplica.

## Etapa 7 — homologação

Mudança funcional é exercitada em ambiente separado (staging ou stack local com massa
fictícia), não em produção. Evidência anexada ao PR.

## Etapa 8 — merge

Só com todos os itens de `docs/RELEASE_CHECKLIST.md` atendidos e autorização expressa do
titular. Merge e deploy são atos humanos.

## Ambientes

```
/opt/ejc/
├── production/    produção — nenhum agente trabalha aqui
├── staging/       homologação
└── development/   trabalho do agente
```

O agente nunca opera no diretório de produção, contra o banco de produção nem com `.env`
real desnecessariamente disponível.
