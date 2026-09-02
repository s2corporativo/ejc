"""Relatório financeiro consolidado do cliente — GET /clients/{client_id}/relatorio-financeiro

Degradação POR SEÇÃO (Onda 1 da refatoração): honorários e despesas são
agregações independentes. Uma que falhe devolve lista vazia, entra em
`secoes_indisponiveis` e vai para o log/Sentry — o relatório ABRE com o resto,
em vez de responder 500 e deixar a tela em branco (achado da auditoria).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.client_ownership import cliente_id_visivel
from app.core.database import get_db
from app.core.degradacao import ColetorDeSecoes
from app.core.security import get_current_user
from app.models.client import Client
from app.models.user import User
from app.services.pii_crypto import mascarar_documento

# secretaria incluída pelo achado 8 da auditoria: tem visão total do CRM
# (client_ownership.visao_total_clientes) mas caía neste gate de topo e
# recebia 403 antes de chegar ao gate de titularidade — a correção de
# titularidade sozinha (abaixo) não bastava, o teto do endpoint também
# precisava mudar (achado do Codex: o teste anterior chamava o handler direto
# e não pegou que _FIN_ADV ainda barrava secretaria na rota real).
_FIN_ADV = {"superadmin", "admin", "socio", "financeiro", "advogado", "secretaria"}


def _req_fin_adv(cu: User = Depends(get_current_user)) -> User:
    # Relatório financeiro contém dados pessoais e financeiros: acesso segue a
    # matriz existente, mas o documento identificador trafega apenas mascarado.
    if cu.role.value not in _FIN_ADV:
        raise HTTPException(status_code=403, detail="Acesso restrito a gestão/financeiro/advogado")
    return cu


async def _cliente_visivel(db: AsyncSession, cu: User, client_id: str) -> bool:
    """financeiro vê o relatório financeiro de QUALQUER cliente — é a razão de
    _FIN_ADV incluir o papel (achado da auditoria: a autorização de topo
    permitia financeiro chamar o endpoint, mas o gate de titularidade nunca
    deixava passar — financeiro nunca é responsável pelo cliente nem advogado
    de caso; a permissão era morta na prática). Regra própria deste relatório
    (não faz parte do gate genérico), então soma-se ao gate canônico
    (client_ownership.cliente_id_visivel: gestão/secretaria veem tudo; demais
    precisam ser responsáveis pelo cliente OU atuar em caso dele)."""
    if cu.role.value == "financeiro":
        return True
    return await cliente_id_visivel(db, cu, client_id)


async def _carregar_honorarios(db: AsyncSession, client_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT f.id, f.tipo, f.status, f.descricao, f.valor, f.percentual_exito,
               f.data_vencimento, f.data_pagamento, f.case_id,
               c.titulo AS caso_titulo, c.numero_interno
        FROM fees f
        LEFT JOIN cases c ON c.id = f.case_id
        WHERE f.client_id = :cid AND f.deleted_at IS NULL
        ORDER BY f.created_at DESC
    """), {"cid": client_id})).mappings().all()
    fees = [dict(f) for f in rows]
    for f in fees:
        f["valor"] = float(f["valor"] or 0)
        if f.get("percentual_exito") is not None:
            f["percentual_exito"] = float(f["percentual_exito"])
    return fees


async def _carregar_despesas(db: AsyncSession, client_id: str) -> list[dict]:
    rows = (await db.execute(text("""
        SELECT cc.id, cc.tipo, cc.categoria, cc.valor, cc.descricao,
               cc.data_lancamento, cc.pago, cc.case_id, c.titulo AS caso_titulo
        FROM centro_custos cc
        JOIN cases c ON c.id = cc.case_id
        WHERE c.client_id = :cid AND cc.deleted_at IS NULL
        ORDER BY cc.data_lancamento DESC
    """), {"cid": client_id})).mappings().all()
    despesas = [dict(d) for d in rows]
    for d in despesas:
        d["valor"] = float(d["valor"] or 0)
    return despesas


router = APIRouter(prefix="/clients/{client_id}/relatorio-financeiro", tags=["Relatório Financeiro Cliente"], dependencies=[Depends(_req_fin_adv)])


