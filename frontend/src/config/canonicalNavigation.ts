import type { ModuleRoute } from "./moduleRegistry";

/**
 * Fonte única do menu principal enxuto do EJC.
 *
 * O registry continua sendo a fonte de verdade de rota, componente e RBAC.
 * Este arquivo define apenas quais domínios aparecem na navegação principal,
 * sua ordem e o rótulo específico de menu quando ele difere do rótulo da rota.
 *
 * Dois menus canônicos convivem aqui (Onda 1 do plano de limpeza
 * 2026-09-20 — docs/audit/AUDITORIA_REAL_2026-09-20.md §3 e §10):
 *
 * 1. `CANONICAL_MENU_9_NAV` — menu alvo de 9 módulos do mapa funcional
 *    auditado (DASHBOARD, CLIENTES, CASOS, AGENDA E PRAZOS, PEÇAS,
 *    CONHECIMENTO JURÍDICO, FINANCEIRO, PORTAL DO CLIENTE, ADMINISTRAÇÃO).
 *    É o DEFAULT desde a ativação da flag pelo Titular (21/09/2026), após a
 *    homologação da Onda 1 (PR #1742, CI verde, gates completos).
 *    Nada é removido do sistema por sair do menu: as rotas absorvidas
 *    (Documentos, Banco de Teses, Radar, Relatórios/Produtividade) seguem
 *    vivas no registry, acessíveis por deep-link, ⌘K e contexto — a Onda 3+
 *    é que as absorve de fato como tabs/workspace.
 *
 * 2. `CANONICAL_MAIN_NAV` — menu de 11 domínios da referência visual
 *    premium DPT aprovada pelo Titular (18/09/2026). Mantido como ROLLBACK:
 *    continua acessível sem deploy via override local (abaixo).
 *
 * A troca é controlada por flag (`ejc_menu9` em localStorage vence o default
 * de ambiente `VITE_EJC_MENU_9`) — rollback imediato por perfil sem deploy.
 * RBAC/lifecycle continuam filtrando o resultado — nenhum link
 * morto é gerado: "portal" não possui ModuleRoute de staff (o Portal do
 * Cliente tem shell próprio confinado por middleware) e é descartado em
 * runtime para usuários internos.
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

/** Menu alvo de 9 módulos (mapa funcional auditado, §3 do plano 2026-09-20). */
export const CANONICAL_MENU_9_NAV = [
  { key: "dashboard", label: "Início" },
  { key: "clientes", label: "Clientes" },
  { key: "casos", label: "Casos" },
  { key: "atividades", label: "Agenda e Prazos" },
  { key: "pecas", label: "Peças" },
  { key: "inteligencia", label: "Conhecimento Jurídico" },
  { key: "financeiro", label: "Financeiro" },
  // Domínio 8 do mapa-alvo. Mantido no contrato canônico por completude, mas
  // sem ModuleRoute de staff: o seletor descarta a chave quando o registry
  // não a expõe (sem link morto). O portal tem shell próprio (/portal,
  // PortalLayout) confinado a cliente_externo por middleware.
  { key: "portal", label: "Portal do Cliente" },
  { key: "configuracoes", label: "Administração" },
] as const;

export type CanonicalMainNavKey = (typeof CANONICAL_MAIN_NAV)[number]["key"];

const MENU9_STORAGE_KEY = "ejc_menu9";

/**
 * Flag do menu de 9 módulos — ATIVADA por decisão do Titular (21/09/2026),
 * após homologação da Onda 1 (PR #1742: gates completos, CI verde).
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
  /** Força um dos dois menus (testes/homologação); ausente = flag. */
  menu9?: boolean;
};

/**
 * Seletor canônico do shell: honra a flag do menu de 9 (ou o override
 * explícito) e mantém o comportamento de RBAC/lifecycle do chamador —
 * módulos ausentes da carteira nunca viram link morto.
 */
export function selectMainNavigation(
  modules: ModuleRoute[],
  options?: MainNavigationOptions,
): ModuleRoute[] {
  const menu9 = options?.menu9 ?? isMenu9Enabled();
  return selectFromNav(
    menu9 ? CANONICAL_MENU_9_NAV : CANONICAL_MAIN_NAV,
    modules,
  );
}
