import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  BellRing,
  Gavel,
  Mail,
  MessageCircle,
  Scale,
  Sparkles,
} from "lucide-react";
import { Link } from "react-router";
import JurisprudentialAlertsStrip from "../components/JurisprudentialAlertsStrip";
import {
  getMailtoUrl,
  getWhatsAppUrl,
  officeBranding,
} from "../config/officeBranding";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import "../styles/dashboard-canonical.css";
import { EntradaInteligente } from "./EntradaUnica";

type AlertType = "prazo" | "tarefa" | "intimacao" | "movimentacao";

type AlertSummary = {
  ativos: number;
  novos: number;
  criticos: number;
  altos: number;
};

type SmartAlertPayload = {
  resumo: Record<AlertType, AlertSummary>;
};

const EMPTY_SUMMARY: AlertSummary = {
  ativos: 0,
  novos: 0,
  criticos: 0,
  altos: 0,
};

const AI_MESSAGE_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
]);

const ENTRY_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "secretaria",
]);

/** Início canônico do EJC com Entrada Única, sinais operacionais e Radar Jurídico. */
export default function DashboardUltra() {
  const user = useAuth((state) => state.user);
  const [alerts, setAlerts] = useState<SmartAlertPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const loadAlerts = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const { data } = await api.get("/atividades/alertas-inteligentes", {
        params: { limit_per_type: 1 },
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

  const prazo = alerts?.resumo?.prazo || EMPTY_SUMMARY;
  const intimacao = alerts?.resumo?.intimacao || EMPTY_SUMMARY;
  const movimentacao = alerts?.resumo?.movimentacao || EMPTY_SUMMARY;

  const comunicacoes = useMemo(
    () => ({
      ativos: intimacao.ativos + movimentacao.ativos,
      novos: intimacao.novos + movimentacao.novos,
    }),
    [intimacao, movimentacao],
  );

  const canUseLegal = AI_MESSAGE_ROLES.has(user?.role || "");
  const canUseEntry = ENTRY_ROLES.has(user?.role || "");
  const firstName = user?.full_name?.trim().split(/\s+/)[0] || "equipe";
  const whatsappUrl = getWhatsAppUrl();
  const mailtoUrl = getMailtoUrl();
  const metricUnavailable = failed || loading;

  let prazoHint = "vencidos ou próximos do vencimento";
  if (metricUnavailable) {
    prazoHint = "consultar agenda";
  } else if (prazo.criticos > 0) {
    prazoHint = `${prazo.criticos} críticos · ${prazo.altos} altos`;
  }

  let comunicacoesHint = "intimações e movimentações monitoradas";
  if (metricUnavailable) {
    comunicacoesHint = "consultar central";
  } else if (comunicacoes.novos > 0) {
    comunicacoesHint = `${comunicacoes.novos} novas · intimações e movimentações`;
  }

  return (
    <div className="ejc-ai-dashboard">
      <header className="ejc-ai-dashboard__brandbar ejc-ai-dashboard__welcome">
        <div className="ejc-ai-dashboard__welcome-copy">
          <span>EJC DePaula Teixeira Adv</span>
          <h2>Olá, {firstName}.</h2>
          <p>
            Decisões jurídicas com organização, clareza e rastreabilidade.
          </p>
        </div>
        <div className="ejc-ai-dashboard__motto" aria-hidden="true">
          <span>Conhecimento</span>
          <span>Estratégia</span>
          <span>Resultados reais</span>
        </div>
      </header>

      <section
        className="ejc-ai-dashboard__signals ejc-ai-dashboard__signals--canonical"
        aria-label="Atalhos operacionais do início"
      >
        <Link
          to="/ajuizamento"
          className="ejc-ai-signal is-task"
          aria-label="Abrir Ajuizamento"
        >
          <span className="ejc-ai-signal__beacon" aria-hidden="true" />
          <Gavel aria-hidden="true" />
          <span>
            <strong>Abrir</strong>
            <small>Ajuizamento</small>
          </span>
          <em>validação, revisão, assinatura e registro do protocolo</em>
        </Link>

        <Link
          to="/atividades?tipo=prazo"
          className={`ejc-ai-signal is-deadline ${
            prazo.criticos > 0 ? "is-alerting" : ""
          }`}
          aria-label={`Riscos de prazos: ${
            metricUnavailable ? "indisponível" : prazo.ativos
          }`}
        >
          <span className="ejc-ai-signal__beacon" aria-hidden="true" />
          <Scale aria-hidden="true" />
          <span>
            <strong>{metricUnavailable ? "—" : prazo.ativos}</strong>
            <small>Riscos de Prazos</small>
          </span>
          <em>{prazoHint}</em>
        </Link>

        <Link
          to="/atividades?tipo=intimacao"
          className={`ejc-ai-signal is-intimation ${
            comunicacoes.novos > 0 ? "is-alerting" : ""
          }`}
          aria-label={`Comunicações processuais: ${
            metricUnavailable ? "indisponível" : comunicacoes.ativos
          }`}
        >
          <span className="ejc-ai-signal__beacon" aria-hidden="true" />
          <BellRing aria-hidden="true" />
          <span>
            <strong>{metricUnavailable ? "—" : comunicacoes.ativos}</strong>
            <small>Comunicações Processuais</small>
          </span>
          <em>{comunicacoesHint}</em>
        </Link>
      </section>

      <div className="ejc-ai-dashboard__main-grid">
        <main className="ejc-ai-dashboard__workspace ejc-ai-dashboard__workspace--entry">
          <div className="ejc-ai-dashboard__workspace-header">
            <div>
              <span>
                <Sparkles aria-hidden="true" /> Entrada Única
              </span>
              <h2>
                Conte o caso ou envie os documentos. O EJC identifica, organiza,
                analisa e transforma o resultado em plano jurídico revisável.
              </h2>
            </div>
            {canUseEntry && (
              <Link to="/entrada" className="ejc-ai-dashboard__full-link">
                Abrir em tela cheia <ArrowUpRight aria-hidden="true" />
              </Link>
            )}
          </div>

          {canUseLegal ? (
            <EntradaInteligente embedded />
          ) : canUseEntry ? (
            <div className="ejc-reference-empty">
              <p>
                Use a Entrada Única para cadastro manual de cliente e caso, sem
                depender de IA.
              </p>
              <Link to="/entrada" className="btn-primary mt-3 inline-flex">
                Abrir Entrada Única
              </Link>
            </div>
          ) : (
            <div className="ejc-reference-empty">
              A Entrada Única está disponível apenas aos perfis autorizados.
            </div>
          )}
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
      </div>

      <footer className="ejc-ai-dashboard__footer">
        <span>
          © {new Date().getFullYear()} {officeBranding.officeName}
        </span>
        <span>
          <AlertTriangle aria-hidden="true" /> Conteúdo jurídico de IA exige
          revisão humana.
        </span>
        <span className="inline-flex items-center gap-2">
          {whatsappUrl ? (
            <a
              href={whatsappUrl}
              target="_blank"
              rel="noreferrer"
              aria-label="Abrir WhatsApp do escritório"
            >
              <MessageCircle aria-hidden="true" />
            </a>
          ) : null}
          {mailtoUrl ? (
            <a href={mailtoUrl} aria-label="Enviar e-mail ao escritório">
              <Mail aria-hidden="true" />
            </a>
          ) : null}
        </span>
      </footer>
    </div>
  );
}
