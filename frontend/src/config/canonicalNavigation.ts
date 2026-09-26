import type { ModuleRoute } from "./moduleRegistry";

/**
 * Fonte única do menu principal enxuto do EJC.
 *
 * O registry continua sendo a fonte de verdade de rota, componente e RBAC.
 * Este arquivo define apenas quais domínios aparecem na navegação principal,
 * sua ordem e o rótulo específico de menu quando ele difere do rótulo da rota.
 *
 * O shell expõe um menu operacional mínimo e mantém o menu amplo anterior
 * somente como rollback. A regra de produto desde a dashboard IA/Controles é:
 * a navegação lateral serve para destinos estruturais; agenda, peças,
 * conhecimento, documentos, radar e produtividade permanecem acessíveis no
 * contexto do caso, na aba Controles, por deep-link e pela busca global.
 *
 * `CANONICAL_CORE_NAV` é o default: Início, Clientes, Casos e Processos,
 * Financeiro e Administração. A lista não cria permissões: RBAC e lifecycle
 * continuam filtrando módulos indisponíveis ao perfil.
 *
 * `CANONICAL_MAIN_NAV` preserva os 11 domínios históricos apenas como
 * rollback operacional.
 *
 * A flag histórica `ejc_menu9` / `VITE_EJC_MENU_9` é mantida por
 * compatibilidade de infraestrutura: "true" seleciona o menu Core atual;
 * "false" retorna ao menu amplo sem deploy.
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

/** Menu estrutural mínimo do EJC após a consolidação IA/Controles. */
export const CANONICAL_CORE_NAV = [
  { key: "dashboard", label: "Início" },
  { key: "clientes", label: "Clientes" },
  { key: "casos", label: "Casos e Processos" },
  { key: "financeiro", label: "Financeiro" },
  { key: "configuracoes", label: "Administração" },
] as const;

/**
 * Alias temporário para consumidores/testes anteriores. Não representa um
 * segundo menu: aponta para o mesmo contrato Core e pode ser removido quando a
 * flag histórica ejc_menu9 for renomeada em uma onda de infraestrutura.
 */
export const CANONICAL_MENU_9_NAV = CANONICAL_CORE_NAV;

export type CanonicalMainNavKey = (typeof CANONICAL_MAIN_NAV)[number]["key"];

const MENU9_STORAGE_KEY = "ejc_menu9";

/**
 * Flag histórica do menu enxuto. Hoje "ativada" significa menu Core mínimo;
 * o nome é preservado para não exigir alteração de ambiente no mesmo deploy.
 *
 * Precedência: `localStorage.ejc_menu9 = "true"|"false"` vence o ambiente;
 * `VITE_EJC_MENU_9="false"` desativa globalmente (opt-out de infra).
 * Rollback: por perfil via localStorage (imediato, sem deploy) ou global via
 * env + rebuild / revert do commit de ativação.
 */
export function isMenu9Enabled(): boolean {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      const local = window.localStorage.getItem(MENU9_STORAGE_KEY);
      if (local === "true") return true;
      if (local === "false") return false;
    }
  } catch {
    // storage indisponível (privacidade/incognito) — cai no default de env
  }
  return import.meta.env?.VITE_EJC_MENU_9 !== "false";
}

/** Override local da flag (uso em homologação/diagnóstico; não exposto em UI). */
export function setMenu9Enabled(enabled: boolean): void {
  try {
    window.localStorage.setItem(MENU9_STORAGE_KEY, String(enabled));
  } catch {
    // storage indisponível — flag permanece no default de env
  }
}

function selectFromNav(
  nav: ReadonlyArray<{ key: string; label: string }>,
  modules: ModuleRoute[],
): ModuleRoute[] {
  const byKey = new Map(modules.map((item) => [item.key, item]));
  return nav.flatMap(({ key, label }) => {
    const item = byKey.get(key);
    return item ? [{ ...item, label }] : [];
  });
}

/** Menu default atual (11 domínios da referência premium DPT). */
export function selectCanonicalMainNavigation(
  modules: ModuleRoute[],
): ModuleRoute[] {
  return selectFromNav(CANONICAL_MAIN_NAV, modules);
}

export type MainNavigationOptions = {
  /** Compatibilidade: true = menu Core mínimo; false = menu amplo de rollback. */
  menu9?: boolean;
};

/**
 * Seletor canônico do shell: honra a flag histórica do menu enxuto e mantém
 * RBAC/lifecycle do chamador. Módulo ausente da carteira nunca vira link morto.
 */
export function selectMainNavigation(
  modules: ModuleRoute[],
  options?: MainNavigationOptions,
): ModuleRoute[] {
  const menu9 = options?.menu9 ?? isMenu9Enabled();
  return selectFromNav(menu9 ? CANONICAL_CORE_NAV : CANONICAL_MAIN_NAV, modules);
}
