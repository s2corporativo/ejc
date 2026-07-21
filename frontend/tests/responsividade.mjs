// Teste de responsividade — dirige Chromium real contra o build servido e
// verifica que a página pública de login não estoura a viewport em mobile/tablet.
//
// Uso:
//   npm run build
//   npx playwright install --with-deps chromium
//   npm run test:responsive
import http from "node:http";
import { existsSync, mkdirSync } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.resolve(__dirname, "..", "dist");
const OUT = process.env.SCREENSHOT_DIR || path.resolve(__dirname, "__out__");
const CHROMIUM = process.env.PW_CHROMIUM || chromium.executablePath();

const MIME = {
  ".html": "text/html",
  ".js": "text/javascript",
  ".css": "text/css",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".json": "application/json",
  ".woff2": "font/woff2",
  ".ico": "image/x-icon",
};

if (!existsSync(DIST)) {
  console.error(
    `[responsividade] dist/ não encontrado em ${DIST}. Rode 'npm run build' antes.`,
  );
  process.exit(2);
}

if (!CHROMIUM || !existsSync(CHROMIUM)) {
  console.error(
    "[responsividade] Chromium não encontrado. Rode " +
      "'npx playwright install --with-deps chromium' ou defina PW_CHROMIUM.",
  );
  process.exit(2);
}

const server = http.createServer(async (req, res) => {
  try {
    const url = decodeURIComponent((req.url || "/").split("?")[0]);
    let file = path.join(DIST, url);
    const isFile = existsSync(file) && (await stat(file)).isFile();
    if (!isFile) file = path.join(DIST, "index.html");
    const body = await readFile(file);
    res.writeHead(200, {
      "content-type": MIME[path.extname(file)] || "application/octet-stream",
      "cache-control": "no-store",
    });
    res.end(body);
  } catch (error) {
    res.writeHead(500);
    res.end(String(error));
  }
});

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 667 },
  { name: "tablet", width: 768, height: 1024 },
];

async function main() {
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Não foi possível resolver a porta do servidor de teste.");
  }
  const base = `http://127.0.0.1:${address.port}/`;

  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: CHROMIUM });
  const falhas = [];

  try {
    for (const viewport of VIEWPORTS) {
      const context = await browser.newContext({
        viewport: { width: viewport.width, height: viewport.height },
      });
      const page = await context.newPage();
      const consoleErrors = [];
      page.on("console", (message) => {
        if (message.type() === "error") consoleErrors.push(message.text());
      });
      page.on("pageerror", (error) => consoleErrors.push(String(error)));

      await page.goto(base, { waitUntil: "networkidle" });
      await page.waitForSelector("input", { timeout: 10000 });

      const { scrollWidth, innerWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        innerWidth: window.innerWidth,
      }));
      await page.screenshot({
        path: path.join(OUT, `login-${viewport.name}.png`),
        fullPage: true,
      });

      const overflow = scrollWidth - innerWidth;
      const passou = overflow <= 1;
      console.log(
        `[${viewport.name} ${viewport.width}x${viewport.height}] ` +
          `scrollWidth=${scrollWidth} innerWidth=${innerWidth} ` +
          `overflowX=${overflow}px → ${passou ? "OK" : "FALHA"}`,
      );
      if (!passou) {
        falhas.push(`${viewport.name}: overflow horizontal de ${overflow}px`);
      }
      if (consoleErrors.length) {
        falhas.push(
          `${viewport.name}: erros no console: ${consoleErrors.slice(0, 5).join(" | ")}`,
        );
      }
      await context.close();
    }
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }

  if (falhas.length) {
    console.error(`\nRESPONSIVIDADE: FALHOU\n - ${falhas.join("\n - ")}`);
    process.exit(1);
  }
  console.log(
    "\nRESPONSIVIDADE: OK — login sem overflow e sem erro de console em mobile/tablet.",
  );
}

main().catch((error) => {
  console.error("[responsividade] erro:", error);
  server.close();
  process.exit(1);
});
