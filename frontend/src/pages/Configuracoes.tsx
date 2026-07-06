import { Link } from "react-router-dom";
import {
  Sun,
  Moon,
  Monitor,
  KeyRound,
  ShieldCheck,
  Users,
  Check,
  ChevronRight,
} from "lucide-react";
import { PageHeader, SectionCard, cn } from "../components/UI";
import { THEME_LABELS, useThemeStore, type ThemeMode } from "../stores/theme";
import { useAuth } from "../stores/auth";

const THEME_OPTIONS: { mode: ThemeMode; icon: typeof Sun }[] = [
  { mode: "light", icon: Sun },
  { mode: "dark", icon: Moon },
  { mode: "system", icon: Monitor },
];

export default function Configuracoes() {
  const { theme, setTheme } = useThemeStore();
  const { user } = useAuth();
  const isAdmin = user?.role === "superadmin" || user?.role === "admin";

  return (
    <div className="max-w-3xl space-y-5">
      <PageHeader
        eyebrow="Preferencias"
        title="Configuracoes"
        subtitle="Ajuste a aparencia do sistema e gerencie sua conta."
      />

      <SectionCard
        title="Aparencia"
        subtitle="Escolha o tema da interface. O modo Sistema acompanha a preferencia do seu dispositivo."
      >
        <div className="grid gap-3 sm:grid-cols-3">
          {THEME_OPTIONS.map(({ mode, icon: Icon }) => {
            const active = theme === mode;
            return (
              <button
                key={mode}
                type="button"
                onClick={() => setTheme(mode)}
                aria-pressed={active}
                className={cn(
                  "flex items-center gap-3 rounded-xl border px-4 py-3 text-left transition-all",
                  active
                    ? "border-primary-500 bg-primary-50 ring-1 ring-inset ring-primary-200"
                    : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50",
                )}
              >
                <span
                  className={cn(
                    "rounded-lg p-2",
                    active
                      ? "bg-primary-600 text-white"
                      : "bg-slate-100 text-slate-500",
                  )}
                >
                  <Icon className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1 text-sm font-medium text-slate-800">
                  {THEME_LABELS[mode]}
                </span>
                {active && <Check className="h-4 w-4 text-primary-600" />}
              </button>
            );
          })}
        </div>
      </SectionCard>

      <SectionCard
        title="Conta e seguranca"
        subtitle="Gerencie suas credenciais de acesso."
      >
        <div className="space-y-3">
          <Link
            to="/trocar-senha"
            className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 transition-all hover:border-slate-300 hover:bg-slate-50"
          >
            <span className="rounded-lg bg-slate-100 p-2 text-slate-500">
              <KeyRound className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-slate-800">
                Trocar senha
              </div>
              <p className="text-xs text-slate-500">
                Defina uma nova senha de acesso ao sistema.
              </p>
            </div>
            <ChevronRight className="h-4 w-4 text-slate-400" />
          </Link>

          <div className="flex items-start gap-3 rounded-xl border border-slate-200 bg-slate-50/60 px-4 py-3">
            <span className="rounded-lg bg-slate-100 p-2 text-slate-500">
              <ShieldCheck className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-slate-800">
                Autenticacao em duas etapas (2FA)
              </div>
              <p className="text-xs text-slate-500">
                A configuracao do 2FA fica no menu de seguranca da barra
                superior (icone de escudo).
              </p>
            </div>
          </div>
        </div>
      </SectionCard>

      {isAdmin && (
        <SectionCard
          title="Administracao"
          subtitle="Ferramentas restritas a administradores."
        >
          <Link
            to="/usuarios"
            className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 transition-all hover:border-slate-300 hover:bg-slate-50"
          >
            <span className="rounded-lg bg-slate-100 p-2 text-slate-500">
              <Users className="h-4 w-4" />
            </span>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-medium text-slate-800">
                Gerenciar usuarios
              </div>
              <p className="text-xs text-slate-500">
                Cadastro, permissoes e status da equipe.
              </p>
            </div>
            <ChevronRight className="h-4 w-4 text-slate-400" />
          </Link>
        </SectionCard>
      )}
    </div>
  );
}
