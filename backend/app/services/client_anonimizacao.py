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
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.client import Client
from app.models.case import Case, CaseStatus
from app.models.case_parte import CaseParte
from app.models.sociedade_cliente import SociedadeCliente, SocioSociedade
from app.models.user import User
from app.models.audit_log import criar_audit_log

_MARCADOR = "[ANONIMIZADO — LGPD ART. 17]"

# Casos nestes status representam representação jurídica EM CURSO — o
# escritório tem obrigação de saber quem é o cliente enquanto atua por ele.
# Anonimizar durante isso comprometeria o próprio dever profissional (EOAB).
_STATUS_BLOQUEIA_ANONIMIZACAO = {
    CaseStatus.aberto, CaseStatus.em_instrucao, CaseStatus.em_producao, CaseStatus.protocolado,
}


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
    return motivos


async def anonimizar_cliente(
    db: AsyncSession, client_id: str, executor_id: str, executor_role: str,
    motivo: str | None = None, forcar: bool = False,
) -> dict:
    """
    Executa a anonimização. Levanta HTTPException se bloqueado (a menos que
    forcar=True — reservado para gestão, com o bloqueio registrado no log
    mesmo assim, para rastreabilidade da decisão de forçar).
    """
    cliente = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not cliente:
        raise HTTPException(404, "Cliente não encontrado")
    if cliente.anonimizado_em:
        raise HTTPException(409, "Cliente já foi anonimizado anteriormente")

    bloqueios = await verificar_bloqueios(db, client_id)
    if bloqueios and not forcar:
        raise HTTPException(409, {
            "mensagem": "Anonimização bloqueada — resolva as pendências ou "
                        "confirme com forcar=true (decisão registrada em auditoria).",
            "bloqueios": bloqueios,
        })

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

    # ── P1-6 da auditoria integral (docs/auditoria-ejc/07-banco-de-dados.md §5.2)
    # Antes daqui a anonimização parava em `clients`, e o titular seguia
    # recuperável por consulta às tabelas satélite — o que descaracteriza o
    # atendimento ao art. 17. As três abaixo carregam o MESMO dado pessoal.

    # 1) case_partes — o titular costuma ser parte do próprio caso, via
    #    client_id. Sem isto, o documento apagado de `clients` continuaria
    #    recuperável aqui. As três colunas de PII saem juntas: o HASH também é
    #    reidentificador (quem tem o CPF confirma a identidade comparando o
    #    HMAC), então zerar só o ciphertext não anonimizaria nada.
    partes = (await db.execute(
        select(CaseParte).where(CaseParte.client_id == client_id)
    )).scalars().all()
    for parte in partes:
        parte.nome = _MARCADOR          # NOT NULL no banco — marcador, não None
        parte.cpf_cnpj_enc = None
        parte.cpf_cnpj_hash = None
        parte.cpf_cnpj_mascarado = None
        parte.email = None
        parte.telefone = None
        parte.representante_legal = None

    # 2) Sociedades e sócios do titular — CNPJ, razão social e documento do
    #    sócio são dado pessoal de PJ/PF vinculado ao mesmo titular. Sem filtro
    #    de `deleted_at`: sociedade soft-deletada continua guardando a PII.
    sociedades = (await db.execute(
        select(SociedadeCliente).where(SociedadeCliente.client_id == client_id)
    )).scalars().all()
    for soc in sociedades:
        soc.razao_social = _MARCADOR    # NOT NULL no banco
        soc.cnpj = None
    if sociedades:
        socios = (await db.execute(
            select(SocioSociedade).where(
                SocioSociedade.sociedade_id.in_([s.id for s in sociedades])
            )
        )).scalars().all()
        for socio in socios:
            socio.nome = _MARCADOR      # NOT NULL no banco
            socio.documento_enc = None
            socio.documento_hash = None
            socio.documento_mascarado = None

    # Portal do cliente: desativa qualquer login vinculado E apaga a identidade.
    #
    # 3) Antes só havia `is_active = False`, e só para os ATIVOS. Desativar não
    #    anonimiza: `email` e `full_name` do usuário de portal SÃO o nome e o
    #    e-mail do titular, e continuavam legíveis em `users` — inclusive nos
    #    logins já desativados, que o filtro antigo nem alcançava. O e-mail vira
    #    um placeholder único (não nulo) porque a coluna é identidade de login e
    #    tem índice único parcial (`uq_users_email_active`, migration 075) —
    #    dois titulares anonimizados não podem colidir.
    usuarios_portal = (await db.execute(
        select(User).where(User.client_id == client_id)
    )).scalars().all()
    for u in usuarios_portal:
        u.is_active = False
        u.full_name = _MARCADOR
        u.email = f"anonimizado+{u.id}@invalido.local"
        u.phone = None

    # Log de auditoria SEM PII — só o fato, quem autorizou, e se foi forçado
    # apesar de bloqueios (rastreabilidade da decisão).
    detalhes = f"Anonimização LGPD art.17. Motivo: {motivo or 'não informado'}."
    if bloqueios:
        detalhes += f" FORÇADO apesar de {len(bloqueios)} bloqueio(s) ativo(s)."
    await criar_audit_log(
        db, executor_id, executor_role, "ANONIMIZAR_LGPD", "clients", client_id,
        detalhes=detalhes,
    )
    await db.commit()

    return {
        "client_id": client_id,
        "anonimizado_em": agora.isoformat(),
        "portal_desativado_para": [u.id for u in usuarios_portal],
        "bloqueios_ignorados": bloqueios if bloqueios else None,
    }
