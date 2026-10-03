# Auditoria — Integrações externas

- Data: 2026-10-01 · Base: `40144d6` + relatórios anteriores (branch `claude/blissful-darwin-nr2i2v`)
- Método: leitura estática de código. **Nenhuma integração foi chamada, nenhum teste foi executado, nada de produção foi acessado** (CLAUDE.md, regra 9). "Operacional" neste relatório significa *"há código com consumidor interno"*, não *"funciona em produção hoje"* — isso não foi verificado.
- Os achados descrevem o código lido. Os marcados "a reproduzir" exigem teste antes de qualquer correção.

## 1. Escopo, mapa e limites

A camada de integração está espalhada em cinco famílias de código, sem camada comum:

| Família | Conteúdo | Lido |
|---|---|---|
| `app/integrations/` | clientes novos (Issue #836/#1527): BrasilAPI, DataJud (wrapper), DJEN/Comunica, CKAN (IBAMA/MJ/CVM/TSE), CNJ SGT, TCU, IBGE, Querido Diário, IDE-Sisema, PGFN, parser INLABS; `routers.py` (`/api/integracoes/*`); `feature_flags.py` | tudo, exceto TCU/IBGE/SGT/PGFN (só pelo roteador e pelo padrão dos demais) |
| `app/services/` (conectores) | `datajud_service`, `djen_service` + `djen_http`, `infosimples_service`, `mni_connector`, `bcb_service`, `indices_service`, `diario_oficial_service`, `validators_service`, `google_drive_service`/`google_drive`, `querido_diario_monitor`, `tribunal_registry` | `datajud` (auth, retry, cache, sync), `infosimples` (inteiro), `djen_http`, `mni_connector`, `bcb_service` (inteiro), `indices_service` (estrutura), `diario_oficial_service` (fetch), `validators_service` (CEP/CNPJ), `google_drive_service` (escopo, LGPD), `tribunal_registry` |
| Ingestão de conhecimento | `services/ingestors/*` (Planalto, STJ, TJMG, LexML, DJEN, Câmara, Senado), `conhecimento_ingest/*` (ANPD, RFB), `juris_import/*`, `jurisprudencia_externa`, `ingestion_service` (helper HTTP) | helper HTTP e inventário de uso; os ingestores por inventário (não lidos linha a linha) |
| Routers | `infosimples_receita`, `infosimples_tjmg`, `car`, `transparencia`, `radar_legislativo`, `processo_eletronico`, `utils`, `calculadoras` | RBAC/ownership/audit de todos; corpo de `utils`, `calculadoras` (trecho) |
| Painel/monitoramento | `integration_status`, `integration_runtime_status`, `heartbeat_service`, `scheduler` (ids de jobs) | `integration_status` (itens e refino), `heartbeat_service` (jobs monitorados) |

**Fora do alcance, por bloqueio do próprio ambiente:** o hook de segurança do repositório impediu a leitura (via Bash) de `credential_registry.py` e `credential_testers.py` ("leitura de arquivo sensível é proibida, CLAUDE.md regra 12 / GOVERNANCA_IA.md"). Respeitei o bloqueio e **não** os li por outro caminho. O Cofre de Credenciais (`credential_vault*`, `credential_registry`, `credential_testers`) **não foi auditado**; só `vault_crypto.py` (política de chaves) foi lido, antes do bloqueio. Pede-se tratamento humano controlado para esse trecho (Fase 8).

**Também não lidos:** corpo dos ingestores e dos clientes TCU/IBGE/SGT/PGFN, `transparencia_service`, `radar_legislativo` (além do `_get_json`), `ajuizamento/conectores` (PDPJ, eproc, PJe-MNI REST), `datajud_sync_service`, tasks Celery do MNI (início), `jurimetria_tribunais`, frontend das integrações, e a suíte de testes (nenhum teste aberto ou executado).

### 1.1 Estado de cada integração da lista (pelo código)

| Integração | O que o código mostra |
|---|---|
| DataJud/CNJ | **Consumido** por sincronização de casos, saneamento e jurimetria dos tribunais; kill-switch `DATAJUD_ENABLED` + chave; retry (3×, só 429/5xx/transporte), limitador de RPS e cache (memória + Redis opcional). |
| DJEN/Comunica | **Consumido** pelo job de captura (`djen_service`, com paginação, teto de páginas fail-closed, deduplicação atômica, sem criar prazo); proxy HTTP privado opcional. Também exposto em `/integracoes/djen/*`. |
| BrasilAPI | **Consumido** para feriados (flag) e CEP/CNPJ; CEP/CNPJ sem kill-switch (ver E5). |
| LexML | **Consumido** (ingestor com flag `LEXML_INGEST_ENABLED`, default ligado); existe uma segunda implementação em `juris_import/lexml.py`. |
| STJ / TJMG | **Consumidos** por ingestores (dois conjuntos: `ingestors/` e `juris_import/`) e, no TJMG, também por Infosimples e MNI. |
| BCB (SGS/Olinda) | **Consumido**, em **duas pilhas** (`bcb_service` legado e `indices_service`); as cinco séries mais usadas ainda passam pela legada (E4). |
| Receita/Infosimples | **Consumido** (consultas pagas, advogado+, com teto diário e auditoria). CNPJ "da Receita" nas telas sem pagar vem de provedores comunitários (E5). |
| CAR/SICAR | **Consumido** apenas via Infosimples (pago). |
| CGU (CEIS/CNEP/CEPIM) | Gated (`TRANSPARENCIA_ENABLED`, default off), advogado+; serviço não lido. |
| Câmara/Senado/ALMG | **Consumidos** pelo radar legislativo (job com heartbeat) e ingestores (Câmara/Senado); ALMG também via LexML. |
| IBGE | **Consumido** apenas pelo monitor do Querido Diário; demais rotas sem consumidor. |
| CVM, TSE, IBAMA, MJ (CKAN) | **Só catálogo**: devolvem metadados/links de recursos; "arquivos volumosos não são baixados"; **nenhum consumidor interno** além da rota. |
| PGFN | **Só catálogo** de arquivos bulk; sem consulta individual; sem consumidor interno. |
| Querido Diário | **Consumido** pelo monitor (flag, job com heartbeat) e por rota. |
| IDE-Sisema | **Só rota** (camadas e feições WFS); sem consumidor interno. |
| INLABS/DOU | O monitor do DOU **não usa XML do INLABS**: lê o índice HTML de `in.gov.br/leiturajornal`. O `inlabs_parser` **não tem consumidor** (E7). |
| Google Drive | Duas coisas distintas e corretas: ingestão de conhecimento (escopo `drive.readonly`, pasta configurada, bloqueio LGPD de peças de cliente) e armazenagem do GED via `rclone`. |
| PJe/MNI | **Consumido** em Fase A (somente leitura) por tasks Celery; credenciais por advogado/tribunal; só TJMG seedado. Peticionamento (PDPJ/PJe REST/eproc) fica atrás de flags default off, não lido. |

## 2. Pontos conformes (verificados no código)

- **Padrão de opt-in:** integrações novas nascem com flag default OFF (`.env.example`), com 503 controlado antes de qualquer I/O (`require_enabled`); `.env.example` só traz placeholders.
- **SSRF:** `safe_outbound_url` valida todos os IPs resolvidos, fixa o IP na conexão e revalida a cada redirect; CKAN usa hosts allowlisted e filtra a URL dos recursos por domínio oficial; WSDL do MNI vem apenas de seed por migration (nenhuma rota cria tribunal) e o zeep usa `forbid_external=True`.
- **Segredos:** token do Infosimples só no corpo do POST; DataJud sem chave embutida no código; proxy do DJEN tratado como segredo e nunca logado; `trust_env=False` no cliente do DJEN.
- **Custo e cache honestos:** Infosimples tem teto diário, cache do dia, sem retry para não duplicar cobrança, auditoria com parâmetros mascarados.
- **Falha visível:** DOU diferencia "nenhum resultado" de "fonte indisponível", com teto de bytes; DJEN falha fechado em execução incompleta; DataJud **não cria prazo** a partir de movimento (barreira jurídica, HITL); `indices_service` "nunca inventa valor".
- **Observabilidade por resultado:** `ingestao_saude` mede se a fonte voltou a produzir, além de o job ter rodado; heartbeats para DJEN, DataJud, DOU, Querido Diário e radar.
- **Drive:** escopo somente leitura, bloqueio LGPD de peça de cliente, `rclone` sem shell, com timeout e caminho validado.
- **Roteador `/integracoes`:** JWT, rate limit por fonte, 502 genérico (sem corpo do upstream), auditoria das consultas que tocam terceiros.

## 3. Achados

Severidade: **M** média · **B** baixa. **Não identifiquei achado de severidade alta nesta leitura**; os de maior impacto são E1 a E4 (credenciais, custo, superfície e cálculo jurídico). "Conf." = certeza após a leitura.

| # | Sev | Conf. | Achado | Evidência |
|---|---|---|---|---|
| E1 | M | Alta | **Credenciais do MNI (id e senha de consultante do advogado em tribunal) são cifradas com a chave de PII** (`PII_ENCRYPTION_KEY`, Fernet único, sem rotação), contrariando a política do próprio Cofre, que determina chave exclusiva e rotação por `MultiFernet` ("nunca reusada de PII"). Vazamento ou rotação da chave de PII passa a envolver também acesso a processos em nome de advogados; e, sem `MultiFernet`, a rotação é impossível sem recifrar tudo. O conector de leitura **não tem flag/kill-switch próprio**: `PJE_MNI_ENABLED` vale só para o REST de peticionamento; o painel marca o conector como "habilitado" por `CELERY_ENABLED`. | `processo_eletronico_credential_service.py`; `vault_crypto.py` (cabeçalho); `config.py` l.519-522; `integration_status.py` l.349-359 |
| E2 | M | Alta (a reproduzir) | **Teto de custo do Infosimples é burlável por concorrência e não conta falha de rede.** A checagem é "contar → chamar → registrar": o registro só ocorre **depois** da chamada paga (timeout de até 330 s), então N requisições simultâneas passam todas abaixo do teto (o código admite "poucas unidades"; com consultas lentas o excesso é limitado só pela concorrência). Erro de rede/HTTP após a Infosimples ter processado **não é contado** e a repetição pelo usuário é cobrada de novo. O cache é por (caminho + parâmetros), não por usuário, e o `resultado` (dados da Receita: nome, situação, óbito, endereço) fica em JSONB **sem cifra**, com purga de 7 dias executada **apenas quando outra consulta é feita**: com a integração parada, o dado pessoal permanece indefinidamente. A tabela é criada em tempo de requisição (`CREATE TABLE IF NOT EXISTS`), sem migration. | `infosimples_service.py` l.265-333, 388-457 |
| E3 | M | Alta | **`/api/integracoes/*` está aberto a qualquer usuário interno e sem consumidor.** Só exige JWT (financeiro, secretaria e estagiário inclusive); nenhuma chamada no frontend (a única menção é um comentário). `GET /integracoes/djen/oab/{uf}/{numero}` devolve comunicações **de qualquer OAB**, com o texto HTML da intimação e as partes (o próprio docstring do cliente alerta para dado de terceiros). As rotas de CKAN, PGFN, IDE-Sisema, TCU, IBGE, SGT e Querido Diário também não têm consumidor interno (IBGE e QD têm só o monitor). As flags dessas integrações são lidas por `os.getenv`, **fora de `Settings`**, logo invisíveis à validação central de configuração. | `integrations/routers.py`; `feature_flags.py`; busca por consumidores |
| E4 | M | Alta (a reproduzir) | **Cálculo judicial ainda passa pela pilha legada nas cinco séries mais usadas.** Em `/calculadoras/correcao-monetaria`, só o que **não** está em `bcb_service.SERIES` vai ao `indices_service`; IPCA, IPCA-E, INPC, Selic e TR seguem em `bcb_service` (e `liquidacao_trabalhista` usa a legada para a fase Selic). A legada: cache em memória **sem TTL e sem limite** (chave inclui datas escolhidas pelo usuário); sem kill-switch (`INDICES_BCB_ENABLED` não vale); **não confere se a série cobre todos os meses do período** (aplica o que vier e conta `meses_aplicados`); erro do BCB vira exceção crua. `selic_anualizada` usa **Selic fixa de 10,75% a.a.** quando o BCB falha (alimenta `visual_law`, com `fonte: "fallback"`). Duas pilhas e tabelas criadas em runtime. | `calculadoras.py` l.100-125; `bcb_service.py`; `calc/liquidacao_trabalhista.py` l.160-175; `routers/visual_law.py` l.175-190 |
| E5 | M | Alta | **CNPJ/CEP "públicos" vêm de provedores comunitários e há três caminhos para o mesmo dado.** `validators_service` consulta OpenCNPJ → BrasilAPI → ReceitaWS (projetos privados/comunitários; a própria BrasilAPI se declara "não oficial"), mas o `docstring` fala em "dados cadastrais públicos da Receita" e `/utils/cnpj` responde "CNPJ não encontrado **na Receita**". Caminhos paralelos: `/utils/cnpj`, `/integracoes/brasilapi/cnpj` e `/infosimples/receita/cnpj` (fonte Receita via agregador pago); `/integracoes/brasilapi/cnpj` e o Infosimples auditam, `/utils/cnpj` não. A consulta revela a terceiros quem o escritório investiga. `GET /utils/validar-cpf/{cpf}` leva o CPF **no caminho da URL** (registrado em log de acesso do nginx, histórico e breadcrumbs), embora a resposta já minimize. | `validators_service.py` l.100-260; `utils.py`; `integrations/routers.py` l.215-243 |
| E6 | M | Alta | **Não há camada HTTP comum nem pilha única de ingestão.** Cada cliente reimplementa timeout, retry, `follow_redirects`, tratamento de erro; há 11 usos de `follow_redirects=True`, `trust_env=True` por padrão no helper de ingestão e teto de bytes encontrado em **poucos pontos** (DOU, IDE-Sisema, Entrada Universal), sem padrão comum. Não há circuit breaker (as menções a *breaker* no código são de IA e rota). Jurisprudência/legislação tem **três implementações paralelas** (`ingestors/`, `juris_import/`, `jurisprudencia_externa`) mais `conhecimento_ingest` e `integrations`: LexML, STJ e TJMG existem ao menos duas vezes. | `ingestion_service.py` l.100-140; busca por `AsyncClient`/`follow_redirects`; busca de consumidores |
| E7 | M | Alta | **"INLABS: XML estruturado do DOU" não está operacional, e o DOU atual raspa HTML com User-Agent de navegador.** O `inlabs_parser` não tem consumidor (apenas o `__init__.py` o cita); o monitor do DOU lê `in.gov.br/leiturajornal` e **se apresenta como Chrome** porque o portal recusa o agente do httpx — fonte frágil e postura de uso a ser avaliada pelo titular (não há tratamento de `robots.txt` nem registro de termos de uso em nenhuma fonte raspada). O parser do INLABS, o de LexML (`juris_import`), o de `jurisprudencia_externa` e o do IDE-Sisema usam `xml.etree` da biblioteca padrão, enquanto o repositório fixa `defusedxml` com a justificativa "parse seguro de XML de terceiros" (aplicado só ao NF-e/OCR). | `integrations/inlabs_parser.py`; `diario_oficial_service.py` l.18-60, 174-200; `requirements.txt` l.94; busca por `xml.etree` |
| E8 | M | Média (a reproduzir) | **Roteamento do MNI ignora o segmento de justiça.** `resolver_tribunal` casa só o código TR (`13`), e o seed é "TJMG = 13". Pelo padrão CNJ, TR 13 também ocorre em TRT13 (J=5) e TRE-MG (J=6); esses números seriam enviados ao endpoint do TJMG com a credencial do advogado. O grau é fixado em "1" por padrão. Impacto provável: falha/"não localizado", não vazamento; mas sincronização incorreta e credencial usada em tribunal errado. | `tribunal_registry.py` l.19-76; `132_processo_eletronico_mni.py` l.100-125 |
| E9 | M | Alta | **Painel e monitoramento incompletos.** `integration_status` não lista CNJ SGT, TCU, IBGE, IBAMA, MJ, CVM, TSE, PGFN, Querido Diário nem IDE-Sisema; "CEP/CNPJ públicos" é fixo `enabled=True, configured=True` (sempre "pronto"); o Drive lê `os.getenv` em vez de `Settings`; os heartbeats cobrem 5 jobs de integração (a saúde por resultado de Planalto/STJ/TJMG/LexML/Câmara/Senado vem de `ingestao_saude`, não de heartbeat). Não há métrica de latência/erro por integração. A chave pública do DataJud "pode ser alterada pelo CNJ a qualquer momento" (comentário do próprio cliente) sem rotina de detecção/rotação documentada no código lido. | `integration_status.py` l.340-520; `heartbeat_service.py` |
| E10 | B | Alta | **Higiene de log e de auditoria.** `_falha_upstream` registra `str(exc)[:500]`; exceções do httpx trazem a URL, que contém CNPJ/CNJ/OAB consultados (`validators_service` evita isso de propósito, o roteador não). `sincronizar_caso` grava `str(e)` em `case.sync_error`. A auditoria WORM de `/integracoes` guarda CNPJ, número CNJ e OAB como `registro_id`, enquanto o sanitizador do projeto trata CNJ como PII estrutural. | `integrations/routers.py` l.107-114, 127-138; `datajud_service.py` l.762-766 |
| E11 | B | Média | **DataJud: dedup e código morto.** A deduplicação de movimentos usa `hash(data\|descrição)` embutido no texto (`[dj:…]`) e varre as descrições do caso a cada sincronização; na primeira sincronização movimentos idênticos entram em duplicata (o conjunto de hashes não é atualizado no laço) e, nas seguintes, novos movimentos idênticos a um já existente são descartados. `sincronizar_prazos_datajud` e `_criar_deadline_automatico` são inertes (a detecção sempre devolve vazio), mas seguem documentados como "cria prazos". Cache e limitador de RPS são por processo; o `docker-compose` avisa para não escalar `--workers` por isso, enquanto o comentário OPS-04 do mesmo serviço pressupõe N workers. | `datajud_service.py` l.128-165, 725-800, 461-470; `docker-compose.yml` l.111-116 |
| E12 | B | Alta | **DDL em tempo de requisição** em 14 pontos de 8 arquivos (Infosimples, `indices_bcb_cache`, transparência, radar, backup, modelos de NFS-e e do cofre), via `CREATE TABLE IF NOT EXISTS`, sem migration: exige privilégio de DDL no papel da aplicação e desalinha o `alembic`. É um precedente declarado no código, mas conflita com a regra de migrations do `CLAUDE.md`. | `grep` de `CREATE TABLE IF NOT EXISTS` |
| E13 | B | Alta | **Pequenos defeitos de consistência:** `radar_legislativo._get_json` repete em qualquer exceção (inclusive 4xx) e não limita corpo; `ide_sisema` lê o corpo inteiro antes de checar o teto; `consultar_cep` de `/integracoes` não audita enquanto `consultar_cnpj` audita; `limiter` (slowapi) por IP convive com `rate_limit` por usuário em rotas diferentes do mesmo conjunto. | `radar_legislativo.py` l.80-100; `ide_sisema_client.py`; `integrations/routers.py` |

## 4. Plano de melhoria, correção e consolidação

Premissas: PRs pequenos por frente; correção de bug com teste de regressão (CLAUDE.md §7); mudança em credenciais/permissões/config exige `security-auditor` (§8); migration só quando indicada, com reserva em `MIGRATION_RESERVATIONS.md` e `alembic upgrade head` do zero; rota alterada atualiza o baseline de rotas, o snapshot OpenAPI e o ledger; testes de integração **sem rede** (mock/fixtures gravadas). Nada enfraquece RBAC, LGPD, sanitização, kill-switch ou HITL.

### Fase 0 — Reproduzir e decidir (≈1–2 dias, sem código de produção)
1. Reproduzir **E2** (N chamadas concorrentes ao mesmo tempo ultrapassam o teto; falha de rede não incrementa o contador), **E4** (série IPCA com meses finais ausentes devolve cálculo sem alerta; BCB fora → Selic 10,75%) e **E8** (número CNJ com J=5/TR=13 resolve para o endpoint do TJMG).
2. Obter, por canal autorizado (regra 9), o **inventário real de flags e credenciais ativas** em produção (sem acessar o ambiente): quais integrações estão ligadas hoje. Sem isso, "operacional" segue sendo só leitura de código.
3. Decisões do titular: política de **uso de fontes raspadas** (DOU com User-Agent de navegador, STJ/TJMG; `robots.txt`/termos); se os provedores comunitários de CNPJ continuam como fallback; o que fazer com rotas sem consumidor; quem acessa `/integracoes/*`.

### Fase 1 — Custo, credenciais e dado pessoal (prioridade)
| Item | Ação | Teste de regressão |
|---|---|---|
| E2 | **Reservar antes de chamar**: `INSERT` atômico de linha `pendente` condicionado à contagem (advisory lock ou `INSERT … SELECT … WHERE count < teto`), confirmar/atualizar após a resposta e contar também falha após envio; cache só com campos normalizados mínimos (ou cifrado), purga por job agendado e não "oportunista"; migrar a tabela para Alembic. | N concorrentes ≤ teto; timeout conta; purga sem consulta nova |
| E1 | Mover as credenciais do MNI para o Cofre (chave exclusiva, `MultiFernet`) com migration + script de recifragem e runbook; criar `PROCESSO_ELETRONICO_ENABLED` (default off) e honrá-lo no router, nas tasks e no painel; adotar `MultiFernet` também em `pii_crypto` (ver C12 do relatório de Clientes). | credencial antiga decifra durante a transição; flag off → 503 |
| E8 | Resolver tribunal por **(J, TR, grau)**; coluna `segmento` no catálogo; recusar número cujo par J.TR não esteja cadastrado. | TRT13/TRE-MG não casam com TJMG |

### Fase 2 — Redução de superfície (E3, E5, E10)
- `/integracoes/*`: exigir advogado+ (ou remover as rotas sem consumidor: CKAN, PGFN, IDE-Sisema, TCU, IBGE, SGT); restringir `djen/oab` às OABs monitoradas do escritório; mover as flags de `os.getenv` para `Settings` (com teste de paridade com `.env.example`).
- CNPJ/CEP: **um** serviço com contrato único; rótulo honesto da fonte ("cadastro público de terceiros", não "Receita") e a Receita oficial só via Infosimples/Conecta; auditoria uniforme; `validar-cpf` e CPF em corpo POST, nunca na URL.
- Logs: mascarar URL/identificadores nas exceções do httpx (uma função de *redaction* única); não gravar `str(e)` em `sync_error`; revisar o que vai a `registro_id` no WORM.

### Fase 3 — Camada HTTP comum (E6, E13)
- Criar `ExternalHttpClient` (única entrada de rede de saída): timeout, retry com política por idempotência, teto de bytes em *streaming*, validação SSRF para qualquer URL derivada de conteúdo raspado, política de redirecionamento e de User-Agent, **redação de URL em log**, métricas (latência/erro/status) e **circuit breaker** por fonte.
- Migrar os clientes aos poucos (primeiro os que recebem dado de usuário: BrasilAPI/CNPJ, Infosimples, DataJud, DJEN), com testes de contrato por fixture. `defusedxml` em **todo** parser de XML de terceiros (INLABS, LexML, `jurisprudencia_externa`, IDE-Sisema).

### Fase 4 — Cálculo jurídico confiável (E4)
- Migrar IPCA, IPCA-E, INPC, Selic e TR para o `indices_service` e **descontinuar** `bcb_service` após teste de paridade numérica (mesmo valor corrigido, mesma memória de cálculo).
- Exigir **cobertura completa** do período (todas as competências presentes) ou devolver erro/alerta explícito; remover a Selic fixa (ou bloquear o cálculo e exibir "índice indisponível"); TTL e limite de tamanho do cache; respeitar `INDICES_BCB_ENABLED`; tabelas em Alembic.

### Fase 5 — Consolidação das fontes de conhecimento (E6, E7)
- Eleger **uma** pilha de ingestão (framework de `ingestors/` com registro de fontes e estado em `fontes_ingestao`) e aposentar `juris_import` e `jurisprudencia_externa` após testes de paridade, mantendo as fontes ativas e o rastro de proveniência.
- INLABS: ou ligar de fato (fluxo autorizado de obtenção do XML, sem automatizar login, como o próprio parser prevê) ou remover o parser órfão e corrigir a documentação; DOU: decisão do titular sobre o User-Agent e a conformidade com os termos da fonte.

### Fase 6 — Observabilidade (E9, E11)
- Painel derivado de **um registro** de integrações (flag, credencial, último resultado, latência, erro) cobrindo todas, inclusive as do #836; trocar "CEP/CNPJ público fixo" por estado medido; heartbeat/saúde por resultado também para Planalto/STJ/TJMG/LexML/Câmara/Senado; sondas canário (`scripts/probe_apis.py` já existe) e alerta de rotação da chave do DataJud.
- DataJud: deduplicação por identificador estável do movimento quando existir; remover o código inerte de prazos; resolver a contradição "um worker" × "N workers" (cache/limitador em Redis ou decisão explícita).

### Fase 7 — Esquema e conformidade (E12)
- Converter os `CREATE TABLE IF NOT EXISTS` (14 pontos) em migrations (números reservados, revisão do autogenerate, `alembic upgrade head` do zero em PostgreSQL 16 + pgvector); retirar o DDL do caminho de requisição.
- Registro de **operadores/suboperadores** (Infosimples, provedores de CNPJ, Google, Maritaca/Groq/Anthropic) no ROPA, com base legal e finalidade; avaliar o risco de a consulta revelar o alvo da investigação do escritório.

### Fase 8 — Lacunas desta auditoria
Auditar, em tratamento humano controlado, o Cofre de Credenciais (`credential_vault*`, `credential_registry`, `credential_testers`) e a integração de peticionamento (PDPJ, PJe-MNI REST, eproc); depois, os ingestores linha a linha, `transparencia_service`, `radar_legislativo`, `datajud_sync_service`, tasks do MNI, `jurimetria_tribunais`, o frontend que consome essas rotas e a suíte de testes. Acionar `security-auditor` antes de fechar as Fases 1 a 3.

### Portões de verificação
- Backend: `ruff check app` + pytest da área (testes com `respx`/fixtures, sem rede) + suíte completa uma vez antes do push; com migration, `alembic upgrade head` do zero; testes de banco com `RUN_DB_TESTS=1`.
- Rotas alteradas/removidas: `backend/scripts/ledger_rotas.py --verificar`, baseline em `test_rotas_registro_explicito.py` e snapshot OpenAPI.
- Frontend (se algo consumir as rotas alteradas): `npm run lint && npm test && npm run build`.
- Deploy: somente pela esteira / `RUNBOOK_DEPLOY_MANUAL.md` (regra 9).

## 5. Limitações
Análise estática; nenhuma chamada externa, nenhum teste executado e nenhum acesso à produção (por isso o estado real das flags, das credenciais e da disponibilidade das fontes é desconhecido). O Cofre de Credenciais ficou fora por bloqueio do ambiente e deve ser auditado sob tratamento humano. Contagens de uso/consumidores são por busca textual. E2, E4 e E8 devem ser reproduzidos antes da correção; E5 e E7 dependem de decisão de produto/jurídica do titular (fontes de terceiros, raspagem, termos de uso).
