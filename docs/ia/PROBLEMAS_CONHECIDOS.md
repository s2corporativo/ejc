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

Nenhum problema comprovado registrado neste arquivo ainda.

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
