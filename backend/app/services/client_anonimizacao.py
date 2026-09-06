# ── app/services/client_anonimizacao.py ───────────────────────────────────────
# Direito ao esquecimento (LGPD art. 17) — Bloco 6b da auditoria EJC.
#
# NÃO é exclusão física. A LGPD (art. 16, II) permite reter dados quando
# necessário para cumprimento de obrigação legal/regulatória (fiscal, dever
# de guarda de honorários/processos) — por isso o registro do cliente
# permanece (id, casos, financeiro), mas os campos de identificação pessoal
# são substituídos por placeholders. Reversível apenas no sentido técnico de
# "não apaga histórico jurídico/fiscal"; a PII em si NÃO é recuperável após
# a anonimização (é sobrescrita, não só ocultada).
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.case import Case, CaseStatus
from app.models.case_parte import CaseParte
from app.models.especializado import TrabalhistaCase
from app.models.user import User
from app.models.legal_doc import LegalDoc, PecaStatus
from app.models.audit_log import criar_audit_log

_MARCADOR = "[ANONIMIZADO — LGPD ART. 17]"

# Casos nestes status representam representação jurídica EM CURSO — o
# escritório tem obrigação de saber quem é o cliente enquanto atua por ele.
# Anonimizar durante isso comprometeria o próprio dever profissional (EOAB).
_STATUS_BLOQUEIA_ANONIMIZACAO = {
    CaseStatus.aberto, CaseStatus.em_instrucao, CaseStatus.em_producao, CaseStatus.protocolado,
}

# Documentos de admissão ainda editáveis podem ser efetivamente redigidos e
# soft-deleted na mesma transação da anonimização. Já um documento aprovado,
# final ou protocolado pode representar instrumento jurídico cuja retenção
# precisa de decisão própria. O serviço NÃO presume prazo/base de guarda e não
# deixa `forcar=true` apagar esse conteúdo silenciosamente.
_STATUS_ADMISSAO_REDIGIVEL = {
    PecaStatus.rascunho,
    PecaStatus.em_revisao,
    PecaStatus.corrigida,
}
_STATUS_ADMISSAO_RETENCAO = {
    PecaStatus.aprovada,
    PecaStatus.final,
    PecaStatus.protocolada,
}


async def _docs_admissao_ativos(db: AsyncSession, client_id: str) -> list[LegalDoc]:
    return (await db.execute(
        select(LegalDoc).where(
            LegalDoc.client_id == client_id,
            LegalDoc.client_admission_kind.is_not(None),
            LegalDoc.deleted_at.is_(None),
        )
    )).scalars().all()


async def verificar_bloqueios(db: AsyncSession, client_id: str) -> list[str]:
    """Retorna motivos que impedem a anonimização agora (lista vazia = liberado)."""
    motivos = []
    casos_ativos = (await db.execute(
        select(Case.numero_interno, Case.status).where(
            Case.client_id == client_id,
            Case.deleted_at.is_(None),
            Case.status.in_(_STATUS_BLOQUEIA_ANONIMIZACAO),
        )
    )).all()
    if casos_ativos:
        numeros = ", ".join(c.numero_interno or "sem número" for c in casos_ativos)
        motivos.append(
            f"{len(casos_ativos)} caso(s) em representação ativa ({numeros}). "
            "Encerre ou arquive antes de anonimizar — o escritório precisa "
            "identificar o cliente enquanto atua por ele (dever profissional OAB)."
        )

    docs = await _docs_admissao_ativos(db, client_id)
    retidos = [d for d in docs if d.status in _STATUS_ADMISSAO_RETENCAO]
    if retidos:
        motivos.append(
            f"{len(retidos)} documento(s) de admissão aprovado/final/protocolado "
            "exigem decisão explícita de retenção antes da anonimização. "
            "O sistema não presume base ou prazo de guarda e não elimina "
            "instrumento jurídico consolidado automaticamente."
        )
    return motivos


