"""Serviços puros da Entrada Universal de Documentos."""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
import re
import tempfile
import zipfile
from pathlib import PurePosixPath
from typing import Any, Iterable

from app.services import ocr_service

logger = logging.getLogger("ejc.entrada_universal")
MAX_ARQUIVOS = 60
MAX_BYTES_ARQUIVO = 25 * 1024 * 1024
MAX_BYTES_LOTE = 120 * 1024 * 1024
MAX_BYTES_ZIP_DESCOMPACTADO = 100 * 1024 * 1024
MAX_TEXTO_LOTE = 160_000
EXTENSOES_SUPORTADAS = {
    ".pdf", ".docx", ".doc", ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".webp", ".heic", ".heif", ".txt", ".xlsx", ".xls", ".csv", ".xml", ".zip",
}
MIME_FALLBACK = {
    ".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".tiff": "image/tiff", ".tif": "image/tiff", ".webp": "image/webp", ".heic": "image/heic",
    ".heif": "image/heif", ".txt": "text/plain", ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xls": "application/vnd.ms-excel",
    ".xml": "application/xml", ".zip": "application/zip",
}
CATALOGO_DOCUMENTAL: dict[str, list[dict[str, Any]]] = {
    "multa_transito": [
        {"tipo": "auto_infracao_transito", "nome": "Auto de infração", "obrigatorio": True, "aliases": ["auto de infracao", "ait", "codigo da infracao", "enquadramento"]},
        {"tipo": "notificacao_transito", "nome": "Notificação de autuação ou penalidade", "obrigatorio": True, "aliases": ["notificacao de autuacao", "notificacao de penalidade", "jari", "cetran"]},
        {"tipo": "documento_veiculo_condutor", "nome": "Documento do veículo e do condutor", "obrigatorio": True, "aliases": ["renavam", "crlv", "cnh", "condutor", "proprietario"]},
        {"tipo": "prova_local_transito", "nome": "Provas do local, sinalização ou equipamento", "obrigatorio": False, "aliases": ["sinalizacao", "fotografia", "radar", "equipamento", "local da infracao"]},
        {"tipo": "decisao_recurso_transito", "nome": "Decisão administrativa anterior", "obrigatorio": False, "aliases": ["decisao da jari", "recurso indeferido", "resultado do julgamento"]},
    ],
    "multa_ambiental": [
        {"tipo": "auto_infracao_ambiental", "nome": "Auto de infração ambiental", "obrigatorio": True, "aliases": ["auto de infracao ambiental", "embargo", "apreensao", "dano ambiental"]},
        {"tipo": "relatorio_fiscalizacao_ambiental", "nome": "Relatório de fiscalização", "obrigatorio": True, "aliases": ["relatorio de fiscalizacao", "vistoria", "coordenadas", "area embargada"]},
        {"tipo": "notificacao_ciencia_ambiental", "nome": "Notificação e prova da ciência", "obrigatorio": True, "aliases": ["notificacao", "aviso de recebimento", "ciencia", "prazo para defesa"]},
        {"tipo": "licenca_laudo_ambiental", "nome": "Licenças, autorizações, laudos e fotografias", "obrigatorio": False, "aliases": ["licenca ambiental", "autorizacao", "laudo tecnico", "fotografia"]},
        {"tipo": "processo_administrativo_ambiental", "nome": "Processo administrativo integral", "obrigatorio": False, "aliases": ["processo administrativo", "decisao administrativa", "recurso ambiental"]},
    ],
    "multa_administrativa": [
        {"tipo": "auto_ou_notificacao_administrativa", "nome": "Auto, notificação ou decisão recorrida", "obrigatorio": True, "aliases": ["auto de infracao", "notificacao", "decisao administrativa", "sancao"]},
        {"tipo": "norma_regulamento_orgao", "nome": "Norma ou regulamento do órgão", "obrigatorio": True, "aliases": ["regulamento", "resolucao", "portaria", "edital", "norma aplicavel"]},
        {"tipo": "processo_administrativo_integral", "nome": "Processo administrativo integral", "obrigatorio": True, "aliases": ["processo administrativo", "autos do processo", "instrucao processual"]},
        {"tipo": "prova_tecnica_regularidade", "nome": "Documentos técnicos e prova de regularidade", "obrigatorio": False, "aliases": ["laudo", "certificado", "comprovante", "relatorio tecnico"]},
    ],
    "revisao_contratual": [
        {"tipo": "contrato_original", "nome": "Contrato original", "obrigatorio": True, "aliases": ["contrato", "instrumento particular", "clausula", "contratante", "contratada"]},
        {"tipo": "aditivo_contratual", "nome": "Aditivos e anexos", "obrigatorio": False, "aliases": ["aditivo", "termo aditivo", "anexo contratual"]},
        {"tipo": "execucao_pagamentos", "nome": "Comprovantes de execução e pagamentos", "obrigatorio": True, "aliases": ["nota fiscal", "comprovante de pagamento", "boleto", "medicao", "entrega"]},
        {"tipo": "comunicacoes_contratuais", "nome": "Comunicações entre as partes", "obrigatorio": False, "aliases": ["notificacao extrajudicial", "e-mail", "mensagem", "inadimplemento"]},
        {"tipo": "prova_dano_contratual", "nome": "Planilhas e documentos do dano", "obrigatorio": False, "aliases": ["planilha", "prejuizo", "perdas e danos", "orcamento"]},
    ],
    "revisao_bancaria": [
        {"tipo": "contrato_bancario", "nome": "Contrato ou cédula de crédito", "obrigatorio": True, "aliases": ["cedula de credito", "contrato bancario", "financiamento", "emprestimo", "credito"]},
        {"tipo": "evolucao_divida", "nome": "Planilha de evolução da dívida e extratos", "obrigatorio": True, "aliases": ["evolucao da divida", "saldo devedor", "extrato", "demonstrativo"]},
        {"tipo": "parcelas_pagas", "nome": "Comprovantes de parcelas pagas", "obrigatorio": True, "aliases": ["parcela paga", "comprovante", "quitacao", "pagamento"]},
        {"tipo": "cet_tarifas_seguros", "nome": "CET, tarifas, seguros e encargos", "obrigatorio": True, "aliases": ["custo efetivo total", "cet", "tarifa", "seguro", "iof", "taxa de juros"]},
    ],
}
_CLASSIFICADORES_GERAIS = [
    ("peticao", ["excelentissimo", "dos fatos", "dos pedidos", "requer a vossa excelencia"]),
    ("sentenca_acordao", ["sentenca", "acordao", "dou provimento", "nego provimento", "julgo procedente"]),
    ("procuracao", ["outorgante", "outorgado", "poderes da clausula ad judicia"]),
    # "cpf" e "data de nascimento" SAÍRAM: aparecem em qualquer petição, contrato
    # ou procuração — eram a origem de peça longa classificada como documento de
    # identificação. Os aliases restantes só ocorrem no documento de identidade.
    ("documento_identificacao", ["registro geral", "carteira de identidade", "orgao expedidor",
                                 "documento de identidade", "carteira nacional de habilitacao"]),
    ("comprovante_residencia", ["energia eletrica", "agua e esgoto", "endereco de fornecimento"]),
    ("laudo_tecnico", ["laudo tecnico", "responsavel tecnico", "conclusao tecnica"]),
    # "valor total" saiu pelo mesmo motivo (aparece em contrato, planilha, orçamento).
    ("nota_fiscal", ["nota fiscal", "nfe", "chave de acesso", "danfe", "natureza da operacao"]),
]

