# EJC — Continuidade: RPO / RTO, Prova de Restauração e Rollback N-1

**Escopo.** Define RPO/RTO **propostos** (para homologação/assinatura), documenta o
drill de backup/restore que **roda localmente** e é comprovado nesta entrega, e
registra a compatibilidade de **rollback entre código N-1 e schema N**.

**O que é executável aqui × o que depende da infra de vocês.** O drill de
`pg_dump → banco vazio → restore → verificação` foi executado de verdade em
PostgreSQL 16 + pgvector local (evidência na seção 4). O backup/restore no
**Google Drive real** (rclone/service account, chave Fernet, VPS Contabo) **não é
executável neste ambiente** — o que falta está listado na seção 5.

---

## 1. Rotina de backup vigente (base do RPO)

Há duas rodas de backup, ambas diárias e convergindo em **~02:00 BRT**:

| Roda | Origem | Formato | Destino | Retenção |
|---|---|---|---|---|
| `scripts/backup.sh` | cron do host `0 2 * * *` (`TZ=America/Sao_Paulo`) | `pg_dump | gzip` (`.sql.gz`) + `uploads.tar.gz` + manifesto `sha256` | local `/opt/ejc/backups` + `rclone gdrive:EJC-Backups` | local 30 d / Drive 90 d |
| Scheduler do backend (`RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md`) | `BACKUP_HORA_UTC=05:00 UTC` (= 02:00 BRT), opt-in `BACKUP_ENABLED=true` | `pg_dump -Fc` **cifrado Fernet** (`.dump.enc`) + `uploads.tar.gz.enc` | Google Drive (service account) | `BACKUP_RETENCAO_DIAS=14` |

A roda **cifrada** (scheduler) é a canônica para offsite (LGPD). O `pg_dump` cobre
apenas o banco; os arquivos físicos (peças, provas, assinaturas do Portal) vivem
em `UPLOAD_DIR` e são salvos à parte — restauração sem os uploads é incompleta.

---

## 2. RPO proposto — **24 horas**

Com um único ciclo diário, a perda máxima aceitável de dados é a janela entre
duas execuções: uma falha às 01:59 perde tudo desde as 02:00 anteriores.

- **RPO proposto: 24 h** (teto determinado pela cadência diária). Perda média
  efetiva tende a ser menor que 24 h.
- **Para reduzir** o RPO abaixo de 24 h seria necessário **PITR / WAL archiving**
  (arquivamento contínuo de WAL) ou dumps mais frequentes — **hoje não
  implementado**. Recomenda-se avaliar PITR se o negócio exigir RPO ≤ 1 h.

---

## 3. RTO proposto — **2 h** (incidente de banco) / até **4 h** (DR completo)

O componente puramente técnico do restore é rápido; o grosso do RTO é decisão
humana, download do offsite e decifragem. Decomposição proposta:

| Etapa | Estimativa | Observação |
|---|---|---|
| Detecção do incidente | ~15 min | Monitor alerta se o último backup passar de 25 h (runbook §9) |
| Decisão humana + janela declarada | ~30 min | DR de produção exige aprovação e backup de segurança do estado atual |
| Download do par cifrado do Drive | ~15 min | Depende de tamanho/banda |
| Decifragem Fernet + `pg_restore --list` | ~5–15 min | `validar_restauracao_cifrada.py` |
| `pg_restore` do banco + `tar -x` dos uploads | ~15–45 min | **Escala com o volume**; componente técnico medido localmente em ~1 s (schema real semeado, seção 4) |
| Boot da stack + migrations (se preciso) + smoke E2E | ~15–30 min | `qa/e2e/run_fictitious_smoke.py` |

- **RTO proposto: 2 h** para restaurar o banco e voltar a operar; **até 4 h** para
  DR completo incluindo uploads e validação. Metas a **confirmar na primeira
  prova real** (runbook §7 mede RTO/RPO efetivos).

---

## 4. Drill LOCAL de backup/restore (executável e comprovado)

Script novo: **`scripts/backup/drill_local_backup_restore.py`**. Faz, sem sair da
máquina: coleta métricas da origem → `pg_dump -Fc` → `createdb` destino vazio
(`template0`) → `pg_restore` → **verifica integridade** → remove o destino.

