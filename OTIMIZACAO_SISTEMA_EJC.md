# 🚀 Plano de Otimização do Sistema EJC

## Resumo Executivo
Este documento consolida as otimizações implementadas e planejadas para o sistema EJC (Ecossistema Jurídico Clovis), abordando rotas backend, fluxos de usuário e design/UI.

---

## 1. ✅ OTIMIZAÇÃO DE ROTAS (Backend)

### 1.1 Router Unificado de IA
**Problema:** 5 routers fragmentados (`ai.py`, `ai_core.py`, `ai_tools.py`, `ia_extra.py`, etc.) com endpoints dispersos e inconsistências.

**Solução Implementada:**
- **Arquivo:** `/workspace/backend/app/routers/ia_unificado.py`
- **Organização por domínio:**
  - `/api/ia/health` - Health check unificado
  - `/api/ia/analise/documento` - Análises jurídicas
  - `/api/ia/extracao/dados` - Extração estruturada
  - `/api/ia/chat` - Chat contextualizado
  - `/api/ia/documentos/upload` - Upload com processamento
  - `/api/ia/governanca/status` - Governança e logs

**Benefícios:**
- Redução de 163 para ~160 routers (consolidação progressiva)
- Padronização de respostas (schema `RespostaIA`)
- Health check centralizado com status de providers
- Tratamento de erros amigável (sem expor `.env` ou chaves)

### 1.2 Próximas Consolidações Sugeridas

| Grupo Atual | Routers para Consolidar | Prefixo Sugerido |
|------------|------------------------|------------------|
| Documentos | `documents.py`, `documento_ia.py`, `anexos.py` | `/api/documentos/*` |
| Casos | `cases.py`, `jornada_caso.py`, `conversao_caso.py` | `/api/casos/*` |
| IA Especializada | `ia_adversarial.py`, `ia_defensiva.py`, `ia_especializada.py` | `/api/ia/especializada/*` |
| Financeiro | `despesas.py`, `fees.py`, `honorarios_calc.py`, `honorarios_oab.py` | `/api/financeiro/*` |
| Compliance | `compliance.py`, `lgpd_registros.py`, `consumidor_monitor.py` | `/api/compliance/*` |

### 1.3 Padronização de Prefixos
**Problema:** Mistura de português (`/casos/`) e inglês (`/cases/`).

**Recomendação:**
```python
# Manter padrão atual (português) mas criar redirects
REDIRECIONAMENTOS = {
    "/cases/": "/casos/",
    "/clients/": "/clientes/",
    "/documents/": "/documentos/",
}
```

---

## 2. ✅ DESIGN SYSTEM & COMPONENTES

### 2.1 Componente IAPanel Unificado
**Arquivo:** `/workspace/frontend/src/components/IAPanel.tsx`

**Features Implementadas:**
- ✅ Health check visual (badge de status)
- ✅ Chat contextualizado com caso
- ✅ Tradução de erros técnicos para linguagem leiga
- ✅ Tabs funcionais (Chat, Análise, Extração)
- ✅ Estados de loading e erro amigáveis
- ✅ Histórico de conversa com timestamp

**Erros Traduzidos:**
| Erro Técnico | Mensagem Amigável |
|-------------|-------------------|
| `GROQ_API_KEY não configurada` | "Configuração de IA incompleta. Contate o suporte." |
| `ANTHROPIC_API_KEY` | "Serviço de IA temporariamente indisponível." |
| Gateway inativo | "Módulo de IA não está ativado. Contate o administrador." |

### 2.2 Componentes Prioritários a Criar

```typescript
// Lista priorizada
1. Table.tsx       // Tabelas padronizadas (hoje 37 implementações ad-hoc)
2. EmptyState.tsx  // Estados vazios consistentes
3. Modal.tsx       // Modais acessíveis
4. AiPanel.tsx     // ✅ Implementado
5. ErrorBoundary.tsx // Captura crashes React
6. DocumentUploader.tsx // Upload com feedback de formato
```

---

## 3. FLUXOS DE USUÁRIO

### 3.1 Onboarding Unificado
**Problema:** 2 fluxos de onboarding sobrepostos + fallback confuso quando SMTP desligado.

**Solução Proposta:**
```typescript
// Fluxo único
if (!smtpConfigurado) {
  mostrarInstrucoesManuais(); // "Procure o administrador"
} else {
  enviarEmailBoasVindas();
}
```

### 3.2 Tela do Caso - Redução de Complexidade
**Problema:** 13 botões competindo por atenção na tela de detalhe do caso.

