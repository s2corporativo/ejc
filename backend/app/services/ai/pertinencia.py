# ── app/services/ai/pertinencia.py ──────────────────────────────────────────
# VALIDAÇÃO DE PERTINÊNCIA — a autoridade citada SUSTENTA a afirmação?
#
# O EJC já valida EXISTÊNCIA da citação (`verificador_jurisprudencia` +
# `citation_gate`): o número CNJ tem DV válido, a súmula está na base curada, o
# artigo consta do diploma certo e vigente. Nada disso responde a pergunta que
# derruba uma peça na audiência: *o dispositivo citado diz o que a peça afirma
# que ele diz?*
#
# É o erro que sobrevive a todos os gates atuais e chega ao juiz: citar o art.
# 373, I do CPC (existe, vigente, diploma certo) para sustentar inversão do ônus
# da prova — que é o inciso VIII do art. 6º do CDC. A citação passa em todos os
# testes de existência e está errada.
#
# COMO A VERIFICAÇÃO É FEITA (e por que ela não é "mais uma opinião da IA")
#
# A IA não é consultada sobre o Direito. Ela recebe DOIS textos — a afirmação da
# peça e o TEXTO REAL da autoridade, lido da base curada — e responde uma única
# pergunta fechada, obrigada a TRANSCREVER LITERALMENTE o trecho da autoridade
# que sustentaria a afirmação. O trecho transcrito é então conferido
# PROGRAMATICAMENTE contra o texto da autoridade: se não ocorrer lá, o veredito
# é descartado e vira `indeterminada`. Uma IA que "concorde" inventando o
# fundamento não consegue passar por essa conferência — é a mesma técnica de
# `documento_service._verificar_origens_v2`.
#
# FAIL-CLOSED, MAS SEM FALSO POSITIVO
#
# Só existem três vereditos, e o do meio é honesto:
#   • `sustentada`      — trecho literal confere e a IA afirmou suporte;
#   • `nao_sustentada`  — a IA afirmou que a autoridade NÃO ampara (bloqueante);
#   • `indeterminada`   — não deu para verificar (sem texto da autoridade na
#                         base, IA desligada/indisponível, trecho não confere).
#
# `indeterminada` NUNCA bloqueia e NUNCA é apresentada como aprovação. Um
# julgado confirmado só no DataJud, por exemplo, não tem ementa na base: dizer
# "pertinente" ali seria inventar. O revisor humano vê "não verificada".
#
# ESCOPO v1 (declarado, não escondido): verifica `sumula` e `artigo`, os dois
# tipos cujo TEXTO existe na base curada. Julgados (`processo_cnj`, `recurso`)
# ficam `indeterminada` com motivo explícito até a base ter ementa deles — a
# ingestão de ementas é o que destrava esse tipo, não uma mudança aqui.
from __future__ import annotations

import logging
import re
import unicodedata

from pydantic import BaseModel, Field

from app.core.config import get_settings

logger = logging.getLogger("ejc.ai.pertinencia")

TASK_TYPE = "verificacao_pertinencia"

SUSTENTADA = "sustentada"
NAO_SUSTENTADA = "nao_sustentada"
INDETERMINADA = "indeterminada"

# Tipos cujo TEXTO íntegro existe na base curada e portanto podem ser
# confrontados. Ampliar exige que a ingestão traga o texto do tipo novo.
TIPOS_VERIFICAVEIS = frozenset({"sumula", "artigo"})

# Teto de citações confrontadas por chamada: cada uma é uma ida ao provedor.
# Excedente vira `indeterminada` com motivo — nunca silêncio.
MAX_POR_CHAMADA = 12

# Caracteres de contexto ao redor da citação, quando não há fronteira de frase.
_JANELA = 400
# Texto da autoridade enviado ao modelo (súmula e artigo cabem folgadamente).
_MAX_AUTORIDADE = 4000
# Piso do trecho transcrito: abaixo disto ("o", "da lei") a conferência
# literal não prova nada — casaria por acaso em quase qualquer texto.
_MIN_TRECHO = 25

