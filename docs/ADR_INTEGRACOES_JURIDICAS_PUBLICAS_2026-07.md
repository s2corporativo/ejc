# ADR — integrações jurídicas públicas brasileiras

**Status:** aprovado para execução incremental  
**Data:** 18/07/2026  
**Escopo:** DataJud, PNCP, PJe, eproc, cadastros, IBAMA e DOU

## Contexto verificado

O EJC já possui conectores para DataJud, PNCP, CEP/CNPJ e monitoramento do
Diário Oficial. Criar novos conectores com o mesmo objetivo aumentaria custo e
divergência. A decisão é consolidar os existentes e só criar adaptadores onde
há lacuna comprovada.

Fontes oficiais consultadas:

- DataJud/CNJ: <https://datajud-wiki.cnj.jus.br/api-publica/>;
- PNCP: <https://pncp.gov.br/api/consulta/swagger-ui/index.html>;
- MNI/integração judiciária: <https://www.cnj.jus.br/integracao-para-os-tribunais/>;
- eproc/TJMG: <https://www.tjmg.jus.br/portal-tjmg/processos/eproc/eproc.htm>;
- CNPJ/Conecta gov.br: <https://www.gov.br/conecta/catalogo/apis/consulta-cnpj>;
- DOU: <https://www.gov.br/pt-br/servicos/acessar-o-diario-oficial-da-uniao>;
- API de publicação no DOU: <https://www.gov.br/conecta/catalogo/apis/publicar-no-dou>;
- dados abertos do IBAMA: <https://dadosabertos.ibama.gov.br/>.

## Decisão por fonte

| Fonte | Estado no EJC | Decisão |
|---|---|---|
| DataJud/CNJ | Conector, sincronização, retry, deduplicação e prazos HITL já implementados | Ativar após smoke test na VPS, usando chave em segredo de ambiente. Manter como fonte pública nacional de capa e movimentos. |
| PNCP | Conector com cache já implementado, mas ainda contém TODO sobre parâmetros do contrato | Validar contra o Swagger atual e só então ativar. Não criar segundo conector. |
| BrasilAPI/OpenCNPJ/ViaCEP/ReceitaWS | Cadeia de fallback já implementada | Manter. Exibir fonte e instante da consulta; não tratar serviço de terceiro como dado oficial da Receita Federal. |
| Conecta gov.br — CPF/CNPJ | Credenciamento voltado à administração pública | Não depender desta API para o escritório privado sem aprovação formal do provedor. |
| PJe | Não há conector próprio nem API REST pública nacional para escritório | Usar DataJud e DJEN para dados públicos. Integração transacional somente por interface oficial/MNI e credenciamento do tribunal. |
| eproc | Não há conector; TJMG disponibiliza consulta pública por portal e está migrando do PJe | Criar futuramente um adaptador MNI/eproc apenas após credenciamento escrito e documentação do tribunal. Não automatizar login, 2FA, certificado ou consulta HTML. |
| IBAMA | Sem conector operacional; fonte principal é catálogo/dados em lote | Implementar ingestor de dados abertos por dataset, com versão, hash, data de captura e atualização idempotente. Não modelar como consulta unitária em tempo real. |
| SICAFI | Portal sem API pública documentada | Manter fluxo manual de certidão e anexação ao caso. |
| DOU | Serviço atual chama o endpoint interno da busca pública do portal | Reclassificar como integração não documentada e best-effort. Para ingestão confiável, priorizar INLABS/XML mediante cadastro. A API WS-INCom é de publicação, não de consulta. |
| Jusbrasil/agregadores | Sem necessidade para o núcleo gratuito | Opcional e contratual, com avaliação de custo, licença, DPA, retenção e rastreabilidade da fonte. |

## Arquitetura escolhida para PJe e eproc

PJe e eproc não serão acoplados diretamente aos casos. Ambos deverão
implementar uma porta comum, mantendo o DataJud como adaptador padrão:

```text
ProcessSourceAdapter
  consultar_processo(numero_cnj)
  sincronizar_movimentos(numero_cnj, cursor)
  consultar_documento(chave)          # somente se o convênio permitir
  status()

Adaptadores: DataJudAdapter | PjeMniAdapter | EprocMniAdapter
```

Cada adaptador ficará atrás de feature flag própria. Credenciais, certificados
e chaves ficam exclusivamente no cofre/ambiente da VPS. O frontend chama apenas
rotas internas do EJC e nunca recebe segredo do tribunal.

## Integridade, segurança e LGPD

- validar acesso ao caso antes de qualquer consulta ou sincronização;
- armazenar somente dados necessários ao serviço jurídico contratado;
- registrar fonte, identificador externo, instante de captura e hash;
- deduplicar por `fonte + processo + evento externo`;
- não registrar chaves, certificados, CPF/CNPJ completo ou respostas integrais;
- aplicar timeout, retry exponencial, circuit breaker e limite por fonte;
- processos sigilosos não podem ser enriquecidos por fonte pública;
- prazo inferido de movimento externo permanece rascunho até confirmação humana;
- scraping só poderá ser adotado após análise específica de termos, robots,
  estabilidade e base jurídica, nunca para contornar autenticação ou 2FA.

## Fases de implantação

1. **Ativação segura:** smoke tests de DataJud e PNCP na VPS, métricas de
   latência/erro, sem alterar o fluxo principal.
2. **Fontes em lote:** ingestor IBAMA com catálogo de datasets, proveniência e
   atualização idempotente.
3. **PJe/eproc:** obter documentação e autorização de um tribunal piloto;
   implementar primeiro consulta e movimentos em modo somente leitura.
4. **Transações:** peticionamento, ciência e download integral ficam fora do
   escopo até auditoria de certificado, mandato, responsabilidade e trilha de
   auditoria.

## Critérios de aceite

- testes de contrato com respostas gravadas e sanitizadas;
- teste real controlado na VPS para cada fonte ativada;
- degradação sem interromper cadastro, caso, prazo ou documento;
- nenhuma credencial em código, log ou resposta;
- métricas por fonte: disponibilidade, latência, erros, cache e rate limit;
- rollback imediato por feature flag;
- revisão jurídica dos termos de uso antes de qualquer integração credenciada
  ou comercial.

## Consequências

A solução evita conectores duplicados e scraping frágil, preserva o EJC quando
uma fonte externa cai e permite acrescentar PJe/eproc por tribunal sem alterar o
núcleo de casos. Em contrapartida, consultas transacionais de PJe/eproc dependem
de credenciamento externo e não podem ser prometidas como API pública imediata.
