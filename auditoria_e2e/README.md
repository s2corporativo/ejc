# Bateria de Auditoria E2E do EJC

Suíte idempotente de testes end-to-end para validação pré-deploy do ecossistema EJC, criada em 12/08/2026 durante a auditoria E2E completa do sistema.

## Visão geral

| Item | Valor |
|---|---|
| Cenários | 55 (T01 a T23), cobrindo autenticação/RBAC, CRM, casos, prazos, tarefas, documentos, agenda, triagem, peças, dashboard, DPT360, financeiro, andamentos, notificações, IA/RAG, dossiê, workflow, score jurídico e teardown LGPD |
| Resultado na validação | 51 PASS / 4 FAIL (falhas apenas por ausência de provedor LLM externo — respostas fail-safe corretas: 502/503 com mensagem leiga) |
| Tempo de execução | < 2 minutos contra API local na porta 8000 |
| Isolamento | Todos os dados criados usam o prefixo `TESTE_EJC_AUDITORIA_2026` e são desfeitos no teardown (anonimização LGPD, nunca exclusão física) |

## Execução

Pré-requisitos: backend rodando em `localhost:8000` (PostgreSQL + Alembic migrado + usuário admin), usuário `admin@seu-dominio.com.br`.

```bash
# Executar a bateria:
python3 auditoria_e2e/testes_e2e.py

# Saída: linhas PASS/FAIL por teste; o log completo pode ser gravado em arquivo:
python3 auditoria_e2e/testes_e2e.py > auditoria_e2e/resultados_e2e_$(date +%s).txt 2>&1
```

O script é idempotente: se o cliente/caso de teste já existir, reutiliza-os em vez de criar duplicatas. O teardown usa o fluxo LGPD correto — encerramento de caso via pós-mortem (`POST /cases/{id}/encerrar`) e direito ao esquecimento por anonimização (`POST /clients/{id}/esquecimento`); exclusão física é deliberadamente não utilizada por restrição legal.

## Interpretação dos resultados

| Situação | Interpretação |
|---|---|
| 51/55+ PASS, 4 FAIL de IA | Normal sem provedor LLM configurado (chat, pesquisar, resumir, pré-preenchimento) |
| 55/55 PASS | Todos os provedores de IA ativos e funcionais |
| Falhas em T01/T04/T05 | Problema de infra/autenticação — revisar boot, DB e migrations |
| Falhas em T19/T23 | Regressão em LGPD — investigar antes de qualquer deploy |

## Conteúdo do diretório

- `testes_e2e.py` — suíte completa (única dependência: `requests`).
- `run_audit.sh` — sobe o uvicorn local e executa a bateria.
- `resultados_e2e_v45.txt` — log da execução de validação final (51 PASS / 4 FAIL).
