import { useCallback, useEffect, useState } from "react";
import {
  DollarSign,
  Clock,
  CheckCircle,
  AlertCircle,
  Receipt,
  TrendingUp,
} from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { ErrorState, Modal, Spinner, fmtDate, fmtMoney } from "../../components/UI";

const ST: Record<string, [string, string, string]> = {
  pago: ["Pago", "text-success-600", "bg-success-50"],
  pendente: ["Em aberto", "text-warn-600", "bg-warn-50"],
  atrasado: ["Em atraso", "text-danger-600", "bg-danger-50"],
  cancelado: ["Cancelado", "text-slate-400", "bg-slate-50"],
};

export default function PortalFinanceiro() {
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [recibo, setRecibo] = useState<any>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(false);
    api
      .get("/portal/financeiro")
      .then((r) => setRows(asList(r.data)))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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

  const kpis = [
    {
      label: "Total honorários",
      value: fmtMoney(total),
      icon: TrendingUp,
      color: "text-primary-500",
      bg: "bg-primary-50",
    },
    {
      label: "Recebido",
      value: fmtMoney(pago),
      icon: CheckCircle,
      color: "text-success-500",
      bg: "bg-success-50",
    },
    {
      label: "Em aberto",
      value: fmtMoney(pendente),
      icon: Clock,
      color: "text-warn-500",
      bg: "bg-warn-50",
    },
    {
      label: "Em atraso",
      value: fmtMoney(atrasado),
      icon: AlertCircle,
      color: "text-danger-500",
      bg: "bg-danger-50",
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
          <div key={k.label} className="card p-4">
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
        <div className="bg-danger-50 border border-danger-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-danger-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-danger-700">
              Pagamento em atraso
            </p>
            <p className="text-xs text-danger-600 mt-0.5">
              Você possui {fmtMoney(atrasado)} em honorários vencidos. Entre em
              contato com o escritório para regularizar.
            </p>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-700 flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-slate-400" /> Lançamentos
          </h2>
        </div>
        {loading ? (
          <Spinner />
        ) : error ? (
          <ErrorState
            message="Não foi possível carregar seus lançamentos financeiros."
            onRetry={load}
          />
        ) : rows.length === 0 ? (
          <div className="p-10 text-center text-slate-400 text-sm">
            Nenhum lançamento — você está em dia com o escritório.
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
                      {fmtMoney(f.valor ?? 0)}
                    </p>
                    <span
                      className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full mt-1 ${cor} ${bgcor}`}
                    >
                      {label}
                    </span>
                    {f.status === "pago" && (
                      <button
                        onClick={() => setRecibo(f)}
                        className="block ml-auto mt-1 text-xs text-success-600 hover:underline inline-flex items-center gap-1"
                      >
                        <Receipt className="w-3 h-3" /> Ver confirmação
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Confirmação de pagamento — apenas os dados que o escritório registrou */}
      <Modal
        open={recibo !== null}
        onClose={() => setRecibo(null)}
        title="Confirmação de pagamento"
        size="sm"
      >
        {recibo && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-success-600">
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
              <p className="text-sm font-semibold">Pagamento registrado</p>
            </div>
            <div className="text-sm space-y-2">
              <div>
                <p className="text-xs text-slate-400">Descrição</p>
                <p className="text-slate-800 font-medium">{recibo.descricao}</p>
              </div>
              <div>
                <p className="text-xs text-slate-400">Valor</p>
                <p className="text-slate-800 font-bold">
                  {fmtMoney(recibo.valor ?? 0)}
                </p>
              </div>
              {recibo.vencimento && (
                <div>
                  <p className="text-xs text-slate-400">Vencimento</p>
                  <p className="text-slate-800">{fmtDate(recibo.vencimento)}</p>
                </div>
              )}
            </div>
            <p className="text-xs text-slate-400">
              Confirmação emitida pelo Portal do Cliente com base nos registros
              do escritório. Para um recibo formal, solicite pelas Mensagens.
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
