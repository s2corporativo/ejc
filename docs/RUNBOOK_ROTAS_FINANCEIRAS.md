# Runbook — prova das rotas financeiras implantadas

## Objetivo

Comprovar, depois de um deploy humano autorizado, que o runtime corresponde ao
SHA esperado e que as três rotas publicadas chegam ao backend autenticado:

- `GET /api/v1/despesas`
- `GET /api/v1/office-contracts`
- `GET /api/v1/partner-withdrawals`

Este procedimento responde ao P6 da Auditoria Técnica Parte 9. Em 2026-07-29,
produção retornou 404 para as três rotas, embora a `main` as contenha, monte em
`backend/app/main.py` e publique no snapshot OpenAPI.

## Segurança

- Execute primeiro em homologação, com massa fictícia.
- Use token curto de conta dedicada com perfil financeiro autorizado.
- Nunca coloque token, senha ou resposta financeira em Issue, PR, terminal
  compartilhado, arquivo versionado ou log.
- O script envia o token ao `curl` pela entrada padrão e não salva o corpo das
  respostas financeiras.
- Merge, deploy e acesso à produção continuam sendo atos humanos.

## Pré-condições

1. SHA exato da release autorizada.
2. Ambiente já implantado pelo fluxo oficial.
3. Token JWT efêmero de `superadmin`, `admin`, `socio` ou `financeiro`.
4. `curl`, `bash` e `python3` disponíveis na estação do operador.

## Execução

```bash
read -rsp "Token efêmero: " EJC_SMOKE_TOKEN
echo
export EJC_SMOKE_TOKEN
EJC_BASE_URL="https://homolog.example.test" \
EJC_EXPECTED_SHA="<sha-da-release>" \
bash scripts/smoke_rotas_financeiras.sh
unset EJC_SMOKE_TOKEN
```

Repita em produção somente depois da homologação e da autorização do titular.
Use o domínio de produção em `EJC_BASE_URL`; não use `-k` nem desative a
validação TLS.

## Resultado esperado

```text
OK: SHA implantado confere (...)
OK: /api/v1/despesas -> 200
OK: /api/v1/office-contracts -> 200
OK: /api/v1/partner-withdrawals -> 200
OK: smoke das rotas financeiras concluído
```

## Diagnóstico

| Resultado | Interpretação | Próxima ação |
|---|---|---|
| SHA divergente | release/deploy defasado | interromper; reconciliar o artefato implantado |
| 401 | token inválido ou expirado | obter novo token por canal autorizado |
| 403 | perfil sem permissão financeira | usar conta de homologação com papel correto |
| 404 | rota não chegou ao runtime | verificar imagem, proxy e montagem sem alterar produção diretamente |
| 5xx | rota existe, mas falhou no backend/DB | preservar logs sanitizados e abrir incidente específico |

Um 200 só é válido se o SHA também conferir. Isso evita declarar a correção
funcional enquanto outro commit estiver implantado.

## Testes

```bash
bash scripts/tests/test_financial_routes_smoke.sh
pytest -q backend/tests/test_rotas_financeiras_montadas.py
```

O teste shell usa `curl` simulado, não faz chamadas de rede e confirma que o
token não aparece na saída.

## Rollback

Este runbook e o smoke são somente leitura: não alteram dados nem configuração.
Se o smoke falhar, não há rollback de banco; o deploy deve seguir o plano de
rollback da release autorizada.
