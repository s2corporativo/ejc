# ── app/services/google_drive_taxonomy.py ─────────────────────────────────────
# Classificação determinística de documentos Google Drive para o RAG jurídico.
#
# Objetivo: evitar que material heterogêneo do Drive entre todo como "doutrina".
# A classificação é conservadora, auditável e baseada em sinais verificáveis do
# caminho/nome/MIME. Não substitui curadoria humana; apenas define uma categoria
# inicial e metadados para revisão.
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DriveTaxonomyDecision:
    categoria: str
    confianca: str
    prioridade: int
    tipo_fonte: str
    area_juridica: str | None
    excluir: bool
    motivo: str
    sinais: list[str]

    def as_extra(self) -> dict:
        return {
            "categoria_sugerida": self.categoria,
            "confianca_sugerida": self.confianca,
            "prioridade": self.prioridade,
            "tipo_fonte": self.tipo_fonte,
            "area_juridica": self.area_juridica,
            "excluir": self.excluir,
            "motivo": self.motivo,
            "sinais": self.sinais,
        }


_EXCLUIR_TOKENS = {
    "teste", "testes", "rascunho", "rascunhos", "lixo", "tmp", "temporario",
    "temporaria", "backup", "bkp", "old", "antigo", "antiga", "nao indexar",
    "nao-indexar", "nao_indexar", "não indexar", "99_testes",
}

_AREA_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("penal_execucao", (
        "execucao penal", "execução penal", "indulto", "comutacao", "comutação",
        "livramento", "lco", "falta grave", "regime aberto", "semiaberto",
        "fechado", "progressao", "progressão", "regressao", "regressão",
        "remicao", "remição", "tornozeleira", "peculio", "pecúlio", "prd",
        "ppl", "guia de execucao", "guia de execução", "hediondo", "lep",
    )),
    ("penal", ("penal", "criminal", "crime", "prisao", "prisão", "flagrante")),
    ("trabalhista", ("trabalhista", "trabalho", "clt", "fgts", "verbas rescisorias", "tst")),
    ("tributario", ("tributario", "tributário", "fiscal", "imposto", "tributo", "carf", "icms", "iss", "pis", "cofins")),
    ("bancario", ("bancario", "bancário", "juros", "financiamento", "emprestimo", "empréstimo", "contrato bancario")),
    ("ambiental", ("ambiental", "meio ambiente", "ibama", "semad", "copam", "prada")),
    ("administrativo", ("administrativo", "tcu", "contratacao publica")),
    ("civil", ("civil", "consumidor", "contrato", "indenizacao", "indenização", "obrigacao", "obrigação")),
)


def normalizar_chave(valor: str | None) -> str:
    texto = (valor or "").replace("_", " ").replace("-", " ").lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(ch for ch in texto if not unicodedata.combining(ch))
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def _tem(texto: str, termos: tuple[str, ...] | set[str]) -> list[str]:
    achados: list[str] = []
    for termo in termos:
        t = normalizar_chave(termo)
        if t and t in texto:
            achados.append(termo)
    return achados


def _tem_token_exclusao(texto: str) -> list[str]:
    sinais: list[str] = []
    for token in _EXCLUIR_TOKENS:
        t = normalizar_chave(token)
        if not t:
            continue
        if " " in t:
            if t in texto:
                sinais.append(token)
        elif re.search(rf"(^|\W){re.escape(t)}(\W|$)", texto):
            sinais.append(token)
    return sinais


def detectar_area(nome: str, caminho: str | None = None) -> tuple[str | None, list[str]]:
    texto = normalizar_chave(f"{caminho or ''} {nome}")
    for area, termos in _AREA_RULES:
        sinais = _tem(texto, termos)
        if sinais:
            return area, sinais
    return None, []


