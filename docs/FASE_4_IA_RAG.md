# FASE 4 — IA LOCAL + RAG JURÍDICO (Instruções para Claude Code)

Este documento contém as instruções exatas para a implantação da infraestrutura de IA Soberana no EJC v4.0.

## 1. DOCKER OLLAMA SETUP
Adicione o serviço abaixo ao seu `docker-compose.yml`:

```yaml
services:
  ollama:
    image: ollama/ollama:latest
    container_name: ejc_ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - backend_ejc_net
    environment:
      - OLLAMA_HOST=0.0.0.0:11434
    restart: always

volumes:
  ollama_data:
```

**Comando para start:** `docker compose up ollama -d`

## 2. PUXAR MODELOS OLLAMA
Execute os comandos abaixo na VPS para baixar os modelos:

1. `docker exec -it ejc_ollama ollama pull qwen2.5:3b` (Principal - ~2.3GB)
2. `docker exec -it ejc_ollama ollama pull deepseek-r1:7b` (Reasoning - ~4.7GB)
3. `docker exec -it ejc_ollama ollama pull gemma2:2b` (Lightweight - ~1.6GB)
4. `docker exec -it ejc_ollama ollama pull llama3:8b` (Fallback - ~4.7GB)

**Listar modelos:** `docker exec -it ejc_ollama ollama list`

## 3. EMBEDDINGS SERVICE (BGE-M3)
Refatore o arquivo `backend/app/modules/rag/embeddings_service.py`:

```python
from sentence_transformers import SentenceTransformer
import torch

class EmbeddingsService:
    def __init__(self):
        # Prioridade BGE-M3 (Melhor para jurídico brasileiro)
        try:
            self.model = SentenceTransformer('BAAI/bge-m3')
        except:
            self.model = SentenceTransformer('intfloat/multilingual-e5-base')

    def embed_documento(self, texto: str):
        # Chunking: 512 tokens com overlap 50
        chunks = self._chunk_text(texto, 512, 50)
        return [self.model.encode(c).tolist() for c in chunks]

    def _chunk_text(self, text, size, overlap):
        return [text[i:i+size] for i in range(0, len(text), size-overlap)]
```

## 4. RAG INTEGRADO AO NÚCLEO COGNITIVO
Arquivo: `backend/app/modules/nuclei_cognitivo/rag_service.py` (NOVO)

```python
from app.modules.rag.embeddings_service import EmbeddingsService
from app.core.ai_brain import ai_gateway

class NucleoCognitivoRAGService:
    async def analisar_com_rag(self, prompt, contexto, tenant_id):
        # 1. Busca semântica de precedentes e teses
        docs = await self.buscar_docs_relevantes(prompt, tenant_id)

        # 2. Enriquecimento do prompt
        prompt_enriquecido = f"BASE DE CONHECIMENTO:\n{docs}\n\nPROMPT:\n{prompt}\n\nCONTEXTO:\n{contexto}"

        # 3. Chamada ao AI Gateway
        return await ai_gateway.processar_demanda(prompt_enriquecido, tipo="juridico_profundo")
```

## 5. AI GATEWAY COM FALLBACK
Refatore `backend/app/core/ai_brain.py` para incluir o fallback:

```python
async def processar_com_fallback(self, prompt, tipo):
    # 1. Tenta Ollama (Local)
    res = await self._call_ollama(self.models[tipo], prompt)
    if "Erro" not in res:
        return res

    # 2. Fallback: Claude (Opcional)
    # return await self._call_claude(prompt)

    return "Falha em todos os modelos de IA."
```

## 6. VETORIZAR DOCUMENTOS EXISTENTES
Script: `backend/scripts/vectorize_documents.py`

```python
import asyncio
from app.services.rag_juridico import RAGService

async def main():
    rag = RAGService()
    print("Iniciando vetorização de massa documental...")
    # Lógica de loop sobre documentos do banco
    print("Vetorização concluída com sucesso.")

if __name__ == "__main__":
    asyncio.run(main())
```

## 7. CHECKLIST DE VALIDAÇÃO
- [ ] Ollama rodando na porta 11434
- [ ] Modelos Qwen e DeepSeek listados no `ollama list`
- [ ] Teste de busca semântica retorna similaridade > 0.6
- [ ] Fallback automático funcionando ao desligar o container Ollama
- [ ] Isolamento por Tenant garantido na busca pgvector
