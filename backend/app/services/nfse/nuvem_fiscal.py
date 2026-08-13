# ── app/services/nfse/nuvem_fiscal.py ────────────────────────────────────────
# Adapter Nuvem Fiscal (https://nuvemfiscal.com.br) da interface NFSeProvider.
#
# CONTRATO (extraído do OpenAPI/SDK oficial; ver docs/NFSE_VIABILIDADE.md):
#   • Auth OAuth2 client_credentials:
#       POST {AUTH}/oauth/token  (form-urlencoded)
#       grant_type=client_credentials&client_id=..&client_secret=..&scope="nfse empresa"
#       → access_token (Bearer), expires_in. Token CACHEADO até expirar
#         (menos margem), em cache de MÓDULO (sobrevive entre requisições).
#   • Um só host de API ({BASE}); produção vs. homologação é campo no payload
#       (ambiente / tpAmb=1|2). Este módulo é HOMOLOGAÇÃO por padrão (NFSE_MODO).
#   • Emitir (modelo nacional/DPS): POST {BASE}/nfse/dps  → {id, status} (ASSÍNCRONO)
#   • Status:  GET  {BASE}/nfse/{id}
#   • PDF:     GET  {BASE}/nfse/{id}/pdf   · XML: GET {BASE}/nfse/{id}/xml
#   • Cancelar: POST {BASE}/nfse/{id}/cancelamento
#
# SEGREDOS: client_id/secret vão SÓ no corpo do /oauth/token; o Bearer vai SÓ no
# header Authorization. Nunca em log, exceção, audit ou resposta ao caller —
# NFSeProviderError carrega só code/mensagem do provedor (nunca o corpo/token).
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timezone
from decimal import Decimal

import httpx

from app.core.config import NFSE_REGIMES_TRIBUTARIOS_VALIDOS, get_settings

from .base import (
    NFSeConfigError,
    NFSePedidoEmissao,
    NFSeProvider,
    NFSeProviderError,
    NFSeResultado,
)

logger = logging.getLogger("ejc.nfse")

# Margem (s) subtraída do expires_in para renovar o token antes de expirar.
_MARGEM_TOKEN_S = 60

# NFS-01 (auditoria jul/2026): tradução TÉCNICA de NFSE_REGIME_TRIBUTARIO →
# (opSimpNac, regEspTrib) do leiaute nacional da DPS. Isto NÃO decide qual é o
# regime real do escritório (isso é NFSE_REGIME_TRIBUTARIO, no .env, escolhido
# pelo titular com o contador) — só traduz a escolha já feita para os códigos
# do schema. opSimpNac reflete SOMENTE a opção pelo Simples Nacional (LC
# 123/2006): "lucro_presumido"/"lucro_real" são regimes de IRPJ, irrelevantes
# para opSimpNac, então ambos caem em "1 = não optante". regEspTrib fica
# "0 = Nenhum" para as três opções — nenhuma delas afirma um regime especial de
# ISS (ex.: sociedade uniprofissional/"sociedade de profissionais", LC 116/03
# art. 9º §§1º-3º); se o escritório tiver essa condição, é uma configuração que
# esta correção NÃO cobre — sinalizar ao contador antes de assumi-la.
_REGIME_TRIBUTARIO_MAP: dict[str, tuple[int, int]] = {
    "simples_nacional": (3, 0),   # optante ME/EPP (advocacia não pode ser MEI — LC 123/2006 art. 18-A §4º)
    "lucro_presumido": (1, 0),    # não optante pelo Simples Nacional
    "lucro_real": (1, 0),         # não optante pelo Simples Nacional
}
assert set(_REGIME_TRIBUTARIO_MAP) == NFSE_REGIMES_TRIBUTARIOS_VALIDOS, (
    "_REGIME_TRIBUTARIO_MAP dessincronizado de NFSE_REGIMES_TRIBUTARIOS_VALIDOS"
)

# Cache de token no nível do MÓDULO (não da instância): get_provider() cria uma
# instância nova por requisição, mas o token deve ser reaproveitado entre elas.
# Chave = client_id → (access_token, expira_em_monotonic).
_token_cache: dict[str, tuple[str, float]] = {}


def _novo_client(timeout: float) -> httpx.AsyncClient:
    """Fábrica isolada do cliente HTTP (ponto de mock nos testes)."""
    return httpx.AsyncClient(timeout=timeout)


