# Catálogo de APIs e Fontes de Dados — EJC

> Levantamento consolidado em 11/07/2026 (pesquisa multi-fonte com verificação
> documental); reorganizado em 18/07/2026 com **status real verificado no
> código** (backend/app/services/ e backend/app/core/config.py). Itens
> marcados **[NV]** não puderam ser verificados ao vivo (o ambiente de
> pesquisa bloqueava alguns domínios oficiais) — confirmar com uma chamada
> real a partir da VPS antes de integrar.
>
> **Sondagem AO VIVO (11/07/2026, workflow probe-apis)**: BCB SGS 14/14 séries OK
> (incl. Taxa Legal 29543 = 0,706607 em 07/2026; CDI 4391 e IPCA-E 10764
> confirmados), Olinda taxaJuros OK, BrasilAPI feriados OK (13 em 2026),
> IBGE OK, Câmara OK (~13s), Senado OK, STJ CKAN OK (20 datasets), Normas
> RFB OK, ANPD OK, TPU OK, DataJud TJMG OK com a chave pública (~16s),
> Portal Transparência 401 estruturado (falta só token gratuito).
> PTAX respondeu 400 por sintaxe OData do probe (API viva). CNPJ
> (BrasilAPI/OpenCNPJ) 200 com corpo válido (parser do probe truncou).
> ALMG: timeout 25s — integrar com timeout alto e degradação. Querido
> Diário devolveu HTML no probe — reverificar contrato. TCU REST: endpoint
> do probe errado (site oficial ok) — descobrir na implementação.
> DJEN 403 para runner GitHub (WAF) — já integrado no EJC via VPS.

## 1. APIs públicas gratuitas — ativar primeiro

Todas GRATUITAS. Várias **já estão integradas no código** — para essas, "ativar"
significa no máximo ligar uma flag e/ou colar uma credencial gratuita no `.env`.
Legenda de status: ✅ integrado e ligado por default · 🔑 integrado, falta só
credencial/flag · 🔧 integrado, desligado por flag (sem credencial necessária) ·
📋 não integrado — sugestão futura.

### 1.1 Já integradas no EJC (service pronto no backend)

| Fonte | O que resolve no fluxo jurídico | Custo | Status real no código | O que falta para ativar |
|---|---|---|---|---|
| **BCB — SGS + Olinda** (SELIC, IPCA, INPC, IGP-M, TR, poupança, CDI, **Taxa Legal 29543**, taxaJuros, PTAX) | Correção monetária e juros oficiais nos **cálculos judiciais** (Lei 14.905/2024, EC 113/2021); revisional bancária (contrato vs. média do banco); painel de taxas do ramo Bancário | Grátis, sem chave | ✅ `services/indices_service.py` (SGS+Olinda, cache 2 camadas, `INDICES_BCB_ENABLED=True` por default) e `services/bcb_service.py` (painel de taxas) | Nada — já ativo |
| **BrasilAPI — feriados nacionais** | Feriados no **cálculo de prazos processuais** (deadline_calculator); sync automático de anos futuros (Carnaval, Corpus Christi) | Grátis, sem chave | ✅ `services/feriados_service.py` (merge aditivo na tabela `feriados`, `FERIADOS_BRASILAPI_ENABLED=True` por default, job no scheduler) | Nada — já ativo |
| **CEP** (BrasilAPI v2 → ViaCEP) e **CNPJ** (OpenCNPJ → BrasilAPI → ReceitaWS) | Cadastro instantâneo de cliente PF/PJ (endereço por CEP; razão social/QSA/CNAE por CNPJ) + validação de dígitos CPF/CNPJ offline | Grátis, sem chave | ✅ `services/validators_service.py` (cadeia de fallback multi-fonte) + endpoints `/utils/cep/{cep}` e `/utils/cnpj/{cnpj}` em `routers/utils.py` — sem flag, sempre ativo | Nada — já ativo |
| **DataJud / CNJ** (API Pública) | Consulta de movimentações processuais por número CNJ em qualquer tribunal; sync automático dos casos dos clientes; base dos andamentos | Grátis — chave **pública** divulgada pelo CNJ na wiki do DataJud | 🔑 `services/datajud_service.py` + `services/datajud_sync_service.py` (retry, alias por tribunal). Default `DATAJUD_ENABLED=False`, `DATAJUD_API_KEY=""` | Colar a chave pública em `DATAJUD_API_KEY` e ligar `DATAJUD_ENABLED=true` (e opcionalmente `DATAJUD_SYNC_ENABLED=true`) |
| **Portal da Transparência (CGU)** — CEIS/CNEP/CEPIM | **Due diligence da parte contrária**: sanções por CNPJ (inidoneidade, Lei Anticorrupção, impedimento de convênio) | Grátis — token emitido por cadastro de e-mail no portal | 🔑 `services/transparencia_service.py` (3 bases, cache diário, retenção LGPD 7 dias). Default `TRANSPARENCIA_ENABLED=False`, `TRANSPARENCIA_API_KEY=""`. Probe ao vivo: 401 estruturado — **falta só o token** | Pedir o token gratuito por e-mail, colar em `TRANSPARENCIA_API_KEY` e ligar `TRANSPARENCIA_ENABLED=true` |
| **DJEN / Comunica CNJ** | Captura de intimações/publicações por OAB; vincula ao caso, cria movimento e alerta (o advogado define o prazo — decisão HITL) | Grátis, sem auth | 🔧 `services/djen_service.py`. Default `DJEN_INGEST_ENABLED=False`; exige `DJEN_OABS_MONITORADAS`. WAF bloqueia runner GitHub — rodar da VPS | Ligar `DJEN_INGEST_ENABLED=true` e cadastrar as OABs monitoradas |
| **PNCP — Contratações Públicas** (Lei 14.133/2021) | Consulta pública de contratações por data/UF/município/modalidade (contexto de direito administrativo) | Grátis, sem chave | ✅ `services/pncp_service.py` (cache, filtros validados, timeout/retry). Default `PNCP_ENABLED=True` | Nada — consulta já ativa; APIs de manutenção ficam fora de escopo |
| **Jurisprudência TJMG** (crawler) | Precedentes do tribunal da casa na base de conhecimento | Grátis (portal público, sem API — crawler) | 🔧 `TJMG_INGEST_ENABLED=False` por default; mudanças no portal podem exigir manutenção | Ligar `TJMG_INGEST_ENABLED=true` |

