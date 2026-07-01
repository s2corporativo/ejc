# Serviço interno de embeddings do EJC.
# Roda em container separado, sem porta pública, para manter o backend principal leve.
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.services.embedding_service import EMBED_DIM, MODEL_NAME, disponivel, gerar_embeddings

app = FastAPI(title="EJC Embeddings Service", version="1.0.0")


class EmbedRequest(BaseModel):
    textos: list[str] = Field(..., min_length=1, max_length=64)
    modo: str = Field("passage", pattern="^(passage|query)$")


@app.get("/health")
async def health():
    return {
        "status": "ok" if disponivel() else "degraded",
        "modelo": MODEL_NAME,
        "dimensao": EMBED_DIM,
        "provider": "local",
    }


@app.post("/embed")
async def embed(req: EmbedRequest):
    vetores = await gerar_embeddings(req.textos, modo=req.modo)
    if not vetores:
        raise HTTPException(503, "Embeddings indisponíveis")
    return {
        "modelo": MODEL_NAME,
        "dimensao": EMBED_DIM,
        "quantidade": len(vetores),
        "embeddings": vetores,
    }