def _mapear_status(bruto: str) -> str:
    """Normaliza o status do provedor para o vocabulário do EJC."""
    s = (bruto or "").strip().lower()
    if s in ("autorizada", "autorizado", "registrada", "registrado", "emitida", "concluido", "concluída", "sucesso"):
        return "autorizada"
    if s in ("cancelada", "cancelado"):
        return "cancelada"
    if s in ("rejeitada", "rejeitado", "erro", "negada", "negado", "falha"):
        return "rejeitada"
    # processando | pendente | em_processamento | vazio → ainda em curso
    return "processando"


class NuvemFiscalProvider(NFSeProvider):
    def __init__(self) -> None:
        s = get_settings()
        self._base = (s.NFSE_NUVEMFISCAL_BASE_URL or "").rstrip("/")
        self._auth = (s.NFSE_NUVEMFISCAL_AUTH_URL or "").rstrip("/")
        self._client_id = s.NFSE_NUVEMFISCAL_CLIENT_ID or ""
        self._client_secret = s.NFSE_NUVEMFISCAL_CLIENT_SECRET or ""
        self._cnpj = re.sub(r"\D", "", s.NFSE_EMITENTE_CNPJ or "")
        self._mun_ibge = (s.NFSE_EMITENTE_MUN_IBGE or "").strip()
        self._timeout = float(s.NFSE_TIMEOUT or 60)
        self._ambiente = "producao" if (s.NFSE_MODO or "").lower() == "producao" else "homologacao"
        # NFS-01/NFS-02: cacheados no __init__ (mesmo padrão de client_id/secret
        # acima) — get_provider() cria uma instância nova por requisição, então
        # isto sempre reflete a config corrente.
        self._regime_tributario = (s.NFSE_REGIME_TRIBUTARIO or "").strip()
        self._trib_issqn_default = s.NFSE_TRIB_ISSQN_DEFAULT
        self._tipo_retencao_iss_default = s.NFSE_TIPO_RETENCAO_ISS_DEFAULT

    # ── Config guard ───────────────────────────────────────────────────────────

    def _exigir_config(self) -> None:
        faltando = []
        if not self._client_id:
            faltando.append("NFSE_NUVEMFISCAL_CLIENT_ID")
        if not self._client_secret:
            faltando.append("NFSE_NUVEMFISCAL_CLIENT_SECRET")
        if not self._cnpj:
            faltando.append("NFSE_EMITENTE_CNPJ")
        if faltando:
            raise NFSeConfigError(
                "NFS-e não configurada — faltam: " + ", ".join(faltando) + ". "
                "Preencha no .env da VPS. A emissão real ainda exige o "
                "certificado A1 no painel do provedor e a confirmação das "
                "definições fiscais (alíquota ISS, item LC116, cTribNac) com o "
                "contador."
            )

    def _exigir_definicoes_fiscais(self) -> None:
        """NFS-01/NFS-02 (auditoria jul/2026): regime tributário e tributação/
        retenção de ISS padrão — exigidos só para EMITIR (as demais operações
        não montam a DPS). O boot já falha com NFSE_ENABLED=true e config
        ausente (Settings._validar_seguranca_producao); este guard é defesa em
        profundidade para o caso de a config mudar em runtime (ex.: settings
        cacheados/sobrescritos por teste) sem reiniciar o processo.
        """
        if self._regime_tributario and self._regime_tributario not in _REGIME_TRIBUTARIO_MAP:
            raise NFSeConfigError(
                f"NFSE_REGIME_TRIBUTARIO inválido: {self._regime_tributario!r}. "
                "Use um de: " + ", ".join(sorted(_REGIME_TRIBUTARIO_MAP)) + "."
            )
        faltando = []
        if not self._regime_tributario:
            faltando.append("NFSE_REGIME_TRIBUTARIO")
        if self._trib_issqn_default is None:
            faltando.append("NFSE_TRIB_ISSQN_DEFAULT")
        if self._tipo_retencao_iss_default is None:
            faltando.append("NFSE_TIPO_RETENCAO_ISS_DEFAULT")
        if faltando:
            raise NFSeConfigError(
                "NFS-e não configurada — faltam: " + ", ".join(faltando) + ". "
                "CONFIRME com o contador antes de preencher: o regime "
                "tributário REAL do escritório e a tributação/retenção padrão "
                "do ISS (esta última pode ser sobreposta por nota em "
                "POST /nfse/emitir, quando o tomador exigir retenção)."
            )

    # ── OAuth2 (token cacheado) ────────────────────────────────────────────────

    async def _obter_token(self) -> str:
        agora = time.monotonic()
        cacheado = _token_cache.get(self._client_id)
        if cacheado and cacheado[1] > agora:
            return cacheado[0]

        dados = {
            "grant_type": "client_credentials",
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "scope": "nfse empresa",
        }
        try:
            async with _novo_client(self._timeout) as c:
                r = await c.post(f"{self._auth}/oauth/token", data=dados)
        except httpx.HTTPError as e:
            logger.warning("[nfse] falha HTTP no /oauth/token: %s", type(e).__name__)
            raise NFSeProviderError(
                502, f"Falha de rede ao autenticar no provedor de NFS-e ({type(e).__name__})."
            ) from None
        if r.status_code != 200:
            # NÃO incluir o corpo da resposta na mensagem (higiene de segredo).
            raise NFSeProviderError(
                r.status_code, "Falha na autenticação com o provedor de NFS-e "
                "(verifique client_id/client_secret)."
            )
        js = r.json()
        token = js.get("access_token")
        if not token:
            raise NFSeProviderError(502, "Provedor de NFS-e não retornou access_token.")
        expira = int(js.get("expires_in") or 3600)
        _token_cache[self._client_id] = (token, agora + max(expira - _MARGEM_TOKEN_S, 30))
        return token

    # ── HTTP autenticado ───────────────────────────────────────────────────────

    async def _api(self, method: str, path: str, *, json: dict | None = None, want: str = "json"):
        token = await self._obter_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            async with _novo_client(self._timeout) as c:
                r = await c.request(method, f"{self._base}{path}", headers=headers, json=json)
        except httpx.HTTPError as e:
            logger.warning("[nfse] falha HTTP em %s %s: %s", method, path, type(e).__name__)
            raise NFSeProviderError(
                502, f"Falha de rede ao comunicar com o provedor de NFS-e ({type(e).__name__})."
            ) from None
        if r.status_code >= 400:
            raise self._erro_provedor(r)
        if want == "bytes":
            return r.content
        if want == "text":
            return r.text
        return r.json()

    def _erro_provedor(self, r: httpx.Response) -> NFSeProviderError:
        """Constrói NFSeProviderError a partir da resposta de erro do provedor.

        Lê code/mensagem do shape de erro da Nuvem Fiscal; NUNCA inclui headers
        (Authorization/Bearer). Se o corpo não for JSON, usa só o status HTTP.
        """
        code: object = r.status_code
        msg = f"Provedor retornou HTTP {r.status_code}."
        detalhes: list[str] = []
        try:
            js = r.json()
            if isinstance(js, dict):
                err = js.get("error")
                if isinstance(err, dict):
                    msg = str(err.get("message") or msg)
                    code = err.get("code") or code
                elif js.get("message"):
                    msg = str(js.get("message"))
                for e in (js.get("errors") or []):
                    if isinstance(e, dict):
                        detalhes.append(str(e.get("message") or e.get("mensagem") or e))
                    else:
                        detalhes.append(str(e))
        except Exception:
            logger.warning(
                "[NFSe] Falha ao extrair detalhes do corpo de erro do provedor "
                "(fail-soft): erro base preservado.",
                exc_info=True,
            )
        return NFSeProviderError(code, msg, detalhes)

    # ── Montagem do DPS (padrão nacional) ──────────────────────────────────────

    def _montar_dps(self, pedido: NFSePedidoEmissao) -> dict:
        s = get_settings()
        tp_amb = 2 if self._ambiente == "homologacao" else 1
        cmun_prest = self._mun_ibge
        tom = pedido.tomador
        cmun_tom = (tom.cod_municipio_ibge or cmun_prest)
        item = pedido.item_lista_servico or s.NFSE_ITEM_LC116
        ctrib = pedido.cod_tributacao_nacional or s.NFSE_CTRIB_NAC
        aliq = pedido.aliquota_iss if pedido.aliquota_iss is not None else Decimal(str(s.NFSE_ISS_ALIQUOTA or 0))
        compet = pedido.competencia or date.today().isoformat()

        # NFS-01/NFS-02: nada fixo aqui — _exigir_definicoes_fiscais() já
        # garantiu que _regime_tributario é uma chave válida e que os defaults
        # de ISS existem (config ou pedido). Ver comentário de
        # _REGIME_TRIBUTARIO_MAP para o porquê de cada tradução.
        op_simp_nac, reg_esp_trib = _REGIME_TRIBUTARIO_MAP[self._regime_tributario]
        trib_issqn = pedido.trib_issqn if pedido.trib_issqn is not None else self._trib_issqn_default
        tp_ret_issqn = (
            pedido.tipo_retencao_iss if pedido.tipo_retencao_iss is not None
            else self._tipo_retencao_iss_default
        )

        doc = re.sub(r"\D", "", tom.documento or "")
        toma: dict = {
            "xNome": tom.nome,
            "end": {
                "cMun": cmun_tom,
                "UF": (tom.uf or "").upper(),
                "CEP": re.sub(r"\D", "", tom.cep or ""),
            },
        }
        if len(doc) == 14:
            toma["CNPJ"] = doc
        elif len(doc) == 11:
            toma["CPF"] = doc
        if tom.email:
            toma["email"] = tom.email

        inf_dps = {
            "tpAmb": tp_amb,
            "dhEmi": datetime.now(timezone.utc).isoformat(),
            "dCompet": compet,
            "prest": {
                "CNPJ": self._cnpj,
                # regTrib vem de NFSE_REGIME_TRIBUTARIO — CONFIRMADO com o
                # contador na configuração (nunca chutado aqui); muda a base
                # de cálculo da DPS. Ver _REGIME_TRIBUTARIO_MAP.
                "regTrib": {"opSimpNac": op_simp_nac, "regEspTrib": reg_esp_trib},
            },
            "toma": toma,
            "serv": {
                "locPrest": {"cLocPrestacao": cmun_prest},
                "cServ": {
                    "cTribNac": ctrib,
                    "cItemListaServico": item,
                    "xDescServ": pedido.descricao,
                },
            },
            "valores": {
                "vServPrest": {"vServ": round(float(pedido.valor), 2)},
                "trib": {
                    "tribMun": {
                        # tribISSQN/tpRetISSQN dependem do TOMADOR e do
                        # MUNICÍPIO dele (LC 116/2003 art. 6º; LC 123/2006
                        # art. 21 §4º) — nunca propriedade fixa do emitente.
                        # Default de config (NFSE_TRIB_ISSQN_DEFAULT/
                        # NFSE_TIPO_RETENCAO_ISS_DEFAULT), sobreponível por
                        # nota (pedido.trib_issqn/tipo_retencao_iss) quando o
                        # tomador exigir retenção.
                        "tribISSQN": trib_issqn,
                        "cLocIncid": cmun_prest,
                        "pAliq": round(float(aliq), 4),
                        "tpRetISSQN": tp_ret_issqn,
                    }
                },
            },
        }
        return {"ambiente": self._ambiente, "referencia": pedido.referencia, "infDPS": inf_dps}

    def _parse_resultado(self, js: dict | None) -> NFSeResultado:
        js = js or {}
        status = _mapear_status(str(js.get("status") or js.get("situacao") or ""))

        mensagens: list[str] = []
        err = js.get("erro") or js.get("error")
        if isinstance(err, dict):
            m = err.get("message") or err.get("mensagem")
            if m:
                mensagens.append(str(m))
        elif isinstance(err, str):
            mensagens.append(err)
        for m in (js.get("mensagens") or []):
            if isinstance(m, dict):
                mensagens.append(str(m.get("descricao") or m.get("mensagem") or m))
            else:
                mensagens.append(str(m))

        def _url(chave: str) -> str | None:
            v = js.get(chave)
            if isinstance(v, dict):
                return v.get("url")
            return js.get(f"{chave}_url") or (v if isinstance(v, str) else None)

        return NFSeResultado(
            status=status,
            provider_id=js.get("id"),
            numero=str(js.get("numero")) if js.get("numero") is not None else None,
            chave_acesso=js.get("chave_acesso") or js.get("chaveAcesso"),
            ambiente=js.get("ambiente") or self._ambiente,
            pdf_url=_url("pdf"),
            xml_url=_url("xml"),
            mensagens=mensagens,
            bruto={k: js.get(k) for k in ("id", "status", "numero", "chave_acesso", "ambiente")},
        )

    # ── Interface ──────────────────────────────────────────────────────────────

    async def emitir(self, pedido: NFSePedidoEmissao) -> NFSeResultado:
        self._exigir_config()
        self._exigir_definicoes_fiscais()
        corpo = self._montar_dps(pedido)
        js = await self._api("POST", "/nfse/dps", json=corpo)
        return self._parse_resultado(js)

    async def consultar(self, provider_id: str) -> NFSeResultado:
        self._exigir_config()
        js = await self._api("GET", f"/nfse/{provider_id}")
        return self._parse_resultado(js)

    async def baixar_pdf(self, provider_id: str) -> bytes:
        self._exigir_config()
        return await self._api("GET", f"/nfse/{provider_id}/pdf", want="bytes")

    async def baixar_xml(self, provider_id: str) -> str:
        self._exigir_config()
        return await self._api("GET", f"/nfse/{provider_id}/xml", want="text")

    async def cancelar(self, provider_id: str, motivo: str) -> NFSeResultado:
        self._exigir_config()
        js = await self._api(
            "POST", f"/nfse/{provider_id}/cancelamento", json={"justificativa": motivo}
        )
        return self._parse_resultado(js)
