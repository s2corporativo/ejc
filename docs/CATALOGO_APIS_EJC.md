# Catálogo de APIs e Fontes de Dados — EJC

> Levantamento consolidado em 11/07/2026 (pesquisa multi-fonte com verificação
> documental). Itens marcados **[NV]** não puderam ser verificados ao vivo
> (o ambiente de pesquisa bloqueava alguns domínios oficiais) — confirmar com
> uma chamada real a partir da VPS antes de integrar.
>
> Já integrados no EJC: DataJud/CNJ, LexML SRU, STJ Dados Abertos, DJEN/Comunica
> CNJ, Infosimples (TJMG processo + Receita CPF/CNPJ), Google Drive, BCB (a
> integrar), Anthropic/Groq.

## Prioridade P0 — integrar já (alto valor, gratuito, acesso fácil)

| Fonte | O que dá | Acesso | Módulo EJC |
|---|---|---|---|
| **BCB — API SGS** | SELIC (11 diária, 432 meta, 4390 acum. mês), IPCA (433), INPC (188), IGP-M (189), IPCA-15 (7478), IPCA-E (10764 [NV periodicidade]), TR (226), poupança (25/195) e **Taxa Legal Lei 14.905/2024 (29543)** já calculada | REST JSON sem auth; janela máx. 10 anos por consulta; cachear | **Cálculos judiciais** (correção monetária + juros oficiais) |
| **BCB — Olinda taxaJuros** | Taxa de juros por **instituição e modalidade** (diária/mensal) | OData JSON sem auth | **Revisional bancária** (comparar contrato vs. média do próprio banco) |
| **BCB — Ranking de reclamações** | Índice de reclamações por banco, trimestral | OData/CSV sem auth | Bancário (fundamentar falha sistêmica) |
| **BrasilAPI** | CEP (com fallback multi-fonte), **feriados nacionais**, CNPJ, taxas, bancos | REST sem auth | **Prazos** (feriados!), cadastro |
| **OpenCNPJ / minha-receita** | CNPJ completo (QSA, CNAEs, Simples) | OpenCNPJ: 50 req/s sem auth; minha-receita: self-host possível | Cadastro de clientes PJ |
| **TCU — Webservices** | API REST de acórdãos + bulk de 5 bases de jurisprudência | REST JSON sem auth | Base de conhecimento (adm. público) |
| **Portal da Transparência (CGU)** | Sanções CEIS/CNEP/CEPIM, contratos, convênios | REST com token gratuito (cadastro e-mail) | Due diligence de parte contrária |
| **Câmara dos Deputados v2** | PLs, tramitações, votações por tema/keyword | REST JSON sem auth | Radar Regulatório |
| **Senado — Dados Abertos** | Matérias, movimentações, LegislacaoService | REST XML/JSON sem auth (modernizado 05/2025 — abstrair client) | Radar Regulatório |
| **ALMG — /api/v2** | PLs **estaduais MG**, legislação mineira | REST JSON/XML sem auth [NV limites] | Radar Regulatório (MG) |
| **CNJ — TPU/SGT** | Tabelas processuais unificadas (classes/assuntos/movimentos) | SOAP público sem auth + download Excel/SQL | Normalização de dados processuais |
| **STJ Dados Abertos** | Inteiro teor de decisões (CKAN) | Bulk sem auth | Base de conhecimento (já parcialmente usado) |
| **INLABS (Imprensa Nacional)** | DOU completo em XML diário | Cadastro gratuito + ZIPs por seção; scripts oficiais Python | Radar de normas novas (D+0) |
| **Querido Diário** | Diários oficiais municipais (busca textual) | REST JSON sem auth (~60 req/min); BH coberto; **Betim [NV]** | Radar municipal |
| **ANPD (scraping leve)** | Regulamentos, guias e sanções LGPD | HTML/PDF gov.br (estável) | Base de conhecimento (LGPD) |
| **Normas RFB (sijut2consulta)** | IN, ADI, Soluções de Consulta COSIT consolidadas | Querystring parametrizável (sem API oficial) | Base de conhecimento (tributário) |
| **PGFN Dívida Ativa** | Inscritos em dívida ativa da União/FGTS | CSV bulk trimestral sem auth | Due diligence |
| **IBAMA Dados Abertos + IDE-Sisema MG** | Autos de infração, embargos (coordenadas); ~790 camadas geo de MG (WMS/WFS) | CSV/OGC sem auth | Ambiental (due diligence, sobreposição de imóvel) |
| **ANS (FTP aberto)** | Reclamações NIP contra planos de saúde, IGR | CSV bulk sem auth | Consumidor/saúde suplementar |
| **Consumidor.gov.br / Sindec / Anatel / ANAC** | Reclamações por empresa/tema | CSV bulk mensal/anual | Consumidor (prova estatística) |
| **INSS/Dataprev Dados Abertos** | Benefícios concedidos/cessados por espécie/UF | CSV bulk mensal | Previdenciário (analytics) |
| **CAGED/RAIS (PDET)** | Microdados de vínculos e salários | FTP anônimo (.7z) | Trabalhista (fundamentar cálculos) |
| **STF Corte Aberta** | Estatísticas e decisões (CSV; espelho BigQuery na Base dos Dados) | CSV/BigQuery | Constitucional (RAG/analytics) |
| **IBGE Agregados/SIDRA** | IPCA/INPC/IPCA-15 na fonte primária | REST JSON sem auth | Cálculos (dupla checagem) |
| **PTAX (Olinda)** | Câmbio oficial diário | OData sem auth | Cálculos com moeda estrangeira |

