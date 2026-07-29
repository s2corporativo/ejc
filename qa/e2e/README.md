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

Variáveis opcionais:

| Variável | Default | Efeito |
|---|---|---|
| `EJC_E2E_STRICT` | `true` | Resposta 404/405/501/503 num passo marca **DEGRADADO** e falha a execução. `false` tolera (ambiente incompleto), mas o relatório continua registrando. |
| `EJC_E2E_CLEANUP` | `true` | Remove (soft-delete) os recursos fictícios criados ao final. `false` preserva para inspeção manual. |

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

### Rigor (auditoria máxima 2026-07-26, achado AI-005)

O runner era um smoke frouxo — POSTs pulados em silêncio, 404/405 contando como
sucesso, nenhuma verificação de efeito. Regras atuais:

- **Assert de efeito**: toda escrita é relida pela API e o conteúdo conferido
  (cliente persistiu o nome? caso ficou vinculado ao cliente? PATCH mudou mesmo
  os campos? movimento apareceu na timeline? documento ficou no caso?). Um `201`
  que não persiste nada deixa de passar.
- **Campo não verificável não é "ok"**: se nenhum campo do PATCH volta na
  releitura, o assert falha — ausência não prova persistência.
- **Degradados**: 404/405/501/503 nunca contam como sucesso; são listados no
  resumo e falham em modo estrito.
- **Cobertura omitida é declarada**: check da matriz não executado entra no
  relatório em `nao_coberto`, com motivo — nunca some num `continue`.
- **Negativas**: requisição sem token deve dar 401 e id inexistente deve dar
  404; um 200 nesses casos é falha.
- **Cleanup idempotente** ao final (desligável por env).

Também existe um teste unitário em `backend/tests/test_e2e_fictitious_matrix.py` que garante que a matriz cobre todos os módulos registrados no `module_registry`.

## O que esta suíte não faz

- Não testa pixel-perfect de UI.
- Não substitui Playwright visual no futuro.
- Não deve ser rodada contra produção sem autorização explícita.
- Não cobre jornada por PAPEL (advogado/estagiário/cliente externo) nem asserts
  diretos no banco — o AI-005 pede ambos; o que existe hoje é a verificação de
  efeito **pela API** e as negativas de autorização acima.

Para inspeção manual, rode com `EJC_E2E_CLEANUP=false`: os dados ficam no
ambiente e podem ser localizados pelo marcador `E2E-FICTICIO`.

## Próxima evolução recomendada

Adicionar Playwright para validar o navegador real:

- login;
- navegação pelo menu;
- criação de cliente/caso;
- upload de documento;
- carregamento da tela `/mapa-modulos`;
- bloqueio de cliente externo acessando áreas internas.
