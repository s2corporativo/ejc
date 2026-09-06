# Parecer Técnico — Avaliação do Relatório de Auditoria Funcional do EJC (16/08/2026)

**Documento avaliado:** Relatório Técnico de Auditoria Funcional do EJC — 16 achados (3 críticos, 3 altos, 4 médios, 6 baixos) e 8 pontos positivos
**Executor do relatório:** agente técnico de QA (Claude, sessão Cowork), auditoria por navegação na produção `https://ejc.depaulateixeira.adv.br/`
**Avaliador:** Manus AI, com acesso direto ao código-fonte (`s2corporativo/ejc`, branch `homologacao-m07-2026-08-16`) e ao backend em execução local
**Data:** 16/08/2026

---

## 1. Veredicto geral

O relatório é **tecnicamente sólido e metodologicamente correto**: todo achado está ancorado em evidência observada (código HTTP de resposta de API, reprodução em sessões distintas, Central de Diagnóstico nativa do próprio EJC, rastreabilidade dos dados fictícios criados). Não identifiquei afirmações inventadas. Há, contudo, **um desalinhamento essencial que reduz a severidade real dos três achados "críticos"**: a auditoria foi executada sobre a **produção em execução**, enquanto a homologação concluída hoje (M01–M36) produziu correções e validações no **código corrente do repositório, ainda não publicado na produção** (push pendente por motivo de autenticação GitHub). Em outras palavras, o relatório descreve com precisão o estado da produção, mas não distingue o que é defeito do sistema do que é **versão desatualizada da produção**.

A tabela seguinte consolida a avaliação achado a achado, com base em verificação direta no código-fonte e em chamadas reais ao backend local.

## 2. Avaliação achado a achado

| Achado | Veredito | Fundamento da verificação |
|---|---|---|
| F-01 — GED indisponível (500) | **Verdadeiro na produção; não é defeito do código atual** | `GET /api/documents/` retorna **200 OK** no código atual com token válido (rota `documents.py` l.41). Os 500s de produção são consistentes com ambiente desatualizado ou variável de deploy ausente (`UPLOAD_DIR`, causa do bug M10 já corrigido). **Resolve-se com o deploy da branch homologada + reteste** |
| F-02 — Relatório LGPD (500, sem aviso) | **Verdadeiro na produção; não é defeito do código atual** | `GET /api/clients/{id}/relatorio-lgpd` retorna **200 OK** no código atual (rota `clients.py` l.797). A **lacuna de UX** (ausência de toast de erro no frontend) é mérito real e deve ser corrigida em qualquer caso |
| F-03 — Falha DJEN na Central de Diagnóstico | **Observação de produção; causa não determinável sem logs** | Na homologação (M13), a captura retorna 503 claro quando a feature está desligada (`DJEN_INGEST_ENABLED=false`), comportamento esperado. Se em produção a feature estiver ativa e falhando, a recomendação do relatório (contenção manual no PJe + investigação de logs do worker) é a correta |
| F-04 — Scheduler anpd/normas_rfb em atenção | **Plausível; fonte externa** | Mesma natureza de F-03: exige logs do scheduler. A recomendação (verificar mudança de URL/formato das fontes) é tecnicamente adequada |
| F-05 — Travamento da interface (freeze) | **Plausível; requer reprodução controlada** | Não verificável no backend; coerente com processamento síncrono pesado no frontend (lista de clientes + lote de 153 notificações). A recomendação de profiling e virtualização é correta |
| F-06 — Contas HOMOLOG-* Superadmin ativas | **Verdadeiro (produção)** | Não aplicável ao nosso sandbox de homologação (usuários `ejc_qa_auth_*`), mas verdadeiro sobre produção. Recomendação de desativação é a correta e alinhada ao princípio de menor privilégio |
| F-07 — Dados fictícios acumulados sem expurgo | **Verdadeiro (produção)** | Mesma natureza de F-06. A rotina de limpeza pós-homologação é uma pendência operacional real; a execução deve seguir a regra do projeto: diagnóstico + aprovação prévia do Dr. Clovis antes de qualquer exclusão |
| F-08 — Parte contrária não vira registro estruturado | **CONFIRMADO no código** | A criação de caso pela Entrada Única grava `parte_contraria` como texto livre no registro do caso (`clients.py` l.189/277), sem criar registro estruturado na entidade de Partes (`case_partes.py`). É feature request legítima e bem fundamentada: peças, procurações e verificação de conflito perdem a parte contrária |
| F-09 — KPIs não atualizam em tempo real | **Plausível (frontend)** | Comportamento de cache de agregados; baixo risco, correção simples de invalidação de estado |
| F-10 — Timeline "Data Não Informada" | **CONFIRMADO — causa raiz identificada** | O backend retorna a coluna derivada `COALESCE(data_evento, created_at) AS "quando"`, mas o frontend (`DashboardUltra.tsx` l.748) lê `data_movimento \|\| created_at \|\| data` — **nenhum desses campos existe no payload**. Severidade média do relatório é correta; correção trivial de mapeamento |
| F-11 — Selo de confiança em campos vazios | **Plausível (frontend)** | Não verificável sem acesso à tela; recomendação de suprimir o selo em campo vazio é correta |
| F-12 — Toast expõe rota interna | **CONFIRMADO no código** | `cases.py` l.392 devolve a mensagem "Use POST /cases/{id}/arquivar" com verbo HTTP e caminho técnico, exibida verbatim ao usuário. Achado com mérito: exposição de superfície de API em mensagem de negócio. Corrigir com texto de negócio e detalhe técnico apenas em log |
| F-13 — "Seguro & Conforme" não navegável | **Plausível (UX)** | Ajuste de affordance; sem impacto funcional |
| F-14 — Google Fonts 503 | **Verdadeiro como observação** | Dependência externa redundante (fonte local já é carregada); self-hosting é a recomendação correta |
| F-15 — CPF sem máscara na listagem | **CONFIRMADO — achado mais relevante do relatório** | A listagem `GET /clients/` serializa `cpf_plain`/`cnpj_plain` decifrados via `ClientResponse` (`schemas/client.py` l.189–208), expondo o documento completo a qualquer perfil com acesso de leitura à listagem, enquanto a busca global já mascara. Inconsistência real com o princípio de minimização da LGPD (art. 6º, III); corrigir com mascaramento na listagem e exposição completa somente na ficha individual com gate de titularidade |
| F-16 — 153 notificações sem agrupamento | **Feature request legítima** | Baixo risco; recomendável para a saúde do recurso |

