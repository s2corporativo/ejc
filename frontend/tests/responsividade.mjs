// Teste de responsividade (Bloco 6) — dirige o navegador REAL (Chromium) contra
// o build servido e verifica que a página pública (login) não estoura a viewport
// em mobile (375px) e tablet (768px). Auto-contido: sobe um servidor estático do
// dist/ (com fallback SPA), lança o Chromium e sai 0/1.
//
// Uso:  npm run build && node tests/responsividade.mjs
// O binário do Chromium pré-instalado é resolvido por PW_CHROMIUM ou pelo caminho
// padrão do ambiente (/opt/pw-browsers/...). Não baixa navegador.
import http from "node:http";
import { readFile, stat } from "node:fs/promises";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DIST = path.resolve(__dirname, "..", "dist");
const OUT = process.env.SCREENSHOT_DIR || path.resolve(__dirname, "__out__");
const CHROMIUM =
  process.env.PW_CHROMIUM ||
  "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";

const MIME = {
  ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
  ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
  ".json": "application/json", ".woff2": "font/woff2", ".ico": "image/x-icon",
};

if (!existsSync(DIST)) {
  console.error(`[responsividade] dist/ não encontrado em ${DIST}. Rode 'npm run build' antes.`);
  process.exit(2);
}

// Servidor estático com fallback SPA (rota sem arquivo → index.html).
const server = http.createServer(async (req, res) => {
  try {
    const url = decodeURIComponent((req.url || "/").split("?")[0]);
    let file = path.join(DIST, url);
    let ok = existsSync(file) && (await stat(file)).isFile();
    if (!ok) file = path.join(DIST, "index.html"); // fallback SPA
    const body = await readFile(file);
    res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
    res.end(body);
  } catch (e) {
    res.writeHead(500);
    res.end(String(e));
  }
});

const VIEWPORTS = [
  { name: "mobile", width: 375, height: 667 },
  { name: "tablet", width: 768, height: 1024 },
];

async function main() {
  await new Promise((r) => server.listen(0, r));
  const port = server.address().port;
  const base = `http://127.0.0.1:${port}/`;

  mkdirSync(OUT, { recursive: true }); // garante o diretório dos screenshots
  const browser = await chromium.launch({ executablePath: CHROMIUM });
  const falhas = [];
  try {
    for (const vp of VIEWPORTS) {
      const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
      const page = await ctx.newPage();
      await page.goto(base, { waitUntil: "networkidle" });
      await page.waitForSelector("input", { timeout: 10000 }); // formulário de login
      const { sw, iw } = await page.evaluate(() => ({
        sw: document.documentElement.scrollWidth,
        iw: window.innerWidth,
      }));
      await page.screenshot({ path: path.join(OUT, `login-${vp.name}.png`), fullPage: true }).catch(() => {});
      const overflow = sw - iw;
      const passou = overflow <= 1; // tolerância de 1px (arredondamento)
      console.log(
        `[${vp.name} ${vp.width}x${vp.height}] scrollWidth=${sw} innerWidth=${iw} ` +
        `overflowX=${overflow}px → ${passou ? "OK" : "FALHA (estoura horizontal)"}`,
      );
      if (!passou) falhas.push(`${vp.name}: overflow horizontal de ${overflow}px`);
      await ctx.close();
    }
  } finally {
    await browser.close();
    server.close();
  }

  if (falhas.length) {
    console.error("\nRESPONSIVIDADE: FALHOU\n - " + falhas.join("\n - "));
    process.exit(1);
  }
  console.log("\nRESPONSIVIDADE: OK — sem overflow horizontal em mobile/tablet (página de login).");
}

main().catch((e) => {
  console.error("[responsividade] erro:", e);
  server.close();
  process.exit(1);
});
