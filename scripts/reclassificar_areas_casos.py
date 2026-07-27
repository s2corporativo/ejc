#!/usr/bin/env python3
"""Reclassificação CURADA da área dos casos históricos do EJC.

    ⚠ EXIGE BACKUP PRÉVIO. Rode `scripts/backup.sh` (ou o procedimento de
    RUNBOOK_BACKUP.md / RUNBOOK_ROTINA_BACKUP_DIARIA_GDRIVE.md) ANTES de
    qualquer execução com --aplicar. Regra crítica do repositório: nenhuma
    operação de escrita em massa sem backup verificado.

    ⚠ SIMULAÇÃO É O PADRÃO. Sem --aplicar este script NÃO escreve nada.

Contexto: até o commit b073d5f o frontend achatava a área do caso (o hub
Bancário gravava `civil`, imobiliário e trânsito idem, `digital_lgpd` virava
`empresarial` e `administrativo` virava `tributario`). Casos novos já nascem
certos; os históricos não. Reclassificar o histórico é decisão do escritório —
este script existe para que, quando decidirem, seja um comando e não um projeto.

NÃO é um UPDATE cego: a área correta não é dedutível de `cases.area`. A decisão
vem do registro especializado vinculado e está isolada, sem banco, em
`scripts/reclassificacao_areas.py` (leia a docstring de lá: é onde mora o
critério). Aqui ficam só conexão, transação, relatório e rollback.

Ordem obrigatória (ver RUNBOOK_RECLASSIFICACAO_AREAS.md):
    backup → simulação → conferência humana da amostra → aplicar → verificar

Exemplos:
    # 1) simulação (não escreve nada)
    python3 scripts/reclassificar_areas_casos.py

    # 2) aplicar, com confirmação interativa e arquivo de rollback
    python3 scripts/reclassificar_areas_casos.py --aplicar --confirmo-producao

    # 3) desfazer exatamente o que foi aplicado
    python3 scripts/reclassificar_areas_casos.py \\
        --reverter var/reclassificacao/rollback_20260727T120000Z.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote, urlparse

_AQUI = Path(__file__).resolve().parent
if str(_AQUI) not in sys.path:
    sys.path.insert(0, str(_AQUI))

from reclassificacao_areas import (  # noqa: E402
    DE_ACHATAMENTO,
    ALVOS_COM_SINAL,
    CasoBruto,
    Decisao,
    Nivel,
    classificar,
    resumir,
    selecionar_para_aplicar,
)

log = logging.getLogger("reclassificar_areas")

FRASE_CONFIRMACAO = "RECLASSIFICAR"
HOSTS_LOCAIS = {"localhost", "127.0.0.1", "::1", "db", "postgres"}
DIR_PADRAO = Path("var/reclassificacao")


# ── SQL ──────────────────────────────────────────────────────────────────────
# Só leitura. `area::text` porque `cases.area` é o enum nativo `casearea`.
SQL_TOTAIS = """
SELECT area::text AS area, count(*) AS n
  FROM cases
 WHERE deleted_at IS NULL
 GROUP BY 1
 ORDER BY 2 DESC
"""

SQL_CANDIDATOS = """
SELECT
  c.id,
  c.area::text AS area,
  c.titulo,
  EXISTS (SELECT 1 FROM bancario_cases s
           WHERE s.case_id = c.id AND s.deleted_at IS NULL) AS tem_bancario,
  EXISTS (SELECT 1 FROM civel_cases s
           WHERE s.case_id = c.id AND s.deleted_at IS NULL) AS tem_civel,
  EXISTS (SELECT 1 FROM empresarial_cases s
           WHERE s.case_id = c.id AND s.deleted_at IS NULL) AS tem_empresarial,
  EXISTS (SELECT 1 FROM penal_cases s
           WHERE s.case_id = c.id AND s.deleted_at IS NULL) AS tem_penal,
  EXISTS (SELECT 1 FROM trabalhista_cases s
           WHERE s.case_id = c.id AND s.deleted_at IS NULL) AS tem_trabalhista,
  COALESCE((SELECT array_agg(DISTINCT s.tipo) FROM admin_cases s
             WHERE s.case_id = c.id AND s.deleted_at IS NULL), '{}') AS admin_tipos,
  (SELECT count(*) FROM bank_analyses b
    WHERE b.case_id = c.id AND b.deleted_at IS NULL) AS qtd_analises,
  COALESCE((SELECT array_agg(a.area) FROM caso_areas a
             WHERE a.case_id = c.id AND a.principal), '{}') AS areas_principais
 FROM cases c
