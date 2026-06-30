// ── API client com refresh automático ────────────────────
import axios from "axios";

const api = axios.create({ baseURL: "/api" });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("ejc_access");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

let refreshing: Promise<string> | null = null;

api.interceptors.response.use(
  (r) => r,
  async (error) => {
    const original = error.config;
    // Troca de senha obrigatória: backend bloqueia tudo com 403+flag
    if (
      error.response?.status === 403 &&
      error.response?.data?.must_change_password &&
      window.location.pathname !== "/trocar-senha"
    ) {
      window.location.href = "/trocar-senha";
      return Promise.reject(error);
    }
    if (error.response?.status === 401 && !original._retry) {
      original._retry = true;
      const rt = localStorage.getItem("ejc_refresh");
      if (!rt) {
        logout();
        return Promise.reject(error);
      }
      try {
        refreshing ??= axios
          .post("/api/v1/auth/refresh", { refresh_token: rt })
          .then((res) => {
            localStorage.setItem("ejc_access", res.data.access_token);
            localStorage.setItem("ejc_refresh", res.data.refresh_token);
            return res.data.access_token as string;
          })
          .finally(() => {
            refreshing = null;
          });
        const newToken = await refreshing;
        original.headers.Authorization = `Bearer ${newToken}`;
        return api(original);
      } catch {
        logout();
      }
    }
    return Promise.reject(error);
  },
);

export function logout() {
  const rt = localStorage.getItem("ejc_refresh");
  if (rt) axios.post("/api/v1/auth/logout", { refresh_token: rt }).catch(() => {});
  localStorage.removeItem("ejc_access");
  localStorage.removeItem("ejc_refresh");
  localStorage.removeItem("ejc_user");
  window.location.href = "/login";
}

export default api;
