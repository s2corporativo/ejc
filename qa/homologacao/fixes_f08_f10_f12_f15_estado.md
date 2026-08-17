# Estado — Correções F-08, F-10, F-12, F-15 (16/08/2026)

## Implementadas (Fase 1 concluída)

**F-08** — `backend/app/services/entrada_service.py`: import `CaseParte` adicionado (l.39); após `db.add(case)` no `criar_caso_do_rascunho`, criado registro estruturado `tipo="reu"` com `parte_contraria` (se não vazia) + registro `tipo="autor"` vinculado ao client_id (se client existe). Mesma transação, observações marcadas "Cadastrada automaticamente pela Entrada Única.".

**F-10** — `backend/app/routers/movimentos.py`: SELECT agora retorna também `m.created_at AS created_at` e `m.data_evento AS data_evento` (mantido `quando`). Frontend `DashboardUltra.tsx` lê `data_movimento || created_at || data` → agora casa com `created_at`.

**F-12** — `backend/app/routers/cases.py`: mensagens 422 substituídas por texto de negócio ("O arquivamento de caso possui fluxo próprio… Use a ação 'Arquivar caso' na ficha do caso." / encerramento análogo). Comentário F-12 no código.

**F-15** — `backend/app/schemas/client.py`: `model_serializer(mode="wrap")` em `ClientResponse` adiciona campo `documento_exibicao` = `mascarar_documento` (CPF `***.456.789-**`, CNPJ `**.345.678/****-**`). Verificado via teste local: dump OK para CPF, CNPJ e vazio. Frontend `Clientes.tsx` l.219 agora: `{c.documento_exibicao || c.cpf || c.cnpj || "—"}`. Nota: `documento_exibicao` também é adicionado na ficha individual (mesmo schema); mantive cpf/cnpj em claro no payload p/ consumidores internos; listagem visual usa o mascarado.

## Fase 2 — Testes pendentes
- Reiniciar uvicorn se necessário (as mudanças são de código interpretado; restart recomendado).
- F-08: criar rascunho via /api/entrada/analisar (IA off → texto 40+ chars) e depois /api/entrada/{id}/criar-caso com advogado QA (token ejc_qa_auth_advogado@golocal.ejc, role advogado, senha EjcQa2026!SenhaForte) e verificar case_partes criado (SQL: SELECT * FROM case_partes WHERE case_id=?).
- F-10: GET /api/movimentos/recentes com token e conferir campos created_at/data_evento no JSON.
- F-12: PATCH /api/cases/{case_id} com {"status":"arquivado"} e conferir 422 com texto de negócio (usar token advogado, caso QA c02afca9-af79-4fd8-a4e3-da80d4a23971).
- F-15: GET /api/clients/ com token socio/advogado e conferir "documento_exibicao" mascarado no JSON.

## Fase 3
- Commit: `git add -A && git commit -m "Correções auditoria F-08/F-10/F-12/F-15 (entrada única partes estruturadas, timeline data, mensagem arquivar, máscara CPF listagem)"`
- Relatório: registrar em PARECER/NOTAS; entregar ao usuário com provas.

## Dados de teste
- Usuários QA: senha EjcQa2026!SenhaForte; advogado ejc_qa_auth_advogado@golocal.ejc (role advogado).
- Caso QA M34/M36 usado antes: c02afca9-af79-4fd8-a4e3-da80d4a23971 (verificar acesso advogado).
- Servidor: uvicorn porta 8000, roda com `./scripts/inventory/env_shell.sh`.

## Provas de execução (Fase 2)

F-10 PROVED — GET /api/movimentos/recentes com token socio retornou campos `created_at` e `data_evento` (além do `quando`) em todos os registros (e.g. "2026-08-16T18:44:11.818394+00:00"). Frontend lê data_movimento || created_at || data → casa com created_at.

F-15 PROVED — GET /api/clients?limit=2 retornou "documento_exibicao" mascarado em TODOS os registros com documento: CPF 12345678909 → "***.456.789-**"; CNPJ 12345678000195 → "**.345.678/****-**"; 22334496004674 → "**.334.496/****-**"; 90688272002 → "***.882.720-**". Campos cpf/cnpj continuam no payload (consumidores internos); frontend listagem usa documento_exibicao.

F-12 — pendente: PATCH /api/cases/{case_id} status arquivado → esperar 422 "O arquivamento de caso possui fluxo próprio…"

F-08 — pendente: criar caso via Entrada Única com advogado QA e conferir case_partes (tipo reu/autor).
