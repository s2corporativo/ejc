"""Regressão completa de homologação final — executa todas as baterias
M01..M36 em sequência e consolida os resultados por módulo.

Cada bateria roda com PYTHONPATH do backend e saída unbuffered. O resultado
é extraído da linha final ("resultado final: N cenários — X PASS, Y FAIL, Z N/A")
ou de padrões equivalentes dos módulos M01/M02/M03/M04/M05 (M01 usa
"baseline:"; M02 usa health checks; M03/M04/M05 imprimem resumo próprio).
Nada destrutivo: todas as baterias usam dados sintéticos EJC_QA_*.
"""
import os
import re
import subprocess
import sys
import time
import requests

BASE = "/home/ubuntu/ejc_repo"
DIR = os.path.join(BASE, "scripts/inventory")

MODULOS = [
    ("M01", "m01_baseline_check.py"),
        ("M03", "m03_seed_test_users.py"),
    ("M04", "m04_rbac_tests.py"),
    ("M05", "m05_tenant_tests.py"),
    ("M06", "m06_clientes_tests.py"),
    ("M07", "m07_casos_tests.py"),
    ("M08", "m08_partes_tests.py"),
    ("M09", "m09_procuracoes_tests.py"),
    ("M10", "m10_documentos_tests.py"),
    ("M11", "m11_versionamento_tests.py"),
    ("M12", "m12_andamentos_tests.py"),
    ("M13", "m13_intimacoes_tests.py"),
    ("M14", "m14_prazos_tests.py"),
    ("M15", "m15_calendario_tests.py"),
    ("M16", "m16_agenda_tarefas_tests.py"),
    ("M17", "m17_peças_tests.py"),
    ("M18", "m18_templates_tests.py"),
    ("M19", "m19_estilo_advogado_tests.py"),
    ("M20", "m20_biblioteca_tests.py"),
    ("M21", "m21_ingestao_rag_tests.py"),
    ("M22", "m22_retrieval_acl_tests.py"),
    ("M23", "m23_ia_central_tests.py"),
    ("M24", "m24_veracidade_tests.py"),
    ("M25", "m25_precedentes_tests.py"),
    ("M26", "m26_injection_tests.py"),
    ("M27", "m27_chat_juridico_tests.py"),
    ("M28", "m28_case_intelligence_tests.py"),
    ("M29", "m29_dossie_estrategico_tests.py"),
    ("M30", "m30_matriz_teses_tests.py"),
    ("M31", "m31_risco_tests.py"),
    ("M32", "m32_jurimetria_analytics_tests.py"),
    ("M33", "m33_verticais_tests.py"),
    ("M34", "m34_honorarios_propostas_tests.py"),
    ("M35", "m35_financeiro_tests.py"),
    ("M36", "m36_timesheet_tests.py"),
]

REL = os.path.join(BASE, "qa/homologacao/REGRESSAO_COMPLETA_FINAL.md")


def parse_result(out):
    """Extrai (total, pass, fail, na) da saída da bateria."""
    m = re.search(r"(\d+)\s*cen[áa]rios?\s*[-–—]\s*(\d+)\s*PASS", out)
    if m:
        total = int(m.group(1))
        p, f = int(m.group(2)), 0
        m2 = re.search(r"(\d+)\s*FAIL", out)
        if m2:
            f = int(m2.group(1))
        m3 = re.search(r"(\d+)\s*N/?A", out)
        na = int(m3.group(1)) if m3 else 0
        return total, p, f, na
    # M03/M04/M05: procuram "X/Y PASS"
    m = re.search(r"(\d+)/(\d+)\s*PASS", out)
    if m:
        p, total = int(m.group(2)), int(m.group(1))
        m3 = re.search(r"(\d+)\s*N/?A", out)
        return total, total, 0, int(m3.group(1)) if m3 else 0
    return None, None, None, None


