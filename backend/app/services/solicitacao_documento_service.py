# ── app/services/solicitacao_documento_service.py ────────────────────────────
# Lógica compartilhada da Solicitação de Documentos ao cliente (migration 084):
# funções PURAS (status agregado + templates determinísticos de e-mail) usadas
# pelos routers solicitacoes_documentos (advogado) e portal_documentos (Portal
# do Cliente). Canais: e-mail + sino APENAS (WhatsApp fora de escopo).
from __future__ import annotations

import html

ASSINATURA_AUTOMATICA = (
    "De Paula Teixeira Advogados — mensagem automática, "
    "não responda este e-mail."
)

# Limites do contrato do endpoint de criação.
MIN_ITENS = 1
MAX_ITENS = 30


def recalcular_status(status_itens: list[str]) -> str:
    """Status agregado da solicitação a partir dos status dos itens.

    Função pura: 'atendida' se TODOS enviados; 'parcial' se ao menos um
    enviado; senão 'pendente'. Lista vazia (não deveria ocorrer — criação
    exige MIN_ITENS) degrada para 'pendente'.
    """
    if not status_itens:
        return "pendente"
    enviados = sum(1 for s in status_itens if s == "enviado")
    if enviados == len(status_itens):
        return "atendida"
    if enviados > 0:
        return "parcial"
    return "pendente"


def montar_email_solicitacao(
    nome_cliente: str,
    itens: list[dict],
    mensagem: str | None = None,
) -> tuple[str, str]:
    """Template DETERMINÍSTICO (sem IA) do e-mail de solicitação de documentos.

    Retorna (assunto, corpo_html). Tom sóbrio de escritório: lista dos
    documentos pedidos (nome + descrição opcional), mensagem livre do advogado
    (quando houver) e instrução de envio pelo Portal do Cliente. Aviso de
    comunicação automática ao final.
    """
    assunto = "[De Paula Teixeira Advogados] Solicitação de documentos"
    # nome/descricao/mensagem são texto livre do advogado: escape obrigatório
    # antes de compor o corpo HTML enviado em nome do escritório.
    linhas = "".join(
        "<li><b>{nome}</b>{desc}</li>".format(
            nome=html.escape((i.get("nome") or "").strip()),
            desc=(f" — {html.escape(i['descricao'].strip())}"
                  if (i.get("descricao") or "").strip() else ""),
        )
        for i in itens
    )
    bloco_mensagem = (
        f"<p>{html.escape(mensagem.strip())}</p>"
        if (mensagem or "").strip() else ""
    )
    corpo = (
        f"<p>Prezado(a) {html.escape(nome_cliente or 'cliente')},</p>"
        "<p>Para o andamento do seu caso, solicitamos a gentileza de nos "
        "enviar os seguintes documentos:</p>"
        f"<ul>{linhas}</ul>"
        f"{bloco_mensagem}"
        "<p>O envio deve ser feito pelo <b>Portal do Cliente</b>, na seção "
        "Documentos, onde os itens solicitados estão listados. Em caso de "
        "dúvidas, entre em contato com o escritório.</p>"
        "<p>Atenciosamente,</p>"
        f"<p>{ASSINATURA_AUTOMATICA}</p>"
    )
    return assunto, corpo
