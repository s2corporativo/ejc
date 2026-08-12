# DPT360 — Política de Retenção e Ciclo de Vida LGPD

## Objetivos

1. Definir ciclo de vida canônico para oportunidades (leads) capturadas pelo DPT Empresarial 360
2. Preservar dados vinculados a Cliente/Caso (nunca expurgar se convertido)
3. Automatizar anonimização/expurgo de oportunidades sem conversão, com auditoria completa
4. Evitar reintroduzir data loss do hotfix #1082 enquanto define retenção indefinida clara
5. Separar metadados imutáveis (auditoria) de dados pessoais (email, telefone, mensagem)

## Estados canônicos

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│  TRIAGEM_PENDENTE ──(análise)──→ TRIAGEM_CONCLUIDA ──(rejeitar)──→ DESCARTADA
│        │                               │
│        │                               └──(converter)──→ CONVERTIDA ✓
│        │
│        └──(expirar 30d)──→ EXPIRADA
│
│  DESCARTADA ──(30d)──→ ANONIMIZADA ──(∞)──→ EXPURGADA (job)
│
│  CONVERTIDA ──(protegido)──X (nunca expurga)
│
└─────────────────────────────────────────────────────────────────────────┘
```

### Definições

| Estado | Semântica | Entrada | Saída | Retenção |
|--------|-----------|---------|-------|----------|
| `triagem_pendente` | Recém-criada, não analisada | Intake | → `triagem_concluida` ou `expirada` | 30 dias |
| `triagem_concluida` | Analisada (resultado positivo/negativo) | Manual | → `convertida`, `descartada`, ou re-triada | 90 dias |
| `convertida` | Vinculada a Cliente/Caso real | Sistema | ✗ Nunca muda | ∞ (protegida) |
| `descartada` | Rejeitada (spam, inviável, duplicada) | Manual | → `anonimizada` | 30 dias |
| `expirada` | `triagem_pendente` > 30d sem análise | Job | → `anonimizada` (automático) | N/A |
| `anonimizada` | Email/telefone/mensagem removidos, metadados preservados | Job | → `expurgada` | ∞ (sem PII) |
| `expurgada` | Removida do banco | Job | — | — |

## Campos de modelo

Estender `DocumentIntakeBatch`:

```python
# Estado de ciclo de vida (default: triagem_pendente para novo batch)
ciclo_vida_estado = Column(
    String(32),
    nullable=False,
    default="triagem_pendente",
    index=True
)

# Timestamp de última mudança de estado (auditoria de timing)
ciclo_vida_updated_at = Column(
    DateTime(timezone=True),
    server_default=func.now(),
    onupdate=func.now()
)

# Sinaliza se PII (email, telefone, mensagem) foi removido
anonimizada_em = Column(
    DateTime(timezone=True),
    nullable=True,
    index=True
)

# Quem/quando moveu de triagem_pendente → triagem_concluida (auditoria)
triagem_concluida_por = Column(String(36), nullable=True)  # FK user
triagem_concluida_em = Column(DateTime(timezone=True), nullable=True)
```

## Fluxos de automação

### 1. Anonimização automática (job `dpt360_lifecycle_anonimizar`)

**Trigger**: Daily, 02:30 UTC

**Seleção**:
```sql
WHERE modalidade = 'dpt360_oportunidade'
  AND ciclo_vida_estado IN ('descartada', 'expirada')
  AND ciclo_vida_updated_at < NOW() - INTERVAL '30 days'
  AND anonimizada_em IS NULL
  AND case_id IS NULL
```

**Ação**:
1. Sob `SELECT ... FOR UPDATE`:
   - Verificar se ainda está em estado protegido (descartada/expirada)
   - Verificar se case_id permanece NULL
2. Remover campos pessoais de `resultado["dpt360_opportunity"]`:
   - `email` → NULL
   - `telefone` → NULL
   - `mensagem` → NULL
   - `contato` → NULL
   - **Preservar**: origem, urgencia_declarada, status, assunto, empresa
3. Gravar `anonimizada_em = NOW()`
4. Registrar em AuditLog: ação=`ANONIMIZAR`, entidade=`DocumentIntakeBatch`

**Proteção contra TOCTOU**: Defesa no resultado é revalidada sob lock antes de modificação.

### 2. Expurgo automático (job `dpt360_lifecycle_expurgar`)

**Trigger**: Daily, 03:00 UTC (após anonimização)

**Seleção**:
```sql
WHERE modalidade = 'dpt360_oportunidade'
  AND ciclo_vida_estado IN ('anonimizada')
  AND anonimizada_em < NOW() - INTERVAL '30 days'
  AND case_id IS NULL