def _categoria_legislacao(area: str | None) -> str:
    if area == "penal_execucao":
        return "legislacao_penal"
    if area == "penal":
        return "legislacao_penal"
    if area == "trabalhista":
        return "legislacao_trabalhista"
    if area == "tributario":
        return "legislacao_tributaria"
    if area == "bancario":
        return "legislacao_bancaria"
    if area == "ambiental":
        return "legislacao_ambiental"
    if area == "administrativo":
        return "legislacao_administrativa"
    return "legislacao_geral"


def _categoria_jurisprudencia(area: str | None, texto: str) -> str:
    if "stj" in texto:
        return "jurisprudencia_stj"
    if "stf" in texto:
        return "jurisprudencia_stf"
    if "tjmg" in texto:
        return "jurisprudencia_tjmg"
    if area == "trabalhista" or "tst" in texto:
        return "jurisprudencia_tst"
    if area == "tributario" or "carf" in texto:
        return "jurisprudencia_carf"
    if area == "administrativo" or "tcu" in texto:
        return "jurisprudencia_tcu"
    return "jurisprudencia"


# Termos de sinal normativo forte (usados também na classificação abaixo). Um
# arquivo com esses sinais NO NOME nunca é descartado por token de exclusão.
_LEGISLACAO_TERMOS = (
    "lei", "decreto", "codigo", "código", "constituicao", "constituição",
    "resolucao", "resolução", "portaria", "instrucao normativa", "instrução normativa",
    "provimento", "estatuto", "medida provisoria", "medida provisória",
)
_JURISPRUDENCIA_TERMOS = (
    "jurisprudencia", "jurisprudência", "acordao", "acórdão", "ementa",
    "julgado", "precedente", "repetitivo", "irdr", "iac", "tese fixada",
    "stj", "stf", "tjmg", "tst", "carf", "tcu",
)


# ── Sinais de PEÇA DE CLIENTE (conteúdo cliente-específico) ───────────────────
# Documentos vinculados a um cliente/processo concreto NÃO podem entrar no RAG
# compartilhado como material genérico ("modelo_documento_juridico"/"doutrina"):
# entrariam com client_id=NULL e seriam recuperáveis em qualquer caso/cliente,
# vazando conteúdo sigiloso entre clientes (quebra de sigilo/LGPD). Quando um
# destes sinais aparece, a decisão vira "peca_interna" — categoria RESTRITA que
# consta de _RESTRICTED_CATS no ai_service: o filtro de escopo do RAG (fail-
# closed) só recupera o doc quando kd.client_id == escopo do cliente.
#
# Os regex numéricos rodam sobre o texto BRUTO (nome/caminho) porque
# normalizar_chave converte "-" em espaço e destruiria a pontuação de nº de
# processo/CPF/CNPJ. O nº CNJ segue o padrão NNNNNNN-DD.AAAA.J.TR.OOOO, com
# pontuação tolerada como opcional. As âncoras (?<!\d)/(?!\d) impedem que um
# trecho maior de dígitos (ex.: timestamp) case por dentro; CPF/CNPJ ainda são
# confirmados por dígito verificador para não marcar IDs numéricos aleatórios.
_CNJ_RE = re.compile(r"(?<!\d)\d{7}-?\d{2}\.?\d{4}\.?\d\.?\d{2}\.?\d{4}(?!\d)")
_CPF_RE = re.compile(r"(?<!\d)\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?!\d)")
_CNPJ_RE = re.compile(r"(?<!\d)\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}(?!\d)")
# "processo nº", "proc nº", "autos nº" no texto normalizado (o "nº" vira "no").
_PROCESSO_MARCADOR_RE = re.compile(r"\b(processo|proc|autos)\s+n[o]?\b")
# Pastas/segmentos de caminho que indicam material cliente-específico. "contencioso"
# foi deixado de fora por ser ambíguo com bibliotecas de modelos organizadas por
# área (ex.: "Modelos/Contencioso Cível/") — evita falso-positivo de sobre-restrição.
_CLIENTE_PASTA_TERMOS = ("clientes", "cliente", "casos", "processos")


