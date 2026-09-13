# ── app/services/ajuizamento/conectores/pje_mni.py ───────────────────────────
# PJe via MNI — PJeMniConnector + MniClient com dois transportes:
#
#   MniSoapTransport  → reaproveita app/services/mni_connector.MNIConnector
#                       (MNI 2.2.2 SOAP, SOMENTE LEITURA: consultarProcesso,
#                       consultarAvisosPendentes, consultarTeorComunicacao).
#   MniRestTransport  → "Serviço MNI Client" documentado em
#                       https://docs.pje.jus.br/servicos-auxiliares/servico-mni-client/
#                       (API REST auxiliar que expõe entregarManifestacaoProcessual
#                       para criar processo ou anexar documentos; `POST /api/*/
#                       manifestacao`; validação por SSO Keycloak com role
#                       `invoke-service-endpoint`; entidades ManifestacaoV1/V2 com
#                       `idSistemaDestino`; versões 2.2.2, 2.2.3 e 3.0.0).
#
# Host, contexto e versão vêm SEMPRE do perfil do tribunal (base_url +
# api_version) — nenhum endpoint fixo universal. Escrita só com perfil
# homologado + PJE_MNI_ENABLED + token; senão REQUIRES_AUTHORIZATION sem I/O.
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.services.ajuizamento.canonico import CanonicalJudicialCase
from app.services.ajuizamento.capacidades import ContextoConector, EstadoCapacidade
from app.services.ajuizamento.conectores.base import (
    ConectorJudicial, ErroConector, ResultadoEnvio, ResultadoOperacao, TimeoutConector, hash_payload,
)
from app.services.ajuizamento.conectores.pdpj import PdpjAuthProvider, PdpjAuthError

logger = logging.getLogger("ejc.ajuizamento.pje_mni")

VERSOES_MNI_SUPORTADAS = ("2.2.2", "2.2.3", "3.0.0")
_POLO = {"ativo": "AT", "passivo": "PA", "terceiro": "TC"}
_TIPO_PESSOA = {"fisica": "fisica", "juridica": "juridica", "autoridade": "autoridade", "orgao": "orgaorepresentacao"}


@dataclass(frozen=True)
class ManifestacaoMni:
    """ManifestacaoV2 — campos com os nomes do MNI (dadosBasicos do tipo
    TipoCabecalhoProcesso). O endpoint exato (`/api/<versao>/manifestacao`)
    é montado a partir do perfil."""
    idSistemaDestino: str
    versao: str
    dadosBasicos: dict[str, Any]
    documentos: list[dict[str, Any]]
    numeroProcesso: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"idSistemaDestino": self.idSistemaDestino, "versao": self.versao,
             "dadosBasicos": self.dadosBasicos, "documento": self.documentos}
        if self.numeroProcesso:
            d["numeroProcesso"] = self.numeroProcesso
        return d


