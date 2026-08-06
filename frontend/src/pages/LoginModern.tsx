import { useState } from "react";
import {
  Link,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  LockKeyhole,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import api from "../lib/api";
import type { LoginResponse } from "../types";
import { useAuth } from "../stores/auth";
import { usePreferencesStore } from "../stores/preferences";
import { canRoleAccessPath } from "../config/moduleRegistry";
import { officeBranding } from "../config/officeBranding";
// Vinheta de marca (10s, muda, toca UMA vez e congela no logo final)
const BRAND_INTRO_VIDEO = "/brand/logo-intro.mp4";
const BRAND_INTRO_POSTER = "/brand/logo-intro-poster.jpg";

/** Vinheta da logomarca no login. Respeita prefers-reduced-motion e cai
 *  para a logomarca estática se o vídeo falhar (rede lenta/bloqueio). */
function BrandIntro({ className }: { className?: string }) {
  const [fallback, setFallback] = useState(false);
  const reduceMotion =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  if (fallback || reduceMotion) {
    return (
      <img
        src={officeBranding.logoPath}
        alt="De Paula Teixeira Sociedade de Advogados"
        className={`brand-logo-img h-40 w-auto max-w-[440px] ${className || ""}`}
      />
    );
  }
  return (
    <video
      className={`w-[460px] max-w-full rounded-xl shadow-card ${className || ""}`}
      autoPlay
      muted
      playsInline
      preload="auto"
      poster={BRAND_INTRO_POSTER}
      onError={() => setFallback(true)}
      aria-label="De Paula Teixeira Sociedade de Advogados"
    >
      <source src={BRAND_INTRO_VIDEO} type="video/mp4" />
    </video>
  );
}

type LoginLocationState = { from?: string } | null;

export default function LoginModern() {
  const { setSession, bootstrap } = useAuth();
  const nav = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totpCode, setTotpCode] = useState("");
  const [requiresTotp, setRequiresTotp] = useState(false);
  const [erro, setErro] = useState("");
  const [loading, setLoading] = useState(false);

  const requestedPath = (location.state as LoginLocationState)?.from;

  // Aviso pós-troca de senha obrigatória: logout() redireciona (hard) para
  // /login?motivo=senha-alterada — sem isto o usuário caía deslogado sem feedback.
  const [searchParams] = useSearchParams();
  const senhaAlterada = searchParams.get("motivo") === "senha-alterada";

  const submit = async () => {
    setErro("");
    if (requiresTotp && !/^\d{6}$/.test(totpCode)) {
      setErro("Informe o código de 6 dígitos do aplicativo autenticador.");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.post<LoginResponse>("/auth/login", {
        email,
        password,
        ...(totpCode ? { totp_code: totpCode } : {}),
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
      if (data.precisa_configurar_2fa) {
        nav("/configurar-2fa", { replace: true });
        return;
      }
      await bootstrap();
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
      const detail = e.response?.data?.detail;
      const message =
        typeof detail === "string"
          ? detail
          : detail?.message || "Falha no login";
      if (message.includes("TOTP obrigatório")) {
        setRequiresTotp(true);
        setErro("Confirme o código do aplicativo autenticador.");
      } else {
        setErro(message);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen overflow-hidden bg-canvas text-slate-950">
      <div className="brand-watermark opacity-[0.05]" aria-hidden="true" />
      <div className="relative z-10 grid min-h-screen lg:grid-cols-[1fr_460px]">
        <section className="relative hidden flex-col justify-between overflow-hidden p-10 text-slate-900 lg:flex">
          <div className="relative flex items-center gap-3">
            {/* Vinheta da marca — toca uma vez e congela na logomarca */}
            <BrandIntro />
          </div>

          <div className="relative max-w-2xl">
            <div className="mb-4 inline-flex items-center gap-2 rounded-full bg-ouro-palha px-3 py-1 text-xs font-semibold text-ouro-profundo">
              <Sparkles className="h-3.5 w-3.5" />
              Plataforma jurídica empresarial
            </div>
            <h1 className="max-w-xl text-2xl font-bold leading-snug tracking-tight text-slate-950">
              Gestão jurídica com controle, produtividade e IA revisável.
            </h1>
            <p className="mt-3 max-w-xl text-sm leading-6 text-slate-500">
              Centralize casos, clientes, prazos, documentos, financeiro e
              produção jurídica em um ambiente seguro para operação
              profissional.
            </p>
            <div className="mt-4 grid max-w-xl grid-cols-3 gap-3">
              {[
                ["Prazos", "Alertas críticos"],
                ["Financeiro", "Honorários e receitas"],
                ["IA", "Respostas revisáveis"],
              ].map(([title, desc]) => (
                <div
                  key={title}
                  className="rounded-xl border border-border bg-white p-3 shadow-soft transition-shadow duration-150 hover:shadow-card"
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
            <div className="mb-8 flex items-center justify-center lg:hidden">
              <img
                src={officeBranding.logoPath}
                alt="De Paula Teixeira Sociedade de Advogados"
                className="brand-logo-img h-28 w-auto max-w-[320px]"
              />
            </div>

            {/* Card de login flat: borda 1px + sombra mínima (idioma Verdelimp) */}
            <div className="rounded-xl border border-border bg-white p-6 shadow-card">
              <div className="mb-7">
                <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl bg-ouro-palha text-ouro-profundo">
                  {requiresTotp ? (
                    <ShieldCheck className="h-5 w-5" />
                  ) : (
                    <LockKeyhole className="h-5 w-5" />
                  )}
                </div>
                <p className="eyebrow">
                  {requiresTotp ? "Segunda etapa" : "Área restrita"}
                </p>
                <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-950">
                  {requiresTotp ? "Confirmar autenticação" : "Entrar no EJC"}
                </h1>
                <p className="mt-2 text-sm text-slate-500">
                  {requiresTotp
                    ? "Digite o código temporário do aplicativo autenticador."
                    : "Use suas credenciais internas para acessar o escritório digital."}
                </p>
              </div>

              {senhaAlterada && !erro && (
                <div
                  role="status"
                  className="mb-4 flex items-start gap-2 rounded-xl bg-success-50 px-3 py-2.5 text-sm text-success-700 ring-1 ring-inset ring-success-200"
                >
                  <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>
                    Senha alterada com sucesso — entre novamente com a nova
                    senha.
                  </span>
                </div>
              )}
              {erro && (
                <div className="mb-4 flex items-start gap-2 rounded-xl bg-danger-50 px-3 py-2.5 text-sm text-danger-700 ring-1 ring-inset ring-danger-200">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  <span>{erro}</span>
                </div>
              )}

              <form
                className="space-y-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  void submit();
                }}
              >
                <div>
                  <label className="label">E-mail</label>
                  <input
                    className="input h-11"
                    type="email"
                    value={email}
                    autoFocus={!requiresTotp}
                    disabled={requiresTotp}
                    placeholder="seu@escritorio.adv.br"
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </div>
                <div>
                  <label className="label">Senha</label>
                  <input
                    className="input h-11"
                    type="password"
                    value={password}
                    disabled={requiresTotp}
                    placeholder="********"
                    onChange={(e) => setPassword(e.target.value)}
                  />
                </div>
                {requiresTotp && (
                  <div>
                    <label className="label">Código de autenticação</label>
                    <input
                      className="input h-11 font-mono text-center tracking-[0.4em]"
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      autoFocus
                      maxLength={6}
                      value={totpCode}
                      placeholder="000000"
                      onChange={(e) =>
                        setTotpCode(e.target.value.replace(/\D/g, ""))
                      }
                    />
                  </div>
                )}
                <button
                  type="submit"
                  className="btn-primary h-11 w-full"
                  disabled={loading}
                >
                  {loading ? (
                    "Validando..."
                  ) : (
                    <>
                      {requiresTotp ? "Confirmar" : "Entrar"}{" "}
                      <ArrowRight className="h-4 w-4" />
                    </>
                  )}
                </button>
                {requiresTotp ? (
                  <button
                    type="button"
                    className="btn-ghost w-full justify-center text-xs"
                    onClick={() => {
                      setRequiresTotp(false);
                      setTotpCode("");
                      setErro("");
                    }}
                  >
                    Voltar e alterar credenciais
                  </button>
                ) : (
                  <div className="space-y-2 text-center">
                    <Link
                      to="/recuperar-senha"
                      className="text-xs font-medium text-primary-600 transition-colors hover:text-primary-700"
                    >
                      Esqueci minha senha
                    </Link>
                    <p className="text-xs text-slate-400">
                      Não tem acesso? Solicite ao administrador do escritório.
                    </p>
                  </div>
                )}
              </form>
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
