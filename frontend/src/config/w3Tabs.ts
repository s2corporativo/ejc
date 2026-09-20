/**
 * Flags da Onda 3 — Caso como workspace central (§10 do plano de limpeza
 * 2026-09-20: docs/audit/AUDITORIA_REAL_2026-09-20.md).
 *
 * A absorção "Data Room → contexto de Caso/Documento" (§3, absorções-chave)
 * entra como ABA do workspace do caso, atrás de flag para rollback imediato
 * por perfil (`localStorage.ejc_w3_dataroom`) ou global (`VITE_EJC_W3_TABS=false`
 * + rebuild), seguindo o mesmo padrão da flag do menu de 9 módulos (Onda 1).
 *
 * As abas de Peças, Documentos e Prazos do caso já são canônicas no workspace
 * (Tela C/Bloco 3) — a flag controla apenas as superfícies NOVAS desta onda.
 */

const W3_DATAROOM_STORAGE_KEY = "ejc_w3_dataroom";

/** Tab "Data Room" do caso — default ATIVO; rollback por perfil sem deploy. */
export function isDataRoomTabEnabled(): boolean {
  try {
    if (typeof window !== "undefined" && window.localStorage) {
      const local = window.localStorage.getItem(W3_DATAROOM_STORAGE_KEY);
      if (local === "true") return true;
      if (local === "false") return false;
    }
  } catch {
    // storage indisponível (privacidade/incognito) — cai no default de env
  }
  return import.meta.env?.VITE_EJC_W3_TABS !== "false";
}

/** Override local da flag (homologação/diagnóstico; não exposto em UI). */
export function setDataRoomTabEnabled(enabled: boolean): void {
  try {
    window.localStorage.setItem(W3_DATAROOM_STORAGE_KEY, String(enabled));
  } catch {
    // storage indisponível — flag permanece no default
  }
}

/** Chaves de tab controladas por flag da Onda 3 (com sua condição de exibição). */
const TABS_COM_FLAG: Record<string, () => boolean> = {
  dataroom: isDataRoomTabEnabled,
};

/**
 * Filtra a lista de abas de uma seção removendo as abas cuja flag está OFF.
 * Seletor único usado por CasoDetalhe (GROUPS, validação de deep-link e
 * render) — barra e dock só linkam seções, então não enumeram abas.
 */
export function filtrarTabsW3<T extends string>(tabs: readonly T[]): T[] {
  return tabs.filter((t) => TABS_COM_FLAG[t]?.() ?? true);
}
