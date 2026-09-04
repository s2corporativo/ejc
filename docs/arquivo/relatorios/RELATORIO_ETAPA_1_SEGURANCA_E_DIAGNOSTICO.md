# RELATORIO ETAPA 1 - SEGURANCA E DIAGNOSTICO INICIAL

Data: 2026-07-02  
Repositorio analisado: `C:\Users\User\EJC`  
Branch de trabalho criada: `audit-ejc-graphify-etapa1`  
Escopo: leitura tecnica, inventario, seguranca e preparacao. Nenhuma funcionalidade foi alterada nesta etapa.

## 1. Estado de preservacao

- Branch criada com sucesso a partir do estado local existente.
- Nao foram apagados arquivos.
- Nao foram movidos arquivos.
- Nao foi executada migracao, script SQL, comando de banco, deploy, build ou teste com potencial de alterar estado.
- O repositorio ja estava com alteracoes nao commitadas antes desta etapa. Elas foram preservadas sem revert, sem merge e sem limpeza.
- A troca de branch acionou automaticamente um hook local do Graphify com mensagem de rebuild em segundo plano. Nao houve intervencao manual nesse processo.

## 2. Stack identificada

### Backend

- Linguagem/runtime: Python 3.11, conforme `backend/Dockerfile`.
- Framework API: FastAPI `0.111.0`.
- Servidor ASGI: Uvicorn.
- ORM/banco: SQLAlchemy async `2.0.30`, asyncpg, PostgreSQL 16 via Docker.
- Migracoes: Alembic, com `backend/alembic.ini` e 55 arquivos em `backend/alembic/versions`.
- Validacao/configuracao: Pydantic v2 e pydantic-settings.
- Autenticacao/autorizacao: JWT com `python-jose`, PyJWT, passlib/bcrypt; middleware proprio `AuthMiddleware`.
- Seguranca/observabilidade: slowapi rate limit, Sentry opcional, sanitizacao e servicos de seguranca.
- Upload/documentos: PyMuPDF, pypdf, pdfplumber, python-docx, pandas, openpyxl, qrcode, Pillow, pytesseract.
- Testes/dev: pytest, pytest-asyncio, pytest-cov, ruff, pre-commit.

### Frontend

- Framework: React 18 + TypeScript.
- Build: Vite 5.
- Estilo: Tailwind CSS, PostCSS, CSS tematico proprio.
- Roteamento: react-router-dom.
- Estado/API: Zustand e Axios.
- UI: lucide-react, componentes proprios em `frontend/src/components`.
- Scripts principais: `npm run dev`, `npm run build`, `npm run lint`, `npm run format:check`.

### IA e RAG

- Provedores/configuracao: Groq, Ollama e Anthropic provider presentes em `backend/app/services/providers`.
- Gateway central: `backend/app/services/ai_gateway.py`.
- Servicos relacionados: `ai_service.py`, `case_intel.py`, `rag_juridico.py`, `embedding_service.py`, `embeddings_api.py`, `peca_service.py`.
- Dependencias: langchain, langchain-community, langchain-groq, fastembed, pgvector.
- Configuracao atual por codigo: `EMBEDDINGS_ENABLED=False` por padrao; provider AI em modo `auto`.

### Docker/deploy

- `docker-compose.yml` com servicos `db`, `backend` e `frontend`.
- Banco: `postgres:16-alpine`, volume `postgres_data`.
- Backend: build local `./backend`, env_file `.env`, volumes `uploads_data` e `backups_data`, healthcheck em `/health` interno.
- Frontend: build local `./frontend`, Nginx Alpine, porta `80:80`, proxy `/api/` para `backend:8000`.
- Scripts operacionais: `scripts/deploy.sh`, `backup.sh`, `restore.sh`, `post_deploy_check.sh`, `monitor_health.sh`, `deploy_vps_safe.sh`.
- Ferramentas VPS: `vps-tools/run.js`, `upload.js`, `sync.js`, `pull-file.js`, `ssh-config.js`, `tunnel.js`.

## 3. Estrutura geral de pastas

