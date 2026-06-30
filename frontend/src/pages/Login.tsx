import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import api from "../lib/api";
import { useAuth } from "../stores/auth";

export default function Login() {
  const { setSession } = useAuth();
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setErro("");
    setLoading(true);
    try {
      const { data } = await api.post("/auth/login", { email, password });
      localStorage.setItem("ejc_access", data.access_token);
      localStorage.setItem("ejc_refresh", data.refresh_token);
      const user = {
        id: data.user_id,
        email,
        full_name: data.full_name,
        role: data.role,
      };
      localStorage.setItem("ejc_user", JSON.stringify(user));
      setSession(user);
      if (data.must_change_password) {
        nav("/trocar-senha");
        return;
      }
      nav(data.role === "cliente_externo" ? "/portal" : "/");
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha no login");
    } finally {
      setLoading(false);
    }
  };

  return (
    /* Fundo: gradiente navy com brilho bronze sutil vindo do logo */
    <div
      className="min-h-screen flex items-center justify-center px-4 relative overflow-hidden
                    bg-gradient-to-b from-navy-950 via-navy-900 to-navy"
    >
      {/* Halo bronze ambiente — referencia as cores douradas das balanças */}
      <div
        className="pointer-events-none absolute -top-28 left-1/2 -translate-x-1/2 w-[50rem] h-[50rem]
                      rounded-full bg-bronze/8 blur-3xl"
        aria-hidden
      />

      <div className="w-full max-w-sm relative animate-rise">
        <div className="card p-8 shadow-float ring-1 ring-bronze/40 border-bronze/50">
          {/* ── Logomarca — centralizada e destacada ── */}
          <div className="flex flex-col items-center mb-8">
            <img
              src="/logo.png"
              alt="De Paula Teixeira Advogados"
              className="h-28 w-auto object-contain"
            />
            {/* Linha bronze igual ao do sidebar */}
            <div className="mt-3 h-px w-12 bg-bronze/50" aria-hidden />
            <p className="mt-2 eyebrow">Área Restrita</p>
          </div>

          {erro && (
            <div className="mb-4 px-3 py-2.5 rounded-lg bg-red-50 text-red-700 text-sm ring-1 ring-inset ring-red-200">
              {erro}
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="label">E-mail</label>
              <input
                className="input"
                type="email"
                value={email}
                autoFocus
                placeholder="seu@escritorio.adv.br"
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
              />
            </div>
            <div>
              <label className="label">Senha</label>
              <input
                className="input"
                type="password"
                value={password}
                placeholder="••••••••"
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit()}
              />
            </div>
            <button
              className="btn-primary w-full"
              disabled={loading}
              onClick={submit}
            >
              {loading ? "Entrando…" : "Entrar"}
            </button>
            <div className="text-center">
              <Link
                to="/recuperar-senha"
                className="text-xs text-bronze hover:text-bronze-dark transition-colors"
              >
                Esqueci minha senha
              </Link>
            </div>
          </div>
        </div>
        <p className="mt-6 text-center text-[11px] text-slate-300/70 tracking-wide">
          De Paula Teixeira Sociedade de Advogados
        </p>
      </div>
    </div>
  );
}
