# ── app/services/anexos_service.py ───────────────────────────────────────────
# Gerador de "Documento Único de Anexos" — capa + índice + folhas de separação
# ("DOC. 0X") padronizadas, seguido da mesclagem dos anexos reais do processo.
#
# Reproduz o padrão de peça do escritório: banner institucional, número do
# documento em destaque e uma LEGENDA que sintetiza a relevância probatória de
# cada peça juntada. A legenda é redigida pela IA via ai_gateway, com o mesmo
# contrato de garantia dos demais fluxos:
#   1. Sanitização LGPD do texto do documento antes de sair para o provedor.
#   2. Base anti-alucinação (task de prosa → legal_base) + instrução explícita
#      de não inventar conteúdo.
#   3. AILog gravado em toda chamada (HITL rastreável).
#   4. Toda saída é RASCUNHO — revisão do advogado obrigatória.
#
# A montagem visual (capa/índice/separadores) é DETERMINÍSTICA (HTML→PDF via
# weasyprint); a IA só escreve as legendas. Anexos em PDF são mesclados 1:1;
# imagens são embutidas em página própria; demais formatos ganham apenas a folha
# de separação (o arquivo original segue no GED).
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import asyncio
import base64
import html as html_lib
import io
import logging
import os
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ai_log import AITipoUso
from app.models.case import Case
from app.models.client import Client
from app.models.document import Document
from app.services.ai_gateway import chat as gw_chat
from app.services.ai_guard import registrar_ai_log
from app.services.ai_service import buscar_contexto_rag, _escopo_cliente_do_caso
from app.services.citation_check import verificar_citacoes
from app.services.document_format import padronizar_documento_juridico
from app.services.sanitizer import sanitizar_pii
from app.services import visual_law_theme as vlt

logger = logging.getLogger("ejc.anexos")
settings = get_settings()

_LEGENDA_MAX = 240   # caracteres máximos de uma legenda de separador
_OCR_MAX = 1600      # texto do documento enviado à IA (após sanitização)

_MIME_PDF = {"application/pdf", "application/x-pdf"}
_MIME_IMG = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}


# ── Contexto e itens ──────────────────────────────────────────────────────────

@dataclass
class ContextoAnexos:
    titulo_acao: str
    partes: str
    referencia: str          # subtítulo do banner (ex.: "Reserva 46190319300")
    rodape: str              # ex.: "Juizado Especial Cível da Comarca de Betim/MG"


@dataclass
class ItemAnexo:
    ordem: int
    titulo: str              # rótulo curto (linha do índice)
    legenda: str = ""        # síntese probatória (subtítulo do separador)
    document_id: str | None = None
    obrigatorio: bool = False  # se True e não incorporável → aborta o pacote
    _filepath: str | None = field(default=None, repr=False)
    _mimetype: str | None = field(default=None, repr=False)
    _contexto: str = field(default="", repr=False)   # trecho sanitizado p/ as razões


class DocumentoUnicoIncompletoError(RuntimeError):
    """O "documento único" não pôde ser montado íntegro (anexo corrompido ou item
    obrigatório não incorporável). Subclasse de RuntimeError de propósito: os
    chamadores que já tratam RuntimeError (legal_docs) degradam para 503; o
    router de anexos trata explicitamente para devolver 409 + manifesto."""

    def __init__(self, message: str, manifesto: list | None = None):
        super().__init__(message)
        self.manifesto = manifesto or []


# ── Contexto do caso ──────────────────────────────────────────────────────────

async def montar_contexto(db: AsyncSession, case: Case, referencia: str | None) -> ContextoAnexos:
    """Deriva os dados do cabeçalho institucional a partir do caso/cliente."""
    cliente = None
    if case.client_id:
        cliente = (await db.execute(
            select(Client).where(Client.id == case.client_id)
        )).scalar_one_or_none()

    nome_cli = cliente.nome_exibicao if cliente else "Cliente"
    parte_contraria = case.parte_contraria or "Parte contrária"
    partes = f"{nome_cli} vs. {parte_contraria}"

    comarca = case.comarca or "—"
    vara = case.vara or "Juízo competente"
    rodape = f"{vara} da Comarca de {comarca}"

    ref = referencia or case.numero_processo or case.numero_interno or ""

    return ContextoAnexos(
        titulo_acao=(case.titulo or "Documento de anexos").upper(),
        partes=partes,
        referencia=ref,
        rodape=rodape,
    )


