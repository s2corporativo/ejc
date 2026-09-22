"""Contratos universais da inteligência produzida pela Entrada Única.

O contrato é aditivo ao legado: a tela antiga continua recebendo os campos já
existentes, enquanto ``inteligencia_juridica`` passa a ser a representação
canônica para novos consumidores. Dados não suportados pela entrada permanecem
nulos ou como pendência; não são completados por inferência.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


EstadoEpistemologico = Literal[
    "confirmado",
    "extraido",
    "alegado_cliente",
    "alegado_parte_contraria",
    "controvertido",
    "inferencia_ia",
    "recomendacao_ia",
    "nao_identificado",
]


class SourceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    origem: Literal["relato", "documento", "ocr", "rag", "norma", "manual", "sistema"]
    documento_id: str | None = None
    nome_documento: str | None = None
    pagina: int | None = Field(default=None, ge=1)
    trecho: str | None = Field(default=None, max_length=2_000)
    fonte_url: str | None = None


class ConfidenceMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valor: float | None = Field(default=None, ge=0, le=1)
    justificativa: str | None = Field(default=None, max_length=1_000)
    requer_confirmacao_humana: bool = True


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conteudo: str = Field(min_length=1, max_length=5_000)
    tipo: Literal["fato", "entidade", "data", "valor", "documento", "contradicao"]
    estado: EstadoEpistemologico
    fontes: list[SourceReference] = Field(default_factory=list)
    confianca: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)


class PartyCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nome: str
    papel: str | None = None
    tipo: str | None = None
    qualificacao: str | None = None
    relacao: str | None = None
    evidencias: list[str] = Field(default_factory=list)
    estado: EstadoEpistemologico = "extraido"
    confianca: ConfidenceMetadata = Field(default_factory=ConfidenceMetadata)


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evento: str
    data_literal: str | None = None
    data_iso: str | None = None
    estado: Literal["confirmada", "aproximada", "inferida", "nao_identificada"]
    evidencias: list[str] = Field(default_factory=list)
    requer_confirmacao_humana: bool = True


class LegalIssueCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    titulo: str
    pergunta: str
    prioridade: Literal["alta", "media", "baixa"] = "media"
    fatos_necessarios: list[str] = Field(default_factory=list)
    lacunas: list[str] = Field(default_factory=list)
    estado: Literal["candidata", "nao_verificada"] = "candidata"


class MissingInformation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pergunta: str
    motivo: str
    impacto: Literal["alto", "medio", "baixo"] = "medio"
    altera: list[str] = Field(default_factory=list)


class SuggestedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    acao: str
    tipo: Literal["documento", "tarefa", "prazo", "pesquisa", "revisao", "decisao"]
    prioridade: Literal["alta", "media", "baixa"] = "media"
    estado: Literal["sugerida", "pendente_confirmacao"] = "sugerida"
    fundamento_evidencias: list[str] = Field(default_factory=list)


class FeeReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disponivel: bool = False
    seccional: str | None = None
    servico_identificado: str | None = None
    item_codigo: str | None = None
    valor_minimo: float | None = None
    percentual: float | None = None
    fonte: str | None = None
    vigencia: str | None = None
    candidatos: list[dict[str, Any]] = Field(default_factory=list)
    aviso: str = "Honorários pendentes de confirmação e consulta à tabela oficial vigente."


class CaseIntelligence(BaseModel):
    """Envelope canônico e revisável de uma análise de entrada."""

    model_config = ConfigDict(extra="forbid")

    versao_contrato: str = "case_intelligence.v1"
    status: Literal["rascunho", "degradado"] = "rascunho"
    classificacao: dict[str, Any] = Field(default_factory=dict)
    partes: list[PartyCandidate] = Field(default_factory=list)
    fatos: list[EvidenceItem] = Field(default_factory=list)
    cronologia: list[TimelineEvent] = Field(default_factory=list)
    questoes_juridicas: list[LegalIssueCandidate] = Field(default_factory=list)
    informacoes_faltantes: list[MissingInformation] = Field(default_factory=list)
    provas_necessarias: list[SuggestedAction] = Field(default_factory=list)
    riscos: list[dict[str, Any]] = Field(default_factory=list)
    estrategias: list[dict[str, Any]] = Field(default_factory=list)
    honorarios: FeeReference = Field(default_factory=FeeReference)
    fontes: list[SourceReference] = Field(default_factory=list)
    alertas: list[str] = Field(default_factory=list)
    revisao_obrigatoria: bool = True


def _confidence(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 1:
        number /= 100
    return max(0.0, min(1.0, number))


def _source(origem: str, *, documento_id: str | None = None,
            trecho: str | None = None) -> SourceReference:
    allowed = {"relato", "documento", "ocr", "rag", "norma", "manual", "sistema"}
    return SourceReference(origem=origem if origem in allowed else "sistema",
                           documento_id=documento_id, trecho=trecho)


def build_case_intelligence(proposta: dict[str, Any]) -> CaseIntelligence:
    """Normaliza a proposta legada sem inventar campos ausentes.

    A função é pura e segura para ser usada tanto no intake quanto em testes.
    Ela não promove candidatos para entidades oficiais e conserva a revisão HITL.
    """
    proposta = proposta if isinstance(proposta, dict) else {}
    origem = "relato" if proposta.get("fatos") else "documento"
    fatos_texto = str(proposta.get("fatos") or "").strip()
    fatos = []
    if fatos_texto:
        fatos.append(EvidenceItem(
            id="fato-entrada-1",
            conteudo=fatos_texto[:5_000],
            tipo="fato",
            estado="alegado_cliente" if origem == "relato" else "extraido",
            fontes=[_source(origem, trecho=fatos_texto[:2_000])],
            confianca=ConfidenceMetadata(valor=0.65 if origem == "relato" else 0.55,
                                          justificativa="Origem preservada; confirmação humana obrigatória."),
        ))

    partes: list[PartyCandidate] = []
    cliente = proposta.get("cliente") or {}
    if isinstance(cliente, dict) and cliente.get("nome"):
        partes.append(PartyCandidate(
            nome=str(cliente["nome"]), papel="cliente", estado="extraido",
            evidencias=["fato-entrada-1"] if fatos else [],
            confianca=ConfidenceMetadata(valor=_confidence(cliente.get("confianca")),
                                          justificativa=str(cliente.get("origem") or "")),
        ))
    if proposta.get("parte_contraria"):
        partes.append(PartyCandidate(
            nome=str(proposta["parte_contraria"]), papel="parte_contraria",
            estado="extraido", evidencias=["fato-entrada-1"] if fatos else [],
            confianca=ConfidenceMetadata(valor=0.5, justificativa="Extraída como candidata; confirme a qualificação."),
        ))

    classificacao = {
        "ramo_principal": (proposta.get("area") or {}).get("valor") if isinstance(proposta.get("area"), dict) else None,
        "assunto": (proposta.get("assunto") or {}).get("valor") if isinstance(proposta.get("assunto"), dict) else proposta.get("assunto"),
        "natureza": (proposta.get("natureza") or {}).get("tipo") if isinstance(proposta.get("natureza"), dict) else None,
        "confianca": (proposta.get("area") or {}).get("confianca") if isinstance(proposta.get("area"), dict) else None,
        "ramos_secundarios": [],
        "requer_desambiguacao": not bool((proposta.get("area") or {}).get("valor") if isinstance(proposta.get("area"), dict) else None),
    }

    faltantes = []
    for item in proposta.get("documentos_faltantes") or []:
        faltantes.append(MissingInformation(
            pergunta=f"É possível obter: {item}?",
            motivo="Documento indicado como faltante na triagem.",
            impacto="medio", altera=["prova", "estrategia"],
        ))
    for item in proposta.get("provas_necessarias") or []:
        faltantes.append(MissingInformation(
            pergunta=f"Existe prova ou documento para: {item}?",
            motivo="Prova necessária indicada pela análise preliminar.",
            impacto="alto", altera=["tese", "risco", "estrategia"],
        ))

    provas = [SuggestedAction(acao=str(item), tipo="documento", prioridade="media",
                              estado="pendente_confirmacao", fundamento_evidencias=["fato-entrada-1"] if fatos else [])
              for item in (proposta.get("provas_necessarias") or []) if str(item).strip()]
    alertas = [str(x) for x in (proposta.get("avisos") or []) if str(x).strip()]
    if proposta.get("degradado"):
        alertas.append("Análise degradada: parte da IA ficou indisponível; complete manualmente.")

    honorarios_raw = proposta.get("honorarios_sugeridos")
    honorarios_raw = honorarios_raw if isinstance(honorarios_raw, dict) else {}
    honorarios = FeeReference(
        disponivel=bool(honorarios_raw.get("disponivel")),
        seccional=honorarios_raw.get("seccional"),
        servico_identificado=honorarios_raw.get("servico_identificado"),
        candidatos=list(honorarios_raw.get("candidatos") or [])[:20],
        aviso=str(honorarios_raw.get("aviso") or FeeReference.model_fields["aviso"].default),
    )

    return CaseIntelligence(
        status="degradado" if proposta.get("degradado") else "rascunho",
        classificacao=classificacao,
        partes=partes,
        fatos=fatos,
        informacoes_faltantes=faltantes[:30],
        provas_necessarias=provas[:30],
        riscos=[],
        estrategias=[],
        honorarios=honorarios,
        fontes=[_source(origem)] if fatos else [],
        alertas=list(dict.fromkeys(alertas)),
        revisao_obrigatoria=True,
    )


def build_document_intelligence(resultado: dict[str, Any]) -> CaseIntelligence:
    """Converte o resultado de ``/entrada-universal/processar`` sem duplicar IA."""
    resultado = resultado if isinstance(resultado, dict) else {}
    classificacao = resultado.get("classificacao") or {}
    resumo = resultado.get("resumo_executivo") or {}
    fatos_texto = resumo.get("sumario") if isinstance(resumo, dict) else resumo
    fatos = []
    if fatos_texto:
        fatos.append(EvidenceItem(
            id="fato-documental-1", conteudo=str(fatos_texto)[:5_000], tipo="fato",
            estado="extraido", fontes=[_source("documento")],
            confianca=ConfidenceMetadata(valor=0.55, justificativa="Extração documental pendente de conferência."),
        ))
    partes_raw = resultado.get("partes") or {}
    if isinstance(partes_raw, dict):
        partes_raw = partes_raw.get("partes") or partes_raw.get("candidatos") or []
    partes = []
    for index, item in enumerate(partes_raw if isinstance(partes_raw, list) else []):
        item = item if isinstance(item, dict) else {"nome": str(item)}
        nome = str(item.get("nome") or item.get("parte") or "").strip()
        if nome:
            partes.append(PartyCandidate(
                nome=nome, papel=item.get("papel") or item.get("tipo"),
                estado="extraido", evidencias=["fato-documental-1"] if fatos else [],
                confianca=ConfidenceMetadata(valor=_confidence(item.get("confianca")),
                                              justificativa="Extração documental; confirme qualificação."),
            ))
    cronologia = []
    for item in resultado.get("datas_eventos") or []:
        item = item if isinstance(item, dict) else {"evento": str(item)}
        cronologia.append(TimelineEvent(
            evento=str(item.get("evento") or item.get("descricao") or "Evento extraído"),
            data_literal=item.get("data_texto") or item.get("data"),
            data_iso=item.get("data_iso"),
            estado="confirmada" if item.get("confirmada") else "aproximada",
            evidencias=["fato-documental-1"] if fatos else [],
        ))
    return CaseIntelligence(
        status="degradado" if not (resultado.get("ia") or {}).get("estrutura_valida", False) else "rascunho",
        classificacao={
            "ramo_principal": classificacao.get("area"),
            "fase": classificacao.get("fase"),
            "tipo_documento": classificacao.get("tipo_documento"),
            "requer_desambiguacao": True,
        },
        partes=partes, fatos=fatos, cronologia=cronologia,
        informacoes_faltantes=[MissingInformation(
            pergunta=f"Confirmar: {item}", motivo="Pendência indicada pela prontidão documental.",
            impacto="medio", altera=["prova", "estrategia"],
        ) for item in (resultado.get("documentos_faltantes") or [])[:30]],
        fontes=[_source("documento")],
        alertas=list(resultado.get("alertas_ia") or []) + [
            "Resultado documental é preliminar e exige revisão humana."
        ],
        revisao_obrigatoria=True,
    )
