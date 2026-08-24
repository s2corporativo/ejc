# ── app/services/teses_seed_importador.py ────────────────────────────────────
# Importador do lote estático de teses candidatas (PR 3 da série de
# consolidação do Banco de Teses — ver docs/decisoes/ADR_BANCO_TESES_CANONICO_
# 2026-08-24.md). Lê `backend/data/legal/theses_master.jsonl`, valida cada
# registro e persiste em `teses` com `status_validacao="descoberta"`.
#
# NÃO é o pipeline de coleta de evidência (teses_evidencia_import.py, que
# busca fonte oficial via LexML/STJ/TJMG/TCU) — é só o ponto de partida: o
# titular já nomeou o tópico da tese, mas nenhuma fonte foi conferida ainda.
# `status_validacao` só sobe para "coletada"+ quando o pipeline de coleta
# anexar `LegalEvidence` real àquela tese. Este módulo nunca grava nada acima
# de "descoberta" — é erro de importação, não um valor possível.
#
# Idempotente por desenho: rodar 2x com o mesmo arquivo produz 0 mudanças na
# segunda vez. Nunca sobrescreve texto já editado por humano nem rebaixa
# status_validacao de uma tese existente — dedup encontrado é só relatado, a
# linha do arquivo é ignorada por completo (persistir é sempre INSERT, nunca
# UPDATE).
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional
from uuid import uuid4

from sqlalchemy import select

from app.core.taxonomia import normalizar_area
from app.models.audit_log import criar_audit_log
from app.models.tese import ORIENTACOES, Tese, TeseStatus, TeseTipo
from app.services.tese_caso_matcher import extrair_termos

CAMINHO_PADRAO = (
    Path(__file__).resolve().parents[2] / "data" / "legal" / "theses_master.jsonl"
)

# Formato usado nos próprios exemplos do titular: BAN-001, CON-002, TRA-006.
_RE_CODIGO = re.compile(r"^[A-Z]{3}-\d{3}$")

# Único status que um arquivo de seed ESTÁTICO pode declarar. Qualquer outro
# valor implica confiabilidade que este pipeline não pode atestar sem passar
# pela coleta de evidência real — falha alta e visível, nunca silenciosa.
_STATUS_PERMITIDO_NO_ARQUIVO = {"descoberta"}

_CAMPOS_TEXTO = (
    "fundamentacao", "jurisprudencia", "contra_argumento", "pressupostos",
    "excecoes", "estrategia", "instancia", "procedimento", "parte_favorecida",
    "tribunal", "magistrado", "tags", "observacoes",
)
_CAMPOS_LISTA = ("requisitos", "provas_necessarias", "riscos", "fontes")

# Sobreposição mínima (interseção / menor conjunto) entre os termos do título
# para considerar duas teses da MESMA área como a mesma tese candidata, mesmo
# com fraseado diferente — cobre o caso comum de um título ser a forma
# abreviada/expandida do outro (ex.: "CDC" vs "Código de Defesa do
# Consumidor"). Overlap coefficient em vez de Jaccard: um título mais longo
# que só ACRESCENTA palavras ao mais curto ainda deve casar. Exige pelo menos
# 2 termos em cada lado — um único termo em comum nunca basta para deduplicar
# silenciosamente duas teses distintas. Limiar alto de propósito: dedup
# falso-positivo apagaria uma tese distinta em silêncio.
_LIMIAR_SIMILARIDADE_TITULO = 0.8


class ImportacaoSeedInvalida(ValueError):
    """Arquivo de seed com registro inválido — falha alta, não silenciosa."""


def _ler_registros(caminho: Path) -> list[dict]:
    registros = []
    with caminho.open(encoding="utf-8") as f:
        for i, linha in enumerate(f, start=1):
            linha = linha.strip()
            if not linha:
                continue
            try:
                registros.append(json.loads(linha))
            except json.JSONDecodeError as exc:
                raise ImportacaoSeedInvalida(
                    f"{caminho}:{i}: linha JSONL inválida — {exc}"
                ) from exc
    return registros


def _validar_registro(registro: dict, *, linha: int, caminho: Path) -> dict:
    codigo = str(registro.get("codigo") or "").strip().upper()
    if not _RE_CODIGO.match(codigo):
        raise ImportacaoSeedInvalida(
            f"{caminho}:{linha}: codigo {registro.get('codigo')!r} fora do "
            "formato AAA-999 (3 letras maiúsculas, hífen, 3 dígitos)."
        )

    status = registro.get("status_validacao")
    if status not in _STATUS_PERMITIDO_NO_ARQUIVO:
        raise ImportacaoSeedInvalida(
            f"{caminho}:{linha}: tese {codigo} tem status_validacao={status!r}; "
            f"seed estático só aceita {sorted(_STATUS_PERMITIDO_NO_ARQUIVO)} — "
            "qualquer status de maior confiança precisa vir do pipeline de "
            "coleta/validação com fonte real, nunca de um arquivo estático."
        )

    titulo = str(registro.get("titulo") or "").strip()
    if not titulo:
        raise ImportacaoSeedInvalida(f"{caminho}:{linha}: tese {codigo} sem titulo.")

    descricao = str(registro.get("descricao") or "").strip()
    if not descricao:
        raise ImportacaoSeedInvalida(f"{caminho}:{linha}: tese {codigo} sem descricao.")

    area_bruta = registro.get("area_juridica")
    area = normalizar_area(area_bruta)
    if area is None:
        raise ImportacaoSeedInvalida(
            f"{caminho}:{linha}: tese {codigo} tem area_juridica={area_bruta!r} "
            "sem correspondência canônica (ver core/taxonomia.normalizar_area)."
        )

    orientacao = registro.get("orientacao")
    if orientacao is not None and orientacao not in ORIENTACOES:
        raise ImportacaoSeedInvalida(
            f"{caminho}:{linha}: tese {codigo} tem orientacao={orientacao!r} "
            f"inválida — esperado um de {ORIENTACOES} ou null."
        )

    normalizado = {
        "codigo": codigo,
        "titulo": titulo,
        "descricao": descricao,
        "area_juridica": area,
        "orientacao": orientacao,
        "status_validacao": status,
    }
    for campo in _CAMPOS_TEXTO:
        valor = registro.get(campo)
        normalizado[campo] = str(valor).strip() if valor not in (None, "") else None
    for campo in _CAMPOS_LISTA:
        valor = registro.get(campo)
        normalizado[campo] = valor if isinstance(valor, list) else []
    return normalizado


