import { expect, test, type Page } from "@playwright/test";

const visualUser = {
  id: "00000000-0000-0000-0000-000000000001",
  full_name: "Clovis José Soares",
  email: "clovis@depaulateixeira.adv.br",
  role: "socio",
  is_active: true,
  oab_number: "OAB/MG",
  permissions: [],
};

const areas = [
  "Trabalhista",
  "Cível",
  "Empresarial",
  "Consumidor",
  "Ambiental",
  "Administrativo",
];

const statuses = ["aberto", "em_instrucao", "em_producao", "protocolado"];

const cases = Array.from({ length: 28 }, (_, index) => ({
  id: `case-${index + 1}`,
  titulo: [
    "Defesa em reclamação trabalhista",
    "Revisão contratual empresarial",
    "Ação indenizatória",
    "Procedimento ambiental",
    "Recurso administrativo",
  ][index % 5],
  numero_interno: `EJC-2026-${String(index + 1).padStart(4, "0")}`,
  area: areas[index % areas.length],
  status: statuses[index % statuses.length],
  archived_at: null,
}));

const deadlines = [
  {
    id: "prazo-1",
    titulo: "Interposição de recurso ordinário",
    case_title: "Almeida x Indústria Horizonte",
    data_prazo: "2026-08-05",
    dias_restantes: 1,
  },
  {
    id: "prazo-2",
    titulo: "Apresentação de contestação",
    case_title: "Construtora Vale Verde",
    data_prazo: "2026-08-07",
    dias_restantes: 3,
  },
  {
    id: "prazo-3",
    titulo: "Manifestação sobre laudo",
    case_title: "Silva x Município de Betim",
    data_prazo: "2026-08-10",
    dias_restantes: 6,
  },
];

const movements = [
  {
    id: "mov-1",
    case_id: "case-1",
    tipo: "publicacao",
    descricao: "Intimação disponibilizada no Diário de Justiça",
    quando: "2026-08-04T08:42:00",
    case_titulo: "Almeida x Indústria Horizonte",
    numero_interno: "EJC-2026-0001",
  },
  {
    id: "mov-2",
    case_id: "case-2",
    tipo: "peticao",
    descricao: "Contestação revisada e liberada para protocolo",
    quando: "2026-08-04T08:10:00",
    case_titulo: "Construtora Vale Verde",
    numero_interno: "EJC-2026-0002",
  },
  {
    id: "mov-3",
    case_id: "case-3",
    tipo: "documento",
    descricao: "Novo documento anexado ao dossiê do processo",
    quando: "2026-08-03T17:35:00",
    case_titulo: "Silva x Município de Betim",
    numero_interno: "EJC-2026-0003",
  },
  {
    id: "mov-4",
    case_id: "case-4",
    tipo: "prazo",
    descricao: "Prazo processual confirmado pelo advogado responsável",
    quando: "2026-08-03T15:20:00",
    case_titulo: "Grupo Comercial Minas",
    numero_interno: "EJC-2026-0004",
  },
  {
    id: "mov-5",
    case_id: "case-5",
    tipo: "audiencia",
    descricao: "Audiência de conciliação incluída na agenda",
    quando: "2026-08-03T13:05:00",
    case_titulo: "Ferreira x Serviços Urbanos",
    numero_interno: "EJC-2026-0005",
  },
];

const tasks = [
  { id: "task-1", titulo: "Revisar documentos", status: "pendente" },
  { id: "task-2", titulo: "Conferir cálculos", status: "em_andamento" },
  { id: "task-3", titulo: "Preparar reunião", status: "pendente" },
  { id: "task-4", titulo: "Protocolar recurso", status: "pendente" },
  { id: "task-5", titulo: "Atualizar cliente", status: "concluida" },
];

const agenda = [
  {
    id: "agenda-1",
    tipo: "audiencia",
    titulo: "Audiência de instrução",
    caso_titulo: "Almeida x Indústria Horizonte",
    data_evento: "2026-08-06",
    hora: "09:30",
    concluido: false,
  },
  {
    id: "agenda-2",
    tipo: "reuniao",
    titulo: "Reunião com cliente",
    caso_titulo: "Construtora Vale Verde",
    data_evento: "2026-08-08",
    hora: "14:00",
    concluido: false,
  },
  {
    id: "agenda-3",
    tipo: "diligencia",
    titulo: "Diligência no fórum",
    caso_titulo: "Silva x Município de Betim",
    data_evento: "2026-08-11",
    hora: "10:00",
    concluido: false,
  },
];

async function installVisualFixtures(page: Page) {
  await page.addInitScript((user) => {
    localStorage.setItem("ejc_access", "visual-validation-token");
    localStorage.setItem("ejc_user", JSON.stringify(user));
    localStorage.setItem("ejc_privacy_mode", "false");
    localStorage.setItem("ejc_onboarding_v1", "dispensado");
    localStorage.setItem("ejc_menu_groups", JSON.stringify({}));
  }, visualUser);

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api\/v1/, "");

    let payload: unknown = { items: [], data: [], total: 0 };

    if (path === "/users/me/security") {
      payload = { permissions: [] };
    } else if (path === "/users/me") {
      payload = visualUser;
    } else if (path.startsWith("/dashboard/")) {
      payload = {
        casos: { total: cases.length, ativos: cases.length },
        degradado: [],
      };
    } else if (path.startsWith("/deadlines/")) {
      payload = deadlines;
    } else if (path.startsWith("/movimentos/recentes")) {
      payload = movements;
    } else if (path.startsWith("/cases/")) {
      payload = cases;
    } else if (path.startsWith("/tasks/")) {
      payload = tasks;
    } else if (path.startsWith("/agenda-eventos/")) {
      payload = agenda;
    } else if (path.startsWith("/notifications/")) {
      payload = { data: [], nao_lidas: 2 };
    } else if (
      path.includes("ia-status") ||
      path.includes("/ai/status") ||
      path.includes("/health")
    ) {
      payload = { disponivel: true, status: "ok" };
    } else if (path.includes("module-lifecycle")) {
      payload = { modules: {}, items: [] };
    }

    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });
}

const sizes = [
  { name: "1440", width: 1440, height: 1000 },
  { name: "1366", width: 1366, height: 900 },
  { name: "1024", width: 1024, height: 900 },
  { name: "768", width: 768, height: 1024 },
  { name: "390", width: 390, height: 844 },
  { name: "360", width: 360, height: 800 },
];

for (const size of sizes) {
  test(`dashboard v2 em ${size.name}px`, async ({ browser }, testInfo) => {
    const context = await browser.newContext({
      viewport: { width: size.width, height: size.height },
      deviceScaleFactor: 1,
      locale: "pt-BR",
      timezoneId: "America/Sao_Paulo",
      colorScheme: "light",
    });
    const page = await context.newPage();
    await installVisualFixtures(page);

    await page.goto("http://127.0.0.1:4173/", {
      waitUntil: "networkidle",
    });
    await expect(page.locator(".ejc-dashboard-v2")).toBeVisible();
    await expect(page.locator(".ejc-kpi-card")).toHaveCount(4);
    await page.screenshot({
      path: testInfo.outputPath(`dashboard-${size.name}.png`),
      fullPage: true,
    });

    if (size.width <= 390) {
      await page.getByRole("button", { name: "Abrir menu" }).click();
      await expect(page.locator("aside")).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath(`dashboard-${size.name}-menu.png`),
        fullPage: false,
      });
    }

    await context.close();
  });
}
