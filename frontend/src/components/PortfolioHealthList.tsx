import { Briefcase } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Badge, EmptyState } from "./UI";
import {
  PORTFOLIO_LEVEL_LABELS,
  PORTFOLIO_LEVEL_TONE,
  type PortfolioCase,
  ordenarCarteira,
  principalMotivo,
} from "./portfolioHealthModel";

export default function PortfolioHealthList({
  items,
  onNavigate,
}: {
  items: PortfolioCase[];
  onNavigate?: () => void;
}) {
  const navigate = useNavigate();
  const ordered = ordenarCarteira(items);

  if (!ordered.length) {
    return (
      <EmptyState
        icon={Briefcase}
        title="Nenhum caso ativo no escopo"
        message="O painel não encontrou casos que possam ser avaliados para este usuário."
      />
    );
  }

  return (
    <div className="space-y-3">
      {ordered.map((item) => (
        <button
          key={item.id}
          type="button"
          onClick={() => {
            onNavigate?.();
            navigate(item.route);
          }}
          className="block w-full rounded-xl border border-slate-200 p-4 text-left transition hover:border-primary-200 hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-400"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={PORTFOLIO_LEVEL_TONE[item.level]}>
                  {PORTFOLIO_LEVEL_LABELS[item.level]} · {item.score}
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
              <p className="mt-1 text-xs text-primary-700">
                Próxima ação: {item.next_recommended_action}
              </p>
            </div>
            <div className="text-right text-xs text-slate-500">
              <p>{item.area || "Área não informada"}</p>
              <p className="mt-1">
                {item.advogado_responsavel || "Sem responsável principal"}
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
            <span>Ações abertas: {item.metrics.actionable_tasks || 0}</span>
            <span>Prazos vencidos: {item.metrics.overdue_deadlines || 0}</span>
            <span>
              Próximos 3 dias: {item.metrics.deadlines_next_3_days || 0}
            </span>
            <span>Inatividade: {item.inactive_days} dia(s)</span>
          </div>
        </button>
      ))}
    </div>
  );
}
