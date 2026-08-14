#!/usr/bin/env python3
"""Edição cirúrgica da Fase 3 em CasoDetalhe.tsx (Fase 3 / QA).

Mudanças:
1. Remove as functions locais TabTesesSugeridas, TabJurisprudencia e a
   interface TesesSugeridasResp (consolidadas em TabTeses/TabIndicadoresJuridicos).
2. Remove também a function local TabLista — substituída pelos componentes
   extraídos TabTeses (usava TabLista internamente) e TabIndicadoresJuridicos.
3. Ajusta o switch renderTab: teses→TabTeses, indicadores→TabIndicadoresJuridicos.
   Removem os cases: teses-sugeridas, jurisprudencia, precedentes, score, risco,
   iaDefensive (agora embutido em TabFerramentas).
4. Atualiza os imports: adiciona TabTeses e TabIndicadoresJuridicos.
"""
import sys

p = "frontend/src/pages/CasoDetalhe.tsx"
s = open(p).read()

# ── 1. Remover bloco: interface TesesSugeridasResp + TabTesesSugeridas +
#    TabJurisprudencia (consolidadas em TabTeses/TabIndicadoresJuridicos).
#    O TabLista permanece — ainda é usado pelos cases contratos/procurações/etc.
# TabJurisprudencia vem antes do TabLista; TesesSugeridasResp/TabTesesSugeridas
# vêm depois. Remover os dois blocos separadamente.
anc1 = "function TabJurisprudencia({ caseId, caso }: { caseId: string; caso: Case }) {"
end1 = s.find("// ── Tab genérico: lista simples")
i1 = s.find(anc1)
assert i1 > 0 and end1 > i1, (i1, end1)
s = s[:i1] + s[end1:]

anc2 = "interface TesesSugeridasResp {"
end2 = s.find("// Fase 1 — \"Dados do caso\" numa linha recolhível")
i2 = s.find(anc2)
assert i2 > 0 and end2 > i2, (i2, end2)
s = s[:i2] + s[end2:]

# ── 3. Remover cases do switch (teses, teses-sugeridas, jurisprudencia,
#    precedentes, score, risco, iaDefensive) ──────────────────────────────────
def remove_case(caso):
    global s
    marker = f'case "{caso}":'
    idx = s.find(marker)
    assert idx > 0, f"case {caso!r} não encontrado"
    # o case termina no próximo "case " no mesmo nível de indentação
    head = s[:idx]
    tail = s[idx + len(marker):]
    m = re.search(r"\n      case \"", tail)
    if m:
        tail = tail[m.start():]
    else:
        m = re.search(r"\n      default:", tail)
        tail = tail[m.start():] if m else tail
    s = head + tail

cases_remover = ["teses-sugeridas", "jurisprudencia", "precedentes",
                 "score", "risco", "iaDefensiva"]
import re
for c in cases_remover:
    remove_case(c)

# ── case "teses" → usar TabTeses extraído ────────────────────────────────────
# localizar bloco do case teses até o próximo case
marker = 'case "teses":'
idx = s.find(marker)
assert idx > 0
head = s[:idx]
tail = s[idx + len(marker):]
m = re.search(r"\n      case \"", tail)
rest = tail[m.start():] if m else tail
novo = (
    'case "teses":\n'
    '        return <TabTeses caso={caso} />;'
)
s = head + novo + rest

# ── case "ferramentas" → manter (TabFerramentas já embute IaDefensivaCaso) ──

# ── 4. imports ──────────────────────────────────────────────────────────────
imp_novo = (
    'import TabTeses from "./CasoDetalhe/TabTeses";\n'
    'import TabIndicadoresJuridicos from "./CasoDetalhe/TabIndicadoresJuridicos";\n'
)
# inserir após o import do TabResumo
ancora = 'import TabResumo, { AvisoCasoEncerrado } from "./CasoDetalhe/TabResumo";\n'
s = s.replace(
    'import TabResumo, { AvisoCasoEncerrado } from "./CasoDetalhe/TabResumo";\n',
    'import TabResumo, { AvisoCasoEncerrado } from "./CasoDetalhe/TabResumo";\n'
    + imp_novo,
    1,
)

# remover imports de componentes agora não usados (MotorTeses continua usado?
# TabTeses o usa — remover de CasoDetalhe)
for impr in ["MotorTeses", "MatrizRisco", "BadgesAlerta", "CalculadoraAcordo",
             "AnaliseEstrategica"]:
    s = re.sub(r'^import ' + impr + r' from "[^"]+";\n', "", s, flags=re.M)
# ContextualAIAssistant permanece (é usado no layout).

open(p, "w").write(s)
print("OK")
