# ── app/services/geracao_documental.py ───────────────────────────────────────
# Geração Documental (P0.3) — kit inicial REAL e DETERMINÍSTICO (sem LLM).
#
# A partir de um caso + cliente já carregados, gera por PREENCHIMENTO DE
# TEMPLATE (nenhuma cláusula redigida por IA):
#   1. Procuração ad judicia (reutiliza documental._procuracao + registro
#      Procuracao). Poderes especiais do CPC art. 105 SÓ entram quando
#      explicitamente marcados (tipo_poderes="ad_judicia_et_extra"/"especiais").
#   2. Contrato de honorários (reutiliza documental._contrato_honorarios) com
#      valor SUGERIDO puxado da TabelaOABHonorario vigente pela área do caso.
#      Sem item aplicável → referência fica explicitamente "a definir".
#      REGRA ABSOLUTA (CLAUDE.md/modelo): NUNCA inventar valor/item/vigência.
#   3. Checklist documental inicial por área (template fixo por ramo).
#
# Persistência no padrão da casa (documental.gerar_documentos_iniciais):
# LegalDoc SEMPRE em status=rascunho com human_reviewed=False; ai_generated=True
# aciona o gate HITL existente (legal_doc.py: nunca aprova sem revisão humana).
# Auditoria via criar_audit_log é obrigatória.
from __future__ import annotations

from datetime import date
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select

from app.models.audit_log import criar_audit_log
from app.models.case import Case
from app.models.client import Client
from app.models.legal_doc import LegalDoc, PecaStatus, PecaTipo
from app.models.redesign import TabelaOABHonorario
from app.models.user import User
from app.services.document_format import padronizar_documento_juridico
from app.services.documental import _contrato_honorarios, _procuracao

AVISO_RASCUNHO = (
    "Documentos gerados automaticamente por preenchimento de template "
    "(sem redacao por IA). Status: RASCUNHO — sujeitos a revisao e "
    "aprovacao do advogado responsavel antes de qualquer uso."
)

AVISO_SEM_ITEM_OAB = (
    "Valor de referencia A DEFINIR: nenhum item aplicavel da Tabela OAB/MG "
    "vigente foi encontrado para a area do caso. Nunca inventamos valores — "
    "consulte a tabela oficial OAB/MG ou cadastre o item (fonte obrigatoria)."
)

# ── Checklist documental inicial por área ─────────────────────────────────────
# Documentos usuais de instrução (template fixo — não são valores OAB).
_CHECKLIST_BASE = [
    "Documento de identidade (RG ou CNH)",
    "CPF (ou CNPJ e contrato social, se pessoa juridica)",
    "Comprovante de residencia/endereco atualizado",
    "Procuracao assinada",
    "Contrato de honorarios assinado",
]

_CHECKLIST_POR_AREA: dict[str, list[str]] = {
    "trabalhista": [
        "CTPS (fisica ou digital)",
        "Contrato de trabalho e aditivos",
        "Contracheques/holerites do periodo",
        "Termo de rescisao (TRCT) e comprovantes de FGTS",
    ],
    "familia": [
        "Certidao de casamento ou de nascimento",
        "Certidoes de nascimento dos filhos",
        "Comprovantes de renda das partes",
        "Relacao e documentos dos bens do casal",
    ],
    "consumidor": [
        "Contrato/nota fiscal ou comprovante da compra",
        "Protocolos de atendimento junto ao fornecedor",
        "Comunicacoes trocadas (e-mails, mensagens)",
        "Comprovantes do dano (faturas, extratos, laudos)",
    ],
    "civil": [
        "Contrato ou instrumento da relacao juridica",
        "Comprovantes de pagamento/recebimento",
        "Comunicacoes trocadas entre as partes",
    ],
    "previdenciario": [
        "Extrato CNIS",
        "Carta de indeferimento/decisao do INSS",
        "Laudos e atestados medicos",
        "Comprovantes de contribuicao/atividade",
    ],
    "criminal": [
        "Boletim de ocorrencia",
        "Copia do inquerito/processo (se houver)",
        "Rol e contatos de testemunhas",
    ],
    "tributario": [
        "Auto de infracao ou certidao de divida ativa",
        "Comprovantes de recolhimento do tributo",
        "Contrato social e alteracoes (se PJ)",
    ],
    "empresarial": [
        "Contrato social e alteracoes",
        "Contratos objeto da demanda",
        "Demonstracoes financeiras/documentos contabeis",
    ],
    "ambiental": [
        "Auto de infracao/notificacao do orgao ambiental",
        "Licencas, outorgas e certificados",
        "CAR e documentacao do imovel",
    ],
    "administrativo": [
        "Copia integral do processo administrativo",
        "Ato administrativo impugnado",
        "Notificacoes e intimacoes recebidas",
    ],
    "imobiliario": [
        "Matricula atualizada do imovel",
        "Contrato (compra e venda/locacao)",
        "Comprovantes de pagamento (IPTU, condominio, aluguel)",
    ],
    "sucessoes": [
        "Certidao de obito",
        "Documentos pessoais do falecido e herdeiros",
        "Relacao e documentos dos bens do espolio",
        "Testamento (se houver)",
    ],
}

