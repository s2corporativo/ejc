import { spawn } from "node:child_process";
import process from "node:process";
import { chromium } from "playwright";

const HOST = "127.0.0.1";
const PORT = Number(process.env.EJC_PLAYWRIGHT_PORT || 4173);
const BASE_URL =
  process.env.EJC_PLAYWRIGHT_BASE_URL || `http://${HOST}:${PORT}`;

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitForPreview(timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs;
  let lastError;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(`${BASE_URL}/login`, {
        redirect: "manual",
        signal: AbortSignal.timeout(2000),
      });
      if (response.ok) return;
      lastError = new Error(`preview respondeu HTTP ${response.status}`);
    } catch (error) {
      lastError = error;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(
    `preview não ficou pronto em ${timeoutMs}ms: ${lastError?.message || "sem resposta"}`,
  );
}

async function noHorizontalOverflow(page, label) {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(
    overflow.scrollWidth <= overflow.clientWidth + 1,
    `${label}: overflow horizontal ${overflow.scrollWidth} > ${overflow.clientWidth}`,
  );
}

const preview = spawn(
  "npm",
  ["run", "preview", "--", "--host", HOST, "--port", String(PORT)],
  {
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env },
    detached: process.platform !== "win32",
  },
);

let previewLog = "";
for (const stream of [preview.stdout, preview.stderr]) {
  stream?.on("data", (chunk) => {
    previewLog += String(chunk);
    if (previewLog.length > 12000) previewLog = previewLog.slice(-12000);
  });
}

let browser;
const pageErrors = [];

try {
  await waitForPreview();
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(`${BASE_URL}/login`, {
    waitUntil: "networkidle",
    timeout: 30000,
  });

  assert(
    await page.getByRole("heading", { name: "Entrar no EJC" }).isVisible(),
    "login não exibiu o título esperado",
  );
  assert(
    await page.locator('input[type="email"]').isVisible(),
    "campo de e-mail não está visível",
  );
  assert(
    await page.locator('input[type="password"]').isVisible(),
    "campo de senha não está visível",
  );
  assert(
    await page.getByRole("button", { name: /Entrar/i }).isVisible(),
    "botão Entrar não está visível",
  );
  await noHorizontalOverflow(page, "desktop/login");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  await noHorizontalOverflow(page, "mobile/login");
  assert(
    await page.getByRole("heading", { name: "Entrar no EJC" }).isVisible(),
    "login mobile não está utilizável",
  );

  for (const path of ["/", "/casos", "/clientes", "/financeiro", "/entrada"]) {
    await page.goto(`${BASE_URL}${path}`, {
      waitUntil: "domcontentloaded",
      timeout: 20000,
    });
    await page.waitForURL("**/login", { timeout: 10000 });
    assert(
      new URL(page.url()).pathname === "/login",
      `rota protegida ${path} não redirecionou para /login`,
    );
  }

  await page.goto(`${BASE_URL}/login?motivo=senha-alterada`, {
    waitUntil: "networkidle",
    timeout: 20000,
  });
  assert(
    await page.getByRole("status").isVisible(),
    "feedback pós-troca de senha não está visível",
  );

  assert(
    pageErrors.length === 0,
    `erros JavaScript no navegador: ${pageErrors.join(" | ")}`,
  );

  console.log(
    JSON.stringify({
      status: "sucesso",
      gate: "playwright-secretless",
      base_url: BASE_URL,
      checks: {
        login_desktop: true,
        login_mobile: true,
        protected_routes_redirect: true,
        password_change_feedback: true,
        javascript_errors: 0,
      },
    }),
  );
} catch (error) {
  console.error("PLAYWRIGHT_GATE_FALHOU:", error?.stack || error);
  if (previewLog) console.error("PREVIEW_LOG:\n" + previewLog);
  process.exitCode = 1;
} finally {
  await browser?.close().catch(() => {});
  if (preview.exitCode === null) {
    try {
      if (process.platform === "win32") preview.kill("SIGTERM");
      else process.kill(-preview.pid, "SIGTERM");
    } catch {
      // processo já encerrado
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (preview.exitCode === null) {
    try {
      if (process.platform === "win32") preview.kill("SIGKILL");
      else process.kill(-preview.pid, "SIGKILL");
    } catch {
      // processo já encerrado
    }
  }
}
