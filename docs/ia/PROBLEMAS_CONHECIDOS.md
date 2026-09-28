# Problemas conhecidos - EJC

Este arquivo registra apenas problemas comprovados por código, teste, log sanitizado, issue, PR ou ambiente controlado. Não registre hipóteses soltas, dados reais de clientes, documentos jurídicos, tokens, senhas ou informações processuais sigilosas.

## Como usar

Antes de iniciar uma correção, consulte este arquivo para evitar retrabalho e para identificar regressões. Ao confirmar um problema novo, registre a evidência antes de alterar código. Ao resolver, mantenha o histórico resumido.

## Classificação

- `crítico`: interrompe operação essencial, expõe dado jurídico, causa perda de dados, quebra autorização ou indisponibilidade.
- `alto`: afeta processo importante, RBAC, documentos, financeiro, IA jurídica, prazos ou integridade de dados.
- `médio`: afeta uso normal com contorno viável.
- `baixo`: falha localizada, cosmética ou melhoria técnica sem impacto operacional imediato.

## Status permitidos

- `identificado`
- `em investigação`
- `correção preparada`
- `aguardando validação`
- `resolvido`
- `monitoramento`
- `aceito temporariamente`

## Problemas ativos

### EJC-IA-CONVERGENCIA — integração Manus separada do núcleo

- Status: identificado; severidade: alto para promoção de supervisão automática.
- Base de diagnóstico: `7cc95b097bbb1d47b71c4116b4b9e3977a2a223b`; referência #1651.
- Estado atual: **PARCIAL**. Existe integração Manus explícita, mas não supervisor
  governado pelo núcleo/Tool Broker.
- Evidência: `manus_deep_reasoning.iniciar_raciocinio` chama
  `ManusClient.create_task`; não passa pelo `SingleAICoreOrchestrator`.
- Guardas próprias, pseudonimização e bloqueio de roteamento automático existem;
  este registro não afirma vazamento, autonomia segura ou execução externa indevida.
- O cliente atual envia `connectors=[]`, `enable_skills=[]` e
  `force_skills=[]`; isso reduz o escopo da chamada atual, mas não certifica
  isolamento de uma futura supervisão com ferramentas.
- O shadow em `legal_brain/shadow.py` anexa diagnóstico ao resultado do núcleo:
  não é shadow A/B isolado.
- `ai/agent/budget.py` acumula passos/tokens/custo após turnos: não é reserva
  transacional universal antes das chamadas.
- Pendências bloqueantes para autonomia: hardening #1726, fontes #1728, curadoria
  humana #1201, Tool Broker, estados persistentes e orçamento prévio.

#### Condição verificável para encerramento

Este problema só pode passar a `resolvido` quando TODOS os itens abaixo tiverem
evidência vinculada ao SHA:

- [ ] `MANUS-01`: plano Manus não executa ferramenta diretamente; toda execução
      passa pelo broker autorizado.
- [ ] `TB-01`: chamada sem RBAC/ownership falha antes de produzir side effect.
- [ ] `TB-02`: retomada revalida autorização.
- [ ] `STATE-01`: transições persistentes são registradas com versão de
      plano/policy e motivo resumido.
- [ ] `STATE-02`: retry com mesma chave de idempotência não duplica efeito.
- [ ] `COST-01`: orçamento é reservado antes do dispatch, inclusive retries e
      chamadas auxiliares.
- [ ] `SEC-01`: fluxo classificado como local não despacha conteúdo a provider
      ou supervisor externo.
- [ ] `SHADOW-01`: shadow não altera caso, prazo, peça ou financeiro.
- [ ] `HITL-01`: produção jurídica não é promovida sem revisão humana.
- [ ] #1726 e #1728 cumprem seus critérios próprios, sem bypass.
- [ ] #1201 atinge o gold set humano real exigido pela issue canônica.
- [ ] rollback/runbook foi executado e comprova tratamento das execuções pendentes.

Uma flag, classe, arquivo, template ou documentação não satisfaz nenhum desses
itens isoladamente. `MANUS_AUTO_ROUTING_ENABLED=true` não é mecanismo de promoção.

- Rollback do lote documental #1868: revert dos arquivos de documentação;
  nenhuma alteração de runtime, schema, filas ou produção.


## Modelo de registro

```md
### EJC-000 - Título objetivo

## Identificação

- Código: EJC-000
- Sistema: EJC
- Módulo:
- Ambiente:
- Severidade:
- Status:
- Data da identificação:
- Commit ou PR relacionado:

## Evidência

- Sintoma:
- Forma de reprodução:
- Logs relevantes, sem secrets ou PII:
- Arquivos relacionados:
- Testes que demonstram a falha:

## Análise

- Causa confirmada ou hipótese:
- Impacto:
- Risco de regressão:
- Dependências:
- Soluções já tentadas:
- Motivo de tentativa malsucedida:

## Tratamento

- Correção adotada:
- Validações:
- Rollback:
- Pendências:
- Condição para encerramento:
```

## Histórico resumido

Sem problemas encerrados registrados neste arquivo ainda.
