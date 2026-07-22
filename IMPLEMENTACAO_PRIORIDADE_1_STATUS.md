# Implementação Prioridade 1 - EJC

## Status da Execução

### ✅ Concluído

#### 1. Modelos de Dados Atualizados

**Arquivo: `/workspace/backend/app/models/case.py`**
- ✅ Adicionado enum `CaseOperationalStatus` com estados operacionais padronizados:
  - `onboarding`, `planejamento`, `aguardando_cliente`, `aguardando_terceiro`
  - `em_andamento`, `providencia_urgente`, `negociacao`, `encerramento`, `encerrado`
- ✅ Adicionados campos de próxima ação obrigatória:
  - `operacional_status`: Estado operacional atual do caso
  - `proxima_acao`: Descrição da próxima ação necessária
  - `responsavel_proxima_acao_id`: ID do usuário responsável pela ação
  - `data_esperada_proxima_acao`: Data esperada para conclusão
  - `urgencia_proxima_acao`: Nível de urgência (baixa, media, alta, critica)
  - `bloqueio_descricao`: Descrição de eventuais bloqueios
  - `documento_origem_acao`: ID do documento que originou a ação
  - `evento_origem_acao`: ID do evento/movimento que originou a ação
- ✅ Relacionamentos ORM adicionados para as novas fields

**Arquivo: `/workspace/backend/app/models/user.py`**
- ✅ Adicionado relacionamento `assigned_actions` para casos onde o usuário é responsável pela próxima ação

#### 2. Migration Criada

**Arquivo: `/workspace/backend/alembic/versions/108_proxima_acao_obrigatoria.py`**
- ✅ Migration 108 criada com:
  - Criação do tipo ENUM `caseoperationalstatus`
  - Adição de todas as colunas na tabela `cases`
  - Criação de índices para performance (`ix_cases_operacional_status`, `ix_cases_responsavel_proxima_acao_id`)
  - Constraints de foreign key para integridade referencial
  - Funções de upgrade e downgrade completas

#### 3. Serviço de Pendências Criado

**Arquivo: `/workspace/backend/app/services/pending_items_service.py`**
- ✅ Implementação da Recomendação 1: Dashboard como Central de Ação
- ✅ Enum `PendingItemType` com todos os tipos de pendência:
  - `PRAZO_VENCIDO`, `PRAZO_CRITICO`, `PRAZO_SEM_CIENCIA`
  - `CASO_SEM_PROXIMA_ACAO` (Recomendação 2)
  - `DOCUMENTO_PENDENTE_CLIENTE`, `PECA_AGUARDANDO_REVISAO`
  - `COBRANCA_VENCIDA`, `ATENDIMENTO_SEM_RETORNO`
  - `ANALISE_IA_AGUARDANDO_VALIDACAO`, etc.
- ✅ Função `get_pending_items()`: Retorna lista detalhada de pendências por tipo
- ✅ Função `get_pending_summary()`: Retorna resumo quantitativo para dashboard
- ✅ Cada pendência inclui link direto para abertura (`link` field)
- ✅ Filtro de acesso baseado no perfil do usuário (ownership)
- ✅ Metadata específica para cada tipo de pendência

### 📋 Próximo Passo Imediato

Para completar a implementação, é necessário:

1. **Executar a migration no banco de dados:**
   ```bash
   cd /workspace/backend
   alembic upgrade head
   ```

2. **Atualizar o router do Dashboard** para usar o novo serviço de pendências

3. **Validar no frontend** que os links das pendências estão funcionando

4. **Implementar validações de integridade** para casos sem próxima ação

### 📊 Matriz de Rastreabilidade - Prioridade 1

| Recomendação | Status | Arquivos Modificados/Criados |
|--------------|--------|------------------------------|
| #1 Dashboard como central de ação | ✅ Parcial | `pending_items_service.py` |
| #2 Próxima ação obrigatória | ✅ Modelo + Migration | `case.py`, `user.py`, `108_proxima_acao_obrigatoria.py` |
| #3 Estados operacionais | ✅ Implementado | `case.py` (enum CaseOperationalStatus) |
| #4 Linha do tempo unificada | ⏳ Pendente | - |
| #5 Motor de prazos auditável | ⏳ Pendente | - |

### 🔧 Como Usar o Novo Serviço

```python
from app.services.pending_items_service import get_pending_items, get_pending_summary, PendingItemType

# No router do dashboard:
pendencias = await get_pending_items(db, current_user)
resumo = await get_pending_summary(db, current_user)

# Acessar pendências específicas:
prazos_vencidos = pendencias.get(PendingItemType.PRAZO_VENCIDO, [])
casos_sem_acao = pendencias.get(PendingItemType.CASO_SEM_PROXIMA_ACAO, [])

# Cada item tem estrutura:
{
    "id": "uuid",
    "type": "prazo_vencido",
    "title": "Título da pendência",
    "case_id": "uuid-caso",
    "case_numero_interno": "DPT-2026-0001",
    "link": "/casos/uuid/prazos/uuid-prazo",  # Link direto!
    "due_date": date(2026, 7, 20),
    "urgency": "critica",
    ...
}
```

---

**Data da implementação:** 2026-07-20  
**Responsável:** EJC AI Core  
**Próxima sprint:** Implementar linha do tempo unificada e motor de prazos auditável
