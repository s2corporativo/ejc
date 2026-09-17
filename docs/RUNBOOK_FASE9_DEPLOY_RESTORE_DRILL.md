# Fase 9 — Runbook de Deploy + Restore Drill (Plano Mestre)

> **Status: NÃO EXECUTADO.** Este runbook só entra em execução com **janela
> agendada** e **go explícito do Titular** (mensagem direta na issue da Fase 9 /
> #1572). Nenhuma etapa abaixo é automatizada por CI; todas são manuais na VPS,
> com backtracking documentado.

Escopo da Fase 9 do Plano Mestre: colocar em produção o acumulado das fases
2–8 e **comprovar restauração** (drill) sobre cópia cifrada local — pré-condição
que o issue #1572 estabeleceu para qualquer saneamento destrutivo dos dumps
históricos em claro.

## 0. Pré-condições (todas obrigatórias antes de marcar a janela)

1. **Main verde**: pipeline Woodpecker da main em `success` no commit alvo.
2. **Suíte completa verde no CI** (backend + frontend + gates) no commit alvo.
3. **Migrations**: `alembic heads` com **um único head**; nenhuma migration
   pendente entre o commit em produção e o alvo sem revisão prévia.
4. **Backup pré-deploy com sucesso**: executar `scripts/backup.sh` e conferir
   `local_ok=true` **com retenção** (cópia cifrada persistida no `BACKUP_DIR`,
   não temporária — semântica nova do #1572) e `offsite_ok` conforme política
   (`BACKUP_OFFSITE_OBRIGATORIO`).
5. **Restore drill ensaiado** (seção 3) em ambiente de staging/local **antes**
   da janela — a janela não é lugar para descobrir que o drill não funciona.
6. **Janela comunicada**: usuário final avisado (o deploy reinicia serviços;
   downtime esperado na ordem de minutos).
7. **Pessoal**: Titular (go/no-go) + executor com acesso root à VPS.

## 1. Janela e go/no-go

| Item | Detalhe |
|---|---|
| Janela sugerida | fora do horário comercial; evitar dia de fechamento financeiro |
| Duração reservada | 90 min (deploy ~15 min + drill ~30 min + margem) |
| Go | mensagem explícita do Titular citando o commit alvo (SHA) |
| Abort | permitido a qualquer ponto antes da seção 4; rollback da seção 5 |
| Congelamento | nenhum merge na main a partir do anúncio da janela até o fechamento |

Checklist de go (marcar na issue durante a janela):

```
[ ] Commit alvo: __________ (SHA) — main verde (pipeline #____)
[ ] Backup pré-deploy: local_ok=true (retido), offsite_ok=____, artefatos: ______
[ ] Janela comunicada ao escritório
[ ] GO explícito do Titular (quem/quando): ________
```

## 2. Deploy (composição dos runbooks existentes)

Base: `docs/DEPLOY-VPS.md` (seção "Atualizar para uma nova versão") +
`scripts/deploy_vps_safe.sh` (lock `deploy_lock.sh` + verificação pós).

1. Entrar na VPS e posicionar o repositório no commit alvo:
   `git fetch && git checkout <SHA-alvo>`.
2. Executar o deploy seguro (aplica migrations via entrypoint, sobe os
   serviços e respeita o lock de deploy):
   `./scripts/deploy_vps_safe.sh` (ou o passo a passo manual do DEPLOY-VPS.md
   quando o script não estiver disponível).
3. Acompanhar os logs do boot até ver, na ordem:
   `[entrypoint] Aplicando migrations (alembic upgrade head)...` →
   `[entrypoint] Iniciando uvicorn...`.
4. Verificação pós-deploy: `./scripts/post_deploy_check.sh` + "Verificação
   rápida" do DEPLOY-VPS.md (health, login, uma leitura de casos, uma leitura
   de prazos).
5. Registrar na issue: SHA em produção, duração, qualquer desvio.

## 3. Restore drill (o entregable central da Fase 9)

Base: `docs/BACKUP_RESTORE_RUNBOOK.md` — seções "Prova automática de
restauração" e "Execução manual do restore drill". O drill **em produção na
janela** valida a cadeia inteira: artefato cifrado local → decifragem →
restore em banco EFÊMERO → verificação de integridade → limpeza.

1. Escolher o conjunto de artefatos do backup pré-deploy (seção 1) — nunca
   gerar artefato ad hoc para o drill; a prova vale porque é o MESMO
   mecanismo que protege produção.
2. Executar o drill conforme o runbook de backup (comando do drill/restore em
   banco efêmero, sem tocar a base de produção).
3. Critérios de aceite (espelham o runbook): restore conclui sem erro;
   contagens de tabelas críticas conferem com as do inventário do ciclo de
   backup; um login de teste autentica contra a base restaurada (hash de
   senha íntegro); PII cifrada lê corretamente (chave vigente).
4. Prova com artefato real externo: se o offsite estiver ativo, baixar UM
   artefato offsite e repetir a decifragem (seção "Prova com artefato real
   externo" do runbook).
5. Registrar na issue: duração do restore, contagens, resultado do login de
   teste, RTO observado (comparar com o RTO alvo documentado no runbook de
   backup).

**Somente após o drill aprovado** o Titular pode autorizar, em decisão
separada, o saneamento destrutivo dos dumps históricos em claro (fora desta
janela, com runbook próprio).

## 4. Fechamento

- Atualizar `PLANO_MESTRE_STATUS.md` (Fase 9 → completa, com link para a
  issue da janela e o log do drill).
- Arquivar na issue: saída do `post_deploy_check.sh`, log do drill, horários
  de início/fim.

## 5. Rollback

Disparar se a verificação pós-deploy falhar de forma não-mitigável dentro da
janela OU se o drill reprovar com o backup que seria a última linha de defesa:

1. `git checkout <SHA-anterior-em-producao>` e reexecutar o deploy seguro.
2. Migrations para baixo **somente** se o deploy as aplicou e o runbook da
   migration em questão prevê reversão; caso contrário, reverter código sem
   reverter schema (o backend deve tolerar colunas remanescentes — validar no
   ensaio da pré-condição 5).
3. Se a base ficou inconsistente: restaurar do conjunto do backup pré-deploy
   (mesmo mecanismo do drill — é para isso que a prova existe).
4. Post-mortem curto na issue antes de reagendar.

## 6. Pós-janela (semana seguinte)

- Monitorar erro/latência nos painéis de observabilidade por 48h.
- Com o drill comprovado: agendar o saneamento dos dumps legados (decisão
  separada, janela separada).
- Fechar #1572 com a evidência do drill anexada.
