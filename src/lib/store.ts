import { create } from "zustand";
import { persist } from "zustand/middleware";

export type View = "landing" | "app";

export type WritingStyle =
  | "formal"      // formal técnico (padrão)
  | "sintetico"   // conciso e direto
  | "academic"    // acadêmico/doutrinário
  | "direto";     // linguagem simples

export interface LawyerProfile {
  name: string;
  oab: string;
  oabUf: string;
  office: string;
  email: string;
  phone: string;
  address: string;
}

interface AppState {
  view: View;
  setView: (v: View) => void;
  appTab:
    | "assistente"
    | "dashboard"
    | "biblioteca"
    | "calculadora"
    | "cerebro"
    | "intelligence"
    | "tribunal"
    | "wizard"
    | "pipeline"
    | "generator"
    | "editor"
    | "homologacao"
    | "visuallaw"
    | "datajud"
    | "grafo"
    | "settings";
  setAppTab: (t: AppState["appTab"]) => void;
  currentDocId: string | null;
  setCurrentDocId: (id: string | null) => void;
  currentCaseId: string | null;
  setCurrentCaseId: (id: string | null) => void;
  brainContext: string | null; // contexto da análise cerebral para passar ao gerador
  setBrainContext: (ctx: string | null) => void;
  activeDebateId: string | null;
  setActiveDebateId: (id: string | null) => void;
  selectedTemplateSlug: string | null;
  setSelectedTemplateSlug: (slug: string | null) => void;
  selectedSkillSlugs: string[];
  toggleSkill: (slug: string) => void;
  clearSkills: () => void;
  authOpen: boolean;
  setAuthOpen: (b: boolean) => void;
  user: { email: string; name: string | null } | null;
  setUser: (u: { email: string; name: string | null } | null) => void;
  // Perfil e estilo
  profile: LawyerProfile;
  setProfile: (p: Partial<LawyerProfile>) => void;
  writingStyle: WritingStyle;
  setWritingStyle: (s: WritingStyle) => void;
  defaultSkills: string[];
  toggleDefaultSkill: (slug: string) => void;
}

const DEFAULT_PROFILE: LawyerProfile = {
  name: "Advogado Demo",
  oab: "123456",
  oabUf: "SP",
  office: "Escritório JuridIA Advocacia",
  email: "demo@juridia.com.br",
  phone: "(11) 99999-0000",
  address: "Av. Paulista, 1000 — São Paulo/SP",
};

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      view: "app",
      setView: (view) => set({ view }),
      appTab: "dashboard",
      setAppTab: (appTab) => set({ appTab }),
      currentDocId: null,
      setCurrentDocId: (currentDocId) => set({ currentDocId }),
      currentCaseId: null,
      setCurrentCaseId: (currentCaseId) => set({ currentCaseId }),
      brainContext: null,
      setBrainContext: (brainContext) => set({ brainContext }),
      activeDebateId: null,
      setActiveDebateId: (activeDebateId) => set({ activeDebateId }),
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
      // Perfil e estilo
      profile: DEFAULT_PROFILE,
      setProfile: (p) => set({ profile: { ...get().profile, ...p } }),
      writingStyle: "formal",
      setWritingStyle: (writingStyle) => set({ writingStyle }),
      defaultSkills: ["cpc-estrutura-peticao", "cnj-615-2025"],
      toggleDefaultSkill: (slug) => {
        const cur = get().defaultSkills;
        if (cur.includes(slug)) {
          set({ defaultSkills: cur.filter((s) => s !== slug) });
        } else {
          set({ defaultSkills: [...cur, slug] });
        }
      },
    }),
    {
      name: "juridia-store",
      partialize: (s) => ({
        view: s.view,
        appTab: s.appTab,
        user: s.user,
        selectedSkillSlugs: s.selectedSkillSlugs,
        profile: s.profile,
        writingStyle: s.writingStyle,
        defaultSkills: s.defaultSkills,
      }),
    }
  )
);
