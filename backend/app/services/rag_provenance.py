"""Contrato de proveniência para resultados do RAG jurídico.

A proveniência é normalizada a partir dos campos já existentes em
``knowledge_docs`` e do JSONB ``extra``. O módulo é deliberadamente puro: não
abre sessão de banco, não altera o schema e não amplia o escopo de acesso.

Campos canônicos adicionais podem ser gravados em ``extra["proveniencia"]``
sem migration. A promoção futura para colunas dedicadas só deve ocorrer após
medição do uso e auditoria de dados reais.
"""

from __future__ import annotations

from enum import Enum
from pathlib import PurePath
from typing import Any, Mapping
from urllib.parse import urlparse


class StatusFonte(str, Enum):
    """Estados jurídicos permitidos para a fonte utilizada pela IA."""

    CONFIRMADA = "confirmada"
    PENDENTE_CONFERENCIA = "pendente_conferencia"
    NAO_LOCALIZADA = "nao_localizada"
    POSSIVELMENTE_DESATUALIZADA = "possivelmente_desatualizada"
    IDENTIFICACAO_INSUFICIENTE = "identificacao_insuficiente"


_STATUS_VALIDOS = {status.value for status in StatusFonte}
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


def avaliar_status_fonte(
    doc: Mapping[str, Any],
    proveniencia: Mapping[str, Any] | None = None,
) -> tuple[StatusFonte, list[str]]:
    """Classifica a fonte sem presumir confirmação inexistente.

    A ordem é fail-safe: fonte não vigente, não localizada ou sem identificação
    nunca é promovida a confirmada apenas porque o documento foi revisado.
    """

    extra = _mapping(doc.get("extra"))
    prov = _mapping(proveniencia) or _mapping(extra.get("proveniencia"))
    motivos: list[str] = []

    vigente = doc.get("vigente")
    vigencia_status = str(
        _primeiro(prov.get("vigencia_status"), extra.get("vigencia_status"), "")
    ).strip().lower()
    if vigente is False or vigencia_status in _STATUS_VIGENCIA_CRITICA:
        motivos.append("documento marcado como não vigente, revogado ou superado")
        return StatusFonte.POSSIVELMENTE_DESATUALIZADA, motivos

    if prov.get("fonte_localizada") is False or _bool(prov.get("nao_localizada")):
        motivos.append("a origem declarada não foi localizada")
        return StatusFonte.NAO_LOCALIZADA, motivos

    identificadores = (
        doc.get("fonte"),
        doc.get("chave_origem"),
        doc.get("titulo"),
        prov.get("url"),
        prov.get("nome_arquivo"),
    )
    if not any(value not in (None, "") for value in identificadores):
        motivos.append("faltam título, arquivo, URL ou chave de origem")
        return StatusFonte.IDENTIFICACAO_INSUFICIENTE, motivos

    status_explicito = str(prov.get("status_fonte") or "").strip().lower()
    if status_explicito in _STATUS_VALIDOS:
        motivos.append("status de proveniência informado explicitamente")
        return StatusFonte(status_explicito), motivos

    rag_status = str(extra.get("rag_status") or "").strip().lower()
    confirmado = (
        doc.get("revisado") is True
        or rag_status == "aprovado"
        or _bool(extra.get("conferido"))
        or _bool(prov.get("confirmada"))
    )
    if confirmado:
        motivos.append("documento aprovado, revisado ou conferido")
        return StatusFonte.CONFIRMADA, motivos

    motivos.append("a fonte possui identificação, mas ainda não foi conferida")
    return StatusFonte.PENDENTE_CONFERENCIA, motivos


def normalizar_proveniencia(
    *,
    doc: Mapping[str, Any],
    chunk: Mapping[str, Any] | None = None,
    limite_trecho: int = 600,
) -> dict[str, Any]:
    """Gera a representação auditável e minimizada de uma fonte RAG.

    ``client_id`` não é exposto. O escopo do caso é mantido apenas por
    ``case_id``, necessário para rastreabilidade e para a checagem de isolamento
    pela camada chamadora.
    """

    extra = _mapping(doc.get("extra"))
    prov = _mapping(extra.get("proveniencia"))
    chunk_map = _mapping(chunk)
    chunk_meta = _mapping(_primeiro(chunk_map.get("metadata"), chunk_map.get("extra"), {}))

    status, motivos = avaliar_status_fonte(doc, prov)
    fonte = _primeiro(prov.get("url"), prov.get("fonte"), doc.get("fonte"))
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
    data_documento = _primeiro(
        prov.get("data_documento"),
        extra.get("data_documento"),
        doc.get("atualizado_em"),
    )

    conteudo = str(_primeiro(chunk_map.get("conteudo"), chunk_map.get("trecho"), ""))
    trecho = conteudo.strip()
    if limite_trecho >= 0 and len(trecho) > limite_trecho:
        trecho = f"{trecho[:limite_trecho].rstrip()}…"

    return {
        "documento_id": doc.get("id"),
        "chunk_id": chunk_map.get("id") or chunk_map.get("chunk_id"),
        "chunk_index": chunk_map.get("chunk_index"),
        "nome_arquivo": _nome_arquivo(fonte, doc.get("titulo"), prov),
        "pagina": pagina,
        "trecho": trecho or None,
        "fonte": fonte,
        "chave_origem": doc.get("chave_origem"),
        "processo_origem": processo_origem,
        "case_id": doc.get("case_id"),
        "data_documento": data_documento,
        "categoria": doc.get("categoria"),
        "tribunal": doc.get("tribunal"),
        "versao": doc.get("versao"),
        "vigente": doc.get("vigente"),
        "revisado": doc.get("revisado"),
        "hash_conteudo": doc.get("hash_conteudo"),
        "status_fonte": status.value,
        "motivos_status": motivos,
    }
