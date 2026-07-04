# ── app/services/citation_gate.py ────────────────────────────────────────────
"""
citation_gate.py — Gate antialucinação de citações jurídicas (Fase 4).

Camada de POLÍTICA sobre o verificador rigoroso já existente
(verificador_jurisprudencia.py, que extrai/classifica citações como
verificada/identificada/suspeita/generica contra a base RAG oficial +
validação estrutural CNJ/súmula). Este módulo NÃO re-extrai nada — apenas:

  1. Decide, conforme `settings.CITACOES_POLITICA` ("bloquear"|"marcar"|
     "desligado", default "marcar"), se o output de IA pode ser APROVADO
     no fluxo HITL (PATCH /ai/logs/{id}/hitl) sem override do revisor.
  2. Define o que é citação BLOQUEANTE (indício forte de alucinação):
       • status `suspeita`   — formato/faixa estruturalmente inválidos
         (DV CNJ errado, súmula fora de faixa, tribunal inexistente);
       • status `generica`   — menção vaga sem referência verificável;
       • status `identificada` de JULGADO (processo_cnj/recurso) sem
         tribunal E data no contexto — "ementas/julgados devem ter
         processo+tribunal+data verificáveis" (objetivo da Fase 4).
     Citações `identificada` COM referência completa (ex.: REsp com nº,
     tribunal e data de julgamento) não bloqueiam: são plausíveis e a
     confirmação de inteiro teor é responsabilidade do revisor (OAB) —
     bloquear todo julgado não confirmável externamente inviabilizaria o
     HITL, já que a base local só confirma súmulas/artigos por lookup exato.
  3. Expõe `validar_citacoes(db, texto) -> RelatorioCitacoes` (validação sob
     demanda via POST /ia/validar-citacoes e gate do HITL).

100% local e determinístico (sem LLM, sem rede externa) — por isso o
relatório pode ser RECOMPUTADO a qualquer momento a partir do texto
(GET /ai/logs/{id}/citacoes), sem precisar de coluna nova no AILog.
"""
from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("ejc.citation_gate")

POLITICA_BLOQUEAR = "bloquear"
POLITICA_MARCAR = "marcar"
POLITICA_DESLIGADO = "desligado"
_POLITICAS_VALIDAS = {POLITICA_BLOQUEAR, POLITICA_MARCAR, POLITICA_DESLIGADO}

# Tipos de citação que referenciam JULGADO (exigem tribunal+data verificáveis).
_TIPOS_JULGADO = {"processo_cnj", "recurso"}


def politica_citacoes() -> str:
    """Política vigente, normalizada; valor inválido cai no default 'marcar'."""
    val = (get_settings().CITACOES_POLITICA or "").strip().lower()
    if val not in _POLITICAS_VALIDAS:
        logger.warning("CITACOES_POLITICA inválida (%r) — usando 'marcar'.", val)
        return POLITICA_MARCAR
    return val


class CitacaoBloqueante(BaseModel):
    citacao: str
    tipo: str
    status: str
    motivo: str


class RelatorioCitacoes(BaseModel):
    """Resultado do gate: relatório completo + decisão de política."""
    politica: str
    total: int = 0
    verificadas: int = 0
    # NÃO confirmadas na base oficial (identificada + suspeita + generica).
    nao_verificadas: int = 0
    score: int | None = None
    bloqueia_aprovacao: bool = False
    bloqueantes: list[CitacaoBloqueante] = Field(default_factory=list)
    motivos: list[str] = Field(default_factory=list)
    # Relatório integral do verificador rigoroso (shape de
    # verificar_jurisprudencia); None quando politica == "desligado".
    relatorio: dict | None = None


def avaliar_bloqueantes(relatorio: dict) -> list[dict]:
    """Citações do relatório que impedem aprovação na política 'bloquear'.

    Retorna dicts {citacao, tipo, status, motivo} (ver critérios no docstring
    do módulo). Função pura/síncrona para reuso no response_validator.
    """
    bloqueantes: list[dict] = []
    for c in relatorio.get("citacoes") or []:
        status, tipo = c.get("status"), c.get("tipo")
        motivo: str | None = None
        if status == "suspeita":
            motivo = c.get("aviso") or "formato/faixa estruturalmente inválidos"
        elif status == "generica":
            motivo = ("menção genérica a jurisprudência sem referência "
                      "verificável (processo, tribunal, órgão e data)")
        elif status == "identificada" and tipo in _TIPOS_JULGADO:
            faltas = [n for n, v in (("tribunal", c.get("tribunal")),
                                     ("data", c.get("data"))) if not v]
            if faltas:
                motivo = ("julgado citado sem " + " e ".join(faltas) +
                          " verificáveis no contexto — exija processo, "
                          "tribunal e data de julgamento/publicação")
        if motivo:
            bloqueantes.append({
                "citacao": c.get("citacao") or c.get("trecho") or "",
                "tipo": tipo or "desconhecido",
                "status": status or "desconhecido",
                "motivo": motivo,
            })
    return bloqueantes


async def validar_citacoes(
    db, texto: str, *, politica: str | None = None,
) -> RelatorioCitacoes:
    """Valida as citações de um texto gerado por IA e aplica a política.

    - `db`: sessão async (lookup de súmulas/artigos na base RAG oficial).
    - `politica`: override explícito; default = settings.CITACOES_POLITICA.

    `bloqueia_aprovacao` só é True na política "bloquear" E havendo citação
    bloqueante; em "marcar" os bloqueantes são listados (para o revisor),
    mas não impedem aprovação; em "desligado" nada é verificado.
    """
    pol = (politica or "").strip().lower() or politica_citacoes()
    if pol not in _POLITICAS_VALIDAS:
        pol = politica_citacoes()

    if pol == POLITICA_DESLIGADO:
        return RelatorioCitacoes(
            politica=pol,
            motivos=["Verificação de citações desligada (CITACOES_POLITICA)."],
        )

    from app.services.verificador_jurisprudencia import verificar_jurisprudencia
    rel = await verificar_jurisprudencia(db, texto)

    bloqueantes = [CitacaoBloqueante(**b) for b in avaliar_bloqueantes(rel)]
    motivos: list[str] = []
    if bloqueantes:
        motivos.append(
            f"{len(bloqueantes)} citação(ões) bloqueante(s): possível alucinação "
            "ou julgado sem tribunal+data verificáveis."
        )
    if rel["nao_encontradas"]:
        motivos.append(
            f"{rel['nao_encontradas']} citação(ões) não confirmada(s) na base "
            "oficial interna — confirme o inteiro teor antes do protocolo."
        )

    return RelatorioCitacoes(
        politica=pol,
        total=rel["total"],
        verificadas=rel["confirmadas"],
        nao_verificadas=rel["nao_encontradas"],
        score=rel.get("score"),
        bloqueia_aprovacao=pol == POLITICA_BLOQUEAR and bool(bloqueantes),
        bloqueantes=bloqueantes,
        motivos=motivos,
        relatorio=rel,
    )
