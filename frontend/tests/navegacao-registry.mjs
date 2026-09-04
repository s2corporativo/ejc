// Suíte de navegação do moduleRegistry — dirige Chromium real contra uma
// instância viva do EJC (dev server ou build servido com proxy para a API),
// faz login real na UI e visita TODAS as rotas de STAFF_ROUTES e todos os
// redirects de LEGACY_REDIRECTS, coletando erros de console, pageerrors,
// respostas /api/ >= 500 e telas brancas.
//
// Uso:
//   cd frontend && npm run dev            # (ou sirva o build com proxy /api)
//   EJC_NAV_EMAIL=alguem@escritorio.adv.br \
//   EJC_NAV_PASSWORD='...' \
//   node tests/navegacao-registry.mjs
//
// Env:
//   EJC_NAV_BASE       base da UI (default http://localhost:5173)
//   EJC_NAV_EMAIL      e-mail de login (obrigatório — sem ele: exit 2)
//   EJC_NAV_PASSWORD   senha de login (obrigatória — sem ela: exit 2)
//   EJC_NAV_CASE_ID    valor para segmentos :id (sem ele a rota é pulada)
//   EJC_NAV_CLIENT_ID  valor para segmentos :clientId (sem ele a rota é pulada)
//   PLAYWRIGHT_BROWSERS_PATH  default /opt/pw-browsers (Chromium instalado)
//
// Saída: resumo por rota no stdout + JSON em tests/output/navegacao-registry.json.
// Exit 0 = ok; 1 = tela branca, pageerror ou resposta /api/ 5xx em alguma
// rota (erros de console apenas são listados); 2 = pré-condição ausente
// (credencial, Chromium, dev server fora do ar, falha de login).
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

process.env.PLAYWRIGHT_BROWSERS_PATH ||= "/opt/pw-browsers";
const { chromium } = await import("playwright");

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REGISTRY = path.resolve(
  __dirname,
  "..",
  "src",
  "config",
  "moduleRegistry.tsx",
);
const OUT_DIR = path.resolve(__dirname, "output");
const OUT_JSON = path.join(OUT_DIR, "navegacao-registry.json");

const BASE = (process.env.EJC_NAV_BASE || "http://localhost:5173").replace(
  /\/$/,
  "",
);
const EMAIL = process.env.EJC_NAV_EMAIL;
const PASSWORD = process.env.EJC_NAV_PASSWORD;
const CASE_ID = process.env.EJC_NAV_CASE_ID || "";
const CLIENT_ID = process.env.EJC_NAV_CLIENT_ID || "";
const HOJE = new Date().toISOString().slice(0, 10);

if (!EMAIL || !PASSWORD) {
  console.error(
    "[navegacao-registry] Credenciais ausentes: defina EJC_NAV_EMAIL e " +
      "EJC_NAV_PASSWORD no ambiente. Este script nunca inventa senha.",
  );
  process.exit(2);
}

let CHROMIUM = process.env.PW_CHROMIUM || chromium.executablePath();
if (!CHROMIUM || !existsSync(CHROMIUM)) {
  const fallback = "/opt/pw-browsers/chromium";
  if (existsSync(fallback)) CHROMIUM = fallback;
}
if (!CHROMIUM || !existsSync(CHROMIUM)) {
  console.error(
    "[navegacao-registry] Chromium não encontrado. Defina " +
      "PLAYWRIGHT_BROWSERS_PATH (ex.: /opt/pw-browsers) ou PW_CHROMIUM.",
  );
  process.exit(2);
}

