# ── app/services/ajuizamento/conectores/pdpj.py ──────────────────────────────
# PDPJ-Br / Jus.br — PDPJConnector + PdpjAuthProvider.
#
# Fontes oficiais consultadas (05/09/2026):
#   - Autenticação SSO (Keycloak, realm `pje`):
#     https://docs.pdpj.jus.br/servicos-estruturantes/autenticacao-sso/
#     token endpoint documentado — homologação:
#       https://sso.stg.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token
#     produção:
#       https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token
#     grant_type=password (usuário) ou client_credentials (conta de serviço);
#     header `Authorization: bearer TOKEN`; cadastro de client mediante
#     solicitação a integracaopdpj@cnj.jus.br.
#   - Petição inicial (Portal de Serviços):
#     https://docs.pdpj.jus.br/servicos-negociais/portal-servicos/pet-inicial/
#     A página documenta o contrato TRIBUNAL ← Portal (notificação
#     "PeticaoInicialProtocolada" com `dadosBasicos` {classeProcessual,
#     codigoLocalidade, competencia, valorCausa, nivelSigilo,
#     assistenciaJudiciaria, pedidoLiminarAntecipacaoTutela, assuntos[], polo[]}
#     e callback {protocoloPortal, protocolo, dataHora, sucesso,
#     idOrgaoDistribuido, numeroProcesso, erros[]}). NÃO há endpoint público
#     documentado para sistemas de escritório protocolarem via API: o envio
#     por terceiros depende de habilitação institucional. Por isso
#     `file_new_case` responde REQUIRES_AUTHORIZATION sem chamada remota, e o
#     mapeamento CanonicalJudicialCase → PdpjNewCasePayload segue os NOMES
#     documentados acima, marcado como PENDENTE DE CONFIRMAÇÃO do endpoint.
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import Settings
from app.services.ajuizamento.canonico import CanonicalJudicialCase
from app.services.ajuizamento.capacidades import ContextoConector, EstadoCapacidade
from app.services.ajuizamento.conectores.base import (
    ConectorJudicial, ErroConector, ResultadoEnvio, ResultadoOperacao, hash_payload,
)

logger = logging.getLogger("ejc.ajuizamento.pdpj")

# Endpoints OFICIAIS documentados do SSO — únicos hosts aceitos. Nenhum outro
# host de token pode ser configurado (evita exfiltração do client_secret).
SSO_TOKEN_URLS: dict[str, str] = {
    "homologacao": "https://sso.stg.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token",
    "producao": "https://sso.cloud.pje.jus.br/auth/realms/pje/protocol/openid-connect/token",
}
_MARGEM_EXPIRACAO_S = 30
_POLO = {"ativo": "AT", "passivo": "PA", "terceiro": "TC"}
_TIPO_PESSOA = {"fisica": "FISICA", "juridica": "JURIDICA", "autoridade": "AUTORIDADE", "orgao": "ORGAOREPRESENTACAO"}
_TIPO_DOCUMENTO_TPU_PADRAO = {"peticao_inicial": 58}   # documentado no exemplo oficial (58 = petição inicial)


class PdpjAuthError(ErroConector):
    pass


@dataclass
class TokenPdpj:
    access_token: str
    expires_at: float
    refresh_token: str | None = None
    refresh_expires_at: float | None = None
    token_type: str = "bearer"
    scope: str = ""
    roles: tuple[str, ...] = ()

    @property
    def expirado(self) -> bool:
        return time.monotonic() >= (self.expires_at - _MARGEM_EXPIRACAO_S)


