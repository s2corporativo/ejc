# ── app/services/ajuizamento/canonico.py ─────────────────────────────────────
# CanonicalJudicialCase — representação única, independente de tribunal, do
# que será protocolado. Construída a partir das entidades EXISTENTES
# (Client, Case, CaseParte, User, LegalDoc, Procuracao, Document); os
# conectores mapeiam daqui para o payload de cada destino.
#
# PII: o snapshot serializável (`to_dict`) mascara CPF/CNPJ e guarda o hash
# cego; o valor em claro fica no atributo `documento` em memória e só é lido
# pelo mapeador do conector no instante do envio.
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.services.pii_crypto import hash_documento, mascarar_documento, normalizar_documento

POLOS = ("ativo", "passivo", "terceiro")
TIPOS_PARTE_POLO = {
    "autor": "ativo", "requerente": "ativo", "exequente": "ativo",
    "reu": "passivo", "requerido": "passivo", "executado": "passivo",
    "terceiro": "terceiro",
}
TIPOS_DOCUMENTO = (
    "peticao_inicial", "procuracao", "documento_pessoal", "comprovante",
    "probatorio", "complementar",
)


@dataclass(frozen=True)
class Identificacao:
    ejc_id: str
    case_id: str
    client_id: str
    tribunal: str | None = None
    segmento: str | None = None
    grau: str | None = None
    sistema: str | None = None
    jurisdicao: str | None = None
    codigo_localidade: str | None = None
    competencia: str | None = None
    competencia_codigo: str | None = None
    unidade_judicial: str | None = None
    ambiente: str | None = None


@dataclass(frozen=True)
class Assunto:
    codigo: str
    nome: str | None = None
    principal: bool = False


@dataclass(frozen=True)
class Processo:
    classe_codigo: str | None
    classe_nome: str | None
    assuntos: tuple[Assunto, ...]
    valor_causa: Decimal | None
    nivel_sigilo: int = 0
    gratuidade: bool = False
    tutela: bool = False
    prioridade: str | None = None
    caracteristicas: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Endereco:
    cep: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    municipio: str | None = None
    uf: str | None = None


@dataclass(frozen=True)
class Parte:
    origem_id: str            # id em case_partes ou clients
    origem: str               # "client" | "case_parte"
    polo: str                 # ativo|passivo|terceiro
    tipo_pessoa: str          # fisica|juridica|autoridade|orgao
    nome: str
    documento: str | None = None       # CPF/CNPJ em claro (só memória)
    nome_social: str | None = None
    nascimento: date | None = None
    filiacao: str | None = None
    nacionalidade: str | None = None
    profissao: str | None = None
    email: str | None = None
    telefone: str | None = None
    endereco: Endereco | None = None
    ids_extras: dict[str, str] = field(default_factory=dict)

    @property
    def documento_normalizado(self) -> str | None:
        return normalizar_documento(self.documento)


@dataclass(frozen=True)
class Representacao:
    advogado_id: str
    nome: str
    oab_numero: str | None
    oab_uf: str | None
    tipo: str = "advogado"    # advogado|advogado_auxiliar|estagiario
    documento: str | None = None
    procuracao_id: str | None = None
    procuracao_document_id: str | None = None


@dataclass(frozen=True)
class DocumentoCanonico:
    document_id: str          # Document.id ou LegalDoc.id
    origem: str               # "document" | "legal_doc"
    file_name: str
    mime_type: str | None
    size: int | None
    sha256: str | None
    document_type: str        # TIPOS_DOCUMENTO
    tpu_document_type: str | None = None
    signed: bool = False
    signature_type: str | None = None
    created_at: datetime | None = None
    ordem: int = 0


