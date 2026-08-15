# ADR — NFSE_ENABLED permanece desabilitado (regime Simples Nacional)

**Status:** Decidido (aguardando desbloqueio externo) · **Data:** 15/08/2026
**Decisores:** Dr. Clovis (titular) e contador externo
**Documentos relacionados:** `docs/NFSE_VIABILIDADE.md` (levantamento de 12/07/2026)

## Contexto

O EJC possui um módulo de emissão de NFS-e no backend controlado pelo flag de
ambiente `NFSE_ENABLED` (padrão `false` por projeto, conforme
`docs/NFSE_VIABILIDADE.md`). Em 15/08/2026, durante a revisão das pendências
administrativas da onda de estabilização, o titular confirmou que o escritório
opra pelo **Simples Nacional**.

A dúvida a esclarecer era se o flag poderia ser habilitado em produção como
parte da estabilização ou se deveria permanecer desabilitado até validação
fiscal externa.

## Alternativas consideradas

| # | Alternativa | Avaliação |
|---|---|---|
| A | Habilitar `NFSE_ENABLED=true` em produção imediatamente | Rejeitada — emitiria risco fiscal sem validação do contador e sem pré-requisitos (certificado e-CNPJ A1, parametrização no Emissor Nacional, definição de alíquota/ISS). |
| B | Manter `NFSE_ENABLED=false` por padrão até confirmação do contador | Escolhida — zero exposição fiscal; o módulo continua disponível para homologação futura sem retrabalho. |
| C | Habilitar apenas `NFSE_MODO=homologacao` em ambiente de testes | Não necessária agora — o flag existe apenas em `.env` local e a homologação só faz sentido após a conclusão dos itens 1–3 do pré-requisito fiscal. |

## Decisão

`NFSE_ENABLED` **permanece `false`** em todos os ambientes. Qualquer alteração
do flag em produção exige, nesta ordem: (1) confirmação do contador sobre o
enquadramento de serviços advocatícios no Simples Nacional em Betim/MG (alíquota
de ISS, existência de regime fixo/SUP que altera a base de cálculo da DPS e item
LC 116/03 17.14); (2) entrega do certificado digital e-CNPJ ICP-Brasil tipo A1
e primeiro acesso no Emissor Nacional; (3) escolha do provedor (Nuvem Fiscal,
eNotas ou similar) e chave de API. Só então o fluxo homologação → nota de teste
conferida com o contador → produção poderá ser iniciado.

## Justificativa técnica

1. **Regime tributário**: no Simples Nacional, o ISS dos serviços é recolhido
   integralmente pela guia DAS mensal. A emissão da NFS-e (padrão nacional,
   Sefin — Decreto Municipal 51.670 de Betim) é obrigação declarativa acessória
   vinculada ao prestador, não geradora de nova obrigação principal — mas o
   preenchimento da DPS (alíquota, base, item de serviço) depende exatamente
   dos parâmetros que o contador precisa validar.
2. **Risco de erro fiscal**: parametrização incorreta da DPS (alíquota errada,
   base de cálculo indevida, item LC 116/03 incorreto) gera notas fiscalmente
   inválidas, passíveis de exigência da prefeitura e de retrabalho de
   cancelamento/emissão. O custo do erro supera o benefício de antecipar o
   flag.
3. **Arquitetura preservada**: a interface de provedor abstrata (`NFSeProvider`)
   e os adapters já documentados em `NFSE_VIABILIDADE.md` não dependem do flag;
   quando os pré-requisitos existirem, a ativação é puramente operacional
   (`.env` da VPS + certificado), sem alteração de código.

## Consequências

- O flag `NFSE_ENABLED` deve constar como `false` no `.env` de produção e não
  deve ser exposto em README, PR ou log.
- Nenhum deploy ou merge deve alterar esse default.
- A tela do módulo Financeiro (emitir NFS-e a partir de honorário/recebível)
  permanece desativada por role/config sem impacto funcional.
- O item fica registrado como pendência administrativa no roadmap (fora de
  código): "NFSE_ENABLED — aguardando confirmação de regime/alíquota com o
  contador; certificado e-CNPJ A1; escolha de provedor".

## Rastreabilidade

- Levantamento de viabilidade: `docs/NFSE_VIABILIDADE.md` (12/07/2026)
- Confirmação do regime pelo titular: sessão Manus 15/08/2026
- Decisão registrada neste ADR: 15/08/2026