```

**Ação**:
1. Sob `SELECT ... FOR UPDATE`:
   - Revalidar estado = anonimizada, case_id IS NULL
2. Deletar `DocumentIntakeItem`s (se houver arquivos anexos)
3. Deletar `Document`s (se houver)
4. Deletar `DocumentIntakeBatch`
5. Registrar em AuditLog: ação=`EXPURGAR`, entidade=`DocumentIntakeBatch`, apenas ID/timestamp (sem PII)

### 3. Mudança de estado manual (rotas de staff)

**Endpoint** `POST /api/dpt360/oportunidades/{id}/ciclo-vida`

Payload:
```json
{
  "novo_estado": "triagem_concluida",
  "motivo": "Analisada, sem interesse"  // opcional
}
```

**Transições válidas**:
- `triagem_pendente` → `triagem_concluida` (staff)
- `triagem_concluida` → `triagem_pendente` (re-análise)
- `triagem_concluida` → `descartada` (rejeição)
- `triagem_pendente` → `descartada` (rejeição sem análise)
- Qualquer outro: 422 Unprocessable Entity

**Ação**:
1. Verificar RBAC (require_gestao ou require_admin)
2. Sob `SELECT ... FOR UPDATE`:
   - Revalidar estado atual do batch
   - Revalidar case_id IS NULL
3. Atualizar `ciclo_vida_estado`, `ciclo_vida_updated_at`
4. Se novo_estado = `triagem_concluida`: gravar `triagem_concluida_por` e `triagem_concluida_em`
5. Registrar AuditLog com motivo (sem PII da oportunidade)
6. Disparar webhook (opcional): notificar responsible sobre oportunidades descartadas em lote

## Proteção contra data loss

**Invariante crítica**: Oportunidade com `case_id` preenchido nunca é alterada de `convertida` nem expurgada, mesmo se job falhar a revalidar.

**Mecanismo**:
1. Ao converter para Cliente/Caso: `UPDATE DocumentIntakeBatch SET ciclo_vida_estado = 'convertida' WHERE id = ?`
2. Job verifica `ciclo_vida_estado = 'convertida'` e pula (no-op seguro)
3. Ao deletar Document vinculado a um Cliente/Caso via RBAC: job não toca `DocumentIntakeBatch` (já não seria selecionado)

**Testes mandatórios**:
- Triagem concluída, convertida a Cliente → nunca é expurgada
- Triagem concluída, convertida a Caso → nunca é expurgada
- Concorrência: DELETE do caso não dispara expurgo de oportunidade
- Concorrência: mudança de estado + job rodando não causa TOCTOU

## Auditoria

**Campos registrados em AuditLog**:
- `acao`: `CRIAR`, `MUDAR_CICLO_VIDA`, `ANONIMIZAR`, `EXPURGAR`
- `entidade`: `DocumentIntakeBatch`
- `registro_id`: ID do batch
- `user_id`: quem disparou (NULL para jobs)
- `dados_antes`: `{ciclo_vida_estado: "triagem_pendente", ...}`
- `dados_depois`: `{ciclo_vida_estado: "triagem_concluida", triagem_concluida_em: "2026-08-12T14:30:00Z", ...}`
- `detalhes`: motivo/contexto (sem PII: ex. "Rejeitado", não "Rejeitado porque disse Y na mensagem")

**Nunca registra em AuditLog**:
- email, telefone, mensagem, contato (pessoais)
- Nome do lead
- Mensagem de inteligência que contenha PII

## Validação de segurança

- [ ] Nenhum email/telefone/mensagem de oportunidade descartada/expirada escapa para AuditLog
- [ ] AuditLog de ANONIMIZAR/EXPURGAR não contém dados pessoais
- [ ] Revalidação sob lock: impede TOCTOU entre seleção e modificação
- [ ] Invariante: case_id = 'convertida' nunca é tocada
- [ ] RBAC: só `gestao` ou `admin` pode mudar `ciclo_vida_estado` manualmente
- [ ] Dry-run disponível: jobs têm `dry_run=True` para teste antes de `dry_run=False`

## Plano de implementação

### Fase 1: Schema + Serviço (Este PR)
1. Migration: adicionar 4 colunas (estado, updated_at, anonimizada_em, triagem_concluida_*)
2. `dpt360_lifecycle_service.py`: funções de mudança de estado + anonimização
3. Rota `POST /api/dpt360/oportunidades/{id}/ciclo-vida`
4. Job `dpt360_lifecycle_anonimizar` e `dpt360_lifecycle_expurgar`
5. Testes de máquina de estados

### Fase 2: Ativação e Rollout (Próximo PR)
1. Ativar jobs com `dry_run=True` inicialmente
2. Monitorar relatórios de simulação
3. Gradualmente `dry_run=False`
4. Frontend: interface para mudar estados manualmente

## Referências

- Issue #1082: Hotfix imediato (preserva oportunidades do job genérico)
- Issue #1083: Radar não sinalizava truncamento
- Issue #1084: Reidratação duplicada
- Issue #1086: Esta política (ciclo de vida definitivo)