Verificações: mesma `alembic_version`; mesmo nº de tabelas BASE; mesma contagem
das tabelas-chave; extensões `vector` (pgvector) e `pg_trgm` presentes; e, como
bônus, round-trip byte a byte de um **dado** `vector` (não só da extensão).

```bash
export DATABASE_URL_SYNC='postgresql://user:pass@host:5432/ejc_db'
DRILL_ALLOW=1 python3 scripts/backup/drill_local_backup_restore.py
# opcionais: DRILL_KEY_TABLES=clients,cases,users  DRILL_REPORT=./evidencias/drill.json
```

**Resultado real desta sessão** (PostgreSQL 16.13 + pgvector 0.6.0, banco semeado
com o schema real do EJC na revisão `036`):

| Verificação | Origem | Destino | Resultado |
|---|---|---|---|
| `alembic_version` | `b6c7d8e9f0a1` | `b6c7d8e9f0a1` | OK |
| tabelas BASE (`public`) | 66 | 66 | OK |
| extensões | `vector 0.6.0`, `pg_trgm 1.6` | idem | OK |
| linhas-chave | `clients=2, cases=2, users=3, deadlines=0, knowledge_chunks=0` | idem | OK |
| dado pgvector (`drill_vec.emb`) | `[1,2,3]…` | idêntico | OK |
| banco temporário removido | — | — | sim (sem leftover) |

`status=sucesso`, duração 1,15 s, dump 197.714 bytes, exit 0.

**Teste negativo** (prova de que o drill de fato verifica): apontado a um banco
sem as extensões, retorna `status=erro`,
`falhas=['extensão ausente no destino: vector', 'extensão ausente no destino: pg_trgm']`,
exit 1.

**Relação com os scripts existentes** (reaproveitados, não duplicados):

- `scripts/backup/restore_drill.py` — gate de continuidade com dump **cifrado**
  (Fernet) + marcador de integridade; exige chave. Este drill local dispensa
  cifragem e adiciona as checagens que faltavam ao gate: **extensões** e
  **linhas-chave**. Os dois se complementam.
- `scripts/backup/validar_restauracao_cifrada.py` — validação/restauração do par
  cifrado do Drive (runbook §6/§7); é o caminho para a prova REAL da seção 5.
- `scripts/restore.sh` — restauração operacional para produção/homologação.

---

## 5. O que falta para o backup/restore no Drive REAL (NÃO executável aqui)

Este ambiente não tem Docker, credenciais do Drive nem acesso à VPS. Para fechar
o gate G7 / issue #378 é preciso, **na VPS Contabo**:

1. **Credencial do Drive** — uma das duas: `rclone.conf` em
   `/root/.config/rclone/` (roda `scripts/backup.sh`) **ou** service account
   `BACKUP_GOOGLE_DRIVE_AUTH_MODE=service_account` +
   `BACKUP_GOOGLE_DRIVE_SERVICE_ACCOUNT_FILE`/`_JSON` (roda o scheduler cifrado).
2. **Chave Fernet** `BACKUP_ENCRYPTION_KEY`, gerada uma vez e **custodiada fora da
   VPS** (perdê-la torna todo backup irrecuperável).
3. **Ativação** `BACKUP_ENABLED=true` + `BACKUP_DRIVE_FOLDER_ID`, recarregar o
   backend (`scripts/backup/ativar_backup.sh`).
4. **Stack de pé** — os scripts usam `docker exec` em `ejc_db`/`ejc_backend`.
5. **Prova real de restauração** (runbook §6 e §7): baixar o par `.enc` do Drive,
   `validar_restauracao_cifrada.py --restore-test` em banco descartável, amostrar
   uploads, **medir RTO/RPO efetivos** e substituir os valores propostos das
   seções 2 e 3 pelos medidos.
6. **Monitor externo** alertando backup > 25 h e restauração periódica vencida.

Enquanto 1–6 não forem feitos na infra de vocês, o drill da seção 4 cobre a
mecânica e a fidelidade do `pg_dump/restore`, mas **não** prova o caminho
cifrado + Drive fim a fim.

---

## 6. Rollback e compatibilidade N-1 (schema N × código N-1)

