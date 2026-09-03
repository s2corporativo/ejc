#!/usr/bin/env python3
"""Governança do gold set jurídico real do EJC.

Este módulo NÃO cria gabarito jurídico e NÃO transforma caso sintético em
certificação. Ele valida a evidência mínima exigida para que um caso humano
curado possa contar como gold:

- pseudonimização/LGPD;
- payload efetivamente avaliável;
- curador identificado (revisor opcional, pode ser o mesmo);
- datas explícitas de revisão e conferência de vigência;
- ao menos uma fonte oficial HTTPS com referência da versão revisada;
- ausência de placeholders/fonte fictícia;
- cobertura explícita de cenários normais, de fronteira e de exceção.

A validação é offline e determinística: o CI confere a PROVENIÊNCIA declarada,
não tenta substituir a revisão humana consultando a Internet.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

# Fontes institucionais brasileiras típicas. O sufixo é deliberadamente
# conservador; fonte fora da lista precisa ser incorporada de forma explícita,
# não aceita silenciosamente pelo CI.
_SUFFIXES_OFICIAIS = (
    ".gov.br",
    ".jus.br",
    ".leg.br",
    ".mp.br",
    ".def.br",
)
_HOSTS_OFICIAIS = {
    "planalto.gov.br",
    "www.planalto.gov.br",
    "oab.org.br",
    "www.oab.org.br",
}
_PLACEHOLDERS = (
    "ficticia",
    "fictícia",
    "ficticio",
    "fictício",
    "placeholder",
    "[informar]",
    "exemplo apenas",
    "sumula-ficticia",
    "súmula-fictícia",
)
_CENARIOS = {"normal", "fronteira", "excecao"}
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass
class AuditoriaGold:
    arquivos_reais: int = 0
    casos_reais: int = 0
    # Propostas ainda NÃO atestadas por humano (status="candidato"). Contadas à
    # parte de propósito: candidato nunca vira cobertura.
    casos_candidatos: int = 0
    por_area: dict[str, int] = field(default_factory=dict)
    por_cenario: dict[str, int] = field(default_factory=dict)
    erros: list[str] = field(default_factory=list)

    @property
    def pronto(self) -> bool:
        return self.arquivos_reais > 0 and self.casos_reais > 0 and not self.erros


def _data_iso(valor: object, campo: str, erros: list[str]) -> date | None:
    try:
        d = date.fromisoformat(str(valor or ""))
    except ValueError:
        erros.append(f"{campo}: use data ISO YYYY-MM-DD")
        return None
    if d > date.today():
        erros.append(f"{campo}: data futura não é evidência de revisão")
    return d


def _host_oficial(url: str) -> bool:
    try:
        p = urlparse(url)
    except Exception:
        return False
    host = (p.hostname or "").lower().rstrip(".")
    if p.scheme != "https" or not host:
        return False
    return host in _HOSTS_OFICIAIS or any(host.endswith(s) for s in _SUFFIXES_OFICIAIS)


def _validador_pii() -> Callable[[str], list[str]]:
    """Carrega o sanitizer obrigatório; a ausência deve bloquear o gold set."""
    from app.services.sanitizer import validar_sem_pii

    return validar_sem_pii


def _pii(caso: dict) -> list[str]:
    """Valida todo o payload versionado e falha fechado sem sanitizer."""
    try:
        validar_sem_pii = _validador_pii()
    except Exception:
        return ["validação de PII indisponível: sanitizer obrigatório não carregou"]

    try:
        payload = json.dumps(caso, ensure_ascii=False, sort_keys=True, default=str)
        tipos = validar_sem_pii(payload)
    except Exception:
        return ["validação de PII indisponível: sanitizer falhou ao validar o payload"]

    if not tipos:
        return []
    return [
        "PII detectada no payload versionado: "
        + ", ".join(sorted(set(map(str, tipos))))
    ]


def _lista_textual_nao_vazia(valor: object) -> bool:
    return bool(
        isinstance(valor, list)
        and any(isinstance(item, str) and item.strip() for item in valor)
    )


def _validar_payload_avaliavel(caso: dict) -> list[str]:
    """Impede metadados de curadoria sem conteúdo de avaliação de contar no gate."""
    erros: list[str] = []
    query = str(caso.get("query") or "").strip()
    fatos = str(caso.get("fatos") or "").strip()

    if query:
        if not _lista_textual_nao_vazia(caso.get("expected_titulos")):
            erros.append(
                "gold RAG exige expected_titulos não vazio para medir retrieval"
            )
        return erros

    if fatos:
        if not str(caso.get("tipo_peca_esperado") or "").strip():
            erros.append("gold de peças exige tipo_peca_esperado")
        if not _lista_textual_nao_vazia(caso.get("teses_esperadas")):
            erros.append("gold de peças exige teses_esperadas não vazio")
        if not _lista_textual_nao_vazia(caso.get("criterios")):
            erros.append("gold de peças exige criterios objetivos não vazios")
        return erros

    return ["caso real precisa de query (RAG) ou fatos (peças) para ser avaliável"]


def _validar_placeholders(caso: dict) -> list[str]:
    erros: list[str] = []
    for campo in ("expected_citacoes", "jurisprudencia_esperada"):
        valores = caso.get(campo) or []
        if not isinstance(valores, list):
            erros.append(f"{campo} deve ser lista quando informado")
            continue
        for valor in valores:
            norm = str(valor).casefold()
            if any(p in norm for p in _PLACEHOLDERS):
                erros.append(
                    f"{campo} contém placeholder/fonte fictícia: {valor!r}"
                )
    return erros


def validar_caso_real(caso: dict) -> list[str]:
    """Valida um caso que pretende contar como gold jurídico humano-curado."""
    erros: list[str] = []
    if caso.get("ficticio") is not False:
        erros.append("ficticio deve ser false para caso gold real")

    area = str(caso.get("area") or "").strip().lower()
    if not area:
        erros.append("area é obrigatória")

    cenario = str(caso.get("cenario") or "").strip().lower()
    if cenario not in _CENARIOS:
        erros.append("cenario deve ser normal, fronteira ou excecao")

    erros.extend(_validar_payload_avaliavel(caso))

    curadoria = caso.get("curadoria")
    if not isinstance(curadoria, dict):
        return erros + [
            "curadoria deve ser objeto com curador, datas e fontes_oficiais"
        ]

    curador = str(curadoria.get("curador") or "").strip()
    if not curador:
        erros.append("curadoria.curador é obrigatório")
    # `revisor` é opcional e pode coincidir com o curador. A exigência de duas
    # identidades distintas foi removida por decisão do titular em 23/08/2026:
    # o escritório opera hoje com um único jurista, e a regra tornava o gate
    # impossível de satisfazer em vez de elevar a qualidade. Quando houver
    # segundo par de olhos, registre-o aqui — o campo continua sendo lido.

    revisado = _data_iso(
        curadoria.get("revisado_em"), "curadoria.revisado_em", erros
    )
    vigencia = _data_iso(
        curadoria.get("vigencia_conferida_em"),
        "curadoria.vigencia_conferida_em",
        erros,
    )
    if revisado and vigencia and vigencia > revisado:
        erros.append("vigencia_conferida_em não pode ser posterior a revisado_em")

    fontes = curadoria.get("fontes_oficiais")
    if not isinstance(fontes, list) or not fontes:
        erros.append("curadoria.fontes_oficiais deve ser lista não vazia")
    else:
        for idx, fonte in enumerate(fontes, 1):
            prefixo = f"curadoria.fontes_oficiais[{idx}]"
            if not isinstance(fonte, dict):
                erros.append(f"{prefixo}: deve ser objeto")
                continue
            titulo = str(fonte.get("titulo") or "").strip()
            url = str(fonte.get("url") or "").strip()
            if not titulo:
                erros.append(f"{prefixo}.titulo é obrigatório")
            if not _host_oficial(url):
                erros.append(
                    f"{prefixo}.url deve ser HTTPS de domínio oficial reconhecido"
                )

            consultada = _data_iso(
                fonte.get("consultada_em"), f"{prefixo}.consultada_em", erros
            )
            if revisado and consultada and consultada > revisado:
                erros.append(
                    f"{prefixo}.consultada_em não pode ser posterior a revisado_em"
                )

            identificador = str(
                fonte.get("identificador_versao") or ""
            ).strip()
            hash_sha256 = str(fonte.get("hash_sha256") or "").strip()
            if not identificador and not hash_sha256:
                erros.append(
                    f"{prefixo}: informe identificador_versao ou hash_sha256 "
                    "para reconstruir a versão jurídica revisada"
                )
            if hash_sha256 and not _SHA256.fullmatch(hash_sha256):
                erros.append(f"{prefixo}.hash_sha256 deve ter 64 caracteres hex")

    erros.extend(_validar_placeholders(caso))
    erros.extend(_pii(caso))
    return erros


def _carregar_jsonl(path: Path) -> tuple[list[tuple[int, dict]], list[str]]:
    """Carrega objetos preservando a linha física original do JSONL."""
    casos: list[tuple[int, dict]] = []
    erros: list[str] = []
    for n, linha in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        linha = linha.strip()
        if not linha or linha.startswith("#"):
            continue
        try:
            valor = json.loads(linha)
        except json.JSONDecodeError as exc:
            erros.append(f"{path.name}:{n}: JSON inválido: {exc}")
            continue
        if not isinstance(valor, dict):
            erros.append(f"{path.name}:{n}: cada linha deve ser objeto JSON")
            continue
        casos.append((n, valor))
    return casos, erros


def _e_candidato(caso: dict) -> bool:
    """Caso proposto para o gold set, ainda sem atestação humana.

    A marca é explícita (`status: "candidato"`) e vem acompanhada de
    `atestado_por: null` — nenhum heurístico adivinha isso.
    """
    return str(caso.get("status") or "").strip().lower() == "candidato"


def auditar_diretorio(base: str | os.PathLike[str]) -> AuditoriaGold:
    """Audita gold sets reais; exemplos/templates não contam como cobertura."""
    raiz = Path(base)
    out = AuditoriaGold()
    ids: dict[str, tuple[Path, int]] = {}

    for path in sorted(raiz.glob("gold_set*.jsonl")):
        nome = path.name.lower()
        if ".example." in nome or ".synthetic." in nome or ".sintetico." in nome:
            continue
        casos, erros_arquivo = _carregar_jsonl(path)
        out.erros.extend(erros_arquivo)
        # CANDIDATO ≠ ATESTADO (I7, 03/09/2026). Caso marcado
        # `status: "candidato"` é proposta de gold set — ainda sem curador,
        # fonte oficial conferida nem vigência. Ele NÃO conta como cobertura
        # jurídica e NÃO é medido pela régua de proveniência: contá-lo seria
        # transformar rascunho de máquina em certificação humana.
        candidatos = [c for _, c in casos if _e_candidato(c)]
        out.casos_candidatos += len(candidatos)
        casos = [(n, c) for n, c in casos if not _e_candidato(c)]
        if not casos and not erros_arquivo:
            continue
        out.arquivos_reais += 1

        for linha, caso in casos:
            # Cenários agênticos são outro benchmark, não gold jurídico material.
            if "intencao" in caso and "query" not in caso and "fatos" not in caso:
                continue

            cid = str(caso.get("id") or "").strip()
            prefixo = f"{path.name}:{linha} ({cid or '?'})"
            errs: list[str] = []

            if not cid:
                errs.append("id é obrigatório")
            elif cid in ids:
                primeira_path, primeira_linha = ids[cid]
                errs.append(
                    "id duplicado; primeira ocorrência em "
                    f"{primeira_path.name}:{primeira_linha}"
                )
            else:
                ids[cid] = (path, linha)

            errs.extend(validar_caso_real(caso))
            out.erros.extend(f"{prefixo}: {e}" for e in errs)
            if not errs:
                out.casos_reais += 1
                area = str(caso.get("area") or "").strip().lower()
                cenario = str(caso.get("cenario") or "").strip().lower()
                out.por_area[area] = out.por_area.get(area, 0) + 1
                out.por_cenario[cenario] = out.por_cenario.get(cenario, 0) + 1
    return out


def avaliar_prontidao(
    audit: AuditoriaGold,
    *,
    areas: list[str] | None = None,
    min_casos_area: int = 0,
    min_total: int = 0,
    cenarios: list[str] | None = None,
    min_casos_cenario: int = 0,
) -> list[str]:
    erros = list(audit.erros)
    if audit.casos_reais < min_total:
        erros.append(
            f"casos reais válidos={audit.casos_reais} < mínimo total={min_total}"
        )
    for area in areas or []:
        n = audit.por_area.get(area.strip().lower(), 0)
        if n < min_casos_area:
            erros.append(f"área {area}: {n} caso(s) < mínimo {min_casos_area}")
    for cenario in cenarios or []:
        chave = cenario.strip().lower()
        if chave not in _CENARIOS:
            erros.append(f"cenário obrigatório desconhecido: {cenario}")
            continue
        n = audit.por_cenario.get(chave, 0)
        if n < min_casos_cenario:
            erros.append(
                f"cenário {cenario}: {n} caso(s) < mínimo {min_casos_cenario}"
            )
    return erros


def main() -> None:
    p = argparse.ArgumentParser(
        description="Governança do gold set jurídico real do EJC"
    )
    p.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--require-real", action="store_true")
    p.add_argument("--areas", default="")
    p.add_argument("--min-casos-area", type=int, default=0)
    p.add_argument("--min-total", type=int, default=0)
    p.add_argument("--cenarios", default="")
    p.add_argument("--min-casos-cenario", type=int, default=0)
    args = p.parse_args()

    audit = auditar_diretorio(args.dir)
    areas = [x.strip().lower() for x in args.areas.split(",") if x.strip()]
    cenarios = [x.strip().lower() for x in args.cenarios.split(",") if x.strip()]
    erros = avaliar_prontidao(
        audit,
        areas=areas,
        min_casos_area=args.min_casos_area,
        min_total=args.min_total,
        cenarios=cenarios,
        min_casos_cenario=args.min_casos_cenario,
    )
    if args.require_real and audit.casos_reais == 0:
        erros.append("nenhum gold set jurídico humano-curado disponível")

    print(
        f"gold real: arquivos={audit.arquivos_reais} "
        f"casos_válidos={audit.casos_reais} "
        f"candidatos_não_atestados={audit.casos_candidatos}"
    )
    for area, n in sorted(audit.por_area.items()):
        print(f"  área {area}: {n}")
    for cenario, n in sorted(audit.por_cenario.items()):
        print(f"  cenário {cenario}: {n}")
    if erros:
        print("GOLD GOVERNANCE: NÃO PRONTO/BLOQUEADO")
        for erro in erros:
            print(f"  - {erro}")
        raise SystemExit(1)
    if audit.casos_reais == 0:
        print("GOLD GOVERNANCE: estrutura válida, cobertura jurídica real = ZERO")
    else:
        print("GOLD GOVERNANCE: casos presentes cumprem a proveniência mínima")


if __name__ == "__main__":
    main()
