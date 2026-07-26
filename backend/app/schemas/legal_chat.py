"""Schemas Pydantic da Sala Jurídica Conversacional (V1)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.models.legal_chat import CHAT_MODOS, SESSION_STATUS

# Teto conservador por mensagem — protege o gateway de IA contra abuso de
# tokens (mesma filosofia dos tetos de diplomacia_v3/trabalhista_liquidacao).
MAX_MENSAGEM_CHARS = 40_000
MAX_WORKSPACE_CHARS = 400_000


class SessaoCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=255)
    cliente_potencial: str | None = Field(default=None, max_length=255)
    area_sugerida: str | None = Field(default=None, max_length=100)
    workspace_texto: str | None = Field(default=None, max_length=MAX_WORKSPACE_CHARS)


class SessaoUpdate(BaseModel):
    """PATCH parcial — inclui o autosave da área de trabalho livre."""

    titulo: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = None
    favorita: bool | None = None
    cliente_potencial: str | None = Field(default=None, max_length=255)
    area_sugerida: str | None = Field(default=None, max_length=100)
    advogado_responsavel_id: str | None = Field(default=None, max_length=36)
    workspace_texto: str | None = Field(default=None, max_length=MAX_WORKSPACE_CHARS)

    @field_validator("status")
    @classmethod
    def _status_valido(cls, v: str | None) -> str | None:
        if v is not None and v not in SESSION_STATUS:
            raise ValueError(f"status inválido; use um de: {sorted(SESSION_STATUS)}")
        return v


class MensagemCreate(BaseModel):
    conteudo: str = Field(min_length=1, max_length=MAX_MENSAGEM_CHARS)
    modo: str = Field(default="conversa_livre")
    # Quando True, o texto da área de trabalho entra como contexto da IA.
    incluir_workspace: bool = True
    usar_rag: bool = True

    @field_validator("modo")
    @classmethod
    def _modo_valido(cls, v: str) -> str:
        if v not in CHAT_MODOS:
            raise ValueError(f"modo inválido; use um de: {sorted(CHAT_MODOS)}")
        return v


class EstadoUpdate(BaseModel):
    """Edição manual do estado jurídico consolidado (gera nova versão)."""

    resumo: str | None = Field(default=None, max_length=10_000)
    estado: dict = Field(default_factory=dict)

    @field_validator("estado")
    @classmethod
    def _chaves_conhecidas(cls, v: dict) -> dict:
        permitidas = {
            "fatos", "provas", "contradicoes", "questoes", "teses",
            "riscos", "pendencias", "cronologia", "fontes",
        }
        desconhecidas = set(v) - permitidas
        if desconhecidas:
            raise ValueError(f"chaves de estado desconhecidas: {sorted(desconhecidas)}")
        for chave, valor in v.items():
            if not isinstance(valor, list):
                raise ValueError(f"'{chave}' deve ser uma lista")
        return v


class ConverterRequest(BaseModel):
    """Conferência obrigatória antes da conversão em caso."""

    client_id: str | None = Field(default=None, max_length=36)
    novo_cliente_nome: str | None = Field(default=None, max_length=255)
    area: str = Field(min_length=1, max_length=50)
    titulo_caso: str = Field(min_length=1, max_length=255)
    descricao: str | None = Field(default=None, max_length=10_000)
    advogado_responsavel_id: str = Field(min_length=1, max_length=36)
    confirmo_conflito_verificado: bool
    confirmo_dados_revisados: bool

    @field_validator("confirmo_conflito_verificado", "confirmo_dados_revisados")
    @classmethod
    def _confirmacoes_obrigatorias(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("a conversão exige confirmação explícita do advogado")
        return v


class VincularCasoRequest(BaseModel):
    """Vincula a análise a um CASO JÁ EXISTENTE (alternativa à conversão)."""

    case_id: str = Field(min_length=1, max_length=36)
    confirmo_dados_revisados: bool

    @field_validator("confirmo_dados_revisados")
    @classmethod
    def _confirmacao_obrigatoria(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("o vínculo exige confirmação explícita do advogado")
        return v


class SaidaAlternativaRequest(BaseModel):
    """Saídas que não geram processo (arquivar/descartar exigem justificativa)."""

    acao: Literal["encerrar_consulta", "arquivar", "descartar"]
    justificativa: str | None = Field(default=None, max_length=2_000)

    @field_validator("justificativa")
    @classmethod
    def _justificativa_no_descarte(cls, v: str | None, info) -> str | None:
        if info.data.get("acao") == "descartar" and not (v or "").strip():
            raise ValueError("descartar exige justificativa registrada")
        return v
