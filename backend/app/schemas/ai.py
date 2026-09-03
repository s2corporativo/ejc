# ── app/schemas/ai.py ────────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List

# Teto de 200.000 chars replica o de VerificarCitacoesRequest (já validado em
# produção) — protege o gateway/provedor de payload sem limite (auditoria de
# segurança, 18/08: nada em ai_gateway.py valida tamanho de mensagem antes de
# _chamar_provedor; quem chama o gateway direto, sem passar por
# ai_skill_service, ignorava AI_LONG_DOCUMENT_MAX_CHARS).
_MAX_TEXTO_IA = 200_000

class AnalisarCasoRequest(BaseModel):
    descricao_fatos: str = Field(..., max_length=_MAX_TEXTO_IA)
    area: str
    case_id: Optional[str] = None
    nomes_proteger: Optional[List[str]] = None   # cliente, parte contrária

class ResumirDocRequest(BaseModel):
    texto: str = Field(..., max_length=_MAX_TEXTO_IA)
    case_id: Optional[str] = None

class HITLRevisaoRequest(BaseModel):
    status: str   # revisado | aplicado | descartado
    # Gate de citações (CITACOES_POLITICA="bloquear"): aprovar output com
    # citação bloqueante exige override EXPLÍCITO + justificativa (auditada).
    override_citacoes: bool = False
    justificativa_override: Optional[str] = Field(None, max_length=2000)

class VerificarCitacoesRequest(BaseModel):
    """Verificador rigoroso de jurisprudência (anti-alucinação)."""
    texto: str = Field(..., min_length=1, max_length=200_000)
    consultar_datajud: bool = False   # confirma nº CNJ no DataJud (máx. 5/verificação)


# ══ I1 — UMA PORTA DE IA POR CAPACIDADE (análise E2E de 03/09/2026) ══════════
# Contrato ÚNICO de entrada/saída das cinco capacidades (`/ia/*`). Os limites
# abaixo são a fonte da verdade também para o frontend (contador + maxLength):
# limite que só existe no backend vira 422 depois de o advogado escrever a peça
# inteira.
LIMITES_CAPACIDADE: dict[str, tuple[int, int]] = {
    # capacidade: (min_length, max_length)
    "analisar": (30, _MAX_TEXTO_IA),   # = /ai/analisar-caso (mín. 30 dos fatos)
    "redigir": (5, 12_000),            # = /ai/gerar-minuta (tema) e /ai/executar
    "resumir": (20, _MAX_TEXTO_IA),    # une /ai/resumir-texto e /ai/resumir-documento
    "conversar": (3, 12_000),          # = /ai/core/chat
    "extrair": (20, _MAX_TEXTO_IA),    # texto documental completo
}


class _CapacidadeRequestBase(BaseModel):
    """Campos comuns às cinco portas. `texto` e `mensagem` são sinônimos: a
    porta aceita os dois nomes para não obrigar cada tela a renomear o campo."""
    texto: Optional[str] = None
    mensagem: Optional[str] = None
    case_id: Optional[str] = Field(None, max_length=64)
    area: Optional[str] = Field(None, max_length=60)
    perfil: Optional[str] = Field(None, max_length=40)
    opcoes: Optional[dict] = None


class AnalisarRequest(_CapacidadeRequestBase):
    texto: Optional[str] = Field(None, min_length=30, max_length=_MAX_TEXTO_IA)
    mensagem: Optional[str] = Field(None, min_length=30, max_length=_MAX_TEXTO_IA)


class RedigirRequest(_CapacidadeRequestBase):
    texto: Optional[str] = Field(None, min_length=5, max_length=12_000)
    mensagem: Optional[str] = Field(None, min_length=5, max_length=12_000)


class ResumirRequest(_CapacidadeRequestBase):
    texto: Optional[str] = Field(None, min_length=20, max_length=_MAX_TEXTO_IA)
    mensagem: Optional[str] = Field(None, min_length=20, max_length=_MAX_TEXTO_IA)


class ConversarRequest(_CapacidadeRequestBase):
    texto: Optional[str] = Field(None, min_length=3, max_length=12_000)
    mensagem: Optional[str] = Field(None, min_length=3, max_length=12_000)


class ExtrairRequest(_CapacidadeRequestBase):
    texto: Optional[str] = Field(None, min_length=20, max_length=_MAX_TEXTO_IA)
    mensagem: Optional[str] = Field(None, min_length=20, max_length=_MAX_TEXTO_IA)


class TokensIA(BaseModel):
    input: Optional[int] = None
    output: Optional[int] = None
    total: Optional[int] = None


class RespostaCapacidadeIA(BaseModel):
    """Resposta ÚNICA das cinco capacidades.

    `is_rascunho`/`requer_revisao` não são opção de exibição: saída de IA
    jurídica é rascunho sob revisão humana (OAB), e o carimbo vem de
    `hitl_policy.aplicar()`.
    """
    conteudo: str
    capacidade: str
    tarefa: Optional[str] = None
    modelo: Optional[str] = None
    provider: Optional[str] = None
    log_id: Optional[str] = None
    is_rascunho: bool = True
    requer_revisao: bool = True
    status_hitl: str = "gerado"
    aviso_hitl: str = ""
    fontes_rag: List[dict] = Field(default_factory=list)
    citacoes: List[dict] = Field(default_factory=list)
    alertas: List[str] = Field(default_factory=list)
    custo_estimado_brl: float = 0.0
    tokens: TokensIA = Field(default_factory=TokensIA)
    # Relatório da crítica adversarial quando a capacidade a executa. É o mesmo
    # dado que `hitl_policy.aplicar()` usa para decidir o carimbo de revisão:
    # ausente do schema, o `response_model` o descartava e a tela exibia
    # "revisão obrigatória" sem poder mostrar o motivo (achado da revisão
    # automatizada do PR, 03/09/2026). `None` = a capacidade não a executou.
    critica_adversarial: Optional[dict] = None
