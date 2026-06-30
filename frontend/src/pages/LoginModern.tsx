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
    <div className="min-h-screen overflow-hidden bg-[#F7F8FA] text-slate-950">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_18%_10%,rgba(185,138,60,.18),transparent_28rem),radial-gradient(circle_at_92%_8%,rgba(110,82,40,.10),transparent_24rem)]" />
      <div className="relative grid min-h-screen lg:grid-cols-[1fr_460px]">
        <section className="hidden flex-col justify-between border-r border-slate-200 bg-white/55 p-10 backdrop-blur-xl lg:flex">
          <div className="flex items-center gap-3">
            <img
              src={BRAND_LOGO}
              alt="De Paula Teixeira Sociedade de Advogados"
              className="brand-logo-img h-20 w-auto max-w-[270px]"
            />
          </div>

          <div className="max-w-2xl">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-semibold text-amber-800">
              <Sparkles className="h-3.5 w-3.5" />
              Plataforma juridica empresarial
            </div>
            <h1 className="max-w-xl text-5xl font-semibold leading-tight tracking-tight text-slate-950">
              Gestao juridica com controle, produtividade e IA revisavel.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-500">
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
                  className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm"
                >
                  <div className="text-sm font-semibold text-slate-950">
                    {title}
                  </div>
                  <div className="mt-1 text-xs text-slate-500">{desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-slate-500">
            <ShieldCheck className="h-4 w-4 text-amber-700" />
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

            <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-xl shadow-slate-200/70">
              <div className="mb-7">
                <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-blue-50 text-blue-700">
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
                <div className="mb-4 flex items-start gap-2 rounded-xl bg-red-50 px-3 py-2.5 text-sm text-red-700 ring-1 ring-inset ring-red-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{erro}</span>
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
                    className="text-xs font-medium text-amber-700 transition-colors hover:text-blue-700"
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
