import { create } from "zustand";
import { persist } from "zustand/middleware";

export type View = "landing" | "app";

interface AppState {
  view: View;
  setView: (v: View) => void;
  appTab: "generator" | "editor" | "jurisprudence" | "batch" | "documents";
  setAppTab: (t: AppState["appTab"]) => void;
  currentDocId: string | null;
  setCurrentDocId: (id: string | null) => void;
  selectedTemplateSlug: string | null;
  setSelectedTemplateSlug: (slug: string | null) => void;
  selectedSkillSlugs: string[];
  toggleSkill: (slug: string) => void;
  clearSkills: () => void;
  authOpen: boolean;
  setAuthOpen: (b: boolean) => void;
  user: { email: string; name: string | null } | null;
  setUser: (u: { email: string; name: string | null } | null) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      view: "landing",
      setView: (view) => set({ view }),
      appTab: "generator",
      setAppTab: (appTab) => set({ appTab }),
      currentDocId: null,
      setCurrentDocId: (currentDocId) => set({ currentDocId }),
      selectedTemplateSlug: null,
      setSelectedTemplateSlug: (selectedTemplateSlug) => set({ selectedTemplateSlug }),
      selectedSkillSlugs: [],
      toggleSkill: (slug) => {
        const cur = get().selectedSkillSlugs;
        if (cur.includes(slug)) {
          set({ selectedSkillSlugs: cur.filter((s) => s !== slug) });
        } else {
          set({ selectedSkillSlugs: [...cur, slug] });
        }
      },
      clearSkills: () => set({ selectedSkillSlugs: [] }),
      authOpen: false,
      setAuthOpen: (authOpen) => set({ authOpen }),
      user: { email: "demo@juridia.com.br", name: "Advogado Demo" },
      setUser: (user) => set({ user }),
    }),
    {
      name: "juridia-store",
      partialize: (s) => ({
        view: s.view,
        appTab: s.appTab,
        user: s.user,
        selectedSkillSlugs: s.selectedSkillSlugs,
      }),
    }
  )
);
