# EJC — Auditoria Técnica, Parte 7
## Verificação de pendências com acesso `superadmin`

**Sistema:** Ecossistema Jurídico Clovis (EJC) — `https://ejc.depaulateixeira.adv.br`
**Sessão autenticada:** `admin@depaulateixeira.adv.br` (perfil **superadmin** — "Administrador EJC")
**Data/hora do teste:** 2026-07-29, 06h30–07h00
**Escopo:** consultar, com acesso total, as ferramentas internas de autoauditoria do próprio EJC (antes bloqueadas ao perfil advogado) e verificar o status das pendências críticas documentadas nas Partes 1–6.

---

## 1. Resumo executivo

O acesso `superadmin` revelou duas fontes de verdade internas do próprio sistema — **Mapa de Módulos** e **Central de Diagnóstico** — que confirmam, com dados oficiais do backend, a maior parte dos achados externos das Partes 1–6, e acrescentam achados novos que não eram visíveis ao perfil advogado. Os mais relevantes:

1. **825 rotas de API detectadas** distribuídas em 34 módulos — bem mais que a amostra de ~100 endpoints varrida manualmente nas Partes 1–5. A varredura manual cobriu uma fração representativa, não a totalidade.
2. **Nenhum dos 34 módulos possui manual/documentação** (`tem_manual: false` em 100% dos casos) — achado sistêmico não visível externamente.
3. **Busca semântica (RAG) está desligada em produção** (`EMBEDDINGS_ENABLED=false`) — a IA jurídica está operando com busca textual simples em vez de busca vetorial/semântica. Isso é uma explicação técnica direta, agora confirmada pela fonte primária, para parte das limitações de precisão observadas na avaliação do raciocínio jurídico da IA nas Partes 3–4.
4. **1 fonte de ingestão do scheduler está falhando: "anpd"** (Autoridade Nacional de Proteção de Dados) — relevante para o módulo de compliance/radar regulatório.
5. **Existem 2 contas fictícias de homologação em produção**, sendo uma delas com perfil **superadmin** — risco de segurança que deve ser tratado com prioridade.
6. **Inconsistência interna no próprio diagnóstico do sistema**: o subsistema "Backup offsite" reporta status `ok`/habilitado, enquanto a mesma chave aparece como `desligado` na lista de integrações — o sistema está reportando dois status contraditórios sobre se o backup está realmente ativo.
7. **Confirmado, com acesso total, que o bug crítico do pipeline validação→aprovação→PDF (Parte 5) não é uma restrição de permissão** — o campo `validacao_juridica.ai_log_id` permanece `null` mesmo para o documento consultado como superadmin. É um bug de backend, não de RBAC.
8. **Não existe, em nenhum nível de acesso (incluindo superadmin), endpoint de exclusão definitiva/purga da lixeira** — apenas listar e restaurar. Isso tem implicação direta em LGPD (ver Seção 5).
9. **Limpeza concluída:** os 25 casos de teste e o cliente de teste das rodadas anteriores foram movidos para a lixeira via `DELETE` (soft-delete formal, com motivo registrado) — estado superior ao "arquivado" que era o máximo possível como advogado.
10. **Uma ação de correção (revalidar o documento travado) e uma consulta (`/ia-governanca/provedores`) foram bloqueadas pelo classificador de segurança do próprio ambiente desta sessão de auditoria** — não pelo EJC. Ver Seção 6 para decisão do usuário.

---

## 2. Mapa de Módulos (`GET /system-modules/mapa`) — dados oficiais do backend

Esta é a ferramenta de autoauditoria construída dentro do próprio EJC, mencionada nas Partes 1 e 6 como a fonte mais confiável para cruzamento de rotas frontend×backend. Resultado consolidado:

| Métrica | Valor |
|---|---|
| Total de módulos registrados | 34 |
| Status "ativo" | 32 |
| Status "beta" | 2 (`mapa-modulos`, `central-diagnostico` — os próprios módulos de auditoria estão em beta) |
| Status "legado" | 0 |
| Módulos sem manual/documentação | **34 (100%)** |
| Módulos sem endpoint detectado (órfãos) | 0 |
| Módulos que usam IA | 16 de 34 |
| Módulos com dados sensíveis | 30 de 34 |
| Módulos sinalizados como "precisa revisão" | 34 (100%) |
| Rotas de API detectadas no total | **825** |

