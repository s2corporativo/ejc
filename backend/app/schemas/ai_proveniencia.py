# ── Contrato canônico de proveniência para respostas e artefatos de IA ────────
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


_CHAVES_METADADOS_PROIBIDAS = {
    "client_id",
    "tenant_id",
    "user_id",
    "owner_id",
    "cpf",
    "cnpj",
    "rg",
    "email",
    "telefone",
    "phone",
    "address",
    "endereco",
}
_FRAGMENTOS_SEGREDO = (
    "token",
    "secret",
    "senha",
    "password",
    "api_key",
    "apikey",
    "authorization",
    "cookie",
)


def _chave_metadado_sensivel(chave: Any) -> bool:
    normalizada = str(chave).strip().lower()
    return normalizada in _CHAVES_METADADOS_PROIBIDAS or any(
        fragmento in normalizada for fragmento in _FRAGMENTOS_SEGREDO
    )


def _sanitizar_metadados(value: Any) -> Any:
    """Remove identificadores pessoais e segredos de estruturas aninhadas."""

    if isinstance(value, Mapping):
        return {
            str(chave): _sanitizar_metadados(item)
            for chave, item in value.items()
            if not _chave_metadado_sensivel(chave)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitizar_metadados(item) for item in value]
    return value


class StatusConferenciaFonte(str, Enum):
    CONFIRMADA = "confirmada"
    PENDENTE_CONFERENCIA = "pendente_conferencia"
    NAO_LOCALIZADA = "nao_localizada"
    POSSIVELMENTE_DESATUALIZADA = "possivelmente_desatualizada"
    IDENTIFICACAO_INSUFICIENTE = "identificacao_insuficiente"


class TipoFonteJuridica(str, Enum):
    FONTE_OFICIAL = "fonte_oficial"
    DOCUMENTO_CASO = "documento_caso"
    PECA_INTERNA = "peca_interna"
    TESE_INTERNA = "tese_interna"
    JURISPRUDENCIA_VALIDADA = "jurisprudencia_validada"
    DOUTRINA_AUTORIZADA = "doutrina_autorizada"
    OUTRA = "outra"


class NivelConfidencialidadeFonte(str, Enum):
    PUBLICA = "publica"
    INTERNA = "interna"
    CONFIDENCIAL = "confidencial"
    RESTRITA = "restrita"
    SEGREDO_JUSTICA = "segredo_justica"


