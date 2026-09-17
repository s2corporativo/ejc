// Links internos mortos: varre estaticamente frontend/src atrás de TODO
// destino de navegação literal (Link/NavLink/Navigate to=, navigate(), href=)
// e valida que o caminho existe no conjunto de rotas registradas
// (STAFF_ROUTES) + aliases (LEGACY_REDIRECTS) + rotas literais do App
// (login/portal/públicas). Segmentos dinâmicos (`/casos/${id}`) são
// normalizados para casar rotas com :param. Falha listando cada link morto
// com arquivo:linha.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { LEGACY_REDIRECTS, STAFF_ROUTES } from "./moduleRegistry";

const SRC_DIR = join(dirname(fileURLToPath(import.meta.url)), "..");

// Exceções: rotas montadas literalmente no App.tsx fora do registry
// (mantidas em sincronia com routeIntegrity.test.ts, que valida o App).
const APP_LITERAL_ROUTES = [
  "/login",
  "/recuperar-senha",
  "/redefinir-senha",
  "/trocar-senha",
  "/portal",
  "/portal/casos",
  "/portal/casos/:id",
  "/portal/financeiro",
  "/portal/assinaturas",
  "/portal/mensagens",
  "/portal/documentos",
  "/ia-governanca/provedores",
];

const KNOWN_ROUTES: string[] = [
  // subPaths (auditoria §2.6 #7): sub-rotas internas do mesmo módulo — ex.
  // /dpt360/* — são destinos válidos tanto quanto o path principal.
  ...STAFF_ROUTES.flatMap((m) => [m.path, ...(m.subPaths ?? [])]),
  ...LEGACY_REDIRECTS.map((r) => r.from),
  ...APP_LITERAL_ROUTES,
];

type LinkSite = { file: string; line: number; raw: string; pathname: string };

const DYN = "__dyn__"; // placeholder de segmento dinâmico (`${...}`)

function* walk(dir: string): Generator<string> {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      if (name === "node_modules" || name === "dist") continue;
      yield* walk(full);
    } else if (
      /\.(ts|tsx)$/.test(name) &&
      !/\.test\.(ts|tsx)$/.test(name) &&
      !name.endsWith(".d.ts")
    ) {
      yield full;
    }
  }
}

// Padrões de navegação interna com destino LITERAL. Destinos em variável
// (ex.: to={module.path}) não são resolvíveis estaticamente e ficam fora —
// o registry já é validado por routeIntegrity.test.ts.
const LINK_PATTERNS: RegExp[] = [
  /\bto="([^"]+)"/g, // <Link to="/x">
  /\bto=\{"([^"]+)"\}/g, // to={"/x"}
  /\bto=\{'([^']+)'\}/g, // to={'/x'}
  /\bto=\{`([^`]+)`\}/g, // to={`/x/${id}`}
  /\bnavigate\(\s*"([^"]+)"/g, // navigate("/x")
  /\bnavigate\(\s*'([^']+)'/g,
  /\bnavigate\(\s*`([^`]+)`/g, // navigate(`/x/${id}`)
  /\bhref="(\/[^\"]*)"/g, // <a href="/x">
  /\bhref=\{`(\/[^`]*)`\}/g,
];

function normalize(raw: string): string | null {
  // `${...}` → placeholder de 1 segmento; depois corta query/hash.
  let p = raw.replace(/\$\{[^}]*\}/g, DYN);
  p = p.split("?")[0].split("#")[0];
  if (!p.startsWith("/")) return null; // relativo: resolvido pelo router no contexto
  if (p.startsWith("//") || p.startsWith("/api/") || p === "/api") return null; // externo / contrato HTTP (coberto no backend)
  if (p.startsWith("/analytics/")) return null; // endpoints de dados, não rotas de navegação
  p = p.replace(/\/+$/, "") || "/";
  return p;
}

function segmentMatches(routeSegment: string, linkSegment: string): boolean {
  return (
    routeSegment.startsWith(":") ||
    linkSegment === DYN ||
    routeSegment === linkSegment
  );
}

function routeMatches(routePath: string, pathname: string): boolean {
  const routeSegs = routePath.split("/").filter(Boolean);
  const linkSegs = pathname.split("/").filter(Boolean);
  if (routePath === "/" || pathname === "/") return routePath === pathname;

  // React Router usa `*` terminal para rotas-filhas do mesmo workspace. O
  // validador precisa reconhecer o mesmo contrato; tratar `*` como texto
  // literal gera falso link morto para destinos válidos como /dpt360/radar.
  const wildcardIndex = routeSegs.indexOf("*");
  if (wildcardIndex >= 0) {
    if (wildcardIndex !== routeSegs.length - 1) return false;
    const prefix = routeSegs.slice(0, wildcardIndex);
    if (linkSegs.length < prefix.length) return false;
    return prefix.every((seg, i) => segmentMatches(seg, linkSegs[i]));
  }

  if (routeSegs.length !== linkSegs.length) return false;
  return routeSegs.every((seg, i) => segmentMatches(seg, linkSegs[i]));
}

function isKnown(pathname: string): boolean {
  if (pathname === "/") return true; // dashboard
  return KNOWN_ROUTES.some((route) => routeMatches(route, pathname));
}

describe("links internos do frontend", () => {
  it("a varredura encontra um volume plausível de links (sanidade do extrator)", () => {
    const sites = collectLinks();
    expect(sites.length).toBeGreaterThan(20);
  });

  it("reconhece wildcard terminal sem aceitar prefixo diferente", () => {
    expect(routeMatches("/dpt360/*", "/dpt360/radar")).toBe(true);
    expect(routeMatches("/dpt360/*", "/dpt360/empresas/123")).toBe(true);
    expect(routeMatches("/dpt360/*", "/outro/radar")).toBe(false);
    expect(routeMatches("/dpt360/*/invalido", "/dpt360/radar/invalido")).toBe(
      false,
    );
  });

  it("todo link/navigate/href interno aponta para rota registrada (sem link morto)", () => {
    const mortos = collectLinks().filter((s) => !isKnown(s.pathname));
    const linhas = mortos.map(
      (s) => `  ${s.pathname}  <- ${s.file}:${s.line} (raw: ${s.raw})`,
    );
    expect(
      mortos,
      `${mortos.length} link(s) interno(s) sem rota correspondente:\n${linhas.join("\n")}\n` +
        "Corrija o destino, registre a rota no moduleRegistry ou adicione um LEGACY_REDIRECT.",
    ).toEqual([]);
  });
});

function collectLinks(): LinkSite[] {
  const sites: LinkSite[] = [];
  for (const file of walk(SRC_DIR)) {
    const src = readFileSync(file, "utf-8");
    const rel = relative(SRC_DIR, file);
    for (const pattern of LINK_PATTERNS) {
      pattern.lastIndex = 0;
      for (const m of src.matchAll(pattern)) {
        const raw = m[1];
        if (/^(https?:|mailto:|tel:|#)/.test(raw)) continue;
        const pathname = normalize(raw);
        if (pathname === null) continue;
        const line = src.slice(0, m.index ?? 0).split("\n").length;
        sites.push({ file: rel, line, raw, pathname });
      }
    }
  }
  return sites;
}