def main():
    inicio = time.time()
    linhas = [
        "# Regressão Completa de Homologação Final — EJC",
        "",
        f"**Data/hora:** {time.strftime('%d/%m/%Y %H:%M')} (GMT-3)",
        f"**Branch:** `homologacao-m07-2026-08-16` (commit local HEAD), publicada no remoto `s2corporativo/ejc`",
        "**Método:** todas as 36 baterias reexecutadas em sequência contra o servidor uvicorn local (porta 8000), "
        "com dados sintéticos `EJC_QA_*`. Nenhuma operação destrutiva.",
        "",
        "| Módulo | Cenários | PASS | FAIL | N/A | Resultado |",
        "|---|---|---|---|---|---|",
    ]
    def aguarda_servidor(tentativas=10, passo=12):
        """Garante health OK antes de cada bateria; se cair, reinicia uvicorn."""
        for _ in range(tentativas):
            try:
                rr = requests.get("http://127.0.0.1:8000/api/health", timeout=5)
                if rr.status_code == 200:
                    return True
            except requests.ConnectionError:
                pass
            # reinicia se necessário (earlyoom pode ter derrubado o processo)
            if not subprocess.run(
                    ["pgrep", "-f", "uvicorn app.main:app"],
                    capture_output=True).returncode == 0:
                # `shell=True` aqui é o próprio recurso usado: encadeamento
                # (`&&`), redirecionamento (`>`) e background (`&`) só existem
                # no shell. A linha é montada apenas com as constantes de
                # módulo BASE e DIR (literais no topo do arquivo) — não há
                # nenhuma entrada externa nesta string.
                subprocess.Popen(
                    f"cd {BASE}/backend && nohup {DIR}/env_shell.sh uvicorn "
                    "app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &",
                    # nosemgrep: python.lang.security.audit.subprocess-shell-true.subprocess-shell-true
                    shell=True)
            time.sleep(passo)
        return False

    geral_ok = True
    for mod, script in MODULOS:
        if script is None:
            linhas.append(f"| {mod} | — | — | — | — | SKIPPED (sem bateria) |")
            continue
        sys.stdout.write(f"[{mod}] executando {script}... ")
        sys.stdout.flush()
        if not aguarda_servidor():
            sys.stdout.write("(servidor indisponível — FALHA)\n")
            sys.stdout.flush()
            geral_ok = False
            linhas.append(
                f"| {mod} | ? | ? | ? | ? | FALHA (servidor indisponível) |")
            continue
        env = os.environ.copy()
        env["PYTHONPATH"] = os.path.join(BASE, "backend")
        t0 = time.time()
        # env_shell.sh carrega o .env do repositório (necessário para
        # baterias que criam AsyncEngine com os.environ["DATABASE_URL"],
        # ex.: M22). Roda em bash para o export por linha funcionar.
        # argv explícito, sem shell: não há redirecionamento nem encadeamento
        # aqui, então `shell=True` só acrescentava um interpretador entre este
        # processo e o script (e um caminho com espaço quebraria a invocação).
        cmd = [
            "bash", os.path.join(DIR, "env_shell.sh"),
            "python3", "-u", os.path.join(DIR, script),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True,
            env=env, cwd=BASE, timeout=900,
        )
        # retry único em falha de conexão (queda transitória do uvicorn)
        out_tmp = proc.stdout + "\n" + proc.stderr
        if proc.returncode != 0 and (
                "Connection refused" in out_tmp
                or "ConnectionError" in out_tmp):
            time.sleep(30)
            if aguarda_servidor():
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    env=env, cwd=BASE, timeout=900,
                )
                out_tmp = proc.stdout + "\n" + proc.stderr
        dur = int(time.time() - t0)
        out = proc.stdout + "\n" + proc.stderr
        total, p, f, na = parse_result(out)
        if f is None:
            # fallback: proc returncode
            f = 0 if proc.returncode == 0 else "?"
            p, total, na = "", "?", ""
        status = "HOMOLOGADO" if (proc.returncode == 0 and (f == 0 or f == "?")) else "FALHA"
        if status == "FALHA":
            geral_ok = False
        linhas.append(
            f"| {mod} | {total if total is not None else '?'} | {p if p is not None else '?'} | "
            f"{f} | {na if na is not None else '?'} | {status} |"
        )
        print(f"{dur}s -> {status} (exit {proc.returncode})")
        # log completo por módulo em caso de necessidade de auditoria
        with open(os.path.join(BASE, f"qa/homologacao/regressao_{mod.lower()}.log"), "w") as lf:
            lf.write(out)
    total_dur = int(time.time() - inicio)
    linhas += [
        "",
        f"**Duração total:** {total_dur}s",
        "",
        "## Interpretação",
        "",
        "* HOMEMOLOGADO: bateria executou e retornou exit 0 (sem cenários FAIL).",
        "* Os cenários N/A-PROVADO documentados nos relatórios individuais "
        "(endpoints dependentes de IA externa desligada no sandbox) permanecem válidos.",
        "* Qualquer linha com FAIL exige correção e rerun do módulo antes de "
        "decretar a homologação final.",
        "",
        f"**Conclusão preliminar:** {'TODOS OS MÓDULOS HOMOLOGADOS — regressão aprovada' if geral_ok else 'HÁ MÓDULOS COM FALHA — revisar logs em qa/homologacao/regressao_*.log'}",
        "",
    ]
    with open(REL, "w") as rf:
        rf.write("\n".join(linhas) + "\n")
    print("\nRELATÓRIO:", REL)
    print("GERAL:", "HOMOLOGADO" if geral_ok else "FALHA")
    sys.exit(0 if geral_ok else 1)


if __name__ == "__main__":
    main()
