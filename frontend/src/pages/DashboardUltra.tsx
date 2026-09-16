import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bell,
  CheckCircle2,
  Clock3,
  Eye,
  Mail,
  MessageCircle,
  Radio,
  Scale,
  Sparkles,
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import DashboardAiChat from "../components/DashboardAiChat";
import JurisprudentialAlertsStrip from "../components/JurisprudentialAlertsStrip";
import {
  getMailtoUrl,
  getWhatsAppUrl,
  officeBranding,
} from "../config/officeBranding";

type AlertType = "prazo" | "tarefa" | "intimacao" | "movimentacao";
type AlertState = "novo" | "visualizado" | "tratado";
type AlertLevel = "critico" | "alto" | "atencao" | "info" | "normal";

type AlertSummary = {
  ativos: number;
  novos: number;
  criticos: number;
  altos: number;
};

type SmartAlert = {
  source_type: AlertType;
  source_id: string;
  titulo: string;
  descricao?: string | null;
  data?: string | null;
  case_id?: string | null;
  caso_titulo?: string | null;
  responsavel_nome?: string | null;
  prioridade?: string | null;
  dias_restantes?: number | null;
  nivel_alerta: AlertLevel;
  estado_alerta: AlertState;
  link: string;
};

type SmartAlertPayload = {
  resumo: Record<AlertType, AlertSummary>;
  itens: Record<AlertType, SmartAlert[]>;
};

const EMPTY_SUMMARY: AlertSummary = {
  ativos: 0,
  novos: 0,
  criticos: 0,
  altos: 0,
};

// Paridade deliberada com `requer_advogado` do endpoint de mensagens da Sala.
// Perfis auxiliares continuam vendo o Dashboard, mas não recebem um composer que
// o backend invariavelmente recusaria com 403.
const AI_MESSAGE_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
]);

const ALERT_CONFIG: Array<{
  type: AlertType;
  label: string;
  hint: string;
  className: string;
  icon: typeof Scale;
}> = [
  {
    type: "prazo",
    label: "Prazos",
    hint: "vencidos ou em até 3 dias",
    className: "is-deadline",
    icon: Scale,
  },
  {
    type: "tarefa",
    label: "Tarefas",
    hint: "vencidas, hoje ou alta prioridade",
    className: "is-task",
    icon: Clock3,
  },
  {
    type: "intimacao",
    label: "Intimações",
    hint: "pendentes de tratamento",
    className: "is-intimation",
    icon: Bell,
  },
  {
    type: "movimentacao",
    label: "Movimentações",
    hint: "novidades dos últimos 7 dias",
    className: "is-movement",
    icon: Radio,
  },
];

function formatAlertDate(value?: string | null) {
  if (!value) return "Sem data";
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (match) return `${match[3]}/${match[2]}/${match[1]}`;
  return value;
}

function stateLabel(state: AlertState) {
  if (state === "visualizado") return "Visualizado";
  if (state === "tratado") return "Tratado";
  return "Novo";
}

function levelLabel(level: AlertLevel) {
  if (level === "critico") return "Crítico";
  if (level === "alto") return "Alto";
  if (level === "atencao") return "Atenção";
  if (level === "info") return "Novo andamento";
  return "Normal";
}

