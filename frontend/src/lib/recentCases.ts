export type RecentCaseItem = {
  id: string;
  titulo: string;
  area?: string | null;
  favorite: boolean;
  lastOpened: number;
};

const STORAGE_KEY = "ejc_recent_cases_v1";
export const RECENT_CASES_EVENT = "ejc-recent-cases-changed";

function readRaw(): RecentCaseItem[] {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "[]");
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item) => item && typeof item.id === "string")
      .map((item) => ({
        id: String(item.id),
        titulo: String(item.titulo || "Caso"),
        area: item.area ? String(item.area) : null,
        favorite: Boolean(item.favorite),
        lastOpened: Number(item.lastOpened || 0),
      }));
  } catch {
    return [];
  }
}

function save(items: RecentCaseItem[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(items.slice(0, 20)));
    window.dispatchEvent(new Event(RECENT_CASES_EVENT));
  } catch {
    // Preferência local é opcional; não interrompe o fluxo do caso.
  }
}

export function getRecentCases(): RecentCaseItem[] {
  return readRaw().sort((a, b) => {
    if (a.favorite !== b.favorite) return Number(b.favorite) - Number(a.favorite);
    return b.lastOpened - a.lastOpened;
  });
}

export function rememberRecentCase(item: {
  id: string;
  titulo?: string | null;
  area?: string | null;
}) {
  const current = readRaw();
  const existing = current.find((x) => x.id === item.id);
  const next: RecentCaseItem = {
    id: item.id,
    titulo: item.titulo?.trim() || existing?.titulo || "Caso",
    area: item.area ?? existing?.area ?? null,
    favorite: existing?.favorite ?? false,
    lastOpened: Date.now(),
  };
  save([next, ...current.filter((x) => x.id !== item.id)]);
}

export function toggleCaseFavorite(item: {
  id: string;
  titulo?: string | null;
  area?: string | null;
}): boolean {
  const current = readRaw();
  const existing = current.find((x) => x.id === item.id);
  const favorite = !(existing?.favorite ?? false);
  const next: RecentCaseItem = {
    id: item.id,
    titulo: item.titulo?.trim() || existing?.titulo || "Caso",
    area: item.area ?? existing?.area ?? null,
    favorite,
    lastOpened: existing?.lastOpened || Date.now(),
  };
  save([next, ...current.filter((x) => x.id !== item.id)]);
  return favorite;
}

export function isCaseFavorite(id: string): boolean {
  return Boolean(readRaw().find((item) => item.id === id)?.favorite);
}
