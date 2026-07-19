# ── app/schemas/document_intake.py ───────────────────────────────────────────
"""Contrato TIPADO da extração de importação de documentos (#83 — Gap A).

Antes deste módulo o pipeline `documento_service.extrair_e_analisar` devolvia
um dict frouxo para o frontend pré-preencher o caso. Aqui definimos os schemas
Pydantic v2 que dão forma a essa saída — sem alterar auth, persistência ou a
política LGPD do intake.

Princípios (CLAUDE.md / regras invioláveis do intake):
  • LACUNA = None ou lista vazia. NUNCA inventar valor, papel, CPF, lei ou nº
    de processo. Campo ausente permanece null.
  • Toda saída é MINUTA: `necessita_revisao_humana` nasce True (revisão do
    advogado/OAB obrigatória).
  • A PII determinística (CPF/CNPJ/nº CNJ) vem de `extracao_estruturada`
    (regex local, sem LLM) e chega aqui como `CampoExtraido` com
    `trecho_origem` = o próprio literal casado no texto (rastreabilidade R4).

Este é um contrato de LEITURA/RETORNO ADITIVO: `CasoExtraido`,
`ClienteExtraido` etc. não substituem os models persistidos nem
`cases.aplicar_extracao` — apenas descrevem, de forma validada e fail-safe, o
que a importação extraiu para o frontend.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CampoExtraido(BaseModel):
    """Valor extraído com rastreabilidade opcional.

    Reutilizável em qualquer campo cuja origem no documento se queira auditar:
      • `valor`         — o dado em si (str, número, etc.); None = lacuna.
      • `trecho_origem` — citação LITERAL e curta de onde o valor veio (ou None).
      • `confianca`     — 0..1 (None quando não aplicável). Extração
                          determinística → 1.0; heurística/LLM → valor do modelo.
    """

    valor: Any = None
    trecho_origem: Optional[str] = None
    confianca: Optional[float] = None


class ParteExtraida(BaseModel):
    """Uma parte do processo (papel livre: autor/reu/terceiro/vitima/testemunha…)."""

    nome: Optional[str] = None
    papel: Optional[str] = None
    cpf: Optional[CampoExtraido] = None
    cnpj: Optional[CampoExtraido] = None
    qualificacao: Optional[str] = None


class ClienteExtraido(BaseModel):
    """Dados do provável cliente (parte a ser cadastrada), quando identificáveis."""

    nome: Optional[str] = None
    cpf: Optional[CampoExtraido] = None
    cnpj: Optional[CampoExtraido] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    endereco: Optional[str] = None


class CasoExtraido(BaseModel):
    """Núcleo do caso a pré-preencher (área, foro, nº CNJ, valor, fatos)."""

    area: Optional[str] = None
    # Texto bruto da IA quando `area` não normaliza para o canônico (nesse caso
    # `area` carrega a sentinela "outro") — transparência para o revisor humano.
    area_bruta: Optional[str] = None
    subramo: Optional[str] = None
    numero_cnj: Optional[CampoExtraido] = None
    orgao: Optional[str] = None
    vara: Optional[str] = None
    tribunal: Optional[str] = None
    valor_causa: Optional[CampoExtraido] = None
    resumo_fatos: Optional[str] = None


class PedidoExtraido(BaseModel):
    descricao: Optional[str] = None
    natureza: Optional[str] = None       # ex.: principal, subsidiário, cautelar
    fundamento: Optional[str] = None


class ProvaExtraida(BaseModel):
    titulo: Optional[str] = None
    tipo: Optional[str] = None           # ex.: documental, pericial, testemunhal
    finalidade: Optional[str] = None     # fato probando


class PrazoExtraido(BaseModel):
    tipo: Optional[str] = None           # ex.: contestação, recurso, prescrição
    data_base: Optional[str] = None
    termo_final: Optional[str] = None
    fatal: bool = False
    base_legal: Optional[str] = None


class RiscoExtraido(BaseModel):
    descricao: Optional[str] = None
    probabilidade: Optional[str] = None  # baixa/media/alta (livre)
    impacto: Optional[str] = None


class TeseSugerida(BaseModel):
    titulo: Optional[str] = None
    fundamento: Optional[str] = None
    forca: Optional[str] = None          # força/robustez estimada (livre)


class PendenciaRevisao(BaseModel):
    """Ponto que a extração NÃO conseguiu resolver e exige revisão humana."""

    descricao: Optional[str] = None
    campo_alvo: Optional[str] = None     # nome do campo a preencher manualmente
    severidade: Optional[str] = None     # baixa/media/alta (livre)


class DocumentoIntakeResult(BaseModel):
    """Resultado tipado e validado da extração de um documento importado.

    Agrega o que a importação conseguiu extrair. Todo campo/lista ausente
    permanece null/vazio (NUNCA inventar). `necessita_revisao_humana` nasce
    True: a saída é sempre minuta sujeita à revisão do advogado responsável.
    """

    tipo_documento: Optional[str] = None
    confianca_classificacao: Optional[float] = None

    cliente: Optional[ClienteExtraido] = None
    caso: Optional[CasoExtraido] = None
    partes: list[ParteExtraida] = Field(default_factory=list)
    pedidos: list[PedidoExtraido] = Field(default_factory=list)
    provas: list[ProvaExtraida] = Field(default_factory=list)
    prazos: list[PrazoExtraido] = Field(default_factory=list)
    riscos: list[RiscoExtraido] = Field(default_factory=list)
    teses: list[TeseSugerida] = Field(default_factory=list)
    pendencias: list[PendenciaRevisao] = Field(default_factory=list)

    resumo_fatos: Optional[str] = None
    necessita_revisao_humana: bool = True
