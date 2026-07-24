from pathlib import Path

page = Path("frontend/src/pages/SalaAnaliseJuridica.tsx")
s = page.read_text()
s = s.replace(
    'import { useCallback, useEffect, useMemo, useRef, useState } from "react";',
    'import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";',
)
s = s.replace(
    'description="Converse com a IA, anexe provas, confronte versões e transforme a análise validada em caso."',
    'subtitle="Converse com a IA, anexe provas, confronte versões e transforme a análise validada em caso."',
)
s = s.replace(
    'description="Crie uma sala para iniciar a investigação jurídica."',
    'message="Crie uma sala para iniciar a investigação jurídica."',
)
s = s.replace(
    'description="A conversa ficará vinculada ao dossiê preliminar e às provas anexadas."',
    'message="A conversa ficará vinculada ao dossiê preliminar e às provas anexadas."',
)
s = s.replace(
    '<Markdown>{message.content}</Markdown>',
    '<Markdown source={message.content} />',
)
s = s.replace("children: React.ReactNode;", "children: ReactNode;")
s = s.replace(
    "nomes_proteger: [],",
    "nomes_proteger: selected.potencial_cliente ? [selected.potencial_cliente] : [],",
)
s = s.replace(
    "const report = selected?.relatorio || {};",
    "const report: Relatorio = selected?.relatorio ?? {};",
)
s = s.replace('.replaceAll("_", " ")', '.replace(/_/g, " ")')
s = s.replace(
    '<button onClick={() => setError(null)} aria-label="Fechar">',
    '<button type="button" onClick={() => setError(null)} aria-label="Fechar">',
)
s = s.replace(
    '<button className="rounded-xl p-2 text-slate-500 hover:bg-slate-100" onClick={() => fileRef.current?.click()} title="Anexar provas">',
    '<button type="button" className="rounded-xl p-2 text-slate-500 hover:bg-slate-100" onClick={() => fileRef.current?.click()} title="Anexar provas" aria-label="Anexar provas">',
)
s = s.replace(
    'disabled={!prompt.trim() || busy}\n                    title="Enviar"',
    'disabled={!prompt.trim() || busy}\n                    title="Enviar"\n                    aria-label="Enviar mensagem"',
)
s = s.replace(
    '<button onClick={onClose}><X size={20} /></button>',
    '<button type="button" onClick={onClose} aria-label="Fechar"><X size={20} /></button>',
)
s = s.replace(
    'className={`max-h-[90vh] w-full overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl ${wide ? "max-w-3xl" : "max-w-lg"}`} onMouseDown={(e) => e.stopPropagation()}',
    'role="dialog" aria-modal="true" aria-label={title} className={`max-h-[90vh] w-full overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl ${wide ? "max-w-3xl" : "max-w-lg"}`} onMouseDown={(e) => e.stopPropagation()}',
)
page.write_text(s)

registry = Path("frontend/src/config/moduleRegistry.tsx")
r = registry.read_text()
lazy_anchor = 'const RaioXProcesso = lazy(() => import("../pages/RaioXProcesso"));'
if "const SalaAnaliseJuridica =" not in r:
    if lazy_anchor not in r:
        raise SystemExit("Âncora do lazy import não encontrada")
    r = r.replace(
        lazy_anchor,
        lazy_anchor
        + '\nconst SalaAnaliseJuridica = lazy(() => import("../pages/SalaAnaliseJuridica"));',
        1,
    )

route_anchor = '  {\n    key: "raio-x-processo",\n    path: "/raio-x",'
route = '''  {
    key: "sala-analise-juridica",
    path: "/sala-analise",
    label: "Sala de Análise Jurídica",
    description:
      "Conversa jurídica preliminar com provas, contradições, riscos e conversão validada em caso.",
    group: "Pesquisar & IA",
    icon: Sparkles,
    component: SalaAnaliseJuridica,
    roles: ROLES.juridico,
    showInNav: true,
    essential: true,
    order: 5,
    helpKey: "inteligencia",
    usesAI: true,
    sensitive: true,
    backendPrefixes: ["/api/raio-x", "/api/ai"],
  },
'''
if 'key: "sala-analise-juridica"' not in r:
    if route_anchor not in r:
        raise SystemExit("Âncora da rota Raio-X não encontrada")
    r = r.replace(route_anchor, route + route_anchor, 1)

old_start = r.find(route_anchor)
if old_start < 0:
    raise SystemExit("Bloco do Raio-X não encontrado")
old_end = r.find("\n  },", old_start)
if old_end < 0:
    raise SystemExit("Fim do bloco do Raio-X não encontrado")
old_end += len("\n  },")
old_block = r[old_start:old_end]
old_block = old_block.replace("showInNav: true", "showInNav: false", 1)
old_block = old_block.replace("essential: true", "essential: false", 1)
r = r[:old_start] + old_block + r[old_end:]
registry.write_text(r)

test = Path("frontend/src/config/moduleRegistry.test.ts")
t = test.read_text()
t = t.replace(
    'it("destaca Raio-X e Financeiro apenas para os perfis autorizados", () => {',
    'it("destaca Sala de Análise e Financeiro apenas para os perfis autorizados", () => {',
)
t = t.replace(
    'expect(advogado.find((item) => item.path === "/raio-x")?.essential).toBe(',
    'expect(\n      advogado.find((item) => item.path === "/sala-analise")?.essential,\n    ).toBe(',
)
t = t.replace('      "/raio-x",', '      "/sala-analise",')
test.write_text(t)
