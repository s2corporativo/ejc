import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bell,
  Clock3,
  Mail,
  MessageCircle,
  Radio,
  Scale,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import DashboardAiChat from "../components/DashboardAiChat";
import JurisprudentialAlertsStrip from "../components/JurisprudentialAlertsStrip";
import {
  getMailtoUrl,
  getWhatsAppUrl,
  officeBranding,
} from "../config/officeBranding";

interface DashboardPayload {
  prazos?: {
    vencidos?: number;
    criticos_3d?: number;
    proximos_7d?: number;
  };
  degradado?: string[];
}

interface ActivityItem {
  id?: string;
  tipo?: string;
  subtipo?: string;
  fonte?: string;
  status?: string;
}

const FINAL_ACTIVITY_STATUSES = new Set([
  "concluido",
  "concluida",
  "tratada",
  "cancelado",
  "cancelada",
  "arquivado",
  "arquivada",
  "encerrado",
  "encerrada",
]);

const LEGAL_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
  "estagiario",
]);

function isFinalActivity(status?: string) {
  return FINAL_ACTIVITY_STATUSES.has((status || "").toLowerCase());
}

function isTask(item: ActivityItem) {
  return item.tipo === "tarefa" || item.fonte === "tarefa";
}

function isIntimation(item: ActivityItem) {
  const kind =
    `${item.tipo || ""} ${item.subtipo || ""} ${item.fonte || ""}`.toLowerCase();
  return kind.includes("intimacao") || kind.includes("intimação");
}

function isMovement(item: ActivityItem) {
  const kind = `${item.tipo || ""} ${item.subtipo || ""} ${item.fonte || ""}`
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  return (
    kind.includes("moviment") ||
    kind.includes("andamento") ||
    kind.includes("datajud")
  );
}

