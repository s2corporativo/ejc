# ── app/services/evento_processual.py ────────────────────────────────────────
# Catálogo DETERMINÍSTICO de eventos processuais → regra de termo inicial.
#
# Arquitetura obrigatória (Orquestrador Jurídico, Fase 2):
#   • A IA NUNCA calcula — no máximo IDENTIFICA evento/data candidata.
#   • Este módulo resolve o termo inicial de forma 100% determinística, com
#     base legal citada, e SÓ para regras de certeza absoluta; o resto sai
#     como "verificar" (contagem_confirmavel=False, termo_inicial=None).
#   • O termo inicial SEMPRE passa por confirmação humana antes de virar
#     Deadline (gate 422 no POST /motor-peca/gerar — intocado).
#
# SEMÂNTICA DO TERMO INICIAL (crítica para não errar por 1 dia):
#   `termo_inicial` é o DIES A QUO — o "dia do começo do prazo" (CPC art. 231),
#   que é EXCLUÍDO da contagem (CPC art. 224, caput). É exatamente o valor a
#   alimentar em deadline_calculator.prazo_dias_uteis(termo_inicial, N), que
#   começa a contar no dia útil SEGUINTE. O campo `inicio_contagem` informa o
#   1º dia útil efetivamente contado (ex.: CPC art. 224, §3º — "primeiro dia
#   útil que seguir ao da publicação").
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from app.services.deadline_calculator import proximo_dia_util

AVISO_CONFIRMACAO = (
    "Termo inicial derivado deterministicamente do evento — confirmação "
    "humana do advogado é OBRIGATÓRIA antes de criar qualquer prazo fatal."
)

# Meios aceitos como consulta efetiva da intimação eletrônica
_MEIOS_CONSULTA = {"consulta", "consulta_eletronica"}
# Meios que atestam ciência na própria audiência
_MEIOS_AUDIENCIA = {"ciencia_em_audiencia", "audiencia_com_ciencia"}


# ── Catálogo (somente certeza absoluta; demais = "verificar") ────────────────
CATALOGO_EVENTOS: dict[str, dict[str, Any]] = {
    "publicacao_dje": {
        "nome": "Publicação no Diário da Justiça eletrônico (DJe)",
        "base_legal": "CPC, art. 224, §§2º e 3º",
        "descricao": ("Contagem inicia no 1º dia útil que seguir ao da "
                      "publicação (dies a quo = dia da publicação, excluído)."),
    },
    "disponibilizacao_dje": {
        "nome": "Disponibilização no DJe (dia anterior à publicação)",
        "base_legal": "Lei 11.419/2006, art. 4º, §§3º e 4º c/c CPC, art. 224, §§2º e 3º",
        "descricao": ("Considera-se PUBLICAÇÃO o 1º dia útil seguinte à "
                      "disponibilização; a contagem inicia no 1º dia útil "
                      "seguinte à publicação."),
    },
    "intimacao_eletronica": {
        "nome": "Intimação eletrônica em portal próprio (com consulta)",
        "base_legal": "Lei 11.419/2006, art. 5º, §§1º e 3º c/c CPC, art. 231, V",
        "descricao": ("Intimação considera-se realizada no dia da consulta "
                      "efetiva; sem consulta, tacitamente 10 dias corridos "
                      "após o envio (data exata a VERIFICAR nos autos)."),
    },
    "juntada_ar": {
        "nome": "Juntada aos autos do aviso de recebimento (AR)",
        "base_legal": "CPC, art. 231, I",
        "descricao": "Dia do começo do prazo = data da juntada do AR aos autos.",
    },
    "juntada_mandado": {
        "nome": "Juntada aos autos do mandado cumprido (oficial de justiça)",
        "base_legal": "CPC, art. 231, II",
        "descricao": "Dia do começo do prazo = data da juntada do mandado cumprido.",
    },
    "audiencia": {
        "nome": "Audiência (decisão proferida em audiência)",
        "base_legal": "CPC, art. 1.003, §1º (por analogia)",
        "descricao": ("Ciência na própria audiência ⇒ dies a quo = data da "
                      "audiência. Sem confirmação da ciência em audiência, "
                      "a regra é 'verificar'."),
    },
    "ciencia_em_audiencia": {
        "nome": "Ciência/intimação na própria audiência",
        "base_legal": "CPC, art. 1.003, §1º (por analogia)",
        "descricao": "Dies a quo = data da audiência em que houve a ciência.",
    },
    "ciencia_expressa": {
        "nome": "Ciência expressa/inequívoca nos autos",
        "base_legal": ("CPC, art. 239, §1º (comparecimento espontâneo) / "
                       "art. 231, VIII (carga dos autos)"),
        "descricao": ("Dies a quo = data em que a parte manifestou ciência "
                      "inequívoca nos autos (verificada pelo advogado)."),
    },
}

EVENTOS_VALIDOS: tuple[str, ...] = tuple(sorted(CATALOGO_EVENTOS))


def _saida(evento: str, data_evento: date, *, termo: Optional[date],
           confirmavel: bool, base_legal: str,
           avisos: list[str]) -> dict[str, Any]:
    """Formata a resposta padrão do resolvedor (datas como objetos `date`)."""
    inicio_contagem = None
    if termo is not None:
        # 1º dia efetivamente contado = próximo dia útil APÓS o dies a quo
        # (CPC art. 224, caput e §3º) — informativo p/ o advogado conferir.
        inicio_contagem = proximo_dia_util(termo + timedelta(days=1))
    return {
        "evento": evento,
        "nome": CATALOGO_EVENTOS.get(evento, {}).get("nome", evento),
        "data_evento": data_evento,
        "termo_inicial": termo,
        "inicio_contagem": inicio_contagem,
        "contagem_confirmavel": confirmavel,
        "base_legal": base_legal,
        "avisos": avisos,
    }


