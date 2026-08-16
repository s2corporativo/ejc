# M08 — Superfície de API partes (16/08/2026)

## Endpoints existentes (router case_partes.py, prefix /cases/{case_id}/partes)
| Rota | Método | Obs |
|---|---|---|
| GET /cases/{case_id}/partes | list | gate verificar_acesso_caso; retorna list[dict] com ativo=true |
| POST /cases/{case_id}/partes | create 201 | ParteCreate: tipo, papel_processual, nome, cpf_cnpj, qualificacao, email, telefone, representante_legal, oab, client_id, observacoes; INSERT raw SQL + audit CREATE; SEM validação de duplicidade (mesmo CPF/CNPJ no caso) |
| DELETE /cases/{case_id}/partes/{parte_id} | 204 | UPDATE ativo=false SEM verificação de existência (update afeta 0 linhas = sucesso silencioso) → BUG a corrigir (M08 original criou) |
| PATCH /cases/{case_id}/partes/{parte_id} | NÃO EXISTE | M08 original criou — recriar |

## Correções M08 a implementar (como no original)
1. PATCH partes (edição de nome/cpf/papel/representante/oab/observacoes com auditoria UPDATE).
2. DELETE endurecido: 404 se parte inexistente/inativa (rowcount check).
3. Validação CPF/CNPJ no POST (validators_service.cpf_valido/cnpj_valido?).

## Tabela case_partes
id, case_id (not null), tipo varchar(30) not null, papel_processual, nome not null, cpf_cnpj varchar(18), qualificacao, email, telefone, representante_legal, oab varchar(20), client_id, ativo boolean default true, observacoes, created_at, updated_at, created_by. Sem unique constraint.

## Tipos aceitos (do app): verificar ParteTipo enum ou valores — grep "tipo" in case_partes migration/model.

## Recursos QA para M08
- Caso QA principal (M07 run 3): vários casos criados; usar GET /cases?area=tributario para pegar um id ativo. Cliente: 9e6cd7cd-148c-49c9-95cb-d61de37fe520.
- Admin: ejc_qa_auth_admin@golocal.ejc, advogado UUID 4701ecbf-cf9b-422f-b75a-b906814b8213, financeiro ejc_qa_auth_financeiro@golocal.ejc, cliente ejc_qa_auth_cliente@golocal.ejc. Todos senha EjcQa2026!SenhaForte.

## Padrão bateria
scripts/inventory/m07_casos_tests.py como referência (tokens memoizados, sleep(18), X-Forwarded-For 127.0.0.1, db() psql helper).