def _termos_titulo(titulo: str) -> frozenset[str]:
    return frozenset(extrair_termos(titulo))


def _titulos_similares(a: frozenset[str], b: frozenset[str]) -> bool:
    if len(a) < 2 or len(b) < 2:
        return False
    intersecao = len(a & b)
    menor = min(len(a), len(b))
    return menor > 0 and (intersecao / menor) >= _LIMIAR_SIMILARIDADE_TITULO


async def importar_theses_master(
    db, caminho: Optional[str | Path] = None, *, user_id: Optional[str] = None,
) -> dict:
    """Pipeline normalizar → validar → dedup → persistir do lote estático.

    Idempotente: rodar de novo com o mesmo arquivo devolve `importados: 0`.
    Dedup em duas camadas — código exato (rápido, cobre a idempotência) e
    similaridade de termos do título dentro da mesma área (cobre a mesma
    tese candidata com fraseado diferente, inclusive contra teses legadas já
    existentes na base). Uma linha que dá dedup é apenas contada, nunca vira
    UPDATE — texto já editado por humano nunca é sobrescrito por este módulo.
    """
    caminho_path = Path(caminho) if caminho else CAMINHO_PADRAO
    if not caminho_path.exists():
        raise FileNotFoundError(f"Arquivo de seed não encontrado: {caminho_path}")

    brutos = _ler_registros(caminho_path)
    normalizados = [
        _validar_registro(r, linha=i, caminho=caminho_path)
        for i, r in enumerate(brutos, start=1)
    ]

    vistos_codigo: set[str] = set()
    unicos = []
    duplicados_no_arquivo = 0
    for reg in normalizados:
        if reg["codigo"] in vistos_codigo:
            duplicados_no_arquivo += 1
            continue
        vistos_codigo.add(reg["codigo"])
        unicos.append(reg)

    existentes = (
        await db.execute(select(Tese.codigo, Tese.titulo, Tese.area_juridica))
    ).all()
    codigos_existentes = {row.codigo for row in existentes if row.codigo}
    termos_existentes = [
        (row.area_juridica or "", _termos_titulo(row.titulo or ""))
        for row in existentes
    ]

    importados = 0
    ja_existentes = 0
    codigos_criados: list[str] = []

    for reg in unicos:
        if reg["codigo"] in codigos_existentes:
            ja_existentes += 1
            continue

        termos_novo = _termos_titulo(reg["titulo"])
        duplicado_por_similaridade = any(
            area == reg["area_juridica"] and _titulos_similares(termos_novo, termos_existente)
            for area, termos_existente in termos_existentes
        )
        if duplicado_por_similaridade:
            ja_existentes += 1
            continue

        tese = Tese(
            id=str(uuid4()),
            titulo=reg["titulo"],
            descricao=reg["descricao"],
            area_juridica=reg["area_juridica"],
            orientacao=reg["orientacao"],
            codigo=reg["codigo"],
            status_validacao=reg["status_validacao"],
            tipo=TeseTipo.escritorio,
            # rascunho, não ativa: tese ainda "descoberta" (sem fonte
            # conferida) não deve entrar na varredura tese→caso nem em
            # sugestão automática — só o ciclo de validação humana promove.
            status=TeseStatus.rascunho,
            fundamentacao=reg["fundamentacao"],
            jurisprudencia=reg["jurisprudencia"],
            contra_argumento=reg["contra_argumento"],
            pressupostos=reg["pressupostos"],
            excecoes=reg["excecoes"],
            estrategia=reg["estrategia"],
            instancia=reg["instancia"],
            procedimento=reg["procedimento"],
            parte_favorecida=reg["parte_favorecida"],
            tribunal=reg["tribunal"],
            magistrado=reg["magistrado"],
            tags=reg["tags"],
            observacoes=reg["observacoes"],
            requisitos=reg["requisitos"],
            provas_necessarias=reg["provas_necessarias"],
            riscos=reg["riscos"],
            fontes=reg["fontes"],
            versao=1,
        )
        db.add(tese)
        codigos_existentes.add(reg["codigo"])
        termos_existentes.append((reg["area_juridica"], termos_novo))
        codigos_criados.append(reg["codigo"])
        importados += 1

    if importados:
        await criar_audit_log(
            db, user_id, "sistema",
            acao="SEED_LOTE_TESES_CANDIDATAS", entidade="teses", registro_id=None,
            detalhes=(
                f"{importados} teses candidatas importadas de "
                f"{caminho_path.name} (status_validacao=descoberta): "
                f"{', '.join(codigos_criados)}."
            ),
        )

    await db.commit()

    return {
        "lidos": len(brutos),
        "duplicados_no_arquivo": duplicados_no_arquivo,
        "importados": importados,
        "ja_existentes": ja_existentes,
        "codigos_criados": codigos_criados,
    }