# ── Legenda por IA (síntese probatória) ───────────────────────────────────────

_SYSTEM_LEGENDA = (
    "Você redige a LEGENDA de um documento juntado a uma petição, no padrão de um "
    "índice de anexos forense. Escreva UMA única linha (no máximo 35 palavras), sem "
    "markdown, sintetizando objetivamente o que o documento é e o que ele comprova. "
    "Baseie-se SOMENTE no conteúdo fornecido — não invente valores, datas, números "
    "de protocolo, nomes ou fatos ausentes do texto. Se o conteúdo for insuficiente, "
    "descreva apenas o tipo do documento (ex.: 'Comprovante de pagamento', "
    "'Reclamação registrada no Consumidor.gov'). Não use aspas nem ponto final."
)


def _limpar_legenda(texto: str) -> str:
    linha = (texto or "").strip().splitlines()[0].strip() if texto else ""
    linha = linha.strip().strip('"').strip("«»").rstrip(".").strip()
    # remove prefixos de "raciocínio" que alguns modelos vazam
    if linha.lower().startswith(("legenda:", "resposta:", "síntese:")):
        linha = linha.split(":", 1)[1].strip()
    if len(linha) > _LEGENDA_MAX:
        linha = linha[: _LEGENDA_MAX - 1].rstrip() + "…"
    return linha


async def gerar_legenda_ia(
    db: AsyncSession,
    *,
    user_id: str,
    case_id: str | None,
    titulo: str,
    tipo: str | None,
    ocr_text: str | None,
) -> str:
    """
    Redige a legenda de um documento via ai_gateway (task de prosa, com base
    anti-alucinação) e grava AILog. Sanitiza o texto do documento antes de sair
    para o provedor. Em qualquer falha, devolve "" (o chamador usa o rótulo).
    """
    base_texto = (ocr_text or "").strip()
    if not base_texto:
        return ""

    texto_limpo, houve_pii = sanitizar_pii(base_texto[:_OCR_MAX])
    user = (
        f"[TÍTULO DO DOCUMENTO]\n{titulo}\n\n"
        f"[TIPO]\n{tipo or 'não informado'}\n\n"
        f"[CONTEÚDO EXTRAÍDO (pode estar mascarado por LGPD)]\n{texto_limpo}"
    )
    try:
        resp = await gw_chat(
            messages=[
                {"role": "system", "content": _SYSTEM_LEGENDA},
                {"role": "user", "content": user},
            ],
            task_type="chat_rapido",   # prosa → recebe base anti-alucinação
            temperature=0.2,
            max_tokens=160,
        )
    except Exception as exc:  # provedor indisponível não pode derrubar o PDF inteiro
        logger.warning("Legenda IA indisponível para '%s': %s", titulo, exc)
        return ""

    legenda = _limpar_legenda(resp.texto)

    try:
        await registrar_ai_log(
            db,
            user_id=user_id,
            tipo_uso=AITipoUso.resumo_documento,
            case_id=case_id,
            prompt_sanitizado=user,
            pii_removida=houve_pii,
            resposta=legenda,
            modelo=resp.modelo,
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
        )
    except Exception as exc:
        # AILog é obrigatório: se não conseguimos auditar, não usamos a legenda IA.
        logger.error("Falha ao gravar AILog da legenda '%s': %s", titulo, exc)
        return ""

    return legenda


# ── HTML: capa, índice e folhas de separação ──────────────────────────────────

def _css_base() -> str:
    # Tema central Visual Law (dourado + logo De Paula Teixeira).
    return vlt.css_tema()


def _doc(css_extra: str, corpo: str) -> str:
    return (
        '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8">'
        f"<style>{_css_base()}{css_extra}</style></head><body>{corpo}</body></html>"
    )


def _esc(s: str) -> str:
    return html_lib.escape(s or "")