Os pontos positivos P-01 a P-08 (validação de CPF com dígito verificador, HITL, soft-delete com motivo, lixeira, mascaramento na busca global, Central de Diagnóstico, ausência do módulo de licitações no manifesto) são **coerentes com a homologação executada**, que comprovou os mesmos comportamentos (validações de DV no M08, auditoria e lixeira no M07/M12, mascaramento na busca no M06/M22).

## 3. Revisão da classificação de severidade

A metodologia e a evidência do relatório são adequadas, mas a classificação dos três críticos merece revisão à luz do desalinhamento de versão: **F-01 e F-02 não são defeitos do sistema**, e sim sintomas de produção desatualizada — severidade real na produção enquanto o deploy não ocorre, mas **criticidade do código: nenhuma**. O único "crítico" que permanece com mérito de urgência é **F-03**, pela natureza do risco (perda de prazo processual), cuja contenção manual recomendada pelo próprio relatório deve ser executada de imediato independentemente de qualquer correção. Em contrapartida, **F-15 merece elevação para severidade alta**: a exposição de CPF/CNPJ decifrado na listagem é violação do princípio de minimização da LGPD, não mero incômodo de UX.

## 4. Plano de ação recomendado (consolidado)

| Prioridade | Ação | Responsável técnico |
|---|---|---|
| Imediata | Executar a contenção manual do F-03: verificar intimações pendentes nos últimos dias diretamente no PJe/DJEN e revisar logs do worker de captura | Equipe jurídica + infra |
| Imediata | Fazer o **deploy da branch homologada** (`homologacao-m07-2026-08-16`) à produção e retestar F-01 e F-02 (espera-se que ambos desapareçam) | Infra |
| Curto prazo | Correções pontuais confirmadas: F-10 (mapeamento `quando` na timeline), F-12 (mensagem de negócio no bloqueio de exclusão), F-08 (criar registro estruturado de parte contrária na confirmação da Entrada Única) | Desenvolvimento |
| Curto prazo | F-15: mascaramento de CPF/CNPJ na listagem de clientes, com revelação completa restrita à ficha individual (gate de titularidade) | Desenvolvimento |
| Curto prazo | F-06/F-07: levantamento formal dos registros e contas HOMOLOG-* em produção, com expurgo/desativação mediante aprovação do Dr. Clovis, preservando trilha de auditoria | Desenvolvimento + gestão |
| Médio prazo | F-05 (profiling do freeze), F-04 (logs das fontes anpd/normas_rfb), F-09/F-11/F-13/F-14/F-16 | Desenvolvimento |

## 5. Conclusão

O relatório de auditoria é **confiável, bem evidenciado e útil**, e deve ser tomado como base de ação. Sua única limitação relevante é não distinguir o estado da produção em execução do estado do código corrente homologado hoje — consequência direta da pendência de push/deploy. Após o deploy da branch homologada, os três achados críticos perdem dois de seus pilares (F-01 e F-02), restando como urgente apenas a contenção do F-03 (DJEN). Recomendo ainda a correção dos quatro achados confirmados no código (F-08, F-10, F-12, F-15), com atenção especial ao F-15, cuja elevação de severidade sugiro pela implicação direta de LGPD. Se desejar, posso executar as correções confirmadas (F-10, F-12, F-15 e F-08) e preparar o expurgo formal do F-07 para sua aprovação.
