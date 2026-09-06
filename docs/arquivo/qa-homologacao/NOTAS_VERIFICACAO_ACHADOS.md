# Avaliação do Relatório de Auditoria Funcional (16/08/2026) — notas de verificação

## Contexto
Usuário pediu avaliação do relatório gerado por outro agente (Claude, sessão Cowork) sobre produção https://ejc.depaulateixeira.adv.br/. Nossos fatos: homologação local M01-M36 concluída HOJE; branch homologacao-m07-2026-08-16; push remoto pendente; produção pode estar rodando uma VERSÃO ANTIGA (commits da homologação ainda não publicados).

## Verificações F-01 / F-02 (documentos e relatorio-lgpd 500)
- Local (código homologado): `/api/documents/` → 200 OK; `/api/clients/{id}/relatorio-lgpd` → 200 OK (com token socio). Código existe e funciona localmente (routers documents.py l.41, clients.py l.797).
- CONCLUSÃO: os 500s reportados em produção são CONSISTENTES com produção rodando versão anterior à homologação OU problema de ambiente de produção (ex.: UPLOAD_DIR/env como no bug M10). Não são defeitos do código atual do repo. O relatório NÃO está errado sobre produção, mas não distingue versão de produção vs. código corrente. Classificação dos achados como "CRÍTICO do sistema" é excessiva: são críticos do AMBIENTE DE PRODUÇÃO atual, corrigíveis por deploy.
- F-03/F-04 (DJEN falho, scheduler anpd/normas_rfb): nossa homologação M13/M15 confirmou comportamento esperado com DJEN_INGEST_ENABLED=false. Em produção pode estar ativo e falhando (chave/chancela). Não verificável sem logs — parecer deve manter ceticismo quanto à causa.
- F-05 (freeze UI): não verificável localmente; plausível (153 notificações). Sem evidência de código no repo.
- F-06 (contas HOMOLOG superadmin ativas): PRODUÇÃO ≠ nosso sandbox local (nossos QA são ejc_qa_auth_*, não HOMOLOG-*). Verdadeiro sobre produção; não afeta nosso repo.
- F-07 (dados fictícios acumulados): idem produção.
- F-08 (parte contrária da Entrada Única não vira registro em Partes): verificar no código. Entrada Única (router entrada_única/frontdesk?) grava parte_contraria como texto no case; case_partes.py exige registro estruturado. Se verdadeiro → FEATURE REQUEST legítima (não bug de quebra).
- F-09, F-10 (timeline "Data Não Informada", KPI não atualiza): F-10 → frontend mapeia campo de data diferente do payload; verificar campo da API /movimentos/recentes (nosso backend retorna data_evento). Plausível.
- F-11 (selo confiança em campos vazios): frontend Peças; não verificável sem acesso.
- F-12 (toast expõe rota interna POST /cases/{id}/arquivar): nosso código exige motivo; mensagem arquivamento pode expor rota — verificar casos.py e frontdesk/entrada.
- F-13 (menu Seguro&Conforme não navegável): UX frontend.
- F-14 (Google Fonts 503): dependência externa; recomendável self-hosting.
- F-15 (CPF sem máscara na listagem): VERIFICAR documents/clients.py — clientes expõem cpf_cnpj cifrado (documento_plain/migration 112); listagem pode expor via documento_plain — checar backend/app/routers/clients.py na listagem. Se listagem decifra → achado real e importante.
- F-16 (153 notificações): agrupamento = feature request.

## Verificações feitas até agora
- F-01: /api/documents/ 200 local ✓ (código OK; produção precisa de deploy)
- F-02: /api/clients/{id}/relatorio-lgpd 200 local ✓
- P-01..P-08: coerentes com nossa homologação (CPF DV, soft-delete motivo 5 chars, lixeira, sem módulo licitações no frontend manifest, central diagnóstico, HITL).

## Pendências de verificação
1. F-08: entrada única → parte_contraria texto vs case_partes estruturada
2. F-10: campos de data no payload /movimentos/recentes (backend retorna data_evento? frontend espera outro nome?)
3. F-12: mensagem de bloqueio de exclusão com rota exposta
4. F-15: listagem /clients expõe cpf_cnpj decifrado?

## Resultados das verificações no código (16/08 ~21:10)

**F-01 (documentos 500):** `/api/documents/` retorna 200 no código atual com token válido. Rota existe (documents.py l.41). Os 500s de produção indicam produção sem o deploy da homologação ou problema de ambiente (variável UPLOAD_DIR era causa do 500 no bug M10). ACHADO VERDADEIRO SOBRE PRODUÇÃO, mas não é defeito do código atual → classificar como "corrigido na homologação / pendente de deploy".

