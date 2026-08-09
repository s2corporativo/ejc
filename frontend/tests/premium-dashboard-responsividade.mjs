// Homologação visual do AppShell v2 e dashboard ultra em Chromium real.
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

const today = new Date();
const tomorrow = new Date(today);
tomorrow.setDate(today.getDate() + 1);
const yesterday = new Date(today);
yesterday.setDate(today.getDate() - 1);

const FIXTURES = {
  dashboard: {
    casos: {
      por_status: { ativo: 98, arquivado: 18, suspenso: 8, encerrado: 2 },
      por_area: [
        { area: "trabalhista", total: 57 },
        { area: "civil", total: 32 },
        { area: "empresarial", total: 19 },
        { area: "tributario", total: 12 },
        { area: "ambiental", total: 6 },
      ],
      total: 126,
      ativos: 98,
      arquivados: 18,
      encerrados: 2,
    },
    prazos: { vencidos: 1, criticos_3d: 4, proximos_7d: 18 },
    // Sentinelas deliberadas: a página compartilhada não pode renderizá-las.
    financeiro: {
      pendente: 918273.45,
      atrasado: 876543.21,
      recebido_mes: 765432.1,
      escopo: "homologacao-nao-renderizar",
    },
    degradado: [],
  },
  activities: [
    {
      id: "atividade-tarefa",
      tipo: "tarefa",
      fonte: "tarefa",
      titulo: "Revisar contestação",
      date: dateKey(today),
      status: "a_fazer",
      case_id: "caso-1",
      caso_titulo: "Processo trabalhista principal",
      prioridade: "alta",
    },
    {
      id: "atividade-audiencia",
      tipo: "agenda",
      subtipo: "audiencia",
      fonte: "agenda",
      titulo: "Audiência trabalhista",
      date: dateKey(today),
      status: "pendente",
      case_id: "caso-1",
      caso_titulo: "Processo trabalhista principal",
    },
    {
      id: "atividade-reuniao",
      tipo: "agenda",
      subtipo: "reuniao",
      fonte: "agenda",
      titulo: "Reunião com cliente",
      date: dateKey(tomorrow),
      status: "pendente",
      case_id: "caso-2",
      caso_titulo: "Consultoria empresarial",
    },
    {
      id: "atividade-prazo",
      tipo: "prazo",
      fonte: "prazo",
      titulo: "Prazo para manifestação",
      date: dateKey(tomorrow),
      status: "pendente",
      case_id: "caso-3",
      caso_titulo: "Ação cível",
    },
  ],
  agenda: {
    items: [
      {
        id: "atividade-audiencia",
        tipo: "audiencia",
        hora: "09:00",
        local: "Fórum trabalhista",
      },
      {
        id: "atividade-reuniao",
        tipo: "reuniao",
        hora: "14:00",
        local: "Online",
      },
    ],
    total: 2,
  },
  movements: {
    items: [
      {
        id: "movimento-1",
        titulo: "Recurso especial publicado",
        descricao: "Publicação de recurso especial no processo",
        status: "publicado",
        created_at: `${dateKey(today)}T09:30:00`,
        case_id: "caso-1",
        case_title: "Processo trabalhista principal",
        case_number: "5001234-56.2024.8.13.0024",
        cliente_nome: "Cliente de homologação",
      },
      {
        id: "movimento-2",
        titulo: "Manifestação protocolada",
        descricao: "Manifestação protocolada no processo",
        status: "protocolado",
        created_at: `${dateKey(yesterday)}T17:45:00`,
        case_id: "caso-3",
        case_title: "Ação cível",
        case_number: "0123456-78.2023.8.13.0024",
      },
    ],
    total: 2,
  },
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
  if (pathname === "/agenda-eventos/") return FIXTURES.agenda;
  if (pathname === "/movimentos/recentes") return FIXTURES.movements;
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
  await page.waitForSelector(".ejc-ultra-dashboard", { timeout: 15000 });
  await page.getByText("Legal Operations Command Center").waitFor();
  await page.getByText("Casos ativos").waitFor();

  const layout = await page.evaluate(() => {
    const topbar = document.querySelector("header.fixed.inset-x-0.top-0");
    const dashboard = document.querySelector(".ejc-ultra-dashboard");
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
    failures.push(`${viewport.name}: dashboard ultra não está visível`);
  }

  const normalizedMainText = layout.mainText.toLocaleLowerCase("pt-BR");

  for (const forbidden of [
    "918.273,45",
    "876.543,21",
    "765.432,10",
    "homologacao-nao-renderizar",
    "Faturamento",
    "Receitas",
    "Despesas",
    "Honorários",
    "Saldo financeiro",
  ]) {
    if (normalizedMainText.includes(forbidden.toLocaleLowerCase("pt-BR"))) {
      failures.push(
        `${viewport.name}: conteúdo financeiro indevido: ${forbidden}`,
      );
    }
  }

  for (const expected of [
    "126",
    "98",
    "Tarefas pendentes",
    "Prazos em 7 dias",
    "Movimentações recentes",
    "Próximos compromissos",
    "Áreas de atuação",
    "Distribuição dos casos",
    "Publicação de recurso especial no processo",
  ]) {
    if (!normalizedMainText.includes(expected.toLocaleLowerCase("pt-BR"))) {
      failures.push(`${viewport.name}: conteúdo operacional ausente: ${expected}`);
    }
  }

  // O contexto inteiro roda com reducedMotion="reduce". O hover não pode
  // deslocar o cartão quando o usuário solicitou redução de movimento.
  const metric = page.locator(".ejc-ultra-metric").first();
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
    await page.getByRole("button", { name: "Abrir menu" }).click();
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
      `\nDASHBOARD ULTRA RESPONSIVO: FALHOU\n - ${failures.join("\n - ")}`,
    );
    process.exit(1);
  }

  console.log(
    "\nDASHBOARD ULTRA RESPONSIVO: OK — sete larguras, sem overflow, " +
      "sem erro de console, sem movimento indevido e sem sentinelas financeiras renderizadas.",
  );
}

main().catch((error) => {
  console.error("[dashboard-ultra] erro:", error);
  server.close();
  process.exit(1);
});
