---
name: gestor-rag-ia-juridica
description: >
  Plan, configure, and manage the internal legal AI system with RAG (Retrieval-Augmented Generation) for a Brazilian law firm using Ollama for local LLM, LangChain or LlamaIndex for orchestration, pgvector for semantic search, and sentence-transformers for embeddings. Use whenever the user needs to: plan or review the RAG architecture for EJC; configure Ollama with a legal model (llama3, mistral, sabia, phi3); set up pgvector in PostgreSQL; design the knowledge base curation flow (which documents enter RAG, confidence level); plan AI logs and mandatory human review; understand AI limits in legal context; or configure the AI module in EJC. AI never replaces the lawyer. All output is draft requiring review. No automated advice to external parties. Trigger on: RAG juridico, IA interna, Ollama configurar, pgvector, embeddings, base conhecimento IA, curadoria RAG, modelo local LLM, LangChain, busca semantica, IA no EJC, modelo llama, sabia juridico, IA sem API paga.
---

# Gestor de RAG e IA Jurídica Interna — EJC

## Premissas Absolutas

- IA não substitui o advogado — nunca
- IA não gera peça final — gera rascunho marcado para revisão humana
- IA não promete resultado — nunca
- IA não responde consulta jurídica para cliente externo como definitiva
- Todo uso de IA registrado no audit log
- Documento não revisado não alimenta RAG sem marcação de baixa confiança
- Rascunho de IA tem peso menor que modelo aprovado por advogado
- Aviso de uso de IA deve ser visível para o usuário interno

---

## 1. Arquitetura RAG para o EJC

### Visão Geral

```
FLUXO COMPLETO:

Documento entra no EJC
      ↓
Classificação humana (tipo, área, confiança)
      ↓
Aprovação para RAG (advogado/sócio)
      ↓
Processamento: text splitting → embeddings (sentence-transformers)
      ↓
Armazenamento: pgvector (PostgreSQL)
      ↓
Query do advogado
      ↓
Busca semântica (pgvector) → recupera chunks relevantes
      ↓
LLM local (Ollama) + contexto recuperado → gera resposta
      ↓
Resposta marcada como "rascunho IA" → revisão humana obrigatória
      ↓
Log registrado (quem, quando, modelo, caso, revisado por)
```

### Componentes

```
COMPONENTE          | TECNOLOGIA              | STATUS NO EJC
LLM local           | Ollama                  | Preparado para fase futura
Orquestração RAG    | LangChain ou LlamaIndex | Preparado para fase futura
Busca semântica     | pgvector (PostgreSQL)   | Extensão a habilitar
Embeddings          | sentence-transformers   | Preparado para fase futura
Base de documentos  | PostgreSQL + storage    | Ativo (curadoria manual agora)
Logs de IA          | audit_logs EJC          | Ativo (estrutura pronta)
Revisão humana      | EJC workflow            | Ativo
```

---

## 2. Ollama — Configuração Local

### Instalação

```bash
# Linux (VPS Ubuntu ou local)
curl -fsSL https://ollama.com/install.sh | sh

# Verificar instalação
ollama --version

# Iniciar serviço
ollama serve

# Testar
curl http://localhost:11434/api/generate -d '{
  "model": "llama3",
  "prompt": "Olá",
  "stream": false
}'
```

### Modelos Recomendados para Jurídico PT-BR

```
OPÇÕES AVALIADAS:

1. llama3 (Meta) — 8B parâmetros
   + Excelente em português
   + Bom raciocínio jurídico
   - Necessita ~8GB RAM
   Comando: ollama pull llama3

2. mistral (Mistral AI) — 7B parâmetros
   + Rápido e eficiente
   + Bom em seguir instruções
   - Português um pouco inferior ao llama3
   Comando: ollama pull mistral

3. sabia-3 (Maritaca AI) — modelo brasileiro
   + Treinado especificamente em português
   + Melhor para textos jurídicos PT-BR
   - Verificar disponibilidade no Ollama
   Comando: ollama pull maritaca-ai/sabia-3 (verificar nome atual)

4. phi3 (Microsoft) — 3.8B parâmetros
   + Muito leve (roda em máquina modesta)
   + Surpreendentemente bom
   - Menos capaz que llama3 em textos longos
   Comando: ollama pull phi3

RECOMENDAÇÃO PARA EJC:
- Hardware limitado (<16GB RAM): phi3 ou mistral
- Hardware médio (16-32GB RAM): llama3
- Hardware robusto (>32GB RAM): llama3:70b ou sabia-3

REQUISITOS MÍNIMOS:
- llama3 (8B): 8GB RAM livres + SSD (modelo ~5GB)
- mistral (7B): 8GB RAM livres + SSD
- phi3 (3.8B): 4GB RAM livres + SSD
```

