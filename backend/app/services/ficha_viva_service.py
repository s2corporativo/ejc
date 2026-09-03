# ── app/services/ficha_viva_service.py ───────────────────────────────────────
# FICHA VIVA do Banco de Teses — Legal Drafting 2.0, §5 ("Legal Knowledge
# Skills"), implementado sobre a estrutura CANÔNICA `teses` + `tese_caso_links`
# (ver o cabeçalho de `models/tese.py` e a decisão registrada no ledger de
# migrations). Este módulo NÃO substitui `matriz_teses_service` (teses do CASO,
# efêmeras, HITL) nem `tese_caso_matcher` (casamento tese↔caso por termos): ele
# cuida do que faltava para o CATÁLOGO INSTITUCIONAL ser auditável e vivo.
#
# Três coisas, e nenhuma delas é "mais uma tabela":
#
#   1. VERSIONAMENTO — uma peça protocolada em março precisa ser explicável em
#      outubro. Sem histórico, a ficha que a fundamentou já mudou e não há como
#      saber o que ela dizia. `tese_versoes` é imutável por construção.
#   2. LASTRO — `Tese.fundamentacao` e `Tese.jurisprudencia` são texto livre: a
#      ficha afirma "Súmula 297/TST" e nada no sistema sabe se existe, se
#      continua vigente, ou de onde veio. `tese_fontes` dá referência, trecho
#      REAL e status de verificação a cada elemento.
#   3. RECUSA — hoje o advogado que discorda de uma ficha simplesmente não a
#      usa, e o catálogo nunca fica sabendo: a ficha segue parecendo boa porque
#      só é medida quando é usada. `tese_overrides` registra a NÃO-aplicação, e
#      é isso que fecha o ciclo de aprendizado.
#
# Nada aqui usa IA. São registros de fato e aritmética verificável — a
# confiança da ficha é MEDIDA em casos reais, nunca opinada por um modelo.
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from app.models.tese import (
    ELEMENTOS_FONTE, MOTIVOS_OVERRIDE, STATUS_FONTE,
    Tese, TeseFonte, TeseOverride, TeseVersao,
)

logger = logging.getLogger("ejc.ficha_viva")

# Campos que compõem a fotografia da ficha. Lista explícita (e não
# `__table__.columns`) porque o snapshot é um CONTRATO de auditoria: uma coluna
# nova não deve mudar retroativamente o que as versões antigas significam, e um
# campo removido do model não pode sumir do histórico já gravado.
CAMPOS_SNAPSHOT: tuple[str, ...] = (
    "titulo", "descricao", "fundamentacao", "jurisprudencia",
    "contra_argumento", "area_juridica", "tribunal", "magistrado", "tags",
    "observacoes", "gatilhos", "tipo", "status",
)

# Amostra mínima para chamar `taxa_sucesso` de confiança. Abaixo disto, uma
# ficha 1-de-1 mostraria "100%" — número verdadeiro e conclusão falsa, que é
# pior que número nenhum quando um advogado decide a tese da peça por ele.
MIN_AMOSTRA_CONFIANCA = 5

MOTIVOS_QUE_PEDEM_REVISAO = ("erro_na_ficha", "jurisprudencia_virou")
# A partir de quantas recusas por esses motivos a ficha é sinalizada. Dois é
# deliberadamente baixo: uma recusa pode ser o caso; duas já são padrão.
LIMIAR_REVISAO = 2

JUSTIFICATIVA_MIN = 15


