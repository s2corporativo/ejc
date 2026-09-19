// Homologação visual do AppShell canônico + DashboardUltra (identidade DPT
// esmeralda & ouro) em Chromium real, em 7 viewports.
// As respostas abaixo existem somente no contexto Playwright e não alteram o produto.
import http from "node:http";
import { existsSync, mkdirSync } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.resolve(__dirname, "..", "dist");
const OUT =
  process.env.PREMIUM_SCREENSHOT_DIR ||
  path.resolve(__dirname, "__out__", "premium-dashboard");
const CHROMIUM = process.env.PW_CHROMIUM || chromium.executablePath();

const VIEWPORTS = [
  { name: "mobile-360", width: 360, height: 800 },
  { name: "mobile-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "tablet-1024", width: 1024, height: 768 },
  { name: "desktop-1366", width: 1366, height: 768 },
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "desktop-1920", width: 1920, height: 1080 },
];

const USER = {
  id: "usuario-homologacao",
  email: "advogado.homologacao@example.test",
  full_name: "Clóvis Soares",
  role: "advogado",
  permissions: [],
  avatar_url: null,
};

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".ico": "image/x-icon",
};

function dateKey(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function isoDateTime(date, hhmm) {
  return `${dateKey(date)}T${hhmm}:00`;
}

function diasAFrente(dias) {
  const date = new Date();
  date.setDate(date.getDate() + dias);
  return date;
}

const today = new Date();

// Fixtures no CONTRATO REAL do DashboardUltra (endpoints de DashboardUltra.tsx):
// /dashboard/ → Kpis; /atividades → Atividade[]; /cases/ → CasoResumo[];
// /documents/ → { total }; /tasks/ → Tarefa[].
const FIXTURES = {
  dashboard: {
    casos: { ativos: 98 },
    clientes_ativos: 48,
  },
  activities: [
    {
      id: "at-prazo-hoje",
      tipo: "prazo",
      titulo: "Prazo final — Contestação",
      date: isoDateTime(today, "11:30"),
      status: "pendente",
      case_id: "caso-1",
      caso_titulo: "Empresa X vs. Banco Y",
      urgencia: "critico",
      dias_restantes: 0,
    },
    {
      id: "at-tarefa-hoje",
      tipo: "tarefa",
      titulo: "Revisar petição inicial",
      date: isoDateTime(today, "14:00"),
      status: "a_fazer",
      case_id: "caso-1",
      caso_titulo: "Empresa X vs. Banco Y",
      urgencia: "atencao",
      dias_restantes: 0,
    },
    {
      id: "at-intimacao-amanha",
      tipo: "intimacao",
      titulo: "Audiência de instrução",
      date: isoDateTime(diasAFrente(1), "09:00"),
      status: "pendente",
      case_id: "caso-2",
      caso_titulo: "Construtora Alpha",
      dias_restantes: 1,
    },
    {
      id: "at-prazo-semana",
      tipo: "prazo",
      titulo: "Manifestação sobre laudo",
      date: isoDateTime(diasAFrente(3), "16:00"),
      status: "pendente",
      case_id: "caso-3",
      caso_titulo: "Maria Oliveira",
      urgencia: "normal",
      dias_restantes: 3,
    },
  ],
  cases: [
    {
      id: "caso-1",
      titulo: "Empresa X vs. Banco Y",
      status: "ativo",
      area: "consumidor",
      numero_processo: "1001234-56.2023.8.26.0100",
    },
    {
      id: "caso-2",
      titulo: "João Silva vs. Plano de Saúde",
      status: "ativo",
      area: "saude",
      numero_processo: "5005678-22.2024.4.03.6100",
    },
    {
      id: "caso-3",
      titulo: "Construtora Alpha",
      status: "ativo",
      area: "imobiliario",
      numero_processo: "1023456-78.2023.8.26.0100",
    },
    {
      id: "caso-4",
      titulo: "Maria Oliveira",
      status: "encerrado",
      area: "familia",
      numero_processo: "3009876-12.2022.8.26.0100",
    },
  ],
  documents: { total: 129, items: [] },
  tasks: [
    {
      id: "task-1",
      titulo: "Revisar petição inicial",
      status: "concluida",
      data_limite: dateKey(today),
      concluida_em: isoDateTime(today, "08:00"),
    },
    {
      id: "task-2",
      titulo: "Retorno para cliente — Grupo Santos",
      status: "concluida",
      data_limite: dateKey(today),
      concluida_em: isoDateTime(today, "09:00"),
    },
    {
      id: "task-3",
      titulo: "Analisar minuta de contrato",
      status: "pendente",
      prioridade: "alta",
      data_limite: dateKey(today),
    },
    {
      id: "task-4",
      titulo: "Estudo tema 1.234/STJ",
      status: "pendente",
      data_limite: dateKey(today),
    },
    {
      id: "task-5",
      titulo: "Atualizar banco de teses",
      status: "pendente",
      data_limite: dateKey(today),
    },
  ],
  entradaMeta: { modalidades: [] },
};

if (!existsSync(DIST)) {
  console.error(`[premium-dashboard] dist/ não encontrado em ${DIST}.`);
  process.exit(2);
}
if (!CHROMIUM || !existsSync(CHROMIUM)) {
  console.error("[premium-dashboard] Chromium não encontrado.");
  process.exit(2);
}

const server = http.createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent((request.url || "/").split("?")[0]);
    let file = path.join(DIST, pathname);
    const validFile = existsSync(file) && (await stat(file)).isFile();
    if (!validFile) file = path.join(DIST, "index.html");
    response.writeHead(200, {
      "content-type": MIME[path.extname(file)] || "application/octet-stream",
      "cache-control": "no-store",
    });
    response.end(await readFile(file));
  } catch (error) {
    response.writeHead(500);
    response.end(String(error));
  }
});

