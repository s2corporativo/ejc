import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = process.cwd();
const layout = readFileSync(
  resolve(ROOT, "src/components/LayoutReference.tsx"),
  "utf8",
);
const dashboard = readFileSync(
  resolve(ROOT, "src/pages/DashboardUltra.tsx"),
  "utf8",
);
const theme = readFileSync(
  resolve(ROOT, "src/styles/ejc-reference-systemwide.css"),
  "utf8",
);

describe("EJC Petroleum & Gold — contrato visual canônico", () => {
  it("mantém a marca institucional grande na sidebar sem alterar a navegação canônica", () => {
    expect(layout).toContain('md:w-[17rem]');
    expect(layout).toContain('md:left-[17rem]');
    expect(layout).toContain('z-[60]');
    expect(layout).toContain('md:z-40');
    expect(layout).toContain('ejc-sidebar-brand__logo');
    expect(layout).toContain('selectCanonicalMainNavigation');
    expect(layout).not.toContain('md:w-[15.5rem]');
  });

  it("mantém Entrada Única e Radar Jurídico no início com a nova composição", () => {
    expect(dashboard).toContain('ejc-ai-dashboard__main-grid');
    expect(dashboard).toContain('Entrada Única');
    expect(dashboard).toContain('Radar Jurídico');
    expect(dashboard).toContain('<EntradaInteligente embedded />');
    expect(dashboard).not.toContain('style={{ width: "clamp(156px, 16vw, 220px)" }}');
  });

  it("fixa a paleta Petroleum & Gold e regras responsivas no tema final", () => {
    expect(theme).toContain('--ejc-petroleum: #485b5a');
    expect(theme).toContain('--ejc-ice: #e5eded');
    expect(theme).toContain('--ejc-gold: #c19f4b');
    expect(theme).toContain('html:not(.dark) .ejc-ai-dashboard');
    expect(theme).toContain('color: var(--ejc-petroleum-deep)');
    expect(theme).toContain('.ejc-ai-dashboard__logo');
    expect(theme).toContain('@media (max-width: 767px)');
    expect(theme).toContain('@media (prefers-reduced-motion: reduce)');
  });
});
