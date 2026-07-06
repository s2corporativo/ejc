"""
RAG Jurídico — EJC Intelligence v3.0
Implementa busca semântica, ingestão de DataJud/Jurisprudências.ai e Match de Casos.
"""
import logging
from fastapi import HTTPException
from app.core.ai_brain import ai_brain
from app.core.public_apis import api_client

logger = logging.getLogger("rag_juridico")

class RAGJuridico:
    def __init__(self):
        self.ai = ai_brain
        self.apis = api_client

    async def ingestao_jurisprudencia(self, tribunal: str, tema: str):
        """
        Ingestão via Jurisprudências.ai (STF, STJ, TJMG).

        Status HONESTO: a conexão com a fonte externa ainda não foi
        implementada e não há fila (Celery/RQ) enfileirando nada aqui. Antes
        esta função respondia {"status": "Ingestão em fila"}, sugerindo um
        processamento que nunca acontecia. A ingestão real e verificável de
        conhecimento no RAG passa por app/routers/rag.py (/rag/ingest,
        /rag/ingest-pdf, /rag/ingest-url) + ingestion_service.
        """
        logger.info(
            "ingestao_jurisprudencia chamada (não implementada) — tribunal=%s tema=%s",
            tribunal, tema,
        )
        return {
            "status": "nao_implementado",
            "tribunal": tribunal,
            "tema": tema,
            "detail": (
                "Ingestão automática de Jurisprudências.ai ainda não implementada "
                "e sem fila. Use os endpoints /rag/ingest* para ingestão verificável."
            ),
        }

    async def match_de_casos(self, texto_caso: str, area: str):
        """
        Match de Casos com base na jurisprudência.

        DESABILITADO por segurança jurídica: a implementação anterior pedia
        julgados/decisões ao LLM SEM grounding RAG (sem recuperar trechos com
        fonte da base vetorial e sem passar pelo citation_gate), o que produzia
        acórdãos e números de processo ALUCINADOS entregues como reais.

        O caminho seguro (busca vetorial em knowledge_chunks + verificação de
        citações) exige sessão de banco, que este ponto não recebe. Em vez de
        gerar conteúdo não verificado, retornamos 501 e direcionamos o usuário
        aos fluxos com fontes citadas verificadas (busca RAG e veredito de IA).
        """
        raise HTTPException(
            status_code=501,
            detail=(
                "Match de Casos indisponível: a geração sem grounding RAG foi "
                "desativada para evitar julgados/números de processo alucinados. "
                "Use /rag/buscar (base de conhecimento com fontes) ou o veredito "
                "de IA, que anexam apenas citações verificadas."
            ),
        )

rag_juridico = RAGJuridico()