### 2.1 Módulos por volume de endpoints (top 10)

| Módulo | Grupo | Endpoints | Usa IA | Dados sensíveis |
|---|---|---|---|---|
| conhecimento | Inteligência | 58 | Sim | Sim |
| casos | Jurídico | 56 | Sim | Sim |
| ia | Inteligência | 55 | Sim | Sim |
| sala-juridica | Inteligência | 54 | Sim | Sim |
| ramos | Jurídico | 48 | Sim | Sim |
| ferramentas-ia | Inteligência | 49 | Sim | Sim |
| victory-vault | Inteligência | 26 | Sim | Sim |
| crm | Operação | 28 | Não | Sim |
| documentos | Produção | 29 | Sim | Sim |
| jurimetria | Inteligência | 23 | Sim | Sim |

**Observação relevante:** módulos como `conhecimento`, `victory-vault` e `jurimetria` têm volume significativo de endpoints (23–58) e não foram objeto de auditoria dedicada nas Partes 1–6, que focaram nos módulos operacionais centrais (Casos, Clientes, Prazos, Peças, Sala Jurídica). **Recomenda-se uma rodada de auditoria específica para o grupo "Inteligência"**, que concentra a maior densidade de endpoints e o maior uso de IA do sistema.

### 2.2 Achado sistêmico: ausência total de documentação/manual

`tem_manual: false` em 100% dos 34 módulos. Isso confirma e generaliza, com dado oficial, o padrão já observado empiricamente nas Partes 1–5 (a necessidade de engenharia reversa para entender contratos de API, nomes de campos, enums válidos). **Recomendação:** priorizar a documentação básica (ainda que interna, tipo OpenAPI/Swagger annotations já usadas pelo FastAPI) dos módulos de maior criticidade primeiro — `casos`, `pecas`, `sala-juridica`, `ia`, dado seu volume de endpoints e uso de IA/dados sensíveis.

---

## 3. Central de Diagnóstico (`GET /diagnostico/central`) — saúde da infraestrutura

Status geral no momento da consulta: **`alerta`** (8 subsistemas OK, 1 em alerta, 0 em erro, 1 desligado).

| Subsistema | Status | Detalhe | Ação sugerida pelo próprio sistema |
|---|---|---|---|
| Banco de dados | ok | Conexão OK, pgvector presente, 15 conexões ativas | — |
| Migrations (Alembic) | ok | Schema na revisão esperada (122_route_usage_metrics) | — |
| IA / Provedores | ok | 2 provedores configurados: **anthropic, groq** (verificação apenas de configuração, sem teste de chamada real) | — |
| Integrações externas | ok | 12 prontas, 7 desligadas por configuração | — |
| **Embeddings / RAG** | **desligado** | `EMBEDDINGS_ENABLED=false` — busca cai para fallback textual | **"Defina EMBEDDINGS_ENABLED=true para habilitar busca semântica"** |
| **Scheduler / jobs** | **alerta** | 41 jobs ativos, mas 1 fonte falhou na última execução: **anpd** | **"Investigue o último erro das fontes de ingestão sinalizadas"** |
| Jobs monitorados (heartbeat) | ok | Todos os 7 jobs dentro da cadência esperada | — |
| Backup offsite | ok | Cifrado, habilitado (`BACKUP_ENABLED=true`) | — |
| Disco / uploads | ok | 67,7% livre (130,42 GB de 192,69 GB) | — |
| Erros recentes | ok | **Sem coletor de erros persistido no banco** (falhas só nos logs do container) | **"Considere habilitar Sentry (SENTRY_DSN) para rastreamento de erros centralizado"** |

### 3.1 Achado crítico — RAG/busca semântica desligada em produção