# CaseArea → grafias usadas em tabela_oab_honorarios.area_juridica (o seed
# importado do PDF usa "civel"; o enum do caso usa "civil"). Só ALIASES de
# grafia — nunca mapear para área diferente.
_AREA_ALIASES: dict[str, list[str]] = {
    "civil": ["civil", "civel"],
}


def _area_str(case: Case) -> str:
    a = getattr(case, "area", None)
    return getattr(a, "value", None) or str(a or "")


def _aliases_area(area: str) -> list[str]:
    return _AREA_ALIASES.get((area or "").strip().lower(), [area])


async def _itens_oab_vigentes(db, area: str, hoje: date, limite: int = 5):
    """Itens VIGENTES da tabela OAB/MG para a área (ativo e vigência aberta ou
    não vencida). Sem match → lista vazia; NUNCA inventa item/valor."""
    aliases = [a for a in _aliases_area(area) if a]
    if not aliases:
        return []
    q = (
        select(TabelaOABHonorario)
        .where(
            TabelaOABHonorario.ativo.is_(True),
            or_(*[TabelaOABHonorario.area_juridica.ilike(f"%{a}%") for a in aliases]),
            or_(TabelaOABHonorario.vigencia_fim.is_(None),
                TabelaOABHonorario.vigencia_fim >= hoje),
            # Vigência futura (tabela do ano seguinte cadastrada antecipadamente)
            # NÃO é referência válida hoje.
            or_(TabelaOABHonorario.vigencia_inicio.is_(None),
                TabelaOABHonorario.vigencia_inicio <= hoje),
        )
        .order_by(TabelaOABHonorario.vigencia_inicio.desc().nullslast(),
                  TabelaOABHonorario.item_codigo)
        .limit(limite)
    )
    return (await db.execute(q)).scalars().all()


def _item_dict(i: TabelaOABHonorario) -> dict:
    return {
        "item_codigo": i.item_codigo,
        "descricao": i.descricao,
        "valor_minimo": float(i.valor_minimo) if i.valor_minimo is not None else None,
        "percentual": float(i.percentual) if i.percentual is not None else None,
        "unidade": i.unidade,
        "vigencia_inicio": i.vigencia_inicio.isoformat() if i.vigencia_inicio else None,
        "vigencia_fim": i.vigencia_fim.isoformat() if i.vigencia_fim else None,
        "fonte": i.fonte,
    }


def _referencia_oab_txt(item: TabelaOABHonorario) -> str:
    """Texto de referência VERBATIM do item da tabela (sugestão não vinculante)."""
    partes = []
    if item.valor_minimo is not None:
        partes.append(f"minimo R$ {float(item.valor_minimo):,.2f}")
    if item.percentual is not None:
        partes.append(f"{float(item.percentual):g}%")
    valores = " + ".join(partes) if partes else "ver tabela"
    return (
        f"sugestao nao vinculante — item {item.item_codigo} "
        f"({item.descricao}): {valores}; fonte: {item.fonte}"
    )


def _checklist_txt(case: Case, cli: Client, area: str) -> str:
    itens = _CHECKLIST_BASE + _CHECKLIST_POR_AREA.get((area or "").strip().lower(), [])
    linhas = "\n".join(f"[ ] {i}" for i in itens)
    texto = (
        "CHECKLIST DOCUMENTAL INICIAL\n\n"
        f"Caso: {case.titulo}\nCliente: {cli.razao_social or cli.nome}\n"
        f"Area: {area or '-'}\n\n"
        f"{linhas}\n\n"
        "Checklist de partida gerado automaticamente por area do caso. "
        "O advogado responsavel deve adequar os itens ao caso concreto."
    )
    return padronizar_documento_juridico(texto)


def _role_str(cu: User) -> str:
    r = getattr(cu, "role", None)
    return r.value if hasattr(r, "value") else str(r)


