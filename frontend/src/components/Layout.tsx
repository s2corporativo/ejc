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
import { Button, Tooltip, cn } from "./UI";
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

// Logomarca HD com fundo transparente (nunca a versão JPG com fundo)
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
  // Modo privacidade (reuniões/compartilhamento de tela): borra o conteúdo
  // principal sem sair da sessão. Persistido para sobreviver a refresh, mas
  // NUNCA nasce ligado sem escolha explícita do usuário.
  const [privacyMode, setPrivacyMode] = useState(
    () => localStorage.getItem("ejc_privacy_mode") === "true",
  );
  useEffect(() => {
    document.documentElement.classList.toggle("ejc-privacy-mode", privacyMode);
    localStorage.setItem("ejc_privacy_mode", String(privacyMode));
    // O dropdown de notificações e o palette (Ctrl+K) vivem FORA do <main>
    // borrado e exibem títulos de casos/prazos — com o modo ativo, fecha o
    // dropdown e suprime a abertura do palette para não vazar conteúdo.
    if (privacyMode) setNotifOpen(false);
    return () => {
      document.documentElement.classList.remove("ejc-privacy-mode");
    };
  }, [privacyMode]);
  const [notifs, setNotifs] = useState<any[]>([]);
  const [menuOpen, setMenuOpen] = useState(false);
  // Atalho "Novo caso" do cabeçalho: menu com os dois modos de abertura
  // (analisar documento | cadastro manual), ambos na rota /casos/novo.
  const [novoCasoOpen, setNovoCasoOpen] = useState(false);
  const novoCasoRef = useRef<HTMLDivElement>(null);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => {
    try {
      return JSON.parse(localStorage.getItem("ejc_menu_groups") || "{}");
    } catch {
      return {};
    }
  });

  const persistGroups = (next: Record<string, boolean>) => {
    try {
      localStorage.setItem("ejc_menu_groups", JSON.stringify(next));
    } catch {
      // Preferência de interface não deve interromper a navegação.
    }
  };

  const toggleGroup = (group: string) =>
    setOpenGroups((previous) => {
      const next = { ...previous, [group]: previous[group] === false };
      persistGroups(next);
      return next;
    });

  // Modo Essencial: os módulos avançados moram sob uma única seção "Mais /
  // Avançado" RECOLHIDA por padrão (default fechado → só abre com `=== true`).
  const MAIS_KEY = "__mais__";
  const maisOpen = openGroups[MAIS_KEY] === true;
  const toggleMais = () =>
    setOpenGroups((previous) => {
      const next = { ...previous, [MAIS_KEY]: previous[MAIS_KEY] !== true };
      persistGroups(next);
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

  // Fecha o menu "Novo caso" ao clicar fora ou pressionar Esc.
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

  // FRENTE 1 (Modo Essencial): `visible` já vem ordenado por grupo/order.
  // Particiona em essenciais (lista plana no topo, sempre visível) e resto
  // (agrupado dentro de "Mais / Avançado"). Ordem preservada da fonte.
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

  // Item de navegação reutilizado por essenciais e pela seção "Mais": quando
  // expandido mostra `label` + `description` (subtítulo discreto, line-clamp-1)
  // e `title` nativo; quando recolhido, só o ícone com Tooltip (comportamento
  // atual do rail estreito).
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
            "sidebar-nav-item group flex items-center gap-2.5 rounded-lg px-3 text-[13px] font-medium transition-all duration-150",
            collapsed ? "h-9 justify-center px-0" : "py-1.5",
            isActive && "is-active",
          )
        }
      >
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && (
          <span className="min-w-0 flex-1">
            <span className="block truncate leading-tight">{label}</span>
            {description && (
              <span className="mt-0.5 block line-clamp-1 text-[11px] font-normal leading-tight text-slate-400">
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

  return (
    <div className="min-h-screen bg-canvas text-slate-900">
      {/* Palette desmontado sob privacidade: a busca global lista partes/
          CPF/processos e renderiza fora da área borrada. */}
      {!privacyMode && <CommandPalette />}

      <header className="fixed inset-x-0 top-0 z-50 border-b border-slate-200 bg-white">
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
            className="flex shrink-0 items-center px-1 md:hidden"
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
              // Nome acessível próprio (distinto de qualquer "Buscar" local de
              // formulário/modal) — evita que seletores de teste/acessibilidade
              // por texto "Buscar" acabem acionando a busca global por engano.
              aria-label="Abrir busca global do sistema (Ctrl K)"
              className="flex h-10 w-full max-w-xl items-center gap-3 rounded-full bg-slate-900/[0.04] px-4 text-left text-sm text-slate-500 transition-all duration-150 hover:bg-primary-50 dark:bg-white/[0.06] dark:text-slate-400 dark:hover:bg-white/[0.09]"
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
              (/casos/novo) com dois modos de entrada (analisar documento |
              cadastro manual), selecionados por query param `modo` — sem
              criar rota nova. */}
          {canCreateCase && (
            <div ref={novoCasoRef} className="relative inline-flex">
              <Button
                type="button"
                size="md"
                icon={<Plus className="h-4 w-4" />}
                onClick={() => setNovoCasoOpen((value) => !value)}
                aria-haspopup="menu"
                aria-expanded={novoCasoOpen}
                aria-label="Novo caso"
              >
                <span className="hidden lg:inline">Novo caso</span>
                <ChevronDown className="hidden h-4 w-4 lg:block" />
              </Button>
              {novoCasoOpen && (
                <div
                  role="menu"
                  aria-label="Como abrir o novo caso"
                  className="card absolute right-0 top-full z-50 mt-2 w-72 py-1"
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
                        Recomendado — a IA extrai os dados do arquivo
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
                        Preencho os campos do caso por conta própria
                      </span>
                    </span>
                  </Link>
                </div>
              )}
            </div>
          )}

          <HelpButton moduleKey={moduleKey} />

          <button
            type="button"
            onClick={() => setPrivacyMode((value) => !value)}
            title={
              privacyMode
                ? "Modo privacidade ativo — clique para exibir o conteúdo"
                : "Ativar modo privacidade (borra o conteúdo para reuniões/compartilhamento de tela)"
            }
            className={cn(
              "icon-btn hidden sm:flex",
              privacyMode && "bg-primary-50 text-primary-700",
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
              onClick={() => !privacyMode && setNotifOpen((value) => !value)}
              className="icon-btn relative"
              aria-label="Notificações"
            >
              <Bell className="h-4 w-4" />
              {notifCount > 0 && (
                <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-danger-600 px-1 text-[10px] font-semibold text-white ring-2 ring-white">
                  {notifCount}
                </span>
              )}
            </button>

            {notifOpen && (
              <div className="absolute right-0 mt-2 w-80 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-md">
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
          className="fixed inset-0 z-30 bg-slate-950/45 md:hidden"
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
            "relative flex min-h-20 items-center justify-center border-b border-slate-200 px-3",
            collapsed && "px-2",
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
                "brand-logo-img w-auto object-contain",
                collapsed ? "h-8 max-w-12" : "h-14 max-w-[220px]",
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

        <nav className="flex-1 overflow-y-auto px-3 py-4 scrollbar-thin">
          {/* Essenciais — dia a dia do advogado, sempre visíveis no topo. */}
          {essentials.length > 0 && (
            <div className="mb-4">
              {!collapsed && (
                <div className="sidebar-group-label mb-2 px-2 text-2xs font-semibold uppercase tracking-[0.2em]">
                  Essencial
                </div>
              )}
              <div
                className={cn(
                  "space-y-1",
                  !collapsed && "sidebar-tree ml-3 border-l pl-2",
                )}
              >
                {essentials.map((item) => renderNavItem(item))}
              </div>
            </div>
          )}

          {/* Mais / Avançado — todo o restante dos módulos.
              Rail estreito (collapsed): lista plana de ícones+tooltip, sempre
              visível (mantém o comportamento atual). Expandido: uma única
              seção colapsável, RECOLHIDA por padrão, com os grupos dentro. */}
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
                  className="sidebar-group-label mb-2 flex w-full items-center justify-between px-2 text-2xs font-semibold uppercase tracking-[0.2em] transition-colors"
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
                          {isOpen && (
                            <div className="space-y-1 sidebar-tree ml-3 border-l pl-2">
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

        <div className="border-t border-slate-200 p-3">
          {!collapsed && (
            <div className="mb-2 flex items-center gap-2.5 rounded-xl bg-slate-50 px-3 py-2.5 ring-1 ring-inset ring-slate-200">
              <ShieldCheck className="h-4 w-4 shrink-0 text-[#D4AF37]" />
              <div className="min-w-0">
                <div className="truncate text-[11px] font-semibold text-slate-700">
                  Seguro &amp; Conforme
                </div>
                <div className="truncate text-[10px] text-slate-400">
                  Dados protegidos — LGPD
                </div>
              </div>
            </div>
          )}
          <Link
            to="/configuracoes"
            title="Abrir preferências"
            className={cn(
              "flex items-center gap-3 rounded-xl bg-slate-50 p-2",
              collapsed && "justify-center",
            )}
          >
            <UserAvatar user={user} size="md" />
            {!collapsed && (
              <div className="min-w-0 flex-1">
                <div className="truncate text-xs font-semibold text-slate-700">
                  {user?.full_name || "Usuário"}
                </div>
                <div className="truncate text-[11px] capitalize text-slate-400">
                  {user?.role || ""}
                </div>
              </div>
            )}
          </Link>
          <button
            type="button"
            onClick={logout}
            className={cn(
              "mt-2 flex h-10 w-full items-center gap-3 rounded-xl px-3 text-sm font-medium text-slate-500 transition-colors hover:bg-danger-600/10 hover:text-danger-600",
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
        {/* Aviso global: IA não ativada nesta instalação (dispensável). */}
        <IaStatusBanner />
        {/* Modo Caso: faixa fina de contexto do caso ativo (discreta). */}
        <CaseContextBar />
        <main className="ejc-modern-scope flex-1 px-4 py-5 md:px-7 md:py-7">
          <div className="mx-auto w-full max-w-[1440px] animate-rise">
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
          className="fixed bottom-5 right-5 z-30 hidden h-12 w-12 items-center justify-center rounded-xl bg-ai-600 text-white shadow-md hover:bg-ai-700 md:flex"
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
          className="fixed bottom-5 right-5 z-30 hidden h-12 w-12 cursor-not-allowed items-center justify-center rounded-xl bg-slate-300 text-white shadow-md md:flex dark:bg-slate-700"
        >
          <Bot className="h-5 w-5" />
        </button>
      )}
    </div>
  );
}
