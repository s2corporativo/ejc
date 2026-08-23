# ── app/services/impacto_regulatorio.py ──────────────────────────────────────
# Impacto de publicação regulatória sobre o BANCO DE TESES
# (frente 1 de docs/estrategia/EVOLUCAO_ESTRATEGICA_EJC.md).
#
# O radar do EJC já responde "publicação nova → quais EMPRESAS ela atinge":
# `modules/dpt360/radar_service.py` classifica cada alerta de
# `diario_oficial_alertas` numa área e cruza com a carteira de clientes. O que
# faltava era o alvo jurídico — "esta publicação nova mexe com a TESE X" —, que
# é o que a frente 1 pede.
#
# Por isso este módulo NÃO reimplementa nada: reusa `classify_area` e
# `AREA_CASE_ALIASES` do radar (uma taxonomia só, não duas que divergem com o
# tempo) e a composição de score do `tese_caso_matcher` (um peso só). O que é
# novo aqui é apenas a REGRA DE ALINHAMENTO entre a área da publicação e a área
# jurídica da tese, que é por equivalência, não por igualdade.
#
# INVARIANTES:
#   • 100% DETERMINÍSTICO — sem IA. É navegação sobre texto público de Diário
#     Oficial; não há conteúdo jurídico sendo produzido, não há PII saindo.
#   • FUNÇÕES PURAS — sem banco e sem rede. Quem consulta e aplica o gate de
#     visibilidade dos alertas é o router.
#   • SUGESTÃO, NUNCA VEREDITO — a saída diz "esta publicação PODE afetar esta
#     tese, e estes foram os termos que casaram". Reler a tese à luz da
#     publicação continua sendo trabalho do advogado.
from __future__ import annotations

from app.modules.dpt360.radar_service import AREA_CASE_ALIASES, classify_area
from app.services.tese_caso_matcher import (
    PISO_RELEVANCIA_PADRAO,
    normalizar,
    pontuar_texto,
)

# Tetos de varredura. O cruzamento é O(publicações × teses × termos) em memória:
# sem teto, uma janela larga numa base grande vira resposta lenta e enorme.
# 300 é o mesmo teto de classificação que o radar do DPT360 já usa.
MAX_PUBLICACOES_VARRIDAS = 300
MAX_TESES_VARRIDAS = 500

# Publicações listadas por tese na resposta. O total real vai junto, para que
# "3 publicações" nunca seja lido como "só existem 3".
MAX_PUBLICACOES_POR_TESE = 5


def area_alinhada(area_publicacao: str | None, area_tese: object) -> bool:
    """A área da publicação corresponde à área jurídica da tese?

    Não é igualdade de string: os dois vocabulários são diferentes de propósito.
    A publicação é classificada no vocabulário do radar (`tributario`,
    `ambiental`, `administrativo`, `trabalhista`, `lgpd_ia`) e a tese usa o
    vocabulário de área jurídica do escritório (`tributario`, `licitacoes`,
    `digital_lgpd`...). `AREA_CASE_ALIASES` é a ponte que o radar já mantém —
    reusá-la evita uma segunda tabela de equivalências divergindo em silêncio.

    `geral` (a classificação de quando nada casa) não alinha com nada: seria
    reforçar score por ausência de sinal.
    """
    aliases = AREA_CASE_ALIASES.get(str(area_publicacao or ""), set())
    alvo = normalizar(area_tese)
    return bool(alvo) and alvo in {normalizar(a) for a in aliases}


def classificar_publicacao(publicacao: dict) -> str:
    """Área da publicação, pelo mesmo classificador do radar do DPT360."""
    return classify_area(
        publicacao.get("keyword_match"),
        publicacao.get("titulo"),
        publicacao.get("resumo"),
    )


def _texto_publicacao(publicacao: dict) -> str:
    return " ".join(str(publicacao.get(c) or "") for c in
                    ("titulo", "resumo", "keyword_match"))


def ranquear_teses_afetadas(
    teses: list[dict],
    publicacoes: list[dict],
    *,
    piso: int = PISO_RELEVANCIA_PADRAO,
    limite: int = 20,
) -> list[dict]:
    """Cruza publicações × teses e devolve as teses possivelmente afetadas.

    `teses`: dicts com `id`, `titulo`, `descricao`, `tags`, `area_juridica`.
    `publicacoes`: dicts com `id`, `titulo`, `resumo`, `keyword_match` e o que
    mais o router quiser repassar (`fonte`, `link`, `data_publicacao`).

    A saída é agrupada POR TESE — e não por publicação — porque a pergunta do
    advogado é "o que eu preciso reler", não "o que saiu no Diário". Cada tese
    traz as publicações que a atingiram, com os termos que casaram: score sem
    justificativa convida a confiar sem conferir.

    Empates são desempatados por id, senão a mesma consulta devolve listas em
    ordens diferentes conforme a ordem de chegada do SELECT.
    """
    if not teses or not publicacoes:
        return []

    # Classificar a publicação uma vez só, não uma vez por tese.
    contexto = [
        (pub, classificar_publicacao(pub), _texto_publicacao(pub))
        for pub in publicacoes[:MAX_PUBLICACOES_VARRIDAS]
    ]

    afetadas: list[dict] = []
    for tese in teses[:MAX_TESES_VARRIDAS]:
        termos = tese.get("termos") or []
        if not termos:
            continue

        atingiram: list[dict] = []
        for pub, area_pub, texto in contexto:
            alinhada = area_alinhada(area_pub, tese.get("area_juridica"))
            score, casados = pontuar_texto(termos, texto, area_alinhada=alinhada)
            if score < piso:
                continue
            atingiram.append({
                "alerta_id": pub.get("id"),
                "fonte": pub.get("fonte"),
                "titulo": pub.get("titulo"),
                "link": pub.get("link"),
                "data_publicacao": pub.get("data_publicacao"),
                "area_classificada": area_pub,
                "score": score,
                "termos_casados": casados,
                "area_alinhada": alinhada,
            })

        if not atingiram:
            continue

        atingiram.sort(key=lambda p: (-p["score"], str(p.get("alerta_id") or "")))
        afetadas.append({
            "tese_id": tese.get("id"),
            "titulo": tese.get("titulo"),
            "area_juridica": tese.get("area_juridica"),
            "score_maximo": atingiram[0]["score"],
            "total_publicacoes": len(atingiram),
            "publicacoes": atingiram[:MAX_PUBLICACOES_POR_TESE],
        })

    afetadas.sort(key=lambda t: (-t["score_maximo"], str(t.get("tese_id") or "")))
    return afetadas[:limite]