// ── Extração estática das rotas (regex — não importa o .tsx) ─────────────────
function extrairRotas() {
  const fonte = readFileSync(REGISTRY, "utf8");
  const inicioStaff = fonte.indexOf("export const STAFF_ROUTES");
  const inicioLegacy = fonte.indexOf("export const LEGACY_REDIRECTS");
  if (inicioStaff < 0 || inicioLegacy < 0) {
    console.error(
      "[navegacao-registry] STAFF_ROUTES/LEGACY_REDIRECTS não encontrados em " +
        REGISTRY,
    );
    process.exit(2);
  }
  const blocoStaff = fonte.slice(inicioStaff, inicioLegacy);
  const blocoLegacy = fonte.slice(inicioLegacy);

  const staff = [...blocoStaff.matchAll(/^\s*path:\s*"([^"]+)"/gm)].map(
    (m) => m[1],
  );
  const legacy = [...blocoLegacy.matchAll(/^\s*from:\s*"([^"]+)"/gm)].map(
    (m) => m[1],
  );
  return { staff, legacy };
}

// Substitui segmentos dinâmicos; retorna null quando a rota deve ser pulada.
function resolverRota(rota) {
  if (rota.includes("*")) return { url: null, motivo: "curinga" };
  let url = rota;
  const subst = {
    ":id": CASE_ID,
    ":clientId": CLIENT_ID,
    ":slug": "civil",
    ":date": HOJE,
  };
  for (const [seg, valor] of Object.entries(subst)) {
    if (!url.includes(seg)) continue;
    if (!valor) {
      return {
        url: null,
        motivo: `sem valor para ${seg} (defina ${
          seg === ":id" ? "EJC_NAV_CASE_ID" : "EJC_NAV_CLIENT_ID"
        })`,
      };
    }
    url = url.replaceAll(seg, valor);
  }
  if (/:[A-Za-z]/.test(url)) {
    return { url: null, motivo: `segmento dinâmico desconhecido em ${rota}` };
  }
  return { url, motivo: null };
}

// ── Execução ─────────────────────────────────────────────────────────────────
async function login(page) {
  await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded" });
  const email = page.locator('input[type="email"]');
  await email.waitFor({ timeout: 15000 });
  await email.fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').click();

  // 2FA (TOTP) não é suportado por este script — sem código não há como seguir.
  const otp = page.locator('input[autocomplete="one-time-code"]');
  const resultado = await Promise.race([
    page
      .waitForFunction(() => !document.querySelector('input[type="password"]'), {
        timeout: 20000,
      })
      .then(() => "ok")
      .catch(() => "timeout"),
    otp
      .waitFor({ timeout: 20000 })
      .then(() => "2fa")
      .catch(() => "timeout"),
  ]);
  if (resultado === "2fa") {
    console.error(
      "[navegacao-registry] A conta exige 2FA (TOTP) — use uma conta de " +
        "teste sem 2FA.",
    );
    process.exit(2);
  }
  if (resultado !== "ok") {
    console.error(
      "[navegacao-registry] Login não concluiu em 20s — verifique credenciais " +
        "e se o backend está no ar.",
    );
    process.exit(2);
  }
}

