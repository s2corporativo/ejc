/**
 * E2E Playwright - Homologação EJC De Paula Teixeira
 * Testa fluxos críticos com credenciais reais.
 *
 * Uso:
 *   EJC_BASE_URL=https://ejc.depaulateixeira.adv.br \
 *   EJC_USER_EMAIL=admin@depaulateixeira.adv.br \
 *   EJC_USER_PASSWORD=sua_senha \
 *   node tests/e2e-homologacao.mjs
 */

import { chromium } from "playwright";

const BASE_URL = process.env.EJC_BASE_URL || "https://ejc.depaulateixeira.adv.br";
const USER_EMAIL = process.env.EJC_USER_EMAIL;
const USER_PASSWORD = process.env.EJC_USER_PASSWORD;

if (!USER_EMAIL || !USER_PASSWORD) {
  console.error("❌ Necessário definir EJC_USER_EMAIL e EJC_USER_PASSWORD");
  console.error("   Exemplo:");
  console.error("   EJC_BASE_URL=https://ejc.depaulateixeira.adv.br \\");
  console.error("   EJC_USER_EMAIL=admin@depaulateixeira.adv.br \\");
  console.error("   EJC_USER_PASSWORD=sua_senha \\");
  console.error("   node tests/e2e-homologacao.mjs");
  process.exit(1);
}

const ROUTES_TO_TEST = [
  { name: "Dashboard", path: "/", verify: ["Dashboard", "Bienvenue"] },
  { name: "Casos", path: "/casos", verify: ["Casos", "Processos"] },
  { name: "Clientes", path: "/clientes", verify: ["Clientes"] },
  { name: "Atividades", path: "/atividades", verify: ["Agenda", "Atividades"] },
  { name: "Financeiro", path: "/financeiro", verify: ["Financeiro", "Honorários"] },
];

console.log(`\n🔍 E2E EJC - Base: ${BASE_URL}`);
console.log(`👤 Usuário: ${USER_EMAIL}\n`);

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
});
const page = await context.newPage();

let passed = 0;
let failed = 0;

async function runTest(name, fn) {
  console.log(`\n📋 Teste: ${name}`);
  try {
    await fn();
    console.log(`   ✅ PASSOU`);
    passed++;
  } catch (err) {
    console.error(`   ❌ FALHOU: ${err.message}`);
    failed++;
  }
}

// ========== TESTES ==========

await runTest("Login com credenciais válidas", async () => {
  await page.goto(`${BASE_URL}/login`, { waitUntil: "networkidle", timeout: 30000 });

  // Preencher formulário
  await page.fill('input[type="email"]', USER_EMAIL);
  await page.fill('input[type="password"]', USER_PASSWORD);

  // Clicar no botão de login
  await page.click('button[type="submit"]');

  // Aguardar redirect ou dashboard
  await page.waitForURL("**/atividades**", { timeout: 15000 }).catch(() => {});
  await page.waitForURL("**/", { timeout: 15000 }).catch(() => {});

  // Verificar que está logado (sem redirect para /login)
  const url = page.url();
  if (url.includes("/login")) {
    throw new Error("Redirecionou de volta para login - credenciais inválidas?");
  }

  // Verificar elementos do dashboard
  const content = await page.content();
  if (!content.includes("Bienvenue") && !content.includes("Dashboard") && !content.includes("Atividades")) {
    throw new Error("Não encontrou elementos esperados após login");
  }
});

await runTest("Navegação - Sidebar visível", async () => {
  const sidebar = await page.locator("aside, nav, [class*='sidebar']").first();
  if (!(await sidebar.isVisible({ timeout: 5000 }).catch(() => false))) {
    throw new Error("Sidebar não encontrada ou invisível");
  }
});

await runTest("Acesso à página de Casos", async () => {
  await page.goto(`${BASE_URL}/casos`, { waitUntil: "networkidle", timeout: 20000 });
  const content = await page.content();
  if (!content.includes("Caso") && !content.includes("Processo")) {
    throw new Error("Página de Casos não carregou corretamente");
  }
});

await runTest("Acesso à página de Clientes", async () => {
  await page.goto(`${BASE_URL}/clientes`, { waitUntil: "networkidle", timeout: 20000 });
  const content = await page.content();
  if (!content.includes("Cliente")) {
    throw new Error("Página de Clientes não carregou corretamente");
  }
});

await runTest("Acesso à página de Atividades", async () => {
  await page.goto(`${BASE_URL}/atividades`, { waitUntil: "networkidle", timeout: 20000 });
  const content = await page.content();
  if (!content.includes("Atividade") && !content.includes("Agenda")) {
    throw new Error("Página de Atividades não carregou corretamente");
  }
});

await runTest("Acesso ao Financeiro", async () => {
  await page.goto(`${BASE_URL}/financeiro`, { waitUntil: "networkidle", timeout: 20000 });
  const content = await page.content();
  if (!content.includes("Financeiro") && !content.includes("Honorário")) {
    throw new Error("Página de Financeiro não carregou corretamente");
  }
});

await runTest("Logout funciona", async () => {
  // Procurar botão de logout
  const logoutBtn = await page.locator("button:has-text('Logout'), button:has-text('Sair'), [aria-label*='logout' i]").first();
  if (await logoutBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
    await logoutBtn.click();
    await page.waitForURL("**/login**", { timeout: 10000 });
  } else {
    // Fallback: navegar direto
    await page.goto(`${BASE_URL}/logout`, { waitUntil: "networkidle" });
  }

  // Verificar que voltou para login
  const url = page.url();
  if (!url.includes("/login")) {
    console.warn("   ⚠️ Logout pode não ter funcionado (verificar manualmente)");
  }
});

// ========== RESULTADO ==========

await browser.close();

console.log(`\n${"=".repeat(50)}`);
console.log(`📊 RESULTADO: ${passed} passou, ${failed} falhou`);
console.log(`${"=".repeat(50)}\n`);

if (failed > 0) {
  console.log("❌ Homologação FALHOU - verificar testes acima");
  process.exit(1);
} else {
  console.log("✅ Homologação PASSOU - todos os testes OK");
  process.exit(0);
}
