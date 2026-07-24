"""Adaptador dos metadados do RAG para a proveniência jurídica canônica.

O contrato geral, os enums, o isolamento por caso e o envelope de resposta ficam
em ``app.schemas.ai_proveniencia`` e ``app.services.ai.proveniencia``. Este
módulo contém apenas as regras específicas de leitura de ``knowledge_docs`` e
dos chunks recuperados pelo RAG.
"""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import PurePath
from typing import Any, Mapping
from urllib.parse import urlparse

from app.schemas.ai_proveniencia import (
    ProvenienciaJuridica,
    StatusConferenciaFonte,
    TipoFonteJuridica,
)
from app.services.ai.proveniencia import normalizar_proveniencia as normalizar_fonte_canonica

# Alias transitório para consumidores do adaptador anterior. Não define outro
# enum: ambos os nomes apontam para o contrato canônico.
StatusFonte = StatusConferenciaFonte

_STATUS_VALIDOS = {status.value for status in StatusConferenciaFonte}
_STATUS_VIGENCIA_CRITICA = {"revogada", "superada", "desatualizada", "nao_vigente"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _primeiro(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "sim", "yes"}
    return bool(value)


def _enum_texto(value: Any) -> str:
    if hasattr(value, "value"):
        value = value.value
    return str(value or "").strip().lower()


def _datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    texto = str(value or "").strip()
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None


def _url_http(value: Any) -> str | None:
    texto = str(value or "").strip()
    if not texto:
        return None
    parsed = urlparse(texto)
    return texto if parsed.scheme in {"http", "https"} else None


def _nome_arquivo(fonte: Any, titulo: Any, proveniencia: Mapping[str, Any]) -> str | None:
    explicito = _primeiro(
        proveniencia.get("nome_arquivo"),
        proveniencia.get("filename"),
        proveniencia.get("arquivo"),
    )
    if explicito:
        return str(explicito)

    fonte_texto = str(fonte or "").strip()
    if fonte_texto:
        parsed = urlparse(fonte_texto)
        caminho = parsed.path if parsed.scheme else fonte_texto
        nome = PurePath(caminho).name
        if nome and "." in nome:
            return nome

    return str(titulo) if titulo else None


def _tipo_fonte(doc: Mapping[str, Any], prov: Mapping[str, Any]) -> TipoFonteJuridica:
    declarado = _enum_texto(
        _primeiro(prov.get("tipo_fonte"), prov.get("source_type"))
    )
    if declarado:
        try:
            return TipoFonteJuridica(declarado)
        except ValueError:
            pass
    if doc.get("case_id"):
        return TipoFonteJuridica.DOCUMENTO_CASO
    return TipoFonteJuridica.OUTRA


def _data_verificacao(
    doc: Mapping[str, Any],
    extra: Mapping[str, Any],
    prov: Mapping[str, Any],
) -> datetime | None:
    return _datetime(
        _primeiro(
            prov.get("data_verificacao"),
            prov.get("verified_at"),
            extra.get("data_verificacao"),
            extra.get("revisado_em"),
            extra.get("conferido_em"),
            doc.get("revisado_em"),
        )
    )


def avaliar_status_fonte(
    doc: Mapping[str, Any],
    proveniencia: Mapping[str, Any] | None = None,
) -> tuple[StatusConferenciaFonte, list[str]]:
    """Classifica a fonte sem presumir confirmação inexistente."""

    extra = _mapping(doc.get("extra"))
    prov = _mapping(proveniencia) or _mapping(extra.get("proveniencia"))
    motivos: list[str] = []

    vigente = doc.get("vigente")
    vigencia_status = _enum_texto(
        _primeiro(prov.get("vigencia_status"), extra.get("vigencia_status"))
    )
    if vigente is False or vigencia_status in _STATUS_VIGENCIA_CRITICA:
        motivos.append("documento marcado como não vigente, revogado ou superado")
        return StatusConferenciaFonte.POSSIVELMENTE_DESATUALIZADA, motivos

    if prov.get("fonte_localizada") is False or _bool(prov.get("nao_localizada")):
        motivos.append("a origem declarada não foi localizada")
        return StatusConferenciaFonte.NAO_LOCALIZADA, motivos

    fonte = _primeiro(prov.get("url"), prov.get("fonte"), doc.get("fonte"))
    identificadores = (
        fonte,
        doc.get("chave_origem"),
        doc.get("titulo"),
        prov.get("nome_arquivo"),
        doc.get("id"),
    )
    if not any(value not in (None, "") for value in identificadores):
        motivos.append("faltam documento, título, arquivo, URL ou chave de origem")
        return StatusConferenciaFonte.IDENTIFICACAO_INSUFICIENTE, motivos

    tipo_fonte = _tipo_fonte(doc, prov)
    autoridade = _primeiro(prov.get("autoridade"), prov.get("issuer"), extra.get("autoridade"))
    if tipo_fonte is TipoFonteJuridica.FONTE_OFICIAL and not (
        _url_http(fonte) or autoridade
    ):
        motivos.append("fonte oficial sem URL ou autoridade emissora")
        return StatusConferenciaFonte.IDENTIFICACAO_INSUFICIENTE, motivos

    status_explicito = _enum_texto(
        _primeiro(prov.get("status_conferencia"), prov.get("status_fonte"))
    )
    status: StatusConferenciaFonte | None = None
    if status_explicito in _STATUS_VALIDOS:
        status = StatusConferenciaFonte(status_explicito)
        motivos.append("status de proveniência informado explicitamente")

    rag_status = _enum_texto(extra.get("rag_status"))
    confirmado = (
        doc.get("revisado") is True
        or rag_status == "aprovado"
        or _bool(extra.get("conferido"))
        or _bool(prov.get("confirmada"))
    )
    if status is None and confirmado:
        status = StatusConferenciaFonte.CONFIRMADA
        motivos.append("documento aprovado, revisado ou conferido")

    if status is StatusConferenciaFonte.CONFIRMADA:
        if _data_verificacao(doc, extra, prov) is None:
            motivos.append("confirmação sem data de verificação")
            return StatusConferenciaFonte.PENDENTE_CONFERENCIA, motivos
        if tipo_fonte is TipoFonteJuridica.FONTE_OFICIAL and vigente is None:
            motivos.append("fonte oficial confirmada sem estado de vigência")
            return StatusConferenciaFonte.PENDENTE_CONFERENCIA, motivos
        return status, motivos

    if status is not None:
        return status, motivos

    motivos.append("a fonte possui identificação, mas ainda não foi conferida")
    return StatusConferenciaFonte.PENDENTE_CONFERENCIA, motivos


def normalizar_proveniencia(
    *,
    doc: Mapping[str, Any],
    chunk: Mapping[str, Any] | None = None,
    limite_trecho: int = 600,
    case_id_esperado: str | None = None,
) -> ProvenienciaJuridica:
    """Converte metadados RAG para o contrato canônico e valida o escopo."""

    extra = _mapping(doc.get("extra"))
    prov = _mapping(extra.get("proveniencia"))
    chunk_map = _mapping(chunk)
    chunk_meta = _mapping(
        _primeiro(chunk_map.get("metadata"), chunk_map.get("extra"), {})
    )

    status, motivos = avaliar_status_fonte(doc, prov)
    tipo_declarado = _tipo_fonte(doc, prov)
    fonte = _primeiro(prov.get("url"), prov.get("fonte"), doc.get("fonte"))
    url_oficial = _url_http(fonte)
    autoridade = _primeiro(
        prov.get("autoridade"),
        prov.get("issuer"),
        extra.get("autoridade"),
    )
    tipo_fonte = tipo_declarado
    if tipo_declarado is TipoFonteJuridica.FONTE_OFICIAL and not (
        url_oficial or autoridade
    ):
        tipo_fonte = TipoFonteJuridica.OUTRA

    pagina = _primeiro(
        chunk_meta.get("pagina"),
        chunk_meta.get("page_number"),
        chunk_meta.get("page"),
        prov.get("pagina"),
        prov.get("page_number"),
    )
    processo_origem = _primeiro(
        prov.get("processo_origem"),
        prov.get("numero_processo"),
        extra.get("processo_origem"),
        extra.get("numero_processo"),
    )
    data_documento = _datetime(
        _primeiro(
            prov.get("data_documento"),
            extra.get("data_documento"),
            doc.get("atualizado_em"),
        )
    )
    data_verificacao = _data_verificacao(doc, extra, prov)

    conteudo = str(_primeiro(chunk_map.get("conteudo"), chunk_map.get("trecho"), ""))
    trecho = conteudo.strip()
    if limite_trecho >= 0 and len(trecho) > limite_trecho:
        trecho = f"{trecho[:limite_trecho].rstrip()}…"

    versao = doc.get("versao")
    metadados = {
        "chunk_id": chunk_map.get("id") or chunk_map.get("chunk_id"),
        "chunk_index": chunk_map.get("chunk_index"),
        "chave_origem": doc.get("chave_origem"),
        "categoria": doc.get("categoria"),
        "tribunal": doc.get("tribunal"),
        "revisado": doc.get("revisado"),
        "motivos_status": motivos,
        "tipo_fonte_declarado": tipo_declarado.value,
    }
    metadados = {chave: valor for chave, valor in metadados.items() if valor is not None}

    fonte_canonica = ProvenienciaJuridica(
        tipo_fonte=tipo_fonte,
        status_conferencia=status,
        nome_arquivo=_nome_arquivo(fonte, doc.get("titulo"), prov),
        documento_id=str(doc.get("id")) if doc.get("id") is not None else None,
        pagina=pagina,
        trecho=trecho or None,
        processo_origem=str(processo_origem) if processo_origem else None,
        case_id=str(doc.get("case_id")) if doc.get("case_id") else None,
        data_documento=data_documento,
        data_verificacao=data_verificacao,
        versao_documento=str(versao) if versao is not None else None,
        hash_fonte=(
            str(doc.get("hash_conteudo")) if doc.get("hash_conteudo") else None
        ),
        url_oficial=url_oficial,
        autoridade=str(autoridade) if autoridade else None,
        vigente=doc.get("vigente") if isinstance(doc.get("vigente"), bool) else None,
        confianca_extracao=(
            chunk_map.get("score")
            if isinstance(chunk_map.get("score"), (int, float))
            else None
        ),
        inferencia_ia=False,
        metadados=metadados,
    )
    return normalizar_fonte_canonica(
        fonte_canonica,
        case_id_esperado=case_id_esperado,
    )