def _banner_html(ctx: ContextoAnexos) -> str:
    sub = ctx.partes
    if ctx.referencia:
        sub += f" — {ctx.referencia}"
    return vlt.render_banner(ctx.titulo_acao, sub)


def cover_html(ctx: ContextoAnexos, itens: list[ItemAnexo]) -> str:
    """Capa geral: banner + 'ANEXOS' + índice de documentos."""
    linhas = "".join(
        '<div class="indice-linha">'
        f'<span class="indice-doc">Doc. {it.ordem:02d}</span>'
        f'<span class="indice-desc">&mdash; {_esc(it.titulo)}</span>'
        "</div>"
        for it in itens
    ) or '<div class="indice-linha"><span class="indice-desc">Nenhum documento.</span></div>'

    corpo = (
        '<div class="sheet">'
        f"{_banner_html(ctx)}"
        f"{vlt.render_capa('ANEXOS', tamanho_pt=40)}"
        f'<div class="indice-titulo">Índice de Documentos</div>'
        f'<div class="indice">{linhas}</div>'
        f"{vlt.render_rodape(ctx.rodape)}"
        "</div>"
    )
    return _doc("", corpo)


def separador_html(ctx: ContextoAnexos, item: ItemAnexo) -> str:
    """Folha de separação de um documento: banner + 'DOC. 0X' + título + legenda."""
    corpo = (
        '<div class="sheet">'
        f"{_banner_html(ctx)}"
        f"{vlt.render_capa(f'DOC. {item.ordem:02d}', item.titulo, item.legenda)}"
        f"{vlt.render_rodape(ctx.rodape)}"
        "</div>"
    )
    return _doc("", corpo)


def _imagem_html(ctx: ContextoAnexos, item: ItemAnexo, data_uri: str) -> str:
    corpo = (
        '<div class="sheet">'
        f'<img class="img-full" src="{data_uri}" alt="Doc. {item.ordem:02d}">'
        f"{vlt.render_rodape(f'Doc. {item.ordem:02d} — {ctx.rodape}')}"
        "</div>"
    )
    return _doc("", corpo)


# ── Renderização e mesclagem ──────────────────────────────────────────────────

def _render_pdf_sync(html: str) -> bytes:
    from weasyprint import HTML
    return HTML(string=html).write_pdf()


async def _render_pdf(html: str) -> bytes:
    return await asyncio.get_event_loop().run_in_executor(None, _render_pdf_sync, html)


def _caminho_anexo(item: ItemAnexo) -> str | None:
    if not item._filepath:
        return None
    full = os.path.join(settings.UPLOAD_DIR, item._filepath)
    return full if os.path.isfile(full) else None


def _data_uri(path: str, mimetype: str) -> str:
    raw = open(path, "rb").read()
    return f"data:{mimetype};base64," + base64.b64encode(raw).decode("ascii")


def _classificar_formato(item: ItemAnexo, caminho: str | None) -> str:
    """Classifica o anexo para o manifesto de completude:
    pdf | imagem (inlineáveis) · nao_inlineavel (docx/xlsx/Drive) · sem_arquivo."""
    mime = (item._mimetype or "").lower()
    ref = (caminho or item._filepath or "").lower()
    if mime in _MIME_PDF or ref.endswith(".pdf"):
        return "pdf"
    if mime in _MIME_IMG or ref.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        return "imagem"
    if not (item._filepath or item.document_id):
        return "sem_arquivo"
    return "nao_inlineavel"


async def _anexo_para_pdf(ctx: ContextoAnexos, item: ItemAnexo) -> bytes | None:
    """Converte o arquivo anexado em páginas PDF (PDF nativo ou imagem embutida).

    Retorna None quando NÃO há arquivo/formato inlineável (gap legítimo) OU
    quando o arquivo existe mas está corrompido — o chamador
    (montar_documento_unico_com_manifesto) distingue os dois casos e decide se
    aborta (fail-closed) ou apenas sinaliza no manifesto.
    """
    caminho = _caminho_anexo(item)
    if not caminho:
        return None
    mime = (item._mimetype or "").lower()
    if mime in _MIME_PDF or caminho.lower().endswith(".pdf"):
        try:
            return open(caminho, "rb").read()
        except OSError as exc:
            logger.warning("Anexo PDF ilegível (%s): %s", caminho, exc)
            return None
    if mime in _MIME_IMG or caminho.lower().endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
        try:
            uri = _data_uri(caminho, mime or "image/jpeg")
            return await _render_pdf(_imagem_html(ctx, item, uri))
        except Exception as exc:
            logger.warning("Falha ao embutir imagem (%s): %s", caminho, exc)
            return None
    # Formatos não inlineáveis (docx/xlsx/…): fica só a folha de separação.
    return None


