// Integridade de navegação: moduleRegistry ↔ App.tsx.
//
// O App monta as rotas de staff DINAMICAMENTE via STAFF_ROUTES.map (com
// subPaths do mesmo módulo), o portal via PORTAL_ROUTES.map e os aliases via
// LEGACY_REDIRECTS.map — logo, "toda rota do registry está no App" é garantido
// POR CONSTRUÇÃO desde que esses três maps existam e usem module.path /
// redirect.from. Este teste trava exatamente isso e, no sentido inverso,
// garante que NENHUMA rota literal órfã seja adicionada ao App fora das
// exceções explícitas (públicas de autenticação + casco /portal).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  LEGACY_REDIRECTS,
  PORTAL_ROUTES,
  STAFF_ROUTES,
  portalNavHref,
} from "./moduleRegistry";
import { isFinanceTab } from "../pages/FinanceiroWorkspace";
import { isInteligenciaTab } from "../pages/InteligenciaWorkspace";
import { isCentralTab } from "../pages/Central";
import { isActivityView, isItemType } from "../pages/CentralAtividades";

// Fonte de verdade das abas/visões navegáveis por deep-link (?tab=/?view=) dos
// workspaces com sub-navegação por query param. Um LEGACY_REDIRECT que aponte
// para uma dessas rotas é validado contra o predicado REAL da respectiva tela —
// foi a ausência disso que deixou o `/nfse → /financeiro?tab=nfse` quebrado
// passar batido (a aba `nfse` nem existia no FinanceiroWorkspace).
type DeepLinkValidators = {
  tab?: (value: string | null) => boolean;
  view?: (value: string | null) => boolean;
  tipo?: (value: string | null) => boolean;
};
const WORKSPACE_DEEP_LINKS: Record<string, DeepLinkValidators> = {
  "/financeiro": { tab: isFinanceTab },
  "/inteligencia": { tab: isInteligenciaTab },
  "/atividades": { tab: isCentralTab, view: isActivityView, tipo: isItemType },
};

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const appSrc = readFileSync(join(SRC_DIR, "App.tsx"), "utf-8");

// ── Exceções explícitas: rotas montadas literalmente no App, FORA do registry ──
// Autenticação pública + jornadas de segurança autenticadas, mas sem menu:
export const PUBLIC_APP_ROUTES = [
  "/login",
  "/recuperar-senha",
  "/redefinir-senha",
  "/trocar-senha",
  "/configurar-2fa",
] as const;
// Subárvore do Portal do Cliente (PortalLayout, papel cliente_externo):
// rotas vivem em PORTAL_ROUTES (moduleRegistry) e o App só monta o casco
// /portal literal. Este espelho trava os hrefs absolutos esperados.
export const PORTAL_APP_ROUTES = [
  "/portal",
  "/portal/casos",
  "/portal/casos/:id",
  "/portal/financeiro",
  "/portal/assinaturas",
  "/portal/mensagens",
  "/portal/documentos",
] as const;
// Subrotas contextuais de módulos existentes: não viram módulo/menu independente.
export const CONTEXTUAL_STAFF_APP_ROUTES = [
  "/ia-governanca/provedores", // painel técnico dentro da Governança da IA
] as const;
// Aliases legados com segmento dinâmico: LEGACY_REDIRECTS só suporta `to`
// estático (Navigate não interpola :params), então precisam de uma <Route>
// dedicada no App montando um pequeno redirect component em vez de entrar
// no map genérico.
export const DYNAMIC_LEGACY_APP_ROUTES = [
  "/clientes/:clientId/dossie", // alias removido de STAFF_ROUTES; redireciona para /clientes/:clientId
  "/ramos/:slug", // alias legado de /areas-de-atuacao/:slug; AreaAtuacaoLegacyRedirect
  "/casos/:caseId/sala-de-guerra", // módulo removido; SalaDeGuerraLegacyRedirect → /casos/:caseId?tab=teses
] as const;

// Hrefs absolutos esperados da subárvore do portal (sem o casco).
const PORTAL_CHILD_HREFS = PORTAL_APP_ROUTES.filter((p) => p !== "/portal");

function extractLiteralPaths(source: string): string[] {
  // Captura apenas path="..." literal — path={module.path} e path={redirect.from}
  // (as montagens dinâmicas do registry) NÃO casam de propósito.
  return [...source.matchAll(/\bpath="([^"]+)"/g)].map((m) => m[1]);
}

function routeMatches(routePath: string, pathname: string): boolean {
  const routeSegs = routePath.split("/").filter(Boolean);
  const linkSegs = pathname.split("/").filter(Boolean);
  if (routeSegs.length !== linkSegs.length) return false;
  return routeSegs.every(
    (seg, i) => seg.startsWith(":") || seg === linkSegs[i],
  );
}

