"""
Veredito IA — probabilidade de êxito baseada em JURIMETRIA REAL.

Honestidade estatística (mesmo contrato de app/services/jurimetria.py):
- A probabilidade vem da taxa de êxito histórica dos casos ENCERRADOS do
  escritório na área informada. Se a amostra for menor que MIN_AMOSTRA,
  retorna probabilidade_exito=None com aviso explícito — nunca um número
  inventado.
- A jurisprudência de suporte vem da busca RAG real (pgvector), não de mock.
"""
import logging
from typing import List, Optional

from sqlalchemy import String, cast, func, select

from app.core.database import AsyncSessionLocal
from app.core.victory_vault import VictoryVault
from app.models.case import Case
from app.schemas.veredito_ia_schema import (
    AnaliseTeseResponse,
    JurisprudenciaSuporte,
    SugestaoContextualizada,
    TeseVitoriosaSimilar,
)
from app.services.jurimetria import FECHADOS, MIN_AMOSTRA, _bucket, _resumo

logger = logging.getLogger("ejc.veredito_ia")


class VereditoIA:
    def __init__(self):
        self.victory_vault = VictoryVault()

    async def predict_success(
        self, tese_juridica: str, area_juridica: str, tribunais_selecionados: List[str]
    ) -> AnaliseTeseResponse:
        # 1) Probabilidade via jurimetria REAL (casos encerrados com resultado).
        resumo = await self._amostra_resultados(area_juridica)
        if resumo["amostra_suficiente"] and resumo["taxa_exito_com_acordo"] is not None:
            probabilidade: Optional[float] = round(
                resumo["taxa_exito_com_acordo"] / 100.0, 3
            )
            aviso = None
        else:
            probabilidade = None
            aviso = (
                f"Amostra insuficiente: {resumo['n']} caso(s) encerrado(s) com "
                f"resultado na área '{area_juridica}' (mínimo {MIN_AMOSTRA}). "
                "Sem base estatística para estimar probabilidade de êxito."
            )

        # 2) Teses vitoriosas similares (Victory Vault — persistência real).
        teses_vitoriosas = await self.victory_vault.get_teses_vitoriosas(
            area_juridica=area_juridica, query=tese_juridica
        )

        # 3) Jurisprudência de suporte via RAG real (pgvector/textual).
        jurisprudencia_suporte = await self._buscar_jurisprudencia(tese_juridica)

        sugestoes = self._generate_suggestions(probabilidade, teses_vitoriosas)

        return AnaliseTeseResponse(
            probabilidade_exito=probabilidade,
            aviso=aviso,
            amostra=resumo,
            teses_vitoriosas_similares=teses_vitoriosas,
            jurisprudencia_suporte=jurisprudencia_suporte,
            sugestoes_contextualizadas=sugestoes,
        )

    async def _amostra_resultados(self, area_juridica: str) -> dict:
        """Distribuição de resultados dos casos encerrados na área (jurimetria)."""
        try:
            async with AsyncSessionLocal() as db:
                q = select(Case.resultado).where(
                    Case.deleted_at.is_(None),
                    Case.status.in_(FECHADOS),
                    Case.resultado.isnot(None),
                    func.lower(cast(Case.area, String))
                    == (area_juridica or "").strip().lower(),
                )
                linhas = (await db.execute(q)).scalars().all()
            return _resumo([_bucket(r) for r in linhas])
        except Exception as e:
            logger.warning(f"[veredito_ia] jurimetria indisponível: {e}")
            return _resumo([])

    async def _buscar_jurisprudencia(
        self, tese_juridica: str, limite: int = 5
    ) -> List[JurisprudenciaSuporte]:
        """Busca RAG real na base de conhecimento (sem mock)."""
        try:
            from app.services.ai_service import buscar_contexto_rag

            async with AsyncSessionLocal() as db:
                chunks = await buscar_contexto_rag(
                    db, tese_juridica, limite=limite, modo_or=True
                )
        except Exception as e:
            logger.warning(f"[veredito_ia] busca RAG falhou: {e}")
            return []
        return [
            JurisprudenciaSuporte(
                id=str(c.get("chunk_id", "")),
                ementa=(c.get("conteudo") or "")[:1000],
                tribunal=c.get("fonte") or c.get("categoria") or "base interna",
                data="",
                link=None,
            )
            for c in chunks
        ]

    def _generate_suggestions(
        self,
        probabilidade: Optional[float],
        teses_vitoriosas: List[TeseVitoriosaSimilar],
    ) -> List[SugestaoContextualizada]:
        sugestoes: List[SugestaoContextualizada] = []
        if probabilidade is None:
            sugestoes.append(SugestaoContextualizada(
                tipo="Estatística",
                descricao=(
                    "Sem histórico suficiente na área — registre resultados dos "
                    "casos encerrados para habilitar a jurimetria."
                ),
            ))
        if teses_vitoriosas:
            sugestoes.append(SugestaoContextualizada(
                tipo="Melhoria",
                descricao="Revise a argumentação com base nas teses vitoriosas similares.",
            ))
        else:
            sugestoes.append(SugestaoContextualizada(
                tipo="Pesquisa",
                descricao="Nenhuma tese vitoriosa similar registrada — pesquise e cadastre no Victory Vault.",
            ))
        return sugestoes