### Configuração no EJC

```python
# config/ai_config.py
import os

AI_CONFIG = {
    "enabled": os.getenv("AI_ENABLED", "false").lower() == "true",
    "ollama_url": os.getenv("OLLAMA_URL", "http://localhost:11434"),
    "default_model": os.getenv("AI_MODEL", "llama3"),
    "max_tokens": int(os.getenv("AI_MAX_TOKENS", "2000")),
    "temperature": float(os.getenv("AI_TEMPERATURE", "0.1")),  # baixo = mais conservador
    "timeout_seconds": int(os.getenv("AI_TIMEOUT", "60")),
}

# .env
AI_ENABLED=false  # false até habilitar explicitamente
OLLAMA_URL=http://ollama:11434  # se Ollama em container Docker
AI_MODEL=llama3
AI_MAX_TOKENS=2000
AI_TEMPERATURE=0.1  # conservador para jurídico
```

---

## 3. pgvector — Busca Semântica

### Habilitar no PostgreSQL

```sql
-- Habilitar extensão (PostgreSQL 14+ com pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela de embeddings para documentos
CREATE TABLE document_embeddings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    chunk_index INTEGER,
    chunk_text TEXT,
    embedding vector(384),  -- 384 para all-MiniLM-L6-v2
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Índice para busca rápida
CREATE INDEX ON document_embeddings
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Query de busca semântica
SELECT d.chunk_text, d.metadata,
       1 - (d.embedding <=> $1::vector) AS similarity
FROM document_embeddings d
WHERE 1 - (d.embedding <=> $1::vector) > 0.7
ORDER BY d.embedding <=> $1::vector
LIMIT 5;
```

### Docker — Adicionar pgvector

```yaml
# docker-compose.yml — usar imagem com pgvector
services:
  db:
    image: pgvector/pgvector:pg15  # ao invés de postgres:15-alpine
    # resto igual
```

---

## 4. Pipeline de Curadoria da Base RAG

### Fluxo de Aprovação

```
STATUS DO DOCUMENTO PARA RAG:

pendente_classificacao
    → classificado (tipo + área + confiança definidos)
        → em_revisao_humana
            → aprovado_para_rag (confiança: alta/média/baixa)
            → recusado_para_rag (motivo registrado)
                → disponivel (embeddings gerados)
```

### Níveis de Confiança

```
🟢 ALTA CONFIANÇA — peso máximo nas respostas:
- Modelo de peça aprovado por sócio
- Peça revisada e protocolada
- Jurisprudência com link oficial + número completo
- Norma confirmada com link planalto.gov.br
- Tese aprovada por revisão do coordenador

🟡 MÉDIA CONFIANÇA — usar com aviso:
- Tese aprovada por advogado (sem revisão do sócio)
- Jurisprudência com número mas sem link verificado
- Norma confirmada mas sem data de verificação recente
- Modelo de peça não revisado recentemente

🔴 BAIXA CONFIANÇA — rascunho / referência apenas:
- Rascunho gerado por IA (nunca aprovado)
- Documento importado sem revisão humana
- Jurisprudência sem número completo
- Norma com status "possivelmente alterado"

⚫ BLOQUEADO — não entra no RAG:
- Documentos de clientes (dados pessoais — LGPD)
- Documentos confidenciais / segredo de justiça
- Documentos com dados sensíveis não anonimizados
- Documentos rejeitados na curadoria
```

### Tabela rag_documents