# Zona de cabeçalho: onde um documento se identifica ("EXCELENTÍSSIMO...",
# "AUTO DE INFRAÇÃO Nº...", "PROCURAÇÃO"). Um alias aqui vale mais que o mesmo
# alias perdido na página 12.
_JANELA_CABECALHO = 2_500
_PESO_CABECALHO = 2.0
# Evidência mínima para afirmar um tipo. Abaixo disso o documento fica sem tipo
# afirmado (revisão humana), em vez de receber um rótulo confiante e errado.
_SCORE_MINIMO = 3.0
# Margem sobre o segundo colocado. Empate técnico não é classificação.
_MARGEM_MINIMA = 1.5

# Tipos locais → chaves canônicas de `document_types_master`. Só o que está
# mapeado pode ser gravado em `Document.tipo`; o resto permanece sugestão no
# item do lote. Sem isto, o GED guardava chaves inexistentes no catálogo
# ("outro_documento", "sentenca_acordao"), que nenhum seletor/filtro reconhece.
TIPO_LOCAL_PARA_CATALOGO: dict[str, str] = {
    "peticao": "peticao",
    "procuracao": "procuracao",
    "documento_identificacao": "doc_identificacao",
    "comprovante_residencia": "comprovante_residencia",
    "laudo_tecnico": "laudo_tecnico",
    "nota_fiscal": "nfe_xml",
    "contrato_original": "contrato",
    "contrato_bancario": "contrato",
    "aditivo_contratual": "contrato",
    "auto_infracao_transito": "multa_transito",
    "notificacao_transito": "multa_transito",
    "auto_infracao_ambiental": "multa_ambiental",
    "auto_ou_notificacao_administrativa": "auto_infracao",
    "licenca_laudo_ambiental": "laudo_tecnico",
    "prova_tecnica_regularidade": "laudo_tecnico",
}


