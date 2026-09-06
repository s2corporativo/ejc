# Runbook — Correção do Runner e Reacionamento do Deploy VPS

**Data:** 14/08/2026 · **Contexto:** workflows `Deploy VPS` (runs 31789005972, 31789004408, 31789219182) falharam com `startup_failure`; run 31616823786 estava travado em fila por 41h (cancelado).

## Causa raiz

O agente self-hosted do GitHub Actions na VPS não consegue gravar em `/opt/actions-runner/_work/_actions/actions/checkout/v7/` (erro "Access to the path ... is denied"). O runner está online, mas o usuário do serviço perdeu permissão de escrita na pasta de trabalho — típico de troca de owner de `/opt/actions-runner` ou reinstalação/upgrade do agente sob usuário diferente.

## Correção na VPS (requer sudo/SSH no servidor)

```bash
# 1. Identificar o usuário do serviço do runner
systemctl list-units --all | grep -i actions
cat /etc/systemd/system/actions.runner.s2corporativo-ejc*.service 2>/dev/null | grep -E "User=|ExecStart"

# 2. Corrigir o owner recursivo para o usuário do serviço (ex.: usuario)
sudo chown -R usuario:usuario /opt/actions-runner

# 3. Reiniciar o serviço do runner
sudo systemctl restart actions.runner.s2corporativo-ejc.service   # nome real conforme passo 1

# 4. Confirmar no GitHub que o runner voltou a aceitar jobs
#    Settings → Actions → Runners: "ejc-vps" deve mostrar "Idle"
```

## Depois da correção (executar o Manus)

1. Cancelar/eventualmente limpar runs falhos: nada pendente — os 3 runs de hoje já estão concluídos e o run antigo foi cancelado.
2. Reacionar o deploy: `gh workflow run deploy-vps.yml` (executado da sessão Manus).
3. Após deploy concluído com sucesso: mesclar a PR #1139 (`gh pr merge 1139 --merge`), reacionar o deploy novamente (agora com os scripts de ingestão/monitor na VPS).
4. Rodar na VPS:
```bash
nohup python3 backend/scripts/monitor_ingestao.py > /tmp/monitor_ingestao.log 2>&1 &
python3 backend/scripts/ingestao_biblioteca_juridica.py --execute
```
5. Verificar: contagem em `knowledge_docs` (SQL no guia `GUIA_EXECUCAO_PRODUCAO.md`, seção 4) e logs do container `db` (seção 4.2).

## Estado atual do plano

| Item | Status |
|---|---|
| PR #1139 (lote piloto + guia + monitor) | Aberta, aprovada, aguardando merge |
| Workflow Deploy VPS | Bloqueado por permissões no runner (correção pendente na VPS) |
| Run em fila 41h | Cancelado |
| Ingestão real dos 24 temas | Pronta para execução (dry-run validado sem erros) |
