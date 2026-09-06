// Regressão de acessibilidade: com `prefers-reduced-motion: reduce`, o hover
// não pode deslocar os elementos do AppShell.
//
// Sucede `dashboard-ultra-reduced-motion.mjs`, que montava um DOM sintético
// com classes `.ejc-ultra-*` que o produto não renderiza mais — o teste
// passava sem exercitar nada real. Aqui os seletores são os do shell vivo.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const CHROMIUM = process.env.PW_CHROMIUM || chromium.executablePath();
const css = readFileSync(
  path.join(ROOT, "src", "styles", "app-shell.css"),
  "utf8",
);

if (!CHROMIUM || !existsSync(CHROMIUM)) {
  console.error("[shell-reduced-motion] Chromium não encontrado.");
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
    <style>${css}</style>
    <aside class="sidebar-bronze">
      <div><a href="#">Topo</a><button type="button">Recolher</button></div>
      <nav>
        <button type="button" class="sidebar-group-label">Grupo</button>
        <a class="sidebar-nav-item" href="#">
          <svg width="20" height="20" viewBox="0 0 20 20" aria-label="Ícone"></svg>
          <span>Casos</span>
        </a>
        <a class="sidebar-nav-item is-active" href="#">
          <svg width="20" height="20" viewBox="0 0 20 20" aria-label="Ícone ativo"></svg>
          <span>Dashboard</span>
        </a>
      </nav>
      <div><div>Rodapé</div></div>
    </aside>
  `);

  const selectors = [
    ".sidebar-bronze .sidebar-nav-item svg",
    ".sidebar-bronze .sidebar-nav-item.is-active svg",
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
    console.error(`SHELL REDUCED MOTION: FALHOU\n - ${failures.join("\n - ")}`);
    process.exitCode = 1;
  } else {
    console.log("SHELL REDUCED MOTION: OK — hovers permanecem estacionários.");
  }
} finally {
  await context.close();
  await browser.close();
}