**F-02 (relatorio-lgpd 500):** `/api/clients/{id}/relatorio-lgpd` retorna 200 no código atual (clients.py l.797). Idem F-01: produção desatualizada. O relatório tem mérito ao identificar a LACUNA DE UX (sem toast), que é verificável no frontend.

**F-08 (parte contrária):** clients.py l.189/277 grava `parte_contraria=req.parte_contraria` como TEXTO no campo do case (entrada única/criação de caso), sem criar registro estruturado em case_parts (tabela partes). Achado VERDADEIRO e bem fundamentado — é feature request legítima: criar registro estruturado da parte contrária ao confirmar a ficha. Impacto: peças/procurações não herdam a parte contrária.

**F-12 (rota exposta):** CONFIRMADO no código — cases.py l.392: mensagem de erro 422 "Use POST /cases/{id}/arquivar" com rota técnica em texto exibido ao usuário. Achado VERDADEIRO e de mérito (exposição de superfície interna, prática inadequada). Corrigível com texto de negócio + log interno.

**F-15 (CPF sem máscara na listagem):** CONFIRMADO no código — ClientResponse (schemas/client.py l.189-208) serializa `cpf_plain`/`cnpj_plain` (decifração de cpf_enc/cnpj_enc) na LISTAGEM GET /clients/ (clients.py l.394, ClientResponse.model_validate). A busca global mascara, mas a listagem expõe o documento completo a qualquer perfil com acesso de leitura (carteira + gestão). Achado VERDADEIRO e relevante (LGPD — minimização). Correção: mascarar na listagem e expor completo só na ficha individual com gate de titularidade. P-07 (máscara na busca) é consequência do mesmo design inconsistente.

**F-10 (Data Não Informada):** movimentos.py l.37 retorna coluna derivada `COALESCE(m.data_evento, m.created_at) AS quando` — se o frontend mapeia campo com outro nome (ex.: `data` ou `created_at`), mostra "Data Não Informada". Plausível; requer verificar nome esperado pelo componente frontend. Achado PLAUSÍVEL, baixa severidade (somente exibição).

**F-03/F-04 (DJEN/scheduler):** comportamento esperado com features desligadas (DJEN_INGEST_ENABLED=false). Em produção, se ativo, falha do job pode ser chave/chancela ou fonte. Não verificável sem logs — manter recomendação do relatório (contenção manual + logs).

**F-05 (freeze), F-11 (selo), F-16 (notificações):** frontend; não verificáveis no backend local. Coerentes com relatos; classificar como "plausíveis, requerem reprodução".

**F-06/F-07 (contas e dados HOMOLOG em produção):** produção ≠ nosso sandbox; verdadeiros sobre produção. Alinhados com nossa regra de não deixar massa de teste em produção.

## Síntese da avaliação
O relatório é TÉCNICAMENTE BOM (evidência por HTTP status, reprodução, rastreabilidade de dados fictícios, metodologia declarada), mas CLASSIFICAÇÃO SEVERA EXCESSIVA em F-01/F-02: os 500s foram observados na PRODUÇÃO, que provavelmente roda versão anterior à homologação de hoje (branch homologacao-m07-2026-08-16 ainda não publicada). Nenhum dos 3 "críticos" é defeito do código corrente homologado: F-01/F-02 → corrigidos/funcionais no código atual (200 comprovado); F-03 → configuração de feature (DJEN desligado) ou falha de produção a investigar com logs.
Achados com mérito real no código atual: F-08 (parte contrária texto livre), F-12 (rota exposta em mensagem), F-15 (CPF decifrado na listagem), F-06/F-07 (higiene de produção).
P-01..P-08: coerentes com homologação.
Recomendação: (1) fazer deploy da branch homologada à produção e retestar F-01/F-02; (2) correções pontuais F-08/F-12/F-15 no backend; (3) expurgo formal dos dados HOMOLOG (F-07) com aprovação do Dr. Clovis; (4) desativar contas de homologação (F-06).

**F-10 — RAIZ CONFIRMADA.** O backend `movimentos.py` retorna a coluna derivada `COALESCE(m.data_evento, m.created_at) AS "quando"`. O frontend `DashboardUltra.tsx` (l.748-752) lê `movement.data_movimento || movement.created_at || movement.data` — NENHUM desses campos existe no payload, que traz apenas `quando`. Resultado: `formatDateTime(undefined)` → "Data Não Informada". O relatório ACERTOU a severidade MÉDIA e a diagnose (mapeamento frontend ≠ payload backend). Correção trivial: backend passar `created_at`/`data_evento` explícitos OU frontend ler `.quando`. Achado legítimo, severidade média correta.
