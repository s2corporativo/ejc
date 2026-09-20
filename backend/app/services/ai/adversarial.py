# ── app/services/ai/adversarial.py ──────────────────────────────────────────
# MODO DUAS IAS (Fase 5) — IA Crítica/Adversarial.
#
# Conteúdo jurídico de alta complexidade gerado pela IA Proponente (peças,
# análises e estratégia) pode passar por uma SEGUNDA IA que atua como advogado
# da parte contrária + magistrado: caça contradições, lacunas fáticas,
# fragilidades probatórias, teses defensivas prováveis e jurisprudência contrária.
#
# Princípios (imutáveis):
#   • DIVERSIDADE DE PROVIDER: a crítica prefere provider DIFERENTE do que
#     gerou a peça (erro correlacionado ↓). Se só houver um elegível, usa-o —
#     crítica com o mesmo provider ainda vale mais que nenhuma.
#   • NUNCA BLOQUEIA: falha da crítica (provider fora, timeout, PII) devolve
#     `disponivel=False` com aviso — a peça segue para o revisor HITL.
#   • A crítica TAMBÉM passa pelo gate de citações (citation_gate): a
#     jurisprudência sugerida pela IA Crítica pode ser alucinada.
#   • A crítica AJUDA o revisor humano; jamais o substitui (HITL/OAB).
#   • LGPD preservada: a chamada sai pelo ai_gateway.chat, que já aplica a
#     barreira final de sanitização para providers externos.
from __future__ import annotations

import logging
import re

from pydantic import BaseModel, Field

from app.core.ai_errors import descricao_tecnica_segura
from app.core.config import get_settings
from app.services.ai import delimitador
from app.services.citation_gate import RelatorioCitacoes

logger = logging.getLogger("ejc.ai.adversarial")

TASK_TYPE_CRITICA = "critica_adversarial"

AVISO_INDISPONIVEL = (
    "CRÍTICA ADVERSARIAL INDISPONÍVEL: a segunda IA não pôde ser executada. "
    "O conteúdo segue normalmente para revisão humana — redobre a atenção na "
    "revisão (contradições, lacunas fáticas e jurisprudência citada)."
)
AVISO_RASCUNHO = (
    "RELATÓRIO DE CRÍTICA GERADO POR IA — apoio ao revisor humano (HITL). "
    "Não substitui a análise do advogado responsável."
)
# Caso de SIGILO REFORÇADO sem IA local elegível: a crítica é PULADA em vez de
# sair do VPS. Aviso próprio (não o genérico) para que o revisor saiba que a
# ausência da crítica é decisão de política, não indisponibilidade técnica.
AVISO_BLOQUEIO_SIGILO = (
    "CRÍTICA ADVERSARIAL NÃO EXECUTADA — SIGILO REFORÇADO: o caso exige que o "
    "conteúdo não saia do servidor (IA local) e nenhum provedor local está "
    "elegível. A peça segue para revisão humana SEM segunda leitura por IA — "
    "redobre a atenção (contradições, lacunas fáticas e jurisprudência citada). "
    "Para habilitar a crítica nestes casos, suba a IA local (OLLAMA_ENABLED)."
)

# Marcador que ENCABEÇA o relatório no campo DEDICADO AILog.critica_adversarial
# (migration 070). A crítica NÃO vive mais dentro de `resposta` — assim a
# jurisprudência especulativa da crítica não entra no gate de aprovação HITL
# (que varre só `resposta`) nem na ingestão RAG (que destila só `resposta`).
MARCADOR_AILOG = "═══ CRÍTICA ADVERSARIAL (Modo Duas IAs — apoio ao revisor HITL) ═══"

# Substituto usado ao NEUTRALIZAR tentativas de forjar o marcador reservado
# dentro do texto da peça de entrada (paridade com o hardening de
# MARCADOR_OVERRIDE no citation_gate — impede injeção de seção de crítica falsa).
_MARCADOR_NEUTRALIZADO = "[marcador de crítica reservado removido]"


