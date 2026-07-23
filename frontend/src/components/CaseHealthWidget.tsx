import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Clock3,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { Badge, Button, EmptyState, Modal, Spinner } from "./UI";

type HealthLevel = "healthy" | "attention" | "risk" | "critical";

type HealthIndicator = {
  code: string;
  severity: "low" | "medium" | "high" | "critical";
  message: string;
  recommended_action: string;
  count?: number;
};

type CaseHealth = {
  score: number;
  level: HealthLevel;
  last_activity_at: string;
  inactive_days: number;
  metrics: Record<string, number>;
  indicators: HealthIndicator[];
};

type TimelineItem = {
  id: string;
  kind: string;
  title: string;
  description?: string | null;
  status?: string | null;
  source: string;
  occurred_at: string;
};

type TimelineResponse = {
  items: TimelineItem[];
  truncated: boolean;
  saturated_sources: string[];
};

const LEVEL_LABELS: Record<HealthLevel, string> = {
  healthy: "Saudável",
  attention: "Atenção",
  risk: "Em risco",
  critical: "Crítico",
};

const SEVERITY_LABELS: Record<HealthIndicator["severity"], string> = {
  low: "Informativo",
  medium: "Atenção",
  high: "Alto",
  critical: "Crítico",
};

function detalheErro(error: unknown): string {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail;
  return typeof detail === "string" && detail
    ? detail
    : "Não foi possível carregar a saúde operacional do caso.";
}

export function formatarDataEvento(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Data não informada";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(parsed);
}

export function ordenarIndicadores(
  indicators: HealthIndicator[],
): HealthIndicator[] {
  const rank: Record<HealthIndicator["severity"], number> = {
    critical: 4,
    high: 3,
    medium: 2,
    low: 1,
  };
  return [...indicators].sort(
    (a, b) => rank[b.severity] - rank[a.severity],
  );
}

export default function CaseHealthWidget({ caseId }: { caseId: string }) {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [health, setHealth] = useState<CaseHealth | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);

  const indicators = useMemo(
    () => ordenarIndicadores(health?.indicators || []),
    [health],
  );

  const carregar = async () => {
    setLoading(true);
    try {
      const [healthResponse, timelineResponse] = await Promise.all([
        api.get(`/cases/${caseId}/operational-health`),
        api.get(`/cases/${caseId}/timeline`, {
          params: { page: 1, per_page: 15 },
        }),
      ]);
      setHealth(healthResponse.data as CaseHealth);
      setTimeline(timelineResponse.data as TimelineResponse);
    } catch (error) {
      toast.error(detalheErro(error));
      setHealth(null);
      setTimeline(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void carregar();
  }, [open, caseId]);

  const level = health?.level || "attention";
  const HealthIcon =
    level === "healthy"
      ? CheckCircle2
      : level === "critical"
        ? ShieldAlert
        : AlertTriangle;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-48 z-30 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 shadow-md transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2"
        aria-label="Abrir saúde operacional do caso"
      >
        <Activity className="h-4 w-4 text-primary-700" />
        Saúde do caso
      </button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Saúde operacional e linha do tempo"
      >
        {loading ? (
          <div className="grid min-h-64 place-items-center">
            <Spinner />
          </div>
        ) : !health ? (
          <EmptyState
            icon={AlertTriangle}
            title="Diagnóstico indisponível"
            message="Tente atualizar novamente. Nenhuma alteração foi feita no caso."
            action={
              <Button
                variant="secondary"
                onClick={() => void carregar()}
                icon={<RefreshCw className="h-4 w-4" />}
              >
                Atualizar
              </Button>
            }
          />
        ) : (
          <div className="space-y-6">
            <section className="grid gap-4 sm:grid-cols-[160px_1fr]">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-5 text-center">
                <HealthIcon className="mx-auto h-7 w-7 text-primary-700" />
                <div className="mt-2 text-3xl font-bold text-slate-950">
                  {health.score}
                </div>
                <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  {LEVEL_LABELS[level]}
                </div>
              </div>
              <div className="rounded-xl border border-slate-200 p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h3 className="font-semibold text-slate-950">
                      Situação operacional
                    </h3>
                    <p className="mt-1 text-sm text-slate-500">
                      {`Última atividade: ${formatarDataEvento(health.last_activity_at)} · ${health.inactive_days} dia(s) de inatividade`}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => void carregar()}
                    icon={<RefreshCw className="h-4 w-4" />}
                  >
                    Atualizar
                  </Button>
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <Badge>
                    {`Processos ativos: ${health.metrics.active_processes || 0}`}
                  </Badge>
                  <Badge>
                    {`Tarefas pendentes: ${health.metrics.pending_tasks || 0}`}
                  </Badge>
                  <Badge>
                    {`Prazos vencidos: ${health.metrics.overdue_deadlines || 0}`}
                  </Badge>
                  <Badge>
                    {`Retornos vencidos: ${health.metrics.overdue_client_requests || 0}`}
                  </Badge>
                </div>
              </div>
            </section>

            <section>
              <h3 className="font-semibold text-slate-950">
                Pendências e ações
              </h3>
              {indicators.length === 0 ? (
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                  Nenhuma pendência automática foi identificada pelos critérios
                  atuais.
                </div>
              ) : (
                <div className="mt-3 space-y-3">
                  {indicators.map((indicator) => (
                    <div
                      key={indicator.code}
                      className="rounded-xl border border-slate-200 p-4"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge>{SEVERITY_LABELS[indicator.severity]}</Badge>
                        {typeof indicator.count === "number" && (
                          <span className="text-xs text-slate-500">
                            {indicator.count} ocorrência(s)
                          </span>
                        )}
                      </div>
                      <p className="mt-2 text-sm font-medium text-slate-900">
                        {indicator.message}
                      </p>
                      <p className="mt-1 text-sm text-slate-600">
                        Próxima ação: {indicator.recommended_action}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section>
              <div className="flex items-center justify-between gap-3">
                <h3 className="font-semibold text-slate-950">
                  Eventos recentes
                </h3>
                {timeline?.truncated && (
                  <span className="text-xs text-amber-700">
                    Visualização parcial; consulte a linha do tempo completa.
                  </span>
                )}
              </div>
              {!timeline?.items?.length ? (
                <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
                  Nenhum evento foi localizado para este caso.
                </div>
              ) : (
                <ol className="mt-3 space-y-3">
                  {timeline.items.map((item) => (
                    <li
                      key={item.id}
                      className="flex gap-3 rounded-xl border border-slate-200 p-4"
                    >
                      <span className="mt-0.5 rounded-lg bg-slate-100 p-2">
                        <Clock3 className="h-4 w-4 text-slate-600" />
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-slate-900">
                            {item.title}
                          </p>
                          <time className="text-xs text-slate-500">
                            {formatarDataEvento(item.occurred_at)}
                          </time>
                        </div>
                        {item.description && (
                          <p className="mt-1 line-clamp-3 text-sm text-slate-600">
                            {item.description}
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                          <span>Origem: {item.source}</span>
                          {item.status && <span>Status: {item.status}</span>}
                        </div>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </div>
        )}
      </Modal>
    </>
  );
}
