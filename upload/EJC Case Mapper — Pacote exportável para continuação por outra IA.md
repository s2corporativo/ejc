# EJC Case Mapper — Pacote exportável para continuação por outra IA

## Objetivo

Este pacote contém a implementação nativa do núcleo de inteligência jurídica verificável integrado ao EJC. Ele não copia código proprietário da MinutaIA; implementa uma arquitetura própria com funcionalidades equivalentes de organização documental, proveniência, grafo jurídico candidato, skills versionadas, execução auditável e revisão humana.

## Entregas desta versão

- Migration Alembic `174_case_mapper_skills`.
- ORM de `case_assertions`, `skill_versions` e `skill_run_links`.
- Serviço de evidências com hash de citação, idempotência e isolamento por caso.
- Serviço de grafo com nós/arestas candidatas e bloqueio de vínculos cruzados.
- Catálogo e seleção de skills aprovadas.
- Pipeline `case_mapper_v1` com inventário de documentos, extração determinística de trechos, fatos candidatos, evidências, afirmações e snapshot versionado.
- API FastAPI em `/api/cases/{case_id}/inteligencia-grafo`.
- Aba frontend `Inteligência verificável` no workspace do caso.
- Testes de contrato e revisão humana.

## Instalação local

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m alembic upgrade head
```

Configure, no mínimo, `DATABASE_URL`, `JWT_SECRET`, `VAULT_MASTER_KEYS` e as variáveis do gateway de IA. Para ativar o agente, habilite `AI_AGENT_ENABLED=true`. Sem essa flag, a API responde em modo degradado e não executa o agente.

### Frontend

```bash
cd frontend
npm ci
npm run lint
npm run build
```

## API principal

- `POST /api/cases/{case_id}/inteligencia-grafo/map`: inicia o mapeamento em modo somente leitura.
- `GET /api/cases/{case_id}/inteligencia-grafo/assertions`: lista afirmações pendentes.
- `GET /api/cases/{case_id}/inteligencia-grafo/graph`: lista nós e arestas do caso.
- `POST /api/cases/{case_id}/inteligencia-grafo/assertion/{id}/review`: revisão humana.
- `POST /api/cases/{case_id}/inteligencia-grafo/node/{id}/review`: revisão humana de nó.
- `POST /api/cases/{case_id}/inteligencia-grafo/edge/{id}/review`: revisão humana de aresta.

## Regras de segurança

1. O backend nunca confia em `case_id` ou `document_id` enviado pelo frontend sem validar ownership.
2. Um documento ou nó de outro caso é rejeitado antes da escrita.
3. A IA cria somente itens `candidato`, `pendente` e `is_draft=true`.
4. Confirmação exige fonte de evidência; a confirmação é restrita a advogado pelo backend.
5. O snapshot automático nasce descongelado e append-only.
6. O conteúdo de provider/modelo não armazena segredos.
7. Não executar migration em produção sem aplicar em staging e validar backup/rollback.

## Validação executada nesta sessão

```text
Alembic head: 174_case_mapper_skills
Backend: 31 testes aprovados nos gates de case mapper, head e reservations
Frontend: typecheck aprovado
Frontend: testes de CasoDetalhe aprovados
Frontend: build Vite aprovado
```

As dependências do ambiente de validação foram instaladas apenas no sandbox; o pacote não pressupõe que `node_modules` ou um ambiente Python já existam na máquina de destino.

## Limites conhecidos

- O pipeline inicial usa extração determinística de `ocr_text` como baseline verificável. O adaptador completo de chamada ao LLM deve ser conectado ao gateway existente em uma etapa posterior, mantendo o mesmo contrato de rascunho e citation gate.
- A migration foi validada estaticamente e via `alembic heads`; a execução `upgrade head` depende de um PostgreSQL acessível com o schema base e extensões do EJC.
- A aprovação de skills é deliberadamente manual. O seed cria versões `draft` e não as torna automaticamente aptas a orientar o agente.
- Todo conteúdo jurídico gerado por IA exige revisão humana antes de uso ou protocolo.