export default function DashboardUltra() {
  const user = useAuth((state) => state.user);
  const [dashboard, setDashboard] = useState<DashboardPayload | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState({ dashboard: false, activities: false });

  useEffect(() => {
    let active = true;
    setLoading(true);
    Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/atividades", { params: { apenas_pendentes: false } }),
    ])
      .then(([dashboardResult, activitiesResult]) => {
        if (!active) return;
        setFailed({
          dashboard: dashboardResult.status === "rejected",
          activities: activitiesResult.status === "rejected",
        });
        if (dashboardResult.status === "fulfilled")
          setDashboard(dashboardResult.value.data);
        if (activitiesResult.status === "fulfilled")
          setActivities(asList(activitiesResult.value.data));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  const pendingTasks = useMemo(
    () =>
      activities.filter(
        (item) => isTask(item) && !isFinalActivity(item.status),
      ),
    [activities],
  );
  const pendingIntimations = useMemo(
    () =>
      activities.filter(
        (item) => isIntimation(item) && !isFinalActivity(item.status),
      ),
    [activities],
  );
  const pendingMovements = useMemo(
    () =>
      activities.filter(
        (item) => isMovement(item) && !isFinalActivity(item.status),
      ),
    [activities],
  );

  const deadlinesUnavailable =
    failed.dashboard || new Set(dashboard?.degradado || []).has("prazos");
  const deadlineCount = deadlinesUnavailable
    ? 0
    : (dashboard?.prazos?.vencidos ?? 0) +
      (dashboard?.prazos?.criticos_3d ?? 0);
  const canUseLegal = LEGAL_ROLES.has(user?.role || "");
  const whatsappUrl = getWhatsAppUrl();
  const mailtoUrl = getMailtoUrl();

  return (
    <div className="ejc-ai-dashboard">
      <header className="ejc-ai-dashboard__brandbar">
        <div className="ejc-ai-dashboard__brand">
          <img
            src={officeBranding.logoPath}
            alt="De Paula Teixeira Advogados"
            className="ejc-ai-dashboard__logo"
          />
          <div>
            <span>Ecossistema Jurídico</span>
            <h1>EJC</h1>
            <p>
              Inteligência jurídica, documentos e estratégia em um único fluxo.
            </p>
          </div>
        </div>
        <div
          className="ejc-ai-dashboard__contacts"
          aria-label="Contatos do escritório"
        >
          {whatsappUrl ? (
            <a
              href={whatsappUrl}
              target="_blank"
              rel="noreferrer"
              aria-label="Abrir WhatsApp do escritório"
            >
              <MessageCircle aria-hidden="true" /> WhatsApp
            </a>
          ) : (
            <span
              className="is-disabled"
              title="WhatsApp institucional não configurado"
            >
              <MessageCircle aria-hidden="true" /> WhatsApp
            </span>
          )}
          {mailtoUrl ? (
            <a href={mailtoUrl} aria-label="Enviar e-mail ao escritório">
              <Mail aria-hidden="true" /> E-mail
            </a>
          ) : null}
        </div>
      </header>

      <section
        className="ejc-ai-dashboard__signals"
        aria-label="Radar operacional de prazos e atividades"
      >
        <Link
          to="/atividades?tipo=prazo"
          aria-label={`Prazos: ${deadlinesUnavailable || loading ? "—" : deadlineCount}. ${dashboard?.prazos?.vencidos ?? 0} vencidos · ${dashboard?.prazos?.criticos_3d ?? 0} críticos`}
          className={`ejc-ai-signal is-deadline ${deadlineCount > 0 ? "is-alerting" : ""}`}
        >
          <span className="ejc-ai-signal__beacon" aria-hidden="true" />
          <Scale aria-hidden="true" />
          <span>
            <strong>
              {deadlinesUnavailable || loading ? "—" : deadlineCount}
            </strong>
            <small>Prazos em atenção</small>
          </span>
          {!deadlinesUnavailable && (
            <em>
              {dashboard?.prazos?.vencidos ?? 0} vencidos ·{" "}
              {dashboard?.prazos?.criticos_3d ?? 0} em até 3 dias
            </em>
          )}
        </Link>

        <Link
          to="/atividades?tipo=tarefa"
          aria-label={`Tarefas: ${failed.activities || loading ? "—" : pendingTasks.length}. pendentes`}
          className={`ejc-ai-signal is-task ${pendingTasks.length > 0 ? "is-alerting" : ""}`}
        >
          <span className="ejc-ai-signal__beacon" aria-hidden="true" />
          <Clock3 aria-hidden="true" />
          <span>
            <strong>
              {failed.activities || loading ? "—" : pendingTasks.length}
            </strong>
            <small>Tarefas pendentes</small>
          </span>
        </Link>

        <Link
          to="/atividades?tipo=intimacao"
          aria-label={`Intimações: ${failed.activities || loading ? "—" : pendingIntimations.length}. a tratar`}
          className={`ejc-ai-signal is-intimation ${pendingIntimations.length > 0 ? "is-alerting" : ""}`}
        >
          <span className="ejc-ai-signal__beacon" aria-hidden="true" />
          <Bell aria-hidden="true" />
          <span>
            <strong>
              {failed.activities || loading ? "—" : pendingIntimations.length}
            </strong>
            <small>Intimações pendentes</small>
          </span>
        </Link>

        <Link
          to="/atividades"
          aria-label={`Movimentações: ${failed.activities || loading ? "—" : pendingMovements.length}. recentes / pendentes`}
          className={`ejc-ai-signal is-movement ${pendingMovements.length > 0 ? "is-alerting" : ""}`}
        >
          <span className="ejc-ai-signal__beacon" aria-hidden="true" />
          <Radio aria-hidden="true" />
          <span>
            <strong>
              {failed.activities || loading ? "—" : pendingMovements.length}
            </strong>
            <small>Movimentações</small>
          </span>
        </Link>
      </section>

      <main className="ejc-ai-dashboard__workspace">
        <div className="ejc-ai-dashboard__workspace-header">
          <div>
            <span>
              <Sparkles aria-hidden="true" /> Inteligência Jurídica
            </span>
            <h2>
              Converse, anexe, analise e transforme informação em estratégia
              jurídica
            </h2>
          </div>
          <Link to="/sala-juridica" className="ejc-ai-dashboard__full-link">
            Abrir tela completa
          </Link>
        </div>
        <DashboardAiChat canUseLegal={canUseLegal} />
      </main>

      <section
        className="ejc-ai-dashboard__legal-radar"
        aria-label="Radar Jurídico"
      >
        <div className="ejc-ai-dashboard__legal-radar-head">
          <strong>Radar Jurídico</strong>
          <Link to="/dpt360/radar">Abrir radar</Link>
        </div>
        <JurisprudentialAlertsStrip compact />
      </section>

      <footer className="ejc-ai-dashboard__footer">
        <span>
          © {new Date().getFullYear()} {officeBranding.officeName}
        </span>
        <span>
          <AlertTriangle aria-hidden="true" /> Conteúdo jurídico de IA exige
          revisão humana.
        </span>
      </footer>
    </div>
  );
}