@dataclass(frozen=True)
class CanonicalJudicialCase:
    identificacao: Identificacao
    processo: Processo
    partes: tuple[Parte, ...]
    representacao: tuple[Representacao, ...]
    documentos: tuple[DocumentoCanonico, ...]

    # ── Consultas de conveniência ─────────────────────────────────────────
    def partes_por_polo(self, polo: str) -> list[Parte]:
        return [p for p in self.partes if p.polo == polo]

    @property
    def peticao_inicial(self) -> DocumentoCanonico | None:
        return next((d for d in self.documentos if d.document_type == "peticao_inicial"), None)

    # ── Serialização segura (PII mascarada) ───────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        def _val(v: Any) -> Any:
            if isinstance(v, Decimal):
                return str(v)
            if isinstance(v, (date, datetime)):
                return v.isoformat()
            return v

        d = asdict(self)
        for p in d["partes"]:
            doc = p.pop("documento", None)
            p["documento_mascarado"] = mascarar_documento(doc)
            p["documento_hash"] = hash_documento(normalizar_documento(doc))
        for r in d["representacao"]:
            doc = r.pop("documento", None)
            r["documento_mascarado"] = mascarar_documento(doc)
        return json.loads(json.dumps(d, default=_val, ensure_ascii=False))

    def hash(self) -> str:
        """SHA-256 determinístico do snapshot mascarado (idempotência)."""
        return hashlib.sha256(
            json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()


# ── Construção a partir das entidades do EJC ──────────────────────────────────

def _tipo_pessoa_por_documento(doc: str | None, tipo_cliente: str | None) -> str:
    n = normalizar_documento(doc) or ""
    if len(n) == 14:
        return "juridica"
    if len(n) == 11:
        return "fisica"
    return "juridica" if (tipo_cliente or "").upper() == "PJ" else "fisica"


def parte_de_cliente(client: Any, polo: str = "ativo") -> Parte:
    tipo = getattr(getattr(client, "tipo", None), "value", None) or str(getattr(client, "tipo", "") or "")
    documento = getattr(client, "documento_plain", None)
    return Parte(
        origem_id=client.id,
        origem="client",
        polo=polo,
        tipo_pessoa=_tipo_pessoa_por_documento(documento, tipo),
        nome=getattr(client, "nome_exibicao", None) or client.nome or client.razao_social or "",
        documento=documento,
        nascimento=getattr(client, "data_nascimento", None),
        profissao=getattr(client, "profissao", None),
        email=getattr(client, "email", None),
        telefone=getattr(client, "telefone", None) or getattr(client, "whatsapp", None),
        endereco=Endereco(
            cep=getattr(client, "cep", None),
            logradouro=getattr(client, "logradouro", None),
            numero=getattr(client, "numero", None),
            complemento=getattr(client, "complemento", None),
            bairro=getattr(client, "bairro", None),
            municipio=getattr(client, "cidade", None),
            uf=getattr(client, "estado", None),
        ),
    )


def parte_de_case_parte(parte: Any) -> Parte | None:
    tipo = (getattr(parte, "tipo", "") or "").lower()
    polo = TIPOS_PARTE_POLO.get(tipo)
    if polo is None:
        return None   # advogado/procurador não são partes
    documento = getattr(parte, "cpf_cnpj", None)
    return Parte(
        origem_id=parte.id,
        origem="case_parte",
        polo=polo,
        tipo_pessoa=_tipo_pessoa_por_documento(documento, None),
        nome=parte.nome,
        documento=documento,
        email=getattr(parte, "email", None),
        telefone=getattr(parte, "telefone", None),
        ids_extras={"papel_processual": getattr(parte, "papel_processual", None) or ""},
    )


def _split_oab(oab: str | None, uf_padrao: str | None) -> tuple[str | None, str | None]:
    """"123456/MG", "MG123456", "123456" → (numero, uf)."""
    if not oab:
        return None, uf_padrao
    limpo = oab.strip().upper().replace(" ", "")
    if "/" in limpo:
        num, uf = limpo.split("/", 1)
        return num.strip() or None, (uf.strip()[:2] or uf_padrao)
    if len(limpo) > 2 and limpo[:2].isalpha() and limpo[2:].isdigit():
        return limpo[2:], limpo[:2]
    return limpo, uf_padrao


def representacao_de_usuario(user: Any, tipo: str = "advogado",
                             procuracao: Any | None = None) -> Representacao:
    numero, uf = _split_oab(getattr(user, "oab_number", None), getattr(user, "djen_oab_uf", None))
    if getattr(user, "djen_oab_numero", None):
        numero = numero or user.djen_oab_numero
    return Representacao(
        advogado_id=user.id,
        nome=user.full_name,
        oab_numero=numero,
        oab_uf=uf,
        tipo=tipo,
        procuracao_id=getattr(procuracao, "id", None),
        procuracao_document_id=getattr(procuracao, "document_id", None),
    )


def documento_de_document(doc: Any, document_type: str, ordem: int = 0,
                          tpu_document_type: str | None = None) -> DocumentoCanonico:
    return DocumentoCanonico(
        document_id=doc.id,
        origem="document",
        file_name=doc.filename,
        mime_type=doc.mimetype,
        size=doc.size_bytes,
        sha256=doc.sha256,
        document_type=document_type,
        tpu_document_type=tpu_document_type,
        created_at=doc.created_at,
        ordem=ordem,
    )


def documento_de_peca(peca: Any, ordem: int = 0, sha256_pdf: str | None = None,
                      tpu_document_type: str | None = None) -> DocumentoCanonico:
    """A petição é uma LegalDoc (markdown → PDF na exportação). O hash aqui é
    do CONTEÚDO aprovado (ou do PDF, quando já gerado e informado)."""
    conteudo = (peca.conteudo or "").encode("utf-8")
    return DocumentoCanonico(
        document_id=peca.id,
        origem="legal_doc",
        file_name=f"{peca.codigo_peca or peca.id}.pdf",
        mime_type="application/pdf",
        size=None,
        sha256=sha256_pdf or hashlib.sha256(conteudo).hexdigest(),
        document_type="peticao_inicial",
        tpu_document_type=tpu_document_type,
        created_at=peca.created_at,
        ordem=ordem,
    )


def construir_canonico(
    *,
    filing: Any,
    case: Any,
    client: Any,
    partes: list[Any],
    advogados: list[tuple[Any, str, Any | None]],
    documentos: list[DocumentoCanonico],
) -> CanonicalJudicialCase:
    """Monta o CanonicalJudicialCase a partir do filing + entidades carregadas.

    `partes`: CaseParte do caso (o cliente entra sempre no polo ativo, salvo
    parte explícita com client_id = cliente em outro polo).
    `advogados`: [(User, tipo, Procuracao|None)].
    """
    assuntos = tuple(
        Assunto(codigo=str(a.get("codigo")), nome=a.get("nome"), principal=bool(a.get("principal")))
        for a in (filing.assuntos or []) if a.get("codigo")
    )
    valor = filing.valor_causa if filing.valor_causa is not None else getattr(case, "valor_causa", None)
    processo = Processo(
        classe_codigo=filing.classe_codigo,
        classe_nome=filing.classe_nome,
        assuntos=assuntos,
        valor_causa=Decimal(str(valor)) if valor is not None else None,
        nivel_sigilo=int(filing.nivel_sigilo or 0) or (5 if getattr(case, "sigilo_reforcado", False) else 0),
        gratuidade=bool(filing.gratuidade),
        tutela=bool(filing.tutela),
        prioridade=filing.prioridade,
        caracteristicas=dict(filing.caracteristicas or {}),
    )
    lista_partes: list[Parte] = []
    cliente_em_partes = False
    for cp in partes:
        p = parte_de_case_parte(cp)
        if p is None:
            continue
        if getattr(cp, "client_id", None) == client.id:
            cliente_em_partes = True
            # Dados do cadastro do cliente prevalecem (CPF cifrado, endereço).
            base = parte_de_cliente(client, polo=p.polo)
            p = Parte(**{**asdict(base), "endereco": base.endereco, "ids_extras": p.ids_extras,
                         "origem_id": cp.id, "origem": "case_parte"})
        lista_partes.append(p)
    if not cliente_em_partes:
        lista_partes.insert(0, parte_de_cliente(client, polo="ativo"))

    representacao = tuple(
        representacao_de_usuario(u, tipo, proc) for (u, tipo, proc) in advogados
    )
    identificacao = Identificacao(
        ejc_id=filing.id, case_id=case.id, client_id=client.id,
        tribunal=filing.tribunal_code, segmento=filing.segment, grau=filing.degree,
        sistema=filing.system, jurisdicao=filing.jurisdicao,
        codigo_localidade=filing.codigo_localidade, competencia=filing.competencia,
        competencia_codigo=filing.competencia_codigo,
        unidade_judicial=getattr(case, "vara", None), ambiente=filing.environment,
    )
    return CanonicalJudicialCase(
        identificacao=identificacao,
        processo=processo,
        partes=tuple(lista_partes),
        representacao=representacao,
        documentos=tuple(sorted(documentos, key=lambda d: d.ordem)),
    )