- `.github`: workflows/configuracoes de repositorio.
- `backend`: API FastAPI, modelos, schemas, routers, servicos, migracoes Alembic, seeds e testes.
- `frontend`: aplicacao React/Vite, paginas, componentes, estilos, assets publicos e Nginx.
- `scripts`: scripts de deploy, backup, restore, verificacao e auditorias SQL.
- `vps-tools`: ferramentas Node/PowerShell para acesso e sincronizacao com VPS.
- `deploy`: pasta de deploy atualmente sem arquivos na leitura inicial.
- `graphify-out`: saida gerada por ferramenta Graphify.
- `_QUARENTENA`: artefatos isolados/residuais e backups tecnicos.

## 4. Principais modulos existentes

### Backend

- Autenticacao e usuarios: `auth`, `users`, `auth_middleware`, `security`.
- Clientes/CRM/atendimentos: `clients`, `atendimentos`, `conversao_caso`, `crm` no frontend.
- Casos/processos: `cases`, `processes`, `case_partes`, `caso_areas`, `dossie_cliente`, `dossie_estrategico`.
- Prazos/tarefas/agenda: `deadlines`, `tasks`, `agenda_eventos`, `calendar_feed`, `suspensoes`, `intimacoes`.
- Documentos/pecas: `documents`, `documento_ia`, `legal_docs`, `peca_geracao`, `templates`, `signatures`.
- Financeiro/honorarios: `fees`, `honorarios_calc`, `financeiro_consolidado`, `despesas`, `partner_withdrawals`, `centro_custos`.
- Auditoria/governanca: `audit`, `qualidade`, `ia_governanca`, `ia_saude`, `audit_log`.
- IA/conhecimento: `ai`, `ai_tools`, `ai_skills`, `assistente`, `rag`, `teses`, `jurisprudencia_interna`, `jurisprudencia_externa`.
- Portal externo: `portal`, `mensagens`, paginas em `frontend/src/pages/portal`.

### Frontend

- 71 arquivos em `frontend/src/pages`.
- 44 arquivos em `frontend/src/components`.
- Rotas protegidas por token local, com restricoes basicas de perfil no frontend.
- Portal do cliente separado sob `/portal`.
- Sistema interno com rotas para dashboard, clientes, casos, prazos, documentos, pecas, financeiro, IA, auditoria, usuarios e demais modulos.

## 5. Arquivos sensiveis detectados sem exposicao de conteudo

Arquivos reais ou potencialmente sensiveis:

- `vps-tools/.env`: arquivo real de ambiente detectado. Conteudo nao foi lido nem impresso. Esta coberto por `.gitignore`.
- Possiveis `.env` de raiz/backend/frontend: nao encontrados como arquivos existentes nesta leitura, mas estao cobertos por `.gitignore`.
- `vps-tools/set-vps-password.ps1`: script operacional relacionado a senha de VPS; conteudo nao foi exposto no relatorio.
- Arquivos `.sql` em `scripts/audit_2026-07-01`, `backend/scripts` e `vps-tools`: potencialmente alteram banco; nao foram executados.
- Artefatos `.tgz` em `deploy_fases_1-3.tgz`, `vps-tools/_prod_src.tgz` e `_QUARENTENA/ejc_frontend_current.tgz`: podem conter snapshots de codigo/configuracao; nao foram abertos.

Arquivos de exemplo/configuracao:

- `.env.example` e `vps-tools/.env.example` existem e devem permanecer sem valores reais.
- `backend/app/core/config.py` referencia variaveis sensiveis por nome, mas usa ambiente para valores reais.

Resultado da checagem Git:

- `vps-tools/.env` esta ignorado por `.gitignore`.
- `.env`, `backend/.env` e `frontend/.env` tambem estao cobertos por regra de ignore.
- Arquivos rastreados com nomes de senha/token parecem ser telas/modelos/scripts funcionais, nao arquivos de segredo.

## 6. Riscos imediatos