class FichaVivaErro(ValueError):
    """Violação de domínio da ficha — o chamador traduz para HTTP 422."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _valor_serializavel(valor):
    """Enum → seu `.value`; o resto passa direto. O snapshot vai para JSONB."""
    return getattr(valor, "value", valor)


def montar_snapshot(tese: Tese) -> dict:
    """Fotografia da ficha no estado atual (o `conteudo` de `TeseVersao`)."""
    return {c: _valor_serializavel(getattr(tese, c, None)) for c in CAMPOS_SNAPSHOT}


def houve_mudanca(tese: Tese, anterior: dict | None) -> bool:
    """Compara o estado atual com o último snapshot.

    Existe para que salvar uma ficha sem alterar nada NÃO gere versão: um
    histórico cheio de versões idênticas é tão inútil quanto não ter histórico —
    ninguém consegue achar a mudança que importa no meio do ruído."""
    if anterior is None:
        return True
    return montar_snapshot(tese) != {c: anterior.get(c) for c in CAMPOS_SNAPSHOT}


async def registrar_versao(
    db, tese: Tese, *, user_id: str | None = None,
    resumo_mudanca: str | None = None, forcar: bool = False,
) -> TeseVersao | None:
    """Grava a fotografia ATUAL da ficha e avança `tese.versao`.

    Chame DEPOIS de aplicar as alterações e ANTES do commit, na mesma
    transação: versão gravada sem a alteração correspondente (ou vice-versa) é
    exatamente a classe de defeito que o CLAUDE.md marca como recorrente
    ("fluxo que grava em duas tabelas → verifique a transação").

    Devolve `None` quando nada mudou desde a última versão (a menos que
    `forcar`), sem tocar em `tese.versao`.
    """
    ultima = await _ultima_versao(db, tese.id)
    if not forcar and not houve_mudanca(tese, ultima.conteudo if ultima else None):
        return None

    proxima = (ultima.versao + 1) if ultima else 1
    versao = TeseVersao(
        id=str(uuid4()),
        tese_id=tese.id,
        versao=proxima,
        conteudo=montar_snapshot(tese),
        resumo_mudanca=(resumo_mudanca or "").strip()[:2000] or None,
        criado_por=user_id,
    )
    db.add(versao)
    tese.versao = proxima
    return versao


async def _ultima_versao(db, tese_id: str) -> TeseVersao | None:
    from sqlalchemy import desc, select
    return (await db.execute(
        select(TeseVersao)
        .where(TeseVersao.tese_id == tese_id)
        .order_by(desc(TeseVersao.versao))
        .limit(1)
    )).scalar_one_or_none()


async def historico(db, tese_id: str, limite: int = 50) -> list[TeseVersao]:
    from sqlalchemy import desc, select
    return list((await db.execute(
        select(TeseVersao)
        .where(TeseVersao.tese_id == tese_id)
        .order_by(desc(TeseVersao.versao))
        .limit(max(1, min(limite, 200)))
    )).scalars())


def diferenca_entre_versoes(anterior: dict, posterior: dict) -> dict[str, dict]:
    """Campos que mudaram entre duas fotografias — `{campo: {de, para}}`.

    O histórico só serve se alguém conseguir ler o que mudou sem comparar dois
    blocos de texto a olho."""
    saida: dict[str, dict] = {}
    for campo in CAMPOS_SNAPSHOT:
        de, para = (anterior or {}).get(campo), (posterior or {}).get(campo)
        if de != para:
            saida[campo] = {"de": de, "para": para}
    return saida


# ── Lastro (fontes) ──────────────────────────────────────────────────────────

async def adicionar_fonte(
    db, *, tese_id: str, elemento: str, referencia: str, trecho: str,
    fonte_url: str | None = None, knowledge_doc_id: str | None = None,
    authority_record_id: str | None = None,
    status_verificacao: str = "nao_verificada", user_id: str | None = None,
) -> TeseFonte:
    """Liga um elemento da ficha a uma fonte REAL, com o texto dela.

    Invariantes (fail-closed, espelhando `AuthorityRecord`):
      • `trecho` obrigatório — fonte sem o texto que ela diz não é verificável,
        e referência solta é exatamente o formato de uma citação alucinada;
      • `verificada` exige vínculo com a base curada (`knowledge_doc_id`) ou com
        um precedente colhido (`authority_record_id`), ou uma URL oficial. Sem
        nenhum dos três, "verificada" seria só uma palavra digitada.
    """
    if elemento not in ELEMENTOS_FONTE:
        raise FichaVivaErro(
            f"elemento inválido: {elemento!r}. Use um de {list(ELEMENTOS_FONTE)}.")
    if status_verificacao not in STATUS_FONTE:
        raise FichaVivaErro(
            f"status_verificacao inválido: {status_verificacao!r}. "
            f"Use um de {list(STATUS_FONTE)}.")
    referencia = (referencia or "").strip()
    trecho = (trecho or "").strip()
    if not referencia:
        raise FichaVivaErro("referência da fonte é obrigatória.")
    if not trecho:
        raise FichaVivaErro(
            "trecho da fonte é obrigatório: uma referência sem o texto que ela "
            "diz não é verificável.")
    if fonte_url and not _url_http(fonte_url):
        raise FichaVivaErro(
            "fonte_url deve ser http(s) — a URL é renderizada como link no "
            "painel da ficha.")

    # ── O selo "verificada" não pode ser auto-atribuível ─────────────────────
    # Achado do pente fino de 03/09. A regra anterior aceitava QUALQUER
    # `fonte_url` (só `max_length`), então `fonte_url="x"` bastava para marcar
    # "verificada". E o selo não é cosmético: `context_builder._lastro_das_fichas`
    # seleciona exatamente `status_verificacao == "verificada"` e injeta a fonte
    # no dossiê do redator com o rótulo `[FONTE VERIFICADA]`, enquanto a
    # `fundamentacao` do próprio catálogo vai como `[NÃO VERIFICADA]`. Ou seja:
    # texto digitado à mão virava a autoridade citável da peça, e o texto curado
    # virava mera pista — a hierarquia de confiança INVERTIDA.
    #
    # Agora "verificada" exige lastro que o SISTEMA consegue conferir: um
    # documento da base curada ou um precedente registrado que EXISTEM de fato
    # (conferidos por SELECT), ou uma URL de domínio OFICIAL (mesma allowlist de
    # `knowledge_governance.fonte_oficial`, reutilizada — não uma cópia).
    # Referência que ainda não foi ingerida continua registrável: fica
    # `nao_verificada`, com a URL guardada. É o status honesto.
    if status_verificacao == "verificada":
        await _exigir_lastro_conferivel(
            db, knowledge_doc_id, authority_record_id, fonte_url)

    fonte = TeseFonte(
        id=str(uuid4()), tese_id=tese_id, elemento=elemento,
        referencia=referencia[:300], trecho=trecho, fonte_url=fonte_url,
        knowledge_doc_id=knowledge_doc_id, authority_record_id=authority_record_id,
        status_verificacao=status_verificacao,
        verificado_em=_agora() if status_verificacao == "verificada" else None,
        criado_por=user_id,
    )
    db.add(fonte)
    return fonte


def _url_http(url: str | None) -> bool:
    from urllib.parse import urlparse
    try:
        return urlparse(str(url or "")).scheme in ("http", "https")
    except ValueError:
        return False


async def _exigir_lastro_conferivel(
    db, knowledge_doc_id: str | None, authority_record_id: str | None,
    fonte_url: str | None,
) -> None:
    """Levanta `FichaVivaErro` se nada do que sustenta o selo "verificada" for
    conferível. Ver o bloco em `adicionar_fonte` para o porquê."""
    from sqlalchemy import select
    from app.services.knowledge_governance import fonte_oficial

    if fonte_url and fonte_oficial(fonte_url):
        return

    if authority_record_id and db is not None:
        from app.models.matriz_teses import AuthorityRecord
        existe = (await db.execute(
            select(AuthorityRecord.id)
            .where(AuthorityRecord.id == authority_record_id)
        )).first()
        if existe:
            return

    if knowledge_doc_id and db is not None:
        # Mesmo gate do RAG: um documento que o usuário não poderia recuperar
        # também não pode lastrear a ficha institucional.
        from sqlalchemy import text as _text
        from app.services.ai_service import _filtros_gate_rag
        existe = (await db.execute(
            _text("SELECT kd.id FROM knowledge_docs kd "
                  "WHERE kd.id = :did AND kd.deleted_at IS NULL "
                  + _filtros_gate_rag(False) + " LIMIT 1"),
            {"did": knowledge_doc_id},
        )).first()
        if existe:
            return

    raise FichaVivaErro(
        "fonte marcada como 'verificada' exige lastro conferível: um documento "
        "da base curada ou um precedente registrado que existam de fato, ou uma "
        "URL de domínio oficial (planalto.gov.br, *.jus.br…). Referência ainda "
        "não ingerida deve ficar como 'nao_verificada' — a URL fica guardada."
    )


async def fontes_da_ficha(db, tese_id: str) -> list[TeseFonte]:
    from sqlalchemy import select
    return list((await db.execute(
        select(TeseFonte).where(TeseFonte.tese_id == tese_id)
        .order_by(TeseFonte.elemento, TeseFonte.criado_em)
    )).scalars())


def cobertura_de_fontes(fontes: list[TeseFonte]) -> dict:
    """Quanto da ficha está lastreado — e em quê.

    Sem isso, uma ficha com 12 fontes não verificadas e outra com 2 verificadas
    parecem igualmente sólidas na tela."""
    verificadas = sum(1 for f in fontes if f.status_verificacao == "verificada")
    elementos = {f.elemento for f in fontes}
    return {
        "total": len(fontes),
        "verificadas": verificadas,
        "nao_verificadas": len(fontes) - verificadas,
        "elementos_cobertos": sorted(elementos),
        "elementos_sem_fonte": sorted(set(ELEMENTOS_FONTE) - elementos),
    }


# ── Recusa (overrides) ───────────────────────────────────────────────────────

async def registrar_override(
    db, *, tese: Tese, case_id: str, motivo: str, justificativa: str,
    user_id: str | None = None,
) -> TeseOverride:
    """Registra que a ficha foi AFASTADA num caso concreto.

    Não mexe em `vezes_usada`/`vezes_venceu`/`vezes_perdeu`: aquelas métricas
    medem RESULTADO de aplicação (`tese_caso_links`); esta mede NÃO-aplicação.
    Misturar as duas faria uma ficha recusada dez vezes parecer uma ficha
    derrotada dez vezes — diagnósticos opostos.
    """
    if motivo not in MOTIVOS_OVERRIDE:
        raise FichaVivaErro(
            f"motivo inválido: {motivo!r}. Use um de {list(MOTIVOS_OVERRIDE)}.")
    justificativa = (justificativa or "").strip()
    if len(justificativa) < JUSTIFICATIVA_MIN:
        raise FichaVivaErro(
            f"justificativa é obrigatória (mín. {JUSTIFICATIVA_MIN} caracteres): "
            "é ela que transforma a recusa em sinal para revisar o catálogo.")

    override = TeseOverride(
        id=str(uuid4()), tese_id=tese.id, case_id=case_id,
        versao_tese=tese.versao, motivo=motivo,
        justificativa=justificativa[:4000], criado_por=user_id,
    )
    db.add(override)
    return override


async def overrides_da_ficha(
    db, tese_id: str, *, visivel_para=None,
) -> list[TeseOverride]:
    """Recusas da ficha. Com `visivel_para` (um `User`), devolve SÓ as de casos
    que aquele usuário pode abrir.

    O filtro é obrigatório em qualquer superfície que exponha `case_id` ou
    `justificativa`: a justificativa é texto livre escrito por um advogado
    SOBRE UM CASO CONCRETO — "não aplicamos porque a vítima é menor e o
    padrasto confessou" é conteúdo do caso, não metadado da ficha. Sem filtro,
    um estagiário (que está em EQUIPE_JURIDICA) leria isso de qualquer caso do
    escritório, inclusive de caso com `sigilo_reforcado`. Mesmo predicado de
    `casos_candidatos` no router: gestão (socio+) vê tudo; equipe vê apenas os
    casos em que é responsável ou auxiliar.

    `visivel_para=None` devolve TUDO e existe só para uso agregado — a contagem
    por motivo de `sinal_de_revisao`, que não expõe caso nenhum.
    """
    from sqlalchemy import desc, or_, select
    from app.core.security import ROLE_LEVEL
    from app.models.case import Case

    q = (select(TeseOverride)
         .where(TeseOverride.tese_id == tese_id)
         .order_by(desc(TeseOverride.criado_em)))
    if visivel_para is not None and (
        ROLE_LEVEL.get(getattr(visivel_para.role, "value", visivel_para.role), 0)
        < ROLE_LEVEL["socio"]
    ):
        q = q.join(Case, Case.id == TeseOverride.case_id).where(
            Case.deleted_at.is_(None),
            or_(Case.advogado_responsavel_id == visivel_para.id,
                Case.advogado_auxiliar_id == visivel_para.id),
        )
    return list((await db.execute(q)).scalars())


def sinal_de_revisao(overrides: list[TeseOverride]) -> dict:
    """A ficha precisa ser revista? Determinístico, por contagem de motivo.

    `erro_na_ficha` e `jurisprudencia_virou` repetidos dizem que o problema é a
    ficha, não o caso. `fato_distinto` repetido diz outra coisa — o gatilho está
    largo demais e a ficha é oferecida onde não cabe."""
    contagem: dict[str, int] = {}
    for o in overrides:
        contagem[o.motivo] = contagem.get(o.motivo, 0) + 1

    motivos_criticos = sum(contagem.get(m, 0) for m in MOTIVOS_QUE_PEDEM_REVISAO)
    precisa = motivos_criticos >= LIMIAR_REVISAO
    gatilho_largo = contagem.get("fato_distinto", 0) >= LIMIAR_REVISAO

    recomendacoes: list[str] = []
    if precisa:
        recomendacoes.append(
            f"{motivos_criticos} recusa(s) por erro na ficha ou mudança de "
            "orientação — revise fundamentação e jurisprudência antes de a "
            "ficha ser oferecida de novo.")
    if gatilho_largo:
        recomendacoes.append(
            f"{contagem['fato_distinto']} recusa(s) por fato distinto — o "
            "gatilho provavelmente está largo demais e a ficha está sendo "
            "oferecida em casos onde não cabe.")
    return {
        "precisa_revisao": precisa,
        "gatilho_largo": gatilho_largo,
        "total_overrides": len(overrides),
        "por_motivo": contagem,
        "recomendacoes": recomendacoes,
    }


# ── Confiança MEDIDA ─────────────────────────────────────────────────────────

def confianca(tese: Tese, overrides: list[TeseOverride] | None = None) -> dict:
    """Confiança da ficha — medida, com a amostra declarada junto.

    `Tese.taxa_sucesso` sozinha mente por omissão: 1 vitória em 1 uso vira
    "100%". Aqui a taxa só é apresentada como confiança acima de
    `MIN_AMOSTRA_CONFIANCA`; abaixo disso o rótulo é `amostra_insuficiente` e a
    taxa vai junto, rotulada, para o advogado ver o número sem ser induzido por
    ele. Nenhum modelo opina: é contagem.
    """
    venceu = int(getattr(tese, "vezes_venceu", 0) or 0)
    perdeu = int(getattr(tese, "vezes_perdeu", 0) or 0)
    decididos = venceu + perdeu
    taxa = (venceu / decididos) if decididos else None

    if decididos < MIN_AMOSTRA_CONFIANCA:
        rotulo = "amostra_insuficiente"
    elif taxa >= 0.75:
        rotulo = "alta"
    elif taxa >= 0.5:
        rotulo = "media"
    else:
        rotulo = "baixa"

    saida = {
        "rotulo": rotulo,
        "taxa_sucesso": round(taxa, 4) if taxa is not None else None,
        "casos_decididos": decididos,
        "vezes_venceu": venceu,
        "vezes_perdeu": perdeu,
        "amostra_minima": MIN_AMOSTRA_CONFIANCA,
        "explicacao": (
            f"{venceu} de {decididos} caso(s) decidido(s)."
            if decididos else "Nenhum caso decidido ainda."
        ),
    }
    if rotulo == "amostra_insuficiente" and decididos:
        saida["explicacao"] += (
            f" Amostra abaixo de {MIN_AMOSTRA_CONFIANCA} — a taxa é verdadeira, "
            "mas não sustenta conclusão sobre a ficha.")
    if overrides is not None:
        saida["revisao"] = sinal_de_revisao(overrides)
    return saida


# ── Gatilhos ─────────────────────────────────────────────────────────────────

def normalizar_gatilhos(valor) -> list[str]:
    """Aceita lista, JSON em string ou CSV; devolve lista limpa e sem repetição.

    Tolerante na entrada porque o gatilho vem de três lugares — formulário,
    import e sugestão de IA — e recusar por formato faria o campo simplesmente
    não ser preenchido, que é o pior resultado possível para ele."""
    if valor is None:
        return []
    itens: list = []
    limpar_sintaxe = False
    if isinstance(valor, str):
        texto = valor.strip()
        if texto.startswith("["):
            try:
                itens = json.loads(texto)
            except (ValueError, TypeError):
                # JSON quebrado (aspas faltando, colchete não fechado): cai
                # para CSV e LIMPA os restos de sintaxe, senão o gatilho fica
                # gravado como `["a"` — salvo, porém inútil. A limpeza só vale
                # neste caminho: um gatilho legítimo pode conter aspas.
                itens = texto.split(",")
                limpar_sintaxe = True
        else:
            itens = texto.split(",")
    elif isinstance(valor, (list, tuple)):
        itens = list(valor)
    else:
        return []

    saida, vistos = [], set()
    for item in itens:
        bruto = str(item or "")
        if limpar_sintaxe:
            bruto = bruto.strip().strip("[]").strip().strip('"\'')
        limpo = " ".join(bruto.split())[:200]
        chave = limpo.casefold()
        if limpo and chave not in vistos:
            vistos.add(chave)
            saida.append(limpo)
    return saida[:30]
