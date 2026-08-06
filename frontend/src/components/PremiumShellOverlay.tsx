import { useEffect, useMemo, useState, type ReactNode } from "react";
import { BrainCircuit, Clock3, Mail, MessageCircle, Quote } from "lucide-react";
import { Link, useLocation } from "react-router";
import {
  getMailtoUrl,
  getWhatsAppUrl,
  officeBranding,
} from "../config/officeBranding";
import { useAuth } from "../stores/auth";
import { usePreferencesStore } from "../stores/preferences";
import UserAvatar from "./UserAvatar";
import SidebarWeekCalendar from "./SidebarWeekCalendar";

function useMinuteClock() {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    let interval: number | undefined;
    const delay = 60_000 - (Date.now() % 60_000) + 50;
    const timeout = window.setTimeout(() => {
      setNow(new Date());
      interval = window.setInterval(() => setNow(new Date()), 60_000);
    }, delay);
    return () => {
      window.clearTimeout(timeout);
      if (interval) window.clearInterval(interval);
    };
  }, []);

  return now;
}

function roleLabel(role?: string) {
  const labels: Record<string, string> = {
    superadmin: "Superadministrador",
    admin: "Administrador",
    socio: "Sócio",
    advogado: "Advogado",
    advogado_auxiliar: "Advogado auxiliar",
    estagiario: "Estagiário",
    secretaria: "Secretaria",
    financeiro: "Financeiro",
  };
  return role ? labels[role] || role.replace(/_/g, " ") : "Usuário";
}

function OfficeAction({
  href,
  label,
  secondary,
  icon,
  newTab = false,
}: {
  href: string;
  label: string;
  secondary?: string;
  icon: ReactNode;
  newTab?: boolean;
}) {
  const content = (
    <>
      <span className="ejc-office-action__icon">{icon}</span>
      <span className="ejc-office-action__copy">
        <strong>{label}</strong>
        {secondary && <small>{secondary}</small>}
      </span>
    </>
  );

  if (!href) {
    return (
      <button
        type="button"
        className="ejc-office-action is-disabled"
        disabled
        title={`${label}: configuração pública pendente`}
        aria-label={`${label}: configuração pendente`}
      >
        {content}
      </button>
    );
  }

  return (
    <a
      className="ejc-office-action"
      href={href}
      target={newTab ? "_blank" : undefined}
      rel={newTab ? "noopener noreferrer" : undefined}
      title={label === "IA do Escritório" ? "Abrir IA do Escritório" : label}
    >
      {content}
    </a>
  );
}

export default function PremiumShellOverlay() {
  const user = useAuth((state) => state.user);
  const collapsed = usePreferencesStore((state) => state.sidebarCollapsed);
  const location = useLocation();
  const now = useMinuteClock();

  useEffect(() => {
    document.documentElement.style.setProperty(
      "--ejc-sidebar-shell-width",
      collapsed ? "5.25rem" : "18rem",
    );
    document.documentElement.classList.toggle("ejc-shell-collapsed", collapsed);
    return () => {
      document.documentElement.classList.remove("ejc-shell-collapsed");
    };
  }, [collapsed]);

  useEffect(() => {
    document.body.classList.add("ejc-premium-shell-active");
    document.body.classList.toggle(
      "ejc-dashboard-route",
      location.pathname === "/",
    );
    return () => {
      document.body.classList.remove(
        "ejc-premium-shell-active",
        "ejc-dashboard-route",
      );
    };
  }, [location.pathname]);

  const formatted = useMemo(() => {
    const time = new Intl.DateTimeFormat("pt-BR", {
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: officeBranding.timezone,
    }).format(now);
    const date = new Intl.DateTimeFormat("pt-BR", {
      weekday: "long",
      day: "2-digit",
      month: "long",
      timeZone: officeBranding.timezone,
    }).format(now);
    return { time, date };
  }, [now]);

  return (
    <>
      <div
        className="ejc-premium-topbar"
        role="region"
        aria-label="Informações e contatos do escritório"
      >
        <div
          className="ejc-premium-topbar__clock"
          aria-label="Data e hora atual"
        >
          <Clock3 aria-hidden="true" />
          <div>
            <strong>{formatted.time}</strong>
            <span>{formatted.date}</span>
          </div>
        </div>

        <div className="ejc-premium-topbar__message">
          <Quote aria-hidden="true" />
          <div>
            <p>{officeBranding.dailyMessage}</p>
            <span>{officeBranding.dailyMessageSource}</span>
          </div>
        </div>

        <div
          className="ejc-premium-topbar__actions"
          aria-label="Ações do escritório"
        >
          <OfficeAction
            href={getWhatsAppUrl()}
            label="WhatsApp"
            icon={<MessageCircle aria-hidden="true" />}
            newTab
          />
          <OfficeAction
            href={getMailtoUrl()}
            label="E-mail"
            icon={<Mail aria-hidden="true" />}
          />
          <OfficeAction
            href={officeBranding.officeAiUrl}
            label="IA do Escritório"
            secondary={officeBranding.officeAiLabel}
            icon={<BrainCircuit aria-hidden="true" />}
            newTab
          />
        </div>

        <Link
          to="/configuracoes"
          className="ejc-premium-topbar__profile"
          aria-label="Abrir perfil e preferências"
        >
          <UserAvatar user={user} size="md" />
          <span>
            <strong>{user?.full_name || "Usuário"}</strong>
            <small>{roleLabel(user?.role)}</small>
          </span>
        </Link>
      </div>

      {!collapsed && <SidebarWeekCalendar />}
    </>
  );
}