function fixtureFor(requestUrl) {
  const pathname = new URL(requestUrl).pathname.replace(/^\/api\/v1/, "");
  if (pathname === "/users/me") return USER;
  if (pathname === "/users/me/security") return { permissions: [] };
  if (pathname === "/system-modules/settings") {
    return { data: [], protected_module_keys: [] };
  }
  if (pathname === "/ia/status") return { disponivel: true, mensagem: null };
  if (pathname === "/dashboard/") return FIXTURES.dashboard;
  if (pathname === "/atividades") return FIXTURES.activities;
  if (pathname === "/cases/") return FIXTURES.cases;
  if (pathname === "/documents/") return FIXTURES.documents;
  if (pathname === "/tasks/") return FIXTURES.tasks;
  if (pathname === "/entrada-universal/meta") return FIXTURES.entradaMeta;
  if (pathname === "/notifications/") {
    return { data: [], nao_lidas: 0, total: 0 };
  }
  return {};
}

async function installApiFixtures(page) {
  await page.route("**/api/**", async (route) => {
    if (route.request().method() === "OPTIONS") {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json; charset=utf-8",
      body: JSON.stringify(fixtureFor(route.request().url())),
    });
  });
}

async function inspectDashboard(page, viewport, failures) {
  await page.waitForSelector(".ejc-dash", { timeout: 15000 });
  // Dados reais (das fixtures) renderizados — não apenas o esqueleto.
  await page
    .waitForFunction(
      () => {
        const texto = document.querySelector("main")?.innerText ?? "";
        return (
          texto.includes("Casos em destaque") && texto.includes("Clientes ativos")
        );
      },
      { timeout: 15000 },
    )
    .catch(() => {
      failures.push(
        `${viewport.name}: dashboard canônico não montou com dados (Entrada Única/indicadores)`,
      );
    });

  const layout = await page.evaluate(() => {
    const topbar = document.querySelector("header.fixed.inset-x-0.top-0");
    const dashboard = document.querySelector(".ejc-dash");
    return {
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      topbarVisible: Boolean(
        topbar && getComputedStyle(topbar).display !== "none",
      ),
      dashboardVisible: Boolean(
        dashboard && getComputedStyle(dashboard).display !== "none",
      ),
      mainText: document.querySelector("main")?.innerText || "",
    };
  });

  const overflow = layout.scrollWidth - layout.innerWidth;
  if (overflow > 1) {
    failures.push(`${viewport.name}: overflow horizontal de ${overflow}px`);
  }
  if (!layout.topbarVisible) {
    failures.push(`${viewport.name}: topbar principal não está visível`);
  }
  if (!layout.dashboardVisible) {
    failures.push(`${viewport.name}: dashboard canônico não está visível`);
  }

  const normalizedMainText = layout.mainText.toLocaleLowerCase("pt-BR");

  // Conteúdo de outra geração de dashboard (Command Center financeiro) não
  // pode vazar para a identidade DPT, nem sentinelas internas.
  for (const forbidden of [
    "918.273,45",
    "876.543,21",
    "765.432,10",
    "homologacao-nao-renderizar",
    "Faturamento",
    "Receitas",
    "Despesas",
    "Saldo financeiro",
    "Legal Operations Command Center",
  ]) {
    if (normalizedMainText.includes(forbidden.toLocaleLowerCase("pt-BR"))) {
      failures.push(
        `${viewport.name}: conteúdo indevido na identidade DPT: ${forbidden}`,
      );
    }
  }

  // Composição canônica da referência (seção 9 do prompt mestre) com os
  // números das fixtures — provando que os indicadores vêm de dados reais.
  for (const expected of [
    "clóvis",
    "entrada única",
    "prazos hoje",
    "clientes ativos",
    "casos em andamento",
    "documentos recentes",
    "48",
    "98",
    "129",
    "agenda e prazos",
    "casos em destaque",
    "empresa x vs. banco y",
    "construtora alpha",
    "prazo final — contestação",
    "minha rotina hoje",
    "2 de 5 concluídas",
    "acesso rápido",
    "novo caso",
    "novo cliente",
    "enviar documentos",
  ]) {
    if (!normalizedMainText.includes(expected.toLocaleLowerCase("pt-BR"))) {
      failures.push(`${viewport.name}: conteúdo canônico ausente: ${expected}`);
    }
  }

  // O contexto inteiro roda com reducedMotion="reduce". O hover não pode
  // deslocar o cartão quando o usuário solicitou redução de movimento.
  const metric = page.locator(".ejc-dash__stat").first();
  await metric.hover();
  const transformReduzido = await metric.evaluate(
    (element) => getComputedStyle(element).transform,
  );
  if (transformReduzido !== "none") {
    failures.push(
      `${viewport.name}: hover desloca métrica com reduced-motion (${transformReduzido})`,
    );
  }

  const sidebar = page.locator("aside.sidebar-bronze");
  if (viewport.width < 768) {
    await page
      .getByRole("button", { name: "Abrir ou recolher menu" })
      .first()
      .click();
    if (!(await sidebar.isVisible())) {
      failures.push(`${viewport.name}: drawer da sidebar não abriu`);
    }
    const drawerCloseButton = sidebar.getByRole("button", {
      name: "Fechar menu",
    });
    if ((await drawerCloseButton.count()) > 0) {
      await drawerCloseButton.click();
    }
  } else if (!(await sidebar.isVisible())) {
    failures.push(`${viewport.name}: sidebar desktop não está visível`);
  }

  await page.screenshot({
    path: path.join(OUT, `dashboard-${viewport.name}.png`),
    fullPage: true,
  });
  console.log(
    `[${viewport.name} ${viewport.width}x${viewport.height}] ` +
      `scrollWidth=${layout.scrollWidth} innerWidth=${layout.innerWidth} ` +
      `overflowX=${overflow}px → ${overflow <= 1 ? "OK" : "FALHA"}`,
  );
}