def _norm(texto: str | None) -> str:
    raw = (texto or "").casefold().translate(str.maketrans("çáàãâéêíóôõú", "caaaaeeiooou"))
    return re.sub(r"\s+", " ", raw).strip()


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def extensao(nome: str) -> str:
    return os.path.splitext(nome or "")[1].lower()


def validar_extensao(nome: str) -> str:
    ext = extensao(nome)
    if ext not in EXTENSOES_SUPORTADAS:
        raise ValueError(f"Formato não suportado: {ext or 'sem extensão'}")
    return ext


def expandir_zip(nome: str, raw: bytes) -> list[dict[str, Any]]:
    saida, total = [], 0
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise ValueError("Arquivo ZIP inválido ou corrompido") from exc
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_ARQUIVOS:
            raise ValueError(f"ZIP excede o limite de {MAX_ARQUIVOS} arquivos")
        for info in infos:
            path = PurePosixPath(info.filename.replace("\\", "/"))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("ZIP contém caminho inseguro")
            base = path.name
            if not base or base.startswith(".") or "__MACOSX" in path.parts:
                continue
            ext = validar_extensao(base)
            if ext == ".zip":
                raise ValueError("ZIP aninhado não é permitido")
            total += int(info.file_size or 0)
            if total > MAX_BYTES_ZIP_DESCOMPACTADO:
                raise ValueError("ZIP excede o limite descompactado de 100 MB")
            conteudo = zf.read(info)
            if len(conteudo) > MAX_BYTES_ARQUIVO:
                raise ValueError(f"Arquivo {base} excede 25 MB")
            saida.append({"nome": base, "nome_origem": f"{nome}::{info.filename}", "conteudo": conteudo,
                          "extensao": ext, "mimetype": MIME_FALLBACK.get(ext, "application/octet-stream"),
                          "origem_zip": nome})
    if not saida:
        raise ValueError("ZIP não contém documentos suportados")
    return saida