WHERE c.deleted_at IS NULL
  AND c.area::text = ANY(%(areas)s)
ORDER BY c.id
"""

# Guarda `area::text = %(de)s`: se alguém já mudou a área entre a simulação e a
# aplicação, o UPDATE não pega a linha (rowcount 0) em vez de sobrescrever.
SQL_UPDATE_AREA = """
UPDATE cases
   SET area = %(para)s::casearea, updated_at = now()
 WHERE id = %(case_id)s
   AND area::text = %(de)s
   AND deleted_at IS NULL
"""

SQL_AUDIT = """
INSERT INTO audit_logs
  (id, user_id, user_role, ip, acao, entidade, registro_id,
   dados_antes, dados_depois, detalhes, created_at)
VALUES
  (%(id)s, NULL, %(user_role)s, NULL, 'UPDATE', 'cases', %(case_id)s,
   %(antes)s, %(depois)s, %(detalhes)s, now())
"""


# ── Conexão ──────────────────────────────────────────────────────────────────
def resolver_url(cli_url: str | None) -> str:
    """Mesma fonte que o resto do projeto: DATABASE_URL_SYNC (Alembic)."""
    url = cli_url or os.environ.get("DATABASE_URL_SYNC")
    if not url:
        raise SystemExit(
            "DATABASE_URL_SYNC não definida. Exporte a variável (mesma que o "
            "Alembic usa) ou passe --database-url."
        )
    # SQLAlchemy aceita postgresql+psycopg2://; psycopg2 puro, não.
    return url.replace("postgresql+psycopg2://", "postgresql://", 1)


def descrever_banco(url: str) -> str:
    """host:porta/banco — nunca usuário nem senha (não vai para log/arquivo)."""
    p = urlparse(url)
    return f"{p.hostname or '?'}:{p.port or 5432}/{unquote((p.path or '').lstrip('/')) or '?'}"


def parece_producao(url: str) -> tuple[bool, str]:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    banco = unquote((p.path or "").lstrip("/")).lower()
    if os.environ.get("APP_ENV", "").lower() == "production":
        return True, "APP_ENV=production"
    if host and host not in HOSTS_LOCAIS:
        return True, f"host remoto '{host}'"
    for marca in ("prod", "producao", "production"):
        if marca in banco:
            return True, f"nome do banco contém '{marca}'"
    return False, ""


def conectar(url: str):
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError as e:  # pragma: no cover - ambiente sem driver
        raise SystemExit(
            "psycopg2 não instalado. Rode dentro do container backend ou "
            "`pip install -r backend/requirements.txt`."
        ) from e
    return psycopg2.connect(url)


# ── Leitura ──────────────────────────────────────────────────────────────────
def carregar_totais(conn) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(SQL_TOTAIS)
        return {linha[0]: linha[1] for linha in cur.fetchall()}


def carregar_candidatos(conn, *, incluir_titulo: bool) -> list[CasoBruto]:
    areas = sorted(DE_ACHATAMENTO)
    with conn.cursor() as cur:
        cur.execute(SQL_CANDIDATOS, {"areas": areas})
        colunas = [c[0] for c in cur.description]
        linhas = [dict(zip(colunas, linha)) for linha in cur.fetchall()]
    return [
        CasoBruto(
            case_id=str(r["id"]),
            area=str(r["area"]),
            titulo=(r.get("titulo") if incluir_titulo else None),
            tem_bancario_esp=bool(r["tem_bancario"]),
            tem_civel_esp=bool(r["tem_civel"]),
            tem_empresarial_esp=bool(r["tem_empresarial"]),
            tem_penal_esp=bool(r["tem_penal"]),
            tem_trabalhista_esp=bool(r["tem_trabalhista"]),
            admin_tipos=tuple(x for x in (r["admin_tipos"] or ()) if x),
            qtd_analises_bancarias=int(r["qtd_analises"] or 0),
            areas_principais_declaradas=tuple(
                x for x in (r["areas_principais"] or ()) if x
            ),
        )
        for r in linhas
    ]


# ── Relatório ────────────────────────────────────────────────────────────────
def _linha(texto: str = "") -> None:
    print(texto)


def imprimir_relatorio(
    totais: dict[str, int],
    decisoes: Sequence[Decisao],
    *,
    amostra: int,
    incluir_titulo: bool,
) -> None:
    resumo = resumir(decisoes)

    _linha("=" * 74)
    _linha("RECLASSIFICAÇÃO DE ÁREA — SIMULAÇÃO (nenhuma escrita)")
    _linha("=" * 74)

    _linha("\n1) CASOS POR ÁREA ATUAL (todos os casos ativos)")
    for area, n in sorted(totais.items(), key=lambda kv: -kv[1]):
        marca = "  ← área achatada" if area in DE_ACHATAMENTO else ""
        _linha(f"   {area:<16} {n:>7}{marca}")
    _linha(f"   {'TOTAL':<16} {sum(totais.values()):>7}")

    _linha(f"\n2) CANDIDATOS EXAMINADOS: {resumo.total_analisado}")
    _linha("   (só casos nas áreas achatadas: " + ", ".join(sorted(DE_ACHATAMENTO)) + ")")

    _linha("\n3) DISTRIBUIÇÃO POR NÍVEL DE CONFIANÇA")
    rotulo = {
        Nivel.ALTA:       "alta       (elegível a --aplicar)",
        Nivel.MEDIA:      "media      (só revisão humana)",
        Nivel.AMBIGUA:    "ambigua    (só revisão humana)",
        Nivel.SEM_SINAL:  "sem_sinal  (indistinguível por dado)",
        Nivel.CONFIRMADO: "confirmado (área atual correta — não mexer)",
    }
    for nivel in Nivel.ORDEM:
        n = resumo.por_nivel.get(nivel, 0)
        if n:
            _linha(f"   {rotulo[nivel]:<45} {n:>7}")

    _linha("\n4) RECLASSIFICAÇÕES PROPOSTAS (área atual → área nova)")
    if not resumo.por_transicao:
        _linha("   nenhuma.")
    for (de, para), n in sorted(resumo.por_transicao.items()):
        _linha(f"   {de:<14} → {para:<16} {n:>7}")
    _linha(f"\n   ELEGÍVEIS A --aplicar (nível alta): {resumo.total_elegivel}")

    _linha("\n5) POR REGRA")
    for regra, n in sorted(resumo.por_regra.items(), key=lambda kv: (-kv[1], kv[0])):
        _linha(f"   {regra:<40} {n:>7}")

    if incluir_titulo:
        _linha(
            "\n   ⚠ --incluir-titulo ATIVO: as amostras abaixo contêm TÍTULO DE "
            "CASO,\n     ou seja, dado do escritório. Não cole esta saída fora "
            "de canal interno."
        )

    def _amostra(titulo: str, itens: Sequence[Decisao]) -> None:
        _linha(f"\n{titulo} ({len(itens)} no total, mostrando até {amostra})")
        if not itens:
            _linha("   nenhum.")
            return
        for d in itens[:amostra]:
            destino = d.area_nova or "— (sem destino automático)"
            _linha(f"   {d.case_id}  {d.area_atual} → {destino}")
            _linha(f"      regra: {d.regra}")
            _linha(f"      evidência: {d.evidencia}")
            if d.titulo:
                _linha(f"      título: {d.titulo}")

    _amostra("6) AMOSTRA — ELEGÍVEIS (confira ANTES de aplicar)", resumo.elegiveis)
    _amostra("7) AMOSTRA — REVISÃO HUMANA OBRIGATÓRIA (media/ambigua)", resumo.revisar)

    sem_sinal = resumo.por_nivel.get(Nivel.SEM_SINAL, 0)
    _linha("\n8) O QUE ESTE SCRIPT NÃO CONSEGUE DECIDIR")
    _linha(
        f"   {sem_sinal} caso(s) sem nenhum sinal. Não são listados um a um de\n"
        "   propósito: não há evidência para conferir. Um caso 'civil' sem\n"
        "   satélite é indistinguível de imobiliário ou de trânsito, e um\n"
        "   'empresarial' sem satélite é indistinguível de digital_lgpd —\n"
        "   esses três hubs criam caso simples, sem tabela especializada, e o\n"
        "   ROPA da LGPD é por cliente, não por caso."
    )
    _linha(
        "   Alvos com sinal disponível: " + ", ".join(sorted(ALVOS_COM_SINAL)) + "."
    )
    _linha(
        "   Alvos SEM sinal (só decisão humana, caso a caso): "
        + ", ".join(sorted(
            set(a for alvos in DE_ACHATAMENTO.values() for a in alvos) - ALVOS_COM_SINAL
        ))
        + "."
    )
    _linha("\n" + "=" * 74)


# ── Arquivo de rollback ──────────────────────────────────────────────────────
def _agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def gravar_rollback(caminho: Path, payload: dict[str, Any]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    tmp = caminho.with_suffix(caminho.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    tmp.replace(caminho)


def _registrar_auditoria(cur, case_id: str, de: str, para: str, detalhes: str) -> None:
    cur.execute(SQL_AUDIT, {
        "id": str(uuid.uuid4()),
        "user_role": "script",
        "case_id": case_id,
        "antes": json.dumps({"area": de}),
        "depois": json.dumps({"area": para}),
        "detalhes": detalhes,
    })


# ── Aplicação ────────────────────────────────────────────────────────────────
def aplicar(
    conn,
    decisoes: Sequence[Decisao],
    *,
    caminho_rollback: Path,
    banco: str,
    backup_declarado: str,
    lote: int,
) -> dict[str, Any]:
    """Grava o rollback ANTES de tocar em qualquer linha, e só então aplica."""
    payload: dict[str, Any] = {
        "versao": 1,
        "tipo": "reclassificacao_area_cases",
        "gerado_em": _agora(),
        "banco": banco,
        "backup_declarado": backup_declarado,
        "status": "planejado",
        "itens": [
            {
                "case_id": d.case_id,
                "area_anterior": d.area_atual,
                "area_nova": d.area_nova,
                "regra": d.regra,
                "evidencia": d.evidencia,
                "aplicado_em": None,
            }
            for d in decisoes
        ],
    }
    gravar_rollback(caminho_rollback, payload)
    log.info("Plano de rollback gravado em %s (%d itens)",
             caminho_rollback, len(payload["itens"]))

    aplicados = ignorados = 0
    with conn.cursor() as cur:
        for i, item in enumerate(payload["itens"], start=1):
            cur.execute(SQL_UPDATE_AREA, {
                "case_id": item["case_id"],
                "de": item["area_anterior"],
                "para": item["area_nova"],
            })
            if cur.rowcount == 1:
                _registrar_auditoria(
                    cur, item["case_id"], item["area_anterior"], item["area_nova"],
                    f"reclassificar_areas_casos.py: {item['regra']}",
                )
                item["aplicado_em"] = _agora()
                aplicados += 1
            else:
                # Área já mudou desde a simulação → não sobrescreve.
                item["ignorado"] = "area_atual_divergente_ou_caso_ausente"
                ignorados += 1
            if i % lote == 0:
                conn.commit()
                log.info("Commit de lote — %d/%d processados", i, len(payload["itens"]))
    conn.commit()

    payload["status"] = "aplicado"
    payload["concluido_em"] = _agora()
    payload["aplicados"] = aplicados
    payload["ignorados"] = ignorados
    gravar_rollback(caminho_rollback, payload)
    return payload


def ler_rollback(caminho: Path) -> dict[str, Any]:
    try:
        payload = json.loads(caminho.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"Arquivo de rollback não encontrado: {caminho}") from None
    except json.JSONDecodeError as e:
        raise SystemExit(f"Arquivo de rollback ilegível ({caminho}): {e}") from None
    if payload.get("tipo") != "reclassificacao_area_cases":
        raise SystemExit(f"{caminho} não é um arquivo de rollback deste script.")
    return payload


def reverter(conn, caminho: Path, payload: dict[str, Any], *, lote: int) -> dict[str, Any]:
    itens = [i for i in payload.get("itens", []) if i.get("area_anterior") and i.get("area_nova")]

    revertidos = ignorados = 0
    with conn.cursor() as cur:
        for i, item in enumerate(itens, start=1):
            # Guarda invertida: só volta o que está EXATAMENTE na área nova.
            cur.execute(SQL_UPDATE_AREA, {
                "case_id": item["case_id"],
                "de": item["area_nova"],
                "para": item["area_anterior"],
            })
            if cur.rowcount == 1:
                _registrar_auditoria(
                    cur, item["case_id"], item["area_nova"], item["area_anterior"],
                    f"reclassificar_areas_casos.py --reverter {caminho.name}",
                )
                item["revertido_em"] = _agora()
                revertidos += 1
            else:
                ignorados += 1
            if i % lote == 0:
                conn.commit()
    conn.commit()

    payload["status"] = "revertido"
    payload["revertido_em"] = _agora()
    payload["revertidos"] = revertidos
    gravar_rollback(caminho, payload)
    log.info("Revertidos %d; ignorados %d (já estavam na área anterior).",
             revertidos, ignorados)
    return payload


# ── Confirmação ──────────────────────────────────────────────────────────────
def confirmar_interativo(quantidade: int, banco: str) -> bool:
    print(
        f"\nVocê está prestes a ALTERAR a área de {quantidade} caso(s) em {banco}.\n"
        "Confirme que o backup foi feito e que a amostra da simulação foi\n"
        f"conferida por um humano. Digite {FRASE_CONFIRMACAO} para prosseguir: ",
        end="",
    )
    try:
        return input().strip() == FRASE_CONFIRMACAO
    except (EOFError, KeyboardInterrupt):
        return False


# ── CLI ──────────────────────────────────────────────────────────────────────
def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="reclassificar_areas_casos.py",
        description=(
            "Reclassifica a área de casos históricos achatados pelo frontend "
            "antigo. SIMULA por padrão — só escreve com --aplicar. "
            "EXIGE BACKUP PRÉVIO (scripts/backup.sh / RUNBOOK_BACKUP.md): é "
            "escrita em massa na tabela cases. Procedimento completo em "
            "RUNBOOK_RECLASSIFICACAO_AREAS.md."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--aplicar", action="store_true",
                   help="ESCREVE no banco. Sem esta flag o script só relata.")
    p.add_argument("--confirmo-producao", action="store_true",
                   help="Autoriza rodar contra um banco que parece de produção.")
    p.add_argument("--sem-interacao", action="store_true",
                   help="Pula a confirmação digitada. Exige --confirmo-backup.")
    p.add_argument("--confirmo-backup", metavar="REF",
                   help="Referência do backup já verificado (arquivo/ID). "
                        "Vai para o log e para o arquivo de rollback.")
    p.add_argument("--limite", type=int, metavar="N",
                   help="Aplica no máximo N casos (os demais ficam para depois).")
    p.add_argument("--lote", type=int, default=200, metavar="N",
                   help="Commit a cada N casos (padrão: 200).")
    p.add_argument("--amostra", type=int, default=10, metavar="N",
                   help="Quantos exemplos mostrar por bloco (padrão: 10).")
    p.add_argument("--incluir-titulo", action="store_true",
                   help="Inclui o título do caso na amostra. ATENÇÃO: a saída "
                        "passa a conter dado do escritório.")
    p.add_argument("--saida-rollback", type=Path, metavar="ARQ",
                   help=f"Arquivo de rollback (padrão: {DIR_PADRAO}/rollback_<ts>.json).")
    p.add_argument("--reverter", type=Path, metavar="ARQ",
                   help="Restaura exatamente as áreas gravadas neste arquivo.")
    p.add_argument("--database-url", metavar="URL",
                   help="Sobrepõe DATABASE_URL_SYNC (ex.: cópia restaurada).")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    if args.reverter and args.aplicar:
        raise SystemExit("--reverter e --aplicar são mutuamente exclusivos.")
    if args.sem_interacao and not args.confirmo_backup:
        raise SystemExit(
            "--sem-interacao exige --confirmo-backup REF (referência do backup "
            "verificado). Sem backup não se aplica."
        )
    if args.lote < 1:
        raise SystemExit("--lote deve ser >= 1.")

    # Valida o arquivo ANTES de abrir conexão: erro de digitação não deve
    # sequer chegar ao banco.
    plano = ler_rollback(args.reverter) if args.reverter else None

    url = resolver_url(args.database_url)
    banco = descrever_banco(url)
    prod, motivo = parece_producao(url)
    escreve = bool(args.aplicar or args.reverter)
    if prod and escreve and not args.confirmo_producao:
        raise SystemExit(
            f"Banco {banco} parece PRODUÇÃO ({motivo}) e a operação escreve. "
            "Faça o backup, confira a simulação e repita com --confirmo-producao."
        )
    if prod:
        log.warning("Banco %s parece produção (%s).", banco, motivo)
    log.info("Banco alvo: %s | modo: %s", banco,
             "REVERTER" if args.reverter else ("APLICAR" if args.aplicar else "SIMULAÇÃO"))

    try:
        conn = conectar(url)
    except Exception as e:
        # Falha de conexão é o erro mais comum de quem opera o script; traceback
        # cru só atrapalha. Nada foi escrito — a conexão nem chegou a abrir.
        log.error("Não foi possível conectar ao banco (%s): %s",
                  banco, str(e).strip().splitlines()[0])
        log.error("Confira DATABASE_URL_SYNC (ou --database-url). "
                  "NADA foi alterado.")
        return 2

    try:
        if plano is not None:
            if not args.sem_interacao and not confirmar_interativo(
                len(plano.get("itens", [])), banco
            ):
                log.warning("Reversão cancelada — nada foi alterado.")
                return 1
            reverter(conn, args.reverter, plano, lote=args.lote)
            return 0

        totais = carregar_totais(conn)
        casos = carregar_candidatos(conn, incluir_titulo=args.incluir_titulo)
        decisoes = classificar(casos)
        imprimir_relatorio(
            totais, decisoes, amostra=args.amostra,
            incluir_titulo=args.incluir_titulo,
        )
        print(
            "\nAUDITORIA: cada reclassificação aplicada grava uma linha em "
            "audit_logs\n(acao=UPDATE, entidade=cases, user_role='script', "
            "user_id NULL — o helper\ncriar_audit_log() é async e depende do "
            "contexto de request, então o script\ninsere direto na tabela). O "
            "arquivo de rollback é o segundo registro."
        )

        if not args.aplicar:
            print(
                "\nSIMULAÇÃO — NADA FOI ESCRITO.\n"
                "Para aplicar: backup → conferir a amostra do bloco 6 com um "
                "advogado →\nrodar de novo com --aplicar."
            )
            return 0

        alvo = selecionar_para_aplicar(decisoes, args.limite)
        if not alvo:
            log.info("Nenhum caso elegível (nível alta). Nada a aplicar.")
            return 0
        if not args.sem_interacao and not confirmar_interativo(len(alvo), banco):
            log.warning("Confirmação não recebida — NADA foi alterado.")
            return 1

        caminho = args.saida_rollback or (
            DIR_PADRAO / f"rollback_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
        )
        resultado = aplicar(
            conn, alvo, caminho_rollback=caminho, banco=banco,
            backup_declarado=args.confirmo_backup or "(confirmado interativamente)",
            lote=args.lote,
        )
        print(
            f"\nAPLICADO: {resultado['aplicados']} caso(s); "
            f"{resultado['ignorados']} ignorado(s).\n"
            f"Rollback: {caminho}  ← GUARDE ESTE ARQUIVO.\n"
            f"Para desfazer: python3 {Path(__file__).name} --reverter {caminho}"
        )
        return 0
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
