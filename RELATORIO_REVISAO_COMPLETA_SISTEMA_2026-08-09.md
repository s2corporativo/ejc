# Relatório de Revisão Completa do Sistema — EJC (2026-08-09)

**Origem**: pedido do titular por chat — avaliar o sistema inteiro sob duas lentes: engenharia de software e usuário final (advogado), percorrendo todos os módulos, identificando o que está quebrado, o que falta e o que consolidar com urgência. Issue #979.

**Método**: seis frentes de auditoria executadas em paralelo sobre `main@ffc9cbb`:
1. **Stack ao vivo** — a aplicação completa foi subida do zero neste ambiente (PostgreSQL 16 + pgvector, Redis, migrations até `138_consolida_fontes_ingestao`, seeds, backend uvicorn, frontend Vite) e percorrida via navegador (Playwright/Chromium) com dados fictícios: login → clientes PF/PJ → caso → prazos → documentos → financeiro → portal do cliente → IA. 65 screenshots produzidos.
2. **Backend** — auditoria estática de `backend/app` (arquitetura, transações, superfície de API, robustez).
3. **Frontend** — auditoria estática de `frontend/src` (registry, chamadas de API, status, qualidade, UX estrutural).
4. **Segurança** — auth/2FA, RBAC/IDOR, uploads, PII/LGPD, segredos, CORS/nginx, SQLi/SSRF.
5. **Testes/CI** — execução real das suítes e análise dos workflows.
6. **Estado do produto** — plano de lançamento v3 × realidade do código, PRs abertos, migrations.

**Limitações**: IA avaliada com provedores OFF (sem chave real); Celery/DJEN/DataJud não exercitados; produção não foi acessada (regra 9 da governança) — afirmações sobre produção vêm de documentos e evidências de PRs, não de inspeção direta.

---

## 1. Sumário executivo

O EJC de agosto/2026 é um sistema **muito melhor do que o retratado na auditoria externa de julho**. As suítes de teste estão verdes (5.068 testes backend, 446 frontend, 0 falhas), o caminho feliz do fluxo jurídico (cliente → caso → prazo → documento → portal) **funciona de ponta a ponta e é agradável**, a segurança está madura (IDOR do portal fechado, PII de clientes cifrada, SSRF/SQLi/uploads bem tratados, HITL enforçado em código com lock e hash), e vários defeitos históricos confirmados em produção — `?status=all` → 500, prefixo `/v1/v1/` duplicado, conversão que perdia `descricao_fatos` — **não se reproduzem mais no código atual**.

Os problemas de hoje são de outra natureza, e são três:

