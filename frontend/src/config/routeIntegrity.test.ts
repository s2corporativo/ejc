// Integridade de navegação: moduleRegistry ↔ App.tsx.
//
// O App monta as rotas de staff DINAMICAMENTE via STAFF_ROUTES.map e os
// aliases via LEGACY_REDIRECTS.map — logo, "toda rota do registry está no
// App" é garantido POR CONSTRUÇÃO desde que esses dois maps existam e usem
// module.path / redirect.from. Este teste trava exatamente isso e, no sentido
// inverso, garante que NENHUMA rota literal órfã seja adicionada ao App fora
// das exceções explícitas (públicas de autenticação + subárvore do portal).
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { LEGACY_REDIRECTS, STAFF_ROUTES } from "./moduleRegistry";

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");
const appSrc = readFileSync(join(SRC_DIR, "App.tsx"), "utf-8");

// ── Exceções explícitas: rotas montadas literalmente no App, FORA do registry ──
// Públicas (sem sessão) + troca de senha forçada:
export const PUBLIC_APP_ROUTES = [
  "/login",
  "/recuperar-senha",
  "/redefinir-senha",
  "/trocar-senha",
] as const;
// Subárvore do Portal do Cliente (PortalLayout, papel cliente_externo):
export const PORTAL_APP_ROUTES = [
  "/portal",
  "/portal/casos",
  "/portal/casos/:id",
  "/portal/financeiro",
  "/portal/assinaturas",
  "/portal/mensagens",
  "/portal/documentos",
] as const;
// Aliases legados com segmento dinâmico: LEGACY_REDIRECTS só suporta `to`
// estático (Navigate não interpola :params), então precisam de uma <Route>
// dedicada no App montando um pequeno redirect component em vez de entrar
// no map genérico.
export const DYNAMIC_LEGACY_APP_ROUTES = [
  "/clientes/:clientId/dossie", // alias removido de STAFF_ROUTES; redireciona para /clientes/:clientId
  "/ramos/:slug", // alias legado; redireciona para /areas-de-atuacao/:slug
] as const;

// Literais relativos esperados DENTRO do bloco /portal do App.tsx.
const PORTAL_CHILD_LITERALS = PORTAL_APP_ROUTES.filter(
  (p) => p !== "/portal",
).map((p) => p.replace("/portal/", ""));

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

  it("não possui rota literal órfã no App fora das exceções documentadas", () => {
    const literals = extractLiteralPaths(appSrc);
    const permitidos = new Set<string>([
      ...PUBLIC_APP_ROUTES,
      "/portal",
      ...PORTAL_CHILD_LITERALS,
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

  it("mantém a subárvore do portal montada exatamente como o esperado", () => {
    const literals = new Set(extractLiteralPaths(appSrc));
    expect(literals.has("/portal")).toBe(true);
    for (const child of PORTAL_CHILD_LITERALS) {
      expect(
        literals.has(child),
        `rota do portal ausente no App: ${child}`,
      ).toBe(true);
    }
  });

  it("nenhum módulo do registry colide com as rotas literais do App", () => {
    const literaisAbsolutos = new Set<string>([
      ...PUBLIC_APP_ROUTES,
      ...PORTAL_APP_ROUTES,
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
});