class PdpjAuthProvider:
    """OIDC/OAuth2 (Keycloak) — client_credentials. Token só em memória; o
    client_secret vem de Settings (cofre/env) e nunca é exposto/logado."""

    def __init__(self, settings: Settings, transporte: Any | None = None) -> None:
        self._s = settings
        self._token: TokenPdpj | None = None
        self._transporte = transporte   # injeção para testes (objeto com .post)

    @property
    def ambiente(self) -> str:
        return self._s.PDPJ_ENVIRONMENT if self._s.PDPJ_ENVIRONMENT in SSO_TOKEN_URLS else "homologacao"

    @property
    def token_url(self) -> str:
        return SSO_TOKEN_URLS[self.ambiente]

    @property
    def configurado(self) -> bool:
        return bool(self._s.PDPJ_INTEGRATION_ENABLED and self._s.PDPJ_CLIENT_ID and self._s.PDPJ_CLIENT_SECRET)

    def estado(self) -> tuple[EstadoCapacidade, str]:
        if not self._s.PDPJ_INTEGRATION_ENABLED:
            return EstadoCapacidade.CONDITIONAL, "PDPJ_INTEGRATION_ENABLED=false"
        if not self.configurado:
            return EstadoCapacidade.REQUIRES_AUTHORIZATION, "client_id/client_secret não emitidos pelo CNJ (integracaopdpj@cnj.jus.br)"
        return EstadoCapacidade.SUPPORTED, f"SSO {self.ambiente} configurado"

    async def obter_token(self) -> TokenPdpj:
        if self._token and not self._token.expirado:
            return self._token
        if not self.configurado:
            raise PdpjAuthError("credencial PDPJ ausente — habilitação institucional pendente")
        dados = {
            "grant_type": "client_credentials",
            "client_id": self._s.PDPJ_CLIENT_ID,
            "client_secret": self._s.PDPJ_CLIENT_SECRET,
        }
        try:
            if self._transporte is not None:
                resp = await self._transporte.post(self.token_url, data=dados)
            else:
                async with httpx.AsyncClient(timeout=self._s.PDPJ_TIMEOUT_SECONDS) as c:
                    resp = await c.post(self.token_url, data=dados)
        except httpx.HTTPError as exc:
            raise PdpjAuthError(f"SSO PDPJ indisponível ({type(exc).__name__})") from exc
        if resp.status_code != 200:
            # Nunca logar corpo (pode ecoar client_id) — só o status.
            logger.warning("[PDPJ] token recusado (status=%s)", resp.status_code)
            raise PdpjAuthError(f"SSO PDPJ recusou a credencial (HTTP {resp.status_code})")
        corpo = resp.json()
        agora = time.monotonic()
        self._token = TokenPdpj(
            access_token=corpo["access_token"],
            expires_at=agora + float(corpo.get("expires_in", 0)),
            refresh_token=corpo.get("refresh_token"),
            refresh_expires_at=agora + float(corpo["refresh_expires_in"]) if corpo.get("refresh_expires_in") else None,
            token_type=corpo.get("token_type", "bearer"),
            scope=corpo.get("scope", ""),
            roles=tuple(corpo.get("roles", ()) or ()),
        )
        return self._token

    def header_autorizacao(self, token: TokenPdpj) -> dict[str, str]:
        return {"Authorization": f"Bearer {token.access_token}"}


# ── Mapeamento CanonicalJudicialCase → PdpjNewCasePayload ────────────────────

@dataclass
class PdpjNewCasePayload:
    """Payload de nova petição inicial na PDPJ, com os NOMES DE CAMPO do
    contrato oficial documentado em pet-inicial (dadosBasicos/polo/assuntos/
    documentos). O ENDPOINT de envio por terceiros não está documentado
    publicamente — `mapeamento_confirmado=False` até homologação."""
    dadosBasicos: dict[str, Any]
    documentos: list[dict[str, Any]]
    tipoPeticao: str = "INICIAL"
    cpfPeticionante: str | None = None
    nomePeticionante: str | None = None
    mapeamento_confirmado: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tipoPeticao": self.tipoPeticao,
            "cpfPeticionante": self.cpfPeticionante,
            "nomePeticionante": self.nomePeticionante,
            "dadosBasicos": self.dadosBasicos,
            "documentos": self.documentos,
        }


def _int_ou_none(v: str | None) -> int | None:
    if v is None:
        return None
    d = re.sub(r"\D", "", str(v))
    return int(d) if d else None


