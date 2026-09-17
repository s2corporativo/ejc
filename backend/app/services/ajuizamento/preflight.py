# ── app/services/ajuizamento/preflight.py ────────────────────────────────────
# JudicialPreflightValidator — validação pura (sem I/O) do CanonicalJudicialCase
# contra as regras do destino e a matriz de capacidades. Erro bloqueante
# impede o protocolo; aviso não bloqueia; `missing_fields` orienta a UI;
# `authorization_requirements` lista o que depende de habilitação externa.
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable

from app.services.ajuizamento.canonico import CanonicalJudicialCase, TIPOS_DOCUMENTO
from app.services.ajuizamento.capacidades import EstadoCapacidade, MatrizCapacidades
from app.services.validators_service import validar_cnpj, validar_cpf

MIMES_ACEITOS = frozenset({"application/pdf"})
TAMANHO_MAX_BYTES = 10 * 1024 * 1024        # limite conservador por documento
QUANTIDADE_MAX_DOCUMENTOS = 100
UFS = frozenset(
    "AC AL AP AM BA CE DF ES GO MA MT MS MG PA PB PR PE PI RJ RN RS RO RR SC SP SE TO".split()
)

# Consulta opcional ao cache TPU: (tipo, codigo) → descrição | None.
# `None` como função significa "cache indisponível" (vira aviso, não erro).
LookupTpu = Callable[[str, str], str | None] | None


@dataclass
class ResultadoPreflight:
    ready: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    authorization_requirements: list[str] = field(default_factory=list)

    def erro(self, msg: str, campo: str | None = None) -> None:
        self.errors.append(msg)
        if campo and campo not in self.missing_fields:
            self.missing_fields.append(campo)
        self.ready = False

    def aviso(self, msg: str) -> None:
        self.warnings.append(msg)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "missing_fields": list(self.missing_fields),
            "authorization_requirements": list(self.authorization_requirements),
        }


def _documento_valido(doc: str | None, tipo_pessoa: str) -> bool:
    if not doc:
        return False
    if tipo_pessoa == "juridica":
        return validar_cnpj(doc)
    return validar_cpf(doc)


