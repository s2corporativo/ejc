# Baseline de integrações e APIs públicas — 2026-10-01

## Objetivo

Registrar, sem credenciais ou dados pessoais, o contrato técnico que o EJC deve usar para cada integração pública relevante e separar três conceitos que não podem ser confundidos:

1. **configurado**: feature flag e parâmetros locais suficientes;
2. **homologado**: houve prova operacional recente do endpoint correto;
3. **bloqueado/atenção**: a fonte existe, mas a origem de rede, rate-limit, anti-bot, DNS ou outro fator externo impede comprovar a coleta.

Este documento é evidência operacional. Não substitui o estado persistido do painel.

## Matriz técnica

| Integração | Endpoint/contrato confirmado | Natureza | Evidência em 2026-10-01 | Decisão para o EJC |
|---|---|---|---|---|
| DataJud/CNJ | `https://api-publica.datajud.cnj.jus.br/{alias}/_search` | API pública oficial; chave pública rotativa do CNJ | Documentação oficial confirma aliases por tribunal, inclusive `api_publica_tjmg`, `api_publica_trt3` e `api_publica_trf6` | Manter cliente atual. Nunca versionar a chave; obtê-la/configurá-la pelo mecanismo seguro já existente. |
| DJEN/CNJ | `https://comunicaapi.pje.jus.br/api/v1/comunicacao` | GET público sem autenticação; POST/DELETE protegidos para tribunais | Swagger DJEN 1.0.4 declara API pública; GET aceita OAB/processo/data e `itensPorPagina` somente 5 ou 100; 429 requer recuo | Corrigido para 100 itens/página; 4xx/429 não têm retry imediato. Bloqueio geográfico continua sendo falha externa, nunca “zero publicações”. |
| SGT/CNJ | `https://www.cnj.jus.br/sgt/sgt_ws.php?wsdl` | SOAP público oficial | WSDL e operações públicas confirmados; probe da VPS respondeu HTTP 200 XML | Manter cliente atual. |
| TCU | `https://dados-abertos.apps.tcu.gov.br/api/acordao/recupera-acordaos` | REST oficial de acórdãos | Documentação oficial do TCU confirma GET e contrato JSON | Manter cliente atual. |
| IBGE Localidades | `https://servicodados.ibge.gov.br/api/v1/localidades` | REST oficial | Documentação oficial v1.0.0 e probe da VPS HTTP 200 | Manter cliente atual. |
| IBAMA Dados Abertos | `https://dadosabertos.ibama.gov.br/api/3/action` | CKAN oficial | Portal declara API CKAN; probe `package_search` HTTP 200 JSON | Manter, mas só marcar homologado com prova operacional persistida. |
| TSE Dados Abertos | `https://dadosabertos.tse.jus.br/api/3/action` | CKAN oficial | Portal TSE declara API CKAN; probe HTTP 200 JSON | Manter. |
| CVM Dados Abertos | `https://dados.cvm.gov.br/api/3/action` | CKAN atual | Portal CKAN respondeu HTTP 200. O PDA 2026-2028 anuncia uma API pública futura mais ampla; ela ainda não substitui o CKAN atual | Manter CKAN e não migrar para API futura ainda não publicada. |
| MJ/Senacon — dados abertos | `https://dados.mj.gov.br/api/3/action` | CKAN de dados abertos | Portal oficial continua indexado e publica bases Consumidor.gov.br; da VPS o host não resolveu DNS nesta data | Manter como configurado/atenção; não trocar por endpoint não equivalente. |
| Consumidor.gov.br — operações | documentação do próprio Consumidor.gov.br | REST autenticado para credenciadas | API exige habilitação e credenciais da entidade para consultar/responder suas reclamações | Tratar como integração distinta; não usar como substituto anônimo dos dados abertos. |
| PGFN | página oficial de Dados Abertos / arquivos CSV trimestrais | bulk oficial, não API de consulta equivalente | PGFN confirma bases completas em CSV segmentadas por sistema/UF | Manter descoberta/download controlado de arquivos oficiais; não inventar REST inexistente. |
| Querido Diário | `https://api.queridodiario.org.br` | API pública secundária | Swagger 0.19.0 atual expõe `/gazettes`, `/cities`, temas e agregados; probe da VPS HTTP 200 | Manter host atual e proveniência obrigatória para fonte oficial municipal. |
| IDE-Sisema/MG | `https://geoserver.meioambiente.mg.gov.br/ows` | OGC WFS/WMS/WCS oficial | Geoportal e GeoServer oficiais confirmam WFS 2.0; probe GetCapabilities HTTP 200 XML | Manter WFS com allowlist e limites atuais. |
| TJMG Jurisprudência | portal `www5.tjmg.jus.br/jurisprudencia` | interface web pública | Portal/ajuda oficiais existem; não foi localizada documentação oficial de API pública de jurisprudência equivalente | Não inventar API. Manter falha explícita/fail-fast enquanto o POST automatizado for recusado; DataJud não substitui inteiro teor jurisprudencial. |
| LexML | portal `www.lexml.gov.br`; OAI-PMH é padrão de intercâmbio da rede | portal/federador; OAI-PMH para metadados | Documentação do projeto confirma OAI-PMH como mecanismo de coleta/intercâmbio, mas não foi confirmado endpoint central de busca por palavra equivalente ao portal | Não contornar anti-bot. Manter fail-fast e estudar ingestão via provedores OAI-PMH somente com endpoint oficial verificável. |

