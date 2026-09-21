/**
 * Flags de abas das ondas de absorção (§10 do plano de limpeza 2026-09-20:
 * docs/audit/AUDITORIA_REAL_2026-09-20.md).
 *
 * Padrão idêntico ao da flag do menu de 9 módulos (Onda 1): superfície NOVA
 * entra ATIVA por default, com rollback IMEDIATO por perfil
 * (`localStorage.<chave>`) ou global (`VITE_EJC_*_TABS=false` + rebuild) —
 * sem deploy e sem reverter o PR.
 *
 * Onda 3 — aba "Data Room" no workspace do caso (§3, absorções-chave).
 * Onda 4 — abas "Tarefas" e "Intimações" no workspace do caso (Agenda/Prazos/
 * Tarefas/Intimações; escrita continua ÚNICA na Central /atividades — as abas
 * são somente leitura e direcionam para a fonte, como a aba Prazos).
 */

/** Fabrica um par de funções de flag (consulta + override) para uma aba. */
function flagDeTab(storageKey: string, envKey: string) {
  function consulta(): boolean {
    try {
      if (typeof window !== "undefined" && window.localStorage) {
        const local = window.localStorage.getItem(storageKey);
        if (local === "true") return true;
        if (local === "false") return false;
      }
    } catch {
      // storage indisponível (privacidade/incognito) — cai no default de env
    }
    return import.meta.env?.[envKey] !== "false";
  }
  function override(enabled: boolean): void {
    try {
      window.localStorage.setItem(storageKey, String(enabled));
    } catch {
      // storage indisponível — flag permanece no default
    }
  }
  return { consulta, override };
}

const flagDataRoom = flagDeTab("ejc_w3_dataroom", "VITE_EJC_W3_TABS");
const flagTarefas = flagDeTab("ejc_w4_tarefas", "VITE_EJC_W4_TABS");
const flagIntimacoes = flagDeTab("ejc_w4_intimacoes", "VITE_EJC_W4_TABS");

/** Tab "Data Room" do caso — default ATIVO; rollback por perfil sem deploy. */
export function isDataRoomTabEnabled(): boolean {
  return flagDataRoom.consulta();
}

/** Override local da flag (homologação/diagnóstico; não exposto em UI). */
export function setDataRoomTabEnabled(enabled: boolean): void {
  flagDataRoom.override(enabled);
}

/** Tab "Tarefas" do caso (Onda 4) — somente leitura; escrita na Central. */
export function isTarefasTabEnabled(): boolean {
  return flagTarefas.consulta();
}

export function setTarefasTabEnabled(enabled: boolean): void {
  flagTarefas.override(enabled);
}

/** Tab "Intimações" do caso (Onda 4) — somente leitura; escrita na Central. */
export function isIntimacoesTabEnabled(): boolean {
  return flagIntimacoes.consulta();
}

export function setIntimacoesTabEnabled(enabled: boolean): void {
  flagIntimacoes.override(enabled);
}

/** Chaves de tab controladas por flag das ondas (com sua condição de exibição). */
const TABS_COM_FLAG: Record<string, () => boolean> = {
  dataroom: isDataRoomTabEnabled,
  tarefas: isTarefasTabEnabled,
  intimacoes: isIntimacoesTabEnabled,
};

/**
 * Filtra a lista de abas de uma seção removendo as abas cuja flag está OFF.
 * Seletor único usado por CasoDetalhe (GROUPS, validação de deep-link e
 * render) — barra e dock só linkam seções, então não enumeram abas.
 */
export function filtrarTabsW3<T extends string>(tabs: readonly T[]): T[] {
  return tabs.filter((t) => TABS_COM_FLAG[t]?.() ?? true);
}