async def gerar_kit_inicial(
    db,
    case: Case,
    cli: Client,
    cu: User,
    *,
    tipo_poderes: str = "ad_judicia",
    permite_substabelecimento: bool = True,
    poderes_especiais: str | None = None,
) -> dict:
    """Gera o kit documental inicial (procuração + contrato + checklist).

    Determinístico: só preenche templates com dados do caso/cliente/tabela OAB.
    Defaults CONSERVADORES: tipo_poderes="ad_judicia" — os poderes especiais do
    art. 105 do CPC só entram quando o chamador marca explicitamente
    "ad_judicia_et_extra" (ou "especiais" com o texto dos poderes).
    Tudo nasce RASCUNHO (revisão humana obrigatória) e é auditado.
    O commit é feito aqui (transação única do kit).
    """
    hoje = date.today()
    adv = getattr(cu, "full_name", None) or "[advogado responsavel]"
    area = _area_str(case)
    papel = _role_str(cu)

    # ── 1. Procuração — SÓ a minuta (LegalDoc rascunho). O registro formal
    # `Procuracao` NÃO é criado aqui: ele satisfaria o item bloqueante
    # "procuração vigente" dos checklists (motor_peca/conversão) sem qualquer
    # ato de outorga do cliente. A emissão do registro continua exclusiva do
    # fluxo próprio (routers/procuracoes.py), após a assinatura.
    minuta_procuracao = _procuracao(
        case, cli, adv,
        tipo_poderes=tipo_poderes,
        permite_substabelecimento=permite_substabelecimento,
        poderes_especiais=poderes_especiais,
    )

    # ── 2. Contrato de honorários com referência OAB vigente (ou "a definir") ─
    itens = await _itens_oab_vigentes(db, area, hoje)
    if itens:
        referencia = _referencia_oab_txt(itens[0])
        valor_sugerido = {
            "origem": "tabela_oab_estruturada",
            "sugerido": _item_dict(itens[0]),
            "itens_referencia": [_item_dict(i) for i in itens],
            "aviso": "Referencia da tabela OAB/MG — nao vinculante; o advogado define o valor final.",
        }
    else:
        referencia = ("valor de referencia A DEFINIR — sem item aplicavel na "
                      "Tabela OAB/MG vigente para a area do caso")
        valor_sugerido = {"origem": None, "sugerido": None,
                          "itens_referencia": [], "aviso": AVISO_SEM_ITEM_OAB}
    minuta_contrato = _contrato_honorarios(case, cli, adv, area, referencia_oab=referencia)

    # ── 3. Checklist documental inicial por área ─────────────────────────────
    texto_checklist = _checklist_txt(case, cli, area)

    # ── Persistência (padrão gerar_documentos_iniciais): sempre RASCUNHO. ────
    # ai_generated=True marca a origem automática e aciona o gate HITL do
    # LegalDoc (nunca aprova sem human_reviewed=True) — geração é por template,
    # sem redação por LLM.
    docs = [
        ("Procuracao - " + case.titulo, PecaTipo.procuracao, minuta_procuracao),
        ("Contrato de Honorarios - " + case.titulo, PecaTipo.contrato, minuta_contrato),
        ("Checklist Documental Inicial - " + case.titulo, PecaTipo.outro, texto_checklist),
    ]
    criados: list[LegalDoc] = []
    for titulo, tipo, conteudo in docs:
        d = LegalDoc(
            id=str(uuid4()),
            titulo=padronizar_documento_juridico(titulo)[:200],
            tipo_peca=tipo,
            conteudo=conteudo,
            status=PecaStatus.rascunho,
            area=area or None,
            ai_generated=True,
            human_reviewed=False,
            case_id=case.id,
            created_by=cu.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(d)
        criados.append(d)

    # ── Auditoria obrigatória ────────────────────────────────────────────────
    await criar_audit_log(
        db, cu.id, papel, "KIT_DOCUMENTAL", "cases", case.id,
        detalhes=(f"Kit inicial gerado (rascunhos, tipo_poderes={tipo_poderes}): "
                  + ", ".join(d.id for d in criados)),
        dados_depois={
            "legal_doc_ids": [d.id for d in criados],
            "oab_item_aplicado": valor_sugerido["sugerido"] is not None,
        },
    )
    await db.commit()

    doc_proc, doc_contrato, doc_check = criados
    return {
        "case_id": case.id,
        "status": PecaStatus.rascunho.value,
        "aviso": AVISO_RASCUNHO,
        "procuracao": {
            "legal_doc_id": doc_proc.id,
            "titulo": doc_proc.titulo,
            "tipo_poderes": tipo_poderes,
            "permite_substabelecimento": permite_substabelecimento,
            "conteudo": doc_proc.conteudo,
            "aviso": ("Minuta pendente de assinatura — o registro formal de "
                      "procuração é emitido no módulo Procurações após a outorga."),
        },
        "contrato": {
            "legal_doc_id": doc_contrato.id,
            "titulo": doc_contrato.titulo,
            "valor_sugerido": valor_sugerido,
            "conteudo": doc_contrato.conteudo,
        },
        "checklist": {
            "legal_doc_id": doc_check.id,
            "titulo": doc_check.titulo,
            "conteudo": doc_check.conteudo,
        },
    }


class GeracaoDocumental:
    """Compatibilidade com o nome público antigo do módulo (stub v4.0)."""
    gerar_kit_inicial = staticmethod(gerar_kit_inicial)


gerador_docs = GeracaoDocumental()
