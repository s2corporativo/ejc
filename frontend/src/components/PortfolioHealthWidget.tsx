import { useEffect, useMemo, useState } from "react";
import { Activity, AlertTriangle, Briefcase, RefreshCw } from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from "../lib/api";
import { toast } from "./Toast";
import { Badge, Button, EmptyState, Modal, Spinner } from "./UI";

type HealthLevel = "healthy" | "attention" | "risk" | "critical";

type PortfolioCase = {
  id: string;
  numero_interno?: string | null;
  titulo: string;
  area: string;
  prioridade: string;
  risco?: string | null;
  advogado_responsavel?: string | null;
  last_activity_at: string;
  inactive_days: number;
  pending_tasks: number;
  overdue_deadlines: number;
  deadlines_next_3_days: number;
  overdue_client_requests: number;
  active_processes: number;
  unreviewed_ai_documents: number;
  documents_in_review: number;
  health_score: number;
  health_level: HealthLevel;
  route: string;
};

type PortfolioResponse = {
  scope: "office" | "assigned";
  stale_days: number;
  returned: number;
  totals_in_result: Record<HealthLevel, number>;
  items: PortfolioCase[];
};

const LEVEL_LABELS: Record<HealthLevel, string> = {
  critical: "Crítico",
  risk: "Em risco",
  attention: "Atenção",
  healthy: "Saudável",
};

const LEVEL_TONE: Record<HealthLevel, "red" | "amber" | "green" | "slate"> = {
  critical: "red",
  risk: "red",
  attention: "amber",
  healthy: "green",
};

export function principalMotivo(item: PortfolioCase): string {
  if (item.overdue_deadlines > 0) {
    return `${item.overdue_deadlines} prazo(s) vencido(s)`;
  }
  if (item.deadlines_next_3_days > 0) {
    return `${item.deadlines_next_3_days} prazo(s) nos próximos 3 dias`;
  }
  if (item.overdue_client_requests > 0) {
    return `${item.overdue_client_requests} retorno(s) ao cliente vencido(s)`;
  }
  if (item.unreviewed_ai_documents > 0) {
    return `${item.unreviewed_ai_documents} documento(s) de IA sem revisão`;
  }
  if (item.pending_tasks === 0) {
    return "Caso ativo sem próxima tarefa";
  }
  if (item.inactive_days > 0) {
    return `${item.inactive_days} dia(s) sem atividade relevante`;
  }
  return "Sem pendência crítica automática";
}

export function ordenarCarteira(items: PortfolioCase[]): PortfolioCase[] {
  return [...items].sort((a, b) => {
    if (a.health_score !== b.health_score) return a.health_score - b.health_score;
    if (a.overdue_deadlines !== b.overdue_deadlines) {
      return b.overdue_deadlines - a.overdue_deadlines;
    }
    return b.inactive_days - a.inactive_days;
  });
}

function detalheErro(error: unknown): string {
  const detail = (
    error as { response?: { data?: { detail?: unknown } } }
  )?.response?.data?.detail;
  return typeof detail === "string" && detail
    ? detail
    : "Não foi possível carregar a saúde operacional da carteira.";
}

export default function PortfolioHealthWidget() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<PortfolioResponse | null>(null);

  const items = useMemo(() => ordenarCarteira(data?.items || []), [data]);
  const riskCount = useMemo(
    () =>
      items.filter((item) =>
        ["critical", "risk"].includes(item.health_level),
      ).length,
    [items],
  );

  const carregar = async () => {
    setLoading(true);
    try {
      const response = await api.get("/dashboard/operational-health", {
        params: { stale_days: 30, limit: 50 },
      });
      setData(response.data as PortfolioResponse);
    } catch (error) {
      toast.error(detalheErro(error));
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) void carregar();
  }, [open]);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm font-semibold text-slate-800 shadow-md transition hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-400 focus:ring-offset-2"
        aria-label="Abrir saúde operacional da carteira"
      >
        <Activity className="h-4 w-4 text-primary-700" />
        Casos em atenção
      </button>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Saúde operacional da carteira"
        size="xl"
      >
        {loading ? (
          <Spinner />
        ) : !data ? (
          <EmptyState
            icon={AlertTriangle}
            title="Diagnóstico indisponível"
            message="Nenhuma alteração foi feita. Tente atualizar novamente."
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
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div>
                <p className="font-semibold text-slate-950">
                  {riskCount} caso(s) em risco ou situação crítica
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  {`Escopo: ${data.scope === "office" ? "escritório" : "casos atribuídos"} · inatividade considerada após ${data.stale_days} dias`}
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

            {!items.length ? (
              <EmptyState
                icon={Briefcase}
                title="Nenhum caso ativo no escopo"
                message="O painel não encontrou casos que possam ser avaliados para este usuário."
              />
            ) : (
              <div className="space-y-3">
                {items.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => {
                      setOpen(false);
                      navigate(item.route);
                    }}
                    className="block w-full rounded-xl border border-slate-200 p-4 text-left transition hover:border-primary-200 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-400"
                  >
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge tone={LEVEL_TONE[item.health_level]}>
                            {LEVEL_LABELS[item.health_level]} · {item.health_score}
                          </Badge>
                          <span className="text-xs text-slate-500">
                            {item.numero_interno || item.id}
                          </span>
                        </div>
                        <p className="mt-2 truncate font-semibold text-slate-950">
                          {item.titulo}
                        </p>
                        <p className="mt-1 text-sm text-slate-600">
                          {principalMotivo(item)}
                        </p>
                      </div>
                      <div className="text-right text-xs text-slate-500">
                        <p>{item.area}</p>
                        <p className="mt-1">
                          {item.advogado_responsavel ||
                            "Sem responsável principal"}
                        </p>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                      <span>Tarefas: {item.pending_tasks}</span>
                      <span>Prazos vencidos: {item.overdue_deadlines}</span>
                      <span>Próximos 3 dias: {item.deadlines_next_3_days}</span>
                      <span>Inatividade: {item.inactive_days} dia(s)</span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
