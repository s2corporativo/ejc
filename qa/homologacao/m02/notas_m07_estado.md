# M07 — Estado atual (16/08/2026)

## Contexto de recuperação
Sandbox resetou; ambiente reconstruído (Postgres+pgvector, Redis, repo recloneado em branch homologacao-m07-2026-08-16 baseada em origin/homologacao-m06). Backend porta 8000 rodando, migrations até 145 (consolidadas), 7 usuários QA seedados (senha EjcQa2026!SenhaForte), cliente QA 9e6cd7cd-148c-49c9-95cb-d61de37fe520, cliente_externo linkado (client_id). M06 re-executado: 23/24 (1 FAIL de portal corrigido manualmente — cliente ganhou client_id no banco).

## M07 bateria (scripts/inventory/m07_casos_tests.py): 33/34 PASS
Última falha: "duplicidade CNJ rejeitada (409)". Causa real: o caso criado no teste 1 nasce SEM numero_processo (coloquei None para evitar gerar 2 CNJs distintos). O teste 18 cria um caso NOVO com numero_processo=valido — não há conflito porque o caso original não tem CNJ.
### Correção pendente (próximo passo)
Na seção "edição" (após `valido = cnj_valido()`, linha ~94), adicionar PATCH do numero_processo=valido para o caso criado:
```python
    if caso:
        r = S.patch(f"{BASE}/api/cases/{caso}", headers=adm,
                    json={"numero_processo": valido}, timeout=15)
        chk("numero CNJ preenchido na edição", r.status_code == 200, f"HTTP {r.status_code}")
```
Isso preenche o CNJ do caso e o teste 18 passa (guard idempotência = 409).
Também atualizar o chk anti-phantom não precisa de CNJ.

## Detalhes de API aprendidos (M07)
- POST /api/cases exige proxima_acao para casos abertos (G1, caso contrário 422).
- DELETE /api/cases/{id} exige motivo (query ?motivo= ou body {"motivo":...} >=5 chars), 422 sem motivo; 403 para roles fora [admin, socio].
- Arquivar/desarquivar: status muda para CaseStatus.arquivado (sem coluna arquivado_em); GET lista aceita arquivo=ativos|arquivados|todos.
- Status enum: aberto, em_instrucao, em_producao, protocolado, encerrado, arquivado. Fase: pre_processual, conhecimento, recursal, execucao, administrativo. Prioridade: baixa/media/alta/critica.
- Movimentos: POST /cases/{id}/movimentos 201; GET retorna LISTA pura (não {"data":...}).
- GET /cases lista aceita: page, page_size, status (alias), arquivo, advogado, q (busca texto), area NÃO — filtro por área funciona via campo query (teste PASS com area=tributario — existe?). Sim PASS.
- RBAC: POST/GET cases = ["superadmin","admin","socio","advogado","advogado_auxiliar","secretaria"]. financeiro → 403/404.
- Carteira: obter_cliente_autorizado no create; fora da carteira → 404 (single) / 403 (lista).
- Duplicidade CNJ: guard ativo (409) com pg_advisory_xact_lock.
- CNJ válido: gerador módulo 97 (Res CNJ 65/2008): DV = (1 - int(N+AAAA+J+TR+OOOO+00)) % 97.
- Stats: GET /cases/stats 200. Kanban: GET /cases/kanban 200 (rota própria).

## Plano pós-M07
1. Corrigir teste 18 (PATCH numero_processo) → commitar m07.
2. M08 (partes): POST /cases/{id}/partes (autor/réu/terceiro/litisconsorte/representante/advogado/procurador, PF/PJ, vínculo), edição, remoção, duplicidade, integridade. Criar PATCH /cases/{id}/partes/{parte_id} se não existir (foi criação M08). Baterias m08_partes_tests.py.
3. M09 (procurações): /procuracoes GET/POST/POST {id}/minuta/POST {id}/revogar. Baterias m09.
4. M10 (documentos): routers/documents.py — upload/download/preview/metadados/tamanho/MIME/extensões/storage/autorização/isolamento/exclusão/restauração + ataques (extensão dupla, MIME falso, SVG/HTML, executável, >50MB, path traversal). Verificar UPLOAD_DIR no .env local (/home/ubuntu/ejc_repo/data/uploads), MAX_UPLOAD_MB=50.
5. M11: reexecutar m11_versionamento_tests.py (46/46) — pode precisar criar cliente+caso QA dedicados.
6. Commitar cada módulo em sua branch (m07, m08, m09, m10, m11) + m02 (correção consolidada). Push todas (GH_TOKEN OK).
7. M12 Andamentos: prompts no arquivo /home/ubuntu/upload/Pasted_content_76.txt linhas ~412+.
8. Relatórios: criar RELATORIO_MODULO_XX em qa/homologacao/mXX/ e matriz_homologacao.json.

## Comandos úteis
- Env: /home/ubuntu/ejc_repo/scripts/inventory/env_shell.sh <cmd>
- Alembic (fora de backend/): env_shell.sh alembic -c backend/alembic.ini <cmd>
- DB: PGPASSWORD=ejc psql -h localhost -U ejc -d ejc -t -A -c "..."
- uvicorn: cd backend && nohup env_shell.sh uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
- Rate limit login: sleep(18) antes de login, retry 45s em 429.


