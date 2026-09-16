# ── app/services/ajuizamento/conectores/eproc.py ─────────────────────────────
# EprocConnector — eproc (TRF4/TRF2/TRF6, TJRS, TJSC, TJTO, TJMG 2º grau…)
# NÃO possui API pública de peticionamento documentada de forma uniforme; cada
# tribunal habilita integração individualmente (webservice MNI próprio ou
# convênio). Por isso TUDO aqui é CONDITIONAL/REQUIRES_AUTHORIZATION por
# tribunal, dirigido pelo JudicialIntegrationProfile. Nenhum endpoint é
# presumido; sem perfil homologado com base_url informada pelo tribunal, não
# há chamada remota.
from __future__ import annotations

from app.services.ajuizamento.canonico import CanonicalJudicialCase
from app.services.ajuizamento.capacidades import ContextoConector, EstadoCapacidade
from app.services.ajuizamento.conectores.base import ConectorJudicial, ResultadoEnvio, ResultadoOperacao, hash_payload
from app.services.ajuizamento.conectores.pje_mni import mapear_para_mni


class EprocConnector(ConectorJudicial):
    chave = "eproc"
    sistema = "eproc"

    def declaradas(self, ctx: ContextoConector) -> dict[str, tuple[EstadoCapacidade, str]]:
        s = ctx.settings
        p = ctx.perfil
        if not s.EPROC_INTEGRATION_ENABLED:
            base = (EstadoCapacidade.CONDITIONAL, "EPROC_INTEGRATION_ENABLED=false")
        elif p is None:
            base = (EstadoCapacidade.REQUIRES_AUTHORIZATION, "sem perfil do tribunal eproc (convênio/habilitação individual)")
        elif not p.base_url or not p.documentation_url:
            base = (EstadoCapacidade.REQUIRES_AUTHORIZATION,
                    "perfil sem base_url/documentation_url fornecidos pelo tribunal — nenhum endpoint é presumido")
        else:
            base = (EstadoCapacidade.CONDITIONAL, "integração eproc dependente de homologação individual com o tribunal")
        return {
            "validate_target": (EstadoCapacidade.SUPPORTED, "validação local"),
            "file_new_case": base if not (p and p.filing_supported and base[0] == EstadoCapacidade.CONDITIONAL and ctx.homologado)
            else (EstadoCapacidade.SUPPORTED, "perfil eproc homologado"),
            "append_petition": base,
            "read_process": base if not (p and p.process_query_supported) else (EstadoCapacidade.CONDITIONAL, "consulta conforme convênio"),
            "read_movements": base if not (p and p.movement_query_supported) else (EstadoCapacidade.CONDITIONAL, "consulta conforme convênio"),
            "read_notices": base if not (p and p.notice_query_supported) else (EstadoCapacidade.CONDITIONAL, "consulta conforme convênio"),
            "download_document": base if not (p and p.document_download_supported) else (EstadoCapacidade.CONDITIONAL, "download conforme convênio"),
        }

    async def validate_target(self, ctx: ContextoConector, canonico: CanonicalJudicialCase) -> ResultadoOperacao:
        # eproc dos TRFs fala MNI; o mapeamento reaproveita o do PJe/MNI.
        versao = ctx.perfil.api_version if ctx.perfil and ctx.perfil.api_version else "2.2.2"
        m = mapear_para_mni(canonico, id_sistema_destino=ctx.perfil.tribunal_code if ctx.perfil else "", versao=versao)
        return ResultadoOperacao(EstadoCapacidade.CONDITIONAL, dados={"payload_hash": hash_payload(m.to_dict())},
                                 mensagem="mapeamento MNI genérico — campos específicos do eproc dependem do tribunal")

    async def file_new_case(self, ctx: ContextoConector, canonico: CanonicalJudicialCase,
                            *, idempotency_key: str) -> ResultadoEnvio:
        bloqueio = self._bloqueio_escrita(ctx, "file_new_case")
        if bloqueio is not None:
            return bloqueio
        # Perfil homologado, mas o contrato REST/SOAP do eproc de cada tribunal
        # não é público: sem documentação anexada ao perfil o envio não é
        # executado. Este é um estado honesto, não um placeholder.
        return ResultadoEnvio(
            EstadoCapacidade.REQUIRES_AUTHORIZATION,
            mensagem="contrato de peticionamento eproc deste tribunal não confirmado — registrar protocolo manualmente",
        )

    async def append_petition(self, ctx: ContextoConector, canonico: CanonicalJudicialCase,
                              *, numero_cnj: str, idempotency_key: str) -> ResultadoEnvio:
        return await self.file_new_case(ctx, canonico, idempotency_key=idempotency_key)