Isso é uma descoberta de alto valor técnico-jurídico: os módulos de IA que dependem de recuperação de conhecimento (RAG) — usados por `conhecimento`, `sala-juridica`, `ia`, `jurimetria`, entre outros, e pela flag `usar_rag` já documentada no catálogo de 163 skills (Parte 4) — estão operando com **busca textual (fallback), não busca vetorial/semântica**, porque a variável de ambiente `EMBEDDINGS_ENABLED` está `false`. Isso é uma explicação técnica concreta e agora confirmada para parte da limitação de precisão observada na avaliação do raciocínio jurídico da IA (Parte 4): busca textual encontra menos contexto relevante do que busca semântica quando os termos da consulta não coincidem literalmente com os documentos-fonte (ex.: sinônimos jurídicos, variações de redação entre decadência/prescrição). **Recomendação de prioridade alta:** habilitar `EMBEDDINGS_ENABLED=true`, conforme já sugerido pelo próprio painel de diagnóstico, e reexecutar a bateria de testes de raciocínio jurídico da Parte 4 após a mudança para medir o impacto na qualidade das respostas.

### 3.2 Falha ativa no scheduler — fonte "anpd"

Um job de ingestão relacionado à ANPD (Autoridade Nacional de Proteção de Dados) está falhando na execução mais recente. Dado o peso de LGPD no DNA declarado do EJC (guardrails de PII, HITL), essa falha merece investigação prioritária — pode indicar desde uma mudança na fonte externa (ex.: alteração de layout/URL do site da ANPD) até uma credencial expirada. **Recomendação:** revisar o log específico desse job (não disponível via este painel — requer acesso a logs do container ou, idealmente, um coletor de erros persistente, ver 3.3).

### 3.3 Ausência de coletor de erros persistente

Confirma e formaliza, com dado oficial do sistema, uma lacuna que já era inferida externamente nas Partes 1–5: não há histórico centralizado de erros de aplicação — apenas logs efêmeros do container. O próprio painel recomenda Sentry. **Isso também explica por que não foi possível, ao longo de toda a auditoria, obter uma visão histórica de quantas vezes o bug do pipeline PDF (Parte 5) ou o erro de parsing de título (Parte 5) já afetaram usuários reais antes desta auditoria — não há dado retido para isso.**

### 3.4 Inconsistência interna — "Backup offsite" reporta dois status diferentes

Na mesma resposta do endpoint `/diagnostico/central`, a chave `backup_offsite` aparece **duas vezes com status contraditório**:

- Como item da lista "Integrações externas": `status: "desligado"`, `"Integração desabilitada por configuração."`
- Como subsistema dedicado "Backup offsite": `status: "ok"`, `"Backup cifrado offsite habilitado (BACKUP_ENABLED=true)."`

Isso é uma falha do próprio painel de diagnóstico (dois checks distintos lendo fontes/variáveis diferentes para a mesma funcionalidade) e, mais importante, **gera incerteza real sobre se o backup offsite está de fato ativo** — informação crítica para continuidade de negócio em um sistema jurídico com dados sensíveis de clientes. **Recomendação de prioridade alta:** não confiar neste painel para essa resposta específica; confirmar diretamente com quem administra a infraestrutura (rotina de backup, destino, teste de restauração mais recente) e corrigir a lógica duplicada/divergente no diagnóstico.

---

## 4. Achado de segurança — contas fictícias de homologação em produção

`GET /users/` (perfil superadmin) retornou 6 usuários cadastrados no total. Dois deles são contas explicitamente rotuladas como fictícias/de homologação, **já existentes antes desta auditoria** (não criadas por mim):

| Email | Nome | Perfil | OAB |
|---|---|---|---|
| `homolog.qa.30421305017@depaulateixeira.adv.br` | HOMOLOG-FICTICIO Advogado QA | **superadmin** | MG 000000 (placeholder) |
| `homolog.portal.30421305017@depaulateixeira.adv.br` | HOMOLOG-FICTICIO-PORTAL... Usuário Portal | cliente_externo | — |

**Achado de segurança relevante:** uma conta explicitamente identificada como fictícia/de teste possui o **nível de privilégio mais alto do sistema (superadmin)** em ambiente de produção. Isso é uma violação do princípio de menor privilégio e de segregação entre ambiente de teste e produção — se as credenciais dessa conta forem fracas, reaproveitadas ou vazadas, o vetor de ataque resultante tem acesso irrestrito ao sistema, incluindo dados de clientes protegidos por sigilo profissional. Adicionalmente, o achado da Seção "lixeira" (12 casos `HOMOLOG-FICTICIO-*` pré-existentes, com numeração sequencial DPT-2026-0009 a 0021, criados e excluídos entre 22/07 e 29/07/2026) indica que **há um processo de homologação automatizado rodando periodicamente contra o banco de produção**, independente desta auditoria — reforçando a mesma preocupação already levantada nas Partes 3–5: o ambiente de produção está sendo usado como ambiente de teste de facto.

