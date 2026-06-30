import { useEffect, useState } from "react";
import {
  DollarSign,
  Clock,
  CheckCircle,
  AlertCircle,
  TrendingUp,
} from "lucide-react";
import api from "../../lib/api";

const ST: Record<string, [string, string, string]> = {
  pago: ["Pago", "text-emerald-600", "bg-emerald-50"],
  pendente: ["Em aberto", "text-amber-600", "bg-amber-50"],
  atrasado: ["Em atraso", "text-red-600", "bg-red-50"],
  cancelado: ["Cancelado", "text-slate-400", "bg-slate-50"],
};

export default function PortalFinanceiro() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get("/portal/financeiro")
      .then((r) => setRows(r.data?.data ?? r.data ?? []))
      .finally(() => setLoading(false));
  }, []);

  const total = rows.reduce((s, r) => s + (r.valor ?? 0), 0);
  const pago = rows
    .filter((r) => r.status === "pago")
    .reduce((s, r) => s + (r.valor ?? 0), 0);
  const pendente = rows
    .filter((r) => r.status === "pendente")
    .reduce((s, r) => s + (r.valor ?? 0), 0);
  const atrasado = rows
    .filter((r) => r.status === "atrasado")
    .reduce((s, r) => s + (r.valor ?? 0), 0);

  const fmt = (v: number) =>
    v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  const kpis = [
    {
      label: "Total honorários",
      value: fmt(total),
      icon: TrendingUp,
      color: "text-blue-500",
      bg: "bg-blue-50",
    },
    {
      label: "Recebido",
      value: fmt(pago),
      icon: CheckCircle,
      color: "text-emerald-500",
      bg: "bg-emerald-50",
    },
    {
      label: "Em aberto",
      value: fmt(pendente),
      icon: Clock,
      color: "text-amber-500",
      bg: "bg-amber-50",
    },
    {
      label: "Em atraso",
      value: fmt(atrasado),
      icon: AlertCircle,
      color: "text-red-500",
      bg: "bg-red-50",
    },
  ];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-slate-800">Financeiro</h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Seus honorários e pagamentos
        </p>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {kpis.map((k) => (
          <div
            key={k.label}
            className="bg-white rounded-xl border border-slate-200 p-4"
          >
            <div
              className={`w-8 h-8 rounded-lg ${k.bg} flex items-center justify-center mb-2`}
            >
              <k.icon className={`w-4 h-4 ${k.color}`} />
            </div>
            <p className="text-xs text-slate-500">{k.label}</p>
            <p className="text-base font-bold text-slate-800 mt-0.5">
              {k.value}
            </p>
          </div>
        ))}
      </div>

      {/* Alert for overdue */}
      {atrasado > 0 && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-red-700">
              Pagamento em atraso
            </p>
            <p className="text-xs text-red-600 mt-0.5">
              Você possui {fmt(atrasado)} em honorários vencidos. Entre em
              contato com o escritório para regularizar.
            </p>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-700 flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-slate-400" /> Lançamentos
          </h2>
        </div>
        {loading ? (
          <div className="p-10 text-center text-slate-400 text-sm">
            Carregando...
          </div>
        ) : rows.length === 0 ? (
          <div className="p-10 text-center text-slate-400 text-sm">
            Nenhum lançamento
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {rows.map((f, i) => {
              const [label, cor, bgcor] = ST[f.status] ?? [
                f.status,
                "text-slate-500",
                "bg-slate-50",
              ];
              return (
                <div
                  key={i}
                  className="px-5 py-4 flex items-center justify-between gap-4"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {f.descricao}
                    </p>
                    {f.vencimento && (
                      <p className="text-xs text-slate-400 mt-0.5">
                        Venc.{" "}
                        {new Date(f.vencimento + "T12:00").toLocaleDateString(
                          "pt-BR",
                        )}
                      </p>
                    )}
                    {f.tipo && (
                      <p className="text-xs text-slate-400 capitalize">
                        {f.tipo.replace(/_/g, " ")}
                      </p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-bold text-slate-800">
                      {fmt(f.valor ?? 0)}
                    </p>
                    <span
                      className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full mt-1 ${cor} ${bgcor}`}
                    >
                      {label}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
