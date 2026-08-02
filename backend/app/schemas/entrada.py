# ── app/schemas/entrada.py ───────────────────────────────────────────────────
# Contratos da Entrada Única (Bloco 3 — seção 4 do desenho).
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator, model_validator


class ClienteEntrada(BaseModel):
    """Exatamente UM: cliente existente (client_id) OU cliente novo (novo_nome)."""

    client_id: str | None = Field(default=None, max_length=36)
    novo_nome: str | None = Field(default=None, min_length=3, max_length=255)

    @model_validator(mode="after")
    def _exatamente_um(self) -> "ClienteEntrada":
        if bool(self.client_id) == bool(self.novo_nome):
            raise ValueError("informe client_id OU novo_nome (exatamente um)")
        return self


class PrazoEntrada(BaseModel):
    """Prazo confirmado pelo advogado na tela de conferência (vira Deadline)."""

    titulo: str = Field(min_length=3, max_length=255)
    data: date
    descricao: str | None = Field(default=None, max_length=2_000)
    responsavel_id: str | None = Field(default=None, max_length=36)


class CriarCasoEntradaRequest(BaseModel):
    """Payload de POST /entrada/{rascunho_id}/criar-caso."""

    cliente: ClienteEntrada
    area: str = Field(min_length=1, max_length=50)
    titulo: str = Field(min_length=3, max_length=255)
    fatos: str | None = Field(default=None, max_length=50_000)
    parte_contraria: str | None = Field(default=None, max_length=255)
    documentos_ids: list[str] = Field(default_factory=list, max_length=40)
    prazo: PrazoEntrada | None = None
    # G1: omitido → default preenchido na criação (caso sempre nasce com
    # "o que fazer agora").
    proxima_acao: str | None = Field(default=None, max_length=2_000)
    advogado_responsavel_id: str = Field(min_length=1, max_length=36)
    confirmo_dados_revisados: bool
    # Gates de SERVIDOR (paridade com a conversão da Sala Jurídica): achado de
    # conflito/duplicado exige reconhecimento explícito (409 sem estes flags).
    conflict_confirmed: bool = False
    duplicate_confirmed: bool = False

    @field_validator("confirmo_dados_revisados")
    @classmethod
    def _confirmacao_obrigatoria(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("a criação do caso exige confirmação explícita do advogado")
        return v
