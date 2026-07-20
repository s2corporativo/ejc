import {
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  ShieldAlert,
} from "lucide-react";
import { Badge, Button } from "./UI";
import {
  type CaseHealth,
  LEVEL_LABELS,
  formatarDataEvento,
} from "./caseHealthModel";

export default function CaseHealthSummary({
  health,
  onReload,
}: {
  health: CaseHealth;
  onReload: () => void;
}) {
  const level = health.level;
  const HealthIcon =
    level === "healthy"
      ? CheckCircle2
      : level === "critical"
        ? ShieldAlert
        : AlertTriangle;

  return (
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
            <h3 className="font-semibold text-slate-950">Situação operacional</h3>
            <p className="mt-1 text-sm text-slate-500">
              Última atividade: {formatarDataEvento(health.last_activity_at)} ·{" "}
              {health.inactive_days} dia(s) de inatividade
            </p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onReload}
            icon={<RefreshCw className="h-4 w-4" />}
          >
            Atualizar
          </Button>
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <Badge>Processos ativos: {health.metrics.active_processes || 0}</Badge>
          <Badge>Ações abertas: {health.metrics.actionable_tasks || 0}</Badge>
          <Badge>Prazos vencidos: {health.metrics.overdue_deadlines || 0}</Badge>
          <Badge>
            Retornos vencidos: {health.metrics.overdue_client_requests || 0}
          </Badge>
        </div>

        <div className="mt-4 rounded-xl border border-primary-100 bg-primary-50 p-4">
          <p className="text-xs font-semibold uppercase tracking-wide text-primary-700">
            Próxima ação recomendada
          </p>
          <p className="mt-1 text-sm text-primary-900">
            {health.next_recommended_action}
          </p>
        </div>
      </div>
    </section>
  );
}