def neutralizar_marcador_ailog(texto: str | None) -> str | None:
    """Neutraliza o marcador reservado da crítica embutido no texto da peça.

    O ``MARCADOR_AILOG`` delimita o relatório da IA Crítica no campo dedicado;
    se um autor de peça o embutisse no próprio texto, poderia forjar uma seção
    de crítica ao ser exibido/ecoado. Substituímos qualquer ocorrência literal
    (paridade com a rejeição de ``MARCADOR_OVERRIDE`` no citation_gate)."""
    if not texto:
        return texto
    return texto.replace(MARCADOR_AILOG, _MARCADOR_NEUTRALIZADO)

# Maritaca incluída: laboratório/treinamento distintos do gerador reduzem erro
# correlacionado — exatamente o objetivo da diversidade no Modo Duas IAs.
_PROVIDERS_CONHECIDOS = ("ollama", "anthropic", "groq", "maritaca")

SYSTEM_CRITICA = """
Você é a IA CRÍTICA/ADVERSARIAL do escritório De Paula Teixeira Advogados.
Assuma DOIS papéis simultâneos sobre o conteúdo jurídico recebido:
1. ADVOGADO DA PARTE CONTRÁRIA: como você atacaria a tese, análise ou peça? Onde ela é vulnerável?
2. MAGISTRADO EXIGENTE: o que faltou provar? O que está contraditório, prematuro ou mal fundamentado?

Sua missão é BLINDAR o raciocínio encontrando defeitos ANTES do adversário e ANTES da decisão judicial.

Regras absolutas:
- NÃO reescreva o conteúdo; produza apenas o relatório de crítica.
- NÃO invente leis, súmulas, julgados, número de acórdão, relator ou data.
  Jurisprudência contrária deve ser listada como HIPÓTESE A VERIFICAR, nunca
  como certeza; sem fonte certa, escreva exatamente: verificar fonte.
- Separe fato, inferência e lacuna. Seja específico: cite o trecho criticado.
- Todo o resultado é apoio interno ao revisor humano (rascunho HITL).

Responda EXATAMENTE nesta estrutura de seções:

## 1. CONTRADIÇÕES
(internas ao conteúdo e entre a análise/peça e os fatos/documentos do contexto; se nenhuma, escreva "Nenhuma identificada.")

## 2. LACUNAS FÁTICAS
(fatos essenciais não narrados/não provados; datas, valores e nexos ausentes)

## 3. FRAGILIDADES PROBATÓRIAS
(afirmações sem prova, ônus da prova mal endereçado, provas frágeis tratadas como fortes)

## 4. TESES DEFENSIVAS PROVÁVEIS
(preliminares e mérito que a parte contrária provavelmente arguirá, em ordem de risco)

## 5. JURISPRUDÊNCIA CONTRÁRIA A VERIFICAR
(linhas jurisprudenciais adversas plausíveis — SEMPRE como "verificar fonte"; nunca invente referência)

## 6. NOTA DE ROBUSTEZ
NOTA DE ROBUSTEZ: <inteiro 0-100>
(0 = raciocínio indefensável; 100 = análise/peça robusta. Justifique em 2-3 linhas.)
""".strip()

_RE_NOTA = re.compile(r"NOTA\s+DE\s+ROBUSTEZ\s*[:\-]?\s*(\d{1,3})", re.IGNORECASE)


class CriticaAdversarial(BaseModel):
    """Relatório da IA Crítica sobre uma peça (Modo Duas IAs)."""
    disponivel: bool
    relatorio: str | None = None
    nota_robustez: int | None = Field(default=None, ge=0, le=100)
    provedor: str | None = None
    modelo: str | None = None
    provedor_origem: str | None = None
    task_type_origem: str | None = None
    # True quando a crítica rodou em provider DIFERENTE do que gerou a peça.
    provider_diverso: bool = False
    # Gate de citações aplicado À PRÓPRIA CRÍTICA (jurisprudência sugerida
    # pela IA Crítica também pode ser alucinada). None = gate indisponível.
    citacoes: RelatorioCitacoes | None = None
    alertas: list[str] = Field(default_factory=list)
    aviso: str = AVISO_RASCUNHO
    tokens_input: int | None = None
    tokens_output: int | None = None
    duracao_ms: int = 0