**Princípio.** Um deploy pode aplicar a migration N (schema→N) e depois precisar
reverter o **código** para N-1. Se o schema N removeu/alterou algo que o código
N-1 ainda usa, o rollback só de código quebra. O padrão seguro é
**expand → migrate → contract** em releases separados, mantendo N-1 compatível.

### 6.1. Gap no rollback automático do deploy

`scripts/deploy_vps_safe.sh` aplica `alembic upgrade head` (linha 99, quando
`RUN_MIGRATIONS=1`) **após** o health-check, e há passos que podem falhar
**depois** disso (ex.: `reparar_conhecimento_rag`, linha 153; `post_deploy_check`,
linha 160). O `trap rollback ERR` (linhas 32-48) **re-tageia as imagens antigas e
sobe os containers — reverte o CÓDIGO, mas NÃO roda `alembic downgrade`**. Logo,
uma falha pós-migration deixa **schema N + código N-1**: exatamente a zona de
perigo das migrations "contract". A rede de segurança automática é **insuficiente**
para releases que carregam uma migration destrutiva.

### 6.2. Migrations recentes backward-incompatible (exigem cuidado)

| Migration | Mudança destrutiva no `upgrade()` | Por que quebra o código N-1 | Rollback seguro |
|---|---|---|---|
| **112** `client_pii_drop_plaintext` | `DROP COLUMN clients.cpf, clients.cnpj` (texto puro) + índices `ix/uq_clients_cpf/cnpj` | Código N-1 (dual-write) lê/escreve `clients.cpf/cnpj` — comprovado: em head, `SELECT cpf FROM clients` → **`ERROR: column "cpf" does not exist`** | Rollback de código **exige** `alembic downgrade 111_ai_provider_metrics` junto. As colunas voltam **VAZIAS** (texto puro não é reconstruído — comprovado: `cpf_preenchido=0` após downgrade). Se o N-1 então **gravar** cpf/cnpj, repopula texto puro e **reabre o achado C6/LGPD**. |
| **096** `rag_embedding_1024` | `RENAME embedding→embedding_legacy_768`; `DROP`+`ADD embedding vector(1024)` | Código N-1 gera/lê embeddings **768d**: `INSERT` de vetor 768d em `vector(1024)` falha por dimensão; leitura encontra a coluna 1024d **vazia** até o reindex → RAG cai para fallback textual | `alembic downgrade 096→094` restaura `embedding` **768d com dados** (preservados em `embedding_legacy_768`). Rollback só de código (schema em 1024) é incompatível. |

**Comprovação (cluster descartável, migrations reais):** cadeia completa
`001→112 (head)` sobe limpa (igual ao CI); em head, a leitura de `clients.cpf`
falha com `column "cpf" does not exist`; `downgrade 112→111` recria a coluna
vazia; `upgrade` de volta é idempotente. (Ver também a Tarefa 1: os downgrades das
migrations 032/033 foram tornados idempotentes para que um rollback **profundo**
— ex.: `036→031` — não trave mais.)

### 6.3. O que NÃO é risco N-1

A maioria dos `DROP`/`drop_table`/`drop_column` recentes (090, 091, 093, 098, 099,
101, 102, 103, 105, 107, 108, 111) está no **`downgrade()`**, revertendo objetos
que o **próprio `upgrade()`** criou — o código N-1 nunca os conheceu, então não há
incompatibilidade para trás. `106_bytes_bigint` (int→bigint) é alargamento de
tipo: seguro para leitura N-1 (risco só se valores excederem o range de int).

### 6.4. Recomendações

1. **Release com migration "contract" (112, 096) → rollback também do schema.** Não
   confiar no rollback automático só-de-imagem do `deploy_vps_safe.sh`; documentar
   no plano da release o `alembic downgrade <n-1>` correspondente.
2. **Preferir expand/contract em dois releases**: primeiro o release que só
   *adiciona* e passa a usar o novo (mantendo o antigo), depois — após estabilizar
   — o release que *remove* o antigo. Reduz a superfície de rollback perigoso.
3. **Backup imediatamente antes de aplicar contract** (o `deploy_vps_safe.sh` já
   faz `scripts/backup.sh` na linha 74; garantir prova recente de restauração).