## Regras operacionais

- **Nenhuma feature flag, URL válida ou credencial presente prova disponibilidade.** Sem evidência operacional recente, o painel deve exibir atenção/não homologado.
- **HTTP 403, 422 e 429 não recebem retry imediato no DJEN.** Falhas 5xx e de transporte podem receber retry curto e limitado.
- **HTTP 429 do DJEN não deve ser contornado com múltiplos IPs.** A documentação do CNJ classifica essa prática como uso abusivo.
- **DJEN com bloqueio geográfico não equivale a ausência de publicações.**
- **TJMG e LexML não devem receber scraping agressivo nem bypass de anti-bot/WAF.**
- **DataJud é metadado processual e movimentações.** Não deve ser apresentado como substituto de inteiro teor de jurisprudência ou do DJEN.
- **Querido Diário é fonte secundária.** O EJC deve preservar a URL/documento municipal oficial para conferência.
- **PGFN bulk pode conter dados pessoais.** Aplicar minimização, finalidade, controle de acesso, retenção e logs sem CPF/CNPJ completos quando não necessários.

## Probes controlados da VPS nesta auditoria

Resultados sem credenciais e com uma chamada leve por fonte:

- Querido Diário novo host: HTTP 200.
- CVM CKAN: HTTP 200 JSON.
- TSE CKAN: HTTP 200 JSON.
- IBAMA CKAN: HTTP 200 JSON.
- IBGE Localidades: HTTP 200 JSON.
- CNJ/SGT WSDL: HTTP 200 XML.
- IDE-Sisema WFS GetCapabilities: HTTP 200 XML.
- MJ Dados Abertos: falha de resolução DNS a partir da VPS nesta data.

Esses probes servem como baseline de **2026-10-01** e não devem ser hardcoded como estado permanente.

## Revalidação independente — 2026-10-02

Pesquisa documental e probes controlados foram repetidos antes da promoção para produção. O objetivo foi confirmar contratos oficiais e registrar divergências operacionais sem transformar falha externa em sucesso.

### Contratos confirmados em fonte primária

- **DJEN/CNJ:** Swagger oficial v1.0.4 confirma `GET /api/v1/comunicacao` como consulta pública; pesquisas por OAB/texto/processo são limitadas a 10.000 resultados; `itensPorPagina` aceita somente 5 ou 100; HTTP 429 orienta aguardar 1 minuto e proíbe contorno por múltiplos IPs. Também existem `GET /api/v1/comunicacao/tribunal` e `GET /api/v1/caderno/{sigla_tribunal}/{data}/{meio}`.
- **DataJud/CNJ:** permanece a API oficial para metadados de capa e movimentações processuais, sem equivaler a inteiro teor de jurisprudência nem substituir o DJEN.
- **TCU:** o webservice oficial de acórdãos continua documentado em `/api/acordao/recupera-acordaos`.
- **IBAMA, TSE e CVM:** continuam em CKAN; a CVM anunciou no PDA 2026-2028 uma API pública mais ampla futura, mas sem substituição documentada do CKAN atual.
- **Consumidor.gov.br:** a API operacional é REST autenticada e destinada a credenciadas; não deve ser confundida com dados abertos anônimos.
- **PGFN:** a fonte oficial continua sendo distribuição bulk trimestral em CSV; não foi localizada API REST oficial equivalente à base completa.
- **IDE-Sisema/MG:** GeoServer oficial continua expondo WFS/WMS/WCS.
- **TJMG Jurisprudência:** há portal público e documentação de uso, mas não foi localizada API pública oficial equivalente para pesquisa automatizada de inteiro teor; não inventar endpoint.
- **LexML:** a arquitetura oficial documenta OAI-PMH para coleta/intercâmbio de metadados, mas não foi confirmado endpoint central oficial de busca textual equivalente ao portal; manter fail-fast no portal e só integrar provedor OAI-PMH com endpoint oficial comprovado.