def expandir_arquivo(nome: str, raw: bytes, mimetype: str | None = None) -> list[dict[str, Any]]:
    ext = validar_extensao(nome)
    if not raw:
        raise ValueError(f"Arquivo vazio: {nome}")
    if len(raw) > MAX_BYTES_ARQUIVO and ext != ".zip":
        raise ValueError(f"Arquivo {nome} excede 25 MB")
    if ext == ".zip":
        return expandir_zip(nome, raw)
    return [{"nome": os.path.basename(nome), "nome_origem": nome, "conteudo": raw, "extensao": ext,
             "mimetype": mimetype or MIME_FALLBACK.get(ext, "application/octet-stream"), "origem_zip": None}]


def _peso_alias(alias: str) -> float:
    """Aliases longos são evidência forte; palavra solta é evidência fraca.

    "requer a vossa excelencia" identifica uma petição; "sentenca" aparece no
    pedido de qualquer petição. Contá-los igual era o que fazia um documento
    longo pontuar em meia dúzia de tipos ao mesmo tempo.
    """
    palavras = len(alias.split())
    if palavras >= 4:
        return 3.0
    if palavras >= 2:
        return 2.0
    return 1.0


def _score_aliases(aliases: list[str], cabecalho: str, corpo: str) -> float:
    """Soma o peso dos aliases encontrados, com bônus para a zona de cabeçalho.

    A busca exige fronteira de palavra: sem isso "cnh" casava dentro de
    "reconhecimento" e "ait" dentro de "gratuita".
    """
    total = 0.0
    for alias in aliases:
        alvo = _norm(alias)
        if not alvo:
            continue
        padrao = re.compile(rf"(?<!\w){re.escape(alvo)}(?!\w)")
        if padrao.search(cabecalho):
            total += _peso_alias(alvo) * _PESO_CABECALHO
        elif padrao.search(corpo):
            total += _peso_alias(alvo)
    return total


def _nao_classificado(motivo: str) -> dict[str, Any]:
    # Rótulo honesto na tela: "Outro documento" soava como decisão tomada.
    return {"tipo": "outro_documento", "nome": "Não classificado — confirmar", "confianca": 0.0,
            "tipo_catalogo": None, "metodo": "regras_locais",
            "obrigatorio_na_modalidade": False, "requer_confirmacao_humana": True,
            "motivo": motivo}


def classificar_documento(nome: str, texto: str, modalidade: str | None = None) -> dict[str, Any]:
    """Sugere o tipo do documento por regras locais — SUGESTÃO, nunca veredito.

    Devolve `tipo_catalogo` (chave de `document_types_master`) apenas quando a
    evidência é suficiente e o tipo tem correspondente canônico; só esse campo
    pode ser gravado no GED. `requer_confirmacao_humana` é sempre verdadeiro:
    classificação documental é ato do advogado (HITL).
    """
    texto = texto or ""
    cabecalho = _norm(f"{nome} {texto[:_JANELA_CABECALHO]}")
    corpo = _norm(texto[_JANELA_CABECALHO:40_000])
    candidatos: list[tuple[str, str, float, bool]] = []
    if modalidade in CATALOGO_DOCUMENTAL:
        for item in CATALOGO_DOCUMENTAL[modalidade]:
            score = _score_aliases(item["aliases"], cabecalho, corpo)
            if score:
                candidatos.append((item["tipo"], item["nome"], score, bool(item["obrigatorio"])))
    for tipo, aliases in _CLASSIFICADORES_GERAIS:
        score = _score_aliases(aliases, cabecalho, corpo)
        if score:
            candidatos.append((tipo, tipo.replace("_", " ").title(), score, False))
    if not candidatos:
        return _nao_classificado("Nenhum indício textual do tipo documental.")

    candidatos.sort(key=lambda x: (x[2], x[3]), reverse=True)
    tipo, rotulo, score, obrigatorio = candidatos[0]
    if score < _SCORE_MINIMO:
        return _nao_classificado(
            f"Evidência insuficiente para afirmar o tipo (score {score:.1f} < {_SCORE_MINIMO:.1f})."
        )
    segundo = candidatos[1][2] if len(candidatos) > 1 else 0.0
    if score - segundo < _MARGEM_MINIMA:
        return _nao_classificado(
            f"Empate técnico entre '{tipo}' e '{candidatos[1][0]}' — classificação não afirmada."
        )

    # Confiança ancorada na evidência acima do mínimo, com teto: regra local não
    # produz certeza. O valor antigo (0.5 + 0.14×score) exibia ~64% para um
    # único alias fraco encontrado em qualquer ponto do texto.
    confianca = round(min(0.9, 0.45 + (score - _SCORE_MINIMO) * 0.05), 2)
    return {"tipo": tipo, "nome": rotulo, "confianca": confianca,
            "tipo_catalogo": TIPO_LOCAL_PARA_CATALOGO.get(tipo),
            "metodo": "regras_locais", "obrigatorio_na_modalidade": obrigatorio,
            "requer_confirmacao_humana": True,
            "score": round(score, 2), "score_segundo_colocado": round(segundo, 2)}


