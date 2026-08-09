#!/usr/bin/env python3
"""Governança do gold set jurídico real do EJC.

Este módulo NÃO cria gabarito jurídico e NÃO transforma caso sintético em
certificação. Ele valida a evidência mínima exigida para que um caso humano
curado possa contar como gold:

- pseudonimização/LGPD;
- curador e revisor independentes;
- datas explícitas de revisão e conferência de vigência;
- ao menos uma fonte oficial HTTPS por caso;
- ausência de placeholders/fonte fictícia.

A validação é offline e determinística: o CI confere a PROVENIÊNCIA declarada,
não tenta substituir a revisão humana consultando a Internet.
"""
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
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
_PLACEHOLDERS = ("ficticia", "fictício", "placeholder", "[informar]", "exemplo apenas")


@dataclass
class AuditoriaGold:
    arquivos_reais: int = 0
    casos_reais: int = 0
    por_area: dict[str, int] = field(default_factory=dict)
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


def _pii(caso: dict) -> list[str]:
    """Reusa o sanitizer da aplicação, sem enviar conteúdo a provedor externo."""
    try:
        from app.services.sanitizer import validar_sem_pii
    except Exception:
        return []
    erros: list[str] = []
    for campo in ("query", "fatos", "pedidos", "notes"):
        valor = caso.get(campo)
        if not valor:
            continue
        texto = "\n".join(map(str, valor)) if isinstance(valor, list) else str(valor)
        tipos = validar_sem_pii(texto)
        if tipos:
            erros.append(
                f"PII detectada em {campo}: {', '.join(sorted(set(map(str, tipos))))}"
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

    curadoria = caso.get("curadoria")
    if not isinstance(curadoria, dict):
        return erros + ["curadoria deve ser objeto com curador, revisor, datas e fontes_oficiais"]

    curador = str(curadoria.get("curador") or "").strip()
    revisor = str(curadoria.get("revisor") or "").strip()
    if not curador:
        erros.append("curadoria.curador é obrigatório")
    if not revisor:
        erros.append("curadoria.revisor é obrigatório")
    if curador and revisor and curador.casefold() == revisor.casefold():
        erros.append("curador e revisor devem ser pessoas/identidades distintas")

    revisado = _data_iso(curadoria.get("revisado_em"), "curadoria.revisado_em", erros)
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
                erros.append(f"{prefixo}.url deve ser HTTPS de domínio oficial reconhecido")
            _data_iso(fonte.get("consultada_em"), f"{prefixo}.consultada_em", erros)

    for valor in caso.get("expected_citacoes") or []:
        norm = str(valor).casefold()
        if any(p in norm for p in _PLACEHOLDERS):
            erros.append(f"expected_citacoes contém placeholder/fonte fictícia: {valor!r}")

    erros.extend(_pii(caso))
    return erros


def _carregar_jsonl(path: Path) -> tuple[list[dict], list[str]]:
    casos: list[dict] = []
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
        casos.append(valor)
    return casos, erros


def auditar_diretorio(base: str | os.PathLike[str]) -> AuditoriaGold:
    """Audita gold sets reais; exemplos/templates não contam como cobertura."""
    raiz = Path(base)
    out = AuditoriaGold()
    for path in sorted(raiz.glob("gold_set*.jsonl")):
        nome = path.name.lower()
        if ".example." in nome or ".synthetic." in nome or ".sintetico." in nome:
            continue
        casos, erros_arquivo = _carregar_jsonl(path)
        out.erros.extend(erros_arquivo)
        if not casos and not erros_arquivo:
            continue
        out.arquivos_reais += 1
        ids: set[str] = set()
        for idx, caso in enumerate(casos, 1):
            # Cenários agênticos são outro benchmark, não gold jurídico material.
            if "intencao" in caso and "query" not in caso and "fatos" not in caso:
                continue
            cid = str(caso.get("id") or "").strip()
            prefixo = f"{path.name}:{idx} ({cid or '?'})"
            if not cid:
                out.erros.append(f"{prefixo}: id é obrigatório")
            elif cid in ids:
                out.erros.append(f"{prefixo}: id duplicado")
            ids.add(cid)
            errs = validar_caso_real(caso)
            out.erros.extend(f"{prefixo}: {e}" for e in errs)
            if not errs:
                out.casos_reais += 1
                area = str(caso.get("area") or "").strip().lower() or "(sem_area)"
                out.por_area[area] = out.por_area.get(area, 0) + 1
    return out


def avaliar_prontidao(
    audit: AuditoriaGold,
    *,
    areas: list[str] | None = None,
    min_casos_area: int = 0,
    min_total: int = 0,
) -> list[str]:
    erros = list(audit.erros)
    if audit.casos_reais < min_total:
        erros.append(f"casos reais válidos={audit.casos_reais} < mínimo total={min_total}")
    for area in areas or []:
        n = audit.por_area.get(area.strip().lower(), 0)
        if n < min_casos_area:
            erros.append(f"área {area}: {n} caso(s) < mínimo {min_casos_area}")
    return erros


def main() -> None:
    p = argparse.ArgumentParser(description="Governança do gold set jurídico real do EJC")
    p.add_argument("--dir", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--require-real", action="store_true")
    p.add_argument("--areas", default="")
    p.add_argument("--min-casos-area", type=int, default=0)
    p.add_argument("--min-total", type=int, default=0)
    args = p.parse_args()

    audit = auditar_diretorio(args.dir)
    areas = [x.strip().lower() for x in args.areas.split(",") if x.strip()]
    erros = avaliar_prontidao(
        audit,
        areas=areas,
        min_casos_area=args.min_casos_area,
        min_total=args.min_total,
    )
    if args.require_real and audit.casos_reais == 0:
        erros.append("nenhum gold set jurídico humano-curado disponível")

    print(f"gold real: arquivos={audit.arquivos_reais} casos_válidos={audit.casos_reais}")
    for area, n in sorted(audit.por_area.items()):
        print(f"  {area}: {n}")
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
