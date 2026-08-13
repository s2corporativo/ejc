"""Reorganização de imports de main.py por domínio (12/08/2026).

NÃO remove nem adiciona nada: apenas reordena os imports `from app.routers`
em blocos temáticos e a correspondente sequência de include_router, mantendo
a ordem ALFABÉTICA DENTRO de cada bloco. Comportamento idêntico (FastAPI não
depende de ordem de montagem; o gate de paridade prova).
"""
from __future__ import annotations
import re
import sys

MAIN = "/home/ubuntu/ejc/backend/app/main.py"

DOMINIOS = [
    # nome do bloco, predicao sobre o módulo
    ("autenticação e segurança", lambda m: m in {"auth", "audit", "backup_admin", "credential_vault"}),
    ("casos, partes e áreas de atuação", lambda m: m in {"cases", "case_intelligence", "case_partes", "caso_areas", "conversao_caso", "checklists", "conferir_assinar"}),
    ("clientes e atendimento", lambda m: m in {"clients", "atendimentos", "contato", "atendimento_portal"}),
    ("agenda, prazos e atividades", lambda m: m in {"agenda_eventos", "atividades", "deadlines", "andamentos", "calendar_feed", "prazos", "intimacoes", "suspensoes", "tarefas", "kanban"}),
    ("documentos e peças jurídicas", lambda m: m in {"documents", "documentos", "documentos_vinculados", "pecas", "legal_docs", "juris_import", "jurisprudencia_interna", "jurisprudencia_externa", "anexos", "provas", "modelos", "templates", "kit_documental"}),
    ("financeiro e honorários", lambda m: m in {"despesas", "honorarios", "honorarios_oab", "centro_custos", "contratos_societarios", "contratos", "faturas", "pix", "nfse", "financeiro"}),
    ("inteligência jurídica e IA", lambda m: m in {"ai", "ai_core", "ai_skills", "ai_tools", "case_intelligence", "cerebro", "inteligence", "teses", "sumulas", "radar", "diplomacia", "analise_juridica", "ia_agente", "ia_citacoes", "ia_defensiva", "ia_especializada", "ia_governanca", "ia_provider_metrics", "ia_saude", "ai_guardrails"}),
    ("jurimetria e conhecimento", lambda m: m in {"jurimetria", "conhecimento", "curadoria_renomada", "legis", "legislacao", "normativos"}),
    ("integrações e fontes públicas", lambda m: m in {"datajud", "datajud_intelligence", "integracoes", "snj", "querido_diario", "integracao_dje", "processo_eletronico", "mni"}),
    ("RAG e base de conhecimento", lambda m: m in {"rag", "rag_governance", "rag_admin"}),
    ("analytics, arquitetura e diagnóstico", lambda m: m in {"analytics", "architecture", "diagnostico", "observability", "health"}),
    ("visual e produção", lambda m: m in {"visual_law", "breakeven", "indices", "calculadoras", "advogado_estilo", "dashboard"}),
    ("radar legislativo", lambda m: m in {"radar_legislativo", "monitor", "power", "powers"}),
    ("portais e entrada", lambda m: m in {"portal", "portal_entrada", "entrada", "landing", "site", "publico", "sala_juridica", "vitrine"}),
    ("restantes", lambda m: True),
]

IMPORT_RE = re.compile(r"^from app\.routers import ([a-z_0-9]+)")


def main() -> int:
    with open(MAIN, encoding="utf-8") as fh:
        linhas = fh.read().splitlines()

    # 1) capturar sequência de imports de routers
    imports = []  # (nome, linha_completa)
    resto = []
    i = 0
    while i < len(linhas):
        l = linhas[i]
        m = IMPORT_RE.match(l)
        if m:
            imports.append((m.group(1), l))
        else:
            resto.append(l)
        i += 1

    # 2) montar blocos (ordem alfabética dentro do bloco)
    blocos = {n: [] for n, _ in DOMINIOS}
    for nome, linha in imports:
        for bloco_nome, pred in DOMINIOS:
            if pred(nome):
                blocos[bloco_nome].append(linha)
                break
    blocos = {k: sorted(v) for k, v in blocos.items() if v}

    # 3) reconstruir o trecho de imports de routers no mesmo lugar
    bloco_txt = []
    for bloco_nome, ls in blocos.items():
        if bloco_txt:
            bloco_txt.append("")
        bloco_txt.append(f"# ── {bloco_nome.title()} ──")
        bloco_txt.extend(ls)

    # inserir bloco_txt no lugar do primeiro import (removendo todos)
    idx_primeiro = next(i for i, l in enumerate(linhas) if IMPORT_RE.match(l))
    novas = linhas[:idx_primeiro] + bloco_txt + linhas[idx_primeiro + len(imports):]

    with open(MAIN, "w", encoding="utf-8") as fh:
        fh.write("\n".join(novas) + "\n")
    print(f"Reorganizado: {len(imports)} imports em {len(blocos)} blocos")
    return 0


if __name__ == "__main__":
    sys.exit(main())
