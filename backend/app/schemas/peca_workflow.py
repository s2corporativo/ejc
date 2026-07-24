"""Contratos dos modos controlados de produção jurídica.

Os schemas não geram texto jurídico e não chamam IA. Eles descrevem como o
advogado deseja preparar o pipeline canônico de peças já existente.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class ModoProducao(str, Enum):
    LIVRE = "livre"
    GUIADO = "guiado"
    MOLDE = "molde"
    AGENTE = "agente"


class ReferenciaDocumento(BaseModel):
    documento_id: str = Field(..., min_length=1, max_length=64)
    versao: int | None = Field(default=None, ge=1)
    hash_conteudo: str | None = Field(default=None, min_length=6, max_length=128)
    nome: str | None = Field(default=None, max_length=500)


class ConfiguracaoMolde(BaseModel):
    referencia: ReferenciaDocumento
    preservar: list[str] = Field(
        default_factory=lambda: [
            "ordem_dos_topicos",
            "titulos",
            "estilo",
            "estrutura_argumentativa",
            "padrao_de_pedidos",
        ],
        max_length=20,
    )
    substituir: list[str] = Field(
        default_factory=lambda: [
            "partes",
            "fatos",
            "datas",
            "valores",
            "fundamentos_especificos",
            "pedidos_aplicaveis",
        ],
        max_length=30,
    )

    @field_validator("preservar", "substituir")
    @classmethod
    def normalizar_campos(cls, valores: list[str]) -> list[str]:
        saida: list[str] = []
        for valor in valores:
            item = "_".join((valor or "").strip().lower().split())
            if item and item not in saida:
                saida.append(item)
        return saida


class ProducaoModoRequest(BaseModel):
    modo: ModoProducao = ModoProducao.LIVRE
    case_id: str | None = Field(default=None, max_length=64)
    tipo_peca: str = Field(..., min_length=2, max_length=100)
    area_direito: str = Field(..., min_length=2, max_length=100)
    instrucao_livre: str | None = Field(default=None, max_length=6000)
    respostas_guiadas: dict[str, Any] = Field(default_factory=dict)
    documentos_considerados: list[ReferenciaDocumento] = Field(
        default_factory=list,
        max_length=100,
    )
    molde: ConfiguracaoMolde | None = None
    aprovado_para_redacao: bool = False


class EtapaPlanoAgente(BaseModel):
    ordem: int = Field(..., ge=1)
    codigo: str
    titulo: str
    objetivo: str
    exige_aprovacao: bool = False


class ProducaoModoPreparada(BaseModel):
    modo: ModoProducao
    case_id: str | None
    tipo_peca: str
    area_direito: str
    pronto_para_redacao: bool
    exige_aprovacao: bool
    bloqueios: list[str]
    alertas: list[str]
    documentos_considerados: list[ReferenciaDocumento]
    molde: ConfiguracaoMolde | None
    campos_estruturados: dict[str, Any]
    etapas: list[EtapaPlanoAgente]
    instrucoes_pipeline: str
    checklist_revisao: list[str]
