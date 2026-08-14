#!/usr/bin/env python3
"""Monitoramento automático de CPU/memória do container backend durante a ingestão.

Uso (na VPS de produção):
  # Coleta a cada 5s durante 30 min e grava CSV + alertas em /tmp/monitor_ingestao/
  python3 backend/scripts/monitor_ingestao.py --duracao-min 30 --intervalo 5

  # Modo contínuo (roda até ser interrompido) com alerta por e-mail/grep:
  python3 backend/scripts/monitor_ingestao.py

  # Apenas uma coleta instantânea (diagnóstico rápido):
  python3 backend/scripts/monitor_ingestao.py --instantaneo

Integração com a ingestão (uma única linha):
  nohup python3 backend/scripts/monitor_ingestao.py > /tmp/monitor_ingestao.log 2>&1 &
  python3 backend/scripts/ingestao_biblioteca_juridica.py --execute
  kill %1

Requisitos: apenas `docker` (com acesso do usuário) e Python 3.10+.
Não instala dependências novas e não altera o compose.yml.
"""
import argparse
import csv
import os
import signal
import subprocess
import sys
import time
from datetime import datetime

CONTAINER = os.environ.get("MONITOR_CONTAINER", "ejc_backend")
OUT_DIR = os.environ.get("MONITOR_OUT_DIR", "/tmp/monitor_ingestao")
ALERTA_CPU = float(os.environ.get("ALERTA_CPU", "90"))      # % de CPU por núcleo
ALERTA_MEM = float(os.environ.get("ALERTA_MEM", "85"))      # % da memória do container
TETO_MB = int(os.environ.get("TETO_MEM_MB", "2048"))        # alerta se RES exceder
STOP_ON_KILL = os.environ.get("MONITOR_PARA_SEM_INGESTAO", "true") == "true"

rodando = True
signal.signal(signal.SIGINT, lambda *_: stop_loop())
signal.signal(signal.SIGTERM, lambda *_: stop_loop())


def stop_loop():
    global rodando
    rodando = False


def _cmd(args):
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=15).stdout
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        print(f"[monitor] erro ao executar {' '.join(args)}: {e}", file=sys.stderr)
        return ""


def docker_stats_once():
    """Retorna métricas atuais do container via `docker stats --no-stream`."""
    out = _cmd(["docker", "stats", CONTAINER, "--no-stream",
                "--format", "{{.Name}};{{.CPUPerc}};{{.MemUsage}};{{.MemPerc}};{{.NetIO}};{{.BlockIO}}"])
    linha = (out or "").strip().splitlines()[-1]
    if not linha:
        return None
    nome, cpu, mem, memperc, net, blk = [c.strip() for c in linha.split(";")]
    mem_usada, mem_total = mem.split("/")
    mem_usada_mb = _mb(mem_usada)
    mem_total_mb = _mb(mem_total)
    return {
        "cpu_pct": cpu.rstrip("%"),
        "mem_usada_mb": mem_usada_mb,
        "mem_total_mb": mem_total_mb,
        "mem_pct": memperc.rstrip("%"),
        "net": net,
        "blk": blk,
    }


def _mb(valor):
    v, u = valor.split()
    v = float(v.replace(",", "."))
    return v if u.upper() == "MiB" else v * 1024 if u.upper() == "GiB" else v / 1024


def coletar_host():
    """Métricas de memória total do host (evita OOM global)."""
    vm = _cmd(["grep", "-E", "MemTotal|MemAvailable", "/proc/meminfo"])
    tot = avl = 0.0
    for linha in vm.splitlines():
        k, v = linha.split(":")
        kb = int(v.strip().split()[0])
        if "Total" in k:
            tot = kb / 1024
        if "Available" in k:
            avl = kb / 1024
    return {"host_mem_total_mb": tot, "host_mem_usada_mb": tot - avl,
            "host_mem_pct": round((tot - avl) / tot * 100, 1) if tot else 0}


def registrar(amostra, host):
    agora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row = {"hora": agora, **amostra, **host}
    escritor.writerow(row)
    csvf.flush()
    alertas = []
    try:
        if float(amostra["cpu_pct"] or 0) > ALERTA_CPU:
            alertas.append(f"CPU {amostra['cpu_pct']}% > {ALERTA_CPU}%")
        if float(amostra["mem_pct"] or 0) > ALERTA_MEM:
            alertas.append(f"MEM {amostra['mem_pct']}% > {ALERTA_MEM}%")
        if amostra["mem_usada_mb"] > TETO_MB:
            alertas.append(f"RES {amostra['mem_usada_mb']:.0f}MB > {TETO_MB}MB")
    except (TypeError, ValueError):
        pass
    for a in alertas:
        linha_alerta = f"[ALERTA {agora}] {CONTAINER}: {a}"
        print(linha_alerta, flush=True)
        if ARQ_ALERTAS is not None:
            ARQ_ALERTAS.write(linha_alerta + "\n")
            ARQ_ALERTAS.flush()


def ingestao_ativa():
    """Heurística: há processo de ingestão rodando no backend?"""
    ps = _cmd(["docker", "exec", CONTAINER, "pgrep", "-f", "ingestao_biblioteca_juridica"])
    return bool(ps.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--duracao-min", type=int, default=0, help="0 = contínuo")
    ap.add_argument("--intervalo", type=int, default=5, help="segundos entre coletas")
    ap.add_argument("--instantaneo", action="store_true", help="uma coleta e sai")
    args = ap.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    global csvf, escritor, ARQ_ALERTAS
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    arquivo_csv = os.path.join(OUT_DIR, f"metrics_{CONTAINER}_{ts}.csv")
    arquivo_alertas = os.path.join(OUT_DIR, f"alertas_{CONTAINER}_{ts}.txt")
    campos = ["hora", "cpu_pct", "mem_usada_mb", "mem_total_mb", "mem_pct",
              "net", "blk", "host_mem_total_mb", "host_mem_usada_mb", "host_mem_pct"]
    csvf = open(arquivo_csv, "w", newline="")
    escritor = csv.DictWriter(csvf, fieldnames=campos)
    escritor.writeheader()
    ARQ_ALERTAS = open(arquivo_alertas, "w")

    print(f"[monitor] {CONTAINER} | saída: {arquivo_csv} | "
          f"alertas: CPU>{ALERTA_CPU}% MEM>{ALERTA_MEM}% RES>{TETO_MB}MB", flush=True)

    inicio = time.time()
    n = 0
    while rodando:
        n += 1
        amostra = docker_stats_once()
        if amostra is None:
            print("[monitor] container indisponível nesta coleta", flush=True)
        else:
            registrar(amostra, coletar_host())
        if args.instantaneo:
            break
        if args.duracao_min > 0 and (time.time() - inicio) >= args.duracao_min * 60:
            break
        if STOP_ON_KILL and n > 5 and not ingestao_ativa():
            print("[monitor] nenhum processo de ingestão detectado no backend — encerrando", flush=True)
            break
        time.sleep(args.intervalo)

    csvf.close()
    ARQ_ALERTAS.close()
    print(f"[monitor] concluído ({n} coletas). CSV: {arquivo_csv}")


if __name__ == "__main__":
    main()
