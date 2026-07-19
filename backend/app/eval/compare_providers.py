#!/usr/bin/env python3
"""Compara provedores de IA sobre o mesmo contexto RAG.

Fallbacks são registrados, mas nunca entram nas métricas do provedor solicitado.
O comparador não altera o roteamento de produção e não habilita provider algum.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ResultadoProvider:
    caso_id: str
    provider_pedido: str
    provider_real: str = ""
    modelo: str = ""
    fallback: bool = False
    citacoes_total: int = 0
    citacoes_nao_confirmadas: int = 0
    groundedness: float | None = None
    custo_brl: float = 0.0
    duracao_ms: int = 0
    erro: str | None = None


def carregar_gold(path: str) -> list[dict[str, Any]]:
    casos: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as fh:
        for numero, linha in enumerate(fh, 1):
            linha = linha.strip()
            if not linha or linha.startswith("#"):
                continue
            try:
                caso = json.loads(linha)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSON inválido na linha {numero}: {exc}") from exc
            if not caso.get("id") or not caso.get("query"):
                raise ValueError(f"Linha {numero}: id e query são obrigatórios")
            casos.append(caso)
    return casos


async def groundedness_judge(query: str, resposta: str, contexto: str) -> float | None:
    try:
        from app.services import ai_gateway
        r = await ai_gateway.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Avalie quanto a RESPOSTA está sustentada pelo CONTEXTO. "
                        "Responda somente um número entre 0 e 1."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"PERGUNTA:\n{query[:1500]}\n\n"
                        f"CONTEXTO:\n{contexto[:7000]}\n\n"
                        f"RESPOSTA:\n{resposta[:4000]}"
                    ),
                },
            ],
            task_type="resumo",
            temperature=0.0,
            max_tokens=8,
            nivel_inteligencia="padrao",
        )
        import re
        match = re.search(r"[01](?:[.,]\d+)?", r.texto or "")
        if not match:
            return None
        valor = float(match.group(0).replace(",", "."))
        return round(min(1.0, max(0.0, valor)), 3)
    except Exception:
        return None


async def avaliar_provider(db, caso, chunks, provider: str, usar_judge: bool) -> ResultadoProvider:
    from app.services import ai_gateway

    resultado = ResultadoProvider(caso_id=str(caso["id"]), provider_pedido=provider)
    contexto = "\n\n---\n\n".join(
        f"Trecho {idx + 1}:\n{chunk.get('conteudo') or ''}"
        for idx, chunk in enumerate(chunks)
    )
    try:
        resposta = await ai_gateway.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "Você é analista jurídico sênior. Responda somente com base "
                        "no conhecimento recuperado e não invente citações.\n\n"
                        f"CONHECIMENTO RECUPERADO:\n{contexto}"
                    ),
                },
                {"role": "user", "content": str(caso["query"])},
            ],
            task_type="analise_juridica",
            provider_override=provider,
            nivel_inteligencia="alto",
        )
        resultado.provider_real = resposta.provedor
        resultado.modelo = resposta.modelo
        resultado.fallback = resposta.provedor != provider
        resultado.custo_brl = round(float(resposta.custo_estimado_brl or 0), 6)
        resultado.duracao_ms = int(resposta.duracao_ms or 0)

        try:
            from app.services.citation_check import verificar_citacoes
            citacoes = await verificar_citacoes(db, resposta.texto or "")
            if isinstance(citacoes, dict):
                resultado.citacoes_total = int(citacoes.get("total") or 0)
                resultado.citacoes_nao_confirmadas = int(citacoes.get("nao_encontradas") or 0)
        except Exception:
            pass

        if usar_judge:
            resultado.groundedness = await groundedness_judge(
                str(caso["query"]), resposta.texto or "", contexto
            )
    except Exception as exc:
        resultado.erro = f"{type(exc).__name__}: {str(exc)[:240]}"
    return resultado


def agregar(resultados: list[ResultadoProvider]) -> dict[str, dict[str, Any]]:
    por_provider: dict[str, list[ResultadoProvider]] = {}
    for resultado in resultados:
        por_provider.setdefault(resultado.provider_pedido, []).append(resultado)

    agregado: dict[str, dict[str, Any]] = {}
    for provider, itens in por_provider.items():
        erros = [item for item in itens if item.erro]
        fallbacks = [item for item in itens if not item.erro and item.fallback]
        validos = [item for item in itens if not item.erro and not item.fallback]
        cit_total = sum(item.citacoes_total for item in validos)
        cit_ruins = sum(item.citacoes_nao_confirmadas for item in validos)
        grounded = [item.groundedness for item in validos if item.groundedness is not None]
        agregado[provider] = {
            "n_validos": len(validos),
            "fallbacks_excluidos": len(fallbacks),
            "erros": len(erros),
            "taxa_citacoes_nao_confirmadas": round(cit_ruins / cit_total, 4) if cit_total else None,
            "groundedness_media": round(sum(grounded) / len(grounded), 4) if grounded else None,
            "custo_total_brl": round(sum(item.custo_brl for item in validos), 6),
            "duracao_media_ms": (
                int(sum(item.duracao_ms for item in validos) / len(validos))
                if validos else 0
            ),
        }
    return agregado


async def executar(args) -> int:
    from app.core.database import AsyncSessionLocal
    from app.services import ai_service
    from app.services.ai.provider_registry import PROVIDERS_SUPORTADOS

    providers = [p.strip().lower() for p in args.providers.split(",") if p.strip()]
    desconhecidos = [p for p in providers if p not in PROVIDERS_SUPORTADOS]
    if desconhecidos:
        print(f"Providers desconhecidos: {', '.join(desconhecidos)}", file=sys.stderr)
        return 2

    casos = carregar_gold(args.gold)
    resultados: list[ResultadoProvider] = []
    async with AsyncSessionLocal() as db:
        for caso in casos:
            chunks = await ai_service.buscar_contexto_rag(
                db,
                str(caso["query"]),
                limite=args.k,
                categorias=caso.get("categorias") or None,
            )
            for provider in providers:
                item = await avaliar_provider(db, caso, chunks, provider, args.judge)
                resultados.append(item)
                estado = f"FALLBACK→{item.provider_real}" if item.fallback else item.erro or "OK"
                print(
                    f"[{caso['id']}] {provider}: {estado}; "
                    f"citações={item.citacoes_nao_confirmadas}/{item.citacoes_total}; "
                    f"ground={item.groundedness}; custo=R${item.custo_brl}; {item.duracao_ms}ms"
                )

    saida = {
        "providers": providers,
        "casos": len(casos),
        "agregado": agregar(resultados),
        "resultados": [asdict(item) for item in resultados],
        "regra_fallback": "fallbacks são excluídos das métricas do provider pedido",
    }
    print(json.dumps(saida["agregado"], ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps(saida, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Comparação controlada de provedores")
    parser.add_argument("--gold", default="app/eval/gold_set.example.jsonl")
    parser.add_argument("--providers", required=True, help="CSV: anthropic,maritaca")
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--judge", action="store_true")
    parser.add_argument("--out")
    raise SystemExit(asyncio.run(executar(parser.parse_args())))


if __name__ == "__main__":
    main()