## M08 — Progresso (16/08/2026 ~13:10)
Correções aplicadas ao backend/app/routers/case_partes.py: ParteUpdate model, PATCH /{parte_id} (edição com auditoria UPDATE, validação CPF/CNPJ, duplicidade 409, 404 se inexistente), DELETE endurecido (RETURNING id + 404), validação tipo+CPF/CNPJ no POST, duplicidade CPF/CNPJ ativa no caso (409). Imports: from app.services.validators_service import validar_cpf, validar_cnpj; TIPOS_PARTE = autor|reu|terceiro|advogado|procurador. PATCH SQL: sets = ["updated_at = now()"] + [...]; erro inicial "syntax near nome" era por causa de "SET updated_at = now() , nome" — corrigido para ", ".join(sets) após SET.
Uvicorn restarted via session uv: kill PID (pgrep -f uvicorn) then nohup env_shell.sh uvicorn app.main:app --host 0.0.0.0 --port 8000 in backend dir; health ready OK. NÃO usar pkill em comandos compostos (terminal guard).
Bateria scripts/inventory/m08_partes_tests.py — 1ª rodada 25/30. Ajustes feitos após 1ª rodada:
1. audit_logs: coluna é 'acao' (não 'operacao') — sed aplicado.
2. CNPJ_VALIDO/CPF_VALIDO reutilizados batiam em partes de runs anteriores no MESMO caso (409) — precisa usar CPF/CNPJ distintos por run OU escolher caso com client distinto p/ teste 'caso distinto'. FIX pendente: gerar CPF válido novo por run (usar CNPJ fixo de outro cliente) e CASO2 = caso de OUTRO client_id (query DISTINCT client_id ou filtrar por 'M06 Caso' que pertence ao mesmo cliente... pegar caso com client diferente do CASO principal).
Pendências M08 restantes: (a) teste 'CNPJ válido aceito 201' — usar CNPJ único ex: 12345678000195 (validar DV) ou gerar dinamicamente; (b) teste 'mesmo CPF em caso distinto' — escolher caso de outro cliente; (c) reexecutar e confirmar 30/30.
Depois: commitar branch homologacao-m08, escrever relatório qa/homologacao/m08/, seguir para M09 (procurações).
M09 superfície conhecida: router procuracoes prefix /procuracoes — GET /, POST / (201), POST /{id}/minuta, POST /{id}/revogar. Sem GET individual, sem download/assinatura (lacunas M09 documentadas).
M10 superfície: router documents — POST upload (valida magic bytes, limite 50MB, MIMES por extensão), GET download, PATCH atualizar_metadados, DELETE (soft com lixeira trash). UPLOAD_DIR=/home/ubuntu/ejc_repo/data/uploads.
M11 bateria pronta: scripts/inventory/m11_versionamento_tests.py (46/46 original).
Caso QA principal atual: 89b9b439-9ba2-462a-ab99-7dcf1c54cc86 (cliente QA 9e6cd7cd).


## M08 CONCLUÍDO (30/30 PASS) — commit "M08 partes: PATCH edição, DELETE endurecido 404, validação CPF/CNPJ, duplicidade 409, bateria 30/30"
Correções em backend/app/routers/case_partes.py: ParteUpdate + PATCH /{parte_id} (edição com auditoria UPDATE, validação CPF/CNPJ via validar_cpf/validar_cnpj de app/services/validators_service, duplicidade 409, 404 se inativa/inexistente); DELETE endurecido (RETURNING id + 404); POST valida tipo (autor|reu|terceiro|advogado|procurador) e CPF/CNPJ + guard duplicidade ativa 409.
Fórmulas de DV usadas nas baterias (idênticas às do app): CPF dv=(soma*10%11)%10 com pesos (i+1-j), i=9,10; CNPJ pesos1=[5..2] pesos2=[6]+pesos1, dv=11-s%11 (0 se >=10), pos 12 e 13.
Geradores na bateria: _dv_cpf('98765'+randint(1000,9999)), _dv_cnpj('112223'+randint(100000,999999)). Clientes: POST /api/clients exige tipo=PF|PJ, PJ exige razao_social; email não pode ser domínio reservado (.local falha — usar gmail.com ou similar).
Estado DB pós-M08: criado cliente secundário EJC_QA (PJ) + caso secundário para teste multi-cliente; partes QA no caso principal (criadas/inativadas pelo teste).

## M09 superfície (procuracoes.py, 182 linhas, prefix /procuracoes)
Rotas: GET /, POST / (201, response ProcuracaoResponse), POST /{id}/minuta, POST /{id}/revogar (MsgResponse). Sem GET individual, sem download/assinatura (lacunas M09).
Prompt M09 (arquivo comando): teste cadastro, poderes, validade, vínculo, minuta, revogação, auditoria.
Próximo: escrever scripts/inventory/m09_procuracoes_tests.py cobrindo: listagem, criação (outorgante/outorgado, poderes, validade), minuta (200, gera HTML/texto), revogação (200 + status revogada), duplicidade, permissões, auditoria; depois commit + relatório.
M10 superfície: router documents (POST upload validação magic bytes/limite 50MB/MIMEs, GET download, PATCH metadados, DELETE soft→lixeira /api/trash/documents/{id}/restaurar). UPLOAD_DIR=/home/ubuntu/ejc_repo/data/uploads. Bateria m11_versionamento_tests.py existe e precisa de cliente+caso QA (usar CASO principal 89b9b439... ou novo).
uvicorn: session uv (reinciar com kill PID depois nohup env_shell.sh uvicorn... em backend/). Não usar pkill em comandos compostos.


