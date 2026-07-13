import { getModuleCatalog } from "../config/moduleRegistry";
import type { ModuleLifecycleOverride } from "../stores/moduleLifecycle";

type ModuleLike = {
  key: string;
  path: string;
  status?: string;
};

export function filterModulesByLifecycle<T extends ModuleLike>(
  modules: T[],
  settings: Record<string, ModuleLifecycleOverride>,
): T[] {
  return modules.filter((module) => {
    const override = settings[module.key];
    if (!override) return module.status !== "hidden";
    if (!override.enabled || override.status === "disabled") return false;
    if (!override.menu_visible || override.status === "hidden") return false;
    return true;
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
