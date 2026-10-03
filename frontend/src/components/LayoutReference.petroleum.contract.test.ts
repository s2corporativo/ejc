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
const tokens = readFileSync(resolve(ROOT, "src/styles/ejc-tokens.css"), "utf8");
const css = tokens;
const premium = readFileSync(
  resolve(ROOT, "src/styles/ejc-dashboard-premium.css"),
  "utf8",
);
const main = readFileSync(resolve(ROOT, "src/main.tsx"), "utf8");

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

/** Bloco de regras que abre em `sel`: percorre as chaves e devolve até o fecho. */
function bloco(sel: string) {
  const inicio = css.indexOf(sel + " {");
  const abertura = css.indexOf("{", inicio);
  let depth = 0;
  for (let i = abertura; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) return css.slice(inicio, i + 1);
    }
  }
  return "";
}

function blocoClaro() {
  return bloco("html:not(.dark)");
}

function blocoEscuro() {
  // Há `.dark { ... }` aninhado nas regras de apresentação do shell; o bloco
  // de TEMA é o primeiro que declara as variáveis de superfície.
  const candidato = bloco(".dark");
  return candidato.includes("--ejc-background") ? candidato : "";
}

describe("EJC — tema canônico neutro com acento único e ouro de marca", () => {
  it("não deixa nenhum cabeçalho de comentário com quebra de linha literal", () => {
    // Em 28/09/2026 o cabeçalho do bloco claro trazia uma barra invertida
    // seguida de "n" no lugar da quebra de linha: o comentário nunca fechou,
    // o navegador tratou TODO o tema como comentário e a paleta neutra nunca
    // existiu em produção. Qualquer cabeçalho com essa sequência reabre a
    // mesma falha (scripts/auditar-css.mjs --verificar também bloqueia).
    const cabecalhos = tokens.match(/\/\*[^]*?\*\//g) ?? [];
    for (const cabecalho of cabecalhos) {
      expect(
        cabecalho.slice(0, 3),
        "cabeçalho de comentário com barra invertida abre e nunca fecha",
      ).not.toContain("\\" + "n");
    }
    expect(blocoClaro()).toContain("--ejc-primary: #1d4ed8");
  });

  it("mantém cor e shorthand de display em tokens distintos", () => {
    const valoresDeCor = Array.from(
      tokens.matchAll(/--ejc-text-display:\s*([^;]+);/g),
      (match) => match[1].trim(),
    );
    expect(valoresDeCor).toEqual(["#101828", "#f2f4f7"]);
    expect(tokens.match(/--ejc-font-display:/g)).toHaveLength(1);
    expect(tokens).toContain(
      "--ejc-font-display: 700 clamp(26px, 2.5vw, 36px) / 1.12 var(--ejc-font-sans);",
    );
  });

  it("fixa a paleta neutra com um só acento de ação e o ouro reservado à marca", () => {
    const claro = blocoClaro();
    // Superfície e tinta
    expect(claro).toContain("--ejc-background: #f6f7f9");
    expect(claro).toContain("--ejc-surface: #ffffff");
    expect(claro).toContain("--ejc-surface-muted: #f2f4f7");
    expect(claro).toContain("--ejc-border: #e4e7ec");
    expect(claro).toContain("--ejc-text: #101828");
    expect(claro).toContain("--ejc-text-secondary: #475467");
    // Ação: azul único. Sem família azul+roxo+ciano nem gradiente no acento.
    expect(claro).toContain("--ejc-primary: #1d4ed8");
    expect(claro).toContain("--ejc-primary-soft: #eff4ff");
    expect(claro).toContain("--ejc-primary-contrast: #ffffff");
    expect(claro).toContain("--ejc-vibrant-gradient: #1d4ed8");
    expect(claro).not.toContain("--ejc-vibrant-cyan");
    expect(claro).not.toContain("linear-gradient(135deg, #2563eb");
    // Marca: ouro DPT, igual aos PDFs Visual Law
    expect(claro).toContain("--ejc-gold: #8f7117");
    expect(claro).toContain("--ejc-gold-ink: #8f7117");
    expect(claro).toContain("--ejc-gold-soft: #f7f1dc");
    // IA: violeta, exclusivo de inteligência
    expect(claro).toContain("--ejc-ai: #7c3aed");
    // Foco: azul da ação
    expect(claro).toContain("--ejc-focus-ring: rgba(29, 78, 216, 0.4)");
  });

  it("preserva contraste AA no claro e no escuro", () => {
    const claro = blocoClaro();
    const escuro = blocoEscuro();

    expect(contrast("#101828", "#ffffff")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#101828", "#f6f7f9")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#475467", "#ffffff")).toBeGreaterThanOrEqual(4.5);
    // Ação: branco sobre azul = 7:1 (AAA)
    expect(contrast("#ffffff", "#1d4ed8")).toBeGreaterThanOrEqual(4.5);
    // Marca: ouro DPT sobre branco = 4,6:1 (AA)
    expect(contrast("#8f7117", "#ffffff")).toBeGreaterThanOrEqual(4.5);
    // Escuro: canvas grafite, tinta clara, acento azul claro, ouro claro.
    // Um só acento: claro para texto/ícones (5,4:1 sobre a superfície) e o
    // tom sólido da família no botão primário (4,8:1 com branco).
    expect(contrast("#f2f4f7", "#0c0f14")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#f2f4f7", "#151a21")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#5b8def", "#151a21")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("#ffffff", "#3b6fd4")).toBeGreaterThanOrEqual(4.5);
    // Preenchimento de controle cheio consome --ejc-primary-surface, não o
    // acento claro: com texto branco sobre #5B8DEF seriam 3,2:1.
    expect(contrast("#ffffff", "#5b8def")).toBeLessThan(4.5);
    expect(escuro).toContain("--ejc-primary-surface: var(--ejc-primary-solid)");
    expect(escuro).toContain("--ejc-primary-solid: #3b6fd4");
    expect(claro).toContain("--ejc-primary-surface: var(--ejc-primary)");
    // Consumidor real: o preenchimento dos controles cheios no escuro deve
    // consumir o token (não basta a declaração — sem consumidor o valor
    // morto não corrige contraste nenhum).
    expect(premium).toMatch(
      /\.dark \.ejc-dash__tabs button\.is-active\s*\{[^}]*var\(--ejc-primary-surface\)/,
    );
    expect(premium).not.toContain(".ejc-dash__mode");
    // Epígrafe: no claro, o rótulo da cidade segue com texto claro sobre o
    // overlay escuro da foto (tinta escura ali ficaria ~1:1).
    expect(css).not.toContain(
      "html:not(.dark) .ejc-sidebar-epigraph__city strong",
    );
    expect(css).not.toContain(
      "html:not(.dark) .ejc-sidebar-epigraph__city small",
    );
    expect(contrast("#d9b45c", "#151a21")).toBeGreaterThanOrEqual(4.5);
    expect(escuro).toContain("--ejc-surface: #151a21");
    expect(escuro).toContain("--ejc-primary: #5b8def");
    expect(escuro).toContain("--ejc-primary-solid: #3b6fd4");
    expect(escuro).toContain("--ejc-gold: #d9b45c");
  });

  it("não deixa a paleta esmeralda da geração anterior como cor de papel", () => {
    // A paleta esmeralda foi substituída em 18/09 e o tema neutro em 28/09.
    // O bloco claro é a fonte; nenhum literal esmeralda pode voltar como
    // fundo, ação ou texto de marca.
    const claro = blocoClaro();
    for (const literal of ["#0a4132", "#04291f", "#14503f", "#1d2b26"]) {
      expect(claro, `literal esmeralda ${literal} no tema claro`).not.toContain(
        literal,
      );
    }
  });

  it("mantém a camada morta premium-shell fora do bundle", () => {
    // premium-shell.css (618 linhas) estiliza `ejc-premium-topbar` e
    // `ejc-sidebar-week`, que nenhum componente renderiza desde o shell v2.
    expect(main).not.toContain("premium-shell");
  });
});

describe("EJC — shell canônico", () => {
  it("mantém a marca, a navegação canônica e a largura V4 do menu", () => {
    expect(layout).toContain('"md:w-64"');
    expect(layout).toContain('"md:ml-64"');
    expect(layout).toContain('"md:left-64"');
    expect(layout).toContain('"md:w-[4.5rem]"');
    expect(layout).toContain('"md:left-[4.5rem]"');
    expect(layout).toContain("z-[60]");
    expect(layout).toContain("md:z-40");
    expect(layout).toContain("ejc-sidebar-brand__logo");
    expect(layout).toContain("selectMainNavigation");
    expect(layout).toContain("officeName");
    expect(layout).not.toContain("md:w-[17rem]");
    expect(layout).not.toContain("SidebarWeekCalendar");
  });

  it("mantém as classes de navegação agrupada que o shell vai consumir", () => {
    // `moduleRegistry.group` já existe e o CSS já tem `.sidebar-group-label`.
    // O shell (LayoutReference.tsx) é editado pelos PRs #1866 e #1867, então
    // este PR entrega as regras; o componente entra depois do merge deles.
    expect(layout).toContain("sidebar-nav-item");
    expect(tokens).toContain(".sidebar-group-label");
    expect(tokens).toContain(".sidebar-week");
  });

  it("reserva a área do calendário semanal abaixo do menu lateral", () => {
    // O epígrafe (panorama de Betim + citação) ocupava ~30% da altura da
    // sidebar com informação institucional já presente no login. A área foi
    // liberada para o calendário da semana; o epígrafe sai com o shell.
    expect(tokens).toContain(".sidebar-week");
  });

  it("não renderiza epígrafe decorativo na sidebar operacional V4", () => {
    // O V4 removeu foto/citação institucional para priorizar navegação,
    // recentes e agenda no espaço vertical do workspace.
    expect(layout).not.toContain("ejc-sidebar-epigraph");
  });

  it("mantém o menu, a busca global e o relógio do header", () => {
    expect(layout).toContain("ejc-header-search");
    expect(layout).toContain("ejc-app-header");
    expect(layout).toContain("ejc-header-clock");
  });
});

describe("EJC — início canônico", () => {
  it("reproduz a composição da referência no início", () => {
    expect(dashboard).toContain("ejc-dash__greeting");
    expect(dashboard).toContain("ejc-dash__entry");
    expect(dashboard).toContain("Entrada Única");
    expect(dashboard).toContain("<EntradaInteligente embedded />");
    expect(dashboard).toContain("ejc-dash__stats");
    expect(dashboard).toContain("Prazos hoje");
    expect(dashboard).toContain("Clientes ativos");
    expect(dashboard).toContain("Casos em andamento");
    expect(dashboard).toContain("Documentos recentes");
    expect(dashboard).toContain("Casos em destaque");
    // Jornada simplificada (#2013, S3): o fluxo paralelo de sete etapas saiu
    // do início — a régua de progresso vive só no caso.
    expect(dashboard).not.toContain('aria-label="Fluxo jurídico"');
    expect(dashboard).toContain("Decisões que exigem sua atenção hoje");
    expect(dashboard).toContain("Começar novo trabalho");
    expect(dashboard).not.toContain('aria-label="Agenda e Prazos"');
    expect(dashboard).not.toContain("Minha rotina hoje");
  });

  it("alimenta o início com endpoints reais e degrada para traço, nunca zero falso", () => {
    expect(dashboard).toContain('"/dashboard/"');
    expect(dashboard).toContain('"/atividades"');
    expect(dashboard).toContain('"/cases/"');
    expect(dashboard).toContain('"/documents/"');
    expect(dashboard).toContain('"/tasks/"');
    expect(dashboard).toContain("valorOuTraco");
    expect(dashboard).toContain("Promise.allSettled");
  });
});
