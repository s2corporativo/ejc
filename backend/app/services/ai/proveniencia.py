# ── Normalização e validação de proveniência jurídica ─────────────────────────
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from app.schemas.ai_proveniencia import (
    ProvenienciaJuridica,
    RespostaJuridicaRastreavel,
    ResumoConfiabilidadeFontes,
    StatusConferenciaFonte,
    TipoFonteJuridica,
)


class ProvenienciaEscopoError(ValueError):
    """A fonte pertence a outro caso ou não possui escopo verificável."""


_CHAVES_LEGADAS = {
    "filename": "nome_arquivo",
    "file_name": "nome_arquivo",
    "source_name": "nome_arquivo",
    "document_id": "documento_id",
    "doc_id": "documento_id",
    "page": "pagina",
    "page_number": "pagina",
    "excerpt": "trecho",
    "quote": "trecho",
    "process_id": "processo_origem",
    "processo": "processo_origem",
    "source_type": "tipo_fonte",
    "citation_status": "status_conferencia",
    "confidentiality": "nivel_confidencialidade",
    "confidentiality_level": "nivel_confidencialidade",
    "privacy_level": "nivel_confidencialidade",
    "verified_at": "data_verificacao",
    "document_date": "data_documento",
    "document_version": "versao_documento",
    "source_hash": "hash_fonte",
    "official_url": "url_oficial",
    "issuer": "autoridade",
    "is_current": "vigente",
    "extraction_confidence": "confianca_extracao",
    "is_inference": "inferencia_ia",
}

_TIPOS_ESCOPO_CASO = {
    TipoFonteJuridica.DOCUMENTO_CASO,
    TipoFonteJuridica.PECA_INTERNA,
    TipoFonteJuridica.TESE_INTERNA,
}

_STATUS_BLOQUEANTES = {
    StatusConferenciaFonte.NAO_LOCALIZADA,
    StatusConferenciaFonte.POSSIVELMENTE_DESATUALIZADA,
    StatusConferenciaFonte.IDENTIFICACAO_INSUFICIENTE,
}


def _normalizar_chaves(item: Mapping[str, Any]) -> dict[str, Any]:
    normalizado: dict[str, Any] = {}
    metadados_extras: dict[str, Any] = {}
    campos_modelo = set(ProvenienciaJuridica.model_fields)

    for chave, valor in item.items():
        chave_destino = _CHAVES_LEGADAS.get(chave, chave)
        if chave_destino in campos_modelo:
            normalizado[chave_destino] = valor
        else:
            metadados_extras[chave] = valor

    metadados_existentes = normalizado.get("metadados")
    if isinstance(metadados_existentes, Mapping):
        metadados_extras = {**metadados_existentes, **metadados_extras}
    if metadados_extras:
        normalizado["metadados"] = metadados_extras

    return normalizado


def validar_escopo_caso(
    fonte: ProvenienciaJuridica,
    *,
    case_id_esperado: str | None,
) -> None:
    if case_id_esperado is None:
        return

    if fonte.case_id and fonte.case_id != case_id_esperado:
        raise ProvenienciaEscopoError(
            "Fonte rejeitada: case_id diferente do contexto autorizado"
        )

    if fonte.tipo_fonte in _TIPOS_ESCOPO_CASO and not fonte.case_id:
        raise ProvenienciaEscopoError(
            "Fonte interna ou documento do caso sem case_id verificável"
        )


def normalizar_proveniencia(
    item: ProvenienciaJuridica | Mapping[str, Any],
    *,
    case_id_esperado: str | None = None,
) -> ProvenienciaJuridica:
    if isinstance(item, ProvenienciaJuridica):
        fonte = item
    else:
        fonte = ProvenienciaJuridica.model_validate(_normalizar_chaves(item))

    validar_escopo_caso(fonte, case_id_esperado=case_id_esperado)
    return fonte


def _chave_deduplicacao(fonte: ProvenienciaJuridica) -> tuple[Any, ...]:
    """Deduplica somente fontes semanticamente idênticas.

    Status, confidencialidade e marca de inferência integram a chave para que um
    registro restritivo nunca seja ocultado por outro mais permissivo.
    """

    return (
        fonte.hash_fonte,
        fonte.documento_id,
        fonte.nome_arquivo,
        fonte.pagina,
        fonte.trecho,
        fonte.url_oficial,
        fonte.case_id,
        fonte.status_conferencia,
        fonte.nivel_confidencialidade,
        fonte.inferencia_ia,
    )


def normalizar_lote_proveniencia(
    itens: Iterable[ProvenienciaJuridica | Mapping[str, Any]],
    *,
    case_id_esperado: str | None = None,
) -> list[ProvenienciaJuridica]:
    resultado: list[ProvenienciaJuridica] = []
    vistos: set[tuple[Any, ...]] = set()

    for item in itens:
        fonte = normalizar_proveniencia(
            item,
            case_id_esperado=case_id_esperado,
        )
        chave = _chave_deduplicacao(fonte)
        if chave in vistos:
            continue
        vistos.add(chave)
        resultado.append(fonte)

    return resultado


def resumir_confiabilidade(
    fontes: Iterable[ProvenienciaJuridica],
) -> ResumoConfiabilidadeFontes:
    resumo = ResumoConfiabilidadeFontes()

    for fonte in fontes:
        resumo.total += 1
        if fonte.inferencia_ia:
            resumo.inferencias_ia += 1

        match fonte.status_conferencia:
            case StatusConferenciaFonte.CONFIRMADA:
                resumo.confirmadas += 1
            case StatusConferenciaFonte.PENDENTE_CONFERENCIA:
                resumo.pendentes += 1
            case StatusConferenciaFonte.NAO_LOCALIZADA:
                resumo.nao_localizadas += 1
            case StatusConferenciaFonte.POSSIVELMENTE_DESATUALIZADA:
                resumo.possivelmente_desatualizadas += 1
            case StatusConferenciaFonte.IDENTIFICACAO_INSUFICIENTE:
                resumo.identificacao_insuficiente += 1

        if fonte.status_conferencia in _STATUS_BLOQUEANTES:
            resumo.bloqueantes += 1

    return resumo


def construir_resposta_rastreavel(
    *,
    conteudo: str,
    fontes: Iterable[ProvenienciaJuridica | Mapping[str, Any]],
    case_id: str | None = None,
    pontos_validacao_humana: Iterable[str] = (),
) -> RespostaJuridicaRastreavel:
    fontes_normalizadas = normalizar_lote_proveniencia(
        fontes,
        case_id_esperado=case_id,
    )
    resumo = resumir_confiabilidade(fontes_normalizadas)
    pontos = [ponto.strip() for ponto in pontos_validacao_humana if ponto.strip()]

    if resumo.bloqueantes and not pontos:
        pontos.append(
            "Há fontes bloqueantes que exigem conferência humana antes do uso jurídico."
        )

    return RespostaJuridicaRastreavel(
        conteudo=conteudo,
        case_id=case_id,
        fontes=fontes_normalizadas,
        resumo_fontes=resumo,
        pontos_validacao_humana=pontos,
        aprovado_humano=False,
    )
