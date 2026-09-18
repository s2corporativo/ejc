import type { ModuleRoute } from "./moduleRegistry";

/**
 * Fonte única do menu principal enxuto do EJC.
 *
 * O registry continua sendo a fonte de verdade de rota, componente e RBAC.
 * Este arquivo define apenas quais domínios aparecem na navegação principal,
 * sua ordem e o rótulo específico de menu quando ele difere do rótulo da rota.
 *
 * Ordem e rótulos seguem a referência visual premium DPT aprovada pelo
 * Titular em 18/09/2026 (dashboard "EJC DePaula Teixeira Adv"): 11 domínios,
 * incluindo Inteligência Jurídica, Banco de Teses, Radar Operacional e
 * Relatórios (→ /produtividade). Módulos ausentes na carteira/perfil seguem
 * filtrados por RBAC/lifecycle — nenhum link morto é gerado.
 */
export const CANONICAL_MAIN_NAV = [
  { key: "dashboard", label: "Início" },
  { key: "atividades", label: "Agenda e Prazos" },
  { key: "clientes", label: "Clientes" },
  { key: "casos", label: "Casos" },
  { key: "financeiro", label: "Financeiro" },
  { key: "documentos", label: "Documentos" },
  { key: "inteligencia", label: "Inteligência Jurídica" },
  { key: "banco-teses", label: "Banco de Teses" },
  { key: "radar", label: "Radar Operacional" },
  { key: "produtividade", label: "Relatórios" },
  { key: "configuracoes", label: "Configurações" },
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