def _registrar_heif() -> bool:
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
        return True
    except Exception:
        return False


def _ordenar_pontos(points):
    import numpy as np
    rect = np.zeros((4, 2), dtype="float32")
    soma, diff = points.sum(axis=1), np.diff(points, axis=1)
    rect[0], rect[2], rect[1], rect[3] = points[soma.argmin()], points[soma.argmax()], points[diff.argmin()], points[diff.argmax()]
    return rect


def _corrigir_perspectiva_cv2(raw: bytes) -> tuple[bytes, bool]:
    try:
        import cv2
        import numpy as np
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return raw, False
        h, w = image.shape[:2]
        escala = 1400 / max(h, w) if max(h, w) > 1400 else 1.0
        small = cv2.resize(image, None, fx=escala, fy=escala) if escala < 1 else image.copy()
        gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
        contours, _ = cv2.findContours(cv2.Canny(gray, 50, 150), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        quad, min_area = None, small.shape[0] * small.shape[1] * 0.18
        for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
            if cv2.contourArea(contour) < min_area:
                continue
            approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
            if len(approx) == 4:
                quad = approx.reshape(4, 2).astype("float32") / escala
                break
        if quad is None:
            return raw, False
        tl, tr, br, bl = _ordenar_pontos(quad)
        width = int(max((((br - bl) ** 2).sum()) ** .5, (((tr - tl) ** 2).sum()) ** .5))
        height = int(max((((tr - br) ** 2).sum()) ** .5, (((tl - bl) ** 2).sum()) ** .5))
        if width < 300 or height < 300:
            return raw, False
        dst = np.array([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]], dtype="float32")
        warped = cv2.warpPerspective(image, cv2.getPerspectiveTransform(_ordenar_pontos(quad), dst), (width, height))
        ok, encoded = cv2.imencode(".png", warped)
        return (encoded.tobytes(), True) if ok else (raw, False)
    except Exception as exc:
        logger.debug("Correção de perspectiva indisponível: %s", exc)
        return raw, False