## M09 CONCLUÍDO (28/28 PASS) — commit "M09 procurações: bateria 28/28"
Bateria: scripts/inventory/m09_procuracoes_tests.py. Cobriu criação (ad_judicia, ad_judicia_et_extra, especiais+citação/transigir, validade NULL), validações (cliente inexistente, data_outorga), vínculo client_id, minuta fiel (menciona poderes especiais), revogação (persiste revogada=true, sai da listagem, dupla revogação não falha, inexistente 404), foco vencendo 30d (exclui revogadas — correto), financeiro vê 0 itens (carteira), auditoria CREATE/MINUTA/REVOGACAO.

## M10 EM ANDAMENTO (scripts/inventory/m10_documentos_tests.py)
Estado atual da bateria: 11/18. Problemas:
1. Upload PDF_HEAD → 500 interno (meu PDF sintético talvez invalido para libmagic: 'application/pdf' esperado; %PDF-1.4 deve ser detectado — checar uvicorn log /tmp/uvicorn.log pelo traceback real).
2. XLSX_HEAD → 415 (libmagic lê header zip real? PK\x03\x04 com extra fields pode ser 'application/zip' não xlsx — MIME_POR_EXTENSAO ['.xlsx']={application/vnd.openxmlformats...}? Verificar; talvez usar arquivo xlsx real mínimo gerado via zipfile).
3. Upload 'sem caso só cliente' → 500 — BUG REAL a investigar (client-only path via _verificar_acesso_cliente_sem_caso).
Soluções: gerar DOCs com arquivos REAIS mínimos: PDF mínimo %PDF-1.4 OK mas checar erro; xlsx real via zipfile.ZipFile com [Content_Types].xml; png real mínimo (IHDR chunk).
Auditoria falhou só por docs não criados (causa acima).
Superfície documents.py: POST /upload (file, titulo, tipo[peticao/procuracao/contrato/decisao/prova/outro], confidencialidade, case_id, client_id), GET / (case_id, page), GET /{id}/download, PATCH /{id} (metadados), DELETE /{id}, PATCH /{id}/publicacao-portal, GET /tipos. EXTENSOES_PERMITIDAS={pdf,docx,doc,jpg,jpeg,png,xlsx,xls,txt,md,xml}. MAX_UPLOAD_MB=50. _validar_conteudo usa python-magic; MIME_POR_EXTENSAO[linha 58].
Próximos passos M10: gerar arquivos reais, investigar 500 client-only (uvicorn.log), reexecutar → 22/22 esperado; commit; relatório qa/homologacao/m10/.
M11 bateria m11_versionamento_tests.py (46/46) depende de M10 — rerun após M10.
Uvicorn: session uv, log /tmp/uvicorn.log. Banco local ejc/ejc. Branch atual homologacao-m06 com commits m07-m09 adicionados (m02-m06 pushes remotos já feitos).