def resolver_termo_inicial(evento: str, data_evento: date,
                           meio: str | None = None) -> dict[str, Any]:
    """Resolve o termo inicial (dies a quo) a partir do evento processual.

    Retorna {termo_inicial, inicio_contagem, contagem_confirmavel, base_legal,
    avisos, ...}. `termo_inicial=None` + `contagem_confirmavel=False` significa
    "verificar" — o advogado precisa apurar a data nos autos. NUNCA inventa
    regra: evento fora do catálogo sai sempre como "verificar".
    """
    meio_norm = (meio or "").strip().lower() or None
    info = CATALOGO_EVENTOS.get(evento)

    if info is None:
        return _saida(
            evento, data_evento, termo=None, confirmavel=False,
            base_legal="Evento não catalogado — verificar nos autos a regra aplicável",
            avisos=[
                "Evento processual fora do catálogo determinístico — nada foi "
                "presumido. Verifique nos autos a regra do termo inicial e "
                f"informe-o manualmente. Eventos catalogados: {', '.join(EVENTOS_VALIDOS)}.",
            ],
        )

    base = info["base_legal"]

    if evento == "publicacao_dje":
        return _saida(
            evento, data_evento, termo=data_evento, confirmavel=True,
            base_legal=base,
            avisos=[
                "Dies a quo = dia da PUBLICAÇÃO no DJe (excluído da contagem); "
                "a contagem inicia no 1º dia útil seguinte (CPC art. 224, §3º).",
                "Confira se a data informada é a de PUBLICAÇÃO (não a de "
                "disponibilização — para esta, use o evento 'disponibilizacao_dje').",
                AVISO_CONFIRMACAO,
            ],
        )

    if evento == "disponibilizacao_dje":
        publicacao = proximo_dia_util(data_evento + timedelta(days=1))
        return _saida(
            evento, data_evento, termo=publicacao, confirmavel=True,
            base_legal=base,
            avisos=[
                f"Disponibilização em {data_evento.isoformat()} ⇒ considera-se "
                f"PUBLICADO no 1º dia útil seguinte ({publicacao.isoformat()}) — "
                "Lei 11.419/2006, art. 4º, §3º; a contagem inicia no 1º dia útil "
                "seguinte à publicação (art. 4º, §4º c/c CPC art. 224, §3º).",
                AVISO_CONFIRMACAO,
            ],
        )

    if evento == "intimacao_eletronica":
        if meio_norm in _MEIOS_CONSULTA:
            return _saida(
                evento, data_evento, termo=data_evento, confirmavel=True,
                base_legal=base,
                avisos=[
                    "Intimação considera-se realizada no dia da CONSULTA efetiva "
                    "ao teor (Lei 11.419/2006, art. 5º, §1º). Critério CONSERVADOR "
                    "adotado: dies a quo = dia da consulta (a leitura literal do "
                    "CPC art. 231, V — dia útil seguinte à consulta — resultaria "
                    "em vencimento posterior; nunca erramos para depois).",
                    AVISO_CONFIRMACAO,
                ],
            )
        return _saida(
            evento, data_evento, termo=None, confirmavel=False,
            base_legal=base,
            avisos=[
                "Sem a data da CONSULTA efetiva, a intimação eletrônica "
                "considera-se automaticamente realizada ao fim de 10 dias "
                "CORRIDOS contados do envio (Lei 11.419/2006, art. 5º, §3º) — "
                "VERIFICAR nos autos a data do envio/decurso e informar o "
                "termo inicial manualmente.",
                "Se houve consulta, reenvie com meio='consulta' e a data da consulta.",
            ],
        )

    if evento in ("juntada_ar", "juntada_mandado"):
        return _saida(
            evento, data_evento, termo=data_evento, confirmavel=True,
            base_legal=base,
            avisos=[
                "Dies a quo = data da JUNTADA aos autos (excluída da contagem — "
                "CPC art. 224, caput); a contagem inicia no dia útil seguinte.",
                AVISO_CONFIRMACAO,
            ],
        )

    if evento == "audiencia":
        if meio_norm in _MEIOS_AUDIENCIA:
            return _saida(
                evento, data_evento, termo=data_evento, confirmavel=True,
                base_legal=base,
                avisos=[
                    "Ciência na própria audiência ⇒ dies a quo = data da "
                    "audiência (CPC art. 1.003, §1º, por analogia).",
                    AVISO_CONFIRMACAO,
                ],
            )
        return _saida(
            evento, data_evento, termo=None, confirmavel=False,
            base_legal=base,
            avisos=[
                "Não está confirmado que a decisão foi proferida NA audiência "
                "com intimação dos presentes — VERIFICAR a ata. Se confirmado, "
                "reenvie com meio='ciencia_em_audiencia'; caso a intimação "
                "tenha sido posterior (DJe etc.), use o evento correspondente.",
            ],
        )

    if evento == "ciencia_em_audiencia":
        return _saida(
            evento, data_evento, termo=data_evento, confirmavel=True,
            base_legal=base,
            avisos=[
                "Dies a quo = data da audiência em que houve ciência expressa "
                "(CPC art. 1.003, §1º, por analogia) — confira a ata.",
                AVISO_CONFIRMACAO,
            ],
        )

    # ciencia_expressa
    return _saida(
        evento, data_evento, termo=data_evento, confirmavel=True,
        base_legal=base,
        avisos=[
            "Dies a quo = data da ciência inequívoca verificada nos autos "
            "(comparecimento espontâneo — CPC art. 239, §1º — ou carga, "
            "CPC art. 231, VIII). Identifique nos autos o ato que gerou a ciência.",
            AVISO_CONFIRMACAO,
        ],
    )