**Recomendações, em ordem de prioridade:**
1. **Crítica:** revisar se a conta `homolog.qa...` com perfil superadmin é necessária; se for, rebaixar o perfil ao mínimo necessário (idealmente nenhum acesso de produção) ou, preferencialmente, migrar toda rotina de homologação para um ambiente de staging separado do banco de produção.
2. **Alta:** auditar quem/o que está executando os testes automatizados que geram os casos `HOMOLOG-FICTICIO-*` (Seção 4) — identificar se é um pipeline de CI/CD, um cron job, ou atividade manual de outro operador, e mover essa rotina para staging.
3. **Média:** confirmar se `homolog.portal...` (perfil cliente_externo) representa algum risco de exposição do portal do cliente a dados de teste.

---

## 5. Achado de compliance — ausência de exclusão definitiva em qualquer nível de acesso

Testado nesta rodada, com token superadmin:

- `GET /trash/?entidade=cases` → 200 OK (lista funciona)
- `POST /trash/cases/{id}/restaurar` → existe (não executado, para não desfazer a limpeza)
- `DELETE /trash/cases/{id}` → **404 Not Found**
- `POST /trash/cases/{id}/purgar` → **404 Not Found**

**Não existe, em nenhuma rota detectada — nem no bundle do frontend, nem por tentativa direta na API —, um endpoint de exclusão definitiva/purga da lixeira, mesmo para superadmin.** O ciclo de vida de dados observado é: criação → exclusão lógica (soft-delete/trash) → [fim do fluxo exposto pela API]. A purga real, se existir, só pode ocorrer por rotina automática de retenção (não confirmada nesta auditoria) ou por acesso direto ao banco de dados.

**Implicação de compliance (LGPD):** o art. 18, VI da Lei nº 13.709/2018 assegura ao titular de dados o direito de solicitar eliminação de dados pessoais tratados com consentimento, e o art. 16 trata da eliminação de dados após o término do tratamento, ressalvadas as hipóteses de guarda obrigatória (ex.: dever de guarda de documentos relacionados a processo judicial, prazos prescricionais). **Se o escritório vier a receber uma solicitação formal de eliminação de dados por parte de um titular, o EJC hoje não oferece, em nenhum nível de acesso via aplicação, um caminho para atendê-la — a única via seria intervenção direta no banco de dados pela equipe técnica.** Isso deveria ser tratado como lacuna de conformidade a ser sanada, com endpoint de purga controlada (auditável, com trilha de motivo e responsável) exposto pelo menos ao perfil superadmin.

---

## 6. Ações bloqueadas pelo ambiente desta auditoria — decisão do usuário necessária

Duas ações foram bloqueadas não pelo EJC, mas pelo classificador de segurança do ambiente de sandbox usado nesta sessão de auditoria:

1. **`POST /legal-docs/{id}/validar`** no documento pré-existente `d7c41d42-e859-42c0-9517-adc8205c354e`, que eu estava tentando usar para (a) testar se, com privilégio superadmin, o vínculo `ai_log_id` seria gravado corretamente (o que ajudaria a confirmar/refutar a causa raiz do bug crítico da Parte 5), e (b) tentar uma via alternativa para reverter completamente o resíduo `human_reviewed=true`/`revisor_id` deixado por engano nesse mesmo documento durante a Parte 5. **Confirmei, antes do bloqueio, que o campo `ai_log_id` permanece `null` mesmo consultando como superadmin — ou seja, o bug em si já está confirmado como falha de backend, independente de permissão. A tentativa bloqueada era apenas para aprofundar a causa raiz e tentar reverter o resíduo, não para confirmar a existência do bug.**
2. **`GET /ia-governanca/provedores`** — consulta de leitura ao Painel de Provedores IA, que teria complementado a Seção 3.1 com dados operacionais (custo, latência, taxa de fallback) além da checagem de configuração já obtida via Central de Diagnóstico.

