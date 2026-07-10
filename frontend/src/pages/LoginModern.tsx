import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import api from "../lib/api";
import type { LoginResponse } from "../types";
import { useAuth } from "../stores/auth";
import { usePreferencesStore } from "../stores/preferences";
import { canRoleAccessPath } from "../config/moduleRegistry";

const BRAND_LOGO = "/brand/de-paula-teixeira-logo.jpg";

type LoginLocationState = { from?: string } | null;

export default function LoginModern() {
  const { setSession } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [erro, setErro] = useState("");
  const [loading, setLoading] = useState(false);

  const requestedPath = (location.state as LoginLocationState)?.from;

  const submit = async () => {
    setErro("");
    setLoading(true);
    try {
      const { data } = await api.post<LoginResponse>("/auth/login", {
        email,
        password,
      });
      localStorage.setItem("ejc_access", data.access_token);
      const user = {
        id: data.user_id,
        email,
        full_name: data.full_name,
        role: data.role,
      };
      setSession(user);
      if (data.must_change_password) {
        nav("/trocar-senha", { replace: true });
        return;
      }
      if (data.role === "cliente_externo") {
        const portalDestination = requestedPath?.startsWith("/portal")
          ? requestedPath
          : "/portal";
        nav(portalDestination, { replace: true });
        return;
      }

      const isValidStaffDestination =
        requestedPath?.startsWith("/") &&
        !requestedPath.startsWith("/portal") &&
        !requestedPath.startsWith("/login");
      if (isValidStaffDestination && requestedPath) {
        nav(requestedPath, { replace: true });
        return;
      }

      const preferredHome = usePreferencesStore.getState().homeRoute;
      nav(canRoleAccessPath(data.role, preferredHome) ? preferredHome : "/", {
        replace: true,
      });
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha no login");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen overflow-hidden bg-canvas text-slate-950">
      <div className="brand-watermark opacity-[0.05]" aria-hidden="true" />
      <div className="relative z-10 grid min-h-screen lg:grid-cols-[1fr_460px]">
        <section className="relative hidden flex-col justify-between overflow-hidden p-10 text-slate-900 lg:flex">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_35%_45%,rgba(201,162,39,.10),transparent_30rem),radial-gradient(circle_at_90%_90%,rgba(216,185,78,.12),transparent_26rem)]" />
          <div className="relative flex items-center gap-3">
            <img
              src={BRAND_LOGO}
              alt="De Paula Teixeira Sociedade de Advogados"
              className="brand-logo-img h-28 w-auto max-w-[360px] rounded-xl bg-white p-2 shadow-soft ring-1 ring-slate-100"
            />
          </div>

          <div className="relative max-w-2xl">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-primary-200 bg-primary-50 px-3 py-1 text-xs font-semibold text-primary-700">
              <Sparkles className="h-3.5 w-3.5" />
              Plataforma jurídica empresarial
            </div>
            <h1 className="max-w-xl text-5xl font-semibold leading-tight tracking-tight text-slate-950">
              Gestão jurídica com controle, produtividade e IA revisável.
            </h1>
            <p className="mt-5 max-w-xl text-base leading-7 text-slate-500">
              Centralize casos, clientes, prazos, documentos, financeiro e
              produção jurídica em um ambiente seguro para operação
              profissional.
            </p>
            <div className="mt-8 grid max-w-xl grid-cols-3 gap-3">
              {[
                ["Prazos", "Alertas críticos"],
                ["Financeiro", "Honorários e receitas"],
                ["IA", "Respostas revisáveis"],
              ].map(([title, desc]) => (
                <div
                  key={title}
                  className="rounded-2xl border border-slate-200/60 bg-white p-4 shadow-soft"
                >
                  <div className="text-sm font-semibold text-slate-950">
                    {title}
                  </div>
                  <div className="mt-1 text-xs text-slate-400">{desc}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="relative flex items-center gap-2 text-xs text-slate-500">
            <ShieldCheck className="h-4 w-4 text-primary-500" />
            Acesso restrito com trilha de auditoria e perfis de permissão.
          </div>
        </section>

        <section className="flex min-h-screen items-center justify-center px-5 py-10">
          <div className="w-full max-w-md animate-rise">
            <div className="mb-8 flex items-center lg:hidden">
              <img
                src={BRAND_LOGO}
                alt="De Paula Teixeira Sociedade de Advogados"
                className="brand-logo-img h-20 w-auto max-w-[280px] rounded-xl bg-white p-1.5 shadow-soft ring-1 ring-slate-100"
              />
            </div>

            <div className="rounded-2xl border border-slate-200/60 bg-white p-8 shadow-[0_8px_30px_rgba(16,24,40,.08)]">
              <div className="mb-7">
                <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-primary-50 text-primary-600">
                  <LockKeyhole className="h-5 w-5" />
                </div>
                <p className="eyebrow">Área restrita</p>
                <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  Entrar no EJC
                </h1>
                <p className="mt-2 text-sm text-slate-500">
                  Use suas credenciais internas para acessar o escritório
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