def validar_preflight(
    canonico: CanonicalJudicialCase,
    matriz: MatrizCapacidades | None,
    *,
    lookup_tpu: LookupTpu = None,
    campos_obrigatorios_destino: tuple[str, ...] = (),
) -> ResultadoPreflight:
    r = ResultadoPreflight()
    ident, proc = canonico.identificacao, canonico.processo

    # ── Destino ──────────────────────────────────────────────────────────
    if not ident.tribunal:
        r.erro("Tribunal de destino não informado", "tribunal")
    if not ident.sistema:
        r.erro("Sistema judicial (PDPJ, PJe/MNI, eproc) não informado", "sistema")
    if not ident.jurisdicao and not ident.codigo_localidade:
        r.erro("Jurisdição/comarca (ou código de localidade) não informada", "jurisdicao")
    if not ident.competencia and not ident.competencia_codigo:
        r.aviso("Competência não informada — alguns tribunais exigem quando classe/assunto admitem mais de uma")

    # ── Classe / assuntos (TPU) ──────────────────────────────────────────
    if not proc.classe_codigo:
        r.erro("Classe processual (código TPU/CNJ) não informada", "classe_codigo")
    elif not str(proc.classe_codigo).isdigit():
        r.erro("Classe processual deve ser o código numérico da TPU", "classe_codigo")
    elif lookup_tpu is None:
        r.aviso("Cache TPU indisponível — classe não verificada contra a tabela do CNJ")
    elif lookup_tpu("classe", str(proc.classe_codigo)) is None:
        r.aviso(f"Classe {proc.classe_codigo} não encontrada no cache TPU local — confirme o código")
    if not proc.assuntos:
        r.erro("Ao menos um assunto (código TPU/CNJ) é obrigatório", "assuntos")
    else:
        if sum(1 for a in proc.assuntos if a.principal) > 1:
            r.erro("Apenas um assunto pode ser marcado como principal", "assuntos")
        for a in proc.assuntos:
            if not str(a.codigo).isdigit():
                r.erro(f"Assunto '{a.codigo}' deve ser código numérico da TPU", "assuntos")
            elif lookup_tpu is not None and lookup_tpu("assunto", str(a.codigo)) is None:
                r.aviso(f"Assunto {a.codigo} não encontrado no cache TPU local — confirme o código")

    # ── Valor da causa / características ────────────────────────────────
    if proc.valor_causa is None:
        r.erro("Valor da causa não informado", "valor_causa")
    elif proc.valor_causa <= Decimal("0"):
        r.erro("Valor da causa deve ser positivo", "valor_causa")
    if not (0 <= int(proc.nivel_sigilo) <= 5):
        r.erro("Nível de sigilo deve estar entre 0 e 5", "nivel_sigilo")
    if proc.nivel_sigilo > 0 and not proc.caracteristicas.get("justificativa_sigilo"):
        r.aviso("Sigilo solicitado sem justificativa em características (justificativa_sigilo)")
    if proc.tutela and not proc.caracteristicas.get("fundamento_tutela"):
        r.aviso("Pedido de tutela sem fundamento registrado (fundamento_tutela)")
    if proc.gratuidade and not any(d.document_type == "comprovante" for d in canonico.documentos):
        r.aviso("Gratuidade de justiça sem comprovante de hipossuficiência anexado")
    for campo in campos_obrigatorios_destino:
        if campo not in proc.caracteristicas or proc.caracteristicas.get(campo) in (None, ""):
            r.erro(f"Campo exigido pelo tribunal não informado: {campo}", f"caracteristicas.{campo}")

    # ── Partes ───────────────────────────────────────────────────────────
    ativos = canonico.partes_por_polo("ativo")
    passivos = canonico.partes_por_polo("passivo")
    if not ativos:
        r.erro("Polo ativo sem partes", "partes")
    if not passivos:
        r.erro("Polo passivo sem partes", "partes")
    for p in canonico.partes:
        rotulo = f"{p.nome or '(sem nome)'} ({p.polo})"
        if not p.nome or len(p.nome.strip()) < 3:
            r.erro(f"Parte sem nome válido no polo {p.polo}", "partes")
        if p.polo == "ativo":
            if not p.documento:
                r.erro(f"CPF/CNPJ obrigatório para a parte do polo ativo: {rotulo}", "partes")
            elif not _documento_valido(p.documento, p.tipo_pessoa):
                r.erro(f"CPF/CNPJ inválido para {rotulo}", "partes")
            end = p.endereco
            if end is None or not (end.cep and end.logradouro and end.municipio and end.uf):
                r.erro(f"Endereço incompleto (CEP, logradouro, município, UF) para {rotulo}", "partes")
            elif end.uf.upper() not in UFS:
                r.erro(f"UF inválida no endereço de {rotulo}", "partes")
        else:
            if p.documento and not _documento_valido(p.documento, p.tipo_pessoa):
                r.erro(f"CPF/CNPJ inválido para {rotulo}", "partes")
            elif not p.documento:
                r.aviso(f"Parte do polo {p.polo} sem CPF/CNPJ: {rotulo} — o tribunal pode exigir")
            if p.endereco is None or not (p.endereco.municipio and p.endereco.uf):
                r.aviso(f"Endereço da parte {rotulo} incompleto — citação pode ser dificultada")

    # ── Representação ────────────────────────────────────────────────────
    if not canonico.representacao:
        r.erro("Nenhum advogado vinculado ao ajuizamento", "advogados")
    for adv in canonico.representacao:
        if not adv.oab_numero or not adv.oab_uf:
            r.erro(f"OAB (número + UF) ausente para {adv.nome}", "advogados")
        elif adv.oab_uf.upper() not in UFS:
            r.erro(f"UF da OAB inválida para {adv.nome}", "advogados")
        if adv.tipo == "advogado" and not (adv.procuracao_id or adv.procuracao_document_id):
            r.aviso(f"Procuração não vinculada para {adv.nome}")

    # ── Documentos ───────────────────────────────────────────────────────
    docs = canonico.documentos
    if not any(d.document_type == "peticao_inicial" for d in docs):
        r.erro("Petição inicial não anexada", "documentos")
    if not any(d.document_type == "procuracao" for d in docs):
        r.aviso("Procuração não anexada — a maioria dos tribunais exige na inicial")
    if len(docs) > QUANTIDADE_MAX_DOCUMENTOS:
        r.erro(f"Quantidade de documentos acima do limite ({QUANTIDADE_MAX_DOCUMENTOS})", "documentos")
    vistos: set[str] = set()
    for d in docs:
        if d.document_type not in TIPOS_DOCUMENTO:
            r.erro(f"Tipo de documento desconhecido: {d.document_type}", "documentos")
        if d.mime_type and d.mime_type not in MIMES_ACEITOS:
            r.erro(f"Documento '{d.file_name}' com MIME não aceito ({d.mime_type}); exigido PDF", "documentos")
        if d.size is not None and d.size > TAMANHO_MAX_BYTES:
            r.erro(f"Documento '{d.file_name}' excede o tamanho máximo por arquivo", "documentos")
        if not d.sha256:
            r.erro(f"Documento '{d.file_name}' sem hash SHA-256 — integridade não verificada", "documentos")
        elif d.sha256 in vistos:
            r.aviso(f"Documento '{d.file_name}' duplicado (mesmo hash)")
        else:
            vistos.add(d.sha256)
        if d.document_type == "peticao_inicial" and not d.signed:
            r.aviso("Petição inicial ainda não assinada — assinatura é etapa obrigatória antes do envio")

    # ── Conector / autenticação / autorização ────────────────────────────
    if matriz is None:
        r.erro("Nenhum conector resolvido para o destino", "sistema")
    else:
        estado = matriz.estado("file_new_case")
        if estado == EstadoCapacidade.UNSUPPORTED:
            r.erro(f"Conector {matriz.conector} não oferece protocolo de petição inicial", "sistema")
        elif estado in (EstadoCapacidade.REQUIRES_AUTHORIZATION, EstadoCapacidade.CONDITIONAL):
            r.authorization_requirements.extend(matriz.requisitos_autorizacao or [
                matriz.itens["file_new_case"].motivo or "habilitação pendente"
            ])
            r.aviso(
                f"Protocolo eletrônico via {matriz.conector} depende de autorização/homologação "
                "— o fluxo seguirá até a revisão e o protocolo será registrado manualmente"
            )
    return r
