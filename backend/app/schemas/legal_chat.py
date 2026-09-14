"""Schemas Pydantic da Sala Jurídica Conversacional (V1)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

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


# Status derivados de fluxos dedicados (com audit log/congelamento próprios)
# — jamais setáveis via PATCH livre.
_STATUS_FLUXO_DEDICADO = {"convertida_em_caso", "arquivada"}


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
        if v is None:
            return v
        if v in _STATUS_FLUXO_DEDICADO:
            raise ValueError(
                "status derivado de fluxo dedicado; use POST /converter, "
                "POST /vincular-caso ou POST /saida"
            )
        if v not in SESSION_STATUS:
            raise ValueError(f"status inválido; use um de: {sorted(SESSION_STATUS)}")
        return v

    @model_validator(mode="after")
    def _sem_null_explicito(self):
        # {"titulo": null} passa no tipo Optional mas estouraria 500 na coluna
        # non-nullable; None só é aceitável quando o campo foi OMITIDO do PATCH.
        for campo in ("titulo", "status", "favorita"):
            if campo in self.model_fields_set and getattr(self, campo) is None:
                raise ValueError(f"'{campo}' não aceita null explícito")
        return self


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
            "fatos", "partes", "testemunhas", "enderecos", "identificacao_processual", "provas", "documentos",
            "contradicoes", "questoes", "teses", "pedidos", "riscos",
            "pendencias", "cronologia", "datas_relevantes", "valores",
            "competencia", "ramo_direito", "natureza_acao", "procedimento_rito",
            "prescricao_decadencia", "urgencia", "fontes",
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
    # Guarda G1 do caminho canônico (cases.py): caso em triagem sempre nasce
    # com "o que fazer agora". Omitido → default preenchido na conversão.
    proxima_acao: str | None = Field(default=None, max_length=500)
    advogado_responsavel_id: str = Field(min_length=1, max_length=36)
    confirmo_conflito_verificado: bool
    confirmo_dados_revisados: bool
    # Gates SERVIDOR (paridade com o Raio-X): quando a detecção automática
    # encontra conflito/duplicado, a conversão exige o reconhecimento explícito
    # do achado — o checkbox genérico acima não basta (409 sem estes flags).
    conflict_confirmed: bool = False
    duplicate_confirmed: bool = False
    # Anexos da sessão viram Document oficiais do caso (padrão Raio-X).
    transferir_anexos: bool = True
    # Materialização opcional do dossiê estruturado confirmado. Nunca cria
    # prazo automaticamente; somente campos processuais seguros + partes.
    aplicar_dossie_estruturado: bool = False

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
    # Anexos da sessão viram Document oficiais do caso vinculado.
    transferir_anexos: bool = True
    # Aplicação explícita e auditável do dossiê estruturado no caso existente.
    aplicar_dossie_estruturado: bool = False

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

    @model_validator(mode="after")
    def _justificativa_no_descarte(self) -> "SaidaAlternativaRequest":
        # model_validator: field_validator NÃO roda quando o campo é omitido
        # do payload — descarte sem justificativa passava despercebido.
        if self.acao == "descartar" and not (self.justificativa or "").strip():
            raise ValueError("descartar exige justificativa registrada")
        return self