# Dígito verificador de CPF/CNPJ: reutiliza a implementação canônica do projeto
# (app/services/validators_service.py) em vez de manter uma cópia local.
from app.services.validators_service import (  # noqa: E402
    validar_cnpj as _cnpj_valido,
    validar_cpf as _cpf_valido,
)


def _detectar_peca_cliente(nome: str, caminho: str | None, texto_norm: str) -> list[str]:
    """Sinais determinísticos de peça/documento cliente-específico.

    Retorna a lista de sinais encontrados (vazia quando não há). Números de
    processo/CPF/CNPJ são casados no texto BRUTO (com pontuação preservada) e
    CPF/CNPJ são confirmados por dígito verificador (evita marcar timestamps/IDs
    numéricos); pasta de cliente é casada como SEGMENTO do caminho (não como
    palavra solta no nome de um modelo genérico); marcadores textuais
    ("processo nº" etc.) no texto já normalizado.
    """
    bruto = f"{caminho or ''} {nome}"
    sinais: list[str] = []

    m_cnj = _CNJ_RE.search(bruto)
    if m_cnj:
        sinais.append(f"processo_cnj:{m_cnj.group(0)}")
    if any(_cnpj_valido(m.group(0)) for m in _CNPJ_RE.finditer(bruto)):
        sinais.append("cnpj_no_nome")
    elif any(_cpf_valido(m.group(0)) for m in _CPF_RE.finditer(bruto)):
        sinais.append("cpf_no_nome")
    if _PROCESSO_MARCADOR_RE.search(texto_norm):
        sinais.append("marcador_processo")

    # Pasta de cliente: só conta como segmento do caminho, para não reclassificar
    # um modelo genérico cujo NOME mencione "processo/caso" de passagem.
    for seg in normalizar_chave(caminho or "").split("/"):
        seg = seg.strip()
        if not seg:
            continue
        achados = _tem(seg, _CLIENTE_PASTA_TERMOS)
        if achados:
            sinais.append(f"pasta_cliente:{seg}")
            break
    return sinais


