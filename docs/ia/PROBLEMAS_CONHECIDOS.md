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
- Base: `7cc95b097bbb1d47b71c4116b4b9e3977a2a223b`; referência #1651.
- Evidência: `manus_deep_reasoning.iniciar_raciocinio` chama
  `ManusClient.create_task`; não passa pelo `SingleAICoreOrchestrator`.
- Guardas próprias, pseudonimização e bloqueio de roteamento automático existem;
  este registro não afirma vazamento ou execução externa indevida.
- Tratamento: arquitetura canônica atualizada; preservar uso explícito atual e
  consolidar contrato, auditoria, orçamento e ferramentas antes de supervisão.
- Pendências: hardening #1726, fontes #1728 e curadoria humana #1201.
- O shadow em `legal_brain/shadow.py` anexa diagnóstico ao núcleo: não certifica
  shadow A/B isolado. O orçamento do agente é acumulado após turnos: não prova
  reserva financeira universal antes das chamadas.
- Aceite: convergência testada, sigilo transversal, limites e comparação humana;
  sem ativação por simples mudança de `MANUS_AUTO_ROUTING_ENABLED`.
- Rollback deste lote: revert documental; nenhuma alteração de runtime.


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