def normalizar_imagem(raw: bytes, ext: str) -> tuple[bytes, dict[str, Any]]:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    heif = ext in {".heic", ".heif"}
    if heif and not _registrar_heif():
        raise ValueError("Suporte HEIC/HEIF indisponível no servidor")
    corrigida, perspectiva = _corrigir_perspectiva_cv2(raw)
    with Image.open(io.BytesIO(corrigida)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        original = img.size
        img = ImageEnhance.Contrast(ImageOps.autocontrast(img, cutoff=1)).enhance(1.08).filter(ImageFilter.SHARPEN)
        out = io.BytesIO()
        img.save(out, format="PNG", optimize=True)
    return out.getvalue(), {"rotacao_exif_corrigida": True, "perspectiva_corrigida": perspectiva,
                            "contraste_melhorado": True, "nitidez_melhorada": True,
                            "convertido_de_heic": heif, "dimensoes": {"largura": original[0], "altura": original[1]}}


def _ocr_imagem(raw: bytes) -> tuple[str, float]:
    try:
        import pytesseract
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as img:
            rgb = img.convert("RGB")
            try:
                texto = pytesseract.image_to_string(rgb, lang="por")
                data = pytesseract.image_to_data(rgb, lang="por", output_type=pytesseract.Output.DICT)
            except pytesseract.TesseractError:
                texto = pytesseract.image_to_string(rgb)
                data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)
        confs = []
        for value in data.get("conf", []):
            try:
                value = float(value)
                if value >= 0:
                    confs.append(value / 100)
            except (TypeError, ValueError):
                pass
        confianca = sum(confs) / len(confs) if confs else (0.55 if texto.strip() else 0.0)
        return texto.strip(), round(min(max(confianca, 0.0), 1.0), 3)
    except Exception as exc:
        logger.warning("OCR de imagem falhou: %s", exc)
        return "", 0.0


def _extrair_csv(raw: bytes) -> str:
    rows = []
    for row in csv.reader(io.StringIO(raw.decode("utf-8", errors="replace"))):
        cells = [str(c).strip() for c in row if str(c).strip()]
        if cells:
            rows.append(" | ".join(cells))
        if sum(len(x) for x in rows) > ocr_service.MAX_OCR_CHARS:
            break
    return "\n".join(rows)[:ocr_service.MAX_OCR_CHARS]


def extrair_paginas(raw: bytes, ext: str, mimetype: str | None = None) -> dict[str, Any]:
    paginas, avisos, processamento = [], [], None
    if ext == ".pdf":
        try:
            import fitz
            from PIL import Image
            with fitz.open(stream=raw, filetype="pdf") as pdf:
                for index, page in enumerate(pdf):
                    texto, metodo = (page.get_text("text") or "").strip(), "texto_nativo"
                    confianca = 1.0 if texto else 0.0
                    if len(texto) < 20:
                        pix = page.get_pixmap(dpi=220)
                        image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                        buff = io.BytesIO()
                        image.save(buff, format="PNG")
                        normalizada, processamento = normalizar_imagem(buff.getvalue(), ".png")
                        texto, confianca = _ocr_imagem(normalizada)
                        metodo = "ocr"
                    paginas.append({"pagina": index + 1, "texto": texto, "confianca": round(confianca, 3),
                                    "metodo": metodo, "requer_revisao": confianca < .72 or len(texto) < 20})
                    if sum(len(p["texto"]) for p in paginas) >= ocr_service.MAX_OCR_CHARS:
                        avisos.append("Texto truncado no limite seguro de armazenamento")
                        break
        except Exception as exc:
            raise ValueError(f"Falha ao ler PDF: {str(exc)[:160]}") from exc
    elif ext in {".jpg", ".jpeg", ".png", ".tiff", ".tif", ".webp", ".heic", ".heif"}:
        normalizada, processamento = normalizar_imagem(raw, ext)
        texto, confianca = _ocr_imagem(normalizada)
        paginas.append({"pagina": 1, "texto": texto, "confianca": confianca, "metodo": "ocr",
                        "requer_revisao": confianca < .72 or len(texto) < 20})
    elif ext == ".csv":
        paginas.append({"pagina": 1, "texto": _extrair_csv(raw), "confianca": 1.0, "metodo": "csv", "requer_revisao": False})
    else:
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
        try:
            tmp.write(raw)
            tmp.flush()
            tmp.close()
            texto = ocr_service.extrair_texto(tmp.name, mimetype or MIME_FALLBACK.get(ext)) or ""
            paginas.append({"pagina": 1, "texto": texto.strip(), "confianca": 1.0 if texto.strip() else 0.0,
                            "metodo": "extrator_estruturado", "requer_revisao": not bool(texto.strip())})
        finally:
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
    texto_total = "\n\n".join(p["texto"] for p in paginas if p["texto"])
    confs = [float(p["confianca"]) for p in paginas if p.get("texto")]
    if not texto_total.strip():
        avisos.append("Nenhum texto legível foi extraído; o original foi preservado no GED")
    return {"texto": texto_total[:ocr_service.MAX_OCR_CHARS], "paginas": paginas, "page_count": len(paginas),
            "confianca_media": round(sum(confs) / len(confs), 3) if confs else 0.0,
            "processamento_imagem": processamento, "avisos": avisos}


