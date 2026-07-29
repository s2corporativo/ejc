# ── app/services/citation_gate.py ────────────────────────────────────────────
"""
citation_gate.py — Gate antialucinação de citações jurídicas (Fase 4).

Camada de POLÍTICA sobre o verificador rigoroso já existente
(verificador_jurisprudencia.py, que extrai/classifica citações como
verificada/identificada/suspeita/generica contra a base RAG oficial +
validação estrutural CNJ/súmula). Este módulo NÃO re-extrai nada — apenas:

  1. Decide, conforme `settings.CITACOES_POLITICA` ("bloquear"|"marcar"|
     "desligado", default "bloquear"), se o output de IA pode ser APROVADO
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
     MODO ESTRITO (opt-in, flag CITACOES_MODO_ESTRITO, default OFF): uma
     SÚMULA ou ARTIGO citado mas AUSENTE da base curada — que no modo legado
     fica em `identificada` e NÃO bloqueia — passa a BLOQUEAR (a ausência é
     tratada como suspeita de invenção plausível). É bloqueio ADITIVO: nada
     do modo legado é afrouxado, e súmula/artigo `verificada` nunca bloqueia.
  3. Expõe `validar_citacoes(db, texto) -> RelatorioCitacoes` (validação sob
     demanda via POST /ia/validar-citacoes e gate do HITL).

100% local e determinístico (sem LLM, sem rede externa) — por isso o
relatório pode ser RECOMPUTADO a qualquer momento a partir do texto
(GET /ai/logs/{id}/citacoes), sem precisar de coluna nova no AILog.
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

# Tipos de citação que referenciam JULGADO (exigem tribunal+data verificáveis).
_TIPOS_JULGADO = {"processo_cnj", "recurso"}

# Tipos confirmáveis por lookup EXATO na base curada (súmulas/artigos): quando
# CITADOS mas AUSENTES da base, o verificador os deixa em status "identificada"
# (não-bloqueante no modo legado). No MODO ESTRITO essa ausência vira bloqueio
# (ver avaliar_bloqueantes / modo_estrito_citacoes). Para estes tipos,
# "identificada" equivale exatamente a "não encontrado na base" — status
# "verificada" (encontrado) e "suspeita" (fora de faixa/formato) seguem por
# outros ramos e NUNCA passam por aqui.
_TIPOS_CONFIRMAVEIS_BASE = {"sumula", "artigo"}

# ── Limites de custo e de auditoria do gate ─────────────────────────────────
# Teto de citações processadas por verificação (cada súmula/artigo custa um
# lookup no banco). Acima disso o texto é verificado apenas até a citação de
# número MAX e o relatório sai com `verificacao_parcial=true`.
MAX_CITACOES_POR_VERIFICACAO = 200
JUSTIFICATIVA_OVERRIDE_MIN = 10
JUSTIFICATIVA_OVERRIDE_MAX = 500
# Marcador reservado da trilha de override em AILog.fontes_rag — proibido na
# justificativa do revisor para impedir injeção de linhas falsas de auditoria.
MARCADOR_OVERRIDE = "[override_citacoes]"


def politica_citacoes() -> str:
    """Política vigente, normalizada.

    Valor inválido/typo cai no modo SEGURO 'bloquear' (fail-secure): um erro de
    configuração NÃO pode rebaixar silenciosamente o gate antialucinação para o
    modo permissivo — é exatamente esse rebaixamento que deixaria passar citação
    inventada (vetor pelo qual advogados foram punidos).
    """
    val = (get_settings().CITACOES_POLITICA or "").strip().lower()
    if val not in _POLITICAS_VALIDAS:
        logger.warning(
            "CITACOES_POLITICA inválida (%r) — usando 'bloquear' (fail-secure).",
            val,
        )
        return POLITICA_BLOQUEAR
    return val


def modo_estrito_citacoes() -> bool:
    """Modo estrito do gate antialucinação (flag CITACOES_MODO_ESTRITO).

    OFF (default): comportamento legado — súmula/artigo CITADO mas ausente da
    base curada fica só "identificada" e NÃO bloqueia (o gate barra erro
    estrutural, não invenção plausível). ON: essa ausência vira BLOQUEANTE
    (ver avaliar_bloqueantes). Só ADICIONA bloqueio; nunca afrouxa os já
    existentes. Ligue apenas com a base de conhecimento abrangente, senão gera
    falso-positivo em citação real ainda não ingerida (ver .env.example).
    """
    return bool(get_settings().CITACOES_MODO_ESTRITO)


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
    # True quando o texto tinha mais de MAX_CITACOES_POR_VERIFICACAO citações
    # e só as primeiras foram verificadas (proteção de custo).
    verificacao_parcial: bool = False
    bloqueantes: list[CitacaoBloqueante] = Field(default_factory=list)
    motivos: list[str] = Field(default_factory=list)
    # Relatório integral do verificador rigoroso (shape de
    # verificar_jurisprudencia); None quando politica == "desligado".
    relatorio: dict | None = None


def avaliar_bloqueantes(
    relatorio: dict, *, modo_estrito: bool | None = None,
) -> list[dict]:
    """Citações do relatório que impedem aprovação na política 'bloquear'.

    Retorna dicts {citacao, tipo, status, motivo} (ver critérios no docstring
    do módulo). Função pura/síncrona para reuso no response_validator.

    `modo_estrito`: None (default) lê a flag CITACOES_MODO_ESTRITO; True/False
    força o modo (usado em testes). No modo estrito, uma súmula/artigo CITADO
    mas AUSENTE da base curada (status "identificada" — ou seja, o lookup exato
    retornou não-encontrado) passa a BLOQUEAR. Isso apenas ADICIONA bloqueio;
    nenhum bloqueio legado é afrouxado. Súmula/artigo "verificada" (encontrado)
    nunca entra neste ramo, então nunca bloqueia por esta regra.
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
        elif status == "identificada" and tipo in _TIPOS_JULGADO:
            faltas = [n for n, v in (("tribunal", c.get("tribunal")),
                                     ("data", c.get("data"))) if not v]
            if faltas:
                motivo = ("julgado citado sem " + " e ".join(faltas) +
                          " verificáveis no contexto — exija processo, "
                          "tribunal e data de julgamento/publicação")
        elif (modo_estrito and status == "identificada"
              and tipo in _TIPOS_CONFIRMAVEIS_BASE):
            # A-1 (modo estrito): para súmula/artigo, "identificada" significa
            # citado + lookup exato NÃO encontrou na base curada — isto é,
            # referência plausível mas potencialmente inexistente. Sob modo
            # estrito escalamos essa ausência a bloqueio (equivale a suspeita).
            rotulo = "Súmula" if tipo == "sumula" else "Artigo"
            motivo = (f"{rotulo} citado(a) não encontrado(a) na base curada — "
                      "modo estrito (CITACOES_MODO_ESTRITO): confirme a "
                      "existência na fonte oficial ou remova a citação.")
        elif (modo_estrito and status == "possivelmente_desatualizada"
              and tipo in _TIPOS_CONFIRMAVEIS_BASE):
            # Coerência do modo estrito: se "não encontrada na base" já bloqueia
            # (acima), "encontrada APENAS em versão superada" também precisa —
            # senão a citação de redação revogada passaria enquanto a de norma
            # meramente desconhecida é barrada, o que inverte a gravidade.
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

    from app.services.verificador_jurisprudencia import (
        analisar_texto, verificar_jurisprudencia,
    )

    # Teto de custo: cada súmula/artigo verificado custa um lookup no banco.
    # A extração (analisar_texto) é pura/CPU — usamos os spans para cortar o
    # texto na citação nº MAX+1 e verificar só o prefixo (relatório parcial).
    verificacao_parcial = False
    achados = analisar_texto(texto)
    if len(achados) > MAX_CITACOES_POR_VERIFICACAO:
        verificacao_parcial = True
        inicios = sorted(a["span"][0] for a in achados)
        texto = texto[:inicios[MAX_CITACOES_POR_VERIFICACAO]]

    rel = await verificar_jurisprudencia(db, texto)

    bloqueantes = [CitacaoBloqueante(**b) for b in avaliar_bloqueantes(rel)]
    motivos: list[str] = []
    if verificacao_parcial:
        motivos.append(
            f"Texto com mais de {MAX_CITACOES_POR_VERIFICACAO} citações — "
            f"verificação PARCIAL (apenas as {MAX_CITACOES_POR_VERIFICACAO} "
            "primeiras foram processadas)."
        )
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
        verificacao_parcial=verificacao_parcial,
        bloqueantes=bloqueantes,
        motivos=motivos,
        relatorio=rel,
    )


