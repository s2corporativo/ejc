# EJC — Suíte E2E com Dados Fictícios

Esta pasta contém a suíte de homologação ponta a ponta do EJC com dados exclusivamente fictícios.

## Objetivo

Validar, contra ambiente de homologação/staging, os fluxos principais:

- autenticação e 2FA;
- clientes;
- casos e processos canônicos;
- documentos, OCR e análise documental;
- tarefas, prazos e intimações;
- timeline única e saúde operacional;
- IA e conhecimento;
- financeiro e honorários;
- auditoria e portal;
- mapa de módulos e AutoFix;
- adaptadores de compatibilidade Data Room/Teses v4.

## Proteção contra produção

Por padrão, os runners bloqueiam execução contra URLs que não contenham `staging`, `homolog` ou `localhost`.

Para rodar em produção, somente com autorização explícita:

```bash
EJC_ALLOW_PRODUCTION_E2E=true
```

Mesmo nesse modo, todos os dados criados usam o marcador:

```text
E2E-FICTICIO
```

## Gate recomendado da release

Na raiz do repositório:

```bash
cd backend
pip install -r requirements.txt
cd ..

EJC_BASE_URL="https://homolog.ejc.exemplo" \
EJC_TEST_EMAIL="admin-teste@example.com" \
EJC_TEST_PASSWORD="senha-de-teste" \
python qa/e2e/run_release_acceptance.py
```

O `run_release_acceptance.py` reutiliza integralmente o runner base e acrescenta:

- `GET /cases/{id}/processes`;
- `GET /cases/{id}/timeline`;
- `GET /cases/{id}/operational-health`;
- `GET /dashboard/operational-health`;
- verificação dos adaptadores `/data-room-v4` e `/teses-v4`.

Para executar somente o smoke histórico:

```bash
python qa/e2e/run_fictitious_smoke.py
```

## Saída

O runner imprime cada etapa e grava o relatório em:

```text
qa/e2e/reports/e2e_fictitious_report.json
```

O diretório `reports/` é artefato local de execução, não dado de produção.

## Estratégia

A suíte possui três camadas:

1. `fictitious_matrix.json`: cobertura por módulo, rotas e endpoints;
2. `run_fictitious_smoke.py`: cadastro e smoke funcional base;
3. `run_release_acceptance.py`: gate estrutural da release consolidada.

O teste `backend/tests/test_e2e_fictitious_matrix.py` garante que a matriz acompanha o catálogo do sistema.

## Limites honestos

- Não testa fidelidade visual pixel a pixel.
- Não substitui homologação humana do escritório.
- Não deve ser rodada contra produção sem autorização explícita.
- Não apaga automaticamente os registros fictícios, preservando a auditoria; a limpeza deve buscar `E2E-FICTICIO`.
- Backup, restauração e rollback exigem execução operacional própria e evidência anexada à release.

## Evolução recomendada

Adicionar Playwright para validar navegador real:

- login e configuração obrigatória de 2FA;
- navegação do menu;
- criação manual e por documento;
- upload e revisão da extração;
- abertura da saúde do caso/carteira;
- AutoFix na Central de Diagnóstico;
- bloqueio de cliente externo nas áreas internas.