def mesclar_pdfs(partes: list[bytes], *, fail_closed: bool = True) -> bytes:
    """Mescla PDFs (bytes) em um único documento.

    FAIL-CLOSED por padrão (DOC-077): se uma parte NÃO-vazia não puder ser
    incorporada, aborta com DocumentoUnicoIncompletoError em vez de omiti-la em
    silêncio — protocolar um "documento único" com página faltante é pior que
    falhar. Partes vazias/None (gaps intencionais) continuam sendo puladas.

    Pública de propósito: é a MESMA primitiva usada pelo Documento Único de
    Anexos e pelo "Documento Único de Impressão" (routers/legal_docs.py) —
    peça + anexos saem sempre pelo mesmo caminho de mesclagem (pypdf).
    """
    from pypdf import PdfWriter, PdfReader

    writer = PdfWriter()
    for p in partes:
        if not p:
            continue
        try:
            writer.append(PdfReader(io.BytesIO(p)))
        except Exception as exc:
            if fail_closed:
                raise DocumentoUnicoIncompletoError(
                    f"Parte PDF ilegível na mesclagem final ({exc}) — pacote "
                    "abortado para não gerar documento único incompleto."
                ) from exc
            logger.warning("Parte PDF ignorada na mesclagem: %s", exc)
    saida = io.BytesIO()
    writer.write(saida)
    return saida.getvalue()


# Alias privado preservado — chamadas internas/testes antigos continuam válidos.
_mesclar = mesclar_pdfs


async def montar_documento_unico_com_manifesto(
    ctx: ContextoAnexos, itens: list[ItemAnexo]
) -> tuple[bytes, list[dict]]:
    """
    Renderiza capa + índice e, para cada item, a folha de separação seguida do
    anexo real (quando existir e for inlineável). Devolve (PDF único, MANIFESTO
    de completude).

    O manifesto lista, por item, se foi `incorporado` e o `motivo` quando não.
    Contrato de integridade (DOC-077):
      - arquivo inlineável (PDF/imagem) que EXISTE mas falha na incorporação →
        FAIL-CLOSED: aborta com DocumentoUnicoIncompletoError (arquivo corrompido);
      - item marcado `obrigatorio` que não pôde ser incorporado → aborta;
      - formatos não inlineáveis (docx/xlsx/Drive) e arquivos ausentes no
        armazenamento → sinalizados no manifesto, nunca omitidos em silêncio.
    """
    partes: list[bytes] = [await _render_pdf(cover_html(ctx, itens))]
    manifesto: list[dict] = []
    for item in itens:
        partes.append(await _render_pdf(separador_html(ctx, item)))
        caminho = _caminho_anexo(item)
        formato = _classificar_formato(item, caminho)
        entrada = {
            "ordem": item.ordem,
            "titulo": item.titulo,
            "document_id": item.document_id,
            "formato": formato,
            "obrigatorio": bool(getattr(item, "obrigatorio", False)),
            "incorporado": False,
            "motivo": None,
        }
        if formato in ("pdf", "imagem") and caminho is not None:
            anexo = await _anexo_para_pdf(ctx, item)
            if not anexo:
                entrada["motivo"] = "arquivo corrompido ou ilegível — incorporação falhou"
                manifesto.append(entrada)
                raise DocumentoUnicoIncompletoError(
                    f"Doc. {item.ordem:02d} — '{item.titulo}': {entrada['motivo']}. "
                    "Pacote abortado para não protocolar documento incompleto.",
                    manifesto=manifesto,
                )
            partes.append(anexo)
            entrada["incorporado"] = True
        else:
            if formato in ("pdf", "imagem"):
                # referenciado mas ausente no armazenamento: NÃO é corrupção —
                # preserva o comportamento do documento único de impressão
                # (capa "DOC. NN" sem o anexo). Sinalizado, nunca omitido.
                entrada["motivo"] = "arquivo não localizado no armazenamento"
            elif formato == "sem_arquivo":
                entrada["motivo"] = "somente folha de separação (nenhum arquivo anexado)"
            else:
                entrada["motivo"] = "formato não incorporável ao PDF (segue no GED/Drive)"
            if entrada["obrigatorio"]:
                manifesto.append(entrada)
                raise DocumentoUnicoIncompletoError(
                    f"Doc. {item.ordem:02d} — '{item.titulo}': {entrada['motivo']}. "
                    "Item OBRIGATÓRIO não pôde ser incorporado — pacote abortado.",
                    manifesto=manifesto,
                )
        manifesto.append(entrada)
    pdf = await asyncio.get_event_loop().run_in_executor(None, _mesclar, partes)
    return pdf, manifesto