# ── Gate compartilhado do fluxo HITL ─────────────────────────────────────────
# Usado por PATCH /ai/logs/{id}/hitl E PATCH /ia-defensiva/historico/{id}/status
# — qualquer endpoint que altere AILog.status_hitl para revisado/aplicado DEVE
# passar por aqui (senão vira bypass do gate antialucinação).

def sanitizar_justificativa_override(justificativa: str | None) -> str:
    """Sanitiza a justificativa do override (anti log-injection).

    - Colapsa TODO whitespace (inclusive \\n/\\r/\\t) em espaço simples — a
      trilha em fontes_rag é parseada por linha, então quebra de linha na
      justificativa permitiria forjar entradas de auditoria.
    - Rejeita (422) conteúdo com o marcador reservado ``[override_citacoes]``.
    - Exige mínimo de JUSTIFICATIVA_OVERRIDE_MIN caracteres (422).
    - Trunca em JUSTIFICATIVA_OVERRIDE_MAX chars anotando sufixo "…[truncada]".
    """
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
    """Aplica o gate antialucinação antes de aprovar um AILog no HITL.

    - `novo_status` fora de {revisado, aplicado} (ex.: descartado) → livre.
    - Falha na verificação: logada SEMPRE (com stacktrace); fail-closed 503
      SÓ na política "bloquear" (aprovar sem verificar contraria a política —
      runbook: mudar CITACOES_POLITICA para 'marcar' e REINICIAR o backend).
    - Bloqueante sem override → 409; com override → exige justificativa
      sanitizada (ver sanitizar_justificativa_override) e grava trilha dupla:
      espelho em AILog.fontes_rag + audit_logs imutável (criar_audit_log).

    Retorna o RelatorioCitacoes (ou None se o gate não se aplicou/falhou em
    política tolerante). Levanta HTTPException 409/422/503 conforme o caso.
    """
    if novo_status not in ("revisado", "aplicado"):
        return None
    if not (getattr(log, "resposta", None) or "").strip():
        return None

    try:
        gate = await validar_citacoes(db, log.resposta)
    except Exception:
        # B1/B3: SEMPRE logar a falha com stacktrace (antes era silencioso em
        # política 'marcar'); fail-closed apenas quando a política exige.
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

    # Espelho no próprio AILog (campo de rastreabilidade fontes_rag — sem
    # migration; exposto no histórico/GET citações).
    log.fontes_rag = (log.fontes_rag or "") + (
        f"\n{MARCADOR_OVERRIDE} por={revisor.id} "
        f"em={agora.isoformat()} "
        f"bloqueantes={len(gate.bloqueantes)} "
        f"justificativa={just}"
    )

    # Trilha IMUTÁVEL em audit_logs (LGPD art. 37) — sobrevive a edição do
    # AILog; mesma transação do commit do chamador.
    from app.models.audit_log import criar_audit_log
    await criar_audit_log(
        db, revisor.id, getattr(revisor.role, "value", revisor.role),
        "ia_hitl_override_citacoes", "ai_logs", getattr(log, "id", None),
        detalhes=(f"Override do gate de citações (status={novo_status}, "
                  f"bloqueantes={len(gate.bloqueantes)}): {just}"),
    )
    return gate
