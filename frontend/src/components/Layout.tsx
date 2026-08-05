import { useEffect, useMemo, useRef, useState } from "react";
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
  Eye,
  EyeOff,
  LogOut,
  Menu,
  Monitor,
  Moon,
  Pencil,
  Plus,
  ScanSearch,
  Search,
  ShieldCheck,
  Sun,
  X,
} from "lucide-react";
import CaseContextBar from "./CaseContextBar";
import CommandPalette from "./CommandPalette";
import HelpButton from "./HelpButton";
import IaStatusBanner from "./IaStatusBanner";
import { useIaStatus } from "../lib/iaStatus";
import { ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import OnboardingTour from "./OnboardingTour";
import ModuleLifecycleGate from "./ModuleLifecycleGate";
import { useModuleLifecycleStore } from "../stores/moduleLifecycle";
import { filterModulesByLifecycle } from "../lib/moduleLifecycle";
import SecurityMenu from "./SecurityMenu";
import ErrorBoundary from "./ErrorBoundary";
import UserAvatar from "./UserAvatar";
import SidebarWeek from "./SidebarWeek";
import OfficeClock from "./header/OfficeClock";
import DailyMessage from "./header/DailyMessage";
import OfficeLinks from "./header/OfficeLinks";
import { Tooltip, cn } from "./UI";
import { THEME_LABELS, useThemeStore } from "../stores/theme";
import { useAuth } from "../stores/auth";
import { usePreferencesStore } from "../stores/preferences";
import {
  ROLES,
  getHelpModuleKey,
  getNavigationModules,
  type ModuleRoute,
} from "../config/moduleRegistry";
import {
  NOVO_CASO_DOCUMENTO_PATH,
  NOVO_CASO_MANUAL_PATH,
} from "../lib/novoCaso";
import api, { logout } from "../lib/api";

const BRAND_LOGO = "/brand/logo-hd.png";

export default function Layout() {
  const { theme, cycleTheme } = useThemeStore();
  const { disponivel: iaDisponivel } = useIaStatus();
  const user = useAuth((state) => state.user);
  const canCreateCase = Boolean(
    user?.role && (ROLES.clientes as readonly string[]).includes(user.role),
  );
  const lifecycleSettings = useModuleLifecycleStore((state) => state.settings);
  const { sidebarCollapsed: collapsed, setSidebarCollapsed } =
    usePreferencesStore();
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
  const [novoCasoOpen, setNovoCasoOpen] = useState(false);
  const novoCasoRef = useRef<HTMLDivElement>(null);
  const [privacyMode, setPrivacyMode] = useState(
    () => localStorage.getItem("ejc_privacy_mode") === "true",
  );
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("ejc_menu_groups") || "{}");
    } catch {
      return {};
    }
  });

  useEffect(() => {
    document.documentElement.classList.toggle("ejc-privacy-mode", privacyMode);
    localStorage.setItem("ejc_privacy_mode", String(privacyMode));
    if (privacyMode) setNotifOpen(false);
    return () => {
      document.documentElement.classList.remove("ejc-privacy-mode");
    };
  }, [privacyMode]);

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
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!novoCasoOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!novoCasoRef.current?.contains(event.target as Node)) {
        setNovoCasoOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setNovoCasoOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [novoCasoOpen]);

  const visible = useMemo(
    () =>
      filterModulesByLifecycle(
        getNavigationModules(user?.role),
        lifecycleSettings,
      ),
    [user?.role, lifecycleSettings],
  );
  const essentials = useMemo(
    () => visible.filter((item) => item.essential),
    [visible],
  );
  const resto = useMemo(
    () => visible.filter((item) => !item.essential),
    [visible],
  );
  const groups = useMemo(() => {
    const map = new Map<string, ModuleRoute[]>();
    for (const item of resto) {
      map.set(item.group, [...(map.get(item.group) || []), item]);
    }
    return Array.from(map.entries());
  }, [resto]);

  const persistGroups = (next: Record<string, boolean>) => {
    try {
      localStorage.setItem("ejc_menu_groups", JSON.stringify(next));
    } catch {
      // A navegação continua mesmo sem persistência local.
    }
  };

  const toggleGroup = (group: string) =>
    setOpenGroups((previous) => {
      const next = { ...previous, [group]: previous[group] === false };
      persistGroups(next);
      return next;
    });

  const MAIS_KEY = "__mais__";
  const maisOpen = openGroups[MAIS_KEY] === true;
  const toggleMais = () =>
    setOpenGroups((previous) => {
      const next = { ...previous, [MAIS_KEY]: previous[MAIS_KEY] !== true };
      persistGroups(next);
      return next;
    });

  const renderNavItem = (item: ModuleRoute) => {
    const { path, label, description, icon: Icon, end } = item;
    const content = (
      <NavLink
        key={path}
        to={path}
        end={end}
        onClick={() => setMenuOpen(false)}
        title={collapsed ? undefined : description}
        className={({ isActive }) =>
          cn(
            "ejc-sidebar-nav-item group flex items-center gap-3 rounded-xl px-3 text-[12px] font-medium transition-all duration-150",
            collapsed ? "h-11 justify-center px-0" : "py-2",
            isActive && "is-active",
          )
        }
      >
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && (
          <span className="min-w-0 flex-1">
            <span className="block truncate leading-tight">{label}</span>
            {description && (
              <span className="mt-0.5 block line-clamp-1 text-[10px] font-normal leading-tight text-slate-500">
                {description}
              </span>
            )}
          </span>
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
  };

  const sidebarWidth = collapsed ? "md:w-[5.25rem]" : "md:w-72";
  const contentMargin = collapsed ? "md:ml-[5.25rem]" : "md:ml-72";
  const headerOffset = collapsed ? "md:left-[5.25rem]" : "md:left-72";

  return (
    <div className="ejc-shell-root">
      {!privacyMode && <CommandPalette />}

      <header
        className={cn(
          "ejc-shell-header fixed inset-x-0 top-0 z-40 transition-all",
          headerOffset,
        )}
      >
        <div className="flex h-full items-center gap-2 px-3 md:gap-3 md:px-5">
          <button
            type="button"
            className="ejc-header-icon-button flex h-10 w-10 items-center justify-center rounded-xl md:hidden"
            onClick={() => setMenuOpen(true)}
            aria-label="Abrir menu"
          >
            <Menu className="h-5 w-5" />
          </button>

          <Link
            to="/"
            className="flex h-11 w-20 shrink-0 items-center justify-center rounded-xl bg-white px-2 md:hidden"
            aria-label="De Paula Teixeira - EJC"
          >
            <img
              src={BRAND_LOGO}
              alt="De Paula Teixeira Sociedade de Advogados"
              className="max-h-9 w-auto object-contain"
            />
          </Link>

          <div className="hidden xl:block">
            <OfficeClock />
          </div>

          <div className="hidden min-w-0 flex-1 2xl:flex 2xl:justify-center">
            <DailyMessage />
          </div>

          <div className="flex min-w-0 flex-1 justify-center px-1 xl:flex-none xl:w-[300px] 2xl:w-[360px]">
            <button
              type="button"
              onClick={() => window.dispatchEvent(new Event("ejc-open-search"))}
              className="ejc-shell-search flex w-full items-center gap-3 px-3 text-left text-xs"
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="hidden truncate sm:inline">
                Buscar processo, parte ou CPF…
              </span>
              <span className="truncate sm:hidden">Buscar…</span>
              <kbd className="ml-auto hidden rounded-md px-1.5 py-0.5 text-[9px] sm:block">
                Ctrl K
              </kbd>
            </button>
          </div>

          <OfficeLinks />

          {canCreateCase && (
            <div ref={novoCasoRef} className="relative hidden md:inline-flex">
              <button
                type="button"
                onClick={() => setNovoCasoOpen((value) => !value)}
                aria-haspopup="menu"
                aria-expanded={novoCasoOpen}
                className="ejc-header-new-case inline-flex h-9 items-center gap-2 rounded-xl px-3 text-[11px] font-bold"
              >
                <Plus className="h-4 w-4" />
                <span className="hidden 2xl:inline">Novo caso</span>
                <ChevronDown className="hidden h-3.5 w-3.5 2xl:block" />
              </button>
              {novoCasoOpen && (
                <div
                  role="menu"
                  aria-label="Como abrir o novo caso"
                  className="card absolute right-0 top-full z-50 mt-2 w-72 py-1 shadow-float animate-pop"
                >
                  <Link
                    to={NOVO_CASO_DOCUMENTO_PATH}
                    role="menuitem"
                    onClick={() => setNovoCasoOpen(false)}
                    className="menu-item items-start"
                  >
                    <ScanSearch className="mt-0.5 h-4 w-4 shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-medium">
                        Analisar documento e preencher
                      </span>
                      <span className="block text-[11px] text-slate-400">
                        A IA extrai os dados para sua conferência
                      </span>
                    </span>
                  </Link>
                  <Link
                    to={NOVO_CASO_MANUAL_PATH}
                    role="menuitem"
                    onClick={() => setNovoCasoOpen(false)}
                    className="menu-item items-start"
                  >
                    <Pencil className="mt-0.5 h-4 w-4 shrink-0" />
                    <span className="min-w-0">
                      <span className="block font-medium">
                        Cadastrar manualmente
                      </span>
                      <span className="block text-[11px] text-slate-400">
                        Preenchimento direto dos campos do caso
                      </span>
                    </span>
                  </Link>
                </div>
              )}
            </div>
          )}

          <div className="hidden lg:block">
            <HelpButton moduleKey={moduleKey} />
          </div>

          <button
            type="button"
            onClick={() => setPrivacyMode((value) => !value)}
            title={
              privacyMode
                ? "Desativar modo privacidade"
                : "Ativar modo privacidade"
            }
            className={cn(
              "ejc-header-icon-button hidden h-9 w-9 items-center justify-center rounded-xl sm:flex",
              privacyMode && "text-amber-200",
            )}
            aria-pressed={privacyMode}
            aria-label={
              privacyMode
                ? "Desativar modo privacidade"
                : "Ativar modo privacidade"
            }
          >
            {privacyMode ? (
              <EyeOff className="h-4 w-4" />
            ) : (
              <Eye className="h-4 w-4" />
            )}
          </button>

          <button
            type="button"
            onClick={cycleTheme}
            title={`Tema: ${THEME_LABELS[theme]}`}
            className="ejc-header-icon-button hidden h-9 w-9 items-center justify-center rounded-xl lg:flex"
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
              onClick={() => !privacyMode && setNotifOpen((value) => !value)}
              className="ejc-header-icon-button relative flex h-9 w-9 items-center justify-center rounded-xl"
              aria-label="Notificações"
            >
              <Bell className="h-4 w-4" />
              {notifCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-danger-600 px-1 text-[9px] font-semibold text-white ring-2 ring-[#0b111b]">
                  {notifCount}
                </span>
              )}
            </button>

            {notifOpen && (
              <div className="absolute right-0 mt-3 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white text-slate-900 shadow-float animate-pop">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <div className="text-sm font-semibold">Notificações</div>
                  <button
                    type="button"
                    className="text-xs font-medium text-primary-700"
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
                        <div className="text-sm font-medium">
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

          <div className="ejc-security-menu-dark hidden sm:block">
            <SecurityMenu user={user} />
          </div>
        </div>
      </header>

      {menuOpen && (
        <button
          type="button"
          className="fixed inset-0 z-[45] bg-slate-950/65 md:hidden"
          aria-label="Fechar menu"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside
        className={cn(
          "ejc-shell-sidebar fixed bottom-0 left-0 top-0 z-50 flex-col transition-all",
          sidebarWidth,
          menuOpen ? "flex w-72 md:flex" : "hidden md:flex",
        )}
      >
        <div
          className={cn(
            "ejc-brand-tile relative flex items-center justify-center px-4",
            collapsed && "mx-2 px-2",
          )}
        >
          <Link
            to="/"
            className="flex min-w-0 flex-1 justify-center"
            aria-label="Ir para o início do EJC"
          >
            <img
              src={BRAND_LOGO}
              alt="De Paula Teixeira Sociedade de Advogados"
              className={cn(
                "w-auto",
                collapsed ? "h-9 max-w-12" : "h-16 max-w-[230px]",
              )}
            />
          </Link>
          <button
            type="button"
            className="absolute right-2 hidden rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 md:block"
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
            className="absolute right-2 rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700 md:hidden"
            onClick={() => setMenuOpen(false)}
            aria-label="Fechar menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="ejc-sidebar-scroll flex-1 overflow-y-auto px-3 py-3">
          {essentials.length > 0 && (
            <div className="mb-4">
              {!collapsed && (
                <div className="ejc-sidebar-section-title mb-2 px-2 text-[9px] font-bold uppercase tracking-[0.22em]">
                  Essencial
                </div>
              )}
              <div
                className={cn(
                  "space-y-1",
                  !collapsed && "ejc-sidebar-tree ml-2 border-l pl-2",
                )}
              >
                {essentials.map((item) => renderNavItem(item))}
              </div>
            </div>
          )}

          {resto.length > 0 &&
            (collapsed ? (
              <div className="space-y-1">
                {resto.map((item) => renderNavItem(item))}
              </div>
            ) : (
              <div className="mb-2">
                <button
                  type="button"
                  onClick={toggleMais}
                  className="ejc-sidebar-advanced-button mb-2 flex w-full items-center justify-between px-2 text-[9px] font-bold uppercase tracking-[0.2em]"
                  aria-expanded={maisOpen}
                  aria-controls="sidebar-mais"
                >
                  <span>Mais / Avançado</span>
                  <ChevronDown
                    className={cn(
                      "h-3 w-3 transition-transform",
                      !maisOpen && "-rotate-90",
                    )}
                  />
                </button>
                {maisOpen && (
                  <div id="sidebar-mais" className="space-y-4">
                    {groups.map(([group, items]) => {
                      const isOpen = openGroups[group] !== false;
                      return (
                        <div key={group}>
                          <button
                            type="button"
                            onClick={() => toggleGroup(group)}
                            className="ejc-sidebar-advanced-button mb-2 flex w-full items-center justify-between px-2 text-[9px] font-bold uppercase tracking-[0.18em]"
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
                          {isOpen && (
                            <div className="ejc-sidebar-tree ml-2 space-y-1 border-l pl-2">
                              {items.map((item) => renderNavItem(item))}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
        </nav>

        <SidebarWeek collapsed={collapsed} />

        <div className="ejc-sidebar-footer border-t p-3">
          {!collapsed && (
            <div className="mb-2 flex items-center gap-2.5 rounded-xl bg-white/[0.04] px-3 py-2.5 ring-1 ring-inset ring-white/[0.06]">
              <ShieldCheck className="h-4 w-4 shrink-0 text-[#e5ce7f]" />
              <div className="min-w-0">
                <div className="truncate text-[10px] font-semibold text-slate-200">
                  Seguro &amp; Conforme
                </div>
                <div className="truncate text-[9px] text-slate-500">
                  Dados protegidos — LGPD
                </div>
              </div>
            </div>
          )}
          <Link
            to="/configuracoes"
            title="Abrir preferências"
            className={cn(
              "ejc-sidebar-user flex items-center gap-3 rounded-xl p-2",
              collapsed && "justify-center",
            )}
          >
            <UserAvatar user={user} size="md" />
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-slate-100">
                  {user?.full_name || "Usuário"}
                </div>
                <div className="truncate text-[10px] capitalize text-slate-500">
                  {user?.role || ""}
                </div>
              </div>
            )}
          </Link>
          <button
            type="button"
            onClick={logout}
            className={cn(
              "mt-2 flex h-10 w-full items-center gap-3 rounded-xl px-3 text-xs font-medium text-slate-400 transition-colors hover:bg-danger-600/15 hover:text-red-300",
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
          "relative z-10 flex min-h-screen flex-col pt-16 transition-all md:pt-[76px]",
          contentMargin,
        )}
      >
        <IaStatusBanner />
        <CaseContextBar />
        <main className="ejc-modern-scope flex-1 px-4 py-5 md:px-6 md:py-6 xl:px-7">
          <div className="mx-auto w-full max-w-[1540px] animate-rise">
            <ErrorBoundary key={location.pathname}>
              <ModuleLifecycleGate>
                <Outlet />
              </ModuleLifecycleGate>
            </ErrorBoundary>
          </div>
        </main>
      </div>

      <OnboardingTour />
      {iaDisponivel ? (
        <Link
          to="/inteligencia?tab=assistente"
          className="fixed bottom-5 right-5 z-30 hidden h-12 w-12 items-center justify-center rounded-2xl bg-ai-600 text-white shadow-float transition-all duration-150 hover:-translate-y-0.5 hover:bg-ai-700 md:flex"
          aria-label="Assistente IA"
        >
          <Bot className="h-5 w-5" />
        </Link>
      ) : (
        <button
          type="button"
          disabled
          title={ROTULO_IA_NAO_ATIVADA}
          aria-label={`Assistente IA — ${ROTULO_IA_NAO_ATIVADA}`}
          className="fixed bottom-5 right-5 z-30 hidden h-12 w-12 cursor-not-allowed items-center justify-center rounded-2xl bg-slate-300 text-white shadow-md md:flex dark:bg-slate-700"
        >
          <Bot className="h-5 w-5" />
        </button>
      )}
    </div>
  );
}
