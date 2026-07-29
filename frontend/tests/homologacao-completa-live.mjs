// Homologação de UI renderizada do EJC em Chromium real contra a stack ativa.
// Usa exclusivamente usuário e dados fictícios criados pelo workflow de QA.
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = process.env.SCREENSHOT_DIR || path.resolve(__dirname, "__out__/homologacao-live");
const REPORT_PATH = process.env.EJC_QA_BROWSER_REPORT || path.join(OUT, "browser_homologacao_report.json");
const BASE = (process.env.EJC_FRONTEND_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const EMAIL = required("EJC_TEST_EMAIL");
const PASSWORD = required("EJC_TEST_PASSWORD");
const TOTP_SECRET = required("EJC_TEST_TOTP_SECRET");
const AI_REPORT = process.env.EJC_AI_REPORT || path.resolve(__dirname, "../../qa/homologacao/reports/ia_peca_protocolavel_report.json");

fs.mkdirSync(OUT, { recursive: true });

function required(name) {
  const value = (process.env[name] || "").trim();
  if (!value) throw new Error(`Variável obrigatória ausente: ${name}`);
  return value;
}

function base32Decode(input) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const clean = input.toUpperCase().replace(/=+$/, "").replace(/\s+/g, "");
  let bits = "";
  for (const char of clean) {
    const idx = alphabet.indexOf(char);
    if (idx < 0) throw new Error("Segredo TOTP base32 inválido");
    bits += idx.toString(2).padStart(5, "0");
  }
  const bytes = [];
  for (let i = 0; i + 8 <= bits.length; i += 8) bytes.push(parseInt(bits.slice(i, i + 8), 2));
  return Buffer.from(bytes);
}

function totp(secret, when = Date.now()) {
  const counter = Math.floor(when / 1000 / 30);
  const buf = Buffer.alloc(8);
  buf.writeBigUInt64BE(BigInt(counter));
  const digest = crypto.createHmac("sha1", base32Decode(secret)).update(buf).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  const code = ((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, "0");
  return code;
}

function slug(text) {
  return text.toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60) || "pagina";
}

function rating(ms) {
  if (ms <= 500) return "excelente";
  if (ms <= 1000) return "bom";
  if (ms <= 2000) return "atenção";
  return "lento";
}

async function ready(page, timeout = 12000) {
  const started = Date.now();
  await page.waitForFunction(() => {
    const main = document.querySelector("main");
    const body = main?.innerText?.trim() || document.body.innerText.trim();
    return body.length > 20;
  }, null, { timeout }).catch(() => {});
  await page.waitForTimeout(250);
  return Date.now() - started;
}

