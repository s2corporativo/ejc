# ── app/services/ajuizamento/orquestrador.py ─────────────────────────────────
# JudicialFilingService (FilingOrchestrator) — conduz o ajuizamento pela
# máquina de estados: criar (DRAFT) → validar (PREPARING → VALIDATING →
# INVALID | READY_FOR_REVIEW) → aprovar (REVISÃO HUMANA obrigatória →
# APPROVED) → assinar (SIGNING → READY_TO_SUBMIT) → protocolar (SUBMITTING →
# SUBMITTED/CONFIRMED | REQUIRES_AUTHORIZATION | FAILED) → confirmar manual
# → sincronizar (SYNCING → CONFIRMED). Todas as operações são "commit do
# chamador" (router) — uma transação por ação, auditada.
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.ajuizamento import (
    EstadoAjuizamento as E, JudicialFiling, JudicialFilingAttempt, JudicialFilingTransicao,
)
from app.models.case import Case
from app.models.case_parte import CaseParte
from app.models.client import Client
from app.models.document import Document
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.procuracao import Procuracao
from app.models.user import User
from app.services.ajuizamento import assinatura as assinatura_mod
from app.services.ajuizamento import estados
from app.services.ajuizamento.canonico import (
    CanonicalJudicialCase, DocumentoCanonico, TIPOS_DOCUMENTO, construir_canonico,
    documento_de_document, documento_de_peca,
)
from app.services.ajuizamento.capacidades import EstadoCapacidade
from app.services.ajuizamento.conectores.base import ErroConector, ResultadoEnvio, TimeoutConector
from app.services.ajuizamento.conectores.roteador import JudicialConnectorRouter, SistemaNaoSuportado
from app.services.ajuizamento.preflight import validar_preflight
from app.services.ajuizamento.registro_protocolo import formatar_cnj, registrar_protocolo, vincular_ao_caso
from app.services.ajuizamento.sincronizacao import JudicialSyncService
from app.services.ajuizamento.tpu_service import TpuService
from app.services.validators_service import normalizar_cnj, validar_cnj

CONFIRMACAO_REVISAO = "REVISAR E PROTOCOLAR"
STATUS_PECA_APROVADA = frozenset({PecaStatus.aprovada, PecaStatus.final, PecaStatus.protocolada})


class AjuizamentoError(ValueError):
    """Erro de regra de negócio (422)."""


class AjuizamentoNaoEncontrado(LookupError):
    pass