def classificar_drive_file(nome: str, caminho: str | None = None, mime_type: str | None = None) -> DriveTaxonomyDecision:
    texto = normalizar_chave(f"{caminho or ''} {nome}")
    nome_norm = normalizar_chave(nome)
    area, sinais_area = detectar_area(nome, caminho)
    sinais: list[str] = []
    if sinais_area:
        sinais.extend(sinais_area)

    # P3: o token de exclusão casa SÓ no NOME do arquivo (não no caminho) — antes
    # uma pasta "Backup 2023/" descartava uma "Súmula 7 STJ.docx" legítima da
    # vigência do RAG. Além disso, um sinal normativo forte no nome (súmula/lei/
    # jurisprudência) tem PRECEDÊNCIA: material normativo nomeado com
    # "antigo/backup" não é removido silenciosamente da busca.
    tem_sinal_normativo = (
        "sumula" in nome_norm
        or bool(_tem(nome_norm, _LEGISLACAO_TERMOS))
        or bool(_tem(nome_norm, _JURISPRUDENCIA_TERMOS))
    )
    exclusao = _tem_token_exclusao(nome_norm)
    if exclusao and not tem_sinal_normativo:
        return DriveTaxonomyDecision(
            categoria="nao_indexar",
            confianca="bloqueado",
            prioridade=0,
            tipo_fonte="teste_ou_lixo_operacional",
            area_juridica=area,
            excluir=True,
            motivo="Arquivo sinalizado (no nome) como teste, rascunho, backup ou não indexável.",
            sinais=exclusao + sinais,
        )

    if "sumula" in texto or "sumula" in normalizar_chave(nome):
        if "stj" in texto:
            categoria = "sumula_stj"
        elif "stf" in texto:
            categoria = "sumula_stf"
        elif "tst" in texto:
            categoria = "sumula_tst"
        elif "tjmg" in texto:
            categoria = "sumula_tjmg"
        else:
            categoria = "sumula"
        return DriveTaxonomyDecision(categoria, "alta", 95, "sumula", area, False, "Súmula identificada por nome/caminho.", ["sumula"] + sinais)

    legislacao_sinais = _tem(texto, _LEGISLACAO_TERMOS)
    if legislacao_sinais:
        return DriveTaxonomyDecision(
            _categoria_legislacao(area), "alta", 100, "fonte_oficial_normativa",
            area, False, "Norma/legislação identificada por nome/caminho.", legislacao_sinais + sinais,
        )

    jurisprudencia_sinais = _tem(texto, _JURISPRUDENCIA_TERMOS)
    if jurisprudencia_sinais:
        return DriveTaxonomyDecision(
            _categoria_jurisprudencia(area, texto), "alta", 90, "jurisprudencia",
            area, False, "Jurisprudência/precedente identificado por nome/caminho.", jurisprudencia_sinais + sinais,
        )

    # ── PEÇA DE CLIENTE (conteúdo cliente-específico) ─────────────────────────
    # Precedência: material NORMATIVO genérico (súmula/legislação/jurisprudência)
    # já retornou acima e nunca chega aqui. Esta detecção vem ANTES do ramo
    # "modelo_documento_juridico"/"doutrina"/fallback: uma peça vinculada a um
    # cliente/processo concreto é marcada como RESTRITA (peca_interna) para não
    # vazar no RAG compartilhado. Um modelo/minuta GENÉRICO (sem nº de processo,
    # CPF/CNPJ ou pasta de cliente) não dispara aqui e segue como
    # modelo_documento_juridico no ramo abaixo.
    peca_cliente_sinais = _detectar_peca_cliente(nome, caminho, texto)
    if peca_cliente_sinais:
        return DriveTaxonomyDecision(
            "peca_interna", "bloqueado", 0, "peca_cliente_restrita",
            area, True,
            "Peça/documento cliente-específico (nº de processo CNJ, CPF/CNPJ ou "
            "pasta de cliente): bloqueado para ingestão automática por sigilo/LGPD. "
            "O fluxo genérico do Drive não possui client_id/case_id; o documento "
            "só pode entrar no RAG por fluxo explicitamente escopado ao cliente/caso.",
            peca_cliente_sinais + sinais,
        )

    modelo_sinais = _tem(texto, (
        "pecas praticas", "peças práticas", "peca pratica", "peça prática", "peca", "peça",
        "minuta", "modelo", "peticao", "petição", "agravo", "recurso", "manifestacao",
        "manifestação", "contrarrazoes", "contrarrazões", "contestacao", "contestação",
        "inicial", "justificativa", "pedido", "defere", "indefere", "acolhe", "nao acolhe",
        "não acolhe", "progressao", "progressão", "remicao", "remição", "livramento", "indulto",
    ))
    if modelo_sinais:
        return DriveTaxonomyDecision(
            "modelo_documento_juridico", "media", 70, "modelo_ou_minuta",
            area, False, "Modelo/minuta/peça prática identificada; usar como apoio redacional, não como fonte normativa.", modelo_sinais + sinais,
        )

    doutrina_sinais = _tem(texto, (
        "doutrina", "manual", "livro", "curso", "apostila", "artigo", "comentarios",
        "comentários", "compendio", "compêndio", "guia", "roteiro",
    ))
    if doutrina_sinais:
        return DriveTaxonomyDecision(
            "doutrina", "media", 60, "doutrina_ou_material_tecnico",
            area, False, "Material doutrinário/técnico identificado por nome/caminho.", doutrina_sinais + sinais,
        )

    # Fallback conservador: entra como conhecimento geral de baixa prioridade de
    # curadoria, evitando equiparar automaticamente a fonte oficial.
    return DriveTaxonomyDecision(
        "doutrina", "baixa", 40, "documento_nao_classificado",
        area, False, "Sem sinais fortes; classificado conservadoramente como doutrina de baixa prioridade.", sinais,
    )
