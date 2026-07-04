---
name: debugger-sistematico
description: >
  Debugger sistemático multi-etapas para erros em produção, migrações com zero downtime e auditorias de segurança em APIs — aplicado ao ecossistema EJC, sistema-s2, Cuidar Vet e Verde Limp. Use SEMPRE que: erro ocorre em produção mas não reproduz localmente, precisar comparar abordagens com matriz de decisão, planejar migração de tecnologia com rollback e feature flags, auditar schema de banco por N+1 e índices ausentes, escrever estratégia de tratamento de erros com retry e degradação graciosa, revisar rota de API por vulnerabilidades. DIFERENÇA: arquiteto-ejc corrige bugs EJC-específicos; arquiteto-docker-deploy resolve infra; este skill aplica METODOLOGIA de debugging sistemático. Acionar em: erro em produção nao reproduz, debug sistematico, 10 etapas diagnostico, comparar abordagens, matriz decisao tecnica, migracao zero downtime, feature flag rollout, schema banco N+1, indices banco, tratamento erros retry, degradacao graciosa, SQL injection rota, XSS CSRF auditoria, seguranca API.
---

# Debugger Sistemático

## Quando usar este skill vs. outros

| Situação | Skill correto |
|----------|--------------|
| Bug específico em tela/módulo do EJC | `arquiteto-ejc` |
| Sistema não sobe, CORS, Nginx, Docker | `arquiteto-docker-deploy` |
| Erro em produção que não reproduz localmente | **este skill** |
| Comparar 2 arquiteturas com trade-offs | **este skill** |
| Planejar migração de tech com zero downtime | **este skill** |
| Auditar segurança de rota específica | **este skill** |
| Schema de banco com problemas de performance | **este skill** |

---

## Modo 1 — Debug de Produção Não Reproduzível

**Trigger:** "Estou recebendo [ERRO] em produção mas não consigo reproduzir localmente"

### Processo Diagnóstico — 10 Etapas

**Etapa 1 — Captura do erro exato**
- Coletar stack trace completo (não apenas a mensagem)
- Identificar: quando começou, frequência, usuários afetados, padrão (sempre / às vezes / horário específico)

**Etapa 2 — Diff de ambiente**
```
CHECKLIST AMBIENTE:
[ ] Versão Node/Python: local vs. prod
[ ] Variáveis de ambiente: .env local vs. prod (sem revelar valores)
[ ] Versões de dependências: package-lock.json ou requirements.txt idênticos?
[ ] Banco de dados: volume de dados local vs. prod (muitas vezes o volume causa erros)
[ ] Memória/CPU disponível: prod tem recursos diferentes?
[ ] Timezone: servidor em fuso diferente do local?
[ ] Encode/charset: dados reais podem ter caracteres especiais não testados
```

**Etapa 3 — Análise de logs**
- Verificar logs 10 minutos antes do erro (causa raiz quase nunca é onde o erro aparece)
- Buscar padrões: request que antecede o erro, usuário específico, endpoint específico

**Etapa 4 — Reprodução controlada**
- Criar fixture com dados reais (anonimizados) que causam o erro
- Testar em ambiente de staging com dados de produção

**Etapa 5 — Isolamento**
- Binary search no código: comentar metade, ver se erro persiste
- Identificar se é: dados específicos / volume / concorrência / race condition / timeout

**Etapa 6 — Hipóteses ranqueadas**
- Listar as 3 hipóteses mais prováveis com probabilidade estimada
- Testar da mais provável para menos

**Etapa 7 — Correção temporária (hotfix)**
- Deploy de safeguard mínimo para parar o sangramento
- NÃO é a correção definitiva — é para produção voltar a funcionar

**Etapa 8 — Correção definitiva**
- Com a causa raiz identificada, implementar fix adequado
- Inclui tratamento do caso que causou o erro

**Etapa 9 — Teste de regressão**
- Escrever teste que reproduz exatamente o bug
- Garantir que o teste falha sem o fix e passa com o fix

**Etapa 10 — Post-mortem**
```
POST-MORTEM TEMPLATE:
- O que aconteceu:
- Quando começou:
- Impacto (usuários/funcionalidades):
- Causa raiz:
- Por que não foi detectado antes:
- Correção aplicada:
- Como prevenir recorrência:
- Alertas/monitoramento adicionados:
```

