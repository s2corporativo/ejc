import { useEffect, useMemo, useState } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  Bell,
  Bot,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Plus,
  Search,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import CaseContextBar from "./CaseContextBar";
import CommandPalette from "./CommandPalette";
import ErrorBoundary from "./ErrorBoundary";
import HelpButton from "./HelpButton";
import ModuleLifecycleGate from "./ModuleLifecycleGate";
import OnboardingTour from "./OnboardingTour";
import SecurityMenu from "./SecurityMenu";
import UserAvatar from "./UserAvatar";
import { Tooltip, cn } from "./UI";
import {
  getHelpModuleKey,
  getNavigationModules,
  type ModuleRoute,
} from "../config/moduleRegistry";
import { filterModulesByLifecycle } from "../lib/moduleLifecycle";
import api, { logout } from "../lib/api";
import { useAuth } from "../stores/auth";
import { useModuleLifecycleStore } from "../stores/moduleLifecycle";
import { usePreferencesStore } from "../stores/preferences";
import { THEME_LABELS, useThemeStore } from "../stores/theme";
import "../styles/option-one.css";

const BRAND_LOGO = "/brand/logo-hd.png";

const MACRO_GROUP_ORDER = [
  "Início",
  "Operação Jurídica",
  "Clientes e Relacionamento",
  "Conhecimento e Inteligência",
  "Gestão do Escritório",
  "Governança e Segurança",
  "Configurações",
] as const;

const CLIENT_KEYS = new Set([
  "clientes",
  "cliente-detalhe",
  "crm",
  "portal-clientes",
  "mensagens",
]);

const KNOWLEDGE_KEYS = new Set([
  "ramos",
  "ramo-detalhe",
  "inteligencia",
  "governanca-ia",
  "knowledge-hub",
  "biblioteca",
  "memoria-institucional",
  "wiki",
  "datajud",
  "diario-oficial",
  "radar-regulatorio",
  "radar-compliance",
  "noticias",
  "prompts",
]);

const GOVERNANCE_KEYS = new Set([
  "auditoria",
  "mapa-modulos",
  "usuarios",
  "lixeira",
  "central-diagnostico",
]);

const OPERATION_KEYS = new Set([
  "caso-novo",
  "casos",
  "caso-detalhe",
  "caso-jornada",
  "caso-entrevista",
  "sala-de-guerra",
  "raio-x-processo",
  "prazos",
  "suspensoes",
  "tarefas",
  "intimacoes",
  "atividades",
  "documentos",
  "pecas",
  "checklists",
  "workflow",
  "assinaturas",
]);

type NotificationItem = {
  id: string;
  titulo?: string;
  mensagem?: string;
  link?: string;
  lida?: boolean;
};

function macroGroup(module: ModuleRoute) {
  if (module.key === "dashboard") return "Início";
  if (module.key === "configuracoes" || module.key === "ajuda") {
    return "Configurações";
  }
  if (CLIENT_KEYS.has(module.key)) return "Clientes e Relacionamento";
  if (KNOWLEDGE_KEYS.has(module.key)) return "Conhecimento e Inteligência";
  if (GOVERNANCE_KEYS.has(module.key)) return "Governança e Segurança";
  if (OPERATION_KEYS.has(module.key)) return "Operação Jurídica";
  if (module.group === "Inteligência Jurídica") {
    return "Conhecimento e Inteligência";
  }
  if (module.group === "Administração") return "Governança e Segurança";
  if (module.group === "Principal" || module.group === "Produção") {
    return "Operação Jurídica";
  }
  return "Gestão do Escritório";
}

