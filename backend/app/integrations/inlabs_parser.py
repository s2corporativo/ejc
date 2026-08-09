"""Parser seguro dos XMLs do DOU disponibilizados pelo INLABS.

O INLABS exige cadastro/login para download em seu portal. Este módulo NÃO
implementa automação de login nem recebe credenciais; ele processa XML/ZIP já
obtido por fluxo autorizado e mantém o monitor atual do in.gov.br como fallback.

O XML do INLABS é fonte de dados abertos, mas não substitui a versão certificada
do Diário Oficial da União para conferência jurídica final.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from io import BytesIO
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


MAX_XML_BYTES = 25 * 1024 * 1024
MAX_ZIP_COMPRESSED_BYTES = 30 * 1024 * 1024
MAX_ZIP_UNCOMPRESSED_BYTES = 80 * 1024 * 1024
MAX_ZIP_FILES = 200


class InlabsParseError(ValueError):
    pass


@dataclass(frozen=True)
class InlabsArticle:
    titulo: str
    texto: str
    secao: str | None
    data_publicacao: str | None
    edicao: str | None
    categoria: str | None
    identificador: str | None
    url_original: str | None
    fonte: str = "Imprensa Nacional — INLABS/DOU XML"
    requer_conferencia_certificada: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1].split(":", 1)[-1]


def _valor(el: ET.Element, nomes: Iterable[str]) -> str | None:
    """Busca metadado por atributo ou nome de elemento, case-insensitive."""
    procurados = {n.casefold() for n in nomes}
    for chave, valor in el.attrib.items():
        if _local(chave).casefold() in procurados and str(valor).strip():
            return str(valor).strip()
    for filho in el.iter():
        if _local(filho.tag).casefold() in procurados:
            txt = " ".join(x.strip() for x in filho.itertext() if x and x.strip()).strip()
            if txt:
                return txt
    return None


def _texto_por_classe(el: ET.Element, classes: Iterable[str]) -> str | None:
    """Lê elementos HTML-like do XML INLABS, ex. `<p class="identifica">`.

    O heading publicado não é o atributo `name` do article: `name` é usado como
    identificador interno em pacotes reais. Classes podem vir combinadas no
    atributo, por isso a comparação é por token.
    """
    procuradas = {c.casefold() for c in classes}
    for filho in el.iter():
        classes_el = {
            token.casefold()
            for token in str(filho.attrib.get("class") or "").split()
            if token.strip()
        }
        if classes_el & procuradas:
            txt = " ".join(x.strip() for x in filho.itertext() if x and x.strip()).strip()
            if txt:
                return txt
    return None


def _texto_corpo(el: ET.Element) -> str:
    candidatos = {"body", "texto", "text", "conteudo", "content"}
    for filho in el.iter():
        if _local(filho.tag).casefold() in candidatos:
            txt = "\n".join(x.strip() for x in filho.itertext() if x and x.strip()).strip()
            if txt:
                return txt
    # fallback: somente texto interno; metadados curtos são depois removidos da
    # utilidade prática pelo requisito de tamanho mínimo.
    return "\n".join(x.strip() for x in el.itertext() if x and x.strip()).strip()


def parse_xml(xml_bytes: bytes) -> list[InlabsArticle]:
    if not xml_bytes:
        return []
    if len(xml_bytes) > MAX_XML_BYTES:
        raise InlabsParseError("XML INLABS excede o limite de processamento")
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise InlabsParseError("XML INLABS inválido") from exc

    artigos = [
        el for el in root.iter()
        if _local(el.tag).casefold() in {"article", "materia", "publicacao"}
    ]
    if not artigos:
        artigos = [root]

    saida: list[InlabsArticle] = []
    for el in artigos:
        # Schema INLABS real: heading visual em <p class="identifica">;
        # `name` é identificador interno e NÃO deve virar título jurídico.
        titulo = (
            _texto_por_classe(el, ("identifica", "titulo", "title"))
            or _valor(el, ("title", "titulo"))
            or "Publicação DOU"
        )
        corpo = _texto_corpo(el)
        if len(corpo) < 20:
            continue
        saida.append(InlabsArticle(
            titulo=titulo[:500],
            texto=corpo,
            # pubName identifica a seção/edição do DOU; artType é natureza do ato.
            secao=_valor(el, ("pubName", "secao", "section")),
            data_publicacao=_valor(el, ("pubDate", "dataPublicacao", "data_publicacao")),
            edicao=_valor(el, ("editionNumber", "edicao", "edition")),
            categoria=_valor(el, ("artType", "artCategory", "categoria", "category")),
            identificador=_valor(el, ("id", "idMateria", "identificador", "name")),
            url_original=_valor(el, ("urlTitle", "url", "link")),
        ))
    return saida


def parse_zip(zip_bytes: bytes) -> list[InlabsArticle]:
    if not zip_bytes:
        return []
    if len(zip_bytes) > MAX_ZIP_COMPRESSED_BYTES:
        raise InlabsParseError("ZIP INLABS excede o limite compactado")
    try:
        zf = ZipFile(BytesIO(zip_bytes))
    except BadZipFile as exc:
        raise InlabsParseError("ZIP INLABS inválido") from exc

    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_ZIP_FILES:
        raise InlabsParseError("ZIP INLABS contém arquivos demais")
    total = sum(max(0, i.file_size) for i in infos)
    if total > MAX_ZIP_UNCOMPRESSED_BYTES:
        raise InlabsParseError("ZIP INLABS excede o limite descompactado")

    saida: list[InlabsArticle] = []
    for info in infos:
        nome = info.filename.replace("\\", "/")
        if nome.startswith("/") or "../" in f"/{nome}":
            raise InlabsParseError("ZIP INLABS contém caminho inseguro")
        if not nome.lower().endswith(".xml"):
            continue
        dados = zf.read(info)
        if len(dados) > MAX_XML_BYTES:
            raise InlabsParseError("XML dentro do ZIP excede o limite")
        saida.extend(parse_xml(dados))
    return saida