- Worktree ja estava sujo antes desta etapa, com alteracoes em backend, frontend, testes, relatorios e migracao nova. Antes de qualquer correcao futura, separar o que e alteracao pretendida do que e residuo.
- Existe arquivo real `vps-tools/.env`; deve continuar fora de commits e fora de qualquer relatorio.
- Existem scripts SQL e scripts de restore/backup; qualquer execucao exige aprovacao explicita e backup validado.
- O sistema ainda contem referencias de licitacao em backend/frontend (`licitacao_auditoria`, `GuiaLicitacoes`, rota `/licitacao-auditoria`). Se o MVP atual deve remover licitacoes, isso e risco de escopo para etapa posterior, nao correcao desta etapa.
- Configuracao de producao depende de `.env` real com `SECRET_KEY`, `FRONTEND_URL`, credenciais Postgres e chaves de integracao. Ausencia/placeholder pode impedir subida em producao.
- Muitos routers e paginas indicam superficie grande de regressao. Correcoes futuras devem ser pequenas, verificadas e com testes direcionados.
- Relatorios anteriores e arquivos de auditoria podem conter referencias operacionais; revisar antes de publicar ou commitar.

## 7. Comandos seguros recomendados

Leitura e inventario:

```powershell
git -C C:\Users\User\EJC status --short --branch
git -C C:\Users\User\EJC diff --name-only
rg --files C:\Users\User\EJC
Get-ChildItem C:\Users\User\EJC -Force
```

Verificacao sem expor segredo:

```powershell
git -C C:\Users\User\EJC check-ignore -v -- vps-tools/.env .env backend/.env frontend/.env
rg --hidden -l -i --glob '!frontend/node_modules/**' --glob '!vps-tools/node_modules/**' --glob '!backend/.venv*/**' --glob '!.git/**' "(api[_-]?key|secret|token|password|senha|credential|bearer|jwt)" C:\Users\User\EJC
```

Preparacao para etapa futura, sem alterar banco:

```powershell
cd C:\Users\User\EJC\frontend
npm run lint

cd C:\Users\User\EJC\backend
python -m pytest --collect-only
```

Comandos que exigem aprovacao antes de rodar:

```powershell
docker compose up -d
docker compose down
alembic upgrade head
python backend/seeds/seed_all.py
bash scripts/restore.sh
qualquer script .sql
```

## 8. Pendencias antes de avancar

- Confirmar se a base de trabalho para correcao deve ser a branch atual `audit-ejc-graphify-etapa1` com as alteracoes ja existentes, ou se sera necessario abrir uma branch limpa a partir de `main`.
- Decidir o tratamento dos arquivos ja modificados antes desta etapa: manter, revisar por lote ou separar em commits por tema.
- Validar se os artefatos `.tgz`, `_QUARENTENA` e relatorios antigos devem ficar fora do proximo commit.
- Confirmar politica do modulo de licitacao: manter como area juridica/administrativa ou remover do MVP.
- Confirmar se testes/build devem ser executados na Etapa 2 e em qual ordem.
- Antes de qualquer deploy ou migracao, criar backup verificavel do banco e dos uploads.

## 9. Recomendacao tecnica para a proxima etapa

Avancar para uma Etapa 2 de auditoria sem alteracao funcional, focada em:

1. Congelar inventario do Git: listar todos os arquivos alterados e classificar por origem/risco.
2. Rodar verificacoes locais nao destrutivas: TypeScript `tsc --noEmit`, coleta pytest e import-check do FastAPI.
3. Mapear divergencias de rotas: frontend `App.tsx` versus routers registrados em `backend/app/main.py`.
4. Mapear exposicao de licitacao e decidir correcao posterior.
5. Somente depois abrir uma etapa de correcoes pequenas, com commit por bloco e validacao apos cada bloco.

## 10. Criterio de aceite

- Branch criada: atendido (`audit-ejc-graphify-etapa1`).
- Sistema preservado: atendido; nenhuma exclusao, movimentacao em massa, migracao, deploy ou refatoracao.
- Nenhum arquivo funcional alterado nesta etapa: atendido pelo escopo; foi criado apenas este relatorio.
- Relatorio inicial entregue: atendido.
- Riscos iniciais documentados: atendido.