async function main() {
  const { staff, legacy } = extrairRotas();
  const rotas = [
    ...staff.map((r) => ({ rota: r, origem: "staff" })),
    ...legacy.map((r) => ({ rota: r, origem: "legacy" })),
  ];
  console.log(
    `[navegacao-registry] ${staff.length} rotas STAFF + ${legacy.length} ` +
      `redirects legados · base ${BASE}`,
  );

  const browser = await chromium.launch({ executablePath: CHROMIUM });
  const context = await browser.newContext({
    viewport: { width: 1366, height: 900 },
  });
  const page = await context.newPage();

  // Coletores por visita — religados a cada rota.
  let consoleErrors = [];
  let pageErrors = [];
  let api5xx = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => pageErrors.push(String(error)));
  page.on("response", (response) => {
    const url = response.url();
    if (url.includes("/api/") && response.status() >= 500) {
      api5xx.push(`${response.status()} ${url}`);
    }
  });

  // Ping rápido: dev server fora do ar é pré-condição, não falha de rota.
  try {
    await page.goto(`${BASE}/`, { waitUntil: "domcontentloaded", timeout: 15000 });
  } catch (error) {
    console.error(
      `[navegacao-registry] Base ${BASE} inacessível (${error.message}). ` +
        "Suba o dev server (npm run dev) ou aponte EJC_NAV_BASE.",
    );
    await browser.close();
    process.exit(2);
  }

  await login(page);
  console.log("[navegacao-registry] login OK — visitando rotas…\n");

  const resultados = [];
  const puladas = [];
  for (const { rota, origem } of rotas) {
    const { url, motivo } = resolverRota(rota);
    if (!url) {
      puladas.push({ rota, origem, motivo });
      console.log(`  SKIP ${rota} — ${motivo}`);
      continue;
    }

    consoleErrors = [];
    pageErrors = [];
    api5xx = [];
    let bodyLength = 0;
    let navFalhou = null;
    try {
      await page.goto(`${BASE}${url}`, {
        waitUntil: "networkidle",
        timeout: 30000,
      });
      await page.waitForTimeout(400); // settle de lazy imports/redirects
      bodyLength = await page.evaluate(
        () => (document.body?.innerText || "").trim().length,
      );
    } catch (error) {
      navFalhou = String(error?.message || error);
    }

    const telaBranca = !navFalhou && bodyLength < 20;
    const falhou = Boolean(
      navFalhou || telaBranca || pageErrors.length || api5xx.length,
    );
    const status = navFalhou
      ? "navegacao_falhou"
      : telaBranca
        ? "tela_branca"
        : falhou
          ? "falha"
          : "ok";

    resultados.push({
      rota,
      origem,
      url,
      status,
      bodyLength,
      navFalhou,
      consoleErrors,
      pageErrors,
      api5xx,
    });

    const extras = [];
    if (consoleErrors.length) extras.push(`${consoleErrors.length} console.error`);
    if (pageErrors.length) extras.push(`${pageErrors.length} pageerror`);
    if (api5xx.length) extras.push(`${api5xx.length}x 5xx`);
    console.log(
      `  ${status === "ok" ? "OK  " : "FAIL"} ${url}` +
        (extras.length ? ` — ${extras.join(", ")}` : "") +
        (navFalhou ? ` — ${navFalhou}` : ""),
    );
  }

  await browser.close();

  const falhas = resultados.filter((item) => item.status !== "ok");
  const soConsole = resultados.filter(
    (item) => item.status === "ok" && item.consoleErrors.length,
  );

  mkdirSync(OUT_DIR, { recursive: true });
  const resumo = {
    gerado_em: new Date().toISOString(),
    base: BASE,
    total_rotas: rotas.length,
    visitadas: resultados.length,
    puladas,
    falhas: falhas.length,
    rotas_com_console_error: soConsole.map((item) => item.rota),
    resultados,
  };
  writeFileSync(OUT_JSON, JSON.stringify(resumo, null, 2));
  console.log(`\n[navegacao-registry] resumo gravado em ${OUT_JSON}`);

  if (soConsole.length) {
    console.log(
      `\nAVISO — rotas com console.error (não bloqueia):\n - ` +
        soConsole
          .map((i) => `${i.url}: ${i.consoleErrors.slice(0, 3).join(" | ")}`)
          .join("\n - "),
    );
  }
  if (falhas.length) {
    console.error(
      `\nNAVEGAÇÃO: FALHOU (${falhas.length} rota(s))\n - ` +
        falhas
          .map(
            (i) =>
              `${i.url} [${i.status}] ` +
              [...i.pageErrors, ...i.api5xx, i.navFalhou]
                .filter(Boolean)
                .slice(0, 3)
                .join(" | "),
          )
          .join("\n - "),
    );
    process.exit(1);
  }
  console.log(
    `\nNAVEGAÇÃO: OK — ${resultados.length} rotas sem tela branca, ` +
      `pageerror ou 5xx (${puladas.length} puladas).`,
  );
}

main().catch((error) => {
  console.error("[navegacao-registry] erro:", error);
  process.exit(1);
});
