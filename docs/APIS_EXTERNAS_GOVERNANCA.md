# Governança das APIs externas do EJC

Atualizado em 18/07/2026. Este documento registra o que pode ser ativado no
EJC, o modo de autenticação e o que **não** deve ser implementado sem
credenciamento. A regra é uma política por fonte; não existe um cliente de
autenticação universal.

## Matriz de decisão

| Fonte | Acesso | Decisão no EJC |
|---|---|---|
| DataJud/CNJ | Header `Authorization: APIKey ...`; chave pública rotativa divulgada pelo CNJ | Integrado. Opt-in por `DATAJUD_ENABLED` e `DATAJUD_API_KEY`. A chave fica somente no ambiente e nunca no Git. |
| PNCP — consultas | Público, anônimo | Integrado e ligado por padrão. Somente leitura, com cache, rate limit, timeout e retries transitórios. |
| PNCP — manutenção | JWT para plataformas de órgãos públicos credenciadas | Fora de escopo. O EJC não publica, altera ou exclui dados no PNCP. |
| BrasilAPI/OpenCNPJ/ViaCEP | Público, anônimo | Integrado para CEP, CNPJ e feriados. As rotas exigem usuário autenticado e têm rate limit. |
| ReceitaWS pública | Anônima, com limite divulgado pelo fornecedor | Último fallback de CNPJ. Não é tratada como fonte oficial nem como ilimitada. |
| ReceitaWS comercial | Token e plano contratado | Não ativar sem contrato, credencial e teto de custo aprovados. |
| Conecta gov.br | Adesão institucional e OAuth2; destinado a órgãos públicos | Não elegível para o escritório privado. Não criar campos `client_secret` sem uma mudança formal de elegibilidade. |
| Jusbrasil API | Contrato comercial e API key | Não integrado. Implementar somente após contrato, escopo, preço, retenção e licença de uso dos dados. |
| Webservices próprios de tribunais | Credenciamento específico por tribunal | Não existe adaptador genérico. Preferir DataJud para metadados; criar conector individual apenas após documentação e credencial válidas. |
| IBAMA Dados Abertos | Datasets/CKAN públicos | Tratar como ingestão em lote versionada, não como consulta unitária por CNPJ/processo. Incremento separado para o módulo ambiental. |
| DOU — consulta | Portal público | O monitor existente é best-effort e somente leitura. Não confundir com o WS-INCom. |
| WS-INCom/DOU | Autorização restrita para publicação por órgãos | Fora de escopo para consulta do EJC. |

## Controles aplicados

- URLs-base são configurações de servidor; entradas do usuário viram somente
  filtros validados, reduzindo risco de SSRF.
- Segredos ficam em variáveis de ambiente. Status de integração retorna apenas
  booleanos e o modo de acesso.
- DataJud e PNCP repetem somente falhas de transporte, HTTP 429 e HTTP 5xx.
  Erros 4xx de contrato ou credencial não são multiplicados.
- Logs não contêm API key, corpo de resposta, número CNJ, CNPJ ou CEP.
- PNCP interpreta HTTP 204 como resultado vazio, sem tentar decodificar JSON.
- DataJud distingue processo ausente de flag/chave ausente e indisponibilidade
  da fonte; esses estados não podem virar falso HTTP 404.
- Consultas de CEP/CNPJ exigem autenticação do EJC e possuem rate limit por
  usuário. A resposta identifica a fonte utilizada no fallback.
- Nenhum resultado externo entra automaticamente no RAG como aprovado. Fontes
  documentais seguem ingestão, versionamento, proveniência e curadoria humana.

## Configuração operacional

### DataJud

```env
DATAJUD_ENABLED=true
DATAJUD_API_KEY=<chave pública vigente obtida na Wiki do CNJ>
DATAJUD_BASE_URL=https://api-publica.datajud.cnj.jus.br
DATAJUD_TIMEOUT_SECONDS=25
```

A chave pode ser alterada pelo CNJ. HTTP 401/403 deve gerar alerta operacional
para atualização no ambiente, sem commit de código.

### PNCP consulta

```env
PNCP_ENABLED=true
PNCP_BASE_URL=https://pncp.gov.br/api/consulta/v1
PNCP_TIMEOUT_SECONDS=25
```

Não configurar login/JWT do PNCP no EJC: essas credenciais pertencem ao fluxo
de manutenção de plataformas públicas, que não é necessário para pesquisar
contratações.

## Fontes oficiais consultadas

- DataJud — acesso: https://datajud-wiki.cnj.jus.br/api-publica/acesso/
- DataJud — endpoints: https://datajud-wiki.cnj.jus.br/api-publica/endpoints/
- PNCP — Swagger de consulta: https://pncp.gov.br/api/consulta/swagger-ui/index.html
- PNCP — manual de integração: https://pncp.gov.br/manual/pt-br/latest/singlehtml/
- Conecta gov.br: https://www.gov.br/governodigital/pt-br/infraestrutura-nacional-de-dados/interoperabilidade/conecta-gov.br/conecta-gov-br
- ReceitaWS: https://developers.receitaws.com.br/
- Jusbrasil API: https://api.jusbrasil.com.br/docs/introducao/como_contratar.html
- IBAMA Dados Abertos: https://dadosabertos.ibama.gov.br/
- DOU — consulta pública: https://www.gov.br/pt-br/servicos/acessar-o-diario-oficial-da-uniao
- WS-INCom: https://www.gov.br/conecta/catalogo/apis/publicar-no-dou