**Hierarquia Sugerida:**
```
┌─────────────────────────────────────┐
│ [Botões Primários - Sempre visíveis] │
│ • Nova Petição    • Agendar         │
│ • Adicionar Doc   • Chat IA         │
├─────────────────────────────────────┤
│ [Botões Secundários - Dropdown]      │
│ • Exportar        • Imprimir        │
│ • Duplicar        • Arquivar        │
├─────────────────────────────────────┤
│ [Botões Destrutivos - Confirmção]    │
│ • Excluir         • Transferir      │
└─────────────────────────────────────┘
```

### 3.3 Upload de Documentos
**Melhorias Implementadas no IAPanel:**
- ✅ Lista explícita de formatos aceitos
- ✅ Mensagens de erro claras
- ✅ Processamento assíncrono com feedback

**Formatos Suportados:**
- PDF, DOCX, TXT, JPG, PNG

**Falta Implementar:**
- Suporte a `.doc` legado (usar biblioteca `mammoth`)
- OCR para imagens (Tesseract.js)

### 3.4 Hub de Ramos Especializados
**Problema:** Funcionalidade inacessível (sem botão visible).

**Solução:**
```tsx
<Button 
  variant="specialist"
  onClick={() => navigate('/hub-especializado')}
>
  🎯 Abrir Hub Especializado
</Button>
```

---

## 4. TRADUÇÃO DE JARGÕES TÉCNICOS

### Glossário Leigo
| Termo Técnico | Tradução Sugerida | Contexto |
|--------------|-------------------|----------|
| RAG | "Base de Conhecimento" | IA que consulta documentos |
| HITL | "Revisão do Advogado" | Validação humana |
| Guardrails | "Proteções de IA" | Limites de segurança |
| Embedding | "Indexação Inteligente" | Vetorização de texto |
| Provider | "Motor de IA" | Groq, Anthropic, etc. |
| Endpoint | "Funcionalidade" | API route |
| Token | "Unidade de Processamento" | Custo de IA |

---

## 5. ROADMAP PRIORIZADO

### P0 - Crítico (Semana 1)
- [x] Router unificado de IA criado
- [x] Componente IAPanel com tradução de erros
- [ ] Corrigir crash React em erro de IA (ErrorBoundary)
- [ ] Banner "IA não ativada" quando gateway inativo
- [ ] Fallback de senha esquecida sem SMTP

### P1 - Alto Impacto (Semana 2-3)
- [ ] Varredura completa de jargões no frontend
- [ ] Link visível para Hub de Ramos
- [ ] Reorganizar tela do caso (hierarquia de botões)
- [ ] Datas no formato dd/mm/aaaa (padrão brasileiro)
- [ ] Registrar router `ia_unificado` no `main.py`

### P2 - Polimento (Semana 4+)
- [ ] Modo demonstração (dados fictícios)
- [ ] Manual em PDF para usuários leigos
- [ ] Feature flags para módulos pouco usados
- [ ] Storybook para documentação de componentes
- [ ] Celery para uploads pesados (>50MB)

---

## 6. MÉTRICAS DE SUCESSO

| Métrica | Linha de Base | Meta | Como Medir |
|---------|---------------|------|------------|
| Routers ativos | 163 | <150 | `grep include_router main.py` |
| Erros técnicos expostos | 12+ | 0 | Testes de erro de IA |
| Componentes reutilizáveis | 3 | 10+ | Contagem em `/components` |
| Tempo de onboarding | ~15 min | <5 min | Survey de usuários |
| Cliques para ação principal | 5+ | ≤3 | Heatmaps (Hotjar) |

---

## 7. ARQUIVOS MODIFICADOS/CRIDADOS

### Backend
| Arquivo | Status | Descrição |
|--------|--------|-----------|
| `backend/app/routers/ia_unificado.py` | ✅ Criado | Router consolidado de IA |
| `backend/app/main.py` | ⏳ Pendente | Registrar novo router |

### Frontend
| Arquivo | Status | Descrição |
|--------|--------|-----------|
| `frontend/src/components/IAPanel.tsx` | ✅ Criado | Painel unificado de IA |
| `frontend/src/pages/CasoDetalhe.tsx` | ⏳ Pendente | Integrar IAPanel |

---

## 8. PRÓXIMOS PASSOS IMEDIATOS

1. **Registrar router no main.py:**
```python
from app.routers import ia_unificado
app.include_router(ia_unificado.router, prefix=API)
```

2. **Integrar IAPanel no CasoDetalhe:**
```tsx
import { IAPanel } from '../components/IAPanel';

// Adicionar botão que abre o painel
<button onClick={() => setShowIAPanel(true)}>
  🤖 Assistente IA
</button>

{showIAPanel && <IAPanel casoId={casoId} onClose={() => setShowIAPanel(false)} />}
```

3. **Testar health check:**
```bash
curl http://localhost:8000/api/ia/health
```

---

**Documento criado:** $(date +%Y-%m-%d)  
**Responsável:** Equipe de Desenvolvimento EJC  
**Próxima revisão:** 7 dias