describe("integridade App.tsx ↔ moduleRegistry", () => {
  it("monta TODAS as rotas do registry via STAFF_ROUTES.map (nenhum módulo fica órfão)", () => {
    expect(appSrc).toMatch(/STAFF_ROUTES\.map\(/);
    expect(appSrc).toMatch(/path=\{module\.path\}/);
  });

  it("monta TODOS os aliases legados via LEGACY_REDIRECTS.map", () => {
    expect(appSrc).toMatch(/LEGACY_REDIRECTS\.map\(/);
    expect(appSrc).toMatch(/path=\{redirect\.from\}/);
  });

  it("monta o portal via PORTAL_ROUTES.map com o casco /portal literal", () => {
    expect(appSrc).toMatch(/PORTAL_ROUTES\.map\(/);
    const literals = new Set(extractLiteralPaths(appSrc));
    expect(literals.has("/portal")).toBe(true);
  });

  it("PORTAL_ROUTES produz exatamente os hrefs absolutos esperados do portal", () => {
    const hrefs = PORTAL_ROUTES.map((module) => portalNavHref(module));
    expect(hrefs).toEqual([...PORTAL_APP_ROUTES]);
  });

  it("não possui rota literal órfã no App fora das exceções documentadas", () => {
    const literals = extractLiteralPaths(appSrc);
    const permitidos = new Set<string>([
      ...PUBLIC_APP_ROUTES,
      "/portal", // casco do portal; filhos vêm de PORTAL_ROUTES.map
      ...CONTEXTUAL_STAFF_APP_ROUTES,
      ...DYNAMIC_LEGACY_APP_ROUTES,
      "*", // catch-all → NotFound
    ]);
    const orfas = literals.filter((p) => !permitidos.has(p));
    expect(
      orfas,
      `Rota(s) literal(is) no App.tsx fora do registry e das exceções: ${orfas.join(", ")}. ` +
        "Registre no moduleRegistry (staff) ou adicione à lista de exceções deste teste com justificativa.",
    ).toEqual([]);
  });

  it("PORTAL_ROUTES cobre exatamente a subárvore esperada (sem rota órfã no portal)", () => {
    // O casco /portal (rota índice) é montado literalmente no App; o que
    // precisa bater com o espelho PORTAL_APP_ROUTES são os FILHOS.
    const hrefsFilhos = PORTAL_ROUTES.map((m) => portalNavHref(m)).filter(
      (href) => href !== "/portal",
    );
    expect(hrefsFilhos.sort()).toEqual([...PORTAL_CHILD_HREFS].sort());
    // Índice e paths relativos coerentes com a montagem aninhada no App.
    for (const module of PORTAL_ROUTES) {
      if (module.index) expect(module.path).toBeUndefined();
      else expect(module.path).toMatch(/^[a-z][\w-]*(\/:\w+)?$/);
    }
  });

  it("nenhum módulo do registry colide com as rotas literais do App", () => {
    const literaisAbsolutos = new Set<string>([
      ...PUBLIC_APP_ROUTES,
      ...PORTAL_APP_ROUTES,
      ...CONTEXTUAL_STAFF_APP_ROUTES,
    ]);
    for (const module of STAFF_ROUTES) {
      expect(
        literaisAbsolutos.has(module.path),
        `módulo "${module.key}" usa path reservado do App: ${module.path}`,
      ).toBe(false);
    }
  });

  it("todo LEGACY_REDIRECT aponta para uma rota registrada (sem redirect morto)", () => {
    for (const redirect of LEGACY_REDIRECTS) {
      const pathname = redirect.to.split("?")[0] || "/";
      const alvoExiste = STAFF_ROUTES.some((m) =>
        routeMatches(m.path, pathname),
      );
      expect(
        alvoExiste,
        `redirect ${redirect.from} → ${redirect.to} aponta para rota inexistente`,
      ).toBe(true);
    }
  });

  it("todo redirect com ?tab=/?view=/?tipo= cai numa aba REAL do workspace de destino", () => {
    for (const redirect of LEGACY_REDIRECTS) {
      const [pathname, query] = redirect.to.split("?");
      if (!query) continue; // redirect sem sub-navegação por query
      const validators = WORKSPACE_DEEP_LINKS[pathname || "/"];
      if (!validators) continue; // destino sem abas por query param registradas
      const params = new URLSearchParams(query);
      const tab = params.get("tab");
      if (tab !== null) {
        expect(
          validators.tab?.(tab) ?? false,
          `redirect ${redirect.from} → ${redirect.to} usa a aba inexistente "${tab}" em ${pathname}`,
        ).toBe(true);
      }
      const view = params.get("view");
      if (view !== null) {
        expect(
          validators.view?.(view) ?? false,
          `redirect ${redirect.from} → ${redirect.to} usa a visão inexistente "${view}" em ${pathname}`,
        ).toBe(true);
      }
      const tipo = params.get("tipo");
      if (tipo !== null) {
        expect(
          validators.tipo?.(tipo) ?? false,
          `redirect ${redirect.from} → ${redirect.to} usa o tipo inexistente "${tipo}" em ${pathname}`,
        ).toBe(true);
      }
    }
  });
});
