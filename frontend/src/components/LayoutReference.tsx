import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";
import {
  Bell,
  Bot,
  CalendarDays,
  ChevronDown,
  Eye,
  EyeOff,
  Mail,
  Menu,
  MessageCircle,
  Search,
  X,
} from "lucide-react";
import CaseContextBar from "./CaseContextBar";
import CommandPalette from "./CommandPalette";
import ErrorBoundary from "./ErrorBoundary";
import HelpButton from "./HelpButton";
import IaStatusBanner from "./IaStatusBanner";
import ModuleLifecycleGate from "./ModuleLifecycleGate";
import OnboardingTour from "./OnboardingTour";
import SecurityMenu from "./SecurityMenu";
import { toast } from "./Toast";
import SidebarWeekCalendar from "./SidebarWeekCalendar";
import { Tooltip, cn } from "./UI";
import {
  officeBranding,
  getMailtoUrl,
  getWhatsAppUrl,
} from "../config/officeBranding";
import {
  getHelpModuleKey,
  getNavigationModules,
  type ModuleRoute,
} from "../config/moduleRegistry";
import { ROTULO_IA_NAO_ATIVADA } from "../lib/iaErro";
import { useIaStatus } from "../lib/iaStatus";
import { filterModulesByLifecycle } from "../lib/moduleLifecycle";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import { useModuleLifecycleStore } from "../stores/moduleLifecycle";
import { usePreferencesStore } from "../stores/preferences";

const PRIMARY_NAV_KEYS = [
  "dashboard",
  "casos",
  "atividades",
  "clientes",
  "documentos",
  "pecas",
  "financeiro",
  "inteligencia",
  "configuracoes",
] as const;

const NAV_LABELS: Record<string, string> = {
  atividades: "Prazos e Agenda",
  financeiro: "Financeiro",
  inteligencia: "IA Jurídica",
  configuracoes: "Configurações",
};

