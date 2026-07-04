import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  LockKeyhole,
  Scale,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";

const BRAND_LOGO = "/brand/de-paula-teixeira-logo.jpg";

export default function LoginModern() {
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
    <div className="min-h-screen overflow-hidden bg-slate-50 text-slate-950">
      <div className="relative grid min-h-screen lg:grid-cols-[1fr_460px]">
        <section className="relative hidden flex-col justify-between overflow-hidden bg-gradient-to-br from-primary-950 via-primary-900 to-ai-900 p-10 text-white lg:flex">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_10%,rgba(129,140,248,.18),transparent_30rem),radial-gradient(circle_at_90%_90%,rgba(167,139,250,.14),transparent_26rem)]" />
          <div className="relative flex items-center gap-3">
            <img
              src={BRAND_LOGO}
              alt="De Paula Teixeira Sociedade de Advogados"
              className="brand-logo-img h-20 w-auto max-w-[270px] rounded-xl bg-white p-1.5"
            />
          </div>

          <div className="relative max-w-2xl">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1 text-xs font-semibold text-primary-100">
              <Sparkles className="h-3.5 w-3.5" />
              Plataforma juridica empresarial
            </div>
            <h1 className="max-w-xl text-5xl font-semibold leading-tight tracking-tight text-white">
              Gestao juridica com controle, produtividade e IA revisavel.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-primary-200/80">
              Centralize casos, clientes, prazos, documentos, financeiro e
              producao juridica em um ambiente seguro para operacao
              profissional.
            </p>
            <div className="mt-8 grid max-w-xl grid-cols-3 gap-3">
              {[
                ["Prazos", "Alertas criticos"],
                ["Financeiro", "Honorarios e receitas"],
                ["IA", "Rascunhos revisaveis"],
              ].map(([title, desc]) => (
                <div
                  key={title}
                  className="rounded-2xl border border-white/10 bg-white/5 p-4 backdrop-blur-sm"
                >
                  <div className="text-sm font-semibold text-white">
                    {title}
                  </div>
                  <div className="mt-1 text-xs text-primary-200/70">{desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="relative flex items-center gap-2 text-xs text-primary-200/70">
            <ShieldCheck className="h-4 w-4 text-primary-300" />
            Acesso restrito com trilha de auditoria e perfis de permissao.
          </div>
        </section>

        <section className="flex min-h-screen items-center justify-center px-5 py-10">
          <div className="w-full max-w-md animate-rise">
            <div className="mb-8 flex items-center lg:hidden">
              <img
                src={BRAND_LOGO}
                alt="De Paula Teixeira Sociedade de Advogados"
                className="brand-logo-img h-16 w-auto max-w-[240px]"
              />
            </div>

            <div className="rounded-2xl border border-slate-200/60 bg-white p-8 shadow-xl shadow-slate-200/60">
              <div className="mb-7">
                <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
                  <LockKeyhole className="h-5 w-5" />
                </div>
                <p className="eyebrow">Area restrita</p>
                <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  Entrar no EJC
                </h1>
                <p className="mt-2 text-sm text-slate-500">
                  Use suas credenciais internas para acessar o escritorio
                  digital.
                </p>
              </div>

              {erro && (
                <div className="mb-4 flex items-start gap-2 rounded-xl bg-danger-50 px-3 py-2.5 text-sm text-danger-700 ring-1 ring-inset ring-danger-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{erro}</span>
                </div>
              )}

              <div className="space-y-4">
                <div>
                  <label className="label">E-mail</label>
                  <input
                    className="input h-11"
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
                    className="input h-11"
                    type="password"
                    value={password}
                    placeholder="********"
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && submit()}
                  />
                </div>
                <button
                  className="btn-primary h-11 w-full"
                  disabled={loading}
                  onClick={submit}
                >
                  {loading ? (
                    "Entrando..."
                  ) : (
                    <>
                      Entrar <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
                <div className="text-center">
                  <Link
                    to="/recuperar-senha"
                    className="text-xs font-medium text-primary-600 transition-colors hover:text-primary-700"
                  >
                    Esqueci minha senha
                  </Link>
                </div>
              </div>
            </div>
            <p className="mt-6 text-center text-[11px] tracking-wide text-slate-400">
              De Paula Teixeira Sociedade de Advogados
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