export default function DashboardUltra() {
  const user = useAuth((state) => state.user);
  const navigate = useNavigate();
  const [alerts, setAlerts] = useState<SmartAlertPayload | null>(null);
  const [activeType, setActiveType] = useState<AlertType | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [updatingId, setUpdatingId] = useState<string | null>(null);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const { data } = await api.get("/atividades/alertas-inteligentes", {
        params: { limit_per_type: 5 },
      });
      setAlerts(data as SmartAlertPayload);
    } catch {
      setFailed(true);
      setAlerts(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAlerts();
  }, [loadAlerts]);

  const canUseLegal = AI_MESSAGE_ROLES.has(user?.role || "");
  const whatsappUrl = getWhatsAppUrl();
  const mailtoUrl = getMailtoUrl();
  const activeItems = useMemo(
    () => (activeType ? alerts?.itens?.[activeType] || [] : []),
    [activeType, alerts],
  );

  const markState = async (
    item: SmartAlert,
    estado: "visualizado" | "tratado",
    openAfter = false,
  ) => {
    setUpdatingId(item.source_id);
    try {
      await api.patch(
        `/atividades/alertas/${item.source_type}/${item.source_id}`,
        { estado },
      );
      if (openAfter) {
        navigate(item.link);
        return;
      }
      await loadAlerts();
    } finally {
      setUpdatingId(null);
    }
  };

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
        aria-label="Alertas inteligentes do escritório"
      >
        {ALERT_CONFIG.map((config) => {
          const summary = alerts?.resumo?.[config.type] || EMPTY_SUMMARY;
          const Icon = config.icon;
          const isActive = activeType === config.type;
          return (
            <button
              type="button"
              key={config.type}
              aria-pressed={isActive}
              aria-label={`${config.label}: ${failed || loading ? "—" : summary.ativos}. ${summary.novos} novos`}
              className={`ejc-ai-signal ${config.className} ${summary.novos > 0 ? "is-alerting" : ""} ${isActive ? "is-selected" : ""}`}
              onClick={() =>
                setActiveType((current) =>
                  current === config.type ? null : config.type,
                )
              }
            >
              <span className="ejc-ai-signal__beacon" aria-hidden="true" />
              <Icon aria-hidden="true" />
              <span>
                <strong>{failed || loading ? "—" : summary.ativos}</strong>
                <small>{config.label}</small>
              </span>
              <em>
                {summary.novos > 0 ? `${summary.novos} novos · ` : ""}
                {config.hint}
              </em>
            </button>
          );
        })}
      </section>

      {activeType && (
        <section
          className="ejc-smart-alert-panel"
          aria-label={`Detalhes dos alertas de ${activeType}`}
        >
          <header>
            <div>
              <strong>
                {ALERT_CONFIG.find((item) => item.type === activeType)?.label}
              </strong>
              <span>
                O estado do alerta é pessoal e não altera o status jurídico da
                atividade de origem.
              </span>
            </div>
            <Link
              to={
                activeType === "movimentacao"
                  ? "/casos"
                  : `/atividades?tipo=${activeType}`
              }
            >
              Ver todos
            </Link>
          </header>

          {failed ? (
            <div className="ejc-smart-alert-panel__empty">
              Alertas temporariamente indisponíveis.
            </div>
          ) : activeItems.length === 0 ? (
            <div className="ejc-smart-alert-panel__empty">
              Nenhum alerta acionável nesta categoria.
            </div>
          ) : (
            <div className="ejc-smart-alert-list">
              {activeItems.map((item) => (
                <article
                  key={`${item.source_type}-${item.source_id}`}
                  className={`ejc-smart-alert-item is-${item.nivel_alerta}`}
                >
                  <div className="ejc-smart-alert-item__meta">
                    <span className={`is-state-${item.estado_alerta}`}>
                      {stateLabel(item.estado_alerta)}
                    </span>
                    <span>{levelLabel(item.nivel_alerta)}</span>
                  </div>
                  <div className="ejc-smart-alert-item__body">
                    <strong>{item.titulo}</strong>
                    <p>
                      {item.caso_titulo ||
                        item.descricao ||
                        "Sem detalhe adicional."}
                    </p>
                    <small>
                      {formatAlertDate(item.data)}
                      {item.responsavel_nome
                        ? ` · Responsável: ${item.responsavel_nome}`
                        : ""}
                    </small>
                  </div>
                  <div className="ejc-smart-alert-item__actions">
                    {item.estado_alerta === "novo" && (
                      <button
                        type="button"
                        disabled={updatingId === item.source_id}
                        onClick={() => void markState(item, "visualizado")}
                      >
                        <Eye aria-hidden="true" /> Visto
                      </button>
                    )}
                    <button
                      type="button"
                      disabled={updatingId === item.source_id}
                      onClick={() => void markState(item, "visualizado", true)}
                    >
                      Abrir
                    </button>
                    <button
                      type="button"
                      className="is-treat"
                      disabled={updatingId === item.source_id}
                      onClick={() => void markState(item, "tratado")}
                    >
                      <CheckCircle2 aria-hidden="true" /> Tratar alerta
                    </button>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}

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
