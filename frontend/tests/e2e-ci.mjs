import { chromium } from "playwright";

const BASE_URL = process.env.EJC_BASE_URL || "http://127.0.0.1:4173";

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

await page.route("**/api/auth/refresh", (route) =>
  route.fulfill({ status: 401, contentType: "application/json", body: '{"detail":"CI unauthenticated"}' }),
);

const browserErrors = [];
page.on("pageerror", (error) => browserErrors.push(`pageerror: ${error.message}`));
page.on("requestfailed", (request) => {
  browserErrors.push(`requestfailed: ${request.url()} ${request.failure()?.errorText || ""}`);
});
page.on("response", (response) => {
  const status = response.status();
  const url = response.url();
  if (status < 400) return;
  if (status === 401 && url.includes("/api/auth/refresh")) return;
  browserErrors.push(`http ${status}: ${url}`);
});
page.on("console", (msg) => {
  if (msg.type() !== "error") return;
  const text = msg.text();
  if (text.includes("Failed to load resource") && text.includes("401")) return;
  browserErrors.push(`console: ${text}`);
});

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 30000 });
  await page.getByRole("heading", { name: "Entrar no escritório" }).waitFor({ timeout: 10000 });
  assert(await page.locator('input[type="email"]').isVisible(), "campo e-mail invisível");
  assert(await page.locator('input[type="password"]').isVisible(), "campo senha invisível");
  assert(await page.locator('button[type="submit"]').isVisible(), "botão de login invisível");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  const mobileEmail = page.locator('input[type="email"]');
  await mobileEmail.waitFor({ state: "visible", timeout: 5000 });
  assert(await mobileEmail.isVisible(), "login não responsivo em viewport móvel");

  await page.goto(`${BASE_URL}/clientes`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForURL("**/login", { timeout: 10000 });
  assert(page.url().endsWith("/login"), "rota protegida não redirecionou para /login");
  assert(browserErrors.length === 0, `erros inesperados do browser: ${browserErrors.join(" | ")}`);

  console.log(JSON.stringify({
    status: "success",
    checks: ["login-render", "mobile-viewport", "protected-route-redirect", "browser-errors"],
    base_url: BASE_URL,
  }));
} finally {
  await browser.close();
}