```sql
CREATE TABLE rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id),
    source_type VARCHAR(50),  -- modelo / peca / jurisprudencia / tese / norma / doutrina
    confidence_level VARCHAR(20),  -- alta / media / baixa
    rag_status VARCHAR(30),  -- pendente / aprovado / recusado / disponivel
    approved_by UUID REFERENCES users(id),
    approved_at TIMESTAMP,
    rejection_reason TEXT,
    area VARCHAR(50),
    tema VARCHAR(100),
    embeddings_generated BOOLEAN DEFAULT FALSE,
    embeddings_generated_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

## 5. System Prompt Jurídico (Base para LLM)

```python
LEGAL_SYSTEM_PROMPT = """
Você é um assistente jurídico interno do escritório de advocacia.

REGRAS ABSOLUTAS:
1. Você auxilia advogados — NÃO substitui o advogado
2. Suas respostas são RASCUNHOS que exigem revisão humana
3. NUNCA prometa resultado ou afirme que a causa será ganha
4. NUNCA afirme que uma norma está vigente sem fonte oficial
5. Se não tiver certeza: diga "verificar com fonte oficial"
6. Cite sempre a base legal (lei + artigo) quando aplicável
7. Indique o nível de confiança da sua resposta
8. Marque jurisprudência inventada como PENDENTE DE VERIFICAÇÃO

FORMATO DE RESPOSTA:
- Responda em português brasileiro
- Use linguagem técnica jurídica adequada
- Organize com tópicos quando pertinente
- Ao final, indique: "⚠️ RASCUNHO — Revisão humana obrigatória antes de qualquer uso oficial"

LIMITAÇÕES ÉTICAS:
- Não responda consultas de clientes externos diretamente
- Não gere peça final — apenas rascunho para revisão
- Não tome decisões estratégicas — apenas analise opções
- Não confirme prazos sem verificação humana
"""
```

---

## 6. Log de Uso de IA (Obrigatório)

```sql
CREATE TABLE ai_usage_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    case_id UUID REFERENCES cases(id),
    document_id UUID,  -- se gerou documento
    action VARCHAR(50),  -- pesquisa / rascunho / revisao / resumo
    model_used VARCHAR(100),
    prompt_summary TEXT,  -- resumo do que foi pedido (não o prompt completo)
    output_summary TEXT,  -- resumo do que foi gerado
    output_marked_as_draft BOOLEAN DEFAULT TRUE,
    reviewed_by UUID REFERENCES users(id),
    reviewed_at TIMESTAMP,
    review_result VARCHAR(30),  -- aprovado / corrigido / rejeitado
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 7. Status do Módulo IA no EJC (Dashboard)

```
STATUS DA IA INTERNA:

Ollama: ⚪ EM DESENVOLVIMENTO
pgvector: ⚪ EM DESENVOLVIMENTO
Base RAG: 🟡 ESTRUTURA PREPARADA (curadoria manual ativa)
Logs de IA: ✅ ATIVO
Revisão humana: ✅ ATIVO

DOCUMENTOS NA BASE:
Aprovados para RAG: [N]
Pendentes de revisão: [N]
Recusados: [N]
Alta confiança: [N]

PRÓXIMOS PASSOS PARA ATIVAR IA:
1. Instalar Ollama no servidor
2. Fazer pull do modelo escolhido
3. Habilitar pgvector no PostgreSQL
4. Rodar script de geração de embeddings
5. Configurar AI_ENABLED=true no .env
6. Testar com 5-10 queries controladas
7. Validar respostas com advogado antes de liberar para a equipe
```

---

## Acionamento

Frases que ativam este skill:
- "RAG jurídico", "IA interna"
- "Ollama configurar", "modelo local LLM"
- "pgvector", "embeddings jurídicos"
- "base de conhecimento IA", "curadoria RAG"
- "LangChain jurídico", "busca semântica"
- "IA no EJC", "configurar IA"
- "modelo llama", "sabia jurídico"
- "IA sem API paga", "IA local"
- "revisão humana IA", "log de uso IA"
- Quando usuário quer planejar ou implementar IA no sistema jurídico
- Quando usuário pergunta qual modelo usar para jurídico em PT-BR