async def montar_documento_unico(ctx: ContextoAnexos, itens: list[ItemAnexo]) -> bytes:
    """Compat: devolve apenas o PDF único (fail-closed). Usado por legal_docs
    (Documento Único de Impressão). O manifesto é ignorado aqui."""
    pdf, _manifesto = await montar_documento_unico_com_manifesto(ctx, itens)
    return pdf


# ── Conversão do acervo probatório (Prova) em itens do documento único ────────

def itens_de_provas(provas_docs: list[tuple]) -> list[ItemAnexo]:
    """Converte pares (Prova, Document | None) — já ordenados por (ordem,
    created_at) e restritos ao caso pelo chamador — nos ItemAnexo do documento
    único, com ordem sequencial 1..N.

    Sem IA de propósito: título e fato_probando/descrição já foram curados pelo
    advogado no cadastro da prova (HITL na origem); a legenda apenas reaproveita
    esse texto, truncado no mesmo limite dos separadores.
    """
    itens: list[ItemAnexo] = []
    for i, (prova, doc) in enumerate(provas_docs, start=1):
        titulo = (prova.titulo or (doc.titulo if doc is not None else None) or f"Documento {i}").strip()
        legenda = (prova.fato_probando or prova.descricao or "").strip()
        if len(legenda) > _LEGENDA_MAX:
            legenda = legenda[: _LEGENDA_MAX - 1].rstrip() + "…"
        item = ItemAnexo(ordem=i, titulo=titulo, legenda=legenda, document_id=prova.document_id)
        if doc is not None:
            item._filepath = doc.filepath
            item._mimetype = doc.mimetype
        itens.append(item)
    return itens


# ── Resolução dos itens a partir do GED ───────────────────────────────────────

