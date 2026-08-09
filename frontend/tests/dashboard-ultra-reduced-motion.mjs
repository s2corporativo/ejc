// Regressão visual isolada: hover não pode deslocar superfícies do DashboardUltra
// quando o sistema operacional solicita redução de movimento.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const CHROMIUM = process.env.PW_CHROMIUM || chromium.executablePath();
const cssBase = readFileSync(
  path.join(ROOT, "src", "styles", "saas-ultra-v2.css"),
  "utf8",
);
const cssGuard = readFileSync(
  path.join(ROOT, "src", "styles", "saas-ultra-accessibility.css"),
  "utf8",
);

if (!CHROMIUM || !existsSync(CHROMIUM)) {
  console.error("[dashboard-ultra-reduced-motion] Chromium não encontrado.");
  process.exit(2);
}

const browser = await chromium.launch({ executablePath: CHROMIUM });
const context = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  reducedMotion: "reduce",
});
const page = await context.newPage();

try {
  await page.setContent(`
    <style>${cssBase}\n${cssGuard}</style>
    <main>
      <a class="ejc-ultra-primary-action" href="#">Primária</a>
      <a class="ejc-ultra-secondary-action" href="#">Secundária</a>
      <a class="ejc-ultra-metric" href="#">Métrica</a>
      <a class="ejc-ultra-priority" href="#">Prioridade</a>
      <a class="ejc-ultra-command" href="#">Comando</a>
      <aside class="sidebar-bronze">
        <a class="sidebar-nav-item" href="#">
          <svg width="20" height="20" viewBox="0 0 20 20" aria-label="Ícone"></svg>
        </a>
      </aside>
    </main>
  `);

  const selectors = [
    ".ejc-ultra-primary-action",
    ".ejc-ultra-secondary-action",
    ".ejc-ultra-metric",
    ".ejc-ultra-priority",
    ".ejc-ultra-command",
    ".sidebar-bronze .sidebar-nav-item svg",
  ];
  const failures = [];

  for (const selector of selectors) {
    const locator = page.locator(selector);
    await locator.hover();
    const transform = await locator.evaluate(
      (element) => getComputedStyle(element).transform,
    );
    if (transform !== "none") {
      failures.push(`${selector}: transform=${transform}`);
    }
  }

  if (failures.length) {
    console.error(
      `DASHBOARD ULTRA REDUCED MOTION: FALHOU\n - ${failures.join("\n - ")}`,
    );
    process.exitCode = 1;
  } else {
    console.log(
      "DASHBOARD ULTRA REDUCED MOTION: OK — hovers permanecem estacionários.",
    );
  }
} finally {
  await context.close();
  await browser.close();
}
