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

const consoleErrors = [];
let collectConsoleErrors = true;
page.on("console", (msg) => {
  if (collectConsoleErrors && msg.type() === "error") consoleErrors.push(msg.text());
});

try {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 30000 });
  await page.getByRole("heading", { name: "Entrar no EJC" }).waitFor({ timeout: 10000 });
  assert(await page.locator('input[type="email"]').isVisible(), "campo e-mail invisível");
  assert(await page.locator('input[type="password"]').isVisible(), "campo senha invisível");
  assert(await page.locator('button[type="submit"]').isVisible(), "botão de login invisível");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  assert(await page.locator('input[type="email"]').isVisible(), "login não responsivo em viewport móvel");

  assert(consoleErrors.length === 0, `erros de console no login: ${consoleErrors.join(" | ")}`);
  collectConsoleErrors = false;

  await page.goto(`${BASE_URL}/clientes`, { waitUntil: "networkidle", timeout: 30000 });
  await page.waitForURL("**/login", { timeout: 10000 });
  assert(page.url().endsWith("/login"), "rota protegida não redirecionou para /login");


  console.log(JSON.stringify({
    status: "success",
    checks: ["login-render", "mobile-viewport", "protected-route-redirect", "console-errors"],
    base_url: BASE_URL,
  }));
} finally {
  await browser.close();
}