def task_types_criticaveis() -> set[str]:
    """Task_types (normalizados) que disparam crítica automática (CSV da config)."""
    from app.services.ai_gateway import _normalizar_task_type
    csv = get_settings().DUAS_IAS_TASK_TYPES or ""
    return {_normalizar_task_type(t.strip().lower()) for t in csv.split(",") if t.strip()}


def critica_automatica_habilitada(task_type: str | None) -> bool:
    """True se o Modo Duas IAs está ligado E o task_type é elegível."""
    if not get_settings().DUAS_IAS_ENABLED or not task_type:
        return False
    from app.services.ai_gateway import _normalizar_task_type
    return _normalizar_task_type(task_type.strip().lower()) in task_types_criticaveis()


def escolher_provider_diverso(
    provedor_origem: str | None,
    modo_sanitizacao=None,
) -> str | None:
    """Primeiro provider ELEGÍVEL diferente do que gerou a peça, na ordem de
    AI_PROVIDER_PRIORITY. None = nenhum diverso elegível (a crítica roda na
    cadeia automática do gateway, possivelmente no mesmo provider).

    `modo_sanitizacao=LOCAL_COMPLETO` (sigilo reforçado) restringe os candidatos
    a providers LOCAIS: o SIGILO VENCE A DIVERSIDADE. Sem esse filtro, forçar o
    "provider diverso" era exatamente o que empurrava a peça de um caso sigiloso
    para Anthropic/Groq — a diversidade de modelo é desejável, sair do VPS não é
    negociável. Se o único local elegível for o próprio provedor de origem, ele é
    devolvido (crítica no mesmo provider vale mais que nenhuma, e o alerta de
    "MESMO provider" já existe); se nenhum local for elegível, None."""
    from app.services import ai_gateway
    from app.services.ai.sanitization_policy import ModoSanitizacao
    somente_local = modo_sanitizacao == ModoSanitizacao.LOCAL_COMPLETO
    prioridade = [
        p.strip().lower()
        for p in (get_settings().AI_PROVIDER_PRIORITY or "").split(",")
        if p.strip()
    ]
    candidatos = prioridade + [p for p in _PROVIDERS_CONHECIDOS if p not in prioridade]
    if somente_local:
        candidatos = [p for p in candidatos if p not in ai_gateway._PROVIDERS_EXTERNOS]
    for p in candidatos:
        if p != (provedor_origem or "").lower() and ai_gateway._provider_elegivel(p):
            return p
    # Sigilo reforçado: sem local DIVERSO, aceita o próprio provedor de origem
    # (que é local, senão a peça já teria sido bloqueada) antes de desistir.
    if somente_local:
        origem = (provedor_origem or "").lower()
        if origem in candidatos and ai_gateway._provider_elegivel(origem):
            return origem
    return None


def _montar_user_prompt(texto_peca: str, contexto_caso: str | None) -> str:
    # Delimitador com token ALEATÓRIO por chamada (ponto único em
    # `ai/delimitador.py`): dificulta o escape/injeção via `[/PEÇA A CRITICAR]`
    # embutido no texto — o autor da peça não conhece o token.
    tok = delimitador.novo_token()
    return delimitador.montar(
        delimitador.bloco("CONTEXTO DO CASO", contexto_caso, tok, limite=6000),
        delimitador.bloco("PEÇA A CRITICAR", texto_peca, tok),
        instrucao_final=(
            "Produza o relatório de crítica adversarial na estrutura de seções exigida."
        ),
    )


def extrair_nota_robustez(texto: str | None) -> int | None:
    m = _RE_NOTA.search(texto or "")
    if not m:
        return None
    nota = int(m.group(1))
    return nota if 0 <= nota <= 100 else None


