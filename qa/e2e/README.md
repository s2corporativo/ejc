# EJC — Suíte E2E com Dados Fictícios

Esta pasta contém uma suíte de homologação para testar o EJC ponta a ponta com dados fictícios.

## Objetivo

Validar, contra um ambiente de homologação/staging, os fluxos principais do sistema:

- autenticação;
- clientes;
- casos/processos;
- documentos e OCR;
- análise documental automática;
- tarefas/prazos/intimações;
- IA e conhecimento;
- financeiro/honorários;
- auditoria;
- portal;
- mapa de módulos;
- diagnóstico/AutoFix.

## Proteção contra produção

Por padrão, o runner bloqueia execução contra URLs que não contenham `staging`, `homolog` ou `localhost`.

Para rodar em produção, somente com autorização explícita, defina:

```bash
EJC_ALLOW_PRODUCTION_E2E=true
```

Mesmo assim, todos os dados criados usam o marcador:

```text
E2E-FICTICIO
```

## Como rodar

Na raiz do repositório:

```bash
cd backend
pip install -r requirements.txt
cd ..

EJC_BASE_URL="https://homolog.ejc.exemplo" \
EJC_TEST_EMAIL="admin-teste@example.com" \
EJC_TEST_PASSWORD="senha-de-teste" \
python qa/e2e/run_fictitious_smoke.py
```

## Saída

O runner imprime cada etapa e grava o relatório em:

```text
qa/e2e/reports/e2e_fictitious_report.json
```

O diretório `reports/` deve ser tratado como artefato local de execução, não como dado de produção.

## Estratégia dos testes

A suíte possui duas camadas:

1. `fictitious_matrix.json`: matriz de cobertura por módulo, com rotas frontend, endpoints API e dados fictícios.
2. `run_fictitious_smoke.py`: runner HTTP que autentica, cria dados fictícios e executa smoke tests por módulo.

Também existe um teste unitário em `backend/tests/test_e2e_fictitious_matrix.py` que garante que a matriz cobre todos os módulos registrados no `module_registry`.

## O que esta suíte não faz

- Não testa pixel-perfect de UI.
- Não substitui Playwright visual no futuro.
- Não deve ser rodada contra produção sem autorização explícita.
- Não remove automaticamente dados fictícios, para preservar rastreabilidade de auditoria. A limpeza deve buscar o marcador `E2E-FICTICIO`.

## Próxima evolução recomendada

Adicionar Playwright para validar o navegador real:

- login;
- navegação pelo menu;
- criação de cliente/caso;
- upload de documento;
- carregamento da tela `/mapa-modulos`;
- bloqueio de cliente externo acessando áreas internas.
