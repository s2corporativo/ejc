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
| Infraestrutura | Docker, Docker Compose, Nginx e runner GitHub Actions próprio |

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
  deploy_vps_safe.sh    deploy rastreável com validações
docs/                   arquitetura, operação, segurança e homologação
.github/workflows/       CI, release gate, inventário e continuidade
```

## Fluxo obrigatório de mudança

1. Criar branch a partir da `main` atualizada.
2. Implementar uma alteração pequena e coesa.
3. Adicionar ou atualizar testes.
4. Abrir Pull Request usando o checklist do repositório.
5. Aguardar todos os workflows obrigatórios.
6. Revisar diff, riscos e rollback.
7. Integrar somente após os gates verdes.
8. Executar deploy pelo procedimento seguro e registrar evidências.

É proibido usar upload avulso de arquivos, edição direta na VPS ou reinício isolado de container como mecanismo normal de deploy. Essas ações quebram rastreabilidade e podem deixar código, migrations e frontend em versões incompatíveis.

## Gates automatizados

### CI

- Ruff;
- `pip-audit`;
- migrations em PostgreSQL real;
- suíte backend completa;
- Vitest;
- Prettier;
- `npm audit`;
- typecheck e build frontend;
- gold sets e trajetória do agente de IA.

### EJC Release Gate

- conflitos de merge;
- arquivos de credenciais;
- padrões inseguros de CORS;
- resíduos bloqueantes de desenvolvimento.

### Continuity and UI Gates

- dump PostgreSQL em formato custom;
- cifragem com o mesmo mecanismo Fernet do backup do EJC;
- remoção do dump claro antes da restauração;
- decifragem controlada;
- restauração em banco vazio temporário;
- validação de versão Alembic, quantidade de tabelas e marcador de integridade;
- ESLint;
- build e teste responsivo em Chromium real.

### Architecture Inventory — Phase 0

Gera o inventário atual de páginas, componentes, rotas, routers, endpoints, services, models, tabelas e famílias duplicadas. O artefato do workflow é a fonte atualizada para decisões de consolidação.

## Desenvolvimento local

Requisitos mínimos:

- Docker e Docker Compose;
- Python 3.11;
- Node.js 20;
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
npm run format:check
npm run lint:eslint
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
