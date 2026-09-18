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

describe("EJC DePaula Premium — contrato visual canônico", () => {
  it("mantém a logomarca DPT como elemento dominante sem alterar a navegação canônica", () => {
    expect(layout).toContain('md:w-[17rem]');
    expect(layout).toContain('md:left-[17rem]');
    expect(layout).toContain('z-[60]');
    expect(layout).toContain('md:z-40');
    expect(layout).toContain('ejc-sidebar-brand__logo');
    expect(layout).toContain('EJC DePaula Teixeira Adv');
    expect(layout).toContain('selectCanonicalMainNavigation');
    expect(layout).not.toContain('Ecossistema Jurídico Clóvis');
  });

  it("mantém Entrada Única como hero e Radar Jurídico na composição do início", () => {
    expect(dashboard).toContain('ejc-ai-dashboard__main-grid');
    expect(dashboard).toContain('ejc-ai-dashboard__welcome');
    expect(dashboard).toContain('EJC DePaula Teixeira Adv');
    expect(dashboard).toContain('Entrada Única');
    expect(dashboard).toContain('Radar Jurídico');
    expect(dashboard).toContain('<EntradaInteligente embedded />');
    expect(dashboard).not.toContain('Ecossistema Jurídico Clóvis');
  });

  it("fixa a paleta esmeralda, dourado e marfim em todo o sistema", () => {
    expect(theme).toContain('--ejc-petroleum: #073c35');
    expect(theme).toContain('--ejc-ice: #f4f1e8');
    expect(theme).toContain('--ejc-gold: #c9a24a');
    expect(theme).toContain('font-family: Georgia');
    expect(theme).toContain('.ejc-ai-dashboard__workspace--entry');
    expect(theme).toContain('html:not(.dark) .ejc-modern-scope :where(table, .table)');
    expect(theme).toContain('html:not(.dark) :where([role="dialog"], [role="menu"], .dropdown, .popover)');
    expect(theme).toContain('/* Login e Portal do Cliente — mesma identidade');
    expect(theme).toContain('.min-h-screen.bg-canvas > .brand-watermark + div');
    expect(theme).toContain('.ejc-modern-scope > header:not(.fixed)');
    expect(theme).toContain('@media (max-width: 767px)');
    expect(theme).toContain('@media (prefers-reduced-motion: reduce)');
  });
});