def mapear_para_pdpj(canonico: CanonicalJudicialCase) -> PdpjNewCasePayload:
    proc, ident = canonico.processo, canonico.identificacao
    polos: list[dict[str, Any]] = []
    for polo_ejc, sigla in _POLO.items():
        partes = canonico.partes_por_polo(polo_ejc)
        if not partes:
            continue
        polos.append({
            "polo": sigla,
            "parte": [
                {
                    "tipoPolo": sigla,
                    "nome": p.nome,
                    "tipoPessoa": _TIPO_PESSOA.get(p.tipo_pessoa, "FISICA"),
                    "numeroDocumentoPrincipal": p.documento_normalizado,
                    "dataNascimento": p.nascimento.isoformat() if p.nascimento else None,
                    "endereco": (
                        {"cep": p.endereco.cep, "logradouro": p.endereco.logradouro,
                         "numero": p.endereco.numero, "complemento": p.endereco.complemento,
                         "bairro": p.endereco.bairro, "cidade": p.endereco.municipio,
                         "estado": p.endereco.uf} if p.endereco else None
                    ),
                    "advogado": [
                        {"nome": a.nome, "numeroOAB": a.oab_numero, "ufOAB": a.oab_uf,
                         "tipoRepresentante": "A"}
                        for a in canonico.representacao
                    ] if polo_ejc == "ativo" else [],
                }
                for p in partes
            ],
        })
    dados_basicos = {
        "classeProcessual": _int_ou_none(proc.classe_codigo),
        "codigoLocalidade": _int_ou_none(ident.codigo_localidade),
        "competencia": _int_ou_none(ident.competencia_codigo),
        "valorCausa": float(proc.valor_causa) if proc.valor_causa is not None else None,
        "nivelSigilo": int(proc.nivel_sigilo),
        "assistenciaJudiciaria": bool(proc.gratuidade),
        "pedidoLiminarAntecipacaoTutela": bool(proc.tutela),
        "prioridade": proc.prioridade,
        "assuntos": [
            {"codigoNacional": _int_ou_none(a.codigo), "principal": bool(a.principal)} for a in proc.assuntos
        ],
        "polo": polos,
        "outroParametro": [
            {"nome": k, "valor": v} for k, v in sorted(proc.caracteristicas.items())
        ],
    }
    documentos = [
        {
            "idDocumento": d.document_id,
            "descricao": d.file_name,
            "mimetype": d.mime_type,
            "tipoDocumento": d.tpu_document_type or _TIPO_DOCUMENTO_TPU_PADRAO.get(d.document_type),
            "hash": d.sha256,
            "assinado": bool(d.signed),
            "nivelSigilo": int(proc.nivel_sigilo),
        }
        for d in canonico.documentos
    ]
    advogado = canonico.representacao[0] if canonico.representacao else None
    return PdpjNewCasePayload(
        dadosBasicos=dados_basicos, documentos=documentos,
        cpfPeticionante=advogado.documento if advogado else None,
        nomePeticionante=advogado.nome if advogado else None,
        mapeamento_confirmado=False,
    )