function formatClock(date: Date) {
  const dateText = new Intl.DateTimeFormat("pt-BR", {
    timeZone: officeBranding.timezone,
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(date);
  const weekday = new Intl.DateTimeFormat("pt-BR", {
    timeZone: officeBranding.timezone,
    weekday: "long",
  }).format(date);
  const time = new Intl.DateTimeFormat("pt-BR", {
    timeZone: officeBranding.timezone,
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
  return {
    dateText,
    subtext: `${weekday.charAt(0).toUpperCase()}${weekday.slice(1)} · ${time}`,
  };
}

/**
 * AppShell de referência 2026.
 *
 * A implementação altera exclusivamente navegação/apresentação do shell:
 * RBAC, lifecycle, busca global, notificações, contexto do caso, IA, segurança
 * e o Outlet continuam usando os mesmos serviços e componentes do EJC.
 */
export default function LayoutReference() {
  const user = useAuth((state) => state.user);
  const { disponivel: iaDisponivel } = useIaStatus();
  const lifecycleSettings = useModuleLifecycleStore((state) => state.settings);
  const { sidebarCollapsed: collapsed, setSidebarCollapsed } =
    usePreferencesStore();
  const location = useLocation();
  const navigate = useNavigate();
  const moduleKey = useMemo(
    () => getHelpModuleKey(location.pathname),
    [location.pathname],
  );

  const [mobileOpen, setMobileOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [notifCount, setNotifCount] = useState(0);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [now, setNow] = useState(() => new Date());
  const [privacyMode, setPrivacyMode] = useState(
    () => localStorage.getItem("ejc_privacy_mode") === "true",
  );

  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("ejc-privacy-mode", privacyMode);
    localStorage.setItem("ejc_privacy_mode", String(privacyMode));
    if (privacyMode) setNotifOpen(false);
    return () => document.documentElement.classList.remove("ejc-privacy-mode");
  }, [privacyMode]);

  useEffect(() => {
    const loadNotifications = () =>
      api
        .get("/notifications/?apenas_nao_lidas=false&limit=15")
        .then((response) => {
          setNotifications(response.data.data ?? []);
          setNotifCount(response.data.nao_lidas ?? 0);
        })
        .catch(() => {});

    loadNotifications();
    const timer = window.setInterval(loadNotifications, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const visible = useMemo(
    () =>
      filterModulesByLifecycle(
        getNavigationModules(user?.role),
        lifecycleSettings,
      ),
    [user?.role, lifecycleSettings],
  );

  const primary = useMemo(() => {
    const map = new Map(visible.map((item) => [item.key, item]));
    return PRIMARY_NAV_KEYS.map((key) => map.get(key)).filter(
      (item): item is ModuleRoute => Boolean(item),
    );
  }, [visible]);

  const primaryKeys = useMemo(
    () => new Set(primary.map((item) => item.key)),
    [primary],
  );
  const secondary = useMemo(
    () => visible.filter((item) => !primaryKeys.has(item.key)),
    [primaryKeys, visible],
  );

  const sidebarWidth = collapsed ? "md:w-[4.75rem]" : "md:w-[15.5rem]";
  const contentMargin = collapsed ? "md:ml-[4.75rem]" : "md:ml-[15.5rem]";
  const clock = formatClock(now);
  const whatsappUrl = getWhatsAppUrl();
  const mailtoUrl = getMailtoUrl();

  const renderNavItem = (item: ModuleRoute) => {
    const Icon = item.icon;
    const label = NAV_LABELS[item.key] || item.label;
    const content = (
      <NavLink
        key={item.path}
        to={item.path}
        end={item.end}
        onClick={() => setMobileOpen(false)}
        className={({ isActive }) =>
          cn(
            "sidebar-nav-item flex items-center gap-3 px-3 transition-colors",
            collapsed ? "justify-center px-0" : "",
            isActive && "is-active",
          )
        }
      >
        <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
        {!collapsed && <span className="truncate">{label}</span>}
      </NavLink>
    );

    return collapsed ? (
      <Tooltip key={item.path} label={label}>
        {content}
      </Tooltip>
    ) : (
      content
    );
  };

  return (
    <div className="min-h-screen bg-canvas text-slate-900">
      {!privacyMode && <CommandPalette />}

      <header className="fixed inset-x-0 top-0 z-50 border-b border-slate-200 bg-white">
        <div className="flex items-center gap-3 px-3 md:px-5">
          <button
            type="button"
            className="icon-btn"
            onClick={() => {
              if (window.matchMedia("(min-width: 768px)").matches) {
                setSidebarCollapsed(!collapsed);
              } else {
                setMobileOpen(true);
              }
            }}
            aria-label={collapsed ? "Expandir menu" : "Abrir ou recolher menu"}
          >
            <Menu className="h-5 w-5" />
          </button>

          <Link
            to="/"
            className="hidden shrink-0 items-center md:flex"
            aria-label="Ir para o início do EJC"
          >
            <img
              src={officeBranding.logoPath}
              alt={officeBranding.officeName}
              className="brand-logo-img h-10 w-auto max-w-[190px] object-contain"
            />
          </Link>

          <div className="flex min-w-0 flex-1 justify-center px-1 md:px-4">
            <button
              type="button"
              onClick={() => window.dispatchEvent(new Event("ejc-open-search"))}
              className="ejc-header-search flex w-full max-w-[650px] items-center gap-3 px-3.5 text-left text-sm"
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="hidden truncate sm:inline">
                Buscar clientes, casos, documentos, peças…
              </span>
              <span className="truncate sm:hidden">Buscar…</span>
              <kbd className="ml-auto hidden px-1.5 py-0.5 text-[10px] font-medium sm:block">
                ⌘ K
              </kbd>
            </button>
          </div>

          <div
            className="ejc-header-clock"
            aria-label={`${clock.dateText}, ${clock.subtext}`}
          >
            <CalendarDays aria-hidden="true" />
            <span>
              <strong>{clock.dateText}</strong>
              <span>{clock.subtext}</span>
            </span>
          </div>

          <HelpButton moduleKey={moduleKey} />

          <button
            type="button"
            onClick={() => setPrivacyMode((value) => !value)}
            className={cn(
              "icon-btn hidden sm:flex",
              privacyMode && "bg-primary-50 text-primary-700",
            )}
            title={
              privacyMode
                ? "Desativar modo privacidade"
                : "Ativar modo privacidade"
            }
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
              <div className="card absolute right-0 mt-2 w-80 overflow-hidden py-0 shadow-float animate-pop">
                <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
                  <div className="text-sm font-semibold text-slate-950">
                    Notificações
                  </div>
                  <button
                    type="button"
                    className="text-xs font-medium text-primary-700 hover:text-primary-900"
                    onClick={() => {
                      api
                        .post("/notifications/ler-todas")
                        .then(() => {
                          setNotifCount(0);
                          setNotifications((items) =>
                            items.map((item) => ({ ...item, lida: true })),
                          );
                        })
                        .catch(() => {
                          toast.error(
                            "Não foi possível marcar as notificações como lidas.",
                          );
                        });
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
                          setNotifOpen(false);
                        }}
                        className={cn(
                          "w-full border-b border-slate-100 px-4 py-3 text-left hover:bg-slate-50",
                          !notification.lida && "bg-primary-50/60",
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

      {mobileOpen && (
        <button
          type="button"
          className="fixed inset-0 z-30 bg-slate-950/30 md:hidden"
          aria-label="Fechar menu"
          onClick={() => setMobileOpen(false)}
        />
      )}

      <aside
        className={cn(
          "sidebar-bronze fixed bottom-0 left-0 top-[72px] z-40 flex-col transition-all",
          sidebarWidth,
          mobileOpen ? "flex w-[15.5rem] md:flex" : "hidden md:flex",
        )}
      >
        <div className="flex items-center justify-between px-3 pt-3 md:hidden">
          <img
            src={officeBranding.logoPath}
            alt={officeBranding.officeName}
            className="h-9 w-auto max-w-[170px] object-contain"
          />
          <button
            type="button"
            className="icon-btn h-8 w-8"
            onClick={() => setMobileOpen(false)}
            aria-label="Fechar menu"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-3 scrollbar-thin">
          <div className="space-y-1">{primary.map(renderNavItem)}</div>

          {secondary.length > 0 && (
            <div className="mt-3 border-t border-slate-100 pt-2">
              {collapsed ? (
                <div className="space-y-1">{secondary.map(renderNavItem)}</div>
              ) : (
                <>
                  <button
                    type="button"
                    onClick={() => setMoreOpen((value) => !value)}
                    className="sidebar-group-label flex w-full items-center justify-between rounded-lg px-3 py-2 text-[9px] font-semibold uppercase tracking-[0.16em]"
                    aria-expanded={moreOpen}
                  >
                    <span>Mais</span>
                    <ChevronDown
                      className={cn(
                        "h-3 w-3 transition-transform",
                        !moreOpen && "-rotate-90",
                      )}
                    />
                  </button>
                  {moreOpen && (
                    <div className="mt-1 space-y-1">
                      {secondary.map(renderNavItem)}
                    </div>
                  )}
                </>
              )}
            </div>
          )}
        </nav>

        {!collapsed && <SidebarWeekCalendar />}

        <div className="border-t border-slate-200 bg-white">
          <div
            className={cn("ejc-sidebar-contacts", collapsed && "flex-col px-2")}
          >
            {whatsappUrl ? (
              <a
                href={whatsappUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="ejc-sidebar-contact is-whatsapp"
                aria-label="Abrir WhatsApp"
              >
                <MessageCircle className="h-5 w-5" aria-hidden="true" />
              </a>
            ) : (
              <button
                type="button"
                className="ejc-sidebar-contact is-disabled"
                disabled
                title="WhatsApp institucional não configurado"
                aria-label="WhatsApp não configurado"
              >
                <MessageCircle className="h-5 w-5" aria-hidden="true" />
              </button>
            )}
            {mailtoUrl ? (
              <a
                href={mailtoUrl}
                className="ejc-sidebar-contact"
                aria-label="Enviar e-mail"
              >
                <Mail className="h-5 w-5" aria-hidden="true" />
              </a>
            ) : (
              <button
                type="button"
                className="ejc-sidebar-contact is-disabled"
                disabled
                title="E-mail institucional não configurado"
                aria-label="E-mail não configurado"
              >
                <Mail className="h-5 w-5" aria-hidden="true" />
              </button>
            )}
          </div>
        </div>
      </aside>

      <div
        className={cn(
          "relative z-10 flex min-h-screen flex-col pt-[72px] transition-all",
          contentMargin,
        )}
      >
        <IaStatusBanner />
        <CaseContextBar />
        <main className="ejc-modern-scope flex-1 px-3 py-4 md:px-5 md:py-5">
          <div className="mx-auto w-full animate-rise">
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
          className="fixed bottom-5 right-5 z-30 hidden h-11 w-11 items-center justify-center rounded-xl bg-[#0b2a55] text-white shadow-float transition hover:-translate-y-0.5 hover:bg-[#123968] md:flex"
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
          className="fixed bottom-5 right-5 z-30 hidden h-11 w-11 cursor-not-allowed items-center justify-center rounded-xl bg-slate-300 text-white shadow-md md:flex dark:bg-slate-700"
        >
          <Bot className="h-5 w-5" />
        </button>
      )}
    </div>
  );
}