class JudicialFilingService:
    def __init__(self, db: AsyncSession, settings: Settings, roteador: JudicialConnectorRouter | None = None) -> None:
        self.db = db
        self.settings = settings
        self.roteador = roteador or JudicialConnectorRouter()

    # ── Carga ────────────────────────────────────────────────────────────
    async def obter(self, filing_id: str, *, lock: bool = False) -> JudicialFiling:
        stmt = select(JudicialFiling).where(JudicialFiling.id == filing_id, JudicialFiling.deleted_at.is_(None))
        if lock:
            stmt = stmt.with_for_update()
        f = (await self.db.execute(stmt)).scalar_one_or_none()
        if f is None:
            raise AjuizamentoNaoEncontrado("Ajuizamento não encontrado")
        return f

    async def listar(self, *, case_id: str | None = None, casos_visiveis: list[str] | None = None) -> list[JudicialFiling]:
        stmt = select(JudicialFiling).where(JudicialFiling.deleted_at.is_(None)).order_by(JudicialFiling.created_at.desc())
        if case_id:
            stmt = stmt.where(JudicialFiling.case_id == case_id)
        if casos_visiveis is not None:
            stmt = stmt.where(JudicialFiling.case_id.in_(casos_visiveis))
        return list((await self.db.execute(stmt)).scalars().all())

    # ── Criação / edição ─────────────────────────────────────────────────
    async def criar(self, *, case: Case, cu: User, dados: dict[str, Any]) -> JudicialFiling:
        f = JudicialFiling(
            id=str(uuid4()), case_id=case.id, client_id=case.client_id, estado=E.DRAFT.value,
            created_by=cu.id, created_at=datetime.now(timezone.utc),
            nivel_sigilo=5 if getattr(case, "sigilo_reforcado", False) else 0,
            valor_causa=case.valor_causa,
            jurisdicao=case.comarca, tribunal_code=(case.tribunal or "").upper() or None,
            advogados=[{"user_id": uid, "tipo": tipo} for uid, tipo in (
                (case.advogado_responsavel_id, "advogado"), (case.advogado_auxiliar_id, "advogado_auxiliar"),
            ) if uid],
        )
        self._aplicar(f, dados)
        self.db.add(f)
        self.db.add(JudicialFilingTransicao(
            id=str(uuid4()), filing_id=f.id, de_estado=None, para_estado=E.DRAFT.value,
            ator_id=cu.id, motivo="criado a partir do caso", created_at=datetime.now(timezone.utc),
        ))
        return f

    async def atualizar(self, filing: JudicialFiling, *, cu: User, dados: dict[str, Any]) -> JudicialFiling:
        if E(filing.estado) not in estados.ESTADOS_EDITAVEIS:
            raise AjuizamentoError(f"Ajuizamento em estado {filing.estado} não pode ser editado")
        self._aplicar(filing, dados)
        if E(filing.estado) != E.DRAFT:
            estados.transicionar(filing, E.DRAFT, ator_id=cu.id, motivo="edição após validação/revisão", db=self.db)
        filing.preflight = None
        filing.updated_at = datetime.now(timezone.utc)
        return filing

    _CAMPOS = (
        "profile_id", "peticao_legal_doc_id", "tribunal_code", "system", "segment", "degree",
        "environment", "jurisdicao", "codigo_localidade", "competencia", "competencia_codigo",
        "classe_codigo", "classe_nome", "assuntos", "valor_causa", "nivel_sigilo", "gratuidade",
        "tutela", "prioridade", "caracteristicas", "documentos", "advogados",
    )

    def _aplicar(self, f: JudicialFiling, dados: dict[str, Any]) -> None:
        for campo in self._CAMPOS:
            if campo not in dados or (dados[campo] is None and campo in ("assuntos", "documentos", "advogados")):
                continue
            valor = dados[campo]
            if campo == "tribunal_code" and valor:
                valor = str(valor).strip().upper()[:10]
            if campo == "valor_causa" and valor is not None:
                valor = Decimal(str(valor))
            if campo == "documentos" and valor is not None:
                for d in valor:
                    if d.get("document_type") not in TIPOS_DOCUMENTO:
                        raise AjuizamentoError(f"tipo de documento inválido: {d.get('document_type')}")
            setattr(f, campo, valor)

    # ── Canônico ─────────────────────────────────────────────────────────
    async def montar_canonico(self, filing: JudicialFiling) -> CanonicalJudicialCase:
        case = (await self.db.execute(select(Case).where(Case.id == filing.case_id))).scalar_one_or_none()
        client = (await self.db.execute(select(Client).where(Client.id == filing.client_id))).scalar_one_or_none()
        if case is None or client is None:
            raise AjuizamentoError("Caso ou cliente do ajuizamento não encontrado")
        partes = list((await self.db.execute(
            select(CaseParte).where(CaseParte.case_id == case.id, CaseParte.ativo.is_(True))
        )).scalars().all())

        ids_adv = [a.get("user_id") for a in (filing.advogados or []) if a.get("user_id")]
        usuarios = {}
        if ids_adv:
            usuarios = {u.id: u for u in (await self.db.execute(select(User).where(User.id.in_(ids_adv)))).scalars().all()}
        procuracoes = {}
        ids_proc = [a.get("procuracao_id") for a in (filing.advogados or []) if a.get("procuracao_id")]
        if ids_proc:
            procuracoes = {p.id: p for p in (await self.db.execute(
                select(Procuracao).where(Procuracao.id.in_(ids_proc), Procuracao.deleted_at.is_(None))
            )).scalars().all()}
        advogados = []
        for a in filing.advogados or []:
            u = usuarios.get(a.get("user_id"))
            if u is None:
                continue
            proc = procuracoes.get(a.get("procuracao_id"))
            if proc is not None and proc.client_id != client.id:
                raise AjuizamentoError("Procuração vinculada não pertence ao cliente do caso")
            advogados.append((u, a.get("tipo") or "advogado", proc))

        documentos: list[DocumentoCanonico] = []
        if filing.peticao_legal_doc_id:
            peca = (await self.db.execute(select(LegalDoc).where(
                LegalDoc.id == filing.peticao_legal_doc_id, LegalDoc.deleted_at.is_(None),
            ))).scalar_one_or_none()
            if peca is None:
                raise AjuizamentoError("Petição inicial (peça) não encontrada")
            if peca.case_id and peca.case_id != case.id:
                raise AjuizamentoError("A peça selecionada não pertence a este caso")
            assinatura = filing.assinatura or {}
            documentos.append(documento_de_peca(
                peca, ordem=0, sha256_pdf=assinatura.get("document_hash"),
                tpu_document_type=(filing.caracteristicas or {}).get("tpu_tipo_documento_peticao"),
            ))
            if assinatura:
                documentos[0] = DocumentoCanonico(**{**documentos[0].__dict__, "signed": True,
                                                     "signature_type": assinatura.get("signature_type", "icp_brasil")})
        ids_docs = [d.get("document_id") for d in (filing.documentos or []) if d.get("document_id")]
        docs_db = {}
        if ids_docs:
            docs_db = {d.id: d for d in (await self.db.execute(
                select(Document).where(Document.id.in_(ids_docs), Document.deleted_at.is_(None))
            )).scalars().all()}
        for i, d in enumerate(filing.documentos or [], start=1):
            doc = docs_db.get(d.get("document_id"))
            if doc is None:
                raise AjuizamentoError(f"Documento {d.get('document_id')} não encontrado ou excluído")
            if doc.case_id != case.id and doc.client_id != client.id:
                raise AjuizamentoError("Documento anexado não pertence ao caso/cliente")
            documentos.append(documento_de_document(
                doc, d.get("document_type", "complementar"), ordem=int(d.get("ordem", i)),
                tpu_document_type=d.get("tpu_document_type"),
            ))
        return construir_canonico(filing=filing, case=case, client=client, partes=partes,
                                  advogados=advogados, documentos=documentos)

    # ── Validação ────────────────────────────────────────────────────────
    async def validar(self, filing: JudicialFiling, *, cu: User) -> dict[str, Any]:
        if E(filing.estado) not in (E.DRAFT, E.INVALID, E.READY_FOR_REVIEW, E.REQUIRES_AUTHORIZATION, E.FAILED, E.PREPARING):
            raise AjuizamentoError(f"Validação não permitida no estado {filing.estado}")
        if E(filing.estado) != E.PREPARING:
            if E(filing.estado) != E.DRAFT:
                estados.transicionar(filing, E.DRAFT, ator_id=cu.id, motivo="revalidação", db=self.db)
            estados.transicionar(filing, E.PREPARING, ator_id=cu.id, motivo="montagem do canônico", db=self.db)
        canonico = await self.montar_canonico(filing)
        filing.canonico = canonico.to_dict()
        filing.canonico_hash = canonico.hash()
        estados.transicionar(filing, E.VALIDATING, ator_id=cu.id, db=self.db)

        matriz = None
        campos_destino: tuple[str, ...] = ()
        try:
            conector, ctx = await self.roteador.resolver(
                self.db, self.settings, sistema=filing.system, tribunal_code=filing.tribunal_code,
                degree=filing.degree, environment=filing.environment,
            )
            matriz = conector.capacidades(ctx)
            if ctx.perfil is not None:
                filing.profile_id = ctx.perfil.id
                checklist = ctx.perfil.homologation_checklist if isinstance(ctx.perfil.homologation_checklist, dict) else {}
                campos_destino = tuple(checklist.get("campos_obrigatorios") or ())
            alvo = await conector.validate_target(ctx, canonico)
        except SistemaNaoSuportado:
            alvo = None
        lookup = await TpuService(self.db).lookup_fn()
        resultado = validar_preflight(canonico, matriz, lookup_tpu=lookup, campos_obrigatorios_destino=campos_destino)
        if alvo is not None and alvo.dados.get("faltando"):
            for campo in alvo.dados["faltando"]:
                resultado.aviso(f"Mapeamento do destino sem '{campo}' — confirme antes do protocolo")
        saida = resultado.to_dict()
        saida["matriz"] = matriz.to_dict() if matriz else None
        saida["validado_em"] = datetime.now(timezone.utc).isoformat()
        filing.preflight = saida
        if resultado.ready:
            estados.transicionar(filing, E.READY_FOR_REVIEW, ator_id=cu.id, motivo="preflight ok", db=self.db)
        else:
            estados.transicionar(filing, E.INVALID, ator_id=cu.id, motivo="; ".join(resultado.errors)[:2000], db=self.db)
        return saida

    # ── Revisão humana ───────────────────────────────────────────────────
    async def aprovar(self, filing: JudicialFiling, *, cu: User, confirmacao: str, observacoes: str | None) -> JudicialFiling:
        if E(filing.estado) != E.READY_FOR_REVIEW:
            raise AjuizamentoError("Só é possível aprovar um ajuizamento validado (READY_FOR_REVIEW)")
        if (confirmacao or "").strip().upper() != CONFIRMACAO_REVISAO:
            raise AjuizamentoError(f'A aprovação exige a confirmação literal "{CONFIRMACAO_REVISAO}"')
        if not filing.preflight or not filing.preflight.get("ready"):
            raise AjuizamentoError("Preflight ausente ou com erros — revalide antes de aprovar")
        canonico = await self.montar_canonico(filing)
        if canonico.hash() != filing.canonico_hash:
            raise AjuizamentoError("Os dados do caso mudaram desde a validação — revalide antes de aprovar")
        if filing.peticao_legal_doc_id:
            peca = (await self.db.execute(select(LegalDoc).where(LegalDoc.id == filing.peticao_legal_doc_id))).scalar_one_or_none()
            if peca is None or peca.status not in STATUS_PECA_APROVADA or not peca.human_reviewed:
                raise AjuizamentoError("A petição inicial precisa estar aprovada com revisão humana (HITL) antes do protocolo")
        filing.aprovado_por = cu.id
        filing.aprovado_em = datetime.now(timezone.utc)
        estados.transicionar(filing, E.APPROVED, ator_id=cu.id,
                             motivo=f"revisão humana: {observacoes or CONFIRMACAO_REVISAO}", db=self.db)
        return filing

    # ── Assinatura ───────────────────────────────────────────────────────
    async def assinar(self, filing: JudicialFiling, *, cu: User, provider: str | None, dados: dict[str, Any]) -> dict[str, Any]:
        if E(filing.estado) not in (E.APPROVED, E.SIGNING):
            raise AjuizamentoError("Assinatura só após a aprovação (APPROVED)")
        if E(filing.estado) == E.APPROVED:
            estados.transicionar(filing, E.SIGNING, ator_id=cu.id, db=self.db)
        prov = assinatura_mod.provedor(provider)
        if dados.get("signed_document_id"):
            doc = (await self.db.execute(select(Document).where(
                Document.id == dados["signed_document_id"], Document.deleted_at.is_(None),
            ))).scalar_one_or_none()
            if doc is None or doc.case_id != filing.case_id:
                raise AjuizamentoError("Documento assinado não encontrado no caso")
            if doc.mimetype and doc.mimetype != "application/pdf":
                raise AjuizamentoError("O documento assinado deve ser PDF")
            dados = {**dados, "document_sha256": doc.sha256, "signed_document_hash": dados.get("signed_document_hash") or doc.sha256}
        base_hash = (filing.canonico or {}).get("documentos", [{}])[0].get("sha256") if filing.canonico else None
        resultado = await prov.assinar(document_hash=base_hash or "", dados=dados)
        if not resultado.ok:
            estados.transicionar(filing, E.APPROVED, ator_id=cu.id, motivo=f"assinatura não concluída: {resultado.mensagem}", db=self.db)
            return {"estado": resultado.estado.value, "mensagem": resultado.mensagem, "filing_estado": filing.estado}
        filing.assinatura = resultado.evidencia.to_dict()
        filing.assinado_por = cu.id
        filing.assinado_em = resultado.evidencia.signed_at
        # Reconstrói o canônico com a petição marcada como assinada.
        canonico = await self.montar_canonico(filing)
        filing.canonico = canonico.to_dict()
        filing.canonico_hash = canonico.hash()
        estados.transicionar(filing, E.READY_TO_SUBMIT, ator_id=cu.id, motivo="assinatura registrada", db=self.db)
        return {"estado": resultado.estado.value, "mensagem": resultado.mensagem,
                "evidencia": filing.assinatura, "filing_estado": filing.estado}

    # ── Protocolo (idempotente) ──────────────────────────────────────────
    @staticmethod
    def _idempotency_key(filing: JudicialFiling, numero: int) -> str:
        return hashlib.sha256(f"{filing.id}|{numero}|{filing.canonico_hash}".encode()).hexdigest()

    async def _tentativas(self, filing: JudicialFiling) -> list[JudicialFilingAttempt]:
        return list((await self.db.execute(
            select(JudicialFilingAttempt).where(JudicialFilingAttempt.filing_id == filing.id)
            .order_by(JudicialFilingAttempt.numero)
        )).scalars().all())

    async def protocolar(self, filing: JudicialFiling, *, cu: User) -> dict[str, Any]:
        # IDEMPOTÊNCIA PRIMEIRO: uma repetição do POST (clique duplo, retry do
        # cliente, replay) devolve o protocolo já obtido em vez de erro de
        # estado — e jamais reenvia ao tribunal.
        tentativas = await self._tentativas(filing)
        for t in tentativas:
            if t.estado in ("SUBMITTED", "CONFIRMED") and (t.external_protocol or t.external_process_id):
                return {"reutilizada": True, "tentativa": t.numero, "estado": t.estado,
                        "external_protocol": t.external_protocol, "cnj_number": filing.numero_cnj}
        if E(filing.estado) not in (E.READY_TO_SUBMIT, E.FAILED, E.REQUIRES_AUTHORIZATION):
            raise AjuizamentoError("Protocolo só após aprovação e assinatura (READY_TO_SUBMIT)")
        if not filing.aprovado_por or not filing.assinatura:
            raise AjuizamentoError("Ajuizamento sem aprovação humana ou sem assinatura registrada")
        if not self.settings.JUDICIAL_FILING_ENABLED:
            raise AjuizamentoError("JUDICIAL_FILING_ENABLED=false — protocolo eletrônico desligado")

        ultima = tentativas[-1] if tentativas else None
        numero = (ultima.numero + 1) if ultima else 1
        chave = self._idempotency_key(filing, numero)

        if E(filing.estado) != E.READY_TO_SUBMIT:
            estados.transicionar(filing, E.READY_TO_SUBMIT, ator_id=cu.id, motivo="nova tentativa", db=self.db)
        estados.transicionar(filing, E.SUBMITTING, ator_id=cu.id, motivo=f"tentativa {numero}", db=self.db)
        canonico = await self.montar_canonico(filing)
        try:
            conector, ctx = await self.roteador.resolver(
                self.db, self.settings, sistema=filing.system, tribunal_code=filing.tribunal_code,
                degree=filing.degree, environment=filing.environment,
            )
        except SistemaNaoSuportado as exc:
            estados.transicionar(filing, E.FAILED, ator_id=cu.id, motivo=str(exc), db=self.db)
            raise AjuizamentoError(str(exc)) from exc

        # Gate do orquestrador (defesa em profundidade — o conector também
        # bloqueia): sem capacidade SUPPORTED para file_new_case, nenhuma
        # chamada remota acontece e o fluxo segue pelo registro manual.
        matriz = conector.capacidades(ctx)
        if not matriz.pode("file_new_case"):
            item = matriz.itens.get("file_new_case")
            motivo = (item.motivo if item else "") or "protocolo eletrônico indisponível para este destino"
            tentativa_bloqueada = JudicialFilingAttempt(
                id=str(uuid4()), filing_id=filing.id, numero=numero, connector=conector.chave,
                idempotency_key=chave, request_hash=filing.canonico_hash,
                estado="REQUIRES_AUTHORIZATION", detalhe=motivo[:2000],
                iniciada_em=datetime.now(timezone.utc), concluida_em=datetime.now(timezone.utc),
                created_by=cu.id,
            )
            self.db.add(tentativa_bloqueada)
            filing.ultimo_erro = motivo
            estados.transicionar(filing, E.REQUIRES_AUTHORIZATION, ator_id=cu.id, motivo=motivo[:500], db=self.db)
            return {"estado": filing.estado, "tentativa": numero, "mensagem": motivo,
                    "requisitos_autorizacao": matriz.requisitos_autorizacao,
                    "registro_manual_disponivel": True}

        # Após TIMEOUT anterior: consultar o recibo/estado remoto antes de reenviar.
        if ultima is not None and ultima.estado == "TIMEOUT":
            recibo = await conector.get_receipt(ctx, idempotency_key=ultima.idempotency_key,
                                                external_protocol=ultima.external_protocol)
            if recibo.ok and (recibo.dados.get("protocol_number") or recibo.dados.get("cnj_number")):
                return await self._concluir_envio(filing, cu, ultima, conector.chave, ResultadoEnvio(
                    EstadoCapacidade.SUPPORTED, protocol_number=recibo.dados.get("protocol_number"),
                    cnj_number=recibo.dados.get("cnj_number"), confirmado=bool(recibo.dados.get("cnj_number")),
                    response_hash=recibo.response_hash, mensagem="recuperado do recibo remoto"))
            if recibo.estado in (EstadoCapacidade.UNSUPPORTED, EstadoCapacidade.REQUIRES_AUTHORIZATION, EstadoCapacidade.CONDITIONAL):
                estados.transicionar(filing, E.FAILED, ator_id=cu.id,
                                     motivo="timeout anterior sem meio de verificar o recibo remoto — verificação manual obrigatória", db=self.db)
                filing.ultimo_erro = "Tentativa anterior expirou e o conector não permite consultar o recibo; confirme no portal do tribunal antes de reenviar (confirmar-manual)."
                return {"estado": filing.estado, "requer_verificacao_manual": True, "mensagem": filing.ultimo_erro}

        tentativa = JudicialFilingAttempt(
            id=str(uuid4()), filing_id=filing.id, numero=numero, connector=conector.chave,
            idempotency_key=chave, request_hash=filing.canonico_hash, estado="SUBMITTING",
            iniciada_em=datetime.now(timezone.utc), created_by=cu.id,
        )
        self.db.add(tentativa)
        try:
            resultado = await conector.file_new_case(ctx, canonico, idempotency_key=chave)
        except TimeoutConector as exc:
            tentativa.estado, tentativa.detalhe, tentativa.concluida_em = "TIMEOUT", str(exc), datetime.now(timezone.utc)
            filing.ultimo_erro = str(exc)
            estados.transicionar(filing, E.FAILED, ator_id=cu.id, motivo="timeout remoto", db=self.db)
            return {"estado": filing.estado, "tentativa": numero, "mensagem": str(exc), "timeout": True}
        except ErroConector as exc:
            tentativa.estado, tentativa.detalhe, tentativa.concluida_em = "FAILED", str(exc), datetime.now(timezone.utc)
            filing.ultimo_erro = str(exc)
            estados.transicionar(filing, E.FAILED, ator_id=cu.id, motivo=str(exc)[:500], db=self.db)
            return {"estado": filing.estado, "tentativa": numero, "mensagem": str(exc)}
        return await self._concluir_envio(filing, cu, tentativa, conector.chave, resultado)

    async def _concluir_envio(self, filing: JudicialFiling, cu: User, tentativa: JudicialFilingAttempt,
                              conector: str, resultado: ResultadoEnvio) -> dict[str, Any]:
        agora = datetime.now(timezone.utc)
        tentativa.concluida_em = agora
        tentativa.response_hash = resultado.response_hash
        tentativa.detalhe = resultado.mensagem[:2000] if resultado.mensagem else None
        if resultado.estado in (EstadoCapacidade.REQUIRES_AUTHORIZATION, EstadoCapacidade.CONDITIONAL, EstadoCapacidade.UNSUPPORTED):
            tentativa.estado = "REQUIRES_AUTHORIZATION" if resultado.estado != EstadoCapacidade.CONDITIONAL else "FAILED"
            if resultado.estado == EstadoCapacidade.CONDITIONAL and resultado.dados.get("resposta_incompleta"):
                filing.ultimo_erro = f"resposta incompleta do tribunal: {resultado.mensagem}"
                estados.transicionar(filing, E.FAILED, ator_id=cu.id, motivo=filing.ultimo_erro[:500], db=self.db)
            else:
                filing.ultimo_erro = resultado.mensagem
                estados.transicionar(filing, E.REQUIRES_AUTHORIZATION, ator_id=cu.id, motivo=resultado.mensagem[:500], db=self.db)
            return {"estado": filing.estado, "tentativa": tentativa.numero, "mensagem": resultado.mensagem,
                    "requisitos_autorizacao": resultado.dados.get("requisitos_autorizacao", []),
                    "registro_manual_disponivel": True}
        if not (resultado.protocol_number or resultado.cnj_number or resultado.external_process_id):
            tentativa.estado = "FAILED"
            filing.ultimo_erro = "resposta do tribunal sem protocolo, número CNJ ou id externo"
            estados.transicionar(filing, E.FAILED, ator_id=cu.id, motivo=filing.ultimo_erro, db=self.db)
            return {"estado": filing.estado, "tentativa": tentativa.numero, "mensagem": filing.ultimo_erro}
        tentativa.estado = "CONFIRMED" if resultado.confirmado else "SUBMITTED"
        tentativa.external_protocol = (resultado.protocol_number or "")[:120] or None
        tentativa.external_process_id = (resultado.external_process_id or "")[:120] or None
        protocolo = await registrar_protocolo(
            self.db, filing=filing, attempt_id=tentativa.id, connector=conector,
            idempotency_key=tentativa.idempotency_key, external_protocol=resultado.protocol_number,
            external_process_id=resultado.external_process_id, cnj_number=resultado.cnj_number,
            distribution_unit=resultado.distribution_unit, status=tentativa.estado,
            receipt_document_id=None, request_hash=tentativa.request_hash, response_hash=resultado.response_hash,
            confirmado=resultado.confirmado, created_by=cu.id,
        )
        filing.ultimo_erro = None
        estados.transicionar(filing, E.CONFIRMED if resultado.confirmado else E.SUBMITTED, ator_id=cu.id,
                             motivo=f"protocolo {protocolo.external_protocol or protocolo.cnj_number}", db=self.db)
        vinculo = await vincular_ao_caso(self.db, filing=filing, protocolo=protocolo, ator_id=cu.id)
        return {"estado": filing.estado, "tentativa": tentativa.numero, "protocolo": protocolo.id,
                "external_protocol": protocolo.external_protocol, "cnj_number": protocolo.cnj_number,
                "distribution_unit": protocolo.distribution_unit, "recibo": resultado.receipt, "vinculo": vinculo}

    # ── Confirmação manual (protocolo feito no portal do tribunal) ───────
    async def confirmar_manual(self, filing: JudicialFiling, *, cu: User, dados: dict[str, Any]) -> dict[str, Any]:
        if E(filing.estado) not in (E.READY_TO_SUBMIT, E.REQUIRES_AUTHORIZATION, E.FAILED, E.SUBMITTED):
            raise AjuizamentoError("Confirmação manual só após aprovação/assinatura ou tentativa sem protocolo eletrônico")
        if not filing.aprovado_por:
            raise AjuizamentoError("Ajuizamento sem aprovação humana registrada")
        numero_cnj = (dados.get("cnj_number") or "").strip()
        protocolo_ext = (dados.get("external_protocol") or "").strip()
        if not numero_cnj and not protocolo_ext:
            raise AjuizamentoError("Informe o número CNJ ou o número do protocolo")
        recibo_id = (dados.get("receipt_document_id") or "").strip() or None
        if recibo_id:
            doc = (await self.db.execute(select(Document).where(Document.id == recibo_id, Document.deleted_at.is_(None)))).scalar_one_or_none()
            if doc is None or doc.case_id != filing.case_id:
                raise AjuizamentoError("Comprovante inválido: documento não encontrado ou de outro caso")
        # DV do CNJ conferido ANTES de qualquer transição: entrada inválida não
        # pode deixar o ajuizamento preso em SUBMITTING.
        if numero_cnj and len(normalizar_cnj(numero_cnj)) == 20 and not validar_cnj(formatar_cnj(numero_cnj)):
            raise AjuizamentoError("Número CNJ inválido (dígito verificador não confere)")
        tentativas = await self._tentativas(filing)
        ultima = tentativas[-1] if tentativas else None
        if E(filing.estado) != E.SUBMITTED:
            if E(filing.estado) != E.SUBMITTING:
                if E(filing.estado) != E.READY_TO_SUBMIT:
                    estados.transicionar(filing, E.READY_TO_SUBMIT, ator_id=cu.id, motivo="confirmação manual", db=self.db)
                estados.transicionar(filing, E.SUBMITTING, ator_id=cu.id, motivo="protocolo manual no portal", db=self.db)
        protocolo = await registrar_protocolo(
            self.db, filing=filing, attempt_id=ultima.id if ultima else None, connector="manual",
            idempotency_key=ultima.idempotency_key if ultima else None, external_protocol=protocolo_ext or None,
            external_process_id=dados.get("external_process_id"), cnj_number=numero_cnj or None,
            distribution_unit=dados.get("distribution_unit"), status="CONFIRMED", receipt_document_id=recibo_id,
            request_hash=filing.canonico_hash, response_hash=None, confirmado=True, created_by=cu.id,
        )
        if dados.get("protocolado_em"):
            protocolo.submitted_at = protocolo.confirmed_at = dados["protocolado_em"]
            filing.protocolado_em = dados["protocolado_em"]
        filing.ultimo_erro = None
        estados.transicionar(filing, E.CONFIRMED, ator_id=cu.id,
                             motivo=f"protocolo manual {protocolo.external_protocol or protocolo.cnj_number}", db=self.db)
        vinculo = await vincular_ao_caso(self.db, filing=filing, protocolo=protocolo, ator_id=cu.id)
        return {"estado": filing.estado, "protocolo": protocolo.id, "cnj_number": protocolo.cnj_number,
                "external_protocol": protocolo.external_protocol, "vinculo": vinculo}

    # ── Sincronização ────────────────────────────────────────────────────
    async def sincronizar(self, filing: JudicialFiling, *, cu: User) -> dict[str, Any]:
        if E(filing.estado) not in (E.SUBMITTED, E.CONFIRMED):
            raise AjuizamentoError("Sincronização só após o protocolo (SUBMITTED/CONFIRMED)")
        estados.transicionar(filing, E.SYNCING, ator_id=cu.id, db=self.db)
        try:
            saida = await JudicialSyncService(self.db, self.settings).sincronizar(filing)
        except Exception as exc:  # noqa: BLE001
            estados.transicionar(filing, E.FAILED, ator_id=cu.id, motivo=f"sync: {type(exc).__name__}", db=self.db)
            raise
        estados.transicionar(filing, E.CONFIRMED, ator_id=cu.id, motivo="sincronizado", db=self.db)
        return saida

    async def cancelar(self, filing: JudicialFiling, *, cu: User, motivo: str | None) -> JudicialFiling:
        if E(filing.estado) in estados.ESTADOS_PROTOCOLADOS:
            raise AjuizamentoError("Ajuizamento já protocolado não pode ser cancelado")
        estados.transicionar(filing, E.CANCELLED, ator_id=cu.id, motivo=motivo or "cancelado", db=self.db)
        return filing


