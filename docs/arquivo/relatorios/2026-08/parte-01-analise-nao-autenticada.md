# Auditoria Técnica do EJC — Ecossistema Jurídico Clovis
**Ambiente auditado:** https://ejc.depaulateixeira.adv.br (produção)
**Data:** 29/07/2026
**Executor:** auditoria técnica remota (arquiteto-ejc)

---

## 0. Metodologia e limitação de acesso — leitura obrigatória antes das conclusões

Duas rotas de acesso planejadas não puderam ser executadas por restrição de rede do ambiente de execução, não por falha do EJC:

- **SSH (`root@13.140.167.153:22`)**: a porta 22 está bloqueada na saída deste ambiente para qualquer destino (testado inclusive contra `github.com:22`, com o mesmo resultado — timeout). Não é uma falha da sua VPS; é uma política de rede do meu sandbox.
- **Navegador headless (Playwright/Chromium)**: bloqueado ao tentar sair para domínios externos, mesmo com proxy explícito. Também não é falha do EJC.

Em razão disso, **não realizei login nem naveguei visualmente pelas telas como um advogado autenticado faria**. O que segue é uma auditoria técnica de caixa-cinza feita por engenharia reversa responsável do build de produção publicamente servido: leitura do HTML, dos bundles JavaScript (não ofuscados, apenas minificados — texto de interface, rotas e strings de ajuda são legíveis), e testes diretos e não-destrutivos contra a API REST pública (`/api/v1/...`), incluindo cabeçalhos de segurança, CORS, validação, rate limiting e enumeração de usuário.

**Isso não substitui uma auditoria funcional completa.** Para validar comportamento real de tela (renderização, responsividade, fluxos de clique, mensagens de erro em formulário, tempo de resposta percebido), preciso de uma destas alternativas:
1. Credenciais de aplicação (e-mail/senha de um perfil **Advogado**) para eu operar a API autenticada simulando o uso real, endpoint a endpoint; ou
2. Acesso ao código-fonte (repositório Git); ou
3. Gravação de tela / screenshots de uma sessão real sua no sistema.

Tudo abaixo é **verificável e rastreável** a partir do build público — nenhum dado foi presumido.

---

## 1. Mapa de módulos identificados (evidência: chunks carregados sob demanda pelo router)

O sistema carrega **54 páginas/módulos distintos** via lazy-loading. Agrupados por função:

**Operação do caso:** Dashboard, Casos, CasoDetalhe, JornadaCaso (9 etapas: Cliente → Triagem → Documentos → Inteligência → Estratégia → Produção → Revisão → Protocolo → Gestão), DossieCliente, RaioXProcesso, Checklists, Workflow, CaseBreadcrumb.

**Cliente e captação:** Clientes, CRMLeads, CadastroManual, EntrevistaInteligente (triagem por relato livre com IA).

**Prazos e comunicações:** Prazos, Intimacoes, Suspensoes, DiarioOficial, DataJudBusca (integração CNJ).

**Documentos:** GestaoDocumental, Pecas, Assinaturas, PortalAssinaturas (assinatura eletrônica com base legal MP 2.200-2/2001).

**Financeiro:** FinanceiroWorkspace, Dashboards.

**Portal do cliente externo:** PortalDashboard, PortalCasos, PortalCasoDetalhe, PortalDocumentos, PortalFinanceiro, PortalMensagens.

**IA jurídica e governança:** InteligenciaWorkspace, GovernancaIA (curadoria RAG, prompts sistêmicos, guardrails, revisão por advogado), PainelProvedoresIA (custo/latência/fallback entre Anthropic, Maritaca, Groq, Ollama), Prompts, SalaJuridica.

**Compliance e regulatório:** RadarCompliance, RadarRegulatorio, Noticias, Infosimples.

**Administração:** Usuarios, Configuracoes, Configurar2FA, Auditoria, Lixeira (soft delete com restauração), MapaModulos (inventário cruzado frontend×backend), CentralDiagnostico, Central.

**Produtividade:** Produtividade, Tarefas, Ferramentas (atalhos para PJe-Calc, Registrato/BACEN, Meu INSS, e-CAC, Consumidor.gov), RamosHub, RamoBase.

**Conta:** RecuperarSenha, RedefinirSenha, TrocarSenha, Ajuda, NotFound.

Este escopo é significativamente maior do que o descrito como "módulos ativos" na documentação interna do agente EJC (que lista apenas clientes, prazos, peças, honorários, CRM, financeiro, logs). **A documentação de contexto está desatualizada frente ao sistema real** — primeiro achado prático: qualquer decisão tomada com base só na ficha técnica do agente vai subestimar o sistema.

---

## 2. Pontos fortes — o que efetivamente ajuda um advogado

Com base no conteúdo real do módulo de Ajuda (textos de interface, não markdting genérico) e na arquitetura observada:

- **Desenho por jornada, não por CRUD solto.** A "Jornada do Caso" em 9 etapas (Cliente → Triagem → ... → Gestão) é uma modelagem de processo de trabalho real de escritório, não apenas telas de cadastro. Isso é raro em sistemas jurídicos genéricos e tem valor prático real para reduzir etapa esquecida.
- **Governança de IA com enquadramento correto.** O texto de ajuda declara explicitamente: *"A IA é apoio analítico e nunca promete resultado — sempre revise antes de usar em peças ou orientações"* e *"Toda resposta é rascunho sujeito a revisão humana (HITL)"*. Isso está alinhado ao Provimento 205/2021 da OAB (uso de IA na advocacia) e ao dever de revisão humana já fixado como princípio no DNA do agente EJC. Há também trilha de auditoria de uso de IA (módulo Auditoria + Governança da IA), o que é exigível para rastreabilidade.
- **Assinatura eletrônica com base legal correta.** O texto cita MP 2.200-2/2001 e registra identificação, data/hora, IP e hash como comprovante — é a fundamentação jurídica adequada para assinatura eletrônica simples no Brasil.
- **Integração com fonte pública oficial (DataJud/CNJ)** para sincronizar andamentos processuais, evitando conferência manual tribunal a tribunal — ganho de tempo real e verificável.
- **Portal do cliente separado do painel interno**, com documentos, financeiro e mensagens próprios — reduz a carga de "advogado respondendo e-mail de status" e é uma diferença estrutural real frente a planilha/e-mail.
- **Lixeira com restauração** (soft delete) para clientes, casos, prazos e documentos — proteção correta contra exclusão acidental, algo que sistemas jurídicos simples frequentemente não implementam.
- **Segurança de API sólida e verificável nesta auditoria:**
  - Autenticação obrigatória em endpoints sensíveis (`401` com mensagem clara quando token ausente).
  - Mensagem de erro de login genérica (não revela se o e-mail existe).
  - Endpoint de recuperação de senha **não permite enumeração de usuário** (`"Se o e-mail existir, enviaremos as instruções em breve."` independentemente do e-mail testado).
  - **Rate limiting real e funcional**: 5 tentativas de login e 5 solicitações de recuperação de senha em sequência resultam em `429 Too Many Requests` — testado e confirmado nesta auditoria.
  - CORS restritivo (origem não autorizada recebe `400 Disallowed CORS origin`).
  - Cabeçalhos de segurança presentes de forma consistente: `Strict-Transport-Security`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` restritiva (`script-src 'self'`), `Referrer-Policy`.
  - Documentação automática do FastAPI (`/docs`, `/redoc`, `/openapi.json`) **não está exposta publicamente** — postura correta para produção.
  - Fonte tipográfica auto-hospedada, evitando requisição a `fonts.googleapis.com` a partir do próprio código (boa prática de minimização de dados para LGPD, citada no próprio HTML).

---

## 3. Falhas, riscos e inconsistências identificados (evidenciados)

### 3.1 — Referência residual a "Licitações" em duas listas de área jurídica
O DNA técnico do agente EJC determina remoção de **qualquer** referência a licitações. Encontrei a chave `licitacoes` / rótulo `"Licitações"` em duas listas de área/ramo jurídico:
- `CadastroManual` (cadastro manual de caso): lista local termina em `{k:'licitacoes', l:'Licitações'}`.
- `RaioXProcesso`: lista local contém `['licitacoes', 'Licitações e Contratos']`.

**Ressalva técnica importante:** isso **não** é o módulo de radar de licitação/PNCP/pregão que o DNA manda excluir — é uma *tag de área de atuação jurídica* (ao lado de "Direito Administrativo", "Societário" etc.), plausivelmente para casos em que o escritório atua **defendendo ou assessorando em disputas envolvendo licitação** (ex.: impugnação de edital, defesa em sanção administrativa), o que é atividade advocatícia legítima e distinta de "sistema de licitação". Ainda assim, **é uma decisão que precisa ser tomada por vocês, não presumida por mim**: se a intenção do golden rule era remover *qualquer menção*, isso deve ser retirado; se a intenção era remover apenas o módulo de gestão licitatória (radar/PNCP), isso pode ficar. Recomendo decisão explícita e documentada, para não haver ambiguidade em auditorias futuras.

### 3.2 — Lista de áreas jurídicas duplicada em 5 lugares diferentes (risco de manutenção)
Existe um módulo central `areaCatalog` com 24 áreas (Cível, Trabalhista, Consumidor... não inclui "Licitações"). Porém **5 outros módulos redefinem sua própria lista local** em vez de importar o catálogo central: `CadastroManual`, `FinanceiroWorkspace`, `RaioXProcesso`, `RamoBase`, `RamosHub`. 

Isso já causou divergência real e observável: "Licitações" existe em 2 dessas listas locais mas não no catálogo central. Cada nova área jurídica cadastrada exige edição manual em até 6 arquivos, com risco concreto de inconsistência entre telas (ex.: uma área aparecer no formulário de cadastro mas não no filtro do Raio-X, ou vice-versa). É um débito técnico de arquitetura, não um bug pontual — recomendo consolidar em `areaCatalog` como fonte única de verdade.

### 3.3 — Navegação principal esconde módulos administrativos (achado confirmado pelo próprio texto de ajuda do sistema)
O texto de ajuda do próprio EJC declara: *"Vários módulos administrativos (Auditoria, Governança da IA, Produtividade) são alcançados pelos atalhos do Dashboard, mesmo estando fora do menu lateral."*

Isto é uma admissão de falha de descobribilidade (discoverability) pelo próprio produto: um advogado que não souber previamente que esses atalhos existem no Dashboard não vai encontrar Auditoria, Governança da IA ou Produtividade navegando pelo menu lateral — que é o comportamento padrão esperado de navegação. Para um usuário de primeira viagem (exatamente o cenário que você pediu para simular), isso é atrito real: módulos de compliance e auditoria de IA (que deveriam ser altamente visíveis, dado o compromisso do escritório com conformidade OAB/LGPD) ficam escondidos atrás de atalhos não óbvios.

### 3.4 — Funcionalidade anunciada mas não entregue, sem aviso prévio na navegação
Dentro do Dossiê do Cliente, o sistema exibe (é o próprio texto do sistema, não inferência minha): *"[a análise estratégica automática do histórico deste cliente (padrões de litígio, riscos financeiros e oportunidades)] ainda está em desenvolvimento. Enquanto isso, use a Pesquisa e IA com o caso do cliente selecionado."*

Tecnicamente correto informar isso ao usuário no momento do clique — mas o problema de UX é anterior: se o item aparece como opção clicável no menu do Dossiê sem indicação visual de "beta/em construção" *antes* do clique, o advogado perde um passo indo até lá para descobrir que não está pronto. Recomendo sinalizar status ("em desenvolvimento") diretamente no item de menu, e não apenas na tela de destino — o próprio módulo `MapaModulos` já modela isso internamente (status `ativo/beta/legado/oculto`), então a capacidade de sinalizar já existe no sistema; falta aplicá-la de forma visível na navegação, não só no painel administrativo.

### 3.5 — Versão de build não identificável em produção
`GET /api/v1/health` retorna `{"status":"ok","version":"dev","uptime_seconds":...,"environment":"production"}`. Ou seja: em ambiente de produção, o campo `version` está fixo em `"dev"` — a esteira de deploy não está gravando a versão/commit real da build. Isso é um problema operacional relevante para vocês, não para o advogado usuário: em caso de incidente, não há como correlacionar rapidamente "qual versão está no ar" com "qual commit/PR", dificultando rollback e triagem de bug. Recomendo que o pipeline injete `git rev-parse --short HEAD` ou a tag de release nesse campo.

### 3.6 — `robots.txt` inexistente (fallback SPA serve o `index.html` no lugar)
`GET /robots.txt` retorna `200` com o HTML da aplicação (1787 bytes, idêntico ao `index.html`), e não um arquivo `robots.txt` real. Isso é resultado do fallback do SPA/Nginx redirecionando qualquer rota não mapeada para `index.html`. Como o sistema é jurídico interno (dados sensíveis, não deveria ser indexado por buscadores), o ideal é servir um `robots.txt` explícito com `Disallow: /`, e não depender do comportamento acidental do fallback — hoje não há controle explícito sobre indexação por crawlers.

---

## 4. O que precisa ser excluído — avaliação criteriosa

Com a ressalva de que não vi a navegação renderizada (item 0), os candidatos a exclusão/consolidação que a evidência de código sustenta são:

1. **As 5 listas locais duplicadas de área jurídica** (item 3.2) devem ser excluídas e substituídas por importação do `areaCatalog` central. Isso não é opcional a médio prazo: a divergência já existe hoje (item 3.1).
2. **A entrada "Licitações" nas duas listas locais**, condicionada à decisão de negócio do item 3.1 — não excluo por conta própria porque pode ser área de atuação legítima do escritório.
3. **O item de menu do Dossiê do Cliente que leva a uma função inacabada** (item 3.4) — não deve ser excluído, mas precisa de estado visual "em desenvolvimento" até estar pronto, para não gerar expectativa falsa em cliques de primeira viagem.

Não encontrei evidência de módulo morto/órfão sem uso (código presente mas sem rota, ou endpoint mapeado sem tela) a partir do que consegui inspecionar — mas essa é exatamente a pergunta que o próprio módulo `MapaModulos` do sistema foi construído para responder (ele cruza rotas do frontend com endpoints registrados no backend e marca divergências como "precisa_revisao"). Recomendo fortemente que vocês simplesmente abram esse módulo (Administração → Mapa de Módulos) — ele provavelmente já lista, com dados reais do próprio banco, tudo que está órfão, em beta ou legado. É mais confiável que qualquer inferência externa que eu possa fazer sem login.

---

## 5. Nível real de ajuda ao advogado — avaliação

Com base no que é verificável (textos de interface, modelagem de fluxo, integrações declaradas) e não no que presumo sobre a experiência de tela:

O sistema **não é um CRM jurídico genérico com etiqueta de "IA" colada por cima** — a modelagem por jornada de 9 etapas, a curadoria de base RAG com métricas de confiança, o HITL declarado, a integração DataJud/CNJ e os atalhos para ferramentas públicas oficiais (PJe-Calc, Registrato/BACEN, Meu INSS, e-CAC, Consumidor.gov) indicam desenho pensado para reduzir trabalho manual repetitivo real de escritório, não apenas para organizar dados. Isso é ajuda operacional concreta, na medida em que a integração de fato funcione (não pude testar essa parte — ver item 0).

Ao mesmo tempo, dois fatores concretos reduzem a ajuda percebida por um usuário de primeira viagem: (a) descobribilidade de módulos importantes de compliance/auditoria depende de atalhos não óbvios fora do menu principal (item 3.3), o que é especialmente crítico justamente para os módulos ligados a governança de IA e auditoria — os que mais precisam ser vistos por um sócio ou responsável por compliance; e (b) a existência de pelo menos uma funcionalidade anunciada e não entregue sem aviso prévio no ponto de clique (item 3.4) gera fricção desnecessária logo nas primeiras interações, que é exatamente o momento em que a confiança do usuário no sistema está sendo formada.

Em suma: **o desenho conceitual e a cobertura funcional são de nível avançado para um sistema jurídico de escritório de porte médio**; **a maturidade de navegação/descobribilidade para um usuário novo tem lacunas concretas e admitidas pelo próprio produto**; **a postura de segurança de API é sólida e testada nesta auditoria**. A avaliação de "quão bem isso funciona na prática, tela a tela" permanece pendente até eu conseguir autenticação real ou vocês me passarem prints/gravação.

---

## 6. Recomendações priorizadas

**Prioridade alta (correção de arquitetura, baixo custo, alto risco de regressão se não corrigido):**
- Unificar as 5 listas locais de área jurídica em `areaCatalog` (item 3.2).
- Decidir formalmente sobre "Licitações" como área de atuação e documentar a decisão (item 3.1).
- Injetar versão real de build no `/health` (item 3.5).

**Prioridade média (UX para usuário novo):**
- Promover Auditoria, Governança da IA e Produtividade para o menu lateral principal, ou ao menos sinalizar sua existência de forma mais visível que "atalho do Dashboard" (item 3.3).
- Adicionar badge de status ("em desenvolvimento") nos itens de menu ligados a features incompletas, usando o mesmo enum de status que já existe em `MapaModulos` (item 3.4).

**Prioridade baixa (higiene):**
- Servir `robots.txt` explícito com `Disallow: /` (item 3.6).

---

## 7. Próximo passo recomendado

Para completar esta auditoria com o que efetivamente foi pedido — **simular o uso real de um advogado, tela a tela** — a forma mais rápida e confiável, dado que SSH e navegador headless estão bloqueados neste ambiente, é: me passar e-mail e senha de um usuário de teste com perfil **Advogado** (pode ser um usuário descartável, recomendo criar um específico para isso e desativá-lo depois). Com isso, consigo operar a API autenticada reproduzindo, passo a passo, o fluxo Cliente → Triagem → Documentos → Inteligência → Estratégia → Produção → Revisão → Protocolo → Gestão, e reportar erros reais de validação, campos obrigatórios, mensagens de erro e comportamento de cada endpoint — o nível de profundidade que este documento ainda não cobre.