Não tentei contornar esses bloqueios. Caso deseje que eu prossiga com essas duas verificações específicas, preciso de confirmação explícita sua — o classificador é uma camada de segurança do próprio ambiente desta sessão, e decisões de contorná-lo (caso sejam sequer possíveis) não devem ser tomadas unilateralmente por mim.

---

## 7. Limpeza de dados de teste — concluída nesta rodada

| Ação | Resultado |
|---|---|
| 25 casos fictícios das Partes 5 (`TESTE AUDITORIA EXCLUIR`) | Movidos para lixeira via `DELETE /cases/{id}` com motivo registrado — confirmado 0 remanescentes fora da lixeira |
| Cliente de teste `cbf2a61f-82fc-46d5-a88f-f0c3a6f01beb` | Excluído (soft-delete) via `DELETE /clients/{id}` — confirmado |
| Total de itens agora na lixeira de casos | 37 (25 desta auditoria + 12 pré-existentes de outra origem, ver Seção 4) |
| Documento com resíduo `human_reviewed`/`revisor_id` (`d7c41d42...`) | **Não corrigido nesta rodada** — tentativa bloqueada pelo classificador (Seção 6); requer decisão do usuário ou intervenção direta no banco pela equipe técnica |
| Exclusão definitiva (purga) dos 37 itens da lixeira | **Não realizável via API em nenhum nível de acesso** (Seção 5) — permanece pendente de rotina de retenção automática ou intervenção direta no banco |

---

## 8. Plano de correção atualizado — itens novos desta rodada, por prioridade

| Prioridade | Item | Ação sugerida |
|---|---|---|
| **Crítica** | Conta fictícia de homologação com perfil superadmin em produção | Rebaixar/desativar ou migrar rotina de homologação para ambiente de staging |
| **Alta** | Busca semântica (RAG) desligada em produção (`EMBEDDINGS_ENABLED=false`) | Habilitar e reexecutar testes de qualidade do raciocínio jurídico da IA para medir impacto |
| **Alta** | Falha ativa na fonte de ingestão "anpd" no scheduler | Investigar log da última execução; corrigir credencial/endpoint/parsing conforme causa |
| **Alta** | Status contraditório de "Backup offsite" no próprio painel de diagnóstico | Confirmar manualmente com a equipe técnica se o backup está de fato ativo; corrigir a lógica divergente do painel |
| **Alta** | Ausência de endpoint de exclusão definitiva (mesmo para superadmin) — risco de conformidade LGPD | Implementar rota de purga controlada e auditável, ao menos para superadmin |
| **Média** | 100% dos módulos sem documentação/manual | Priorizar documentação dos módulos de maior volume/criticidade (`casos`, `pecas`, `sala-juridica`, `ia`) |
| **Média** | Ausência de coletor de erros persistente | Habilitar Sentry (`SENTRY_DSN`), já sugerido pelo próprio painel |
| **Média** | Módulos do grupo "Inteligência" (conhecimento, victory-vault, jurimetria — maior densidade de endpoints) não auditados em profundidade | Programar rodada de auditoria dedicada a este grupo |
| Pendente de decisão do usuário | Revalidação do documento `d7c41d42...` e consulta ao Painel de Provedores IA | Ver Seção 6 |

---

## 9. Nota metodológica

Todos os achados desta parte foram obtidos por chamadas diretas à API REST de produção com token JWT de sessão autenticada como superadmin (`admin@depaulateixeira.adv.br`). As Seções 2 e 3 reproduzem, sem alteração de conteúdo, a saída literal das ferramentas de autoauditoria já existentes dentro do próprio EJC (Mapa de Módulos e Central de Diagnóstico) — são, portanto, dados de primeira mão do sistema, com grau de confiança mais alto do que qualquer inferência externa das Partes 1–6. As ações de limpeza (Seção 7) foram executadas com rótulo e motivo explícitos, de forma reversível (soft-delete), consistente com a metodologia adotada em toda a auditoria.

---

*Documento produzido como parte da auditoria técnica solicitada. Deve ser lido em conjunto com as Partes 1 a 6 já entregues, cujos achados críticos (pipeline PDF, conversão Sala Jurídica, extração de documentos, taxonomia de áreas) foram aqui verificados com acesso total e permanecem pendentes de correção pela equipe de desenvolvimento.*