async function main() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Não foi possível resolver a porta do servidor de teste.");
  }

  mkdirSync(OUT, { recursive: true });
  const base = `http://127.0.0.1:${address.port}/`;
  const browser = await chromium.launch({ executablePath: CHROMIUM });
  const failures = [];

  try {
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
        locale: "pt-BR",
        timezoneId: "America/Sao_Paulo",
        reducedMotion: "reduce",
      });
      await context.addInitScript(
        ({ user }) => {
          localStorage.setItem("ejc_access", "token-homologacao-visual");
          localStorage.setItem("ejc_user", JSON.stringify(user));
          localStorage.setItem("ejc_onboarding_v1", "dispensado");
          localStorage.setItem("ejc_privacy_mode", "false");
        },
        { user: USER },
      );

      const page = await context.newPage();
      const consoleErrors = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      page.on("pageerror", (error) => consoleErrors.push(String(error)));
      await installApiFixtures(page);
      await page.goto(base, { waitUntil: "networkidle" });
      await inspectDashboard(page, viewport, failures);

      if (consoleErrors.length) {
        failures.push(
          `${viewport.name}: erros no console: ${consoleErrors.slice(0, 5).join(" | ")}`,
        );
      }
      await context.close();
    }
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  if (failures.length) {
    console.error(
      `\nDASHBOARD CANÔNICO RESPONSIVO: FALHOU\n - ${failures.join("\n - ")}`,
    );
    process.exitCode = 1;
  } else {
    console.log(
      `\nDASHBOARD CANÔNICO RESPONSIVO: OK — 7 viewports sem overflow, ` +
        `composição e dados canônicos confirmados. Screenshots em ${OUT}`,
    );
  }
}

main().catch((error) => {
  console.error("[premium-dashboard] erro:", error);
  process.exit(1);
});