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
import HelpButton from "./HelpButton";
import OnboardingTour from "./OnboardingTour";
import ModuleLifecycleGate from "./ModuleLifecycleGate";
import { useModuleLifecycleStore } from "../stores/moduleLifecycle";
import { filterModulesByLifecycle } from "../lib/moduleLifecycle";
import SecurityMenu from "./SecurityMenu";
import ErrorBoundary from "./ErrorBoundary";
import UserAvatar from "./UserAvatar";
import { Button, Tooltip, cn } from "./UI";
import { THEME_LABELS, useThemeStore } from "../stores/theme";
import { useAuth } from "../stores/auth";
import { usePreferencesStore } from "../stores/preferences";
import {
  getHelpModuleKey,
  getNavigationModules,
  type ModuleRoute,
} from "../config/moduleRegistry";
import api, { logout } from "../lib/api";

// Logomarca HD com fundo transparente (nunca a versão JPG com fundo)
const BRAND_LOGO = "/brand/logo-hd.png";

export default function Layout() {
  const { theme, cycleTheme } = useThemeStore();
  const user = useAuth((state) => state.user);
  const lifecycleSettings = useModuleLifecycleStore(
    (state) => state.settings,
  );
  const {
    sidebarCollapsed: collapsed,
    setSidebarCollapsed,
  } = usePreferencesStore();
  const nav = useNavigate();
  const location = useLocation();
  const moduleKey = useMemo(
    () => getHelpModuleKey(location.pathname),
    [location.pathname],
  );
  const [notifCount, setNotifCount] = useState(0);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifs, setNotifs] = useState<any[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("ejc_menu_groups") || "{}");
    } catch {
      return {};
    }
  });

  const toggleGroup = (group: string) =>
    setOpenGroups((previous) => {
      const next = { ...previous, [group]: previous[group] === false };
      try {
        localStorage.setItem("ejc_menu_groups", JSON.stringify(next));
      } catch {
        // Preferência de interface não deve interromper a navegação.
      }
      return next;
    });

  useEffect(() => {
    const load = () =>
      api
        .get("/notifications/?apenas_nao_lidas=false&limit=15")
        .then((response) => {
          setNotifs(response.data.data ?? []);
          setNotifCount(response.data.nao_lidas ?? 0);
        })
        .catch(() => {});
    load();
    const timer = setInterval(load, 60_000);
    return () => clearInterval(timer);
  }, []);

  const visible = useMemo(
    () =>
      filterModulesByLifecycle(
        getNavigationModules(user?.role),
        lifecycleSettings,
      ),
    [user?.role, lifecycleSettings],
  );

  const groups = useMemo(() => {
    const map = new Map<string, ModuleRoute[]>();
    for (const item of visible) {
      map.set(item.group, [...(map.get(item.group) || []), item]);
    }
    return Array.from(map.entries());
  }, [visible]);

  const sidebarWidth = collapsed ? "md:w-[5.25rem]" : "md:w-72";
  const contentMargin = collapsed ? "md:ml-[5.25rem]" : "md:ml-72";

  return (
    <div className="min-h-screen bg-canvas text-slate-900">
      <div className="brand-watermark" aria-hidden="true" />
      <CommandPalette />

      <header className="fixed inset-x-0 top-0 z-50 border-b border-slate-200/60 bg-white/90 backdrop-blur-xl">
        <div className="flex h-16 items-center gap-3 px-3 md:px-6">
          <button
            type="button"
            className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 md:hidden"
            onClick={() => setMenuOpen(true)}
            aria-label="Abrir menu"
          >
            <Menu className="h-5 w-5" />
          </button>

          <Link
            to="/"
            className="flex shrink-0 items-center px-1"
            aria-label="De Paula Teixeira - EJC"
          >
            <img
              src={BRAND_LOGO}
              alt="De Paula Teixeira Sociedade de Advogados"
              className="brand-logo-img h-12 w-auto max-w-[240px] md:h-14 md:max-w-[300px]"
            />
          </Link>

          <div className="flex min-w-0 flex-1 justify-center px-1">
            <button
              type="button"
              onClick={() => window.dispatchEvent(new Event("ejc-open-search"))}
              className="flex h-10 w-full max-w-xl items-center gap-3 rounded-full bg-slate-900/[0.04] px-4 text-left text-sm text-slate-500 transition-all duration-150 hover:bg-ouro-palha/70 dark:bg-white/[0.06] dark:text-slate-400 dark:hover:bg-white/[0.09]"
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="hidden truncate sm:inline">
                Buscar processos por parte, CPF ou número…
              </span>
              <span className="truncate sm:hidden">Buscar…</span>
              <kbd className="ml-auto hidden rounded-md bg-white px-1.5 py-0.5 text-[10px] font-medium text-slate-400 shadow-sm sm:block">
                Ctrl K
              </kbd>
            </button>
          </div>

          {/* DECISÃO: o atalho do header abre o wizard guiado de Novo Caso
              (/casos/novo), não mais a listagem de casos. */}
          <Link to="/casos/novo" className="hidden lg:inline-flex">
            <Button size="md" icon={<Plus className="h-4 w-4" />}>
              Novo caso
            </Button>
          </Link>

          <HelpButton moduleKey={moduleKey} />

          <button
            type="button"
            onClick={cycleTheme}
            title={`Tema: ${THEME_LABELS[theme]} — clique para alternar`}
            className="icon-btn hidden sm:flex"
            aria-label={`Alternar tema (atual: ${THEME_LABELS[theme]})`}
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
              onClick={() => setNotifOpen((value) => !value)}
              className="icon-btn relative"
              aria-label="Notificações"
            >
              <Bell className="h-4 w-4" />
              {notifCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-ouro px-1 text-[10px] font-semibold text-white ring-2 ring-white">
                  {notifCount}
                </span>
              )}
            </button>

            {notifOpen && (
              <div className="absolute right-0 mt-2 w-80 overflow-hidden rounded-xl border border-black/[0.05] bg-white shadow-xl">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <div className="text-sm font-semibold text-slate-950">
                    Notificações
                  </div>
                  <button
                    type="button"
                    className="text-xs font-medium text-primary-600 hover:text-primary-700"
                    onClick={() =>
                      api
                        .post("/notifications/ler-todas")
                        .then(() => setNotifCount(0))
                    }
                  >
                    Marcar lidas
                  </button>
                </div>
                <div className="max-h-96 overflow-y-auto">
                  {notifs.length === 0 ? (
                    <div className="px-4 py-8 text-center text-sm text-slate-400">
                      Sem notificações
                    </div>
                  ) : (
                    notifs.map((notification) => (
                      <button
                        key={notification.id}
                        type="button"
                        onClick={() => {
                          if (notification.link) nav(notification.link);
                          setNotifOpen(false);
                        }}
                        className={cn(
                          "w-full border-b border-slate-50 px-4 py-3 text-left hover:bg-primary-50/60",
                          !notification.lida && "bg-primary-50/40",
                        )}
                      >
                        <div className="text-sm font-medium text-slate-900">
                          {notification.titulo}
                        </div>
                        <div className="mt-1 line-clamp-2 text-xs text-slate-500">
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
          className="fixed inset-0 z-30 bg-slate-950/45 backdrop-blur-sm md:hidden"
          aria-label="Fechar menu"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside
        className={cn(
          "sidebar-bronze fixed bottom-0 left-0 top-16 z-40 flex-col transition-all",
          sidebarWidth,
          menuOpen ? "flex w-72 md:flex" : "hidden md:flex",
        )}
      >
        <div
          className={cn(
            "flex items-center gap-2 px-4 pb-3 pt-4",
            collapsed && "justify-center px-2",
          )}
        >
          {!collapsed && (
            <div className="min-w-0 flex-1">
              <div className="truncate text-[11px] font-semibold uppercase tracking-[0.18em] text-[#E5CE7F]">
                De Paula Teixeira
              </div>
              <div className="mt-0.5 truncate text-[10px] text-[rgba(255,245,230,0.5)]">
                Sociedade de Advogados
              </div>
            </div>
          )}
          <button
            type="button"
            className="hidden rounded-lg p-1.5 text-[rgba(255,245,230,0.55)] hover:bg-[rgba(166,124,82,0.2)] hover:text-[#F5EDD2] md:block"
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
            className="rounded-lg p-1.5 text-[rgba(255,245,230,0.55)] hover:bg-[rgba(166,124,82,0.2)] hover:text-[#F5EDD2] md:hidden"
            onClick={() => setMenuOpen(false)}
            aria-label="Fechar menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="brand-accent-line mx-4 h-px" aria-hidden="true" />

        <nav className="flex-1 overflow-y-auto px-3 py-4 scrollbar-thin">
          {groups.map(([group, items]) => {
            const isOpen = openGroups[group] !== false;
            return (
              <div key={group} className="mb-4">
                {!collapsed && (
                  <button
                    type="button"
                    onClick={() => toggleGroup(group)}
                    className="sidebar-group-label mb-2 flex w-full items-center justify-between px-2 text-2xs font-semibold uppercase tracking-[0.2em] transition-colors"
                    aria-expanded={isOpen}
                  >
                    <span>{group}</span>
                    <ChevronDown
                      className={cn(
                        "h-3 w-3 transition-transform",
                        !isOpen && "-rotate-90",
                      )}
                    />
                  </button>
                )}
                {(collapsed || isOpen) && (
                  <div
                    className={cn(
                      "space-y-1",
                      !collapsed && "sidebar-tree ml-3 border-l pl-2",
                    )}
                  >
                    {items.map(({ path, label, icon: Icon, end }) => {
                      const content = (
                        <NavLink
                          key={path}
                          to={path}
                          end={end}
                          onClick={() => setMenuOpen(false)}
                          className={({ isActive }) =>
                            cn(
                              "sidebar-nav-item group flex h-10 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-all duration-150",
                              collapsed && "justify-center px-0",
                              isActive && "is-active",
                            )
                          }
                        >
                          <Icon className="h-4 w-4 shrink-0" />
                          {!collapsed && (
                            <span className="truncate">{label}</span>
                          )}
                        </NavLink>
                      );
                      return collapsed ? (
                        <Tooltip key={path} label={label}>
                          {content}
                        </Tooltip>
                      ) : (
                        content
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        <div className="border-t border-[rgba(255,245,230,0.12)] p-3">
          {!collapsed && (
            <div className="mb-2 flex items-center gap-2.5 rounded-xl bg-[rgba(255,245,230,0.06)] px-3 py-2.5 ring-1 ring-inset ring-[rgba(255,245,230,0.1)]">
              <ShieldCheck className="h-4 w-4 shrink-0 text-[#D4AF37]" />
              <div className="min-w-0">
                <div className="truncate text-[11px] font-semibold text-[#F5EDD2]">
                  Seguro &amp; Conforme
                </div>
                <div className="truncate text-[10px] text-[rgba(255,245,230,0.55)]">
                  Dados protegidos — LGPD
                </div>
              </div>
            </div>
          )}
          <div
            className={cn(
              "flex items-center gap-3 rounded-xl bg-[rgba(255,245,230,0.06)] p-2",
              collapsed && "justify-center",
            )}
          >
            <UserAvatar user={user} size="md" />
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-[#F5EDD2]">
                  {user?.full_name || "Usuário"}
                </div>
                <div className="truncate text-[11px] capitalize text-[rgba(255,245,230,0.55)]">
                  {user?.role || ""}
                </div>
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={logout}
            className={cn(
              "mt-2 flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-[rgba(255,245,230,0.65)] transition-colors hover:bg-danger-600/25 hover:text-[#F8B9BC]",
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
        {/* Modo Caso: faixa fina de contexto do caso ativo (discreta). */}
        <CaseContextBar />
        <main className="ejc-modern-scope flex-1 px-4 py-5 md:px-7 md:py-7">
          <div className="mx-auto w-full max-w-[1440px] animate-rise">
            <ErrorBoundary key={location.pathname}>
              <ModuleLifecycleGate><Outlet /></ModuleLifecycleGate>
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <OnboardingTour />
      <Link
        to="/inteligencia?tab=assistente"
        className="fixed bottom-5 right-5 z-30 hidden h-12 w-12 items-center justify-center rounded-2xl bg-ai-600 text-white shadow-lg shadow-ai-600/25 hover:bg-ai-700 md:flex"
        aria-label="Assistente IA"
      >
        <Bot className="h-5 w-5" />
      </Link>
    </div>
  );
}