def montar_dossie(itens: Iterable[dict[str, Any]], texto_adicional: str | None = None) -> str:
    blocos = []
    for ordem, item in enumerate(itens, 1):
        nome = item.get("filename") or item.get("nome") or f"Documento {ordem}"
        cls = item.get("classification") or item.get("classificacao") or {}
        blocos.append(f"[DOCUMENTO {ordem}: {nome} | TIPO: {cls.get('tipo', 'não classificado')}]")
        paginas = (item.get("extraction_meta") or {}).get("paginas") or item.get("paginas") or []
        for pagina in paginas:
            if (pagina.get("texto") or "").strip():
                blocos.append(f"[PÁGINA {pagina.get('pagina', '?')}]\n{pagina['texto'].strip()}")
        if not paginas and item.get("texto"):
            blocos.append(item["texto"])
    if texto_adicional and texto_adicional.strip():
        blocos.append(f"[INFORMAÇÕES COMPLEMENTARES DO ADVOGADO]\n{texto_adicional.strip()}")
    return "\n\n".join(blocos)[:MAX_TEXTO_LOTE]


def avaliar_prontidao(modalidade: str | None, itens: Iterable[dict[str, Any]]) -> dict[str, Any]:
    itens_list, catalogo = list(itens), CATALOGO_DOCUMENTAL.get(modalidade or "", [])
    tipos = {((i.get("classification") or i.get("classificacao") or {}).get("tipo")) for i in itens_list
             if (i.get("extraction_status") or i.get("status_extracao")) != "erro"}
    checklist, faltantes = [], []
    for requisito in catalogo:
        presente = requisito["tipo"] in tipos
        checklist.append({"item": requisito["nome"], "tipo": requisito["tipo"],
                          "status": "atendido" if presente else ("pendente" if requisito["obrigatorio"] else "confirmar"),
                          "impeditivo": bool(requisito["obrigatorio"])})
        if requisito["obrigatorio"] and not presente:
            faltantes.append(requisito["nome"])
    erros = [i for i in itens_list if (i.get("extraction_status") or i.get("status_extracao")) == "erro"]
    baixa = [i.get("filename") or i.get("nome") for i in itens_list
             if float((i.get("extraction_meta") or i.get("meta_extracao") or {}).get("confianca_media") or 0) < .62]
    if faltantes:
        nivel, justificativa = "nao_apto_para_redacao", "Há documentos obrigatórios ausentes."
    elif erros or baixa:
        nivel, justificativa = "apto_com_ressalvas", "O conjunto pode ser analisado, mas há falhas ou baixa confiança de leitura."
    else:
        nivel, justificativa = "apto_para_redacao", "Os documentos obrigatórios foram identificados; a revisão humana continua obrigatória."
    return {"nivel": nivel, "justificativa": justificativa, "checklist": checklist,
            "documentos_faltantes": faltantes, "arquivos_com_erro": [i.get("filename") or i.get("nome") for i in erros],
            "arquivos_baixa_qualidade": baixa, "requer_confirmacao_humana": True}


