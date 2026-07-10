import { useMemo } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import {
  Check,
  ChevronRight,
  Database,
  Gauge,
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
import IntegrationHealthPanel from "../components/IntegrationHealthPanel";
import { PageHeader, SectionCard, cn } from "../components/UI";
import { THEME_LABELS, useThemeStore, type ThemeMode } from "../stores/theme";
import {
  usePreferencesStore,
  type HomeRoute,
} from "../stores/preferences";
import { useAuth } from "../stores/auth";
import {
  canRoleAccessPath,
  getModuleCatalog,
  type ModuleStatus,
} from "../config/moduleRegistry";

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
  | "seguranca"
  | "modulos"
  | "integracoes"
  | "administracao";

const STATUS_LABEL: Record<ModuleStatus, string> = {
  active: "Ativo",
  beta: "Beta",
  legacy: "Legado",
  hidden: "Interno",
};

const STATUS_CLASS: Record<ModuleStatus, string> = {
  active: "badge-success",
  beta: "badge-warn",
  legacy: "badge-neutral",
  hidden: "badge-neutral",
};

export default function Configuracoes() {
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const { theme, setTheme } = useThemeStore();
  const { homeRoute, setHomeRoute, sidebarCollapsed, setSidebarCollapsed } =
    usePreferencesStore();
  const user = useAuth((state) => state.user);
  const isAdmin = user?.role === "superadmin" || user?.role === "admin";
  const isAdministrationPath = location.pathname.startsWith("/administracao/");

  const tabs = useMemo(
    () => [
      { key: "pessoal" as const, label: "Pessoal", icon: SlidersHorizontal },
      { key: "navegacao" as const, label: "Navegação", icon: Menu },
      { key: "seguranca" as const, label: "Segurança", icon: ShieldCheck },
      ...(isAdmin
        ? [
            { key: "modulos" as const, label: "Módulos", icon: Route },
            {
              key: "integracoes" as const,
              label: "Integrações",
              icon: Network,
            },
            {
              key: "administracao" as const,
              label: "Administração",
              icon: Settings,
            },
          ]
        : []),
    ],
    [isAdmin],
  );

  const requested = searchParams.get("tab") as SettingsTab | null;
  const defaultTab: SettingsTab = isAdministrationPath
    ? "administracao"
    : "pessoal";
  const tab = tabs.some((item) => item.key === requested)
    ? (requested as SettingsTab)
    : defaultTab;

  const selectTab = (next: SettingsTab) => {
    const params = new URLSearchParams(searchParams);
    params.set("tab", next);
    setSearchParams(params, { replace: true });
  };

  const availableHomeOptions = HOME_OPTIONS.filter((option) =>
    canRoleAccessPath(user?.role, option.route),
  );

  const modules = getModuleCatalog();

  return (
    <div className="max-w-6xl space-y-5">
      <PageHeader
        eyebrow={isAdministrationPath ? "Administração" : "Preferências"}
        title={isAdministrationPath ? "Administração do EJC" : "Configurações"}
        subtitle={
          isAdministrationPath
            ? "Governança dos módulos e acesso aos painéis institucionais, sem exposição de segredos operacionais."
            : "Aparência, navegação e segurança da sua conta."
        }
      />

      <div className="overflow-x-auto">
        <div className="flex w-fit gap-1 rounded-xl border border-slate-200 bg-white/80 p-1 shadow-sm">
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
            title="Conta"
            subtitle="Dados atuais da sessão validados pelo backend."
          >
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="text-xs text-slate-400">Usuário</div>
                <div className="mt-1 text-sm font-semibold text-slate-800">
                  {user?.full_name || "—"}
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <div className="text-xs text-slate-400">E-mail</div>
                <div className="mt-1 truncate text-sm font-semibold text-slate-800">
                  {user?.email || "—"}
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 bg-white p-4">
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
                        : "border-slate-200 bg-white hover:bg-slate-50",
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
              className="flex w-full items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-left hover:bg-slate-50"
            >
              <Menu className="h-5 w-5 text-primary-600" />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-800">
                  Iniciar com menu {sidebarCollapsed ? "recolhido" : "expandido"}
                </div>
                <div className="text-xs text-slate-500">
                  O menu pode ser alterado a qualquer momento pelo botão lateral.
                </div>
              </div>
              <span className="badge badge-neutral">
                {sidebarCollapsed ? "Recolhido" : "Expandido"}
              </span>
            </button>
          </SectionCard>
        </div>
      )}

      {tab === "seguranca" && <AccountSecurity />}

      {tab === "modulos" && isAdmin && (
        <SectionCard
          title="Inventário de módulos e rotas"
          subtitle="Manifesto central usado pelo roteamento, menu e ajuda contextual. Alterações institucionais devem passar por código, revisão e auditoria."
        >
          <div className="overflow-x-auto">
            <table className="table w-full text-sm">
              <thead>
                <tr>
                  <th className="text-left">Módulo</th>
                  <th className="text-left">Grupo</th>
                  <th className="text-left">Rota</th>
                  <th className="text-left">Status</th>
                  <th className="text-left">Risco</th>
                </tr>
              </thead>
              <tbody>
                {modules.map((module) => {
                  const status = module.status ?? "active";
                  return (
                    <tr key={module.key}>
                      <td>
                        <div className="font-medium text-slate-800">
                          {module.label}
                        </div>
                        <div className="text-xs text-slate-400">
                          {module.key}
                        </div>
                      </td>
                      <td>{module.group}</td>
                      <td className="font-mono text-xs">{module.path}</td>
                      <td>
                        <span className={`badge ${STATUS_CLASS[status]}`}>
                          {STATUS_LABEL[status]}
                        </span>
                      </td>
                      <td className="text-xs text-slate-500">
                        {module.sensitive ? "dados sensíveis" : "sem sensíveis"}
                        {module.usesAI ? " · usa IA" : ""}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </SectionCard>
      )}

      {tab === "integracoes" && isAdmin && <IntegrationHealthPanel />}

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
                <div className="mt-1 text-sm text-slate-500">
                  {description}
                </div>
              </div>
              <ChevronRight className="h-4 w-4 text-slate-400" />
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