Obs.: o cliente experimental duplicado `core/public_apis.py` foi removido.
A fonte canônica de índices é `indices_service.py`; CEP/CNPJ usam
`validators_service.py`; jurisprudência entra somente por conectores reais e
fontes verificáveis, nunca por endpoint ilustrativo.

### 1.2 Públicas gratuitas ainda NÃO integradas (📋 sugestão futura — ordem de valor)

| Fonte | O que dá | Acesso | Módulo EJC |
|---|---|---|---|
| **IBGE Agregados/SIDRA** | IPCA/INPC/IPCA-15 na fonte primária | REST JSON sem auth (probe OK) | Cálculos (dupla checagem dos índices BCB) |
| **BCB — Ranking de reclamações** | Índice de reclamações por banco, trimestral | OData/CSV sem auth | Bancário (fundamentar falha sistêmica) |
| **TCU — Webservices** | API REST de acórdãos + bulk de 5 bases de jurisprudência | REST JSON sem auth (endpoint do probe errado — descobrir na implementação) | Base de conhecimento (adm. público) |
| **Câmara dos Deputados v2** | PLs, tramitações, votações por tema/keyword | REST JSON sem auth | Radar Regulatório |
| **Senado — Dados Abertos** | Matérias, movimentações, LegislacaoService | REST XML/JSON sem auth (modernizado 05/2025 — abstrair client) | Radar Regulatório |
| **ALMG — /api/v2** | PLs **estaduais MG**, legislação mineira | REST JSON/XML sem auth [NV limites]; timeout alto + degradação | Radar Regulatório (MG) |
| **CNJ — TPU/SGT** | Tabelas processuais unificadas (classes/assuntos/movimentos) | SOAP público sem auth + download Excel/SQL | Normalização de dados processuais |
| **STJ Dados Abertos** | Inteiro teor de decisões (CKAN) | Bulk sem auth | Base de conhecimento (já parcialmente usado na ingestão) |
| **INLABS (Imprensa Nacional)** | DOU completo em XML diário | Cadastro gratuito + ZIPs por seção; scripts oficiais Python | Radar de normas novas (D+0) |
| **Querido Diário** | Diários oficiais municipais (busca textual) | REST JSON sem auth (~60 req/min); BH coberto; **Betim [NV]**; probe devolveu HTML — reverificar contrato | Radar municipal |
| **ANPD (scraping leve)** | Regulamentos, guias e sanções LGPD | HTML/PDF gov.br (estável) | Base de conhecimento (LGPD) |
| **Normas RFB (sijut2consulta)** | IN, ADI, Soluções de Consulta COSIT consolidadas | Querystring parametrizável (sem API oficial) | Base de conhecimento (tributário) |
| **PGFN Dívida Ativa** | Inscritos em dívida ativa da União/FGTS | CSV bulk trimestral sem auth | Due diligence |
| **IBAMA Dados Abertos + IDE-Sisema MG** | Autos de infração, embargos (coordenadas); ~790 camadas geo de MG (WMS/WFS) | CSV/OGC sem auth | Ambiental (due diligence, sobreposição de imóvel) |
| **ANS (FTP aberto)** | Reclamações NIP contra planos de saúde, IGR | CSV bulk sem auth | Consumidor/saúde suplementar |
| **Consumidor.gov.br / Sindec / Anatel / ANAC** | Reclamações por empresa/tema | CSV bulk mensal/anual | Consumidor (prova estatística) |
| **INSS/Dataprev Dados Abertos** | Benefícios concedidos/cessados por espécie/UF | CSV bulk mensal | Previdenciário (analytics) |
| **CAGED/RAIS (PDET)** | Microdados de vínculos e salários | FTP anônimo (.7z) | Trabalhista (fundamentar cálculos) |
| **STF Corte Aberta** | Estatísticas e decisões (CSV; espelho BigQuery na Base dos Dados) | CSV/BigQuery | Constitucional (RAG/analytics) |
| **minha-receita (self-host)** | CNPJ completo self-hosted (complementa a cadeia já integrada em `validators_service.py`) | Self-host possível | Cadastro de clientes PJ |