async def anonimizar_cliente(
    db: AsyncSession, client_id: str, executor_id: str, executor_role: str,
    motivo: str | None = None, forcar: bool = False,
) -> dict:
    """
    Executa a anonimização. Levanta HTTPException se bloqueado (a menos que
    forcar=True para bloqueios operacionais de representação ativa).

    Documentos de admissão aprovados/finais/protocolados são um bloqueio não
    sobreponível por `forcar`: a decisão sobre retenção precisa ser tratada no
    lifecycle documental, sem o serviço inventar fundamento ou prazo de guarda.
    """
    cliente = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    if cliente.anonimizado_em:
        raise HTTPException(409, "Cliente já foi anonimizado anteriormente")

    docs_admissao = await _docs_admissao_ativos(db, client_id)
    docs_retencao = [d for d in docs_admissao if d.status in _STATUS_ADMISSAO_RETENCAO]
    if docs_retencao:
        raise HTTPException(409, {
            "mensagem": (
                "Anonimização bloqueada por documento de admissão consolidado. "
                "Defina primeiro a retenção ou o descarte governado do documento; "
                "forcar=true não ignora este bloqueio."
            ),
            "bloqueios": [
                f"{len(docs_retencao)} documento(s) de admissão exigem decisão de retenção"
            ],
        })

    bloqueios = await verificar_bloqueios(db, client_id)
    if bloqueios and not forcar:
        raise HTTPException(409, {
            "mensagem": "Anonimização bloqueada — resolva as pendências ou "
                        "confirme com forcar=true (decisão registrada em auditoria).",
            "bloqueios": bloqueios,
        })

    motivo_limpo = (motivo or "").strip()
    if bloqueios and forcar and not motivo_limpo:
        # Transformação irreversível + override de representação ativa exige
        # fundamento explícito. O texto livre é exigido como confirmação humana,
        # mas NÃO é persistido no WORM, pois pode conter PII/dado sensível.
        raise HTTPException(
            422,
            "Justificativa obrigatória para anonimização forçada com bloqueios ativos",
        )

    # Auditoria usa somente vocabulário controlado. Nunca persiste o teor livre
    # de `motivo`: sanitização por regex não garante remoção de nomes de terceiros,
    # saúde ou outros dados sensíveis que poderiam ficar imutáveis no WORM.
    codigo_justificativa = (
        "OVERRIDE_REPRESENTACAO_ATIVA"
        if bloqueios and forcar
        else "ANONIMIZACAO_SEM_BLOQUEIO"
    )

    agora = datetime.now(timezone.utc)

    # Sobrescreve PII. Mantém: id, tipo, status, created_at, relacionamentos
    # (casos, documentos, financeiro) — preservados por obrigação legal.
    cliente.nome = _MARCADOR if cliente.nome else cliente.nome
    cliente.razao_social = _MARCADOR if cliente.razao_social else cliente.razao_social
    cliente.nome_fantasia = None
    # Cutover C6/LGPD: cpf/cnpj em texto puro não existem mais (dropados na
    # migration 112). Limpa os campos cifrados/hash — senão a anonimização
    # ficaria incompleta (cpf_enc ainda decifrável, cpf_hash ainda comparável).
    cliente.cpf_enc = None
    cliente.cnpj_enc = None
    cliente.cpf_hash = None
    cliente.cnpj_hash = None
    cliente.data_nascimento = None
    cliente.profissao = None
    cliente.email = None
    cliente.telefone = None
    cliente.whatsapp = None
    cliente.cep = None
    cliente.logradouro = None
    cliente.numero = None
    cliente.complemento = None
    cliente.bairro = None
    cliente.observacoes = None
    cliente.anonimizado_em = agora

    # DB-03 (auditoria de camadas 06/09/2026): as PARTES vinculadas ao cliente
    # (`case_partes.client_id`) — o cadastro manual e a Entrada Única criam a
    # parte "autor" apontando para o cliente, com nome, documento e contato
    # copiados. Sem isto, após o "esquecimento" sobrava PII do titular
    # amarrada ao caso. Partes SEM client_id (adversas, testemunhas) são
    # terceiros e não são tocadas: o pedido é do cliente, não delas.
    partes = (await db.execute(
        select(CaseParte).where(CaseParte.client_id == client_id)
    )).scalars().all()
    for parte in partes:
        parte.nome = _MARCADOR
        # Coluna em claro (legado), cifra e hash — os três, senão fica
        # documento decifrável/comparável (mesma regra de clients).
        parte.cpf_cnpj_plain = None
        parte.cpf_cnpj_enc = None
        parte.cpf_cnpj_hash = None
        parte.email = None
        parte.telefone = None
        parte.qualificacao = None
        parte.representante_legal = None
    partes_anonimizadas = len(partes)

    # Dado de SAÚDE (LGPD art. 11): o CID do satélite trabalhista dos casos do
    # cliente. Não há finalidade que sobreviva ao esquecimento; o restante do
    # satélite (valores, datas) é histórico processual e fica.
    casos_do_cliente = select(Case.id).where(Case.client_id == client_id)
    res_cid = await db.execute(
        update(TrabalhistaCase)
        .where(TrabalhistaCase.case_id.in_(casos_do_cliente), TrabalhistaCase.cid.is_not(None))
        .values(cid=None)
        .execution_options(synchronize_session=False)
    )
    cids_removidos = int(res_cid.rowcount or 0)

    # Rascunhos/documentos de admissão ainda não consolidados podem conter a
    # qualificação completa em texto puro. Soft-delete sozinho não bastaria:
    # preservaria a PII no banco/lixeira. Por isso o conteúdo é sobrescrito e a
    # peça sai do acervo ativo na mesma transação.
    docs_redigidos = 0
    for doc in docs_admissao:
        if doc.status not in _STATUS_ADMISSAO_REDIGIVEL:
            continue
        kind = (doc.client_admission_kind or "documento")[:40]
        doc.titulo = f"Documento de admissão anonimizado ({kind})"
        doc.conteudo = _MARCADOR
        doc.notas_revisao = None
        doc.deleted_at = agora
        docs_redigidos += 1

    # Portal do cliente: desativa qualquer login vinculado — a identidade que
    # existia (nome/e-mail) não corresponde mais aos dados reais.
    usuarios_portal = (await db.execute(
        select(User).where(User.client_id == client_id, User.is_active.is_(True))
    )).scalars().all()
    for u in usuarios_portal:
        u.is_active = False

    # WORM: somente metadados controlados, suficientes para comprovar o tipo da
    # decisão sem reter texto livre potencialmente pessoal/sensível.
    detalhes = (
        "Anonimização LGPD art.17; "
        f"justificativa_informada={'sim' if bool(motivo_limpo) else 'nao'}; "
        f"codigo={codigo_justificativa}; "
        f"docs_admissao_redigidos={docs_redigidos}; "
        f"partes_anonimizadas={partes_anonimizadas}; cids_removidos={cids_removidos}"
    )
    if bloqueios:
        detalhes += f"; FORÇADO apesar de {len(bloqueios)} bloqueio(s) operacional(is)"
    await criar_audit_log(
        db,
        executor_id,
        executor_role,
        "ANONIMIZAR_LGPD",
        "clients",
        client_id,
        detalhes=detalhes,
        dados_depois={
            "forcado": bool(forcar and bloqueios),
            "bloqueios_ignorados": len(bloqueios),
            "justificativa_informada": bool(motivo_limpo),
            "codigo_justificativa": codigo_justificativa,
            "docs_admissao_redigidos": docs_redigidos,
            "partes_anonimizadas": partes_anonimizadas,
            "cids_removidos": cids_removidos,
        },
    )
    await db.commit()

    return {
        "client_id": client_id,
        "anonimizado_em": agora.isoformat(),
        "portal_desativado_para": [u.id for u in usuarios_portal],
        "bloqueios_ignorados": bloqueios if bloqueios else None,
        "documentos_admissao_anonimizados": docs_redigidos,
        "partes_anonimizadas": partes_anonimizadas,
        "cids_removidos": cids_removidos,
    }