1. **Bugs pontuais no meio do fluxo diário** — dois críticos encontrados na avaliação ao vivo (tela branca ao criar caso com CNJ inválido; despesa com vencimento → 500) que qualquer advogado encontraria na primeira semana de uso.
2. **O funil de integração está entupido** — 27 PRs de produto abertos, GitHub Actions com falha de infraestrutura (issue #976, "não mesclar PRs novos"), e **três PRs incompatíveis entre si reescrevendo a mesma Entrada Única** (#805, #949, #957). É a causa-raiz de julho ("trabalho pronto que não chega ao ar") se reinstalando por outro mecanismo.
3. **A tensão estratégica não resolvida entre subtração e adição** — a auditoria e o plano v3 mandaram cortar (Victory Vault, jurimetria, sociedade, 163 skills, 25 áreas → 2); o repositório entregou reorganização + adição (tudo saiu do menu, quase nada saiu do código, e no mesmo ciclo nasceram 4 verticais premium novos e o DPT360). O critério de lançamento — *um advogado leva um caso real ao protocolo e acha mais fácil que fazer fora* — **nunca foi exercido** (Bloco 7 não iniciado).

---

## 2. Avaliação como usuário (stack real, dados fictícios)

### 2.1 Estado por módulo

| Módulo | Estado | Evidência |
|---|---|---|
| Login + troca de senha obrigatória | ✅ Funciona | Fluxo forçado no 1º login, toast claro |
| Dashboard Início | ✅ Funciona | Onboarding "Primeiros passos 0/4"; banner honesto de IA desativada |
| Clientes (PF + PJ) | ⚠️ Funciona, contadores defasados | Cards TOTAL/PJ não invalidam após criação (corrigem-se minutos depois) |
| Casos — criação (wizard) | 🔴 **Quebra em erro de validação** | CNJ inválido → 422 → **tela branca total**, dados perdidos (bug 1) |
| Casos — detalhe/jornada | ✅ Funciona | Máquina de estados, saúde do caso, jornada |
| Casos — mudança de status | ⚠️ Só via API | Badge "Aberto" não é clicável; não há controle de status na UI do caso |
| Kanban (Quadro) | ⚠️ Confuso | Colunas "Triagem/Em andamento/Aguardando prazo/Acordo" ≠ estados reais da migration 126; caso `em_instrucao` cai em "Triagem" |
| Agenda e Prazos | ✅ Funciona | Prazo e tarefa criados; intimações degradam com toast claro ("Configure sua OAB") |
| Documentos (upload + vínculo) | ✅ Funciona | Upload 201, vínculo confirmado; "0 KB" para arquivo pequeno (arredondamento) |
| Financeiro — honorários | ⚠️ Funciona, sem vínculo a caso | Lançamento nasce com `case_id=null` — não há campo de caso no form |
| Financeiro — despesas | 🔴 **Quebrado** | POST com `vencimento` preenchido → **500** (bug 2) |
| Portal do cliente | ✅ Funciona (destaque positivo) | Acesso, troca de senha, casos/financeiro/mensagens/documentos isolados e corretos |
| Sala Jurídica | 🔴 Degrada mal sem IA | Mensagem fica sem resposta e sem erro visível (422 silencioso) |
| Pesquisa e IA | ✅ Degrada bem | Banner "IA não ativada"; ferramentas determinísticas seguem |
| Peças | ✅ Funciona | Templates gerados na criação do caso; HITL/"Sem Validação" preservado |
| DPT Empresarial 360 | ✅ Funciona (vazio honesto) | Explica cada zero |
| Central de Diagnóstico | ⚠️ Funciona, com duplicatas | "Infosimples" 2×, "Índices BCB" 2× — payload do backend traz ids repetidos |

### 2.2 Bugs encontrados (com reprodução)

1. **[CRÍTICO/UX] Tela branca total no erro de validação da criação de caso.** Casos → Cadastro manual → CNJ com dígito inválido → "Criar caso". O 422 do Pydantic vem como *array* em `detail`; `frontend/src/components/NovoCasoWizard.tsx:271` passa esse array direto para `toast.error(...)` → crash de render do React → página branca e formulário perdido. O advogado copia o número do PJe com um dígito errado e conclui que "o sistema caiu". Correção: validar CNJ no campo antes do submit + tratar `detail` array no toast (o padrão correto já existe em outros forms).
2. **[CRÍTICO/backend] `POST /api/despesas` com `vencimento` (ou `pago_em`) → 500.** `backend/app/routers/despesas.py:168-204` (`create_despesa`) usa `body: dict` sem schema Pydantic e passa a string ISO crua para coluna DATE via asyncpg (`'str' object has no attribute 'toordinal'`). Como a UI sempre envia o campo quando o usuário preenche "Vencimento", **toda despesa com vencimento falha**. Mesmo padrão provável no PATCH. Nota: é exatamente a rota do bug `/v1/v1/` de julho — e é um dos domínios **sem nenhum teste** (§5.2).
3. **[UI] Botão "Ações do caso" fica atrás do widget "Primeiros passos"** (ambos `fixed` bottom-right) — o clique é interceptado enquanto o onboarding não some.
4. **[UX] Sala Jurídica falha em silêncio sem IA** — o backend responde 422 com mensagem útil ("Nenhum provedor de IA está configurado"), mas a UI não exibe nada; a mensagem do usuário fica no chat sem resposta.
5. **[Dados] Central de Diagnóstico com subsistemas duplicados** (ids `infosimples` e `indices_bcb` repetidos no payload; React acusa keys duplicadas). Confirma o achado da auditoria externa sobre divergência interna dos painéis de diagnóstico.
6. **[Menor]** Contadores de Clientes/Casos não invalidam após criação; "Data Não Informada" na timeline do Início para caso recém-criado; documento do portal rotulado "Arquivado em" quando significa "enviado em"; "0 KB" na lista de documentos; CPF/CNPJ sem máscara na lista de clientes; inputs de data em formato americano (`mm/dd/yyyy`) sob locale en — forçar pt-BR.

### 2.3 Defeitos históricos que NÃO se reproduzem mais (confirmado ao vivo)

- `?status=all` / `ativo` → 500: hoje o backend devolve **422 explicativo** com a lista de valores aceitos (`backend/app/routers/cases.py:118-132`); a UI envia `?arquivo=ativos|arquivados` (200).
- Prefixo duplicado: `/api/despesas` 200, `/api/v1/despesas` 200, `/api/v1/v1/despesas` **404** — o rewrite único do `core/api_version_middleware.py` eliminou a classe.
- Conversão Sala → Caso perdendo `descricao_fatos`: corrigida (commit `feddbebd`); conversão judicial hoje é atômica em um único commit (`services/conversao_caso.py:259-332`).

### 2.4 Avaliação de UX (lente do advogado)

**Pontos fortes**: onboarding com 4 tarefas; wizard que busca cliente por CPF antes de criar (evita duplicata); "Próxima ação" obrigatória; jornada derivada de artefatos; portal do cliente limpo com pendências à vista; avisos de IA/HITL em linguagem OAB-correta; degradação quase sempre honesta quando integrações estão OFF.

**Atritos estruturais**:
- **6 portas para "começar um caso"**: `/entrada`, `/casos/novo`, `/cadastro-manual`, Sala Jurídica (conversão), Raio-X, e o componente global `EntradaUniversalGlobal`. É decisão demais para o primeiro dia — e é exatamente o que o Bloco 3.1 do plano deveria resolver (parado em 3 PRs incompatíveis, §6.1).
- **3–4 superfícies de IA lado a lado** (Sala Jurídica, Inteligência, Raio-X, DPT360 como `essential`): usuário novo não sabe onde perguntar.
- **A máquina de estados do caso — coração do produto — não tem controle na UI**: badge parece clicável e não é.
- **Kanban fala uma terceira língua** desconectada dos 4 estados canônicos.
- **Vínculos fracos**: prazo rápido e honorário nascem sem `case_id` — alimenta a classe "gravação não vinculada" que a auditoria já apontou.

**Veredito frente ao critério de lançamento**: o caminho feliz existe e é bom; os bugs 1 e 2 estão no meio do fluxo de trabalho diário e derrubariam a confiança de qualquer advogado na primeira semana. Corrigi-los custa pouco e destrava a percepção de qualidade.

---

## 3. Avaliação de engenharia — Backend

**Números**: 164 routers (163 `include_router` manuais em `main.py` + 5 registrados por *side effect* de import em `routers/__init__.py:24-30`), 166 services, 64 models, ~830 endpoints. **81 de 164 routers definem schemas Pydantic inline** — a camada `schemas/` é minoritária na prática.

**Achados principais**:
- **~13 routers (~1.600 linhas) sem nenhum consumidor no frontend**: `matriz_teses`, `teses_v4`, `cerebro`, `diplomacia_v3`, `consumidor_monitor`, `advogado_estilo`, `prompts`, `processo_eletronico`, `radar_legislativo`, `honorarios_calc`, `jurisprudencia_externa`, `architecture`, `peca_geracao_router`. Superfície autenticável exposta sem uso = custo de manutenção + superfície de ataque.
- **Registro por efeito colateral**: 5 routers (família `entrada_universal` e `defesas_revisoes`, ~1.783 linhas) invisíveis a quem audita o `main.py` — dois mecanismos de registro coexistindo é dívida real.
- **Duplicação de domínio**: financeiro fatiado em 10 routers (honorários em 4 prefixos); colisão semântica `analise_bancaria.py` (que **não** é bancário — é análise de documento por área) × `bank_analysis.py` × `extratos.py`; 5 routers de documento, incluindo o shim `data_room_v4` auto-declarado temporário sem prazo; **duas portas de ingestão vivas** (`entrada.py` e `entrada_universal.py`).
- **Arquivo-monstro**: `ramos.py` com **4.542 linhas e 82 endpoints**.
- **Transações**: das 25 funções com 2+ commits, a maioria é correta ou deliberada (two-phase idempotente do NFSe, commit-por-item em cobrança). Risco residual: batches de ingestão presos em `processando` após crash entre commits (sem varredura de recuperação); `raio_x.py:555` e `rag.py:274` a revisar.
- **Vocabulário de status — divergência residual real**: `processes.status` usa literal `'ativo'` em SQL cru (`cases.py:424`, `conversao_caso.py:303`) sem enum Python — é a fonte da confusão que sobra (e do fallback `"ativo"` na UI).
- **Robustez**: 14 `except Exception: pass` — os 2 em `services/ai/agent/hitl_state.py` são risco de governança (engolir exceção em máquina de estado HITL). Zero IO bloqueante no event loop; N+1 relevante só em 3 rotas de baixo volume.
- **Pontos fortes a preservar**: comentários "forenses" explicando cada correção; 422 informativo em enum; HITL enforçado com `with_for_update` + revalidação de hash; reserva idempotente anti-TOCTOU no NFSe.

---

## 4. Avaliação de engenharia — Frontend

**Números**: 111 páginas, 90 componentes, 46 rotas ativas no `moduleRegistry` + 35 redirects legados, 17 itens de menu (admin). `tsc --noEmit` limpo.

**Achados principais**:
- **~2.240 linhas de código morto**: `DashboardModern.tsx` (1.416) e `DashboardPremium.tsx` (826) não são importados por ninguém — 4 dashboards no código, 1 em uso.
- **596 `any` fora de testes**, concentrados justamente na fronteira com a API (`Documentos` 27, `TabResumo` 25, `Dashboards` 24, `Pecas` 22) — anula o typecheck onde os contratos mais quebram.
- **43 catches silenciosos**, concentrados nas abas de `CasoDetalhe/` — seção some sem aviso (o padrão "tela silenciosamente vazia" criticado pela auditoria). O par `EmptyState`/`ErrorState` já existe em `UI.tsx`.
- **20+ componentes acima de 800 linhas** (`CentralAtividades` 2.036, `RaioXProcesso` 1.912…). O padrão bom já existe: `CasoDetalhe` foi fatiado em `Tab*.tsx`.
- **Metadados errados no registry**: `backendPrefixes` `/api/v1/datajud` e `/api/v1/despesas` (o real é `/api/...`) — envenenam o MapaModulos (mesma classe do achado "mapa subdetecta rotas").
- **Restos de vocabulário**: links `/casos?status=ativo` (que `Casos.tsx` ignora — parâmetro morto) e fallback `StatusBadge "ativo"` em `TabProcessos.tsx:276`.
- **Superfície dupla em uso**: todo o cliente `api` sai por `/api/v1` (rewrite no backend); as 2 chamadas cruas de auth usam `/api` legado. Regras por path (WAF/rate-limit/log no Nginx) precisam cobrir os dois prefixos até haver data de corte.
- **Ponto forte**: disciplina de API client (interceptores de 401/403 bem feitos), nenhuma chamada órfã encontrada na amostragem, 376 usos de `toast.error`, loading states em 70 páginas.

---

## 5. Segurança e Testes/CI

### 5.1 Segurança (sem achado crítico novo)

- **ALTO — CPF/CNPJ das partes do caso em texto claro**: `models/case_parte.py:20` grava e devolve cru (`routers/case_partes.py:42,65`), enquanto Client usa Fernet + HMAC cego. Mesmo tipo de dado pessoal, proteção desigual — corrigir com o padrão de `clients.py` (migration + backfill + máscara na resposta).
- **MÉDIO — refresh token (7 dias) devolvido também no corpo JSON** de `/login` e `/refresh` (`auth.py:330,508`), além do cookie httpOnly — reabre parcialmente a janela de XSS que o cookie fecha. Não emitir no corpo para o navegador.
- **MÉDIO — 2FA globalmente OFF por default** (`two_factor_policy.py`): risco residual **já aceito e registrado pelo titular** (GOVERNANCA_IA §, `SECURITY_2FA_TEMPORARY_DISABLE.md`) — registrado aqui, sem ação.
- **BAIXO**: `log_sanitizer` não mascara telefone/CEP/RG; rotas sensíveis devem depender de `get_current_user` (não só do middleware) para revogação efetiva na janela de 2h.
- **Verificado OK**: rotação de refresh com detecção de reuso, brute-force multicamada, RBAC fail-closed com `cliente_externo` confinado, matriz IDOR do portal fechada, uploads com magic bytes e path UUID, SSRF com revalidação por salto, SQLi ausente, barreira dupla de PII no `ai_gateway`, CORS/nginx endurecidos, guardas anti-produção nos runners E2E. **Pendência operacional (titular/ambiente)**: confirmar no banco de produção que nenhuma conta `homolog.qa*` está ativa e que `EJC_ALLOW_PRODUCTION_E2E` não está setada no VPS.

### 5.2 Testes e CI

- **Execução real**: backend **5.068 passed / 193 skipped / 0 failed** (178 skips são os testes de banco que rodam no CI com `RUN_DB_TESTS=1`); frontend **446 testes passed**, tsc/build/prettier limpos.
- **O CI é mais forte do que o CLAUDE.md descreve** (ruff e pip-audit são *bloqueantes*, há `--cov-fail-under=65`, Playwright real e prova de backup/restore no `continuity-ui-gates`) — a seção CI/CD do CLAUDE.md está desatualizada.
- **Gap nº 1 — financeiro sem testes**: nenhum teste para `despesas`, `office-contracts`, `partner-withdrawals` — exatamente onde o bug 2 (500 do vencimento) vive e onde o `/v1/v1/` de julho foi confirmado. Correlação direta entre ausência de teste e defeito.
- **Gap nº 2 — E2E fora do CI**: `run_fictitious_smoke.py` não é invocado por nenhum workflow; só há smoke pós-merge em staging. Um PR pode quebrar o fluxo ponta a ponta sem travar nada.
- **Gap nº 3 — fakes locais não pegam a classe transacional**: 98 arquivos com `_FakeDB` aceitam qualquer sequência de commits; os 41 arquivos `_dblevel` (que pegam) estão mal distribuídos — quase nenhum no financeiro.
- Higiene: teste de Sentry deixa client global ligado (atexit tenta rede em toda execução); instalação em Debian limpo exige contornos não documentados (`--ignore-installed` para setuptools/cryptography; `python -m pytest`).

---

## 6. O que consolidar com urgência

### 6.1 O funil de integração (o problema nº 1 do momento)

1. **GitHub Actions com falha de infraestrutura** (issue #976: jobs encerrando antes do 1º step, sem logs; diretiva "não mesclar PRs novos"). Enquanto durar, os 27 PRs de produto acumulam *drift* contra a `main` diariamente. **É a causa-raiz de julho — trabalho pronto que não chega ao ar — se reinstalando.** Destravar isso vem antes de qualquer outra coisa.
2. **Três PRs incompatíveis sobre a mesma Entrada Única**: #805 (superseded, 81 commits atrás, 6 regressões conhecidas — **fechar**), #949 (gateway que preserva `/sala-juridica` e `/raio-x`) e #957 (superfície única que os absorve e esconde). #949 e #957 são incompatíveis por construção e ambos criam `EntradaRelato.tsx` → conflito garantido em `EntradaUnica.tsx`, `moduleRegistry.tsx` e nos 4 manifests de rota. **Escolher UM desenho, fechar os demais**, e só depois deixar entrar #965 (migration 139) e #960 (Empresarial→DPT360, que sobrepõe #957). O relatório de consolidação de 29/07 já havia medido esse mesmo padrão e ordenado "não execute merges em paralelo".
3. **RAG de vigência encadeado em 3 PRs** (#895 → #952 → #977) travado por uma prova de deploy que não existe — resolver a dependência de ambiente ou desfazer o encadeamento.

### 6.2 Migrations

- Head da `main`: **138**. Números pulados: 128, 129, 133–137 (restos de reservas; PR #679 draft ainda aberto exige reconciliação).
- **`MIGRATION_RESERVATIONS.md` está mentindo**: lista a 130 como "a abrir" quando ela já está na `main` — e a única função da tabela é evitar colisão. A 139 (PR #965) está reservada só na issue, não na tabela. **Atualizar a tabela é correção de 10 minutos que evita a próxima colisão.**
- **Incógnita produção**: evidência do PR #819 sugere produção possivelmente em `131` — 7 revisões atrás da `main`. Confirmar `alembic current` no servidor **antes** de a 139 entrar (ato do titular/esteira; vedado ao executor pela regra 9).

### 6.3 A decisão de produto que ninguém tomou

A auditoria mandou **subtrair**; o ciclo entregou **reorganização + adição**: Victory Vault, jurimetria (reforçada!), sociedade, `/noticias`, 163 skills e 26 áreas continuam todos no código — só saíram do menu — e nasceram 4 verticais premium + DPT360. Dois documentos oficiais do repo apontam em direções opostas (`plano-lancamento-v3.md`: "na dúvida, remova" × `RELATORIO_ESTADO_PRODUTO.md`: catálogo de diferenciais premium). **Essa tensão precisa ser decidida pelo titular, não descoberta por cada agente a cada tarefa.** Dois itens têm urgência própria:
- **`gerar_dossie_pressao()` continua vivo** em `services/diplomacia_digital.py:58` (e o router `diplomacia_v3` registrado), contra decisão expressa registrada de remoção por risco reputacional/disciplinar.
- **Gate "chance de êxito nunca no portal" é verdade por acidente**: a métrica vive em 9 arquivos e não há teste de contrato garantindo que ela não serialize em `/portal/*`. Um teste fecha a exceção "não negociável" da auditoria.

### 6.4 Bloco 7 — o teste que decide se o produto existe

Nenhuma passagem humana ponta a ponta foi registrada; o substituto sintético (#967) está aberto. Tudo acima serve a isso: **destravar o funil → mesclar a Entrada escolhida → corrigir os bugs 1 e 2 → e então o titular leva um caso real do início ao protocolo.**

---

## 7. Recomendações priorizadas

### P0 — esta semana (destravam confiança e fluxo)
1. Destravar o GitHub Actions (issue #976) — pré-requisito de tudo.
2. Corrigir **bug 1** (tela branca no 422 do wizard de caso — `NovoCasoWizard.tsx:271` + validação de CNJ no campo) e **bug 2** (500 em despesas com vencimento — schema Pydantic em `despesas.py:168-204`), cada um com teste de regressão (`_dblevel` para o 2).
3. Decidir o desenho da Entrada Única (#949 × #957), fechar #805.
4. Atualizar `MIGRATION_RESERVATIONS.md` (130, 139, liberar 128/129/133–137).
5. Teste de contrato "chance de êxito nunca em `/portal/*`".
6. Mesclar os PRs isolados de baixo risco já prontos (#973 timesheet, #975 guards, #703 decadência — este último o plano exige antes de peça a protocolo).

### P1 — este mês (qualidade estrutural)
7. Cifrar CPF/CNPJ de `case_partes` (padrão `pii_crypto`, migration + backfill + máscara).
8. Sala Jurídica: exibir o erro 422 ao usuário; controle de status do caso na UI; Kanban falando o vocabulário dos 4 estados; campo "caso" em prazo rápido e honorário.
9. Testes `_dblevel` para o financeiro (despesas, office-contracts, partner-withdrawals, parcelas) + smoke E2E no CI contra stack efêmera.
10. Excluir `DashboardModern`/`DashboardPremium` (~2.240 linhas mortas); corrigir `backendPrefixes` do registry; remover `?status=ativo` e fallback `"ativo"`; deduplicar ids da Central de Diagnóstico.
11. Auditar os 43 catches silenciosos das abas de `CasoDetalhe/` → `ErrorState`.
12. Refresh token fora do corpo JSON para clientes web; eliminar `except: pass` de `hitl_state.py` e `status_transicao.py`.

### P2 — trimestre (dívida e subtração)
13. Decidir destino dos ~13 routers sem consumidor e do shim `data_room_v4` (telemetria `route_usage` → remover); unificar o registro de routers (fim do side effect).
14. Enum Python para `processes.status`; fatiar `ramos.py` (4.542 linhas) e os 2 maiores componentes do frontend; migrar schemas inline → `schemas/` começando por portal e financeiro.
15. Fixar data de corte da superfície legada `/api`; tipar as fronteiras de API dos 5 arquivos com mais `any`.
16. Atualizar CLAUDE.md (CI bloqueante real, `jornada_caso.py` inexistente) e documentar setup local sem Docker.

---

## 8. Decisões que exigem o titular

| # | Decisão | Contexto |
|---|---|---|
| 1 | **Subtração × adição**: ratificar ou revogar formalmente os cortes do parecer arquitetural (Victory Vault, jurimetria, sociedade, skills, áreas) | §6.3 — dois documentos oficiais em direções opostas |
| 2 | **Desenho da Entrada Única**: #949 (gateway) ou #957 (superfície única) | §6.1 — incompatíveis por construção |
| 3 | **Remoção física do dossiê de pressão** (`diplomacia_digital.py`) | Decisão já registrada, execução pendente |
| 4 | **Atos de ambiente**: `alembic current` em produção; conta `homolog.qa*` inativa; `EJC_ALLOW_PRODUCTION_E2E` ausente; limpeza `HOMOLOG-FICTICIO-*`; cadastro das OABs para o DJEN | Regra 9 — vedados ao executor |
| 5 | **Bloco 7**: agendar a passagem de um caso real ponta a ponta | Critério de lançamento nunca exercido |

---

## 9. Registro de execução (governança, regra 10)

- **Arquivos alterados**: apenas este relatório. Nenhum código de produção tocado; nenhum arquivo de PR aberto modificado. (A stack local criou `backend/.env` de desenvolvimento, não versionado.)
- **Comandos/testes executados**: `pytest` backend completo (5.068 passed/0 failed), `npm run lint`/`test`/`build` frontend (todos verdes), `alembic upgrade head` até 138 em Postgres+pgvector local, stack completa exercitada via navegador com dados fictícios (65 screenshots, retidos no ambiente de execução).
- **Riscos residuais**: achados de produção não verificados in loco (regra 9); IA/Celery/integrações não exercitados com credenciais reais; a checagem de paths de API do frontend foi por amostragem.
- **Fora do escopo → Issues novas**: cada item P0/P1 deve virar Issue própria antes da correção (este PR não corrige nada).
