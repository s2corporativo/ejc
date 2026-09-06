# EJC — Ecossistema Jurídico Clovis

Sistema privado de gestão jurídica, produção assistida por IA e operação de escritório.

## Estado do produto

O EJC possui base técnica funcional e cobertura automatizada ampla, mas a certificação **10/10** depende do cumprimento integral do gate oficial, incluindo governança administrativa, continuidade comprovada e homologação operacional humana.

Fontes canônicas:

- `docs/EJC_10_10_ACCEPTANCE_GATE.md` — critérios oficiais de certificação;
- `docs/EJC_ROTEIRO_HOMOLOGACAO_FINAL.md` — cenários de homologação;
- `docs/audit/INVENTARIO_ARQUITETURAL_FASE_0.md` — inventário gerado do código;
- `docs/arquivo/relatorios/RELATORIO_ESTADO_PRODUTO.md` — estado funcional consolidado;
- `docs/BACKUP_RESTORE_RUNBOOK.md` — continuidade, backup e restauração;
- `docs/GOVERNANCA_IA.md` — governança dos agentes de IA (papéis, limites, fluxo e merge).

Não mantenha contagens manuais de routers, services, páginas ou tabelas neste README. Esses números mudam com frequência e devem ser obtidos pelo workflow **Architecture Inventory — Phase 0**.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | FastAPI, Python 3.11 e SQLAlchemy assíncrono |
| Frontend | React, TypeScript, Vite e Tailwind CSS |
| Banco | PostgreSQL 16, pgvector, pg_trgm e pgcrypto |
| Migrações | Alembic |
| IA/RAG | provedores configuráveis, embeddings locais e reranking |
| Armazenamento | filesystem controlado e integrações externas configuráveis |
| Infraestrutura | Docker, Docker Compose, Nginx no host; CI Woodpecker self-hosted (`.woodpecker.yml`) e deploy por gate host-level (`infra/host-automation/`) |

## Estrutura principal

```text
backend/
  app/                  aplicação FastAPI
  alembic/              migrações versionadas
  tests/                testes unitários, integração e banco real
frontend/
  src/                  aplicação React/TypeScript
  tests/                testes de navegador e responsividade
scripts/
  backup/               ativação, diagnóstico e restore drill
  deploy_manual.sh      deploy manual com as mesmas travas da esteira
  deploy_vps_safe.sh    transação de deploy (nunca chamar direto — ver RUNBOOK_DEPLOY_MANUAL.md)
infra/
  host-automation/      gate Woodpecker + deploy automático por timer systemd
  woodpecker/           CI self-hosted
  monitoring/           Uptime Kuma
docs/                   arquitetura, operação, segurança e homologação
docs/arquivo/           histórico (workflows do Actions aposentados, scripts legados)
```

## Fluxo obrigatório de mudança

1. Criar branch a partir da `main` atualizada.
2. Implementar uma alteração pequena e coesa.
3. Adicionar ou atualizar testes.
4. Abrir Pull Request usando o checklist do repositório.
5. Rodar localmente os portões proporcionais ao diff (`CLAUDE.md` §Verificação) e
   registrar a evidência no corpo do PR; o `ci/woodpecker` roda em paralelo.
6. Revisar diff, riscos e rollback.
7. Integrar somente com evidência completa e Woodpecker verde no HEAD exato.
8. Deploy pela esteira (`infra/host-automation`, automático quando `push/main`
   está verde) ou por `scripts/deploy_manual.sh` (`RUNBOOK_DEPLOY_MANUAL.md`).

É proibido usar upload avulso de arquivos, edição direta na VPS ou reinício isolado de container como mecanismo normal de deploy. Essas ações quebram rastreabilidade e podem deixar código, migrations e frontend em versões incompatíveis.

## Gates automatizados

O GitHub Actions foi aposentado em 2026-08-31 (histórico em `docs/arquivo/ci/`).
O CI oficial é o Woodpecker self-hosted, definido em `.woodpecker.yml`:

- **backend**: Ruff, `compileall`, `alembic heads` + `upgrade head` em
  PostgreSQL 16 + pgvector real, suíte pytest completa com `RUN_DB_TESTS=1`;
- **frontend**: `npm run lint` (tsc + ESLint), Vitest, build Vite;
- **ops-contracts**: sintaxe dos scripts de deploy/backup e testes de shell
  (`scripts/tests/`, `infra/host-automation/tests/`);
- **security**: Semgrep (bloqueante), Trivy vulnerabilidades (bloqueante),
  Trivy misconfig (informativo), Gitleaks (bloqueante).

O inventário arquitetural é gerado sob demanda por
`scripts/generate_architecture_inventory.py` (ver `docs/audit/`).

## Desenvolvimento local

Requisitos mínimos:

- Docker e Docker Compose;
- Python 3.11;
- Node.js 22.22 ou superior (mesma versão do `frontend/Dockerfile`);
- PostgreSQL 16 com pgvector, quando executado fora do Compose.

As configurações devem vir de arquivo `.env` local não versionado. Nunca copie credenciais reais para documentação, issues, commits, logs ou fixtures.

Comandos de verificação usuais:

```bash
# Backend
cd backend
python -m ruff check app
python -m alembic upgrade head
RUN_DB_TESTS=1 python -m pytest tests -q

# Frontend
cd frontend
npm ci
npm run lint          # tsc + ESLint
npm run test
npm run build
```

## Continuidade

O backup de produção deve conter banco e uploads cifrados antes do envio ao armazenamento externo. A chave de criptografia precisa existir também fora da VPS; perder a chave torna os backups irrecuperáveis.

A prova automática de CI demonstra que o formato e o processo de restauração funcionam em ambiente efêmero. Ela não substitui a prova periódica com um artefato real baixado do armazenamento externo, porque essa etapa depende das credenciais e permissões efetivas de produção.

## Segurança

- nunca versionar `.env`, tokens, chaves privadas ou service accounts;
- nunca registrar PII real em testes ou issues;
- aplicar ownership, RBAC e ABAC em listagens, detalhes e mutações;
- responder com `404` quando necessário para evitar enumeração de recursos;
- tratar links públicos como credenciais revogáveis e auditáveis;
- não executar alteração destrutiva sem backup verificável e rollback;
- não declarar o sistema certificado enquanto houver item obrigatório pendente no acceptance gate.

## Produção

Domínio oficial e detalhes da VPS devem ser configurados por variáveis e documentação operacional restrita. O repositório não deve conter IP, senha, instance ID, chave SSH ou comando com segredo embutido.

Para diagnóstico, use os endpoints de saúde, os logs dos containers e os artefatos dos workflows. Toda intervenção relevante deve deixar registro no GitHub ou no log de auditoria do EJC.
