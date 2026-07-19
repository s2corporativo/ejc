"""Utilitários puros para leitura auditável de documentos extensos."""
from __future__ import annotations


def dividir_documento_em_blocos(
    texto: str,
    *,
    tamanho: int = 16_000,
    sobreposicao: int = 500,
) -> list[str]:
    """Divide texto longo sem descartar silenciosamente o final.

    Procura uma quebra de linha próxima do limite e mantém pequena sobreposição
    para não perder o contexto na fronteira. A função é determinística e pura.
    """
    texto = (texto or "").replace("\x00", "").strip()
    if not texto:
        return []
    if tamanho < 2_000:
        raise ValueError("tamanho de bloco muito pequeno")
    if sobreposicao < 0 or sobreposicao >= tamanho // 2:
        raise ValueError("sobreposição inválida")

    blocos: list[str] = []
    inicio = 0
    total = len(texto)
    while inicio < total:
        fim_proposto = min(inicio + tamanho, total)
        fim = fim_proposto
        if fim_proposto < total:
            # Evita cortar no meio de um parágrafo quando houver uma quebra
            # razoavelmente próxima; nunca recua mais que 30% do bloco.
            limite_recuo = inicio + int(tamanho * 0.70)
            quebra = texto.rfind("\n", limite_recuo, fim_proposto)
            if quebra > inicio:
                fim = quebra
        bloco = texto[inicio:fim].strip()
        if bloco:
            blocos.append(bloco)
        if fim >= total:
            break
        inicio = max(fim - sobreposicao, inicio + 1)
    return blocos