_MOTIVO_TIPO_SEM_TEXTO = (
    "Pertinência não verificada: a base curada não guarda o inteiro teor deste "
    "tipo de citação, então não há texto contra o qual confrontar a afirmação. "
    "Confira manualmente se o julgado ampara o que a peça afirma."
)
_MOTIVO_SEM_FONTE = (
    "Pertinência não verificada: o texto da autoridade não foi localizado na "
    "base curada. Confira manualmente na fonte oficial."
)
_MOTIVO_IA_INDISPONIVEL = (
    "Pertinência não verificada: a verificação não pôde ser executada. "
    "Confira manualmente se a autoridade ampara a afirmação."
)
_MOTIVO_TRECHO_NAO_CONFERE = (
    "Pertinência DESCARTADA: a verificação apontou suporte mas não conseguiu "
    "transcrever da autoridade um trecho que realmente exista nela — indício de "
    "fundamento inventado. Trate como NÃO verificada e confira manualmente."
)
_MOTIVO_TETO = (
    f"Pertinência não verificada: mais de {MAX_POR_CHAMADA} citações "
    "verificáveis no texto (teto por chamada). Confira manualmente as demais."
)

_SYSTEM = (
    "Você confere PERTINÊNCIA de citação jurídica. Recebe (a) uma AFIRMAÇÃO "
    "extraída de uma peça e (b) o TEXTO da autoridade citada. Responda "
    "APENAS se o texto da autoridade, POR SI, ampara a afirmação.\n"
    "REGRAS ABSOLUTAS:\n"
    "1. Use SOMENTE o TEXTO DA AUTORIDADE fornecido. Não use conhecimento "
    "próprio, memória, nem outra norma ou julgado.\n"
    "2. Para responder SUSTENTADA você é OBRIGADO a transcrever LITERALMENTE, "
    "caractere a caractere, um trecho do TEXTO DA AUTORIDADE que ampare a "
    "afirmação. Trecho parafraseado, resumido ou inventado invalida a "
    "resposta.\n"
    "3. Se a autoridade trata de assunto diferente, ampara apenas em parte, ou "
    "você não encontra trecho literal que sustente, responda NAO_SUSTENTADA.\n"
    "4. Na dúvida, responda NAO_SUSTENTADA. Nunca responda SUSTENTADA para "
    "'ser útil'.\n"
    "FORMATO EXATO da resposta, sem nada além disto:\n"
    "VEREDITO: SUSTENTADA|NAO_SUSTENTADA\n"
    "TRECHO: <transcrição literal do texto da autoridade, ou vazio>\n"
    "MOTIVO: <uma frase>"
)

_RE_VEREDITO = re.compile(r"VEREDITO:\s*(SUSTENTADA|NAO_SUSTENTADA)", re.I)
_RE_TRECHO = re.compile(r"TRECHO:\s*(.*?)(?=\nMOTIVO:|\Z)", re.I | re.S)
_RE_MOTIVO = re.compile(r"MOTIVO:\s*(.+)", re.I)
# Fronteira de frase: ponto final/interrogação/exclamação seguidos de espaço.
# `art.`, `n.`, `S.A.` e afins não são fronteira — daí exigir a maiúscula.
_RE_FIM_FRASE = re.compile(r"[.!?]\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])")


class Pertinencia(BaseModel):
    """Veredito de pertinência de UMA citação."""

    veredito: str = INDETERMINADA
    afirmacao: str = ""
    trecho_autoridade: str | None = None
    fonte: str | None = None
    motivo: str = ""
    # True quando a IA disse SUSTENTADA mas o trecho transcrito não existe na
    # autoridade — sinal forte de fundamento inventado, guardado para auditoria.
    trecho_rejeitado: bool = False

    @property
    def bloqueante(self) -> bool:
        return self.veredito == NAO_SUSTENTADA


class RelatorioPertinencia(BaseModel):
    habilitada: bool = False
    total: int = 0
    sustentadas: int = 0
    nao_sustentadas: int = 0
    indeterminadas: int = 0
    itens: list[dict] = Field(default_factory=list)
    motivos: list[str] = Field(default_factory=list)