async def resolver_itens(
    db: AsyncSession,
    *,
    cu_id: str,
    case_id: str,
    itens_in: list[dict],
    com_ia: bool = True,
    cu=None,
) -> list[ItemAnexo]:
    """
    Constrói os ItemAnexo a partir da entrada do usuário. Cada entrada pode
    referenciar um documento do GED (document_id) e/ou trazer título/legenda
    manuais. Legenda manual tem prioridade; senão, tenta a IA sobre o ocr_text.

    Segurança:
      - só aceita documentos do PRÓPRIO caso (case_id já checado por ownership
        no router) — impede juntar peça de caso alheio (EOAB/LGPD);
      - COFRE de confidencialidade (DOC-076): quando `cu` é informado, documento
        restrito/confidencial/segredo_justiça só entra no pacote para socio+ —
        MESMO gate do download direto do GED (documents._pode_acessar_confidencial)
        e do Documento Único de Impressão (legal_docs). Caso contrário, 403 (o
        pacote nunca é montado silenciosamente sem o anexo restrito).
    """
    # Reuso do gate central do cofre (não duplica a regra de papel).
    from app.routers.documents import _pode_acessar_confidencial

    itens: list[ItemAnexo] = []
    for i, entrada in enumerate(itens_in, start=1):
        doc: Document | None = None
        doc_id = entrada.get("document_id")
        if doc_id:
            doc = (await db.execute(
                select(Document).where(
                    Document.id == doc_id,
                    Document.case_id == case_id,          # trava anti-IDOR
                    Document.deleted_at.is_(None),
                )
            )).scalar_one_or_none()
            if doc is None:
                from fastapi import HTTPException
                raise HTTPException(
                    404, f"Documento {doc_id} não encontrado neste caso."
                )
            if cu is not None:
                conf = getattr(doc.confidencialidade, "value", str(doc.confidencialidade or "normal"))
                if not _pode_acessar_confidencial(cu, conf):
                    from fastapi import HTTPException
                    raise HTTPException(
                        403,
                        f"Documento '{doc.titulo}' está sob confidencialidade "
                        f"({conf}) e exige perfil sócio ou superior para compor o "
                        "pacote de anexos.",
                    )

        titulo = (entrada.get("titulo") or (doc.titulo if doc else None) or f"Documento {i}").strip()
        legenda = (entrada.get("legenda") or "").strip()

        if not legenda and com_ia and doc is not None:
            legenda = await gerar_legenda_ia(
                db,
                user_id=cu_id,
                case_id=case_id,
                titulo=titulo,
                tipo=doc.tipo,
                ocr_text=doc.ocr_text,
            )

        item = ItemAnexo(
            ordem=i,
            titulo=titulo,
            legenda=legenda,
            document_id=doc_id,
            obrigatorio=bool(entrada.get("obrigatorio", False)),
        )
        if doc is not None:
            item._filepath = doc.filepath
            item._mimetype = doc.mimetype
            if doc.ocr_text:
                item._contexto = sanitizar_pii(doc.ocr_text[:900])[0]
        itens.append(item)
    return itens


# ── Razões / Fundamentação Jurídica (o texto argumentativo) ───────────────────
# Gera o raciocínio jurídico da manifestação — fato → direito → responsabilidade
# → dano → pedido — REFERENCIANDO os anexos pelo número (Doc. 0X), com grounding
# nos documentos + RAG, nível de inteligência máximo (raciocínio adversarial),
# verificação de citações e HITL. Mesmo contrato de garantia do gateway.

_SYSTEM_RAZOES = (
    "Você é advogado(a) sênior brasileiro(a). Redija AS RAZÕES / FUNDAMENTAÇÃO "
    "JURÍDICA de uma manifestação, em português jurídico formal e com raciocínio "
    "ADVERSARIAL: não apenas exponha — enfrente os argumentos da parte contrária, "
    "aponte o dispositivo que os afasta e conclua.\n\n"
    "ESTRUTURA OBRIGATÓRIA (use estes títulos):\n"
    "I — SÍNTESE DOS FATOS — objetiva; ao afirmar um fato comprovado, referencie o "
    "documento juntado pelo rótulo exato 'Doc. 0X'.\n"
    "II — DO DIREITO APLICÁVEL — fundamente cada tese no dispositivo legal pertinente.\n"
    "III — DA RESPONSABILIDADE — enquadre a conduta e enfrente eventual excludente.\n"
    "IV — DOS DANOS — material e moral, com nexo causal explícito.\n"
    "V — DOS PEDIDOS — decorrentes e coerentes com a fundamentação.\n\n"
    "REGRAS INVIOLÁVEIS (OAB / anti-alucinação):\n"
    "1. Cite APENAS lei, súmula ou julgado de que tenha certeza. Em caso de dúvida, "
    "escreva '(verificar)' ao lado — NUNCA invente número de artigo, súmula, "
    "acórdão ou processo.\n"
    "2. Refira-se aos documentos SOMENTE pelos rótulos 'Doc. 0X' fornecidos; não "
    "invente documentos nem o que eles contêm.\n"
    "3. Baseie os fatos apenas no contexto fornecido; lacuna probatória = '(a comprovar)'.\n"
    "4. NUNCA prometa resultado (vedação da OAB).\n"
    "5. Toda a saída é RASCUNHO — revisão do advogado responsável é obrigatória."
)