## 2. Pagas / credenciamento — opcionais

Nenhuma é pré-requisito do fluxo: o núcleo (processos, prazos, cálculos,
cadastro, due diligence básica) roda 100% com as gratuitas da seção 1.

| Fonte | O que dá | Como contratar | Status real no código / Observação |
|---|---|---|---|
| **Infosimples** (PAGO, por consulta) | TJMG processo, Receita CPF/CNPJ, DETRAN-MG, IBAMA, CAR e centenas de consultas | Conta + créditos pré-pagos (api.infosimples.com/cadastro) | 🔑 Conector **já pronto** no EJC: `services/infosimples_service.py` com teto diário de custo (`INFOSIMPLES_MAX_CONSULTAS_DIA=50`), cache do dia e retenção LGPD. Default `INFOSIMPLES_ENABLED=False`; falta contratar e colar `INFOSIMPLES_TOKEN` |
| **MNI eproc-TJMG** (credenciamento, sem custo por consulta) | Consulta processual + avisos direto na fonte | Ofício ao Presidente do TJMG + certificado ICP-Brasil (Portaria Conjunta 1720/PR/2025) [NV se admite escritório privado] | 📋 Não integrado. TJMG migra PJe→eproc até fim de 2026 — mirar eproc; iniciar o ofício já |
| **Escavador API** (PAGO) | Monitoramento processual multi-tribunal + diários | Créditos pré-pagos, sem mensalidade mínima alta | 📋 Não integrado. Melhor custo/benefício p/ escritório de 5 advogados |
| **Serasa/SPC/BoaVista** (PAGO — birôs de crédito) | Score, negativação, protestos | Contrato PJ (SPC via CDL Betim); justificativa LGPD obrigatória | 📋 Não integrado. Preço sob proposta |
| **SERPRO/Dataprev comerciais** (PAGO) | CPF/CNPJ oficiais em tempo real | Contrato comercial | 📋 Não integrado. O Conecta gov.br é só para órgãos públicos |

## Prioridade P2 — monitorar

- **APIs do Codex/CNJ para iniciativa privada** — regulamentação aprovada em ago/2024 (alteração da Res. 121/2010), produto ainda não lançado até jul/2026. Quando sair, tende a substituir agregadores para consulta processual nacional com inteiro teor.
- **Judit.io** (monitoramento, a partir de R$1.000/mês — só com volume grande), JusBrasil/Digesto e Predictus (enterprise).
- **IOF-MG (Jornal Minas Gerais)** — sem API; acervo roda DSpace (testar OAI-PMH `jornal.iof.mg.gov.br/oai/request` [NV]).
- **Normas.leg.br** — normas versionadas (ideal p/ "norma alterada"), sem API pública confirmada.
- **BNMP 3.0** — consulta pública web; endpoint REST do portal existe mas sem termos oficiais [NV].