## Prioridade P1 — próxima leva (alto valor, exige contratação/credenciamento)

| Fonte | O que dá | Como contratar | Observação |
|---|---|---|---|
| **Infosimples** (em integração) | TJMG processo, Receita CPF/CNPJ, DETRAN-MG, IBAMA, CAR e centenas de consultas | Conta + créditos pré-pagos (api.infosimples.com/cadastro) | Conector pronto no EJC com teto de custo e cache |
| **MNI eproc-TJMG** | Consulta processual + avisos direto na fonte, sem custo por consulta | Ofício ao Presidente do TJMG + certificado ICP-Brasil (Portaria Conjunta 1720/PR/2025) [NV se admite escritório privado] | TJMG migra PJe→eproc até fim de 2026 — mirar eproc |
| **Escavador API** | Monitoramento processual multi-tribunal + diários | Créditos pré-pagos, sem mensalidade mínima alta | Melhor custo/benefício p/ escritório de 5 advogados |
| **Serasa/SPC/BoaVista** | Score, negativação, protestos | Contrato PJ (SPC via CDL Betim); justificativa LGPD obrigatória | Preço sob proposta |
| **SERPRO/Dataprev comerciais** | CPF/CNPJ oficiais em tempo real | Contrato comercial | O Conecta gov.br é só para órgãos públicos |

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

- **ALMG Swagger v2**: `dadosabertos.almg.gov.br/api/ajuda/swagger/view/lastest` — confirma a API estadual (P0 acima).
- **dados.mg.gov.br**: portal CKAN de dados abertos do Estado de MG — tem **API de catálogo padrão CKAN** (listar/baixar datasets programaticamente); vasculhar datasets de segurança, saúde e fazenda conforme demanda de caso [NV inventário completo].
- **Prodemge transparência** (`prodemge.gov.br/transparencia`): institucional da empresa de TI do Estado — não é fonte de dados de caso; útil só como referência de quem opera os sistemas estaduais.
- **Conecta — API dos Serviços Estaduais** (`gov.br/conecta/catalogo/apis/api-dos-servicos-estaduais`): catálogo de serviços públicos estaduais; como as demais do Conecta, **adesão restrita a órgãos públicos** — sem acesso privado direto [NV].
- **Portal da Transparência (federal)**: já em P0 — token gratuito por e-mail, sanções CEIS/CNEP para due diligence.

## Top 5 recomendado (ordem de implementação)

1. **BCB SGS + Olinda** — motor de atualização monetária/juros com número oficial (inclui Taxa Legal pós-Lei 14.905/2024). Maior impacto imediato nas calculadoras.
2. **BrasilAPI feriados + CEP + OpenCNPJ** — feriados no cálculo de prazos e cadastro instantâneo de cliente. Esforço baixíssimo.
3. **Câmara v2 + Senado + ALMG** — Radar Regulatório de verdade (federal + estadual MG) por tema.
4. **TCU + STJ + ANPD + Normas RFB** — ingestão contínua na base de conhecimento (a IA passa a citar fontes oficiais atualizadas).
5. **MNI eproc-TJMG (credenciamento)** — consulta processual do tribunal da casa direto na fonte, sem custo por consulta; iniciar o ofício da Portaria 1720/2025 já.

## Regras jurídicas de cálculo (referência para o módulo)

- **EC 113/2021, art. 3º**: condenações da Fazenda Pública → SELIC acumulada, aplicada uma única vez (sem cumulação com outros índices), desde 09/12/2021.
- **Lei 14.905/2024** (vigência 30/08/2024): correção monetária = IPCA (CC art. 389); juros legais = Taxa Legal = SELIC − IPCA (CC art. 406, Res. CMN 5.171/2024). O BCB publica a Taxa Legal pronta na série SGS **29543**.
- Fatores "carimbados" de TJMG/CJF não têm API — reconstruir a partir das séries SGS conforme o Manual de Cálculos do CJF, com smoke test dos códigos no deploy.