def _valores_regex(texto: str) -> dict[str, set[str]]:
    return {"percentuais": set(re.findall(r"\b\d{1,3}(?:[.,]\d+)?\s*%", texto)),
            "placas": set(re.findall(r"\b[A-Z]{3}[- ]?\d[A-Z0-9]\d{2}\b", texto.upper())),
            "processos": set(re.findall(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b", texto)),
            "autos": set(re.findall(r"(?i)\b(?:auto|ait)\s*(?:n[ºo°.]*)?\s*[:#-]?\s*([A-Z0-9./-]{5,})", texto))}


def comparar_documentos(itens: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    docs = []
    for item in itens:
        meta = item.get("extraction_meta") or item.get("meta_extracao") or {}
        texto = "\n".join(p.get("texto", "") for p in meta.get("paginas", [])) or item.get("texto", "")
        docs.append((item.get("filename") or item.get("nome") or "Documento", _valores_regex(texto)))
    divergencias = []
    for chave in ("placas", "processos", "autos"):
        valores = [(nome, vals[chave]) for nome, vals in docs if vals[chave]]
        universo = set().union(*(v for _, v in valores)) if valores else set()
        if len(universo) > 1:
            divergencias.append({"tipo": f"divergencia_{chave}", "titulo": f"Divergência de {chave}",
                                 "detalhes": [{"documento": n, "valores": sorted(v)} for n, v in valores],
                                 "requer_confirmacao_humana": True})
    percentuais = [(n, v["percentuais"]) for n, v in docs if v["percentuais"]]
    universo = set().union(*(v for _, v in percentuais)) if percentuais else set()
    if len(percentuais) >= 2 and len(universo) > 1:
        divergencias.append({"tipo": "percentuais_divergentes", "titulo": "Percentuais diferentes entre documentos",
                             "detalhes": [{"documento": n, "valores": sorted(v)} for n, v in percentuais],
                             "requer_confirmacao_humana": True})
    return divergencias


def manifesto_pacote(modalidade: str | None, prontidao: dict[str, Any]) -> list[dict[str, Any]]:
    bloqueado = prontidao.get("nivel") == "nao_apto_para_redacao"
    itens = [("relatorio_analise", "Relatório de análise", True), ("cronologia", "Cronologia dos fatos e atos", True),
             ("matriz_vicios_teses", "Matriz de vícios, fatos, provas, fundamentos e riscos", True),
             ("checklist_documental", "Checklist documental", True),
             ("memoria_calculo", "Memória de cálculo", modalidade == "revisao_bancaria"),
             ("peca_principal", "Defesa, recurso, parecer ou ação revisional", not bloqueado),
             ("indice_anexos", "Índice dos anexos", True), ("caderno_provas", "Caderno único de provas", True),
             ("procuracao_honorarios", "Procuração e contrato de honorários", not bloqueado),
             ("prazo_tarefa", "Prazo e tarefa vinculados", not bloqueado)]
    return [{"codigo": c, "nome": n, "status": "disponivel" if ok else "bloqueado",
             "motivo": None if ok else "Pendências impeditivas devem ser resolvidas antes da geração."} for c, n, ok in itens]


def resumo_documentos(itens: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    saida = []
    for item in itens:
        meta, cls = item.get("extraction_meta") or {}, item.get("classification") or {}
        paginas = [{"pagina": p.get("pagina"), "confianca": p.get("confianca"), "metodo": p.get("metodo"),
                    "requer_revisao": p.get("requer_revisao"), "trecho": (p.get("texto") or "")[:240]}
                   for p in meta.get("paginas", [])]
        saida.append({"id": item.get("id"), "document_id": item.get("document_id"),
                      "filename": item.get("filename") or item.get("nome"), "source_order": item.get("source_order"),
                      "sha256": item.get("sha256"), "duplicate_of_document_id": item.get("duplicate_of_document_id"),
                      "extraction_status": item.get("extraction_status"), "page_count": meta.get("page_count") or item.get("page_count"),
                      "confianca_media": meta.get("confianca_media"), "classification": cls,
                      "avisos": meta.get("avisos", []), "paginas": paginas})
    return saida