## M10 causa raiz 500s (diagnóstico)
1. `PermissionError: [Errno 13] /app` — settings.UPLOAD_DIR default '/app/uploads' (docker). .env local com UPLOAD_DIR=/home/ubuntu/ejc_repo/data/uploads NÃO carregado pelo uvicorn da session uv. CORRIGIR: export UPLOAD_DIR antes de startar uvicorn (matar e re-startar com env_shell). Mesmo fix para kit documental auto (gera PDF no /app).
2. Uploads 415: meu PDF/XLSX sintéticos não detectados como application/pdf/vnd.openxmlformats — gerar arquivos REAIS mínimos (PDF %PDF-1.4 via pypdf? pdf2 não instalado — usar string %PDF-1.4 + %EOF pode bastar SE libmagic detectar; na real libmagic detecta '%PDF' → application/pdf. Verificar por que 500 antes de 415 (o primeiro PDF deu 500 por /app; segundo XLSX deu 415 porque meu header zip fake não corresponde ao mime esperado).
Plano: (a) restart uvicorn com UPLOAD_DIR exportado; (b) gerar PDF real mínimo (pypdf ou fitz se disponível, senão %PDF-1.4 simples testar com libmagic localmente), xlsx real via zipfile com [Content_Types].xml mínimo, png real mínimo (IHDR+IDAT+IEND via PIL.Image); (c) rerun.


## M10 CONCLUÍDO (27/27 PASS) — commit "M10 documentos/GED: bateria 27/27"
Correções: UPLOAD_DIR exportado no start do uvicorn (bug 500 PermissionError /app — variável de ambiente de deploy não carregada localmente; código íntegro). Bateria usa arquivos REAIS (gen_test_files.py: PDF/XLSX/PNG mínimos validados por libmagic). Auditoria usa ações UPLOAD/UPDATE/DELETE/DOWNLOAD (não CREATE).

## M11 revalidação (em andamento)
Bateria m11_versionamento_tests.py reescrita para ser auto-suficiente (cria cliente/caso QA dinamicamente, mk_pdf com header real %PDF-1.4 detectado como application/pdf). Correção de bug: S session usada antes da definição — corrigido.
Aguardando execução final. Esperado: 46/46 PASS.


## M11 bateria bug de recriação
Segundo POST /api/cases retornou id None — verificar schema (talvez 422: "area" enum? área tributario ok; parte_contraria ok; proxima_acao ok... talvez 403 rate? Não). Investigar resposta. Possível: segundo caso criado imediatamente após o primeiro com mesmo client_id — validação de duplicidade? Improvável. Ver resposta HTTP.


## M12 superfície (andamentos)
- `backend/app/routers/andamentos.py` (prefix /casos): POST /{case_id}/andamentos/sincronizar (DataJud sync upsert em case_movimentos, ownership + rate 5/min, 503 se DATAJUD_ENABLED=false), GET /{case_id}/andamentos/status (booleans config + alias tribunal).
- `backend/app/routers/movimentos.py` (prefix /movimentos): GET /recentes (dashboard, escopo carteira).
- Movimentos CRUD interno já coberto no M07 (POST /cases/{id}/movimentos, lista, exclusão). M12 foca: sincronização DataJud (origem, data, descrição, processo, ordenação, duplicidade/idempotência, atualizações automáticas, auditoria) + status + recentes.
- case_movimentos tabela: ver colunas (data_movimento, descricao, tipo, ordem?).


## M12 detalhes técnicos confirmados
Rota interna de movimentos: POST /api/cases/{case_id}/movimentos (json: tipo, descricao, data_evento — timestamp ISO com Z OK; PATCH /movimentos/{id} edita; DELETE exclui da tabela case_movimentos). Tabela case_movimentos: id, case_id, tipo(varchar30), descricao(text), data_evento(tz, default now()), created_by, created_at, resumo_ia. Sem coluna ordem (ordenação via data_evento).

DataJud: DATAJUD_ENABLED=false e DATAJUD_API_KEY vazio no .env local. POST sincronizar: 503 claro se desativado/sem chave; 422 se caso sem numero_processo; TribunalNaoMapeadoError→422; HTTPError→502; upsert dedup hash(data[:10]|descricao); audit SYNC em case_movimentos. GET status: enabled/configured/numero_processo/tribunal_alias (sem segredos). Dashboard: GET /api/movimentos/recentes (limit 15-50; equipe vê só casos próprios).

Bateria M12 escrita: scripts/inventory/m12_andamentos_tests.py. Testes: criação, autor, data/desc, edição, ordenação por data_evento, duplicidade textual aceita, data inválida 422, estagiário cria/financeiro bloqueado, exclusão, auditoria, status DataJud sem segredos, sync 503 desativado, /recentes sem vazar, upsert idempotente (estrutural).

Clientes/casos QA M11: cliente "EJC_QA Cliente M11" (CNPJ 12345678000195 → reutiliza cliente M09 ae6dc2dc... se já existir), caso "EJC_QA M11 Caso A".

Push: remoto voltou a funcionar? GH_TOKEN expirado — branches homologacao-m02..m06 já pushadas antes do reset; commits M07-M11 locais (a reconfirmar push).


## M12 descoberta: rotas 404
POST /api/cases/{id}/movimentos → 404 (caminho errado). GET status → 404. O PASS "movimento criado 201" veio do M07? Não — M12 é script novo. Verificar rota exata usada no M07 (m07_casos_tests.py) para movimentos e andamentos status.


## M12 gaps confirmados no código
Cases.py: apenas GET listagem e POST criação de movimentos (com event_bus emitir movimento.criado). NÃO existem PATCH/DELETE de movimento — lacunas REAIS (edição e exclusão de movimento inexistem). DataJud sync via POST /api/cases/{id}/sincronizar-processo (dentro cases.py), não /andamentos/sincronizar; andamentos.router (/casos/{id}/andamentos/status|sincronizar) existe mas andamentos.router é montado com prefix=API → /api/casos/{id}/andamentos/status (PORTUGUÊS). M07 roteava tudo em /api/cases/{id}/* (cases.py). Verificar onde andamentos.router foi montado (linha 342 main.py: include_router(andamentos.router, prefix=API) → rotas /api/casos/... OK para andamentos router). Meu M12 usou /api/cases/{id}/andamentos/status → 404 pois cases.py registra /cases (inglês). Corrigir: usar /api/casos/{id}/andamentos/status E /api/casos/{id}/andamentos/sincronizar. Movimentos CRUD: criar (POST /cases/{id}/movimentos), listar (GET /cases/{id}/movimentos), editar/excluir INEXISTENTES → corrigir casos.py adicionando PATCH e DELETE (audit CREATE/UPDATE/DELETE + event_bus).


## M12 correções em andamento
Adicionado em backend/app/routers/cases.py: editar_movimento (PATCH /cases/{id}/movimentos/{mid}) e excluir_movimento (DELETE) com guarda de acesso do caso, 404 endurecido e auditoria UPDATE/DELETE em case_movimentos. Import de MovimentoUpdate adicionado (linha 46). FALTAM: (1) definir class MovimentoUpdate em backend/app/schemas/case.py (após MovimentoCreate, linha ~258): tipo Optional[str]=None, descricao Optional[str]=None, data_evento Optional[datetime]=None — verificar import datetime no schema; (2) criar_movimento NÃO usa payload.data_evento (m.data_evento sempre default now()) — adicionar m.data_evento=payload.data_evento se MovimentoCreate ganhar data_evento Optional; (3) ordenação do GET listar_movimentos é by created_at desc — prompt pede ordenação; deixar data_evento desc seria melhor (ordenar eventos cronologicamente). Deps: datetime em schemas/case.py já tem? verificar. Depois: reiniciar uvicorn (reload? pkill + restart), rodar bateria M12 corrigida (rotas andamentos: usar /api/casos/{id}/andamentos/status e /api/casos/{id}/andamentos/sincronizar — router em português; ou usar /api/cases/{id}/sincronizar-processo para o sync real). Movimentos/recentes OK.


## M12 rotas confirmadas no OpenAPI
GET/POST /api/cases/{id}/movimentos; PATCH/DELETE /api/cases/{id}/movimentos/{mid} (NOSSAS, M12); POST /api/cases/{id}/sincronizar-processo (sync DataJud real); /api/casos/{id}/andamentos/{status|sincronizar|inteligencia|alimentar-ia} (router pt); GET /api/movimentos/recentes. Corrigir bateria m12_andamentos_tests.py: usar essas rotas; status com admin; sync desativado via /api/cases/{id}/sincronizar-processo → 503 claro (DATAJUD_ENABLED false). Movimentos/recentes já correto na bateria.


## M12 estado completo (antes da última rodada)
Correções já aplicadas no código: cases.py ganhou editar_movimento (PATCH) + excluir_movimento (DELETE) com audit UPDATE/DELETE; schemas: MovimentoCreate.data_evento opcional + MovimentoUpdate; listagem ordenada por data_evento desc. Bateria m12_andamentos_tests.py corrigida (rotas status/sincronizar pt; sync 422 sem CNJ; CNJ via PATCH; /recentes lista direta).

PENDENCIAS para a próxima rodada:
1. A bateria referencia _gen_cnj() que NÃO EXISTE no script — criar função que gera CNJ válido módulo 97 (reusar a do M07: m07_casos_tests.py tem cnj_valido() — copiar/adaptar).
2. GAP REAL encontrado: criar_movimento NÃO registra audit log (só PATCH/DELETE que acabei de criar). CORRIGIR: adicionar await criar_audit_log(db, cu.id, _role, "CREATE", "case_movimentos", case_id, dados_depois={...}) em criar_movimento, depois restart uvicorn.
3. Estagiário 404: estagiário está fora da carteira (advogado_responsavel=advogado admin). Guard _filtro_visibilidade devolve 404 uniforme — comportamento LGPD correto, não é bug; o teste foi ajustado para esperar 201 "dentro do escopo" → vai continuar 404 pois estagiário não é responsável/auxiliar. Ajustar teste para aceitar 404 uniforme OU atribuir estagiário como auxiliar. Preferir: aceitar 404 uniforme (404 in allowed) — mudar chk para r.status_code == 404 = fora da carteira bloqueado; e testar estagiário DENTRO do escopo seria atribuir estagiario_id ao caso... o schema CaseUpdate não tem advogado_auxiliar? M07: verificar CaseUpdate campos (advogado_responsavel_id existe; auxiliar não vi). Simples: estagiário 404 é correto (fora da carteira) — ajustar expectativa.
4. Auditoria CREATE movimento: espera 'CREATE/INSERT/MOV' — depois da correção 2, usar chk direto na ação 'CREATE' da entidade case_movimentos.
5. /recentes: verificar formato da resposta real (lista? wrapper?) no 14 — já ajustado para lista direta, mas confirmar.
6. M12 bateria roda com env_shell python3. Servidor uvicorn em 45001, log /tmp/uvicorn.log.
7. Após M12: commit (branch homologacao-m06 ou criar homologacao-m12-andamentos-2026-08-16 a partir da m06?), depois M13 (intimações).
8. M07-M11 baterias: re-push pendente das branches ao final (usuário pediu continuar local e refazer pushes ao final).


# M13 — Intimações DJEN (em andamento)
Bateria: scripts/inventory/m13_intimacoes_tests.py (28 testes). 1ª rodada: 25/28 PASS.
FAILs: (1) cliente externo listar → 403 "Portal do Cliente" (esperava 200/0) — ajustar teste p/ aceitar 403? ou investigar decorator. (2) sugestão keys reais = aviso, case_id, casou, com_id, data_base, data_disponibilizacao, data_sugerida, dias, disponivel, fundamentacao, motivo, numero_processo, revisao_necessaria, tipo_detectado — ajustar chk p/ revisao_necessaria+aviso. (3) capturar-agora: DJEN_INGEST_ENABLED=false NÃO é checado em capturar_para_advogado (só scheduler) — com OAB tenta HTTP real → http_4xx (chave vazia). FIX: adicionar gate DJEN_INGEST_ENABLED no capturar-agora → 503 claro (corrigir backend, reiniciar uvicorn).
Surface M13: GET /api/intimacoes/?apenas_pendentes (is_gestao vê todos, demais advogado_id); GET /status-captura; POST /{com}/processar (422 se prazo não decidido); POST /sugerir-prazo, GET /prazo-sugerido; POST /aceitar-prazo (data_prazo manual obrigatório, case_id obrigatório 422); POST /recusar-prazo (409 se aceito); POST /capturar-agora (OAB 422). Entidade audit: djen_comunicacoes (UPDATE); CREATE deadline origem=djen. Aceite idempotente (criado=false).
DjenComunicacao cols: id, comunicacao_id_externo, advogado_id, numero_processo, tribunal, tipo_comunicacao, data_disponibilizacao, texto_resumo, case_id, processada, processada_por, processada_em, prazo_sugerido_status (nenhum|sugerido|aceito|recusado), prazo_deadline_id, created_at.
Próximos: corrigir 3 FAILs (sugestão chk; cliente externo; gate DJEN no capturar-agora) → rerun → commit → relatório m13 → M14 Prazos.
Nota: capturar_para_advogado fica em backend/app/services/*djen*.py — localizar e editar.
Requisitos M14: prazos CRUD, regime dias úteis/corridos, termo inicial intimação, vencimentos, alertas vencendo (hoje, em X dias), vencidos, recálculo por regime/tribunal.


## M13 correções aplicadas (3 FAILs → reexecutar bateria)
1. Bateria: cliente externo chk → aceitar 403 (rota restrita ao Portal do Cliente) OU 200/0. Feito.
2. Bateria: chk sugestão → campos reais: aviso, revisao_necessaria, fundamentacao, disponivel, data_sugerida, dias. revisao_necessaria=True esperado. Feito.
3. Backend djen_service.py: gate DJEN_INGEST_ENABLED adicionado no capturar_para_advogado (linha ~689, import local get_settings) → retorna fonte_ok=False erro=feature_desabilitada → router intimacoes traduz para 503 claro. Feito.
Uvicorn reiniciado (pid novo, ready OK). Próximo: python3 m13_intimacoes_tests.py → esperado 28/28 → commit → relatório qa/homologacao/m13/RELATORIO_MODULO_13 → M14 Prazos (deadlines.py: CRUD + regime dias úteis/corridos + termo inicial + vencendo + vencidos).
Bateria M14 a escrever: prazos (deadlines) CRUD, criação manual + via intimação aceita, data_prazo inválida 422, vencendo (hoje/7/30d), vencidos, recálculo regime (prazo_dias_uteis x prazo_dias_corridos), auditoria, RBAC (carteira), exclusão/restauração.


# M14 — Prazos (deadlines) — superfície mapeada
Router: /api/deadlines (prefix="/deadlines", tags=Prazos), main.py line 371.
Rotas: POST /calcular (calculadora, não persiste; campos: data_inicio, dias, dias_uteis=true, dobro=false, tribunal=None, tipo=processual) → {data_vencimento, modo, dias_uteis_restantes}. GET / (page, page_size max 200, status=pendente, case_id, tipo, apenas_meus; default status='pendente') → {data: [..+dias_restantes+urgencia(vencido<0,critico<=3,atencao<=7,normal), total, page, page_size}. GET /export.csv (status, case_id, tipo; BOM UTF-8, ';' pt-BR; teto 5000). POST / 201 (DeadlineCreate: titulo, tipo, prioridade=media, data_prazo OU data_intimacao+dias_prazo, dias_uteis=true, dobro, tribunal, base_legal, descricao, case_id, responsavel_id; validator enum tipo/prioridade → 422; se não tem case_id→verificar_acesso_caso; responsavel_id default=cu.id; audit CREATE). PATCH /{id} (update parcial; baixa p/ concluido carimba data_conclusao+concluido_por e audit PRAZO_CONCLUIDO). PATCH /{id}/confirmar (rascunho extraído por IA → PRAZO_CONFIRMADO audit). POST /{id}/ciencia. DELETE /{id}.
Filtros escopo (não-gestão): prazos dos próprios casos (responsável/auxiliar) OU responsavel_id=cu OU case_id=NULL. Gestão vê tudo. ordena por data_prazo ASC.
Enums: tipo (processual etc.), prioridade, status (pendente, concluido, cancelado, rascunho?). Deadline model: titulo, tipo, prioridade, status, data_prazo, data_intimacao, base_legal, descricao, case_id, responsavel_id, confirmed(?), concluido_por, data_conclusao, deleted_at.
Calculadora: prazo_dias_uteis(dia_ini, dias, tribunal, em_dobro, aplicar_recesso, forense) suspende recesso 20/12-20/01 p/ processual; prazo_dias_corridos p/ administrativos (prorrogação fim de semana/feriado via Lei 9.784 art.66).
M14 bateria deve cobrir: POST /calcular (úteis com recesso, corridos, dobro), POST create (manual e com cálculo automático dias+intimação), enum inválido 422, data_prazo ausente 422, UPDATE parcial, PATCH confirmar, DELETE com lixeira, GET listar (default pendente; filtros; escopo não-gestão), CSV export, urgência vencido/critico/atencao, RBAC (advogado_auxiliar vê; estagiário/financeiro não?), auditoria CREATE/PRAZO_CONCLUIDO/UPDATE.
Recursos QA: CASE_ID do M13 (caso com CNJ) — buscar via GET /api/cases?advogado? Não: caso criado pelo admin. Usar DB: SELECT id FROM cases WHERE deleted_at IS NULL LIMIT 1 (cliente mesmo do QA cliente). advogado QA = ejc_qa_auth_advogado@golocal.ejc (precisa ser responsável/auxiliar do caso p/ ver prazo — M13 setou advogado_responsavel_id=adv para o caso).
Depois M14: commit → relatório m14 → M15 Honorários.


# M14 CONCLUÍDO — 33/33 PASS (HOMOLOGADO)
Commit `601925b1`. Correção M14: `DeadlineResponse` (backend/app/schemas/deadline.py) agora expõe `data_conclusao` + `concluido_por` (baixa carimbava os campos mas a API não os retornava — rastreabilidade da baixa).
Fatos-chave M14: calculadora processual 10d úteis de 2026-09-01 → 2026-09-16; dobro → 2026-09-30; recesso: 5d de 2026-12-10 → 2026-12-17 (termina antes do recesso); administrativo corrido → 2026-12-21. Novo prazo vem confirmado=True por default; POST /deadlines/{id}/confirmar exige confirmado=false (teste forçou via DB UPDATE deadlines SET confirmado=false). Auditoria: CREATE + PRAZO_CONCLUIDO; PRAZO_CONFIRMADO + CIENCIA_PRAZO. Export CSV com BOM UTF-8 e separador ';'. Exportação /export.csv em export.py.
Bateria: scripts/inventory/m14_prazos_tests.py (33/33). Debug probe: scripts/inventory/debug_m14_baixa.py.
Padrão bateria: chk(desc, ok, extra) + FALHAS; env: /home/ubuntu/ejc_repo/scripts/inventory/env_shell.sh python3 ...; login c/ retry automático + sleep 20*retry em 429; rate limit login 10/min.
Branch homologacao-m07-2026-08-16 (acumula M07..M14).

# M15 HONORÁRIOS — superfície mapeada (16/08/2026)
- `fees.py` (314 lin, base path ~ /fees): GET / (listar), GET /resumo, POST / (201), PATCH /{fee_id}, POST /{fee_id}/pagamentos (201), DELETE /{fee_id}.
- `exito_rateio.py` (148 lin): GET /{fee_id}/rateio, POST /{fee_id}/rateio (201).
- `honorarios_calc.py` (106 lin): GET /honorarios/cases/{case_id}/provisionamento (prefix /honorarios?), GET .../teto-etico.
- `honorarios_oab.py` (456 lin): GET /tabela, POST /estimar (rate_limit honorarios-estimar 15), GET/POST /itens, POST /itens/{item_id}/encerrar-vigencia, POST /casos/{case_id}/proposta/sugerir, POST /casos/{case_id}/proposta, GET /casos/{case_id}/proposta, POST /propostas/{proposta_id}/aprovar, POST /propostas/{proposta_id}/rejeitar.
- `export.py` linha 187: GET /honorarios.csv.
- Prompt M15: criar/edição/exclusão, êxito/sucumbencia, percentual, múltiplos pagamentos, rateio, provisionamento por caso, teto ético, tabela OAB, estimativas, proposta sugerir/aprovar/rejeitar, RBAC financeiro, auditoria.
- Recursos QA: caso principal (advogado = responsável ID 4701ecbf-*; cliente QA CPF 12345678909 id 9e6cd7cd...), caso secundário multi-cliente criado no M08 (cliente PJ EJC_QA), caso probe M14 (CPF probe).
- Depois de M15: M16 financeiro, M17 contratos, M18 societário, M19 RAG/IA, M20 segurança, ... até M36 relatório final. Push de branches pendente ao final (remoto OK, token válido novamente? — branches m04-m06 já em remoto).


# M15 superfície (Calendário Forense)
IMPORTANTE: M15 no comando mestre = "CALENDÁRIO FORENSE, FERIADOS E SUSPENSÕES" (não honorários — honorários é M34, PROMPT 34 linha 946).
Componentes: `deadline_calculator.py` (pure/sync: FERIADOS_FIXOS nacionais dia/mês, RECESSO_FORENSE 20/12–06/01 [Lei 5.010/66 art.62 I], feriados móveis (Carnaval/Páscoa/Corpus via ano), _FERIADOS_DB municipais/estaduais via tabela `feriados` [id,nome,tipo=nacional|estadual|municipal|forense,movel], suspensões por tribunal via suspensoes_tribunal + dc.carregar_suspensoes_db).
Endpoints: /api/suspensoes/tribunais (GET sugestões), /api/suspensoes/ (GET listar, POST criar 201 com auditoria, DELETE), /api/suspensoes/simular (POST: data_inicio, dias 1..3650, contagem uteis|corridos, tribunal opcional; uteis=dc.prazo_dias_uteis, corridos=prazo_dias_corridos prorrogar_fim True Lei 9.784/99 art.66 §1º; NÃO grava). Tabela feriados tem seed (seed_all) — Betim MG.
Feriados endpoints: sem CRUD público (carregados do DB no startup + scheduler diário; brasilapi sync _sincronizar_feriados_brasilapi).
Calculadora: forense=True (default) exclui recesso 20/12–06/01 + feriados; forense=False (administrativo) não exclui recesso forense.
Já provado no M14: calculadora nacional+recesso; M15 deve provar: feriados nacionais fixos+ móveis (2026), suspensão por tribunal aplicada, comarca/municipal (Betim), forense vs administrativo, tribunal=None, simular endpoints, recesso.


# M15 estado (16/08)
Bateria: scripts/inventory/m15_calendario_tests.py — fixada: (1) expectativa forense 14/12+5u = 2027-01-07 (recesso 20/12–06/01 correto), (2) admin corrido 14/12+5 = 19/12 sáb → prorrogar_fim → 21/12 seg (correto, Lei 9.784/99 art.66 §1º), (3) trib endpoints usam {"tribunais":[...]}, (4) feriado municipal sintético 20/11/2026 via psql db() + dc.carregar_feriados_db() (asyncio.run). 34/36 no run anterior (2 falhas: seed p/ memória e efeito no cálculo). Run final pendente após última edição.
Sequência após M15: M16 Agenda/Tarefas (PROMPT 16), M17 Produção Jurídica/Peças, M18 Templates, M19 Perfil/Estilo, M20 Biblioteca Jurídica, M21 Ingestão RAG, M22 Retrieval RAG/ACL, M23 IA Jurídica Central, M24 Veracidade, M25 Precedentes, M26 Prompt Injection, M27 Chat, M28 Inteligência do Caso, M29 Dossiê Estratégico, M34 Honorários (fim). Relatórios em qa/homologacao/m01, m02... Padrão: commit por módulo em homologacao-m07-2026-08-16; push pendente (remoto OK: branches m04-m06 em origin).
Notas-chave de ambiente: uvicorn via nohup + env_shell em /home/ubuntu/ejc_repo/backend porta 8000, log /tmp/uvicorn.log; restart: kill $(pgrep -f "uvicorn app.main:app"); sleep; nohup. DB: ejc/ejc@localhost/ejc, PGPASSWORD=ejc. Rate limit login 10/min (header X-Forwarded-For: 127.0.0.1 fixo).


# M15 estado 2 (16/08, 35/36)
Último FAIL: limpeza do feriado sintético. Suspeita: set_feriados_db({}) não limpou o conjunto OU f-string do chk avalia argumentos antes (v=23 veio da avaliação pré-chk do extra com set ainda carregado — mas chk também recomputa e retorna False). Verificar se dc.set_feriados_db aponta para o MESMO módulo (import alias pode criar referência ao objeto do module dict, é o mesmo). Debug real: print len(dc._FERIADOS_DB) após set_feriados_db({}).
Nota matemática: 16/11+3 úteis = 19/11; +4 úteis = 23/11 (20/11 feriado suspende) — confirmado pela bateria.
M16: Prompt no arquivo /home/ubuntu/upload/Pasted_content_76.txt linha ~484 (PROMPT 16 — buscar "Módulo 16\|Módulo 016" via grep -n "PROMPT 16").


## M15 HOMOLOGADO — 36/36 PASS (16/08)
Causa raiz do FAIL: 20/11/2026 é feriado NACIONAL (Dia Nacional de Zumbi e da Consciência Negra, Lei 14.759/2023, vigente desde 22/12/2023) — já constava em FERIADOS_NACIONAIS do calendário versionado. O teste de limpeza esperava erroneamente 20/11 voltar a ser dia útil. COMPORTAMENTO DO SISTEMA CORRETO. Fix do teste: data sintética movida para 08/06/2026 (segunda, sem conflito nacional) e contagem 04/06+3 úteis: com feriado → 10/06; após limpeza → 09/06. Commit 56d6f580. Branch: homologacao-m07-2026-08-16.
PRÓXIMO: M16 — Prompt no arquivo /home/ubuntu/upload/Pasted_content_76.txt (grep -n "Módulo 16" ou "Módulo 016").


## M16 superfície descoberta (16/08)
Routers: /api/agenda-eventos (agenda_eventos.py, 262 lin) e /api/tasks (tasks.py, 219 lin).

AGENDA-EVENTOS: GET / (page, page_size, filtro pessoal por carteira/caso; expõe titulo/tipo/data/hora/local/descricao/case_id/responsavel/concluido/caso_titulo), POST / (EventoIn: titulo max255, tipo=reuniao|compromisso|diligencia|audiencia|outro, data_evento date, hora varchar10, local, descricao, case_id, responsavel_id; gate: só gestão cria p/ outro responsável; valida existência do responsável; conflito_agenda no retorno = double-booking AVISA não bloqueia, censura titulo/local de eventos de outros), PATCH /{id} (EventoPatch: titulo/tipo/data/hora/local/descricao/concluido/responsavel; transferência de responsável exige gestão+validação+audit UPDATE com detalhes; recheque conflito; 404; 403 para pessoal de outro), DELETE /{id} (soft deleted_at, gate pessoal sem caso: gestão OU created_by/responsavel; audit DELETE).

TASKS: GET / (case_id, minhas bool; escopo IDOR protegido não-gestão: só casos próprios/sem dono/onde é responsável; ordena data_limite nullslast), POST / (TaskIn: titulo, descricao, prioridade=media, data_limite, case_id, responsavel_id; validação usuário; NOTIFICA o responsável se não é o próprio criador — Notification tipo tarefa), PATCH /{id} (TaskPatch: titulo/descricao/status/prioridade/data_limite/responsavel; status enum TaskStatus a_fazer|em_andamento|concluida|cancelada; concluida→concluida_em UTC + sincroniza atendimento.solicitacao_atendida/atendida_em/atendida_por_id + registrar_acao; task removida zera atendimento.task_id), DELETE /{id} (soft + desvincula atendimento + registrar_acao).

LACUNAS do módulo (não existem no código): recorrência (nenhum campo), lembretes/notificações de EVENTOS (só tarefas notificam), timezone (hora é varchar livre, data date — sem tz), participantes (só responsavel_id), cliente (case_id existe; sem client_id direto em agenda_eventos), conflitos (existe, boa implementação).
Bateria M16 deve: provar CRUD completo, reagendamento (patch data/hora), conflito (mesmo resp/data/hora → conflito_agenda; hora None não colide; edit exclui si mesmo), censura N2 (não-gestão vê "Compromisso de outro usuário"), gate criação p/ outro (403 não-gestão), responsavel inexistente 422, caso sem acesso 403/404, tarefas: criação+notificação para outro, próprias sem notificação, conclusão+concluida_em+atendimento sync, patch status inválido 422, remoção zera atendimento, filtros (case_id, minhas), prioridade, data_limite, escopo IDOR não-gestão.