@dataclass
class PdpjFilingResult:
    protocol_number: str | None
    cnj_number: str | None
    distribution_unit: str | None
    receipt: dict[str, Any] | None
    external_process_id: str | None
    timestamp: datetime | None
    raw_response_hash: str | None
    sucesso: bool
    erros: list[str] = field(default_factory=list)

    @classmethod
    def de_callback(cls, corpo: dict[str, Any]) -> "PdpjFilingResult":
        """Interpreta o callback documentado {protocoloPortal, protocolo, dataHora,
        sucesso, idOrgaoDistribuido, numeroProcesso, erros[]}."""
        ts = None
        bruto = corpo.get("dataHora")
        if bruto:
            for fmt in ("%d/%m/%Y %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
                try:
                    ts = datetime.strptime(str(bruto), fmt)
                    break
                except ValueError:
                    continue
        return cls(
            protocol_number=corpo.get("protocolo") or corpo.get("protocoloPortal"),
            cnj_number=corpo.get("numeroProcesso"),
            distribution_unit=str(corpo["idOrgaoDistribuido"]) if corpo.get("idOrgaoDistribuido") is not None else None,
            receipt={"protocoloPortal": corpo.get("protocoloPortal")} if corpo.get("protocoloPortal") else None,
            external_process_id=corpo.get("numeroProcesso"),
            timestamp=ts,
            raw_response_hash=hash_payload(corpo),
            sucesso=bool(corpo.get("sucesso")),
            erros=[str(e) for e in (corpo.get("erros") or [])],
        )


class PDPJConnector(ConectorJudicial):
    chave = "pdpj"
    sistema = "pdpj"

    def __init__(self, auth: PdpjAuthProvider | None = None) -> None:
        self._auth = auth

    def auth(self, ctx: ContextoConector) -> PdpjAuthProvider:
        if self._auth is None:
            self._auth = PdpjAuthProvider(ctx.settings)
        return self._auth

    def declaradas(self, ctx: ContextoConector) -> dict[str, tuple[EstadoCapacidade, str]]:
        estado_auth, motivo_auth = self.auth(ctx).estado()
        req = EstadoCapacidade.REQUIRES_AUTHORIZATION
        motivo_envio = (
            "endpoint de petição inicial para sistemas externos não documentado publicamente; "
            "exige habilitação institucional junto ao CNJ (integracaopdpj@cnj.jus.br) e homologação"
        )
        return {
            "validate_target": (EstadoCapacidade.SUPPORTED, "validação local do mapeamento documentado"),
            "list_classes": (EstadoCapacidade.CONDITIONAL, "via TpuService (cache local / SGT)"),
            "list_subjects": (EstadoCapacidade.CONDITIONAL, "via TpuService (cache local / SGT)"),
            "file_new_case": (req, motivo_envio),
            "append_petition": (req, motivo_envio),
            "receive_callback": (EstadoCapacidade.SUPPORTED, "callback documentado interpretado por PdpjFilingResult.de_callback"),
            "get_receipt": (req, "recibo só via callback/portal após habilitação"),
            "sign": (EstadoCapacidade.UNSUPPORTED, "assinatura é do SigningProvider, não do conector"),
            "read_process": (estado_auth if estado_auth != EstadoCapacidade.SUPPORTED else req,
                             motivo_auth if estado_auth != EstadoCapacidade.SUPPORTED else "consulta autenticada depende de escopo/role concedidos pelo CNJ"),
        }

    async def validate_target(self, ctx: ContextoConector, canonico: CanonicalJudicialCase) -> ResultadoOperacao:
        payload = mapear_para_pdpj(canonico)
        faltando = [k for k in ("classeProcessual", "codigoLocalidade", "valorCausa") if payload.dadosBasicos.get(k) is None]
        if not payload.dadosBasicos["assuntos"]:
            faltando.append("assuntos")
        if not payload.dadosBasicos["polo"]:
            faltando.append("polo")
        return ResultadoOperacao(
            EstadoCapacidade.SUPPORTED if not faltando else EstadoCapacidade.CONDITIONAL,
            dados={"faltando": faltando, "mapeamento_confirmado": payload.mapeamento_confirmado,
                   "payload_hash": hash_payload(payload.to_dict())},
            mensagem="mapeamento PDPJ pendente de confirmação do endpoint (habilitação institucional)",
        )

    async def file_new_case(self, ctx: ContextoConector, canonico: CanonicalJudicialCase,
                            *, idempotency_key: str) -> ResultadoEnvio:
        bloqueio = self._bloqueio_escrita(ctx, "file_new_case")
        if bloqueio is not None:
            bloqueio.dados["payload_hash"] = hash_payload(mapear_para_pdpj(canonico).to_dict())
            return bloqueio
        # Mesmo com perfil homologado, o endpoint de envio por terceiros não é
        # público: sem `base_url` confirmada no perfil não há chamada.
        return ResultadoEnvio(
            EstadoCapacidade.REQUIRES_AUTHORIZATION,
            mensagem="endpoint PDPJ de petição inicial não confirmado — registrar protocolo manualmente",
            dados={"payload_hash": hash_payload(mapear_para_pdpj(canonico).to_dict())},
        )

    async def append_petition(self, ctx: ContextoConector, canonico: CanonicalJudicialCase,
                              *, numero_cnj: str, idempotency_key: str) -> ResultadoEnvio:
        return await self.file_new_case(ctx, canonico, idempotency_key=idempotency_key)

    async def receive_callback(self, ctx: ContextoConector, payload: dict[str, Any]) -> ResultadoOperacao:
        r = PdpjFilingResult.de_callback(payload)
        return ResultadoOperacao(
            EstadoCapacidade.SUPPORTED if r.sucesso else EstadoCapacidade.CONDITIONAL,
            dados={"protocol_number": r.protocol_number, "cnj_number": r.cnj_number,
                   "distribution_unit": r.distribution_unit, "external_process_id": r.external_process_id,
                   "timestamp": r.timestamp.replace(tzinfo=timezone.utc).isoformat() if r.timestamp and r.timestamp.tzinfo is None else (r.timestamp.isoformat() if r.timestamp else None),
                   "erros": r.erros},
            mensagem="callback interpretado", response_hash=r.raw_response_hash,
        )