def mapear_para_mni(canonico: CanonicalJudicialCase, *, id_sistema_destino: str, versao: str,
                    numero_processo: str | None = None) -> ManifestacaoMni:
    proc, ident = canonico.processo, canonico.identificacao
    polos = []
    for polo_ejc, sigla in _POLO.items():
        partes = canonico.partes_por_polo(polo_ejc)
        if not partes:
            continue
        polos.append({
            "polo": sigla,
            "parte": [
                {
                    "pessoa": {
                        "nome": p.nome,
                        "tipoPessoa": _TIPO_PESSOA.get(p.tipo_pessoa, "fisica"),
                        "numeroDocumentoPrincipal": p.documento_normalizado,
                        "dataNascimento": p.nascimento.strftime("%Y%m%d") if p.nascimento else None,
                        "endereco": (
                            [{"cep": p.endereco.cep, "logradouro": p.endereco.logradouro,
                              "numero": p.endereco.numero, "complemento": p.endereco.complemento,
                              "bairro": p.endereco.bairro, "cidade": p.endereco.municipio,
                              "estado": p.endereco.uf}] if p.endereco else []
                        ),
                    },
                    "advogado": [
                        {"nome": a.nome, "numeroDocumentoPrincipal": a.documento,
                         "inscricao": f"{a.oab_numero}{a.oab_uf}" if a.oab_numero and a.oab_uf else None,
                         "tipoRepresentante": "A"}
                        for a in canonico.representacao
                    ] if polo_ejc == "ativo" else [],
                }
                for p in partes
            ],
        })
    dados_basicos = {
        "classeProcessual": proc.classe_codigo,
        "codigoLocalidade": ident.codigo_localidade,
        "competencia": ident.competencia_codigo,
        "valorCausa": str(proc.valor_causa) if proc.valor_causa is not None else None,
        "nivelSigilo": int(proc.nivel_sigilo),
        "intervencaoMP": False,
        "assunto": [{"codigoNacional": a.codigo, "principal": bool(a.principal)} for a in proc.assuntos],
        "polo": polos,
        "outroParametro": [
            {"nome": "assistenciaJudiciaria", "valor": str(proc.gratuidade).lower()},
            {"nome": "pedidoLiminarAntecipacaoTutela", "valor": str(proc.tutela).lower()},
            *[{"nome": k, "valor": str(v)} for k, v in sorted(proc.caracteristicas.items())],
        ],
    }
    documentos = [
        {"idDocumento": d.document_id, "tipoDocumento": d.tpu_document_type, "descricao": d.file_name,
         "mimetype": d.mime_type, "hash": d.sha256, "nivelSigilo": int(proc.nivel_sigilo)}
        for d in canonico.documentos
    ]
    return ManifestacaoMni(idSistemaDestino=id_sistema_destino, versao=versao,
                           dadosBasicos=dados_basicos, documentos=documentos, numeroProcesso=numero_processo)


# ── Transportes ───────────────────────────────────────────────────────────────

class MniSoapTransport:
    """Leitura MNI 2.2.2 via zeep (MNIConnector existente). Só instancia
    quando chamado (zeep é pesado; endpoint WSDL vem do catálogo `tribunais`)."""

    def __init__(self, endpoint_wsdl: str, credencial: Any, timeout: float) -> None:
        self._wsdl = endpoint_wsdl
        self._cred = credencial
        self._timeout = timeout
        self._conn: Any | None = None

    def _conector(self):
        if self._conn is None:
            from app.services.mni_connector import MNIConnector
            self._conn = MNIConnector(self._wsdl, self._cred, timeout=self._timeout)
        return self._conn

    def consultar_processo(self, numero: str, **kw) -> Any:
        return self._conector().consultar_processo(numero, **kw)

    def consultar_avisos_pendentes(self, **kw) -> Any:
        return self._conector().consultar_avisos_pendentes(**kw)


class MniRestTransport:
    """POST {base_url}/api/{versao}/manifestacao com Bearer token (SSO)."""

    def __init__(self, base_url: str, versao: str, timeout: float, transporte: Any | None = None) -> None:
        if versao not in VERSOES_MNI_SUPORTADAS:
            raise ValueError(f"versão MNI não suportada pelo MNI Client: {versao}")
        self.base_url = base_url.rstrip("/")
        self.versao = versao
        self._timeout = timeout
        self._transporte = transporte

    @property
    def url_manifestacao(self) -> str:
        return f"{self.base_url}/api/{self.versao}/manifestacao"

    async def entregar_manifestacao(self, manifestacao: ManifestacaoMni, *, token: str,
                                    idempotency_key: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                   "Idempotency-Key": idempotency_key}
        corpo = manifestacao.to_dict()
        try:
            if self._transporte is not None:
                resp = await self._transporte.post(self.url_manifestacao, json=corpo, headers=headers)
            else:
                async with httpx.AsyncClient(timeout=self._timeout) as c:
                    resp = await c.post(self.url_manifestacao, json=corpo, headers=headers)
        except httpx.TimeoutException as exc:
            raise TimeoutConector("timeout ao entregar manifestação no MNI Client") from exc
        except httpx.HTTPError as exc:
            raise ErroConector(f"MNI Client indisponível ({type(exc).__name__})") from exc
        if resp.status_code >= 400:
            logger.warning("[PJe-MNI] manifestação recusada (status=%s)", resp.status_code)
            raise ErroConector(f"MNI Client recusou a manifestação (HTTP {resp.status_code})")
        return resp.json() if resp.content else {}


