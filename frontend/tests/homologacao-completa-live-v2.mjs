// Homologação autenticada em Chromium real contra o frontend publicado.
// V2: usa seletores CSS para prosseguir apesar do defeito de acessibilidade
// confirmado na tela de login (labels sem htmlFor/id).
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "../..");
const resolveRoot = (value, fallback) => value ? path.resolve(ROOT, value) : fallback;
const OUT = resolveRoot(process.env.SCREENSHOT_DIR, path.resolve(__dirname, "__out__/homologacao-live"));
const REPORT_PATH = resolveRoot(process.env.EJC_QA_BROWSER_REPORT, path.join(OUT, "browser_homologacao_report.json"));
const AI_REPORT = resolveRoot(process.env.EJC_AI_REPORT, path.resolve(ROOT, "qa/homologacao/reports/ia_peca_protocolavel_report.json"));
const BASE = (process.env.EJC_FRONTEND_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const EMAIL = required("EJC_TEST_EMAIL");
const PASSWORD = required("EJC_TEST_PASSWORD");
const TOTP_SECRET = required("EJC_TEST_TOTP_SECRET");
fs.mkdirSync(OUT, { recursive: true });

function required(name) {
  const value = (process.env[name] || "").trim();
  if (!value) throw new Error(`Variável obrigatória ausente: ${name}`);
  return value;
}
function base32Decode(input) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of input.toUpperCase().replace(/=+$/, "").replace(/\s+/g, "")) {
    const idx = alphabet.indexOf(char);
    if (idx < 0) throw new Error("Segredo TOTP inválido");
    bits += idx.toString(2).padStart(5, "0");
  }
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}
function totp(secret) {
  const counter = Math.floor(Date.now() / 1000 / 30);
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const digest = crypto.createHmac("sha1", base32Decode(secret)).update(buf).digest();
  const offset = digest[digest.length - 1] & 15;
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, "0");
}
function slug(text) {
  return String(text).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 55) || "pagina";
}
function rating(ms) {
  return ms <= 500 ? "excelente" : ms <= 1000 ? "bom" : ms <= 2000 ? "atenção" : "lento";
}
async function ready(page, timeout = 15000) {
  const t0 = Date.now();
  await page.waitForFunction(() => {
    const main = document.querySelector("main");
    return (main?.innerText || document.body.innerText || "").trim().length > 20;
  }, null, { timeout }).catch(() => {});
  await page.waitForTimeout(300);
  return Date.now() - t0;
}
async function shot(page, report, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  report.screenshots.push(file);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, ignoreHTTPSErrors: true });
  const page = await context.newPage();
  const consoleErrors = [], pageErrors = [], httpErrors = [], apiTimings = [];
  page.on("console", msg => { if (msg.type() === "error") consoleErrors.push({ url: page.url(), text: msg.text().slice(0, 1200) }); });
  page.on("pageerror", err => pageErrors.push({ url: page.url(), text: String(err).slice(0, 1200) }));
  page.on("response", res => {
    const url = res.url(), status = res.status();
    if (url.includes("/api/")) {
      const timing = res.request().timing();
      apiTimings.push({ url: url.replace(BASE, ""), status, ms: Math.max(0, Math.round(timing.responseEnd || 0)) });
    }
    if (status >= 400) httpErrors.push({ url, status });
  });
  const report = {
    generated_at: new Date().toISOString(), base_url: BASE,
    accessibility_issues: [], login: {}, transitions: [], interactions: [], responsive: [], screenshots: [],
    console_errors: consoleErrors, page_errors: pageErrors, http_errors: httpErrors, api_timings: apiTimings,
  };

  try {
    let t0 = Date.now();
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.locator('input[type="email"]').waitFor({ state: "visible", timeout: 20000 });
    report.login.initial_render_ms = Date.now() - t0;
    const labels = await page.evaluate(() => [...document.querySelectorAll("label")].map(label => ({
      text: label.textContent?.trim(), htmlFor: label.htmlFor,
      nestedInput: Boolean(label.querySelector("input")),
    })));
    for (const label of labels.filter(x => x.text && !x.htmlFor && !x.nestedInput)) {
      report.accessibility_issues.push({ page: "/login", issue: `Label sem associação semântica: ${label.text}` });
    }
    await shot(page, report, "01-login-desktop");

    await page.locator('input[type="email"]').fill(EMAIL);
    await page.locator('input[type="password"]').fill(PASSWORD);
    t0 = Date.now();
    await page.locator('button[type="submit"]').click();
    await page.locator('input[inputmode="numeric"]').waitFor({ state: "visible", timeout: 15000 });
    report.login.password_step_ms = Date.now() - t0;
    await page.locator('input[inputmode="numeric"]').fill(totp(TOTP_SECRET));
    t0 = Date.now();
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(url => !url.pathname.startsWith("/login"), { timeout: 30000 });
    await ready(page, 20000);
    report.login.totp_to_dashboard_ms = Date.now() - t0;
    report.login.total_perceived_ms = report.login.password_step_ms + report.login.totp_to_dashboard_ms;
    report.login.rating = rating(report.login.total_perceived_ms);
    await shot(page, report, "02-dashboard-desktop");

    const globalInteractions = [
      ["busca_global", async () => { await page.locator("header button").filter({ has: page.locator("svg") }).nth(1).click().catch(async () => page.keyboard.press("Control+K")); await page.keyboard.press("Escape"); }],
      ["privacidade", async () => { const b = page.getByRole("button", { name: /modo privacidade/i }).first(); await b.click(); await b.click(); }],
      ["tema", async () => page.getByRole("button", { name: /Alternar tema/ }).click()],
      ["novo_caso", async () => { await page.getByRole("button", { name: "Novo caso" }).click(); await page.locator('[role="menu"]').waitFor(); report.new_case_options = await page.locator('[role="menuitem"]').allTextContents(); await page.keyboard.press("Escape"); }],
    ];
    for (const [name, fn] of globalInteractions) {
      t0 = Date.now();
      try { await fn(); report.interactions.push({ name, status: "ok", ms: Date.now() - t0 }); }
      catch (e) { report.interactions.push({ name, status: "falha", ms: Date.now() - t0, error: String(e).slice(0, 500) }); }
    }

    const mais = page.getByRole("button", { name: /Mais \/ Avançado/ });
    if (await mais.count() && await mais.getAttribute("aria-expanded") !== "true") await mais.click();
    const links = await page.locator("aside a.sidebar-nav-item").evaluateAll(nodes => nodes.map(node => ({
      label: (node.querySelector("span.block")?.textContent || node.textContent || "").trim(),
      href: node.getAttribute("href"),
    })).filter(x => x.href));
    const unique = [...new Map(links.map(x => [x.href, x])).values()];
    const important = new Set(["/", "/clientes", "/casos", "/atividades", "/documentos", "/pecas", "/ia", "/areas-de-atuacao", "/financeiro", "/configuracoes"]);
    for (const item of unique) {
      const link = page.locator(`aside a.sidebar-nav-item[href="${item.href}"]`).first();
      if (!await link.count()) continue;
      const before = httpErrors.length;
      t0 = Date.now();
      try {
        await link.scrollIntoViewIfNeeded();
        await link.click();
        await page.waitForTimeout(100);
        const waitMs = await ready(page);
        const ms = Date.now() - t0;
        const text = await page.locator("main").innerText().catch(() => "");
        const broken = /algo deu errado|erro inesperado|página não encontrada|não foi possível carregar/i.test(text);
        report.transitions.push({ label: item.label, href: item.href, perceived_ms: ms, ready_wait_ms: waitMs, rating: rating(ms), rendered_chars: text.trim().length, broken, new_http_errors: httpErrors.slice(before) });
        if (important.has(item.href)) await shot(page, report, `nav-${slug(item.label)}-${slug(item.href)}`);
      } catch (e) {
        report.transitions.push({ label: item.label, href: item.href, perceived_ms: Date.now() - t0, rating: "falha", broken: true, error: String(e).slice(0, 700) });
      }
    }

    if (fs.existsSync(AI_REPORT)) {
      const ai = JSON.parse(fs.readFileSync(AI_REPORT, "utf8"));
      const caseId = ai?.ids?.case_id;
      if (caseId) {
        t0 = Date.now();
        await page.goto(`${BASE}/casos/${caseId}`, { waitUntil: "domcontentloaded", timeout: 30000 });
        await ready(page, 20000);
        const ms = Date.now() - t0;
        report.transitions.push({ label: "Caso fictício IA", href: `/casos/${caseId}`, perceived_ms: ms, rating: rating(ms), broken: false });
        await shot(page, report, "caso-ficticio-ia");
        for (const section of ["Visão", "Atividades", "Arquivos", "Estratégia", "Financeiro"]) {
          const sectionLink = page.getByRole("link", { name: new RegExp(section, "i") }).first();
          if (!await sectionLink.count()) continue;
          const s = Date.now();
          try { await sectionLink.click(); await ready(page); report.interactions.push({ name: `caso_${slug(section)}`, status: "ok", ms: Date.now() - s, url: page.url() }); }
          catch (e) { report.interactions.push({ name: `caso_${slug(section)}`, status: "falha", error: String(e).slice(0, 400) }); }
        }
      }
      await page.goto(`${BASE}/pecas`, { waitUntil: "domcontentloaded", timeout: 30000 });
      await ready(page, 20000);
      const marker = ai?.marker || "HOMOLOG-FICTICIO-IA";
      report.interactions.push({ name: "localizar_peca_ia", status: await page.getByText(new RegExp(marker)).count() ? "ok" : "falha" });
      await shot(page, report, "pecas-fila-pos-ia");
    }

    for (const vp of [{ name: "mobile", width: 375, height: 812 }, { name: "tablet", width: 768, height: 1024 }]) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      for (const route of ["/", "/casos", "/pecas"]) {
        await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
        await ready(page);
        const dims = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: innerWidth, scrollHeight: document.documentElement.scrollHeight }));
        const overflow = dims.scrollWidth - dims.innerWidth;
        report.responsive.push({ viewport: vp.name, route, ...dims, overflow_x: overflow, status: overflow <= 1 ? "ok" : "falha" });
        await shot(page, report, `${vp.name}-${slug(route)}`);
        const open = page.getByRole("button", { name: "Abrir menu" });
        if (await open.count()) {
          await open.click(); await page.waitForTimeout(150); await shot(page, report, `${vp.name}-${slug(route)}-menu`);
          await page.getByRole("button", { name: "Fechar menu" }).first().click().catch(() => {});
        }
      }
    }

    report.summary = {
      routes_total: report.transitions.length,
      routes_broken: report.transitions.filter(x => x.broken || x.rating === "falha").length,
      routes_slow_over_2s: report.transitions.filter(x => x.perceived_ms > 2000).length,
      console_errors: consoleErrors.length,
      page_errors: pageErrors.length,
      http_errors: httpErrors.length,
      responsive_failures: report.responsive.filter(x => x.status === "falha").length,
      accessibility_issues: report.accessibility_issues.length,
    };
  } finally {
    fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
    await browser.close();
  }
  console.log(JSON.stringify(report.summary));
}

main().catch(error => {
  fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify({ generated_at: new Date().toISOString(), fatal_error: String(error), stack: error?.stack }, null, 2));
  console.error(error);
  process.exit(1);
});