---

## Modo 2 — Comparação de Abordagens Técnicas

**Trigger:** "Compare estas duas abordagens para [FUNCIONALIDADE]"

### Matriz de Decisão

| Critério | Peso | Opção A | Opção B |
|----------|------|---------|---------|
| Performance | 30% | /10 | /10 |
| Manutenibilidade | 25% | /10 | /10 |
| Custo de implementação | 20% | /10 | /10 |
| Escalabilidade | 15% | /10 | /10 |
| Risco técnico | 10% | /10 | /10 |
| **SCORE PONDERADO** | | | |

**Output obrigatório:**
1. Prós e contras de cada abordagem (técnicos, não de opinião)
2. Qual escolher para um time de [TAMANHO] com budget de [TEMPO]
3. Tempo estimado de desenvolvimento (pessimista / realista / otimista)
4. Custo de manutenção estimado em 12 meses
5. Decisão recomendada com justificativa técnica objetiva

---

## Modo 3 — Plano de Migração Zero Downtime

**Trigger:** "Gere um plano de migração de [TECH ANTIGA] para [TECH NOVA]"

### Estrutura do Plano

**Fase 0 — Avaliação de risco**
```
RISK MATRIX:
- Probabilidade de falha: Baixa / Média / Alta
- Impacto se falhar: Baixo / Médio / Alto
- Score de risco: [Probabilidade × Impacto]
- Decisão Go/No-Go baseada no score
```

**Fase 1 — Preparação (sem afetar produção)**
- Setup do ambiente da nova tecnologia em paralelo
- Migração de dados não-críticos para validar processo
- Documentação do rollback plan

**Fase 2 — Feature Flags (rollout gradual)**
```python
# Exemplo: migrar de PostgreSQL 14 para 15
FEATURE_FLAGS = {
    "use_pg15": {
        "enabled": False,           # começa desligado
        "rollout_percentage": 0,    # % de usuários
        "allowlist": ["user_clovis"]  # usuários de teste
    }
}
```

Estratégia de rollout:
- 0%: apenas devs internos testando
- 5%: usuários beta (confiáveis)
- 25%: validação de performance
- 50%: monitoramento intenso
- 100%: migração completa

**Fase 3 — Go-Live com Runbook**
```
RUNBOOK DO DIA DA MIGRAÇÃO:
08:00 - Backup completo (verificar integridade)
08:30 - Habilitar feature flag para 5%
09:00 - Monitorar métricas (error rate, latência, uso de memória)
09:30 - Se OK: aumentar para 25%
10:00 - Se OK: aumentar para 50%
10:30 - Se OK: 100%
11:00 - Monitoramento pós-migração
ROLLBACK: Se error rate > 1% em qualquer etapa → reverter imediatamente
```

**Fase 4 — Rollback Plan (sempre documentado)**
- Passo a passo para reverter em menos de 15 minutos
- Testar o rollback ANTES do go-live
- Critérios claros de quando acionar o rollback

---

## Modo 4 — Auditoria de Schema de Banco

**Trigger:** "Revise este schema de banco para [TIPO DE APP]"

### Checklist de Auditoria

**Índices:**
```sql
-- Identificar queries N+1: buscar FKs sem índice
-- Exemplo problemático:
SELECT * FROM casos WHERE cliente_id = ?  -- FK sem índice = full table scan

-- Correção:
CREATE INDEX CONCURRENTLY idx_casos_cliente_id ON casos(cliente_id);
-- CONCURRENTLY: cria o índice sem bloquear a tabela em produção
```

**Queries N+1:**
- Identificar: 1 query para lista + N queries para cada item
- Correção: JOIN ou prefetch (eager loading)
- Estimativa de impacto: N+1 com 1000 registros = 1001 queries vs. 1 query com JOIN

**Normalização:**
- Dados duplicados em múltiplas tabelas → extrair para tabela própria
- Calcular por query vs. armazenar pré-calculado: analisar frequência de leitura vs. escrita