async def criticar_peca(
    db,
    texto_peca: str,
    contexto_caso: str | None = None,
    task_type_origem: str | None = None,
    provedor_origem: str | None = None,
    case_id: str | None = None,
    entidades: dict[str, list[str]] | None = None,
    modo_sanitizacao=None,
) -> CriticaAdversarial:
    """Executa a IA Crítica sobre uma peça. NUNCA levanta exceção de provider:
    qualquer falha devolve CriticaAdversarial(disponivel=False, aviso=...).

    - `provedor_origem`: provider que gerou a peça (diversidade — a crítica
      prefere outro provider).
    - `db`: sessão async, usada para o gate de citações da própria crítica E
      para montar as ENTIDADES NOMEADAS do caso (None = gate/entidades pulados).
    - `case_id`: caso ao qual a peça pertence. Quando informado (com `db`),
      resolve o PISO DE SIGILO do caso (`sigilo_reforcado` → LOCAL_COMPLETO) e,
      se `entidades` não vier pronto, monta as entidades nomeadas do caso para
      a pseudonimização REVERSÍVEL do gateway.
    - `entidades`: entidades nomeadas JÁ montadas (ex.: pelo orquestrador) —
      evita reconsultar o banco. Tem precedência sobre `case_id`.
    - `modo_sanitizacao`: piso de sigilo que o CHAMADOR já conhece (ex.: área
      sensível resolvida pelo orquestrador). Só ELEVA o piso; nunca rebaixa o
      que o caso ou o task_type já exigiam.
    """
    from app.services import ai_gateway
    from app.services.ai.sanitization_policy import (
        ModoSanitizacao, modo_para_task, modo_sigilo_por_case_id, reforcar_sigilo,
    )

    # ── PISO DE SIGILO DA CRÍTICA (fail-closed) ──────────────────────────────
    # O furo corrigido aqui: a crítica recebe a PEÇA INTEIRA e o CONTEXTO DO
    # CASO (dossiê/OCR/RAG) e, por design, PREFERE provider EXTERNO para ter
    # diversidade de modelo. O task_type `critica_adversarial` é
    # EXTERNO_PSEUDONIMIZADO na política — então, num caso marcado
    # `sigilo_reforcado`, a GERAÇÃO da peça rodava local (correto) e a CRÍTICA
    # saía do VPS logo depois, levando o mesmo conteúdo. O piso do CASO é
    # resolvido aqui (ponto único: `modo_sigilo_por_case_id`), reforçado pelo
    # piso que o chamador informar, e entregue ao gateway — que também reforça.
    # Falha de LEITURA do caso não vira "pode ir ao externo": devolve
    # `disponivel=False`. Sem crítica é aceitável; crítica vazada não é.
    modo_efetivo = reforcar_sigilo(modo_para_task(TASK_TYPE_CRITICA), modo_sanitizacao)
    if modo_efetivo != ModoSanitizacao.LOCAL_COMPLETO and case_id and db is not None:
        try:
            modo_efetivo = reforcar_sigilo(
                modo_efetivo, await modo_sigilo_por_case_id(db, case_id)
            )
        except Exception as e:
            logger.warning(
                "[DuasIAs] Não foi possível resolver o sigilo do caso %s — "
                "crítica PULADA (fail-closed): %s",
                case_id,
                descricao_tecnica_segura(e),
            )
            return CriticaAdversarial(
                disponivel=False,
                provedor_origem=provedor_origem,
                task_type_origem=task_type_origem,
                aviso=AVISO_INDISPONIVEL,
                alertas=["Sigilo do caso indeterminado — crítica não executada "
                         "para não arriscar envio indevido a provedor externo."],
            )

    # Hardening (paridade com MARCADOR_OVERRIDE): neutraliza o marcador
    # reservado da crítica se embutido no texto da peça, para que não possa
    # forjar uma seção de crítica no campo dedicado nem ser ecoado no relatório.
    texto_peca = neutralizar_marcador_ailog(texto_peca)

    # ── Nomes do caso → pseudonimização REVERSÍVEL no gateway (LGPD) ─────────
    # A minuta (`texto_peca`) e o `contexto_caso` trazem nomes de cliente e
    # parte contrária EM CLARO. A crítica cai em EXTERNO_PSEUDONIMIZADO e
    # PREFERE provider EXTERNO (diversidade) — sem `entidades`, a barreira final
    # do gateway só pega PII ESTRUTURAL (CPF/CNPJ…), NÃO nomes próprios, que
    # vazariam ao provider externo. Montamos as ENTIDADES NOMEADAS do caso para
    # que o gateway troque cada nome por marcador consistente ([CLIENTE_1]/
    # [PARTE_CONTRARIA_1]) ANTES do externo e REIDRATE a resposta localmente.
    # entidades_do_caso é fail-safe: NUNCA levanta ({} → degrada com segurança,
    # a barreira estrutural do gateway continua ativa).
    if entidades is None and case_id and db is not None:
        from app.services.ai.entidades_caso import entidades_do_caso
        entidades = await entidades_do_caso(db, case_id)

    provider_escolhido = escolher_provider_diverso(provedor_origem, modo_efetivo)
    # Sigilo reforçado sem NENHUM provedor local elegível: pula a crítica com
    # aviso PRÓPRIO, em vez de deixar o gateway escolher a cadeia (que também
    # bloquearia, mas com mensagem genérica de indisponibilidade). Nunca
    # degradar silenciosamente a proteção: a ausência da crítica fica explícita
    # no relatório que o revisor HITL lê.
    if modo_efetivo == ModoSanitizacao.LOCAL_COMPLETO and not provider_escolhido:
        logger.warning(
            "[DuasIAs] Caso com SIGILO REFORÇADO e nenhum provedor local "
            "elegível — crítica adversarial PULADA (não sai do VPS). "
            "case_id=%s task_origem=%s", case_id, task_type_origem,
        )
        return CriticaAdversarial(
            disponivel=False,
            provedor_origem=provedor_origem,
            task_type_origem=task_type_origem,
            aviso=AVISO_BLOQUEIO_SIGILO,
            alertas=["Sigilo reforçado: crítica exigiria IA local e não há "
                     "provedor local elegível."],
        )
    try:
        resp = await ai_gateway.chat(
            messages=[
                {"role": "system", "content": SYSTEM_CRITICA},
                {"role": "user", "content": _montar_user_prompt(texto_peca, contexto_caso)},
            ],
            task_type=TASK_TYPE_CRITICA,
            temperature=0.2,
            max_tokens=4000,
            provider_override=provider_escolhido,
            entidades=entidades or None,
            # Piso de sigilo do CASO/chamador. O gateway reforça de novo
            # (reforcar_sigilo) e, em LOCAL_COMPLETO, filtra a cadeia para
            # providers locais — um `provider_override` externo é DESCARTADO
            # ali, não obedecido. Dupla barreira deliberada.
            modo_sanitizacao=modo_efetivo,
        )
    except Exception as e:
        # Failure mode: crítica NUNCA bloqueia a entrega da peça.
        logger.warning(
            "[DuasIAs] Crítica adversarial indisponível — peça segue para HITL. "
            "task_origem=%s provider_origem=%s provider_tentado=%s erro=%s",
            task_type_origem,
            provedor_origem,
            provider_escolhido,
            descricao_tecnica_segura(e),
        )
        return CriticaAdversarial(
            disponivel=False,
            provedor_origem=provedor_origem,
            task_type_origem=task_type_origem,
            aviso=AVISO_INDISPONIVEL,
            alertas=[
                "Segunda revisão por IA indisponível — reforce a revisão humana "
                "antes do uso jurídico."
            ],
        )

    alertas: list[str] = []
    diverso = bool(provedor_origem) and resp.provedor != (provedor_origem or "").lower()
    if provedor_origem and not diverso:
        alertas.append(
            "Crítica executada no MESMO provider que gerou a peça "
            f"({resp.provedor}) — nenhum provider diverso elegível; "
            "diversidade de modelos indisponível nesta chamada."
        )

    # Gate de citações sobre a PRÓPRIA crítica (jurisprudência sugerida pela
    # IA Crítica também pode ser alucinada). Falha do gate → alerta, não erro.
    citacoes: RelatorioCitacoes | None = None
    if db is not None:
        from app.services import citation_gate
        try:
            citacoes = await citation_gate.validar_citacoes(
                db, resp.texto, modo_sanitizacao=modo_efetivo,
                # A crítica é APOIO ao revisor, não peça sujeita a aprovação:
                # sua jurisprudência já vai rotulada como "verificar fonte". N
                # chamadas extras de IA aqui custariam sem mudar decisão.
                verificar_pertinencia=False,
            )
            if citacoes.bloqueantes:
                alertas.append(
                    f"{len(citacoes.bloqueantes)} citação(ões) da PRÓPRIA crítica "
                    "com indício de alucinação — não use a jurisprudência "
                    "sugerida sem verificação manual."
                )
        except Exception as e:
            citacoes = None
            alertas.append(
                "Gate de citações indisponível para o relatório de crítica — "
                "verifique manualmente toda jurisprudência sugerida."
            )
            logger.warning(
                "[DuasIAs] Gate de citações falhou na crítica: %s",
                descricao_tecnica_segura(e),
            )
    else:
        alertas.append(
            "Gate de citações não executado (sem sessão de banco) — verifique "
            "manualmente a jurisprudência sugerida pela crítica."
        )

    nota = extrair_nota_robustez(resp.texto)
    if nota is None:
        alertas.append("IA Crítica não informou NOTA DE ROBUSTEZ no formato esperado.")

    logger.info(
        "[DuasIAs] Crítica adversarial ok: provider=%s (origem=%s, diverso=%s) "
        "nota=%s duracao=%sms",
        resp.provedor, provedor_origem, diverso, nota, resp.duracao_ms,
    )
    return CriticaAdversarial(
        disponivel=True,
        relatorio=resp.texto,
        nota_robustez=nota,
        provedor=resp.provedor,
        modelo=resp.modelo,
        provedor_origem=provedor_origem,
        task_type_origem=task_type_origem,
        provider_diverso=diverso,
        citacoes=citacoes,
        alertas=alertas,
        tokens_input=resp.input_tokens,
        tokens_output=resp.output_tokens,
        duracao_ms=resp.duracao_ms,
    )