## Sem API (fluxo realista = portal web + anexar PDF no EJC)

Cartórios (CENSEC, e-Notariado, CRC), **ONR/Registro de Imóveis** (advogado usa SAEC pagando por ato), CNIB (consulta restrita), **INSS individual** (Meu INSS com procuração; parser de PDF do CNIS é o caminho para automação), custas TJMG (reimplementar cálculo a partir das tabelas anuais em PDF), emolumentos cartórios MG (idem), tabelas INSS/FGTS (portaria anual — rotina interna), e-SAJ/TJSP (só DataJud+DJEN+agregadores), jurisprudência TJMG (sem API; agregadores).

## Tributário MG / Betim (aprofundamento)

- **SEF-MG**: sem API verificada. RICMS/MG, resoluções e orientações DOLT/SUTRI são páginas web raspáveis → **ingestão na base de conhecimento**. e-ITCD é transacional (login gov.br). ITCD = 5% fixo (Lei 14.941/03) — cálculo trivial em tabela interna. Jurisprudência do Conselho de Contribuintes MG: verificar acesso programático [NV].
- **Betim**: ISS/IPTU/ITBI municipais sem API conhecida [NV — pendência de verificação in loco]; Código Tributário Municipal e leis municipais → ingestão via LeisMunicipais/portal da prefeitura; diário oficial próprio (verificar cobertura no Querido Diário via `/api/cities?city_name=Betim`); NFS-e padrão nacional (gov.br) para emissão.
- **CONFAZ**: convênios ICMS em texto público → base de conhecimento.

## Complementos MG (indicados pelo dono)

- **ALMG Swagger v2**: `dadosabertos.almg.gov.br/api/ajuda/swagger/view/lastest` — confirma a API estadual (seção 1.2 acima).
- **dados.mg.gov.br**: portal CKAN de dados abertos do Estado de MG — tem **API de catálogo padrão CKAN** (listar/baixar datasets programaticamente); vasculhar datasets de segurança, saúde e fazenda conforme demanda de caso [NV inventário completo].
- **Prodemge transparência** (`prodemge.gov.br/transparencia`): institucional da empresa de TI do Estado — não é fonte de dados de caso; útil só como referência de quem opera os sistemas estaduais.
- **Conecta — API dos Serviços Estaduais** (`gov.br/conecta/catalogo/apis/api-dos-servicos-estaduais`): catálogo de serviços públicos estaduais; como as demais do Conecta, **adesão restrita a órgãos públicos** — sem acesso privado direto [NV].
- **Portal da Transparência (federal)**: já integrado (seção 1.1) — token gratuito por e-mail, sanções CEIS/CNEP para due diligence.

## Plano de ativação recomendado (ordem)

1. **Já ativos por default** — BCB SGS/Olinda (`indices_service.py`), feriados BrasilAPI (`feriados_service.py`), CEP/CNPJ (`validators_service.py`): nada a fazer.
2. **DataJud/CNJ** — colar a chave pública gratuita no `.env` e ligar as flags: consulta processual + sync de andamentos imediato, custo zero.
3. **Portal da Transparência** — pedir o token gratuito por e-mail e ligar: due diligence de sanções por CNPJ.
4. **DJEN + TJMG** — ligar as flags após validar na VPS; o **PNCP consulta já fica ativo por padrão**.
5. **Novas integrações gratuitas** (seção 1.2) — começar por IBGE (dupla checagem de índices), Câmara/Senado/ALMG (Radar Regulatório) e TCU/STJ/ANPD/Normas RFB (base de conhecimento).
6. **Pagas/credenciamento** (seção 2) — apenas quando houver demanda: Infosimples (conector pronto, falta token pago) e ofício do MNI eproc-TJMG (Portaria 1720/2025, sem custo por consulta após credenciado).

## Regras jurídicas de cálculo (referência para o módulo)

- **EC 113/2021, art. 3º**: condenações da Fazenda Pública → SELIC acumulada, aplicada uma única vez (sem cumulação com outros índices), desde 09/12/2021.
- **Lei 14.905/2024** (vigência 30/08/2024): correção monetária = IPCA (CC art. 389); juros legais = Taxa Legal = SELIC − IPCA (CC art. 406, Res. CMN 5.171/2024). O BCB publica a Taxa Legal pronta na série SGS **29543**.
- Fatores "carimbados" de TJMG/CJF não têm API — reconstruir a partir das séries SGS conforme o Manual de Cálculos do CJF, com smoke test dos códigos no deploy.
