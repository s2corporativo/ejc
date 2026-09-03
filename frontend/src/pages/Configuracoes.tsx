import { useMemo } from "react";
import { Link, useSearchParams } from "react-router";
import {
  Activity,
  Bell,
  Check,
  ChevronRight,
  Gauge,
  KeyRound,
  LayoutDashboard,
  Menu,
  Monitor,
  Moon,
  Network,
  Route,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  Users,
} from "lucide-react";
import AccountSecurity from "../components/AccountSecurity";
import CredentialVaultPanel from "../components/CredentialVaultPanel";
import IntegrationHealthPanel from "../components/IntegrationHealthPanel";
import ModuleLifecycleSettings from "../components/ModuleLifecycleSettings";
import NotificationPreferences from "../components/NotificationPreferences";
import { PageHeader, SectionCard, cn } from "../components/UI";
import { THEME_LABELS, useThemeStore, type ThemeMode } from "../stores/theme";
import { usePreferencesStore, type HomeRoute } from "../stores/preferences";
import { useAuth } from "../stores/auth";
import { canRoleAccessPath } from "../config/moduleRegistry";

const THEME_OPTIONS: { mode: ThemeMode; icon: typeof Sun }[] = [
  { mode: "light", icon: Sun },
  { mode: "dark", icon: Moon },
  { mode: "system", icon: Monitor },
];

const HOME_OPTIONS: Array<{
  route: HomeRoute;
  label: string;
  description: string;
}> = [
  { route: "/", label: "Dashboard", description: "Visão executiva geral" },
  {
    route: "/atividades",
    label: "Agenda e Atividades",
    description: "Prazos, tarefas e compromissos",
  },
  { route: "/casos", label: "Casos", description: "Carteira jurídica" },
  {
    route: "/clientes",
    label: "Clientes",
    description: "Cadastro e relacionamento",
  },
  {
    route: "/inteligencia",
    label: "Inteligência Jurídica",
    description: "Agentes e análise",
  },
  {
    route: "/financeiro",
    label: "Financeiro",
    description: "Honorários, despesas e sociedade",
  },
];

type SettingsTab =
  | "pessoal"
  | "navegacao"
  | "notificacoes"
  | "seguranca"
  | "modulos"
  | "integracoes"
  | "credenciais"
  | "administracao";

