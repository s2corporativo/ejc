#!/usr/bin/env python
# ── scripts/reconciliar_djen_amostra.py ──────────────────────────────────────
# Issue #572 — ferramental de reconciliação da captura DJEN por amostragem
# independente. Lê SOMENTE o banco do EJC (djen_comunicacoes) e devolve, para
# uma OAB e uma janela temporal dadas, a contagem e os identificadores que o
# EJC capturou. NÃO consulta o DJEN/CNJ de forma alguma — o lado oficial da
# comparação é manual, feito por operador humano autorizado, no portal
# Comunica (https://comunica.pje.jus.br) ou equivalente do CNJ, conforme
# `RUNBOOK_RECONCILIACAO_DJEN.md`.
#
# Este script PREPARA a reconciliação; não a executa nem a certifica. Ver o
# runbook para o procedimento completo, o limiar de alerta e o escalonamento.
#
# Execução (container ejc_backend, na VPS, ou localmente com DATABASE_URL
# configurada):
#     docker exec -it ejc_backend python -m scripts.reconciliar_djen_amostra \
#         --oab-numero 123456 --oab-uf MG
#     docker exec -it ejc_backend python -m scripts.reconciliar_djen_amostra \
#         --oab-numero 123456 --oab-uf MG --dias 14 --formato json
#
# Saída: um bloco de detalhe (uso do operador, no terminal) e um bloco de
# evidência MINIMIZADA (OAB mascarada, sem número de processo, pronto para
# colar no registro/incidente) — a contagem oficial e a divergência ficam em
# branco, para o operador preencher após a consulta manual ao DJEN.
from __future__ import annotations

import argparse
import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, timedelta

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.djen import DjenComunicacao
from app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("ejc.reconciliar_djen_amostra")


@dataclass(slots=True)
class ItemCapturado:
    id_interno: str
    comunicacao_id_externo: str
    numero_processo: str | None
    tribunal: str | None
    tipo_comunicacao: str | None
    data_disponibilizacao: str | None
    processada: bool


def _mascarar_oab(numero: str) -> str:
    """Mascara o número da OAB para evidência (mantém 1º e último dígito)."""
    n = (numero or "").strip()
    if len(n) <= 2:
        return "*" * len(n)
    return n[0] + "*" * (len(n) - 2) + n[-1]


async def _localizar_advogado(oab_numero: str, oab_uf: str) -> tuple[str, str] | None:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                # O modelo expõe o nome como `full_name`; `User.name` não existe
                # e levantava AttributeError em TODA execução — a reconciliação
                # do RUNBOOK nunca chegou a rodar de fato.
                select(User.id, User.full_name).where(
                    User.djen_oab_numero == oab_numero.strip(),
                    User.djen_oab_uf == oab_uf.strip().upper(),
                )
            )
        ).first()
        return (row[0], row[1]) if row else None


async def _capturados_no_periodo(
    advogado_id: str, data_inicio: date, data_fim: date
) -> list[ItemCapturado]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(DjenComunicacao)
                .where(
                    DjenComunicacao.advogado_id == advogado_id,
                    DjenComunicacao.data_disponibilizacao >= data_inicio,
                    DjenComunicacao.data_disponibilizacao <= data_fim,
                )
                .order_by(DjenComunicacao.data_disponibilizacao)
            )
        ).scalars().all()
    return [
        ItemCapturado(
            id_interno=c.id,
            comunicacao_id_externo=c.comunicacao_id_externo,
            numero_processo=c.numero_processo,
            tribunal=c.tribunal,
            tipo_comunicacao=c.tipo_comunicacao,
            data_disponibilizacao=(
                c.data_disponibilizacao.isoformat() if c.data_disponibilizacao else None
            ),
            processada=bool(c.processada),
        )
        for c in rows
    ]


