# Runbook — reclassificação de área dos casos históricos

> **Não é uma migration.** É um script operacional de curadoria assistida
> (`scripts/reclassificar_areas_casos.py`) que altera dados em `cases.area`.
> **Simula por padrão** — só escreve com `--aplicar`. **Exige backup prévio.**

## Por que existe

Até o commit `b073d5f` o frontend achatava a área do caso: o hub **Bancário**
gravava `civil`; **Imobiliário** e **Trânsito** idem; **Digital/LGPD** virava
`empresarial` e **Administrativo** virava `tributario` — embora os cinco valores
existam no enum `casearea` desde a migration 083. Casos **novos** já nascem com
a área certa; os **históricos** ficaram com a área antiga, então as agregações
por área (dashboards, jurimetria, roteamento de skills de IA) misturam dois
critérios. Reclassificar o histórico é **decisão do escritório**.

## O que o script consegue — e o que não consegue

Olhando só `cases.area` **não há** como saber se um caso `civil` é bancário,
imobiliário ou de trânsito. O único sinal por caso é o registro especializado
vinculado, e ele só existe para **dois** dos cinco achatamentos:

| Achatamento              | Sinal disponível                       | O script decide? |
|--------------------------|----------------------------------------|------------------|
| `civil` → `bancario`     | `bancario_cases` vinculado             | **Sim** (alta)   |
| `tributario` → `administrativo` | `admin_cases` com tipo exclusivo do hub Administrativo | **Sim** (alta) |
| `civil` → `imobiliario`  | nenhum                                 | Não              |
| `civil` → `transito`     | nenhum                                 | Não              |
| `empresarial` → `digital_lgpd` | nenhum                           | Não              |

Os hubs de Imobiliário, Trânsito e Digital/LGPD criam **caso simples**, sem
tabela satélite; e o ROPA da LGPD (`lgpd_registros_tratamento`) é por **cliente**,
não por caso. Esses três só podem ser reclassificados por **decisão humana**,
caso a caso — o script os lista/conta, nunca os altera.

Níveis: **alta** (único elegível a `--aplicar`) · **media** e **ambigua**
(saem listados para revisão humana, nunca aplicados) · **sem_sinal** (apenas
contados) · **confirmado** (satélite prova que a área atual está certa).

## Ordem obrigatória

1. **Backup verificado.** `scripts/backup.sh` (ou `RUNBOOK_BACKUP.md` /
   `RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md`). Anote a referência do backup.
2. **Simulação** (não escreve nada). O container `ejc_db` não publica porta e a
   imagem do backend não inclui `scripts/` — então copie os dois arquivos para
   dentro de `ejc_backend`, que já tem `psycopg2` e o `DATABASE_URL_SYNC` certo:
   ```bash
   cd /opt/ejc
   docker cp scripts/reclassificacao_areas.py      ejc_backend:/tmp/
   docker cp scripts/reclassificar_areas_casos.py  ejc_backend:/tmp/
   docker exec -it ejc_backend python3 /tmp/reclassificar_areas_casos.py
   ```
   (Em máquina de desenvolvimento, ou contra uma **cópia restaurada** do dump,
   basta `python3 scripts/reclassificar_areas_casos.py` com `DATABASE_URL_SYNC`
   exportada ou `--database-url`. Ensaiar na cópia antes é o caminho mais seguro.)

   > **O script assume PRODUÇÃO por padrão.** Antes, o modo acima (host local,
   > banco `ejc_db`, sem `APP_ENV` no shell) driblava os três sinais de detecção
   > ao mesmo tempo e, com `--sem-interacao --confirmo-backup`, a proteção
   > desaparecia. Agora, para rodar contra banco que **não** é de produção,
   > declare: `--nao-e-producao` (ou `APP_ENV=development`). Sem essa declaração,
   > qualquer operação de escrita exige `--confirmo-producao`.

   > **Assinatura do rollback.** O arquivo de rollback é assinado com HMAC. Defina
   > `EJC_ROLLBACK_HMAC_KEY` (ou tenha `SECRET_KEY` no ambiente, ≥ 16 caracteres);
   > sem isso o script recusa gravar — rollback sem integridade seria pior que
   > rollback nenhum.