export default function Configuracoes() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { theme, setTheme } = useThemeStore();
  const { homeRoute, setHomeRoute, sidebarCollapsed, setSidebarCollapsed } =
    usePreferencesStore();
  const user = useAuth((state) => state.user);
  const isSuperadmin = user?.role === "superadmin";
  const isAdmin = isSuperadmin || user?.role === "admin";

  const tabs = useMemo(
    () => [
      { key: "pessoal" as const, label: "Pessoal", icon: SlidersHorizontal },
      { key: "navegacao" as const, label: "Navegação", icon: Menu },
      { key: "notificacoes" as const, label: "Notificações", icon: Bell },
      { key: "seguranca" as const, label: "Segurança", icon: ShieldCheck },
      ...(isAdmin
        ? [
            { key: "modulos" as const, label: "Módulos", icon: Route },
            {
              key: "integracoes" as const,
              label: "Integrações",
              icon: Network,
            },
          ]
        : []),
      // Cofre de Credenciais: SÓ superadmin (piso do backend é nível 9).
      ...(isSuperadmin
        ? [
            {
              key: "credenciais" as const,
              label: "Credenciais",
              icon: KeyRound,
            },
          ]
        : []),
      ...(isAdmin
        ? [
            {
              key: "administracao" as const,
              label: "Administração",
              icon: Settings,
            },
          ]
        : []),
    ],
    [isAdmin, isSuperadmin],
  );

  const requested = searchParams.get("tab") as SettingsTab | null;
  const tab = tabs.some((item) => item.key === requested)
    ? (requested as SettingsTab)
    : "pessoal";
  const isAdministrationPath = tab === "administracao";

  const selectTab = (next: SettingsTab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  const availableHomeOptions = HOME_OPTIONS.filter((option) =>
    canRoleAccessPath(user?.role, option.route),
  );

  return (
    <div className="max-w-6xl space-y-5">
      <PageHeader
        eyebrow={isAdministrationPath ? "Administração" : "Preferências"}
        title={isAdministrationPath ? "Administração do EJC" : "Configurações"}
        subtitle={
          isAdministrationPath
            ? "Governança dos módulos e acesso aos painéis institucionais, sem exposição de segredos operacionais."
            : "Aparência, navegação, notificações e segurança da sua conta."
        }
      />

      <div className="overflow-x-auto">
        <div className="flex w-fit gap-1 rounded-xl bg-slate-900/[0.05] p-1 dark:bg-white/[0.07]">
          {tabs.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => selectTab(key)}
              className={cn(
                "flex h-9 items-center gap-1.5 whitespace-nowrap rounded-lg px-4 text-sm font-medium transition-all",
                tab === key
                  ? "bg-primary-600 text-white shadow-sm"
                  : "text-slate-500 hover:bg-slate-100 hover:text-slate-800",
              )}
            >
              <Icon className="h-4 w-4" /> {label}
            </button>
          ))}
        </div>
      </div>

      {tab === "pessoal" && (
        <div className="space-y-5">
          <SectionCard
            title="Aparência"
            subtitle="O modo Sistema acompanha a preferência do seu dispositivo."
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
                        : "border-transparent bg-slate-900/[0.05] hover:bg-slate-900/[0.09] dark:bg-white/[0.07]",
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
            title="Conta"
            subtitle="Dados atuais da sessão validados pelo backend."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="card p-4">
                <div className="text-xs text-slate-400">Usuário</div>
                <div className="mt-1 text-sm font-semibold text-slate-800">
                  {user?.full_name || "—"}
                </div>
              </div>
              <div className="card p-4">
                <div className="text-xs text-slate-400">E-mail</div>
                <div className="mt-1 truncate text-sm font-semibold text-slate-800">
                  {user?.email || "—"}
                </div>
              </div>
              <div className="card p-4">
                <div className="text-xs text-slate-400">Perfil</div>
                <div className="mt-1 text-sm font-semibold capitalize text-slate-800">
                  {user?.role || "—"}
                </div>
              </div>
            </div>
          </SectionCard>
        </div>
      )}

      {tab === "navegacao" && (
        <div className="space-y-5">
          <SectionCard
            title="Página inicial"
            subtitle="Tela aberta após o login. A opção financeira só aparece para perfis autorizados."
          >
            <div className="grid gap-3 md:grid-cols-2">
              {availableHomeOptions.map((option) => {
                const active = homeRoute === option.route;
                return (
                  <button
                    key={option.route}
                    type="button"
                    onClick={() => setHomeRoute(option.route)}
                    className={cn(
                      "flex items-center gap-3 rounded-xl border p-4 text-left",
                      active
                        ? "border-primary-500 bg-primary-50"
                        : "border-transparent bg-slate-900/[0.05] hover:bg-slate-900/[0.09] dark:bg-white/[0.07]",
                    )}
                  >
                    <LayoutDashboard className="h-5 w-5 text-primary-600" />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-semibold text-slate-800">
                        {option.label}
                      </div>
                      <div className="text-xs text-slate-500">
                        {option.description}
                      </div>
                    </div>
                    {active && <Check className="h-4 w-4 text-primary-600" />}
                  </button>
                );
              })}
            </div>
          </SectionCard>

          <SectionCard
            title="Menu lateral"
            subtitle="A preferência é persistida no navegador e aplicada imediatamente."
          >
            <button
              type="button"
              onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
              className="flex w-full items-center gap-3 rounded-xl bg-slate-900/[0.05] p-4 text-left hover:bg-slate-900/[0.09] dark:bg-white/[0.07]"
            >
              <Menu className="h-5 w-5 text-primary-600" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-800">
                  Iniciar com menu{" "}
                  {sidebarCollapsed ? "recolhido" : "expandido"}
                </div>
                <div className="text-xs text-slate-500">
                  O menu pode ser alterado a qualquer momento pelo botão
                  lateral.
                </div>
              </div>
              <span className="badge badge-neutral">
                {sidebarCollapsed ? "Recolhido" : "Expandido"}
              </span>
            </button>
          </SectionCard>
        </div>
      )}

      {tab === "notificacoes" && <NotificationPreferences />}

      {tab === "seguranca" && <AccountSecurity />}

      {tab === "modulos" && isAdmin && <ModuleLifecycleSettings />}

      {tab === "integracoes" && isAdmin && <IntegrationHealthPanel />}

      {tab === "credenciais" && isSuperadmin && <CredentialVaultPanel />}

      {tab === "administracao" && isAdmin && (
        <div className="grid gap-4 md:grid-cols-2">
          {[
            {
              title: "Usuários e acessos",
              description: "Cadastro, perfis e status da equipe.",
              to: "/usuarios",
              icon: Users,
            },
            {
              title: "Mapa de módulos",
              description: "Inventário técnico e funcional do EJC.",
              to: "/mapa-modulos",
              icon: Route,
            },
            {
              title: "Governança da IA",
              description: "Curadoria RAG, prompts sistêmicos e guardrails.",
              to: "/ia-governanca",
              icon: Gauge,
            },
            {
              title: "Auditoria",
              description: "Trilha das operações críticas do sistema.",
              to: "/auditoria",
              icon: ShieldCheck,
            },
            {
              // Bloco 4 do plano de lançamento: a Central de Diagnóstico saiu
              // do menu lateral e passa a ser alcançada por aqui — é tarefa de
              // administração, não estação de trabalho do advogado.
              title: "Central de diagnóstico",
              description: "Banco, migrations, IA, integrações e jobs num lugar só.",
              to: "/diagnostico",
              icon: Activity,
            },
          ].map(({ title, description, to, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              className="card flex items-start gap-3 p-5 hover:border-primary-300"
            >
              <span className="rounded-xl bg-primary-50 p-3 text-primary-600">
                <Icon className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="font-semibold text-slate-800">{title}</div>
                <div className="mt-1 text-sm text-slate-500">{description}</div>
              </div>
              <ChevronRight className="h-4 w-4 text-slate-400" />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