def habilitada() -> bool:
    """Opt-in por ambiente (padrão do repo: flag default OFF)."""
    s = get_settings()
    return bool(getattr(s, "PERTINENCIA_ENABLED", False)) and bool(s.AI_ENABLED)


def extrair_afirmacao(texto: str, span: tuple[int, int] | list[int] | None) -> str:
    """A frase da peça que carrega a citação — o que precisa ser sustentado.

    Recorta da fronteira de frase anterior até a seguinte. Sem fronteira (peça
    com parágrafo corrido, comum em petição), cai numa janela de caracteres:
    contexto demais dilui a pergunta, contexto de menos esconde o que a peça
    afirmou. Nunca levanta — texto/span inválidos devolvem string vazia.
    """
    if not texto or not span:
        return ""
    try:
        ini, fim = int(span[0]), int(span[1])
    except (TypeError, ValueError, IndexError):
        return ""
    if ini < 0 or fim > len(texto) or ini >= fim:
        return ""

    esquerda = texto[max(0, ini - _JANELA):ini]
    cortes = list(_RE_FIM_FRASE.finditer(esquerda))
    inicio = max(0, ini - _JANELA) + (cortes[-1].end() if cortes else 0)

    direita = texto[fim:fim + _JANELA]
    corte = _RE_FIM_FRASE.search(direita)
    final = fim + (corte.start() + 1 if corte else len(direita))

    return " ".join(texto[inicio:final].split())


