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
const tokens = readFileSync(resolve(ROOT, "src/styles/ejc-tokens.css"), "utf8");

function luminance(hex: string) {
  const channels = hex
    .match(/[0-9a-f]{2}/gi)!
    .map((channel) => Number.parseInt(channel, 16) / 255)
    .map((channel) =>
      channel <= 0.03928 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4,
    );

  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

function contrast(foreground: string, background: string) {
  const values = [luminance(foreground), luminance(background)].sort(
    (a, b) => b - a,
  );
  return (values[0] + 0.05) / (values[1] + 0.05);
}

describe("EJC Identidade Premium DPT — contrato visual canônico", () => {
  it("mantém a marca institucional grande na sidebar sem alterar a navegação canônica", () => {
    expect(layout).toContain('md:w-[17rem]');
    expect(layout).toContain('md:left-[17rem]');
    expect(layout).toContain('z-[60]');
    expect(layout).toContain('md:z-40');
    expect(layout).toContain('ejc-sidebar-brand__logo');
    expect(layout).toContain('selectMainNavigation');
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
    expect(theme).toContain("--ejc-petroleum: #0c3a2d");
    expect(theme).toContain("--ejc-ice: #f5f4ef");
    expect(theme).toContain("--ejc-gold: #cfa961");
    expect(theme).toContain(
      "linear-gradient(180deg, #0b3d30 0%, #01201b 100%)",
    );
    // Referência DPT: item ativo da sidebar em OURO TRANSLÚCIDO (não sólido),
    // com filete interno dourado — gradiente canônico fixado em contrato.
    expect(theme).toContain("rgba(201, 155, 59, 0.46) 0%");
    expect(theme).toContain("rgba(201, 155, 59, 0.3) 100%");
    expect(premium).toContain("--ejc-dash-green: #0a4132");
    expect(premium).toContain("--ejc-dash-gold: #cfa961");
    expect(premium).toContain(
      '"Playfair Display", Georgia, "Times New Roman", serif',
    );
    expect(premium).toContain("@media (max-width: 767px)");
    expect(premium).toContain("@media (prefers-reduced-motion: reduce)");
    // Rodapé da sidebar com panorama de Betim/MG (#1756) ancorado ao fundo
    // esmeralda da paleta canônica (sem resíduo navy do tema anterior).
    expect(premium).not.toContain("rgba(15, 39, 71");
    expect(premium).not.toContain("rgba(7, 24, 46");
    expect(premium).not.toContain("rgba(56, 189, 248");
    expect(premium).not.toContain("rgba(125, 211, 252");
    expect(premium).not.toContain("#0f2747");
    expect(premium).not.toContain("#38bdf8");
  });

  it("preserva contraste AA e foco perceptível na paleta canônica", () => {
    expect(tokens).toContain("--ejc-primary: #0a4132");
    expect(tokens).toContain("--ejc-gold-ink: #8f7117");
    expect(tokens).toContain("--ejc-background: #f5f4ef");
    expect(tokens).toContain("--ejc-text: #1d2b26");
    expect(tokens).toContain("--ejc-focus-ring: rgba(143, 113, 23, 0.65)");

    expect(contrast("#0a4132", "#ffffff")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#8f7117", "#ffffff")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#1d2b26", "#f5f4ef")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#ede6da", "#14110a")).toBeGreaterThanOrEqual(4.5);
    // Ouro sobre esmeralda (cartões institucionais) — texto grande/UI ≥ 3:1.
    expect(contrast("#cfa961", "#0a4132")).toBeGreaterThanOrEqual(3);
    expect(contrast("#eaca7f", "#04291f")).toBeGreaterThanOrEqual(3);
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
