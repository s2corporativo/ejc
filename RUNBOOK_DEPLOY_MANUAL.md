# Deploy do EJC sem GitHub Actions

**Por que este runbook existe.** Em 2026-08-22T07:41Z a cota de Actions da conta
se esgotou e **nenhum workflow do repositório passou a executar**. Em
2026-08-23T11:51Z um `workflow_dispatch` do `deploy-vps.yml` na `main` terminou
em **1 segundo** com `startup_failure` e `jobs: []` — o critério canônico do
repositório para *infraestrutura, não sucesso*. Nenhum runner foi alocado.

**A conclusão que isso derruba:** achava-se que migrar jobs para o runner
self-hosted `ejc-vps` contornaria a cota, porque minuto self-hosted não é
cobrado. **Não contorna.** O `deploy-vps.yml` já roda em
`runs-on: [self-hosted, ejc-vps]`, está `active`, foi disparado na `main` — e
falhou no startup do mesmo jeito. O bloqueio é **no nível da conta, antes da
alocação do runner**, e não distingue hosted de self-hosted.

**O que continua possível.** O deploy nunca dependeu tecnicamente do Actions: o
runner está instalado DENTRO da VPS e toda a lógica mora em scripts deste
repositório. O Actions é o gatilho, não o mecanismo.

---

## O comando

Na VPS, com um usuário que tenha `sudo -n` e acesso ao socket do Docker:

```bash
cd /caminho/do/checkout            # NÃO use /opt/ejc: é o destino, não a origem
git fetch origin main
git checkout <SHA>                 # o SHA já integrado à main

bash scripts/deploy_manual.sh --sha <SHA> --dry-run   # confere, não muta
bash scripts/deploy_manual.sh --sha <SHA>             # implanta
```

**Rode sempre o `--dry-run` primeiro.** Ele executa o pré-voo e a classificação
de migration e para antes de qualquer mutação — é assim que se descobre, sem
risco, se a migration pendente é expand-only e se o runtime está sadio.

`--run-seeds` reingere o corpus RAG depois do deploy (equivale ao input
`run_seeds` do workflow). O default é **não** reingerir: a esteira automática
sempre reingere, mas fazer isso à mão mexe na base de conhecimento e merece
decisão explícita.

## O que o script preserva — e por que isso importa

`scripts/deploy_manual.sh` **não é um atalho**: ele porta para fora do YAML os
dois passos que só existiam lá dentro, e mantém todas as travas.

| Trava | Onde está | O que acontece sem ela |
|---|---|---|
| Pré-voo (workspace, `/opt/ejc`, `ejc_db`, `sudo -n`) | script | deploy começa e falha no meio, com produção já tocada |
| Revisão Alembic única em produção | script | classificação de migration em cima de estado ambíguo |
| `check_migration_compatibility.py` (expand-only) | script | migration destrutiva entra sem ninguém decidir |
| `RUN_MIGRATIONS` derivado da classificação | script | **default 0** → código novo contra schema antigo, em silêncio |
| Mutex host-level (`deploy_workflow_transaction.sh`) | script | deploy manual e automático se intercalam |
| Backup pré-deploy obrigatório | `deploy_vps_safe.sh` | sem ponto de retorno |
| Health-poll e rollback automático | `deploy_vps_safe.sh` | versão quebrada permanece no ar |
| Idempotência por SHA | script | retrabalho e troca desnecessária de container |

> **A armadilha que motivou o script.** Rodar `scripts/deploy_vps_safe.sh`
> direto *parece* funcionar: ele tem backup, health e rollback. Mas
> `RUN_MIGRATIONS` tem default `0`, e o passo que o liga vivia no YAML. O
> resultado é um deploy "bem-sucedido" com o schema desatualizado — sem erro,
> sem alerta. **Nunca chame `deploy_vps_safe.sh` diretamente.**

`backend/tests/test_deploy_manual_paridade.py` trava essa paridade: se o
workflow ganhar uma trava nova e o caminho manual não, o teste reprova.

## Limitação declarada

O script foi validado por sintaxe, lint e testes — **incluindo a execução real
dos caminhos de recusa** (sem `--sha`, SHA divergente do checkout, ausência de
`/opt/ejc`). O caminho de sucesso **não foi exercido contra a VPS**, porque
fazê-lo exigiria tocar produção. Trate o primeiro uso como tal: `--dry-run`
antes, e alguém acompanhando a saída.

## Quando NÃO usar

- **Para pular revisão.** O SHA implantado tem de estar integrado à `main`.
- **Quando o Actions estiver funcionando.** A esteira automática é a via
  canônica (governança §9); este caminho existe para quando ela não aloca runner.

## Como saber que a esteira voltou

```
mcp__github__actions_list  → list_workflow_runs (deploy-vps.yml)
```
Run com `conclusion: startup_failure` e `jobs: []` = infraestrutura, não falha
do código. Enquanto for esse o resultado, a cota segue esgotada.
