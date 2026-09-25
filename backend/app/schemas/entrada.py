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


class VincularProcessoEntradaRequest(BaseModel):
    """Confirma que um CNJ detectado pertence a um caso já existente."""

    case_id: str = Field(min_length=1, max_length=36)
    confirmo_vinculo: bool

    @field_validator("confirmo_vinculo")
    @classmethod
    def _confirmacao_vinculo_obrigatoria(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("o vínculo processual exige confirmação explícita")
        return v


class CriarCasoEntradaRequest(BaseModel):
    """Payload de POST /entrada/{rascunho_id}/criar-caso."""

    cliente: ClienteEntrada
    area: str = Field(min_length=1, max_length=50)
    titulo: str = Field(min_length=3, max_length=255)
    fatos: str | None = Field(default=None, max_length=50_000)
    parte_contraria: str | None = Field(default=None, max_length=255)
    documentos_ids: list[str] = Field(default_factory=list, max_length=40)
    prazo: PrazoEntrada | None = None

    # Triagem jurídica revisada. Estes campos são aditivos e não exigem nova
    # tabela: prioridade alimenta Case.prioridade; os demais permanecem no
    # snapshot auditável da Entrada Única ligado ao caso.
    assunto: str | None = Field(default=None, max_length=255)
    natureza_demanda: str | None = Field(default=None, max_length=50)
    natureza_provavel: str | None = Field(default=None, max_length=500)
    prioridade: str = Field(default="media", pattern="^(baixa|media|alta|critica)$")
    urgencia_motivo: str | None = Field(default=None, max_length=1_000)
    documentos_faltantes: list[str] = Field(default_factory=list, max_length=20)
    provas_necessarias: list[str] = Field(default_factory=list, max_length=20)
    proximos_passos: list[str] = Field(default_factory=list, max_length=20)

    # G1: omitido → default preenchido na criação (caso sempre nasce com
    # "o que fazer agora").
    proxima_acao: str | None = Field(default=None, max_length=2_000)
    advogado_responsavel_id: str = Field(min_length=1, max_length=36)
    confirmo_dados_revisados: bool
    # Gates de SERVIDOR (paridade com a conversão da Sala Jurídica): achado de
    # conflito/duplicado exige reconhecimento explícito (409 sem estes flags).
    conflict_confirmed: bool = False
    duplicate_confirmed: bool = False
    # Correspondência processual provável exige escolha humana explícita.
    # CNJ exato já cadastrado nunca é liberado para duplicação por este flag.
    processo_novo_confirmado: bool = False

    @field_validator(
        "documentos_faltantes", "provas_necessarias", "proximos_passos"
    )
    @classmethod
    def _listas_triagem_seguras(cls, valores: list[str]) -> list[str]:
        limpos: list[str] = []
        for valor in valores:
            item = valor.strip()
            if not item:
                continue
            if len(item) > 500:
                raise ValueError("itens da triagem devem ter no máximo 500 caracteres")
            limpos.append(item)
        return limpos

    @field_validator("confirmo_dados_revisados")
    @classmethod
    def _confirmacao_obrigatoria(cls, v: bool) -> bool:
        if v is not True:
            raise ValueError("a criação do caso exige confirmação explícita do advogado")
        return v
