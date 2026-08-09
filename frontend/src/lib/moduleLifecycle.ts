import { getModuleCatalog } from "../config/moduleRegistry";
import type { ModuleLifecycleOverride } from "../stores/moduleLifecycle";

type ModuleLike = {
  key: string;
  path: string;
  status?: string;
  label?: string;
  description?: string;
  essential?: boolean;
};

// Rotas mantidas somente por compatibilidade. A tarefa correspondente já existe
// em outro workspace canônico e não deve aparecer novamente na navegação.
const CONSOLIDATED_NAV_KEYS = new Set(["knowledge-hub"]);

// Sala Jurídica e Raio-X continuam sendo módulos/rotas canônicos porque isso
// preserva lifecycle, RBAC, ajuda contextual, manifests e deep links. Porém,
// quando a própria Entrada já está efetivamente visível para o papel atual,
// elas deixam de competir no menu e a Entrada assume o rótulo de gateway único.
const ENTRADA_CONSOLIDATED_NAV_KEYS = new Set([
  "sala-juridica",
  "raio-x-processo",
]);

function visibleByLifecycle<T extends ModuleLike>(
  module: T,
  settings: Record<string, ModuleLifecycleOverride>,
): boolean {
  const override = settings[module.key];
  if (!override) return module.status !== "hidden";
  if (!override.enabled || override.status === "disabled") return false;
  if (!override.menu_visible || override.status === "hidden") return false;
  return true;
}

export function filterModulesByLifecycle<T extends ModuleLike>(
  modules: T[],
  settings: Record<string, ModuleLifecycleOverride>,
): T[] {
  const entradaVisivel = modules.some(
    (module) =>
      module.key === "entrada" && visibleByLifecycle(module, settings),
  );

  return modules
    .filter((module) => {
      if (CONSOLIDATED_NAV_KEYS.has(module.key)) return false;
      if (entradaVisivel && ENTRADA_CONSOLIDATED_NAV_KEYS.has(module.key)) {
        return false;
      }
      return visibleByLifecycle(module, settings);
    })
    .map((module) => {
      if (!entradaVisivel || module.key !== "entrada") return module;
      return {
        ...module,
        label: "Entrada Única",
        description:
          "Porta principal para iniciar um caso por relato/documentos e acessar Sala Jurídica ou Raio-X.",
        essential: true,
      } as T;
    });
}

function routePatternToRegex(path: string): RegExp {
  const escaped = path
    .split("/")
    .map((segment) => {
      if (!segment) return "";
      if (segment.startsWith(":")) return "[^/]+";
      return segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    })
    .join("/");
  return new RegExp(`^${escaped}/?$`);
}

export function matchModuleByPath(pathname: string) {
  const candidates = getModuleCatalog()
    .filter((module) => routePatternToRegex(module.path).test(pathname))
    .sort((a, b) => b.path.length - a.path.length);
  return candidates[0] ?? null;
}

export function lifecycleForPath(
  pathname: string,
  settings: Record<string, ModuleLifecycleOverride>,
): ModuleLifecycleOverride | null {
  const module = matchModuleByPath(pathname);
  return module ? (settings[module.key] ?? null) : null;
}

export function safeReplacementRoute(
  currentPath: string,
  replacement?: string | null,
): string | null {
  if (
    !replacement ||
    !replacement.startsWith("/") ||
    replacement.startsWith("//")
  ) {
    return null;
  }
  const replacementPath = replacement.split("?", 1)[0];
  if (replacementPath === currentPath) return null;
  return replacement;
}
