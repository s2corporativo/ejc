import { create } from "zustand";
import api, {
  getAccessToken,
  limparCasoAtivo,
  refreshAccessToken,
  setAccessToken,
} from "../lib/api";
import { RASCUNHO_KEY } from "../lib/intakeRascunho";
import { limparCadastroManual } from "./cadastroManual";
import type { User } from "../types";

export type AuthStatus = "initializing" | "authenticated" | "unauthenticated";

type SecurityState = {
  permissions?: string[];
};

// B3 (auditoria do Bloco 3): o rascunho da Entrada Única vive em
// sessionStorage e pode conter dados pessoais do relato — não pode sobreviver
// ao fim da sessão numa estação compartilhada. Prefixo espelha
// pages/EntradaUnica/rascunhoStorage.ts (sem import de pages/ em stores/).
function limparRascunhosEntrada() {
  try {
    for (let i = sessionStorage.length - 1; i >= 0; i--) {
      const chave = sessionStorage.key(i);
      if (chave && chave.startsWith("ejc_entrada_rascunho")) {
        sessionStorage.removeItem(chave);
      }
    }
  } catch {
    /* storage indisponível não pode quebrar o logout */
  }
}

// FE-08: só o necessário para montar o shell antes do bootstrap fica em
// localStorage. E-mail, telefone, OAB e OAB do DJEN são dados pessoais que
// não precisam sobreviver ao reload — o /users/me repõe tudo em memória.
export const CAMPOS_USUARIO_PERSISTIDOS = [
  "id",
  "full_name",
  "role",
  "permissions",
  "avatar_url",
] as const satisfies readonly (keyof User)[];

export type StoredUser = Pick<
  User,
  (typeof CAMPOS_USUARIO_PERSISTIDOS)[number]
>;

function readStoredUser(): User | null {
  try {
    const raw = localStorage.getItem("ejc_user");
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<User> | null;
    if (!parsed || typeof parsed.id !== "string" || !parsed.id) return null;
    return parsed as User;
  } catch {
    localStorage.removeItem("ejc_user");
    return null;
  }
}

/** Recorta o usuário aos campos persistíveis (FE-08). */
export function partializeUser(user: User): StoredUser {
  const out: Partial<User> = {};
  for (const campo of CAMPOS_USUARIO_PERSISTIDOS) {
    if (user[campo] !== undefined) {
      (out as Record<string, unknown>)[campo] = user[campo];
    }
  }
  return out as StoredUser;
}

function persistUser(user: User | null) {
  try {
    if (user) {
      localStorage.setItem("ejc_user", JSON.stringify(partializeUser(user)));
    } else localStorage.removeItem("ejc_user");
  } catch {
    // Storage indisponível não deve derrubar a sessão em memória.
  }
}

/** Limpa TUDO que identifica a sessão anterior (token, usuário, rascunhos,
 *  caso ativo). Fonte única para o logout da store e a queda de sessão. */
function limparSessaoLocal() {
  setAccessToken(null);
  localStorage.removeItem(RASCUNHO_KEY);
  limparRascunhosEntrada();
  limparCadastroManual();
  // FE-07: o caso ativo vive em sessionStorage e reidratava para o próximo
  // usuário da mesma aba (id, título, nº do processo, nome do cliente).
  limparCasoAtivo();
  persistUser(null);
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
// FE-02: o access token não sobrevive ao reload (só memória). Um usuário
// persistido é o indício de sessão anterior — o bootstrap tenta reidratar o
// access pelo cookie httpOnly de refresh antes de decidir.
const initialStatus: AuthStatus =
  getAccessToken() || storedUser ? "initializing" : "unauthenticated";

export const useAuth = create<AuthState>((set, get) => ({
  user: storedUser,
  status: initialStatus,
  bootstrap: async () => {
    if (!getAccessToken()) {
      // Sem indício de sessão anterior: não bate no /auth/refresh à toa
      // (anônimo na tela de login).
      if (!get().user && !readStoredUser()) {
        persistUser(null);
        set({ user: null, status: "unauthenticated" });
        return;
      }
      set({ status: "initializing" });
      try {
        // Reidrata o access em memória pelo cookie httpOnly `ejc_refresh`.
        // Promise compartilhada em api.ts: chamadas concorrentes não rotacionam
        // o refresh duas vezes.
        await refreshAccessToken();
      } catch {
        limparSessaoLocal();
        set({ user: null, status: "unauthenticated" });
        return;
      }
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

      const needsTwoFactorSetup =
        error?.response?.data?.precisa_configurar_2fa ||
        error?.response?.data?.detail?.precisa_configurar_2fa;
      if (responseStatus === 403 && needsTwoFactorSetup) {
        const cachedUser = get().user ?? readStoredUser();
        set({
          user: cachedUser,
          status: cachedUser ? "authenticated" : "unauthenticated",
        });
        return;
      }

      if (responseStatus === 401 || responseStatus === 403) {
        limparSessaoLocal();
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
    // O rascunho de intake carrega dados pessoais extraídos de documentos —
    // não pode sobreviver ao fim da sessão em estação compartilhada (LGPD).
    limparSessaoLocal();
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
