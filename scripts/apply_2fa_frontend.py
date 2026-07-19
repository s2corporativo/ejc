#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(path, old, new):
    p = ROOT / path
    t = p.read_text(encoding="utf-8")
    if t.count(old) != 1:
        raise RuntimeError(f"{path}: marcador encontrado {t.count(old)} vez(es)")
    p.write_text(t.replace(old, new, 1), encoding="utf-8")


patch(
    "frontend/src/types/index.ts",
    '''export interface AuthTokens {
  access_token: string;
  token_type?: string;
}
export interface LoginResponse extends AuthTokens {
  user_id: string;
  full_name: string;
  role: string;
  must_change_password?: boolean;
}
''',
    '''export interface AuthTokens {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
}
export interface LoginResponse extends AuthTokens {
  user_id: string;
  full_name: string;
  role: string;
  must_change_password?: boolean;
  precisa_configurar_2fa?: boolean;
}
''',
)
patch(
    "frontend/src/pages/LoginModern.tsx",
    '''      setSession(user);
      await bootstrap();

      if (data.must_change_password) {
''',
    '''      setSession(user);

      if (data.must_change_password) {
''',
)
patch(
    "frontend/src/pages/LoginModern.tsx",
    '''        return;
      }
      if (data.role === "cliente_externo") {
''',
    '''        return;
      }
      if (data.precisa_configurar_2fa) {
        nav("/configurar-2fa", { replace: true });
        return;
      }
      await bootstrap();
      if (data.role === "cliente_externo") {
''',
)
patch(
    "frontend/src/stores/auth.ts",
    '''      if (responseStatus === 401 || responseStatus === 403) {
''',
    '''      const needsTwoFactorSetup =
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
''',
)
patch(
    "frontend/src/lib/api.ts",
    '''    // Só tenta refresh quando a requisição realmente partiu de uma sessão com
''',
    '''    const needsTwoFactorSetup =
      error.response?.data?.precisa_configurar_2fa ||
      error.response?.data?.detail?.precisa_configurar_2fa;
    if (
      error.response?.status === 403 &&
      needsTwoFactorSetup &&
      window.location.pathname !== "/configurar-2fa"
    ) {
      window.location.href = "/configurar-2fa";
      return Promise.reject(error);
    }

    // Só tenta refresh quando a requisição realmente partiu de uma sessão com
''',
)
patch(
    "frontend/src/pages/TrocarSenha.tsx",
    '''        localStorage.setItem("ejc_access", data.access_token);
        await bootstrap();
''',
    '''        localStorage.setItem("ejc_access", data.access_token);
        if (data.precisa_configurar_2fa) {
          toast.success("Senha alterada. Agora proteja a conta com o 2FA.");
          nav("/configurar-2fa", { replace: true });
          return;
        }
        await bootstrap();
''',
)
patch(
    "frontend/src/App.tsx",
    'const TrocarSenha = lazy(() => import("./pages/TrocarSenha"));\n',
    'const TrocarSenha = lazy(() => import("./pages/TrocarSenha"));\nconst Configurar2FA = lazy(() => import("./pages/Configurar2FA"));\n',
)
patch(
    "frontend/src/App.tsx",
    '''            <Route
              path="/portal"
''',
    '''            <Route
              path="/configurar-2fa"
              element={
                <Protected>
                  <Configurar2FA />
                </Protected>
              }
            />

            <Route
              path="/portal"
''',
)
print("frontend 2FA aplicado")