async function screenshot(page, name, fullPage = true) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage });
  return file;
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, ignoreHTTPSErrors: true });
  const page = await context.newPage();
  const consoleErrors = [];
  const pageErrors = [];
  const httpErrors = [];
  const apiTimings = [];
  page.on("console", msg => { if (msg.type() === "error") consoleErrors.push({ url: page.url(), text: msg.text().slice(0, 1000) }); });
  page.on("pageerror", error => pageErrors.push({ url: page.url(), text: String(error).slice(0, 1000) }));
  page.on("response", response => {
    const status = response.status();
    const url = response.url();
    const timing = response.request().timing();
    if (url.includes("/api/")) apiTimings.push({ url: url.replace(BASE, ""), status, ms: Math.max(0, Math.round(timing.responseEnd || 0)) });
    if (status >= 400) httpErrors.push({ url, status });
  });

  const report = {
    generated_at: new Date().toISOString(),
    base_url: BASE,
    login: {},
    transitions: [],
    interactions: [],
    responsive: [],
    screenshots: [],
    console_errors: consoleErrors,
    page_errors: pageErrors,
    http_errors: httpErrors,
    api_timings: apiTimings,
  };

  try {
    const navStart = Date.now();
    await page.goto(`${BASE}/login`, { waitUntil: "domcontentloaded", timeout: 30000 });
    await ready(page);
    report.login.navigation_ms = Date.now() - navStart;
    report.screenshots.push(await screenshot(page, "01-login-desktop"));
    const perf = await page.evaluate(() => {
      const n = performance.getEntriesByType("navigation")[0];
      return n ? { dom_content_loaded_ms: Math.round(n.domContentLoadedEventEnd), load_ms: Math.round(n.loadEventEnd), transfer_bytes: n.transferSize } : null;
    });
    report.login.navigation_timing = perf;

    await page.getByLabel("E-mail").fill(EMAIL);
    await page.getByLabel("Senha").fill(PASSWORD);
    let started = Date.now();
    await page.getByRole("button", { name: /^Entrar/ }).click();
    await page.getByLabel("Código de autenticação").waitFor({ state: "visible", timeout: 15000 });
    report.login.password_step_ms = Date.now() - started;
    await page.getByLabel("Código de autenticação").fill(totp(TOTP_SECRET));
    started = Date.now();
    await page.getByRole("button", { name: /^Confirmar/ }).click();
    await page.waitForURL(url => !url.pathname.startsWith("/login"), { timeout: 30000 });
    await ready(page, 20000);
    report.login.totp_to_dashboard_ms = Date.now() - started;
    report.login.total_perceived_ms = report.login.password_step_ms + report.login.totp_to_dashboard_ms;
    report.login.rating = rating(report.login.total_perceived_ms);
    report.screenshots.push(await screenshot(page, "02-dashboard-desktop"));

    // Interações globais: busca, privacidade, tema e menu de novo caso.
    for (const interaction of [
      { name: "abrir_busca", run: async () => { await page.getByText("Buscar processos por parte, CPF ou número…").click(); await page.keyboard.press("Escape"); } },
      { name: "alternar_privacidade", run: async () => { const b = page.getByRole("button", { name: /Ativar modo privacidade|Desativar modo privacidade/ }); await b.click(); await b.click(); } },
      { name: "alternar_tema", run: async () => { await page.getByRole("button", { name: /Alternar tema/ }).click(); } },
      { name: "menu_novo_caso", run: async () => { await page.getByRole("button", { name: "Novo caso" }).click(); await page.getByRole("menu", { name: "Como abrir o novo caso" }).waitFor(); const items = await page.getByRole("menuitem").allTextContents(); report.interactions.push({ name: "opcoes_novo_caso", status: "ok", items }); await page.keyboard.press("Escape"); } },
    ]) {
      const t0 = Date.now();
      try { await interaction.run(); report.interactions.push({ name: interaction.name, status: "ok", ms: Date.now() - t0 }); }
      catch (e) { report.interactions.push({ name: interaction.name, status: "falha", ms: Date.now() - t0, erro: String(e).slice(0, 500) }); }
    }

    // Expande catálogo avançado e coleta todos os links efetivamente renderizados.
    const mais = page.getByRole("button", { name: /Mais \/ Avançado/ });
    if (await mais.count() && !(await mais.getAttribute("aria-expanded") === "true")) await mais.click();
    await page.waitForTimeout(200);
    const links = await page.locator("aside a.sidebar-nav-item").evaluateAll(nodes => nodes.map(node => ({
      label: (node.querySelector("span.block")?.textContent || node.textContent || "").trim(),
      href: node.getAttribute("href"),
    })).filter(item => item.href));
    const unique = [...new Map(links.map(item => [item.href, item])).values()];

    for (const item of unique) {
      const locator = page.locator(`aside a.sidebar-nav-item[href="${item.href}"]`).first();
      if (!(await locator.count())) continue;
      const t0 = Date.now();
      const beforeErrors = httpErrors.length;
      try {
        await locator.scrollIntoViewIfNeeded();
        await locator.click();
        await page.waitForURL(url => url.pathname === new URL(item.href, BASE).pathname || url.pathname.startsWith(new URL(item.href, BASE).pathname + "/"), { timeout: 12000 }).catch(() => {});
        const renderMs = await ready(page, 12000);
        const total = Date.now() - t0;
        const mainText = await page.locator("main").innerText().catch(() => "");
        const broken = /algo deu errado|erro inesperado|página não encontrada|não foi possível carregar/i.test(mainText);
        report.transitions.push({
          label: item.label,
          href: item.href,
          perceived_ms: total,
          ready_wait_ms: renderMs,
          rating: rating(total),
          rendered_chars: mainText.trim().length,
          broken,
          new_http_errors: httpErrors.slice(beforeErrors),
        });
        if (["/", "/clientes", "/casos", "/atividades", "/documentos", "/pecas", "/ia", "/areas-de-atuacao", "/financeiro", "/configuracoes"].includes(item.href)) {
          report.screenshots.push(await screenshot(page, `nav-${slug(item.label)}-${slug(item.href)}`));
        }
      } catch (e) {
        report.transitions.push({ label: item.label, href: item.href, perceived_ms: Date.now() - t0, rating: "falha", broken: true, erro: String(e).slice(0, 800) });
      }
    }

    // Caso e peça fictícios criados pelo teste real de IA.
    if (fs.existsSync(AI_REPORT)) {
      const ai = JSON.parse(fs.readFileSync(AI_REPORT, "utf8"));
      const caseId = ai?.ids?.case_id;
      const legalDocId = ai?.ids?.legal_doc_id;
      if (caseId) {
        const t0 = Date.now();
        await page.goto(`${BASE}/casos/${caseId}`, { waitUntil: "domcontentloaded", timeout: 30000 });
        await ready(page, 20000);
        report.transitions.push({ label: "Caso fictício IA", href: `/casos/${caseId}`, perceived_ms: Date.now() - t0, rating: rating(Date.now() - t0), rendered_chars: (await page.locator("main").innerText()).length });
        report.screenshots.push(await screenshot(page, "caso-ficticio-ia"));
        // Exercita as cinco macroáreas do caso por clique.
        for (const section of ["Visão", "Atividades", "Arquivos", "Estratégia", "Financeiro"]) {
          const link = page.getByRole("link", { name: new RegExp(`^${section}`) }).first();
          if (await link.count()) {
            const s = Date.now();
            try { await link.click(); await ready(page); report.interactions.push({ name: `caso_${slug(section)}`, status: "ok", ms: Date.now() - s, url: page.url() }); }
            catch (e) { report.interactions.push({ name: `caso_${slug(section)}`, status: "falha", erro: String(e).slice(0, 400) }); }
          }
        }
      }
      if (legalDocId) {
        await page.goto(`${BASE}/pecas`, { waitUntil: "domcontentloaded", timeout: 30000 });
        await ready(page, 20000);
        const marker = ai.marker || "HOMOLOG-FICTICIO-IA";
        const card = page.getByText(new RegExp(marker)).first();
        report.interactions.push({ name: "localizar_peca_ia_na_fila", status: await card.count() ? "ok" : "falha" });
        report.screenshots.push(await screenshot(page, "pecas-fila-pos-ia"));
      }
    }

    // Responsividade real autenticada: mobile e tablet em páginas essenciais.
    for (const vp of [
      { name: "mobile", width: 375, height: 812 },
      { name: "tablet", width: 768, height: 1024 },
    ]) {
      await page.setViewportSize({ width: vp.width, height: vp.height });
      for (const route of ["/", "/casos", "/pecas"]) {
        await page.goto(`${BASE}${route}`, { waitUntil: "domcontentloaded", timeout: 30000 });
        await ready(page, 15000);
        const dims = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth, scrollHeight: document.documentElement.scrollHeight }));
        const overflowX = dims.scrollWidth - dims.innerWidth;
        report.responsive.push({ viewport: vp.name, route, ...dims, overflow_x: overflowX, status: overflowX <= 1 ? "ok" : "falha" });
        report.screenshots.push(await screenshot(page, `${vp.name}-${slug(route)}`));
        const menu = page.getByRole("button", { name: "Abrir menu" });
        if (await menu.count()) { await menu.click(); await page.waitForTimeout(150); report.screenshots.push(await screenshot(page, `${vp.name}-${slug(route)}-menu`)); await page.getByRole("button", { name: "Fechar menu" }).first().click().catch(() => {}); }
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
    };
  } finally {
    fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
    await browser.close();
  }
  console.log(JSON.stringify(report.summary));
  if (report.summary?.routes_broken || report.summary?.page_errors || report.summary?.responsive_failures) process.exitCode = 2;
}

main().catch(error => {
  fs.mkdirSync(path.dirname(REPORT_PATH), { recursive: true });
  fs.writeFileSync(REPORT_PATH, JSON.stringify({ generated_at: new Date().toISOString(), fatal_error: String(error), stack: error?.stack }, null, 2));
  console.error(error);
  process.exit(1);
});