**Escalabilidade:**
```
ESTIMATIVA DE PERFORMANCE:
Cenário atual (sem otimização): X ms para 1.000 registros
Após índices: estimativa Y ms (melhoria Z%)
Com 10.000 registros: estimativa W ms
Com 100.000 registros: estimativa V ms
Recomendação de cache: quando tráfego > [THRESHOLD] req/s
```

---

## Modo 5 — Estratégia de Tratamento de Erros

**Trigger:** "Escreva uma estratégia de tratamento de erros para [TIPO DE APP]"

### Taxonomia de Códigos de Erro

```python
# Para EJC/FastAPI:
class ErrorCode:
    # 4xx — Erro do cliente
    AUTH_INVALID_TOKEN = "AUTH_001"
    AUTH_EXPIRED_TOKEN = "AUTH_002"
    VALIDATION_REQUIRED_FIELD = "VAL_001"
    RESOURCE_NOT_FOUND = "RES_001"
    RESOURCE_ALREADY_EXISTS = "RES_002"
    PERMISSION_DENIED = "PER_001"
    
    # 5xx — Erro do servidor
    DB_CONNECTION_FAILED = "DB_001"
    DB_QUERY_TIMEOUT = "DB_002"
    EXTERNAL_API_TIMEOUT = "EXT_001"
    INTERNAL_UNEXPECTED = "INT_001"
```

### Lógica de Retry

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((TimeoutError, ConnectionError)),
    reraise=True
)
async def call_external_api():
    # Tenta 1x, aguarda 1s, tenta 2x, aguarda 2s, tenta 3x, falha
    pass
```

### Degradação Graciosa

```
HIERARQUIA DE DEGRADAÇÃO:
1. Feature completa funcionando (happy path)
2. Feature com dados em cache (stale data, mas funciona)
3. Feature com funcionalidade reduzida (core funciona, extras não)
4. Fallback manual (mostrar mensagem + instrução alternativa)
5. Manutenção (apenas quando não há alternativa)
```

### Alertas com Thresholds

| Métrica | Threshold Warning | Threshold Critical |
|---------|-----------------|-------------------|
| Error rate | > 0.1% | > 1% |
| Latência P95 | > 500ms | > 2000ms |
| DB connection pool | > 70% | > 90% |
| Disk usage | > 70% | > 85% |
| Memory | > 80% | > 95% |

---

## Modo 6 — Auditoria de Segurança de Rota API

**Trigger:** "Revise minha rota de API por vulnerabilidades"

### Checklist de Segurança

```
SQL INJECTION:
[ ] Usar ORM parametrizado (SQLAlchemy, Prisma) — nunca string concat em SQL
[ ] Validar e sanitizar inputs antes de qualquer query
[ ] Princípio do menor privilégio no usuário do banco

XSS (Cross-Site Scripting):
[ ] Sanitizar todos os outputs antes de renderizar no frontend
[ ] Content-Security-Policy header configurado
[ ] Não usar dangerouslySetInnerHTML sem sanitização

CSRF:
[ ] CSRF token em todos os formulários POST/PUT/DELETE
[ ] SameSite=Strict ou Lax em cookies
[ ] Origin validation em APIs públicas

AUTENTICAÇÃO/AUTORIZAÇÃO:
[ ] JWT com expiração curta (access: 15min, refresh: 7d)
[ ] Validar permissão por recurso (não só por rota)
[ ] Rate limiting por IP e por usuário

EXPOSIÇÃO DE DADOS:
[ ] Nunca retornar senha (mesmo hasheada) em response
[ ] Campos sensíveis excluídos dos schemas de response
[ ] Logs sem dados pessoais identificáveis (LGPD)

INPUT VALIDATION:
[ ] Validar tipo, tamanho e formato de TODOS os inputs
[ ] Rejeitar campos não esperados (allowlist, não blocklist)
[ ] Tamanho máximo de upload definido
```

**Output da auditoria:**
```
RELATÓRIO DE SEGURANÇA:
Criticidade CRÍTICA: [lista com fix imediato]
Criticidade ALTA: [lista — resolver em 48h]
Criticidade MÉDIA: [lista — resolver em 1 semana]
Criticidade BAIXA: [lista — monitorar]

Fix priorizado com código de exemplo para cada vulnerabilidade.
```
