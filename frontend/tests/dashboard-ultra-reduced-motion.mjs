// Regressão visual isolada: hover não pode deslocar superfícies do dashboard
// canônico (.ejc-dash — DashboardUltra, identidade DPT) quando o sistema
// operacional solicita redução de movimento.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const CHROMIUM = process.env.PW_CHROMIUM || chromium.executablePath();
const cssTokens = readFileSync(
  path.join(ROOT, "src", "styles", "ejc-tokens.css"),
  "utf8",
);
const cssDash = readFileSync(
  path.join(ROOT, "src", "styles", "ejc-dashboard-premium.css"),
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
    <style>${cssTokens}\n${cssDash}</style>
    <main>
      <a class="ejc-dash__stat" href="#">Métrica</a>
      <button class="ejc-dash__chip" type="button">Atalho</button>
      <div class="ejc-dash__quick-items"><a href="#">Acesso rápido</a></div>
      <button class="ejc-dash__calendar-day" type="button">1</button>
      <div class="ejc-dash__timeline"><button type="button">Item da agenda</button></div>
      <div class="ejc-dash__cases"><button type="button">Caso em destaque</button></div>
      <div class="ejc-dash__routine"><button type="button">Tarefa da rotina</button></div>
      <a class="sidebar-nav-item" href="#">
        <svg width="20" height="20" viewBox="0 0 20 20" aria-label="Ícone"></svg>
      </a>
    </main>
  `);

  const selectors = [
    ".ejc-dash__stat",
    ".ejc-dash__chip",
    ".ejc-dash__quick-items a",
    ".ejc-dash__calendar-day",
    ".ejc-dash__timeline button",
    ".ejc-dash__cases button",
    ".ejc-dash__routine button",
  ];
  const failures = [];

  for (const selector of selectors) {
    const locator = page.locator(selector).first();
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