class ProvenienciaJuridica(BaseModel):
    """Metadados mínimos para reconstruir a origem de uma afirmação da IA."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    tipo_fonte: TipoFonteJuridica
    status_conferencia: StatusConferenciaFonte = (
        StatusConferenciaFonte.PENDENTE_CONFERENCIA
    )
    # Fail-safe: fonte sem classificação explícita nunca nasce pública.
    nivel_confidencialidade: NivelConfidencialidadeFonte = (
        NivelConfidencialidadeFonte.INTERNA
    )
    nome_arquivo: str | None = Field(default=None, max_length=500)
    documento_id: str | None = Field(default=None, max_length=100)
    pagina: int | None = Field(default=None, ge=1)
    trecho: str | None = Field(default=None, max_length=5_000)
    processo_origem: str | None = Field(default=None, max_length=100)
    case_id: str | None = Field(default=None, max_length=100)
    data_documento: datetime | None = None
    data_verificacao: datetime | None = None
    versao_documento: str | None = Field(default=None, max_length=100)
    hash_fonte: str | None = Field(default=None, max_length=128)
    url_oficial: str | None = Field(default=None, max_length=2_000)
    autoridade: str | None = Field(default=None, max_length=300)
    vigente: bool | None = None
    confianca_extracao: float | None = Field(default=None, ge=0, le=1)
    inferencia_ia: bool = False
    metadados: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadados", mode="before")
    @classmethod
    def minimizar_metadados(cls, value: Any) -> dict[str, Any]:
        sanitizado = _sanitizar_metadados(value or {})
        return sanitizado if isinstance(sanitizado, dict) else {}

    @model_validator(mode="after")
    def validar_rastreabilidade_minima(self) -> "ProvenienciaJuridica":
        identificadores = (
            self.documento_id,
            self.nome_arquivo,
            self.url_oficial,
            self.hash_fonte,
        )
        if not any(identificadores):
            raise ValueError(
                "A fonte deve possuir documento_id, nome_arquivo, url_oficial "
                "ou hash_fonte"
            )

        if self.tipo_fonte == TipoFonteJuridica.FONTE_OFICIAL and not (
            self.url_oficial or self.autoridade
        ):
            raise ValueError(
                "Fonte oficial deve informar url_oficial ou autoridade emissora"
            )

        if (
            self.nivel_confidencialidade
            == NivelConfidencialidadeFonte.SEGREDO_JUSTICA
            and not self.case_id
        ):
            raise ValueError(
                "Fonte em segredo de justiça deve possuir case_id verificável"
            )

        if self.status_conferencia == StatusConferenciaFonte.CONFIRMADA:
            if not self.data_verificacao:
                raise ValueError(
                    "Fonte confirmada deve registrar data_verificacao"
                )
            if (
                self.tipo_fonte == TipoFonteJuridica.FONTE_OFICIAL
                and self.vigente is None
            ):
                raise ValueError(
                    "Fonte oficial confirmada deve informar o estado de vigência"
                )

        return self


class ResumoConfiabilidadeFontes(BaseModel):
    total: int = Field(default=0, ge=0)
    confirmadas: int = Field(default=0, ge=0)
    pendentes: int = Field(default=0, ge=0)
    nao_localizadas: int = Field(default=0, ge=0)
    possivelmente_desatualizadas: int = Field(default=0, ge=0)
    identificacao_insuficiente: int = Field(default=0, ge=0)
    inferencias_ia: int = Field(default=0, ge=0)
    bloqueantes: int = Field(default=0, ge=0)


class RespostaJuridicaRastreavel(BaseModel):
    """Envelope aditivo para respostas jurídicas auditáveis."""

    model_config = ConfigDict(extra="forbid")

    conteudo: str = Field(min_length=1, max_length=500_000)
    case_id: str | None = Field(default=None, max_length=100)
    fontes: list[ProvenienciaJuridica] = Field(default_factory=list)
    resumo_fontes: ResumoConfiabilidadeFontes
    pontos_validacao_humana: list[str] = Field(default_factory=list)
    aprovado_humano: bool = False
    aprovado_por: str | None = Field(default=None, max_length=100)
    aprovado_em: datetime | None = None
    registro_aprovacao_id: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validar_resumo_e_aprovacao(self) -> "RespostaJuridicaRastreavel":
        contagens = {
            "total": len(self.fontes),
            "confirmadas": 0,
            "pendentes": 0,
            "nao_localizadas": 0,
            "possivelmente_desatualizadas": 0,
            "identificacao_insuficiente": 0,
            "inferencias_ia": 0,
            "bloqueantes": 0,
        }
        bloqueantes = {
            StatusConferenciaFonte.NAO_LOCALIZADA,
            StatusConferenciaFonte.POSSIVELMENTE_DESATUALIZADA,
            StatusConferenciaFonte.IDENTIFICACAO_INSUFICIENTE,
        }
        for fonte in self.fontes:
            if fonte.inferencia_ia:
                contagens["inferencias_ia"] += 1
            match fonte.status_conferencia:
                case StatusConferenciaFonte.CONFIRMADA:
                    contagens["confirmadas"] += 1
                case StatusConferenciaFonte.PENDENTE_CONFERENCIA:
                    contagens["pendentes"] += 1
                case StatusConferenciaFonte.NAO_LOCALIZADA:
                    contagens["nao_localizadas"] += 1
                case StatusConferenciaFonte.POSSIVELMENTE_DESATUALIZADA:
                    contagens["possivelmente_desatualizadas"] += 1
                case StatusConferenciaFonte.IDENTIFICACAO_INSUFICIENTE:
                    contagens["identificacao_insuficiente"] += 1
            if fonte.status_conferencia in bloqueantes:
                contagens["bloqueantes"] += 1

        if self.resumo_fontes.model_dump() != contagens:
            raise ValueError(
                "Resumo de confiabilidade divergente das fontes informadas"
            )

        if not self.aprovado_humano:
            return self
        if not (
            self.aprovado_por
            and self.aprovado_em
            and self.registro_aprovacao_id
        ):
            raise ValueError(
                "Aprovação humana exige responsável, data e registro de auditoria"
            )
        if self.resumo_fontes.bloqueantes:
            raise ValueError(
                "Resposta com fonte bloqueante não pode ser marcada como aprovada"
            )
        return self
