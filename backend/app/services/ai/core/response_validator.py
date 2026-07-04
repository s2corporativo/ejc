# ── app/services/ai/core/response_validator.py ───────────────────────────────
# VALIDADOR DE RESPOSTA do Núcleo Único de IA.
#
# Três verificações pós-modelo, ANTES de devolver ao usuário:
#   1. Citações: súmulas/artigos citados são conferidos contra a base oficial
#      (citation_check — lookup exato, anti-alucinação) quando o agente exige fonte.
#   2. Promessa de resultado (vedação ética OAB): detecta e ALERTA — nunca
#      reescreve o texto (a reescrita esconderia o problema do revisor humano).
#   3. Base verificável: tarefa que exige fonte sem NENHUMA fonte RAG nem
#      citação confirmada → resposta prefixada com "SEM BASE VERIFICÁVEL".
from __future__ import annotations
import re

# Vedação de promessa de resultado (Código de Ética OAB, art. 34, e provimentos).
_RE_PROMESSAS = [
    re.compile(r"garant\w*\s+(?:de\s+|o\s+|a\s+)?(?:êxito|exito|resultado|vitória|vitoria|sucesso|ganho)", re.I),
    re.compile(r"certeza\s+de\s+(?:êxito|exito|vitória|vitoria|sucesso|ganhar)", re.I),
    re.compile(r"\b(?:vamos|iremos|vai|irá|ira)\s+(?:certamente\s+)?ganhar\s+(?:a\s+causa|o\s+processo|a\s+ação|a\s+acao)", re.I),
    re.compile(r"100%\s*de\s*(?:chance|êxito|exito|certeza|sucesso)", re.I),
    re.compile(r"êxito\s+(?:é\s+)?garantido|exito\s+(?:é\s+)?garantido", re.I),
]

PREFIXO_SEM_BASE = (
    "SEM BASE VERIFICÁVEL: a resposta abaixo não pôde ser ancorada em fontes "
    "da base interna. Verifique manualmente antes de qualquer uso.\n\n"
)


def detectar_promessa_resultado(texto: str) -> list[str]:
    """Retorna os trechos (curtos) que aparentam prometer resultado."""
    achados: list[str] = []
    for rx in _RE_PROMESSAS:
        for m in rx.finditer(texto or ""):
            achados.append(m.group(0)[:80])
    return achados


async def validar(
    db,
    conteudo: str,
    *,
    exige_fonte: bool = False,
    fontes: list[dict] | None = None,
) -> dict:
    """
    Valida a resposta do modelo. Retorna:
      {conteudo, citacoes|None, sem_base_verificavel, alertas, revisao_obrigatoria}

    Não altera o teor do texto — apenas prefixa o aviso "SEM BASE VERIFICÁVEL"
    quando aplicável e anexa alertas para o revisor humano (HITL).
    """
    alertas: list[str] = []
    revisao_obrigatoria = False
    citacoes: dict | None = None

    # Política do gate antialucinação (Fase 4 — citation_gate):
    # "desligado" pula a verificação; "bloquear" antecipa ao revisor que a
    # aprovação HITL exigirá override se houver citação bloqueante.
    from app.services.citation_gate import politica_citacoes, avaliar_bloqueantes
    politica = politica_citacoes()

    # 1. Citações contra a base oficial (só quando a tarefa exige fonte).
    if exige_fonte and db is not None and politica != "desligado":
        from app.services.citation_check import verificar_citacoes
        try:
            citacoes = await verificar_citacoes(db, conteudo)
        except Exception:
            # Falha da verificação não derruba a resposta — vira alerta HITL.
            citacoes = None
            alertas.append(
                "Verificação automática de citações indisponível — confira "
                "manualmente todas as súmulas/artigos citados."
            )
            revisao_obrigatoria = True
        if citacoes and citacoes.get("nao_encontradas"):
            alertas.append(
                f"{citacoes['nao_encontradas']} citação(ões) NÃO confirmada(s) "
                "na base oficial — verificação manual obrigatória (OAB)."
            )
            revisao_obrigatoria = True
        if citacoes:
            bloqueantes = avaliar_bloqueantes(citacoes)
            if bloqueantes and politica == "bloquear":
                alertas.append(
                    f"{len(bloqueantes)} citação(ões) BLOQUEANTE(s) (política "
                    "'bloquear'): a aprovação HITL exigirá correção do texto "
                    "ou override justificado do revisor."
                )
                revisao_obrigatoria = True

    # 2. Vedação de promessa de resultado — alerta, nunca reescrita.
    promessas = detectar_promessa_resultado(conteudo)
    if promessas:
        alertas.append(
            "Possível promessa de resultado detectada (vedação OAB): "
            + "; ".join(f"\"{p}\"" for p in promessas[:3])
            + ". Remova/reformule antes de qualquer uso."
        )
        revisao_obrigatoria = True

    # 3. Tarefa exige fonte e não há NENHUMA âncora verificável.
    tem_fonte_rag = bool(fontes)
    tem_citacao_conf = bool(citacoes and citacoes.get("confirmadas"))
    sem_base = exige_fonte and not tem_fonte_rag and not tem_citacao_conf
    if sem_base:
        conteudo = PREFIXO_SEM_BASE + (conteudo or "")
        revisao_obrigatoria = True

    return {
        "conteudo": conteudo,
        "citacoes": citacoes,
        "sem_base_verificavel": sem_base,
        "alertas": alertas,
        "revisao_obrigatoria": revisao_obrigatoria,
    }
