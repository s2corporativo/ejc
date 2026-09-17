import type { ModuleRoute } from "./moduleRegistry";

/**
 * Fonte única do menu principal enxuto do EJC.
 *
 * O registry continua sendo a fonte de verdade de rota, componente e RBAC.
 * Este arquivo define apenas quais domínios aparecem na navegação principal,
 * sua ordem e o rótulo específico de menu quando ele difere do rótulo da rota.
 */
export const CANONICAL_MAIN_NAV = [
  { key: "dashboard", label: "Início" },
  { key: "casos", label: "Casos" },
  { key: "clientes", label: "Clientes" },
  { key: "atividades", label: "Agenda" },
  { key: "documentos", label: "Documentos" },
  { key: "ramos", label: "Áreas de Atuação" },
  { key: "financeiro", label: "Financeiro" },
  { key: "configuracoes", label: "Administrativo" },
] as const;

export type CanonicalMainNavKey = (typeof CANONICAL_MAIN_NAV)[number]["key"];

export function selectCanonicalMainNavigation(
  modules: ModuleRoute[],
): ModuleRoute[] {
  const byKey = new Map(modules.map((item) => [item.key, item]));
  return CANONICAL_MAIN_NAV.flatMap(({ key, label }) => {
    const item = byKey.get(key);
    return item ? [{ ...item, label }] : [];
  });
}
