# Rollback do DJEN — migrations 169 e 170

Escopo: reverter o módulo de intimações DJEN após o deploy das migrations
`169_djen_multi_advogado` e `170_djen_remove_unicidade_global` (Issue #1986).

## O que as migrations mudam

| Migration | Efeito | Reversível sem perda? |
|---|---|---|
| 169 | Colunas `texto_integral`, `link_oficial`, `orgao`, `scheduler_heartbeat.last_ok_at`; índice único `(comunicacao_id_externo, advogado_id)` | Sim (só remove o que criou) |
| 170 | Troca o índice **único** global de `comunicacao_id_externo` por um índice comum | Só enquanto não houver a mesma comunicação para mais de um advogado |

## Por que reverter só o código NÃO é seguro depois da 170

O código **anterior** ao DJEN grava com
`INSERT … ON CONFLICT (comunicacao_id_externo) DO NOTHING`. O PostgreSQL só aceita
essa cláusula quando existe um índice único exatamente nessa coluna. Depois da
170 ele não existe, e a captura passa a falhar com:

```text
there is no unique or exclusion constraint matching the ON CONFLICT specification
```

Efeitos: o job `djen` (06h30) termina com erro no heartbeat e `POST
/intimacoes/capturar-agora` devolve 503. O restante do sistema segue saudável. **O
rollback automático do `deploy_vps_safe.sh` restaura a imagem anterior, mas não o
banco**, então ele cai exatamente nesse estado.

O downgrade `170 → 169` recusa-se (`downgrade 170 recusado`) quando já existe a mesma
comunicação para mais de um advogado, porque recriar o índice único global
descartaria dados.

## Caminho preferido: corrigir para frente

As migrations 169/170 são compatíveis com o código novo. Se o problema for de
comportamento, publique um hotfix do código novo em vez de reverter.

## Rollback completo (código + banco) — exige decisão do titular

Operação **destrutiva** para as réplicas (comunicações do mesmo `id` externo para
outros advogados). Regra 2 do `CLAUDE.md`: backup prévio obrigatório; o
`deploy_vps_safe.sh` já o faz, confirme antes. As réplicas são preservadas numa
tabela de reserva.

1. Confirme o backup recente do banco e avise a equipe: a captura ficará parada.
2. Dimensione o impacto (somente leitura):
   ```sql
   SELECT count(*) AS comunicacoes_replicadas
     FROM (SELECT comunicacao_id_externo FROM djen_comunicacoes
           GROUP BY comunicacao_id_externo HAVING count(*) > 1) t;
   ```
3. Preserve as réplicas e remova-as, mantendo a linha mais antiga de cada id
   (desempate por `id`):
   ```sql
   CREATE TABLE djen_comunicacoes_replicas_bkp AS
   SELECT d.*
     FROM djen_comunicacoes d
     JOIN (SELECT id,
                  row_number() OVER (PARTITION BY comunicacao_id_externo
                                     ORDER BY created_at, id) AS rn
             FROM djen_comunicacoes) r ON r.id = d.id
    WHERE r.rn > 1;
   DELETE FROM djen_comunicacoes d
    USING djen_comunicacoes_replicas_bkp b
    WHERE d.id = b.id;
   ```
   Repita a consulta do passo 2: o resultado precisa ser `0` antes de seguir.
4. Rode o downgrade e só depois reverta o código:
   ```bash
   cd backend && python -m alembic downgrade 168_finance_ged_links
   ```
5. Para voltar a publicar o DJEN, recarregue as réplicas de
   `djen_comunicacoes_replicas_bkp` depois da 170 (`INSERT … SELECT`).

## Verificação após qualquer das opções

- `python -m alembic current` coerente com o código implantado.
- `GET /intimacoes/status-captura` sem erro e job `djen` com heartbeat `ok`.