class MniClient:
    def __init__(self, rest: MniRestTransport | None = None, soap: MniSoapTransport | None = None) -> None:
        self.rest = rest
        self.soap = soap


# ── Conector ─────────────────────────────────────────────────────────────────

class PJeMniConnector(ConectorJudicial):
    chave = "pje_mni"
    sistema = "pje_mni"

    def __init__(self, cliente: MniClient | None = None, auth: PdpjAuthProvider | None = None) -> None:
        self._cliente = cliente
        self._auth = auth

    def declaradas(self, ctx: ContextoConector) -> dict[str, tuple[EstadoCapacidade, str]]:
        s = ctx.settings
        perfil = ctx.perfil
        leitura = (
            (EstadoCapacidade.CONDITIONAL, "leitura MNI 2.2.2 via fila Celery (tribunal cadastrado em /processo-eletronico)")
            if not (s.CELERY_ENABLED and s.REDIS_URL)
            else (EstadoCapacidade.SUPPORTED, "leitura MNI 2.2.2 (consultarProcesso/avisos) pela fila")
        )
        if not s.PJE_MNI_ENABLED:
            escrita = (EstadoCapacidade.CONDITIONAL, "PJE_MNI_ENABLED=false")
        elif perfil is None or not perfil.base_url or not perfil.api_version:
            escrita = (EstadoCapacidade.REQUIRES_AUTHORIZATION, "perfil do tribunal sem base_url/api_version do MNI Client")
        elif perfil.api_version not in VERSOES_MNI_SUPORTADAS:
            escrita = (EstadoCapacidade.UNSUPPORTED, f"versão MNI {perfil.api_version} não suportada")
        elif not perfil.filing_supported:
            escrita = (EstadoCapacidade.UNSUPPORTED, "perfil declara filing_supported=false")
        else:
            escrita = (EstadoCapacidade.SUPPORTED, "MNI Client REST habilitado pelo perfil")
        anexar = escrita if (perfil is None or perfil.append_petition_supported or escrita[0] != EstadoCapacidade.SUPPORTED) \
            else (EstadoCapacidade.UNSUPPORTED, "perfil declara append_petition_supported=false")
        return {
            "validate_target": (EstadoCapacidade.SUPPORTED, "validação local do mapeamento MNI"),
            "file_new_case": escrita,
            "append_petition": anexar,
            "read_process": leitura,
            "read_movements": leitura,
            "read_notices": leitura,
            "download_document": leitura,
            "get_receipt": (EstadoCapacidade.CONDITIONAL, "recibo pela resposta síncrona da manifestação; sem consulta por chave"),
        }

    @staticmethod
    def _id_sistema_destino(ctx: ContextoConector) -> str:
        """`idSistemaDestino` da ManifestacaoV2: informado pelo tribunal na
        homologação (checklist.id_sistema_destino); fallback = código do tribunal."""
        p = ctx.perfil
        if p is None:
            return ""
        checklist = p.homologation_checklist if isinstance(p.homologation_checklist, dict) else {}
        return str(checklist.get("id_sistema_destino") or p.tribunal_code)

    async def validate_target(self, ctx: ContextoConector, canonico: CanonicalJudicialCase) -> ResultadoOperacao:
        versao = (ctx.perfil.api_version if ctx.perfil and ctx.perfil.api_version else "2.2.2")
        m = mapear_para_mni(canonico, id_sistema_destino=self._id_sistema_destino(ctx) or "", versao=versao)
        faltando = [k for k in ("classeProcessual", "codigoLocalidade", "valorCausa") if not m.dadosBasicos.get(k)]
        if not m.dadosBasicos["assunto"]:
            faltando.append("assunto")
        return ResultadoOperacao(
            EstadoCapacidade.SUPPORTED if not faltando else EstadoCapacidade.CONDITIONAL,
            dados={"faltando": faltando, "payload_hash": hash_payload(m.to_dict())},
        )

    async def _token(self, ctx: ContextoConector) -> str:
        auth = self._auth or PdpjAuthProvider(ctx.settings)
        try:
            return (await auth.obter_token()).access_token
        except PdpjAuthError as exc:
            raise ErroConector(str(exc)) from exc

    async def _enviar(self, ctx: ContextoConector, canonico: CanonicalJudicialCase, *, operacao: str,
                      numero_processo: str | None, idempotency_key: str) -> ResultadoEnvio:
        bloqueio = self._bloqueio_escrita(ctx, operacao)
        if bloqueio is not None:
            return bloqueio
        perfil = ctx.perfil
        rest = (self._cliente.rest if self._cliente and self._cliente.rest else
                MniRestTransport(perfil.base_url, perfil.api_version, ctx.settings.PJE_MNI_TIMEOUT_SECONDS))
        manifestacao = mapear_para_mni(canonico, id_sistema_destino=self._id_sistema_destino(ctx),
                                       versao=perfil.api_version, numero_processo=numero_processo)
        token = await self._token(ctx)
        resposta = await rest.entregar_manifestacao(manifestacao, token=token, idempotency_key=idempotency_key)
        recibo = resposta.get("recibo") if isinstance(resposta, dict) else None
        numero = (resposta.get("numeroProcesso") or resposta.get("numero_processo")) if isinstance(resposta, dict) else None
        protocolo = (resposta.get("protocoloRecebimento") or resposta.get("protocolo")) if isinstance(resposta, dict) else None
        sucesso = bool(resposta.get("sucesso", bool(protocolo or numero))) if isinstance(resposta, dict) else False
        if not sucesso:
            return ResultadoEnvio(EstadoCapacidade.CONDITIONAL, mensagem=str(resposta.get("mensagem", "resposta incompleta do MNI Client")),
                                  dados={"resposta_incompleta": True}, response_hash=hash_payload(resposta))
        return ResultadoEnvio(
            EstadoCapacidade.SUPPORTED, mensagem="manifestação entregue",
            protocol_number=protocolo, cnj_number=numero, external_process_id=numero,
            receipt=recibo if isinstance(recibo, dict) else ({"recibo": recibo} if recibo else None),
            timestamp=datetime.now(timezone.utc), confirmado=bool(numero),
            response_hash=hash_payload(resposta),
        )

    async def file_new_case(self, ctx: ContextoConector, canonico: CanonicalJudicialCase,
                            *, idempotency_key: str) -> ResultadoEnvio:
        return await self._enviar(ctx, canonico, operacao="file_new_case", numero_processo=None,
                                  idempotency_key=idempotency_key)

    async def append_petition(self, ctx: ContextoConector, canonico: CanonicalJudicialCase,
                              *, numero_cnj: str, idempotency_key: str) -> ResultadoEnvio:
        return await self._enviar(ctx, canonico, operacao="append_petition", numero_processo=numero_cnj,
                                  idempotency_key=idempotency_key)

    async def read_process(self, ctx: ContextoConector, numero_cnj: str) -> ResultadoOperacao:
        # Leitura MNI real roda em task Celery (nunca na request) — aqui só
        # indicamos o caminho existente (/processo-eletronico/sincronizar).
        estado, motivo = self.declaradas(ctx)["read_process"]
        return ResultadoOperacao(estado, mensagem=f"{motivo}; use POST /processo-eletronico/sincronizar",
                                 dados={"assincrono": True})