### Probes da VPS em 2026-10-02

Uma chamada leve por fonte, sem credenciais e sem bypass:

- DJEN `/api/v1/comunicacao?itensPorPagina=5`: **HTTP 403**.
- DJEN `/api/v1/comunicacao/tribunal`: **HTTP 403**.
- DJEN `/api/v1/caderno/TJMG/2026-10-01/D`: **HTTP 403**.
- IBGE Localidades: **HTTP 200 JSON**.
- TSE CKAN: **HTTP 200 JSON**.
- CVM CKAN: **HTTP 200 JSON**.
- TCU Acórdãos: **HTTP 200 JSON**.
- IDE-Sisema WFS GetCapabilities: **HTTP 200 XML**.
- IBAMA CKAN: **HTTP 502** nesta execução; tratar como indisponibilidade transitória/atenção, não como contrato inválido.
- Querido Diário `/health`: **timeout** a partir da VPS nesta execução; manter atenção até nova prova operacional.

### Decisão de arquitetura após a revalidação

1. Não criar fallback não oficial para DJEN: os três endpoints oficiais testados estão bloqueados pela origem atual.
2. Não usar DataJud como substituto do DJEN ou da jurisprudência de inteiro teor do TJMG.
3. Não contornar WAF, anti-bot, geoblock ou rate-limit com proxy aleatório, rotação de IP ou scraping agressivo.
4. O painel só deve promover um conector público de `attention/nao_homologado` para `ready/ok` após prova operacional persistida.
5. IBAMA e Querido Diário devem permanecer em atenção enquanto a VPS não produzir nova prova positiva.

## Fontes oficiais consultadas

- CNJ — API Pública DataJud: https://www.cnj.jus.br/sistemas/datajud/api-publica/
- CNJ — endpoints DataJud: https://datajud-wiki.cnj.jus.br/api-publica/endpoints/
- CNJ — Swagger DJEN: https://hcomunicaapi.cnj.jus.br/swagger/djen.yml
- CNJ — SGT WebService: https://www.cnj.jus.br/sgt/infWebService.php
- TCU — Webservices: https://sites.tcu.gov.br/dados-abertos/webservices-tcu/
- IBGE — API Localidades: https://servicodados.ibge.gov.br/api/docs/localidades
- TSE — Dados Abertos: https://dadosabertos.tse.jus.br/
- IBAMA — Dados Abertos: https://dadosabertos.ibama.gov.br/
- CVM — Dados Abertos/PDA: https://www.gov.br/cvm/pt-br/acesso-a-informacao-cvm/dados-abertos
- MJ/Senacon — Dados Abertos: https://dados.mj.gov.br/
- Consumidor.gov.br — documentação API: https://consumidor.gov.br/pages/principal/documentacao-api
- PGFN — Dados Abertos: https://www.gov.br/pgfn/pt-br/assuntos/divida-ativa-da-uniao/transparencia-fiscal-1/dados-abertos
- Querido Diário — Swagger: https://api.queridodiario.org.br/docs
- IDE-Sisema — Geoportal: https://geoportal.meioambiente.mg.gov.br/home
- TJMG — Pesquisa de Jurisprudência: https://www5.tjmg.jus.br/jurisprudencia/formEspelhoAcordao.do
- LexML — padrões/arquitetura: https://projeto.lexml.gov.br/institucional/historia

## Rollback

Este baseline é documental. A remoção do arquivo não altera execução. As alterações de código associadas devem ser revertidas pelo commit/PR correspondente, sem migration e sem modificação de dados.
