# ── app/services/nfse/base.py ────────────────────────────────────────────────
# Interface abstrata de provedor de NFS-e + contratos (pedido/resultado) e erros
# tipados. Emissão fiscal é ação SENSÍVEL: os erros carregam code/mensagem do
# provedor, mas NUNCA credencial/token (mesma promessa do infosimples_service).
#
# O módulo nasce GATED: o gate de NFSE_ENABLED/provedor fica em
# services/nfse/__init__.get_provider(); o gate de credenciais faltando
# (NFSeConfigError) fica em cada adapter (_exigir_config).
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal

from pydantic import BaseModel, Field


# ── Contratos (Pydantic v2) ───────────────────────────────────────────────────

class NFSeTomador(BaseModel):
    """Tomador do serviço (cliente na nota)."""
    documento: str = Field(description="CPF (11) ou CNPJ (14) — só dígitos ou com máscara")
    nome: str
    email: str | None = None
    cod_municipio_ibge: str | None = Field(
        default=None, description="Código IBGE (7 díg) do município; default = município do emitente"
    )
    uf: str | None = None
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    bairro: str | None = None


class NFSePedidoEmissao(BaseModel):
    """Pedido de emissão de uma NFS-e. Campos fiscais omitidos usam o default
    da configuração do escritório (alíquota ISS, item LC116, cTribNac).

    `trib_issqn`/`tipo_retencao_iss` (NFS-02, auditoria jul/2026): tributabilidade
    e retenção do ISS não são propriedade fixa do emitente — dependem do TOMADOR
    e do MUNICÍPIO dele (LC 116/2003 art. 6º; LC 123/2006 art. 21 §4º). O default
    vem da configuração do escritório (NFSE_TRIB_ISSQN_DEFAULT/
    NFSE_TIPO_RETENCAO_ISS_DEFAULT); sobreponha aqui quando o tomador exigir
    retenção nesta nota específica."""
    referencia: str = Field(description="Chave de idempotência (evita nota duplicada)")
    tomador: NFSeTomador
    descricao: str
    valor: Decimal
    competencia: str | None = Field(default=None, description="Competência YYYY-MM-DD; default = hoje")
    item_lista_servico: str | None = None       # LC 116/03 (default: config)
    cod_tributacao_nacional: str | None = None   # cTribNac (default: config)
    aliquota_iss: Decimal | None = None          # % (default: config)
    # ge=1: códigos do leiaute nacional da DPS começam em 1 — 0/negativo é
    # sempre inválido. O conjunto FECHADO exato (limite superior) ainda não
    # está confirmado com o provedor (docs/NFSE_VIABILIDADE.md, "a confirmar
    # na implementação") — não travamos um teto aqui pra não rejeitar por
    # engano um código válido que ainda não documentamos (review Codex em
    # PR #1074; correção parcial — teto fica para quando o schema oficial
    # for confirmado).
    trib_issqn: int | None = Field(
        default=None, ge=1,
        description="tribISSQN desta nota (1=tributável etc.). Default: NFSE_TRIB_ISSQN_DEFAULT.",
    )
    tipo_retencao_iss: int | None = Field(
        default=None, ge=1,
        description="tpRetISSQN desta nota (retido/não retido). Default: NFSE_TIPO_RETENCAO_ISS_DEFAULT.",
    )


class NFSeResultado(BaseModel):
    """Resultado de uma operação no provedor (emitir/consultar/cancelar)."""
    status: str = Field(description="rascunho|processando|autorizada|rejeitada|cancelada")
    provider_id: str | None = None
    numero: str | None = None
    chave_acesso: str | None = None
    ambiente: str | None = None
    pdf_url: str | None = None
    xml_url: str | None = None
    mensagens: list[str] = Field(default_factory=list)
    bruto: dict | None = Field(default=None, description="Resumo do payload do provedor (sem segredos)")


# ── Erros tipados ──────────────────────────────────────────────────────────────

class NFSeError(RuntimeError):
    """Base dos erros do módulo de NFS-e."""


class NFSeDesabilitadaError(NFSeError):
    """Módulo desligado (NFSE_ENABLED=false). Router → 503."""


class NFSeConfigError(NFSeError):
    """Credencial/empresa faltando ou provedor inválido. Router → 422."""


class NFSeProviderError(NFSeError):
    """O provedor respondeu com erro. Carrega code/mensagem do provedor —
    NUNCA o token/credencial (que só existem no header/corpo da requisição)."""

    def __init__(self, code, mensagem: str, detalhes: list | None = None):
        self.code = code
        self.mensagem = mensagem or ""
        self.detalhes = detalhes or []
        super().__init__(f"Provedor de NFS-e retornou erro {code}: {self.mensagem}")


def http_status_para_erro(e: Exception) -> tuple[int, str]:
    """Mapeia erro tipado → (status HTTP, detail) para os routers.

    Sem import de FastAPI aqui (o service não conhece HTTP); as mensagens dos
    erros tipados nunca contêm credencial/token.
    """
    if isinstance(e, NFSeDesabilitadaError):
        return 503, str(e)
    if isinstance(e, NFSeConfigError):
        return 422, str(e)
    if isinstance(e, NFSeProviderError):
        return 502, str(e)
    return 502, "Falha ao comunicar com o provedor de NFS-e. Tente novamente em instantes."


# ── Interface do provedor ──────────────────────────────────────────────────────

class NFSeProvider(ABC):
    """Interface trocável de provedor de NFS-e (padrão nacional abstraído).

    O primeiro adapter é NuvemFiscalProvider; a interface permite migrar para
    a API oficial (Sefin Nacional) ou outro provedor sem reescrever o resto.
    """

    @abstractmethod
    async def emitir(self, pedido: NFSePedidoEmissao) -> NFSeResultado:
        ...

    @abstractmethod
    async def consultar(self, provider_id: str) -> NFSeResultado:
        ...

    @abstractmethod
    async def baixar_pdf(self, provider_id: str) -> bytes:
        ...

    @abstractmethod
    async def baixar_xml(self, provider_id: str) -> str:
        ...

    @abstractmethod
    async def cancelar(self, provider_id: str, motivo: str) -> NFSeResultado:
        ...
