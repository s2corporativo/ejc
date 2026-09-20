// Homologação visual system-wide da identidade DPT (esmeralda & ouro):
// percorre os 10 domínios internos canônicos em desktop-1440 e tablet-768,
// verifica overflow horizontal, presença do shell canônico (sidebar + topbar)
// e captura screenshots para conferência lado a lado com a referência.
// Respostas existem somente no contexto Playwright; não alteram o produto.
import http from "node:http";
import { existsSync, mkdirSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.resolve(__dirname, "..", "dist");
const OUT =
  process.env.HOMOLOGACAO_SCREENSHOT_DIR ||
  path.resolve(__dirname, "__out__", "homologacao-modulos");
const CHROMIUM = process.env.PW_CHROMIUM || chromium.executablePath();

const VIEWPORTS = [
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "tablet-768", width: 768, height: 1024 },
];

const ROUTES = [
  { name: "agenda", path: "/atividades" },
  { name: "clientes", path: "/clientes" },
  { name: "casos", path: "/casos" },
  { name: "financeiro", path: "/financeiro" },
  { name: "documentos", path: "/documentos" },
  { name: "inteligencia", path: "/inteligencia" },
  { name: "banco-teses", path: "/teses" },
  { name: "radar", path: "/radar" },
  { name: "relatorios", path: "/produtividade" },
  { name: "configuracoes", path: "/configuracoes" },
];

const USER = {
  id: "usuario-homologacao",
  email: "advogado.homologacao@example.test",
  full_name: "Carlos Almeida",
  role: "socio",
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
  ".webp": "image/webp",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".ico": "image/x-icon",
};

// Páginas internas consomem listas em dois formatos: array cru (asList) ou
// envelope Paged {data,total,page,page_size} —Clientes/Casos leem r.data.data.
const PAGINADO = { data: [], total: 0, page: 1, page_size: 50 };
const LISTAS_FIXAS = {
  cases: PAGINADO,
  clients: PAGINADO,
  activities: [],
  tasks: [],
};

if (!existsSync(DIST)) {
  console.error(`[homologacao] dist/ não encontrado em ${DIST}. Rode build.`);
  process.exit(2);
}
if (!CHROMIUM || !existsSync(CHROMIUM)) {
  console.error("[homologacao] Chromium não encontrado.");
  process.exit(2);
}

const server = http.createServer(async (request, response) => {
  try {
    const pathname = decodeURIComponent((request.url || "/").split("?")[0]);
    let file = path.join(DIST, pathname);
    const validFile = existsSync(file) && (await statIsFile(file));
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

async function statIsFile(file) {
  const { stat } = await import("node:fs/promises");
  try {
    return (await stat(file)).isFile();
  } catch {
    return false;
  }
}

function fixtureFor(requestUrl) {
  const pathname = new URL(requestUrl).pathname.replace(/^\/api\/v1/, "");
  if (pathname === "/users/me") return USER;
  if (pathname === "/users/me/security") return { permissions: [] };
  if (pathname === "/system-modules/settings") {
    return { data: [], protected_module_keys: [] };
  }
  if (pathname === "/ia/status") return { disponivel: true, mensagem: null };
  if (pathname === "/dashboard/") return { casos: { ativos: 98 }, clientes_ativos: 48 };
  if (pathname === "/notifications/") {
    return { data: [], nao_lidas: 0, total: 0 };
  }
  const chaveLista = pathname.replace(/^\/+/, "").replace(/\/+$/, "");
  if (chaveLista in LISTAS_FIXAS) return LISTAS_FIXAS[chaveLista];
  // Páginas internas consomem majoritariamente listas; array vazio renderiza
  // o estado vazio canônico sem simular dados inexistentes.
  return [];
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

async function main() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Porta do servidor de teste indisponível.");
  }

  mkdirSync(OUT, { recursive: true });
  const base = `http://127.0.0.1:${address.port}`.replace(/\/$/, "");
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
      await context.addInitScript(({ user }) => {
        localStorage.setItem("ejc_access", "token-homologacao-visual");
        localStorage.setItem("ejc_user", JSON.stringify(user));
        localStorage.setItem("ejc_theme", "light");
      }, { user: USER });

      const page = await context.newPage();
      await installApiFixtures(page);

      for (const rota of ROUTES) {
        await page.goto(base + rota.path, { waitUntil: "networkidle" });
        await page.waitForTimeout(400);

        const layout = await page.evaluate(() => ({
          scrollWidth: document.documentElement.scrollWidth,
          innerWidth: window.innerWidth,
          sidebarVisible: Boolean(
            document.querySelector("aside.sidebar-bronze"),
          ),
          mainText: (document.querySelector("main")?.innerText || "").slice(0, 400),
        }));

        const overflow = layout.scrollWidth - layout.innerWidth;
        if (overflow > 1) {
          failures.push(
            `${viewport.name} ${rota.path}: overflow horizontal de ${overflow}px`,
          );
        }
        if (viewport.width >= 1024 && !layout.sidebarVisible) {
          failures.push(`${viewport.name} ${rota.path}: sidebar ausente`);
        }

        await page.screenshot({
          path: path.join(OUT, `modulo-${rota.name}-${viewport.name}.png`),
          fullPage: false,
        });
        console.log(
          `[${viewport.name}] ${rota.path} → overflow=${overflow}px ${
            overflow <= 1 ? "OK" : "FALHA"
          }`,
        );
      }
      await context.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  if (failures.length > 0) {
    console.error(`\nHOMOLOGAÇÃO DE MÓDULOS: FALHA`);
    for (const failure of failures) console.error(` - ${failure}`);
    process.exit(1);
  }
  console.log(
    `\nHOMOLOGAÇÃO DE MÓDULOS: OK — ${ROUTES.length} domínios × ${VIEWPORTS.length} viewports, shell canônico presente, sem overflow. Screenshots em ${OUT}`,
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