def _normalizar(s: str) -> str:
    """Comparação tolerante ao que NÃO muda o sentido: acento, caixa, espaço e
    aspas tipográficas. O modelo transcreve corretamente e erra a aspa curva ou
    um espaço duplo herdado do PDF — descartar por isso seria falso positivo de
    'trecho inventado'. Tudo além disso continua tendo de conferir."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace("“", '"').replace("”", '"').replace("’", "'").replace("‘", "'")
    s = s.replace("—", "-").replace("–", "-")
    return " ".join(s.lower().split())


def trecho_confere(trecho: str | None, autoridade: str) -> bool:
    """O trecho transcrito ocorre MESMO no texto da autoridade?

    Esta função é a barreira antialucinação da verificação: sem ela, a
    pertinência seria só uma segunda opinião da IA sobre a primeira. Trecho
    curto demais é rejeitado — casaria por acaso e não provaria leitura."""
    limpo = (trecho or "").strip().strip('"').strip()
    if len(limpo) < _MIN_TRECHO:
        return False
    return _normalizar(limpo) in _normalizar(autoridade)


async def texto_da_autoridade(db, citacao: dict) -> tuple[str | None, str | None]:
    """Texto íntegro da autoridade citada, lido da base curada.

    Devolve `(texto, fonte)`; `(None, None)` quando não há texto — nunca
    inventa nem aproxima. Respeita os mesmos filtros de gate do RAG que o
    verificador de existência usa (`_filtros_gate_rag`), então não expõe por
    esta via conteúdo restrito que o fluxo normal não exporia.
    """
    tipo = citacao.get("tipo")
    if tipo not in TIPOS_VERIFICAVEIS or db is None:
        return None, None
    from sqlalchemy import text as _text
    from app.services.ai_service import _filtros_gate_rag

    numero = str(citacao.get("numero") or "").strip()
    if not numero:
        return None, None

    if tipo == "sumula":
        tribunal = (citacao.get("tribunal") or "").strip().lower()
        chaves = (
            [f"sumula:{tribunal}:{numero}"] if tribunal
            else [f"sumula:{t}:{numero}" for t in ("stf", "stj", "tst", "tjmg")]
        )
        linha = (await db.execute(
            _text(
                "SELECT kd.titulo, string_agg(kc.conteudo, E'\\n' ORDER BY kc.ordem) "
                "FROM knowledge_docs kd JOIN knowledge_chunks kc ON kc.doc_id = kd.id "
                "WHERE kd.deleted_at IS NULL AND kd.vigente = TRUE "
                "AND kd.chave_origem = ANY(:k) "
                + _filtros_gate_rag(False)
                + " GROUP BY kd.id, kd.titulo LIMIT 1"
            ),
            {"k": chaves},
        )).first()
    else:  # artigo — reusa o recorte por diploma do verificador (AI-056): o
        # texto tem de vir do diploma REALMENTE citado, nunca de outra lei.
        from app.services.citation_check import _fonte_artigo
        fonte = await _fonte_artigo(db, numero, citacao.get("diploma"), vigente=True)
        if not fonte or not fonte.get("doc_id"):
            return None, None
        linha = (await db.execute(
            _text(
                "SELECT kd.titulo, string_agg(kc.conteudo, E'\\n' ORDER BY kc.ordem) "
                "FROM knowledge_docs kd JOIN knowledge_chunks kc ON kc.doc_id = kd.id "
                "WHERE kd.id = :did AND kd.deleted_at IS NULL "
                + _filtros_gate_rag(False)
                + " GROUP BY kd.id, kd.titulo"
            ),
            {"did": fonte["doc_id"]},
        )).first()

    if not linha or not linha[1]:
        return None, None
    return str(linha[1])[:_MAX_AUTORIDADE], (linha[0] or None)


def _parse(resposta: str) -> tuple[str | None, str, str]:
    m = _RE_VEREDITO.search(resposta or "")
    veredito = m.group(1).lower() if m else None
    t = _RE_TRECHO.search(resposta or "")
    mo = _RE_MOTIVO.search(resposta or "")
    return veredito, (t.group(1).strip() if t else ""), (mo.group(1).strip() if mo else "")


async def avaliar_citacao(
    afirmacao: str,
    autoridade: str,
    fonte: str | None = None,
    modo_sanitizacao=None,
) -> Pertinencia:
    """Confronta UMA afirmação contra o texto de UMA autoridade.

    NUNCA levanta: qualquer falha vira `indeterminada` (a peça segue para o
    revisor humano, que é quem sempre decidiu). `modo_sanitizacao` propaga o
    piso de sigilo do caso — a afirmação vem da peça e carrega os fatos.
    """
    if not afirmacao or not autoridade:
        return Pertinencia(veredito=INDETERMINADA, afirmacao=afirmacao,
                           fonte=fonte, motivo=_MOTIVO_SEM_FONTE)
    from app.services import ai_gateway
    from app.services.ai import delimitador

    tok = delimitador.novo_token()
    user = delimitador.montar(
        delimitador.bloco("AFIRMACAO DA PECA", afirmacao, tok, limite=_JANELA * 2),
        delimitador.bloco("TEXTO DA AUTORIDADE", autoridade, tok,
                          limite=_MAX_AUTORIDADE),
        instrucao_final="Responda no formato exato exigido.",
    )
    try:
        resp = await ai_gateway.chat(
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": user}],
            task_type=TASK_TYPE,
            temperature=0.0,
            max_tokens=400,
            modo_sanitizacao=modo_sanitizacao,
        )
    except Exception as e:
        logger.warning("[pertinencia] verificação indisponível: %s", str(e)[:200])
        return Pertinencia(veredito=INDETERMINADA, afirmacao=afirmacao,
                           fonte=fonte, motivo=_MOTIVO_IA_INDISPONIVEL)

    veredito, trecho, motivo = _parse(resp.texto)
    if veredito is None:
        return Pertinencia(veredito=INDETERMINADA, afirmacao=afirmacao,
                           fonte=fonte, motivo=_MOTIVO_IA_INDISPONIVEL)

    if veredito == SUSTENTADA:
        # A barreira: "sustentada" só vale com trecho que EXISTE na autoridade.
        if not trecho_confere(trecho, autoridade):
            logger.info(
                "[pertinencia] veredito SUSTENTADA descartado — trecho não "
                "confere com a autoridade (%s)", (fonte or "sem título")[:80],
            )
            return Pertinencia(
                veredito=INDETERMINADA, afirmacao=afirmacao, fonte=fonte,
                trecho_autoridade=trecho[:300] or None, trecho_rejeitado=True,
                motivo=_MOTIVO_TRECHO_NAO_CONFERE,
            )
        return Pertinencia(veredito=SUSTENTADA, afirmacao=afirmacao, fonte=fonte,
                           trecho_autoridade=trecho[:300],
                           motivo=motivo or "Trecho da autoridade confere.")

    return Pertinencia(
        veredito=NAO_SUSTENTADA, afirmacao=afirmacao, fonte=fonte,
        motivo=motivo or "A autoridade citada não ampara a afirmação da peça.",
    )


async def avaliar_texto(
    db, texto: str, citacoes: list[dict], modo_sanitizacao=None,
) -> RelatorioPertinencia:
    """Confronta cada citação verificável do texto contra sua autoridade.

    `citacoes` é a lista do `verificador_jurisprudencia` (precisa do `span`,
    para recortar a afirmação). Sequencial de propósito: são poucas por peça
    (teto `MAX_POR_CHAMADA`) e o paralelo multiplicaria o pico de custo e de
    carga no provedor sem ganho perceptível para o revisor.
    """
    if not habilitada():
        return RelatorioPertinencia(habilitada=False)

    itens: list[dict] = []
    motivos: list[str] = []
    verificadas = 0
    for c in citacoes or []:
        # Só faz sentido perguntar "sustenta?" de citação que EXISTE. Para as
        # demais, a existência é o problema, e o gate atual já as trata.
        if c.get("status") != "verificada":
            continue
        if c.get("tipo") not in TIPOS_VERIFICAVEIS:
            itens.append(_item(c, Pertinencia(
                veredito=INDETERMINADA, motivo=_MOTIVO_TIPO_SEM_TEXTO)))
            continue
        if verificadas >= MAX_POR_CHAMADA:
            itens.append(_item(c, Pertinencia(
                veredito=INDETERMINADA, motivo=_MOTIVO_TETO)))
            continue

        try:
            autoridade, fonte = await texto_da_autoridade(db, c)
        except Exception as e:
            logger.warning("[pertinencia] leitura da autoridade falhou: %s", str(e)[:200])
            autoridade, fonte = None, None
        if not autoridade:
            itens.append(_item(c, Pertinencia(
                veredito=INDETERMINADA, motivo=_MOTIVO_SEM_FONTE)))
            continue

        verificadas += 1
        itens.append(_item(c, await avaliar_citacao(
            extrair_afirmacao(texto, c.get("span")), autoridade, fonte,
            modo_sanitizacao=modo_sanitizacao,
        )))

    nao = sum(1 for i in itens if i["veredito"] == NAO_SUSTENTADA)
    sim = sum(1 for i in itens if i["veredito"] == SUSTENTADA)
    indet = len(itens) - nao - sim
    if nao:
        motivos.append(
            f"{nao} citação(ões) cuja autoridade NÃO ampara a afirmação da peça "
            "— erro que passa por todos os testes de existência e é o que cai "
            "na audiência."
        )
    if indet:
        motivos.append(
            f"{indet} citação(ões) com pertinência NÃO verificada — confira "
            "manualmente se a autoridade sustenta o que a peça afirma."
        )
    return RelatorioPertinencia(
        habilitada=True, total=len(itens), sustentadas=sim,
        nao_sustentadas=nao, indeterminadas=indet, itens=itens, motivos=motivos,
    )


def _item(citacao: dict, p: Pertinencia) -> dict:
    return {
        "citacao": citacao.get("citacao") or citacao.get("trecho") or "",
        "tipo": citacao.get("tipo") or "desconhecido",
        "veredito": p.veredito,
        "afirmacao": p.afirmacao[:400],
        "trecho_autoridade": p.trecho_autoridade,
        "fonte": p.fonte or citacao.get("fonte_verificacao"),
        "motivo": p.motivo,
        "trecho_rejeitado": p.trecho_rejeitado,
    }
