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
const premium = readFileSync(
  resolve(ROOT, "src/styles/ejc-dashboard-premium.css"),
  "utf8",
);

describe("EJC Identidade Premium DPT — contrato visual canônico", () => {
  it("mantém a marca institucional grande na sidebar sem alterar a navegação canônica", () => {
    expect(layout).toContain('md:w-[17rem]');
    expect(layout).toContain('md:left-[17rem]');
    expect(layout).toContain('z-[60]');
    expect(layout).toContain('md:z-40');
    expect(layout).toContain('ejc-sidebar-brand__logo');
    expect(layout).toContain('selectCanonicalMainNavigation');
    expect(layout).toContain('officeName');
    expect(layout).toContain('ejc-sidebar-epigraph');
    expect(layout).not.toContain('md:w-[15.5rem]');
    expect(layout).not.toContain('SidebarWeekCalendar');
  });

  it("reproduz a composição da referência premium no início", () => {
    expect(dashboard).toContain('ejc-dash__greeting');
    expect(dashboard).toContain('ejc-dash__entry');
    expect(dashboard).toContain('Entrada Única');
    expect(dashboard).toContain('<EntradaInteligente embedded />');
    expect(dashboard).toContain('ejc-dash__stats');
    expect(dashboard).toContain('Prazos hoje');
    expect(dashboard).toContain('Clientes ativos');
    expect(dashboard).toContain('Casos em andamento');
    expect(dashboard).toContain('Documentos recentes');
    expect(dashboard).toContain('Agenda e Prazos');
    expect(dashboard).toContain('Casos em destaque');
    expect(dashboard).toContain('Acesso rápido');
    expect(dashboard).toContain('Minha rotina hoje');
    expect(dashboard).toContain('/brand/dashboard-themis.jpg');
  });

  it("fixa a paleta Esmeralda & Ouro da referência no tema final", () => {
    expect(theme).toContain('--ejc-petroleum: #0c3a2d');
    expect(theme).toContain('--ejc-ice: #f5f4ef');
    expect(theme).toContain('--ejc-gold: #cfa961');
    expect(theme).toContain('linear-gradient(180deg, #0b3d30 0%, #01201b 100%)');
    // Referência DPT: item ativo da sidebar em OURO TRANSLÚCIDO (não sólido),
    // com filete interno dourado — gradiente canônico fixado em contrato.
    expect(theme).toContain('rgba(201, 155, 59, 0.46) 0%');
    expect(theme).toContain('rgba(201, 155, 59, 0.3) 100%');
    expect(premium).toContain('--ejc-dash-green: #0a4132');
    expect(premium).toContain('--ejc-dash-gold: #cfa961');
    expect(premium).toContain('"Playfair Display", Georgia, "Times New Roman", serif');
    expect(premium).toContain('@media (max-width: 767px)');
    expect(premium).toContain('@media (prefers-reduced-motion: reduce)');
  });

  it("alimenta o início com endpoints reais e degrada para traço, nunca zero falso", () => {
    expect(dashboard).toContain('"/dashboard/"');
    expect(dashboard).toContain('"/atividades"');
    expect(dashboard).toContain('"/cases/"');
    expect(dashboard).toContain('"/documents/"');
    expect(dashboard).toContain('"/tasks/"');
    expect(dashboard).toContain('valorOuTraco');
    expect(dashboard).toContain("Promise.allSettled");
  });
});