@router.get("")
async def relatorio_financeiro_cliente(
    client_id: str,
    db: AsyncSession = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    # Cutover C6/LGPD: cpf/cnpj não existem mais em texto puro (migration 112).
    # Carrega via ORM para usar documento_plain (decifra resiliente) e aplica
    # minimização antes da resposta: o frontend financeiro não necessita do
    # identificador completo e perfis como financeiro/secretaria podem acessar
    # este relatório. O valor integral fica nas rotas LGPD/dossiê com gate próprio.
    cli_obj = (await db.execute(
        select(Client).where(Client.id == client_id, Client.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not cli_obj:
        raise HTTPException(404, "Cliente não encontrado")
    if not await _cliente_visivel(db, cu, client_id):
        # 404 (não 403) para não confirmar a existência de cliente alheio.
        raise HTTPException(404, "Cliente não encontrado")
    cli = {
        "id": cli_obj.id, "nome": cli_obj.nome_exibicao,
        "email": cli_obj.email, "telefone": cli_obj.telefone,
        "whatsapp": cli_obj.whatsapp,
        "cpf_cnpj": mascarar_documento(cli_obj.documento_plain),
    }

    secoes = ColetorDeSecoes("relatorio_financeiro_cliente", db)
    fees = await secoes.tentar("honorarios", _carregar_honorarios(db, client_id), padrao=[])

    def soma(pred):
        return round(sum(f["valor"] for f in fees if pred(f)), 2)

    total          = soma(lambda f: True)
    recebido       = soma(lambda f: f["status"] == "pago")
    pendente       = soma(lambda f: f["status"] not in ("pago", "cancelado"))
    atrasado       = soma(lambda f: f["status"] == "atrasado")
    contratual     = soma(lambda f: f["tipo"] in ("fixo", "misto", "por_hora"))
    exito          = soma(lambda f: f["tipo"] == "exito")
    custas         = soma(lambda f: f["tipo"] == "custas_despesas")
    exito_recebido = soma(lambda f: f["tipo"] == "exito" and f["status"] == "pago")

    # Despesas vinculadas aos casos do cliente (centro de custos)
    despesas = await secoes.tentar("despesas", _carregar_despesas(db, client_id), padrao=[])
    total_despesas    = round(sum(d["valor"] for d in despesas), 2)
    despesas_pagas    = round(sum(d["valor"] for d in despesas if d["pago"]), 2)
    reembolsos        = round(sum(d["valor"] for d in despesas if (d.get("tipo") or "") == "reembolsavel"), 2)

    # Extrato unificado (honorários pagos + despesas) ordenado por data
    extrato = []
    for f in fees:
        if f["status"] == "pago" and f.get("data_pagamento"):
            extrato.append({
                "data": str(f["data_pagamento"]), "tipo": "credito",
                "categoria": f["tipo"], "descricao": f["descricao"] or "Honorário",
                "valor": f["valor"], "caso": f.get("caso_titulo"),
            })
    for d in despesas:
        if d["pago"] and d.get("data_lancamento"):
            extrato.append({
                "data": str(d["data_lancamento"]), "tipo": "debito",
                "categoria": d.get("categoria") or "despesa",
                "descricao": d["descricao"] or "Despesa", "valor": d["valor"],
                "caso": d.get("caso_titulo"),
            })
    extrato.sort(key=lambda x: x["data"], reverse=True)

    # Contratos (casos com honorário contratual)
    contratos = []
    seen_casos: set = set()
    for f in fees:
        if f["case_id"] and f["case_id"] not in seen_casos and f["tipo"] in ("fixo", "misto", "por_hora"):
            seen_casos.add(f["case_id"])
            contratos.append({
                "case_id": f["case_id"], "caso": f.get("caso_titulo"),
                "numero_interno": f.get("numero_interno"),
                "valor": soma(lambda x, cid=f["case_id"]: x["case_id"] == cid and x["tipo"] in ("fixo", "misto", "por_hora")),
            })

    return {
        "cliente": cli,
        "resumo": {
            "total": total, "recebido": recebido, "pendente": pendente, "atrasado": atrasado,
            "honorarios_contratuais": contratual, "honorarios_exito": exito,
            "exito_recebido": exito_recebido, "custas_despesas": custas,
            "total_despesas": total_despesas, "despesas_pagas": despesas_pagas,
            "reembolsos": reembolsos,
            "resultado_liquido": round(recebido - despesas_pagas, 2),
            "taxa_recebimento": round(recebido / total * 100, 1) if total else 0,
        },
        "contratos": contratos,
        "honorarios": fees,
        "despesas": despesas,
        "extrato": extrato,
        **secoes.rodape(),
    }