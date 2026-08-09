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

## Feature flags e ativação segura

Integração externa nova nasce **default OFF**. O contrato está centralizado em
`integrations/feature_flags.py`; o cliente verifica a flag antes de abrir conexão
externa. A referência operacional está em
`docs/INTEGRACOES_PUBLICAS_ONDA_836.env.example`.

| Fonte | Flag |
|---|---|
| CNJ SGT/TPU | `CNJ_SGT_ENABLED` |
| TCU | `TCU_OPEN_DATA_ENABLED` |
| IBGE | `IBGE_LOCALIDADES_ENABLED` |
| IBAMA | `IBAMA_OPEN_DATA_ENABLED` |
| Consumidor.gov/SENACON | `CONSUMIDOR_GOV_OPEN_DATA_ENABLED` |
| CVM | `CVM_OPEN_DATA_ENABLED` |
| TSE | `TSE_OPEN_DATA_ENABLED` |
| PGFN | `PGFN_OPEN_DATA_ENABLED` |
| Querido Diário | `QUERIDO_DIARIO_ENABLED` |
| IDE-Sisema | `IDE_SISEMA_ENABLED` |

Ativação recomendada: **uma fonte por vez**, smoke real na VPS e observação de
latência/erros. Se uma fonte apresentar quebra de contrato, indisponibilidade ou
questão de termos de uso, `FLAG=false` é o rollback imediato antes de qualquer
reversão de código.

### TCU e `.env` legado

O deploy preserva `.env` existente e ambientes antigos podem manter
`JURIS_IMPORT_FONTES=lexml,stj`. Por isso a Onda #836 não exige reescrever esse
CSV: quando `TCU_OPEN_DATA_ENABLED=true`, `tcu` é adicionado logicamente às
fontes ativas. Quando a flag volta a `false`, `tcu` é removido mesmo que alguém
o tenha incluído no CSV. Isso preserva configuração antiga e o kill-switch.

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

## RAG / jurisprudência — TCU

O TCU foi integrado ao importador já existente em
`/api/conhecimento/importar-jurisprudencia`. A fonte `tcu` usa o contrato
`JulgadoNormalizado`, entra na deduplicação e no mesmo pipeline de auditoria/RAG
de STJ, TJMG e LexML. A busca on-demand tem teto de cinco páginas de 100
registros para não varrer o acervo inteiro.

Dois requisitos de rastreabilidade são explícitos:

1. o identificador citável preserva a chave completa do TCU (por exemplo,
   `AC-123-2026-P`) em vez do número simples que se repete entre anos/colegiados;
2. indisponibilidade da API é propagada ao job e registrada como erro, nunca
   convertida em falso “sucesso com zero resultados”.

## INLABS

O portal INLABS exige fluxo de cadastro/autenticação para obtenção dos pacotes.
Por segurança, esta onda não automatiza login, não registra usuário/senha e não
cria segredo novo. O parser aceita XML/ZIP já obtido por fluxo autorizado, com:

- teto de tamanho compactado e descompactado;
- limite de arquivos;
- bloqueio de path traversal;
- normalização de metadados do schema real (`identifica`, `pubName`, `artType`,
  `name` como identificador interno);
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
- Flags default OFF oferecem rollback por fonte sem alteração de código.

## Testes

`backend/tests/test_integracoes_publicas_onda_836.py` cobre clientes, parsers,
limites, proveniência, allowlists, feature flags default OFF, configuração TCU
com `.env` legado, propagação de indisponibilidade TCU, identificação citável,
schema real INLABS, preservação das URLs BrasilAPI e registro do TCU no
importador RAG. Toda rede é simulada por `httpx.MockTransport`.

## Rollback

Primeiro nível: desligar somente a flag da fonte afetada e reiniciar o serviço
que carrega o `.env`, conforme o procedimento operacional padrão do EJC.

Segundo nível: reverter o PR da Issue #836. Não há migration nem alteração de
schema. As rotas antigas de DataJud/DJEN/BrasilAPI mantêm seus paths externos e
continuam cobertas pela suíte histórica.