def filing_para_dict(f: JudicialFiling, *, incluir_canonico: bool = True) -> dict[str, Any]:
    return {
        "id": f.id, "case_id": f.case_id, "client_id": f.client_id, "profile_id": f.profile_id,
        "peticao_legal_doc_id": f.peticao_legal_doc_id, "estado": f.estado,
        "tribunal_code": f.tribunal_code, "system": f.system, "segment": f.segment, "degree": f.degree,
        "environment": f.environment, "jurisdicao": f.jurisdicao, "codigo_localidade": f.codigo_localidade,
        "competencia": f.competencia, "competencia_codigo": f.competencia_codigo,
        "classe_codigo": f.classe_codigo, "classe_nome": f.classe_nome, "assuntos": f.assuntos or [],
        "valor_causa": str(f.valor_causa) if f.valor_causa is not None else None,
        "nivel_sigilo": f.nivel_sigilo, "gratuidade": f.gratuidade, "tutela": f.tutela,
        "prioridade": f.prioridade, "caracteristicas": f.caracteristicas or {},
        "documentos": f.documentos or [], "advogados": f.advogados or [],
        "canonico": f.canonico if incluir_canonico else None, "canonico_hash": f.canonico_hash,
        "preflight": f.preflight, "assinatura": f.assinatura,
        "aprovado_por": f.aprovado_por, "aprovado_em": f.aprovado_em.isoformat() if f.aprovado_em else None,
        "assinado_por": f.assinado_por, "assinado_em": f.assinado_em.isoformat() if f.assinado_em else None,
        "protocolado_em": f.protocolado_em.isoformat() if f.protocolado_em else None,
        "numero_cnj": f.numero_cnj, "process_id": f.process_id, "ultimo_erro": f.ultimo_erro,
        "created_by": f.created_by,
        "created_at": f.created_at.isoformat() if f.created_at else None,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }
