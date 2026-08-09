# Onda #836 — Integrações públicas oficiais do EJC

Data: 08/08/2026

## Objetivo

Ampliar as fontes públicas do EJC sem criar novos módulos de menu, sem tocar
credenciais e sem transformar o backend em proxy aberto. Todas as rotas novas
ficam sob JWT e rate limit no gateway já montado em `app/integrations/routers.py`.

## Fontes implementadas

| Fonte | Implementação | Uso no EJC | Observação |
|---|---|---|---|
| CNJ SGT/TPU | `integrations/cnj_sgt_client.py` | classes, assuntos e movimentos oficiais | SOAP público, sem chave |
| TCU Dados Abertos | `integrations/tcu_client.py` + `services/juris_import/tcu.py` | Administrativo/RAG | busca limitada; não baixa PDF automaticamente |
| IBGE Localidades | `integrations/ibge_localidades_client.py` | canonicalização município/UF/código IBGE | REST oficial |
| IBAMA Dados Abertos | `integrations/ckan_public_client.py` | catálogo de autos/embargos e demais datasets | CKAN oficial; arquivos bulk só por link |
| Consumidor.gov/SENACON | `integrations/ckan_public_client.py` (fonte `mj`) | catálogo oficial de reclamações | mantém estimativas internas separadas |
| CVM Dados Abertos | `integrations/ckan_public_client.py` (fonte `cvm`) | societário/compliance | catálogo de recursos oficiais |
| TSE Dados Abertos | `integrations/ckan_public_client.py` (fonte `tse`) | compliance documental | somente catálogo público; sem perfilamento político |
| PGFN Dados Abertos | `integrations/pgfn_open_data_client.py` | due diligence tributária | descobre arquivos bulk; sem consulta individual |
| Querido Diário | `integrations/querido_diario_client.py` | diários municipais | agregador secundário; conferir publicação original |
| IDE-Sisema/MG | `integrations/ide_sisema_client.py` | Ambiental/geoespacial | WFS 2.0, camada e BBOX validados |
| INLABS/DOU XML | `integrations/inlabs_parser.py` | processamento estruturado do DOU | sem automação de login; exige conferência na versão certificada |

## Rotas

O objeto historicamente chamado `brasilapi_router` permanece com o mesmo nome
para não exigir alteração em `main.py`, mas seu prefixo interno passa a ser
`/integracoes`. As rotas BrasilAPI receberam `/brasilapi` explicitamente, de
modo que os paths externos existentes não mudam.

Rotas adicionadas:

- `GET /api/integracoes/cnj/tpu/versao`
- `GET /api/integracoes/cnj/tpu/pesquisar`
- `GET /api/integracoes/tcu/acordaos`
- `GET /api/integracoes/ibge/municipios/{uf}`
- `GET /api/integracoes/ibge/canonicalizar`
- `GET /api/integracoes/dados-publicos/{fonte}/recursos` (`ibama|mj|cvm|tse`)
- `GET /api/integracoes/pgfn/divida-ativa/recursos`
- `GET /api/integracoes/querido-diario/{codigo_ibge}`
- `GET /api/integracoes/ide-sisema/camadas`
- `GET /api/integracoes/ide-sisema/feicoes`

## RAG / jurisprudência

O TCU foi integrado ao importador já existente em
`/api/conhecimento/importar-jurisprudencia`. A fonte `tcu` usa o contrato
`JulgadoNormalizado`, entra na deduplicação e no mesmo pipeline de auditoria/RAG
de STJ, TJMG e LexML. A busca on-demand tem teto de cinco páginas de 100
registros para não varrer o acervo inteiro.

## INLABS

O portal INLABS exige fluxo de cadastro/autenticação para obtenção dos pacotes.
Por segurança, esta onda não automatiza login, não registra usuário/senha e não
cria segredo novo. O parser aceita XML/ZIP já obtido por fluxo autorizado, com:

- teto de tamanho compactado e descompactado;
- limite de arquivos;
- bloqueio de path traversal;
- normalização de metadados;
- marca explícita `requer_conferencia_certificada=True`.

O monitor DOU atual via `in.gov.br` permanece intacto como caminho operacional.

## LGPD e governança

- Nenhuma rota nova é pública/anônima.
- Nenhum segredo foi adicionado.
- TSE é usado apenas como catálogo documental público; o EJC não cria perfil
  político, segmentação ou inferência sobre pessoas.
- PGFN é catálogo bulk e não endpoint de consulta individual de CPF/CNPJ.
- Querido Diário é rotulado como agregador secundário.
- SICAR/CAR pago via Infosimples não foi alterado; IBAMA/IDE-Sisema são fontes
  públicas complementares, não substitutos semânticos do CAR.
- Falha de uma fonte externa devolve erro controlado sem stack trace ou corpo do
  upstream para o cliente.

## Testes

`backend/tests/test_integracoes_publicas_onda_836.py` cobre clientes, parsers,
limites, proveniência, allowlists, preservação das URLs BrasilAPI e registro do
TCU no importador RAG. Toda rede é simulada por `httpx.MockTransport`.

## Rollback

Não há migration nem alteração de schema. O rollback é a reversão dos commits
da Issue #836/PR correspondente. As rotas antigas de DataJud/DJEN/BrasilAPI
mantêm seus paths externos e podem ser testadas pela suíte histórica.