3. **Conferência humana da amostra.** Um advogado abre os casos do bloco 6
   ("AMOSTRA — ELEGÍVEIS") e confirma que a evidência corresponde à realidade.
   Se algum estiver errado, **pare** e reporte — o critério é que precisa mudar,
   não o dado. Use `--amostra 50` para ver mais e `--incluir-titulo` se precisar
   do título (a saída passa a conter dado do escritório: canal interno apenas).
4. **Aplicar.** Escreve em transação, com commit por lote e arquivo de rollback
   gravado **antes** do primeiro `UPDATE`. Grave o rollback em `/app/backups`
   (volume persistente `backups_data`) e traga o arquivo para o host:
   ```bash
   docker exec -it ejc_backend python3 /tmp/reclassificar_areas_casos.py \
     --aplicar --confirmo-producao \
     --saida-rollback /app/backups/reclassificacao_areas_$(date -u +%Y%m%dT%H%M%SZ).json
   # digite RECLASSIFICAR quando solicitado
   docker cp ejc_backend:/app/backups/reclassificacao_areas_<ts>.json ./
   ```
   Ensaio menor primeiro, se preferir: `--limite 20`.
5. **Verificar.** Rode a simulação de novo: os casos aplicados agora aparecem
   como `confirmado` e o total de elegíveis cai para 0 (idempotência). Confira
   os dashboards por área e os hubs Bancário/Administrativo no frontend.
6. **Guardar o arquivo de rollback** junto do registro do backup. Sem ele não há
   reversão exata. (Sem `--saida-rollback` o padrão é
   `var/reclassificacao/rollback_<ts>.json`, relativo ao diretório atual.)

## Se algo sair errado

- **Reverter tudo:**
  ```bash
  docker exec -it ejc_backend python3 /tmp/reclassificar_areas_casos.py \
    --reverter /app/backups/reclassificacao_areas_<ts>.json --confirmo-producao
  ```
  Restaura exatamente as áreas anteriores. A reversão é guardada: só volta o
  caso que estiver **na área nova**; quem já foi alterado por outra via é
  ignorado, não sobrescrito.
- **Processo morreu no meio:** o arquivo de rollback já existe com o plano
  completo (`status: "planejado"`). `--reverter` sobre ele é seguro — os casos
  que não chegaram a ser alterados são simplesmente ignorados.
- **Reversão insuficiente:** restaure o backup do passo 1 (`scripts/restore.sh`
  / `RUNBOOK_BACKUP.md`).

## Rastro

Cada reclassificação grava uma linha em `audit_logs`
(`acao=UPDATE`, `entidade=cases`, `user_role='script'`, `user_id NULL`, com
`dados_antes`/`dados_depois`). O helper `criar_audit_log()` é async e depende do
contexto de request, então o script insere direto na tabela. O arquivo de
rollback é o segundo registro, e o log do processo vai para stderr.

## Depois do procedimento — expurgo do arquivo de rollback

O arquivo em `/app/backups` contém o mapa `case_id → área` e **dirige `UPDATE`s
em `cases`** quando usado com `--reverter`. Ele é gravado com `0600` (diretório
`0700`) e assinado, mas continua sendo material sensível fora do versionamento:
o `.gitignore var/` **não** cobre `/app/backups`.

Concluída a janela de reversão (recomendado: 7 dias após a aplicação, com a
reclassificação já validada pelo escritório), remova o arquivo:

```bash
docker exec -it ejc_backend sh -lc 'ls -l /app/backups/rollback_*.json'
docker exec -it ejc_backend sh -lc 'shred -u /app/backups/rollback_<ts>.json 2>/dev/null \
  || rm -f /app/backups/rollback_<ts>.json'
```

Se precisar guardar o registro histórico, mova para o cofre de backups do
escritório — não deixe no diretório onde o próprio script procura arquivos para
reverter.

## Manutenção

O critério de decisão vive isolado em `scripts/reclassificacao_areas.py`
(sem banco, sem I/O). Se um hub novo passar a achatar área, ou um satélite novo
aparecer, mexa **lá** — e em `backend/tests/test_reclassificacao_areas_casos.py`,
que trava o critério, a idempotência e a garantia de que a simulação não escreve.
