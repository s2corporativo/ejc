# ── app/services/citation_gate.py ────────────────────────────────────────────
"""
citation_gate.py — Gate antialucinação de citações jurídicas (Fase 4).

Camada de POLÍTICA sobre o verificador rigoroso já existente
(verificador_jurisprudencia.py, que extrai/classifica citações como
verificada/identificada/suspeita/generica contra a base RAG oficial +
validação estrutural CNJ/súmula).

P0.1 — VIGÊNCIA JURÍDICA:
Para ARTIGOS de lei, a aprovação passa a exigir confirmação positiva na base
legislativa apta a fundamentar direito atual. Um artigo `identificada` (não
confirmado após o gate de vigência) ou `possivelmente_desatualizada` bloqueia a
aprovação mesmo com CITACOES_MODO_ESTRITO desligado. Isso é deliberadamente
fail-closed: ausência de corpus/curadoria não autoriza tratar norma como vigente.
O revisor humano ainda pode usar o override auditável já existente, após
confirmar a fonte oficial.

DIMENSÃO 2 — PERTINÊNCIA (opt-in, PERTINENCIA_ENABLED, default OFF):
Tudo acima responde se a citação EXISTE. Não responde se ela SUSTENTA a
afirmação que acompanha — o erro que passa por todos os gates e chega ao juiz
(art. 373, I do CPC citado para inversão do ônus da prova: existe, vigente,
diploma certo, e diz o oposto). Com a flag ligada, cada citação `verificada`
de tipo cujo texto está na base curada é confrontada contra a afirmação; ver
`services/ai/pertinencia.py` para a conferência antialucinação.

O núcleo de EXISTÊNCIA continua 100% local e determinístico (sem LLM, sem rede
externa) — a dimensão de pertinência é a única parte que usa IA, é opt-in, e
pode ser dispensada por chamada (`verificar_pertinencia=False`) para quem
depende dessa garantia.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("ejc.citation_gate")

POLITICA_BLOQUEAR = "bloquear"
POLITICA_MARCAR = "marcar"
POLITICA_DESLIGADO = "desligado"
_POLITICAS_VALIDAS = {POLITICA_BLOQUEAR, POLITICA_MARCAR, POLITICA_DESLIGADO}

_TIPOS_JULGADO = {"processo_cnj", "recurso"}
_TIPOS_CONFIRMAVEIS_BASE = {"sumula", "artigo"}

MAX_CITACOES_POR_VERIFICACAO = 200
JUSTIFICATIVA_OVERRIDE_MIN = 10
JUSTIFICATIVA_OVERRIDE_MAX = 500
MARCADOR_OVERRIDE = "[override_citacoes]"


def politica_citacoes() -> str:
    """Política vigente, normalizada; valor inválido cai em bloquear."""
    val = (get_settings().CITACOES_POLITICA or "").strip().lower()
    if val not in _POLITICAS_VALIDAS:
        logger.warning(
            "CITACOES_POLITICA inválida (%r) — usando 'bloquear' (fail-secure).",
            val,
        )
        return POLITICA_BLOQUEAR
    return val


def modo_estrito_citacoes() -> bool:
    """Modo estrito geral do gate (súmulas/artigos ausentes da base).

    P0.1 tornou ARTIGOS uma exceção mais segura: artigo não confirmado em
    legislação vigente bloqueia independentemente desta flag. A flag continua
    governando a política adicional das súmulas e demais cenários legados.
    """
    return bool(get_settings().CITACOES_MODO_ESTRITO)


class CitacaoBloqueante(BaseModel):
    citacao: str
    tipo: str
    status: str
    motivo: str


class RelatorioCitacoes(BaseModel):
    politica: str
    total: int = 0
    verificadas: int = 0
    nao_verificadas: int = 0
    score: int | None = None
    bloqueia_aprovacao: bool = False
    verificacao_parcial: bool = False
    bloqueantes: list[CitacaoBloqueante] = Field(default_factory=list)
    motivos: list[str] = Field(default_factory=list)
    relatorio: dict | None = None
    # Segunda dimensão do gate (opt-in, PERTINENCIA_ENABLED): a autoridade
    # citada SUSTENTA a afirmação? Existência e pertinência são perguntas
    # diferentes — uma citação pode existir, estar vigente, vir do diploma
    # certo e ainda assim não amparar o que a peça afirma. `None` = dimensão
    # desligada, que é diferente de "verificada e sem achados".
    pertinencia: dict | None = None


def avaliar_bloqueantes(
    relatorio: dict, *, modo_estrito: bool | None = None,
) -> list[dict]:
    """Retorna citações que impedem aprovação na política `bloquear`.

    Regra P0.1: ARTIGO só é apto quando o verificador o confirma (`verificada`)
    contra a legislação que passou pelo gate de vigência. Portanto
    `identificada` e `possivelmente_desatualizada` para tipo `artigo` são
    sempre bloqueantes. Isso não muda o tratamento de julgados ou súmulas.
    """
    if modo_estrito is None:
        modo_estrito = modo_estrito_citacoes()
    bloqueantes: list[dict] = []
    for c in relatorio.get("citacoes") or []:
        status, tipo = c.get("status"), c.get("tipo")
        motivo: str | None = None
        if status == "suspeita":
            motivo = c.get("aviso") or "formato/faixa estruturalmente inválidos"
        elif status == "generica":
            motivo = ("menção genérica a jurisprudência sem referência "
                      "verificável (processo, tribunal, órgão e data)")
        elif status == "identificada" and tipo == "artigo":
            motivo = (
                "Artigo citado não foi confirmado em legislação com vigência "
                "jurídica apta na base curada. Confirme a redação vigente na "
                "fonte oficial ou remova a citação antes da aprovação."
            )
        elif status == "possivelmente_desatualizada" and tipo == "artigo":
            motivo = (
                "Artigo localizado apenas em versão/situação não apta para "
                "fundamentação atual. Confirme a redação vigente na fonte "
                "oficial antes da aprovação."
            )
        elif status == "identificada" and tipo in _TIPOS_JULGADO:
            faltas = [n for n, v in (("tribunal", c.get("tribunal")),
                                     ("data", c.get("data"))) if not v]
            if faltas:
                motivo = ("julgado citado sem " + " e ".join(faltas) +
                          " verificáveis no contexto — exija processo, "
                          "tribunal e data de julgamento/publicação")
        elif (modo_estrito and status == "identificada"
              and tipo in _TIPOS_CONFIRMAVEIS_BASE):
            rotulo = "Súmula" if tipo == "sumula" else "Artigo"
            motivo = (f"{rotulo} citado(a) não encontrado(a) na base curada — "
                      "modo estrito (CITACOES_MODO_ESTRITO): confirme a "
                      "existência na fonte oficial ou remova a citação.")
        elif (modo_estrito and status == "possivelmente_desatualizada"
              and tipo in _TIPOS_CONFIRMAVEIS_BASE):
            rotulo = "Súmula" if tipo == "sumula" else "Artigo"
            motivo = (f"{rotulo} localizado(a) apenas em versão SUPERADA na base "
                      "curada — modo estrito (CITACOES_MODO_ESTRITO): confirme a "
                      "redação vigente na fonte oficial antes de protocolar.")
        if motivo:
            bloqueantes.append({
                "citacao": c.get("citacao") or c.get("trecho") or "",
                "tipo": tipo or "desconhecido",
                "status": status or "desconhecido",
                "motivo": motivo,
            })
    return bloqueantes


async def avaliar_bloqueantes_pertinencia(rel_pert: dict | None) -> list[dict]:
    """Citações cuja AUTORIDADE NÃO AMPARA a afirmação — bloqueantes.

    Só `nao_sustentada` bloqueia. `indeterminada` (sem texto na base, IA
    indisponível, trecho transcrito que não confere) NUNCA bloqueia: não saber
    não é o mesmo que saber que está errado, e tratar os dois igual tornaria a
    dimensão inutilizável assim que a base tivesse uma lacuna. O revisor vê
    "não verificada" no relatório e decide.
    """
    if not rel_pert or not rel_pert.get("habilitada"):
        return []
    return [
        {
            "citacao": i.get("citacao") or "",
            "tipo": i.get("tipo") or "desconhecido",
            "status": "nao_sustentada",
            "motivo": (
                "A autoridade citada NÃO ampara a afirmação da peça: "
                + (i.get("motivo") or "sem trecho de suporte na autoridade.")
                + " Corrija a citação ou a afirmação antes da aprovação."
            ),
        }
        for i in (rel_pert.get("itens") or [])
        if i.get("veredito") == "nao_sustentada"
    ]


async def validar_citacoes(
    db, texto: str, *, politica: str | None = None, modo_sanitizacao=None,
    verificar_pertinencia: bool = True, case_id: str | None = None,
) -> RelatorioCitacoes:
    """Valida citações de um texto gerado por IA e aplica a política.

    Duas dimensões: EXISTÊNCIA (sempre, local e determinística) e PERTINÊNCIA
    (opt-in por `PERTINENCIA_ENABLED`, usa IA).

    - `modo_sanitizacao`: piso de sigilo do caso, propagado à pertinência —
      que envia a AFIRMAÇÃO da peça, carregada de fatos, ao provedor.
    - `case_id`: monta as ENTIDADES NOMEADAS do caso para a pseudonimização
      REVERSÍVEL do gateway. A afirmação enviada à pertinência é uma frase
      inteira da peça e carrega nomes de cliente e parte contrária em claro;
      sem a lista, só o NER heurístico do gateway os protegeria.
    - `verificar_pertinencia=False`: mantém a chamada 100% local e sem LLM
      mesmo com a flag ligada. É o que preserva o contrato documentado de
      `POST /validar-citacoes`, cujos chamadores contam com "sem LLM, sem rede
      externa" e que, por receber texto avulso, não tem caso do qual derivar
      piso de sigilo.
    """
    pol = (politica or "").strip().lower() or politica_citacoes()
    if pol not in _POLITICAS_VALIDAS:
        pol = politica_citacoes()

    if pol == POLITICA_DESLIGADO:
        return RelatorioCitacoes(
            politica=pol,
            motivos=["Verificação de citações desligada (CITACOES_POLITICA)."],
        )

    from app.services.verificador_jurisprudencia import (
        analisar_texto, verificar_jurisprudencia,
    )

    verificacao_parcial = False
    achados = analisar_texto(texto)
    if len(achados) > MAX_CITACOES_POR_VERIFICACAO:
        verificacao_parcial = True
        inicios = sorted(a["span"][0] for a in achados)
        texto = texto[:inicios[MAX_CITACOES_POR_VERIFICACAO]]

    # Auditoria de 2026-08-18 (A/P1-7): no caminho de APROVAÇÃO HITL a verificação
    # consulta o DataJud. Sem isso, um julgado inventado porém bem-formado (nº CNJ
    # com DV válido + tribunal + data) fica "identificada" e não bloqueia — só o
    # revisor humano o barraria. A consulta é fail-safe por construção (teto de
    # consultas por chamada, timeout curto, falha degrada para "identificada") e
    # é opt-in por ambiente: sem DATAJUD_ENABLED o verificador ignora o pedido.
    rel = await verificar_jurisprudencia(
        db, texto, consultar_datajud=get_settings().DATAJUD_ENABLED,
    )

    bloqueantes = [CitacaoBloqueante(**b) for b in avaliar_bloqueantes(rel)]
    motivos: list[str] = []

    # ── Dimensão PERTINÊNCIA (opt-in) ────────────────────────────────────────
    # Fail-safe por construção: qualquer falha aqui devolve a dimensão como
    # desligada e o gate de EXISTÊNCIA segue idêntico. Uma verificação
    # adicional que derrubasse a verificação principal seria pior que não tê-la.
    rel_pert: dict | None = None
    try:
        from app.services.ai import pertinencia as _pert
        if verificar_pertinencia and _pert.habilitada():
            rel_pert = (await _pert.avaliar_texto(
                db, texto, rel.get("citacoes") or [],
                modo_sanitizacao=modo_sanitizacao, case_id=case_id,
            )).model_dump()
            bloqueantes += [
                CitacaoBloqueante(**b)
                for b in await avaliar_bloqueantes_pertinencia(rel_pert)
            ]
            motivos.extend(rel_pert.get("motivos") or [])
    except Exception as e:  # nunca derruba o gate de existência
        logger.warning(
            "[citacoes] verificação de pertinência indisponível "
            "(gate de existência inalterado): %s", str(e)[:200],
        )
        # NÃO devolve `None`: `None` significa "dimensão DESLIGADA" no schema, e
        # o revisor leria uma falha total da checagem como se ela simplesmente
        # não estivesse ativa. Estado próprio, com a mesma honestidade que
        # `indeterminada` tem por citação — a checagem que ele acredita ativa
        # não rodou, e ele precisa saber.
        rel_pert = {
            "habilitada": True, "erro": True, "total": 0, "itens": [],
            "motivos": ["Verificação de PERTINÊNCIA indisponível nesta análise "
                        "— confira manualmente se as autoridades citadas "
                        "sustentam o que a peça afirma."],
        }
        motivos.extend(rel_pert["motivos"])

    if verificacao_parcial:
        motivos.append(
            f"Texto com mais de {MAX_CITACOES_POR_VERIFICACAO} citações — "
            f"verificação PARCIAL (apenas as {MAX_CITACOES_POR_VERIFICACAO} "
            "primeiras foram processadas)."
        )
    if bloqueantes:
        motivos.append(
            f"{len(bloqueantes)} citação(ões) bloqueante(s): possível alucinação, "
            "fonte legal sem vigência confirmada ou julgado incompleto."
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
        verificacao_parcial=verificacao_parcial,
        bloqueantes=bloqueantes,
        motivos=motivos,
        relatorio=rel,
        pertinencia=rel_pert,
    )


def sanitizar_justificativa_override(justificativa: str | None) -> str:
    """Sanitiza justificativa do override contra log-injection."""
    just = " ".join((justificativa or "").split())
    if MARCADOR_OVERRIDE in just.lower():
        raise HTTPException(
            status_code=422,
            detail="Justificativa de override não pode conter o marcador "
                   f"reservado '{MARCADOR_OVERRIDE}' (trilha de auditoria).",
        )
    if len(just) < JUSTIFICATIVA_OVERRIDE_MIN:
        raise HTTPException(
            status_code=422,
            detail="Override do gate de citações exige justificativa "
                   f"(mín. {JUSTIFICATIVA_OVERRIDE_MIN} caracteres) para auditoria.",
        )
    if len(just) > JUSTIFICATIVA_OVERRIDE_MAX:
        just = just[:JUSTIFICATIVA_OVERRIDE_MAX] + "…[truncada]"
    return just


async def aplicar_gate_hitl(
    db, log, novo_status: str, override: bool,
    justificativa: str | None, revisor,
) -> RelatorioCitacoes | None:
    """Aplica o gate antialucinação antes de aprovar um AILog no HITL."""
    if novo_status not in ("revisado", "aplicado"):
        return None
    if not (getattr(log, "resposta", None) or "").strip():
        return None

    # Piso de sigilo do caso do PRÓPRIO AILog: a dimensão de pertinência manda
    # ao provedor a AFIRMAÇÃO da peça, carregada de fatos. Sem isto, o gate de
    # aprovação de um caso sigiloso seria a porta dos fundos que o resto fechou.
    # Sem `case_id` não há piso extra: a política do task_type continua valendo
    # e o gateway reforça de qualquer forma. FALHA DE LEITURA, porém, PROPAGA —
    # `modo_sigilo_por_case_id` não tem try/except de propósito, e esta chamada
    # está FORA do try abaixo: erro transitório lendo `cases` vira 500 em vez de
    # aprovar sem saber se o caso é sigiloso. Fail-closed deliberado; não
    # "conserte" envolvendo em try/except.
    from app.services.ai.sanitization_policy import modo_sigilo_por_case_id
    modo_sigilo = await modo_sigilo_por_case_id(db, getattr(log, "case_id", None))

    try:
        gate = await validar_citacoes(
            db, log.resposta, modo_sanitizacao=modo_sigilo,
            case_id=getattr(log, "case_id", None))
    except Exception:
        logger.exception(
            "Falha na verificação de citações do AILog %s (política %s).",
            getattr(log, "id", "?"), politica_citacoes(),
        )
        if politica_citacoes() == POLITICA_BLOQUEAR:
            raise HTTPException(
                status_code=503,
                detail="Verificação de citações indisponível — a política "
                       "'bloquear' exige verificação antes da aprovação. "
                       "Tente novamente.",
            )
        return None

    if not gate.bloqueia_aprovacao:
        return gate

    if not override:
        raise HTTPException(status_code=409, detail={
            "erro": "citacoes_nao_verificadas",
            "mensagem": "Output de IA contém citações bloqueantes (política "
                        "'bloquear'). Corrija o texto ou aprove com "
                        "override_citacoes=true + justificativa_override.",
            "politica": gate.politica,
            "score": gate.score,
            "motivos": gate.motivos,
            "bloqueantes": [b.model_dump() for b in gate.bloqueantes[:10]],
        })

    just = sanitizar_justificativa_override(justificativa)
    agora = datetime.now(timezone.utc)

    log.fontes_rag = (log.fontes_rag or "") + (
        f"\n{MARCADOR_OVERRIDE} por={revisor.id} "
        f"em={agora.isoformat()} "
        f"bloqueantes={len(gate.bloqueantes)} "
        f"justificativa={just}"
    )

    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db, revisor.id, getattr(revisor.role, "value", revisor.role),
        "ia_hitl_override_citacoes", "ai_logs", getattr(log, "id", None),
        detalhes=(f"Override do gate de citações (status={novo_status}, "
                  f"bloqueantes={len(gate.bloqueantes)}): {just}"),
    )
    return gate