export default function LayoutOptionOne() {
  const { theme, cycleTheme } = useThemeStore();
  const user = useAuth((state) => state.user);
  const lifecycleSettings = useModuleLifecycleStore(
    (state) => state.settings,
  );
  const {
    sidebarCollapsed: collapsed,
    setSidebarCollapsed,
  } = usePreferencesStore();
  const location = useLocation();
  const navigate = useNavigate();
  const moduleKey = useMemo(
    () => getHelpModuleKey(location.pathname),
    [location.pathname],
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [notificationOpen, setNotificationOpen] = useState(false);
  const [notificationCount, setNotificationCount] = useState(0);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [privacyMode, setPrivacyMode] = useState(() => {
    try {
      return localStorage.getItem("ejc_privacy_mode") === "true";
    } catch {
      return false;
    }
  });
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("ejc_option_one_groups") || "{}");
    } catch {
      return {};
    }
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("ejc-privacy-mode", privacyMode);
    try {
      localStorage.setItem("ejc_privacy_mode", String(privacyMode));
    } catch {
      // Preferência visual não deve impedir o uso do sistema.
    }
    return () => root.classList.remove("ejc-privacy-mode");
  }, [privacyMode]);

  useEffect(() => {
    const loadNotifications = () => {
      void api
        .get("/notifications/?apenas_nao_lidas=false&limit=15")
        .then((response) => {
          setNotifications(response.data.data ?? []);
          setNotificationCount(response.data.nao_lidas ?? 0);
        })
        .catch(() => {
          // Notificações são auxiliares; falha silenciosa preserva a operação.
        });
    };

    loadNotifications();
    const timer = window.setInterval(loadNotifications, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const visibleModules = useMemo(
    () =>
      filterModulesByLifecycle(
        getNavigationModules(user?.role),
        lifecycleSettings,
      ),
    [lifecycleSettings, user?.role],
  );

  const groups = useMemo(() => {
    const grouped = new Map<string, ModuleRoute[]>();
    for (const item of visibleModules) {
      const group = macroGroup(item);
      grouped.set(group, [...(grouped.get(group) ?? []), item]);
    }
    return MACRO_GROUP_ORDER.map((group) => [
      group,
      grouped.get(group) ?? [],
    ] as const).filter(([, items]) => items.length > 0);
  }, [visibleModules]);

  const toggleGroup = (group: string) => {
    setOpenGroups((current) => {
      const next = { ...current, [group]: current[group] === false };
      try {
        localStorage.setItem("ejc_option_one_groups", JSON.stringify(next));
      } catch {
        // Preferência visual não deve interromper a navegação.
      }
      return next;
    });
  };

  const sidebarWidth = collapsed ? "md:w-[5.25rem]" : "md:w-64";
  const desktopOffset = collapsed ? "md:left-[5.25rem]" : "md:left-64";
  const contentMargin = collapsed ? "md:ml-[5.25rem]" : "md:ml-64";

  return (
    <div className="ejc-option-one-shell min-h-screen bg-canvas text-slate-900">
      <CommandPalette />

      <header
        className={cn(
          "ejc-option-one-topbar fixed inset-x-0 top-0 z-40 border-b border-slate-200/80 bg-white/95 backdrop-blur-xl transition-all",
          desktopOffset,
        )}
      >
        <div className="flex h-16 items-center gap-2 px-3 md:px-5">
          <button
            type="button"
            className="ejc-option-one-icon-button md:hidden"
            onClick={() => setMenuOpen(true)}
            aria-label="Abrir menu"
          >
            <Menu className="h-5 w-5" />
          </button>

          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event("ejc-open-search"))}
            className="ejc-option-one-search flex min-w-0 flex-1 items-center gap-3 px-4 text-left"
            aria-label="Abrir busca global"
          >
            <Search className="h-4 w-4 shrink-0" />
            <span className="hidden truncate sm:inline">
              Buscar clientes, processos, documentos, tarefas, teses e jurisprudência…
            </span>
            <span className="truncate sm:hidden">Buscar no EJC…</span>
            <kbd className="ml-auto hidden rounded-md bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400 lg:block">
              Ctrl K
            </kbd>
          </button>

          <button
            type="button"
            onClick={() => window.dispatchEvent(new Event("ejc-open-search"))}
            className="ejc-option-one-command hidden lg:inline-flex"
          >
            <Search className="h-4 w-4" />
            Comando rápido
          </button>

          <Link to="/casos/novo" className="ejc-option-one-new-button">
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">Novo</span>
          </Link>

          <Link
            to="/atividades"
            className="ejc-option-one-icon-button hidden sm:inline-flex"
            aria-label="Abrir agenda"
            title="Agenda e prazos"
          >
            <span className="text-[11px] font-bold">HOJE</span>
          </Link>

          <HelpButton moduleKey={moduleKey} />

          <button
            type="button"
            onClick={cycleTheme}
            title={`Tema: ${THEME_LABELS[theme]} — clique para alternar`}
            className="ejc-option-one-icon-button hidden sm:inline-flex"
            aria-label={`Alternar tema. Tema atual: ${THEME_LABELS[theme]}`}
          >
            {theme === "light" ? (
              <Sun className="h-4 w-4" />
            ) : theme === "dark" ? (
              <Moon className="h-4 w-4" />
            ) : (
              <Monitor className="h-4 w-4" />
            )}
          </button>

          <div className="relative">
            <button
              type="button"
              onClick={() => setNotificationOpen((current) => !current)}
              className="ejc-option-one-icon-button relative"
              aria-label="Notificações"
              aria-expanded={notificationOpen}
            >
              <Bell className="h-4 w-4" />
              {notificationCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-primary-950 px-1 text-[10px] font-semibold text-white ring-2 ring-white">
                  {notificationCount}
                </span>
              )}
            </button>

            {notificationOpen && (
              <div className="absolute right-0 mt-2 w-80 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <div className="text-sm font-semibold text-slate-950">
                    Notificações
                  </div>
                  <button
                    type="button"
                    className="text-xs font-semibold text-primary-700 hover:text-primary-950"
                    onClick={() => {
                      void api
                        .post("/notifications/ler-todas")
                        .then(() => setNotificationCount(0));
                    }}
                  >
                    Marcar lidas
                  </button>
                </div>
                <div className="max-h-96 overflow-y-auto">
                  {notifications.length === 0 ? (
                    <div className="px-4 py-8 text-center text-sm text-slate-400">
                      Sem notificações
                    </div>
                  ) : (
                    notifications.map((notification) => (
                      <button
                        key={notification.id}
                        type="button"
                        onClick={() => {
                          if (notification.link) navigate(notification.link);
                          setNotificationOpen(false);
                        }}
                        className={cn(
                          "w-full border-b border-slate-100 px-4 py-3 text-left transition hover:bg-slate-50",
                          !notification.lida && "bg-primary-50/50",
                        )}
                      >
                        <div className="text-sm font-semibold text-slate-900">
                          {notification.titulo}
                        </div>
                        <div className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500">
                          {notification.mensagem}
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          <SecurityMenu user={user} />
        </div>
      </header>

      {menuOpen && (
        <button
          type="button"
          className="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-sm md:hidden"
          aria-label="Fechar menu"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside
        className={cn(
          "ejc-option-one-sidebar fixed inset-y-0 left-0 z-50 flex-col border-r border-slate-200 bg-white transition-all",
          sidebarWidth,
          menuOpen ? "flex w-72 md:flex" : "hidden md:flex",
        )}
      >
        <div className="flex h-20 items-center gap-2 border-b border-slate-100 px-4">
          {!collapsed && (
            <Link to="/" className="min-w-0 flex-1" aria-label="EJC — Início">
              <img
                src={BRAND_LOGO}
                alt="EJC — Escritório Jurídico Clovis"
                className="h-14 w-auto max-w-full object-contain object-left"
              />
            </Link>
          )}
          {collapsed && (
            <Link
              to="/"
              className="flex h-10 w-10 items-center justify-center rounded-xl border border-amber-200 bg-amber-50 font-serif text-lg font-semibold text-amber-700"
              aria-label="EJC — Início"
            >
              EJC
            </Link>
          )}
          <button
            type="button"
            className="ejc-option-one-icon-button hidden md:inline-flex"
            onClick={() => setSidebarCollapsed(!collapsed)}
            aria-label={collapsed ? "Expandir menu" : "Recolher menu"}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" />
            ) : (
              <ChevronLeft className="h-4 w-4" />
            )}
          </button>
          <button
            type="button"
            className="ejc-option-one-icon-button md:hidden"
            onClick={() => setMenuOpen(false)}
            aria-label="Fechar menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {groups.map(([group, items]) => {
            const isOpen = openGroups[group] !== false;
            return (
              <div key={group} className="mb-2">
                {!collapsed && group !== "Início" && (
                  <button
                    type="button"
                    onClick={() => toggleGroup(group)}
                    className="ejc-option-one-group-label flex w-full items-center justify-between px-3 py-2"
                    aria-expanded={isOpen}
                  >
                    <span>{group}</span>
                    <ChevronDown
                      className={cn(
                        "h-3.5 w-3.5 transition-transform",
                        !isOpen && "-rotate-90",
                      )}
                    />
                  </button>
                )}

                {(collapsed || group === "Início" || isOpen) && (
                  <div className="space-y-1">
                    {items.map(({ path, label, icon: Icon, end }) => {
                      const item = (
                        <NavLink
                          key={path}
                          to={path}
                          end={end}
                          onClick={() => setMenuOpen(false)}
                          className={({ isActive }) =>
                            cn(
                              "ejc-option-one-nav-item flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium",
                              collapsed && "justify-center px-0",
                              isActive && "is-active",
                            )
                          }
                        >
                          <Icon className="h-4 w-4 shrink-0" />
                          {!collapsed && <span className="truncate">{label}</span>}
                        </NavLink>
                      );

                      return collapsed ? (
                        <Tooltip key={path} label={label}>
                          {item}
                        </Tooltip>
                      ) : (
                        item
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-slate-100 p-3">
          {!collapsed && (
            <button
              type="button"
              onClick={() => setPrivacyMode((current) => !current)}
              className="mb-2 flex w-full items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-left"
              aria-pressed={privacyMode}
            >
              <span>
                <span className="block text-xs font-semibold text-slate-800">
                  Modo privacidade
                </span>
                <span className="block text-[10px] text-slate-500">
                  Oculta o conteúdo central
                </span>
              </span>
              <span
                className={cn(
                  "relative h-5 w-9 rounded-full transition",
                  privacyMode ? "bg-amber-500" : "bg-slate-300",
                )}
              >
                <span
                  className={cn(
                    "absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition",
                    privacyMode ? "left-[18px]" : "left-0.5",
                  )}
                />
              </span>
            </button>
          )}

          {!collapsed && (
            <div className="mb-2 flex items-center gap-2.5 rounded-xl bg-emerald-50 px-3 py-2.5 text-emerald-800">
              <ShieldCheck className="h-4 w-4 shrink-0" />
              <div className="min-w-0">
                <div className="truncate text-[11px] font-semibold">
                  Seguro e rastreável
                </div>
                <div className="truncate text-[10px] text-emerald-700/75">
                  Auditoria e LGPD preservadas
                </div>
              </div>
            </div>
          )}

          <div
            className={cn(
              "flex items-center gap-3 rounded-xl px-2 py-2",
              collapsed && "justify-center",
            )}
          >
            <UserAvatar user={user} size="md" />
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-slate-900">
                  {user?.full_name || "Usuário"}
                </div>
                <div className="truncate text-[11px] capitalize text-slate-500">
                  {user?.role || ""}
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            onClick={logout}
            className={cn(
              "mt-1 flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-slate-500 transition hover:bg-red-50 hover:text-red-700",
              collapsed && "justify-center px-0",
            )}
            aria-label="Sair"
          >
            <LogOut className="h-4 w-4 shrink-0" />
            {!collapsed && <span>Sair</span>}
          </button>
        </div>
      </aside>

      <div
        className={cn(
          "relative z-10 flex min-h-screen flex-col pt-16 transition-all",
          contentMargin,
        )}
      >
        <CaseContextBar />
        <main className="ejc-option-one-main flex-1 px-4 py-5 md:px-7 md:py-7">
          <div className="mx-auto w-full max-w-[1520px] animate-rise">
            <ErrorBoundary key={location.pathname}>
              <ModuleLifecycleGate>
                <Outlet />
              </ModuleLifecycleGate>
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <OnboardingTour />
      <Link
        to="/inteligencia?tab=assistente"
        className="ejc-option-one-ai-button fixed bottom-5 right-5 z-30 hidden h-12 w-12 items-center justify-center rounded-2xl text-white md:flex"
        aria-label="Abrir assistente de inteligência jurídica"
      >
        <Bot className="h-5 w-5" />
      </Link>
    </div>
  );
}