def _imprimir_evidencia_minimizada(
    oab_numero: str, oab_uf: str, advogado_id: str, data_inicio: date, data_fim: date, total: int
) -> None:
    print()
    print("=" * 72)
    print("EVIDÊNCIA MINIMIZADA — colar no registro/incidente (RUNBOOK_RECONCILIACAO_DJEN.md)")
    print("=" * 72)
    print(f"data_checagem:       {date.today().isoformat()}")
    print(f"janela:              {data_inicio.isoformat()} a {data_fim.isoformat()}")
    print(f"oab_mascarada:       {_mascarar_oab(oab_numero)}/{oab_uf.upper()}")
    print(f"identificador_interno_advogado: {advogado_id}")
    print(f"contagem_ejc:        {total}")
    print("contagem_oficial_djen: <preencher após consulta manual ao portal DJEN/CNJ>")
    print("divergencia:         <preencher: contagem_oficial_djen - contagem_ejc>")
    print("identificadores_ausentes_no_ejc: <preencher, se houver, SEM colar texto da intimação>")
    print("responsavel:         <nome/matrícula de quem executou a consulta manual>")
    print("acao:                <nenhuma | incidente aberto (#issue) | escalonado>")
    print("=" * 72)
    print(
        "Lembrete: NÃO copiar número de processo, texto de intimação ou dado pessoal para "
        "fora deste ambiente controlado. A tabela de identificadores acima do bloco de "
        "evidência é só para conferência do operador nesta sessão de terminal."
    )
    print()


async def executar(oab_numero: str, oab_uf: str, dias: int, formato: str) -> None:
    localizado = await _localizar_advogado(oab_numero, oab_uf)
    if not localizado:
        logger.error(
            "Nenhum advogado com OAB %s/%s cadastrado em users.djen_oab_numero/uf. "
            "Cadastro de OAB é pré-requisito (ver docs/auditoria/plano-lancamento-v3.md, "
            "Bloco 6) — script não pode reconciliar quem não está monitorado.",
            oab_numero,
            oab_uf.upper(),
        )
        return
    advogado_id, nome = localizado

    data_fim = date.today()
    data_inicio = data_fim - timedelta(days=max(dias - 1, 0))

    itens = await _capturados_no_periodo(advogado_id, data_inicio, data_fim)

    if formato == "json":
        print(json.dumps(
            {
                "advogado": nome,
                "advogado_id": advogado_id,
                "janela": {"inicio": data_inicio.isoformat(), "fim": data_fim.isoformat()},
                "total_capturado_ejc": len(itens),
                "itens": [asdict(i) for i in itens],
            },
            indent=2,
            ensure_ascii=False,
        ))
    else:
        logger.info(
            "Advogado: %s (id=%s) — janela %s a %s — %d comunicação(ões) capturada(s) pelo EJC",
            nome,
            advogado_id,
            data_inicio.isoformat(),
            data_fim.isoformat(),
            len(itens),
        )
        for item in itens:
            logger.info(
                "  %s | proc=%s | trib=%s | tipo=%s | data=%s | processada=%s",
                item.comunicacao_id_externo,
                item.numero_processo,
                item.tribunal,
                item.tipo_comunicacao,
                item.data_disponibilizacao,
                item.processada,
            )

    _imprimir_evidencia_minimizada(oab_numero, oab_uf, advogado_id, data_inicio, data_fim, len(itens))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Amostra read-only da captura DJEN do EJC, para reconciliação manual com o "
            "portal oficial (Issue #572). Não consulta o DJEN/CNJ."
        )
    )
    parser.add_argument("--oab-numero", required=True, help="Número da OAB monitorada (só dígitos).")
    parser.add_argument("--oab-uf", required=True, help="UF da OAB monitorada (ex.: MG).")
    parser.add_argument(
        "--dias", type=int, default=7,
        help="Tamanho da janela em dias, terminando hoje (default: 7).",
    )
    parser.add_argument(
        "--formato", choices=["table", "json"], default="table",
        help="Formato da listagem detalhada (default: table/log).",
    )
    return parser


if __name__ == "__main__":
    args = _build_parser().parse_args()
    asyncio.run(executar(args.oab_numero, args.oab_uf, args.dias, args.formato))