_AVISO_RAZOES = (
    "⚠️ RASCUNHO gerado por IA. As citações sinalizadas e os fatos '(a comprovar)' "
    "exigem conferência. Revisão e assinatura do advogado responsável são obrigatórias "
    "antes de qualquer uso (OAB)."
)


async def gerar_razoes_juridicas(
    db: AsyncSession,
    *,
    cu_id: str,
    case_id: str,
    ctx: ContextoAnexos,
    itens: list[ItemAnexo],
    objetivo: str | None = None,
    area: str = "Consumidor",
    nivel: str = "maximo",
) -> dict:
    """
    Redige as razões jurídicas do caso amarrando-as aos anexos (Doc. 0X).
    Retorna {texto, verificacao_citacoes, docs_referenciados, aviso}.
    """
    # Bloco de documentos numerados (rótulo + síntese/contexto sanitizado).
    linhas_docs = []
    for it in itens:
        detalhe = it.legenda or it._contexto or ""
        if it._contexto and it.legenda:
            detalhe = f"{it.legenda}. {it._contexto}"
        linhas_docs.append(f"Doc. {it.ordem:02d} — {it.titulo}: {detalhe[:600]}".rstrip())
    bloco_docs = "\n".join(linhas_docs) or "(sem documentos juntados)"

    # Grounding jurídico via RAG (legislação/súmulas), no escopo do cliente.
    scope_cli = await _escopo_cliente_do_caso(db, case_id)
    consulta = (objetivo or ctx.titulo_acao or area)[:300]
    fontes = await buscar_contexto_rag(db, consulta, limite=6, scope_client_id=scope_cli)
    rag_txt = ""
    if fontes:
        rag_txt = "\n".join(f"- {f['titulo']}: {f['conteudo'][:220]}" for f in fontes)

    user = (
        f"[AÇÃO] {ctx.titulo_acao}\n"
        f"[PARTES] {ctx.partes}\n"
        f"[ÁREA] {area}\n"
        f"[OBJETIVO / PEDIDO CENTRAL] {objetivo or 'reparação dos danos e demais medidas cabíveis'}\n\n"
        f"[DOCUMENTOS JUNTADOS — referencie pelos rótulos]\n{bloco_docs}\n\n"
        f"[BASE DE CONHECIMENTO (RAG) — fundamente-se e cite a fonte]\n"
        f"{rag_txt or '(sem fontes recuperadas — não invente; sinalize (verificar))'}"
    )

    resp = await gw_chat(
        messages=[
            {"role": "system", "content": _SYSTEM_RAZOES},
            {"role": "user", "content": user},
        ],
        task_type="elaboracao_peca",   # prosa → base anti-alucinação
        temperature=0.3,
        max_tokens=4000,
        nivel_inteligencia=nivel,
    )
    texto = padronizar_documento_juridico(resp.texto)

    # Verificação de citações (súmulas/artigos) contra a base — fail-safe.
    verificacao = None
    try:
        verificacao = await verificar_citacoes(db, texto)
    except Exception as exc:
        logger.warning("citation_check (razões) falhou: %s", exc)

    # AILog obrigatório (HITL rastreável).
    try:
        await registrar_ai_log(
            db,
            user_id=cu_id,
            tipo_uso=AITipoUso.redacao_peca,
            case_id=case_id,
            prompt_sanitizado=user,
            pii_removida=True,   # documentos já entram sanitizados em resolver_itens
            resposta=texto,
            modelo=resp.modelo,
            fontes_rag=(rag_txt[:2000] or None),
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
        )
    except Exception as exc:
        # IA sem trilha de auditoria NÃO pode ser entregue (mesma regra do
        # executar_tarefa_ia): peça jurídica exige AILog para HITL/OAB.
        logger.error("Falha ao gravar AILog das razões: %s", exc)
        raise RuntimeError(
            "Razões geradas, mas a trilha de auditoria (AILog) falhou — "
            "saída descartada. Tente novamente."
        ) from None

    return {
        "texto": texto,
        "verificacao_citacoes": verificacao,
        "docs_referenciados": [f"Doc. {it.ordem:02d}" for it in itens],
        "aviso": _AVISO_RAZOES,
    }