def formatar_para_ailog(critica: CriticaAdversarial) -> str:
    """Bloco textual gravado no campo DEDICADO AILog.critica_adversarial
    (migration 070) para o revisor HITL ver a crítica junto da peça — SEM
    contaminar `resposta` (gate de aprovação e ingestão RAG)."""
    linhas = [MARCADOR_AILOG]
    if not critica.disponivel:
        linhas.append(critica.aviso)
        linhas.extend(critica.alertas)
        return "\n".join(linhas)
    cab = [f"Provider da crítica: {critica.provedor}/{critica.modelo}"]
    if critica.provedor_origem:
        cab.append(
            f"Provider da peça: {critica.provedor_origem} "
            f"({'DIVERSO' if critica.provider_diverso else 'MESMO provider'})"
        )
    if critica.nota_robustez is not None:
        cab.append(f"Nota de robustez: {critica.nota_robustez}/100")
    if critica.citacoes is not None:
        cab.append(
            "Gate de citações da crítica: "
            f"{critica.citacoes.total} citação(ões), "
            f"{len(critica.citacoes.bloqueantes)} bloqueante(s) "
            f"(política '{critica.citacoes.politica}')"
        )
    linhas.append(" | ".join(cab))
    for a in critica.alertas:
        linhas.append(f"ALERTA: {a}")
    linhas.append("")
    linhas.append(critica.relatorio or "")
    linhas.append("")
    linhas.append(critica.aviso)
    return "\n".join(linhas)


async def anexar_critica_ao_log(db, log_id: str | None, critica: CriticaAdversarial) -> bool:
    """Grava o relatório de crítica no campo DEDICADO AILog.critica_adversarial.

    NÃO concatena mais em `resposta`: assim a jurisprudência especulativa da
    crítica não entra no gate de aprovação HITL (varre só `resposta`) nem na
    ingestão RAG (destila só `resposta`). Best-effort: falha vira log
    estruturado, nunca exceção (não bloqueia a peça)."""
    if db is None or not log_id:
        return False
    try:
        from app.models.ai_log import AILog
        log = await db.get(AILog, log_id)
        if log is None:
            logger.warning("[DuasIAs] AILog %s não encontrado para anexar crítica.", log_id)
            return False
        log.critica_adversarial = formatar_para_ailog(critica)
        await db.commit()
        return True
    except Exception as e:
        logger.warning(
            "[DuasIAs] Falha ao anexar crítica ao AILog %s (peça não bloqueada): %s",
            log_id, descricao_tecnica_segura(e),
        )
        return False
