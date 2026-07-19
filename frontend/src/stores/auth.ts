import { create } from "zustand";
import api, { getAccessToken } from "../lib/api";
import { RASCUNHO_KEY } from "../lib/intakeRascunho";
import { limparCadastroManual } from "./cadastroManual";
import type { User } from "../types";

export type AuthStatus = "initializing" | "authenticated" | "unauthenticated";

type SecurityState = {
  permissions?: string[];
};

function readStoredUser(): User | null {
  try {
    return JSON.parse(
      localStorage.getItem("ejc_user") || "null",
    ) as User | null;
  } catch {
    localStorage.removeItem("ejc_user");
    return null;
  }
}

function persistUser(user: User | null) {
  try {
    if (user) localStorage.setItem("ejc_user", JSON.stringify(user));
    else localStorage.removeItem("ejc_user");
  } catch {
    // Storage indisponível não deve derrubar a sessão em memória.
  }
}

interface AuthState {
  user: User | null;
  status: AuthStatus;
  bootstrap: () => Promise<void>;
  setSession: (u: User) => void;
  clearSession: () => void;
  loadUser: () => void;
  /** Mescla campos no usuário atual (ex.: avatar_url) e persiste. */
  updateUser: (patch: Partial<User>) => void;
}

const storedUser = readStoredUser();
const initialStatus: AuthStatus = getAccessToken()
  ? "initializing"
  : "unauthenticated";

export const useAuth = create<AuthState>((set, get) => ({
  user: storedUser,
  status: initialStatus,
  bootstrap: async () => {
    if (!getAccessToken()) {
      persistUser(null);
      set({ user: null, status: "unauthenticated" });
      return;
    }

    set({ status: "initializing" });
    try {
      const profileResponse = await api.get<User>("/users/me");
      const securityResponse = await api
        .get<SecurityState>("/users/me/security")
        .catch(() => null);
      const user: User = {
        ...profileResponse.data,
        permissions:
          securityResponse?.data?.permissions ??
          profileResponse.data.permissions ??
          get().user?.permissions,
      };
      persistUser(user);
      set({ user, status: "authenticated" });
    } catch (error: any) {
      const responseStatus = error?.response?.status;

      // Troca de senha OBRIGATÓRIA: o middleware devolve 403 em /users/me até
      // o usuário trocar a senha. NÃO é sessão inválida — derrubar o token
      // aqui expulsava o usuário do /trocar-senha em loop (achado A1 do E2E).
      // Mantém a sessão cacheada; o interceptor do api.ts redireciona para
      // /trocar-senha e o middleware bloqueia todo o resto até a troca.
      if (
        responseStatus === 403 &&
        error?.response?.data?.must_change_password
      ) {
        const cachedUser = get().user ?? readStoredUser();
        set({
          user: cachedUser,
          status: cachedUser ? "authenticated" : "unauthenticated",
        });
        return;
      }

      if (responseStatus === 401 || responseStatus === 403) {
        localStorage.removeItem("ejc_access");
        localStorage.removeItem(RASCUNHO_KEY);
        limparCadastroManual();
        persistUser(null);
        set({ user: null, status: "unauthenticated" });
        return;
      }

      // Falha transitória de rede/servidor: preserva a sessão cacheada. O backend
      // continua sendo a autoridade em todas as requisições e pode negar acesso.
      const cachedUser = get().user ?? readStoredUser();
      set({
        user: cachedUser,
        status: cachedUser ? "authenticated" : "unauthenticated",
      });
    }
  },
  setSession: (user) => {
    persistUser(user);
    set({ user, status: "authenticated" });
  },
  clearSession: () => {
    localStorage.removeItem("ejc_access");
    // O rascunho de intake carrega dados pessoais extraídos de documentos —
    // não pode sobreviver ao fim da sessão em estação compartilhada (LGPD).
    localStorage.removeItem(RASCUNHO_KEY);
    persistUser(null);
    set({ user: null, status: "unauthenticated" });
  },
  loadUser: () => {
    const user = readStoredUser();
    set({
      user,
      status: user && getAccessToken() ? "authenticated" : "unauthenticated",
    });
  },
  updateUser: (patch) => {
    const current = get().user;
    if (!current) return;
    const next = { ...current, ...patch };
    persistUser(next);
    set({ user: next });
  },
}));
