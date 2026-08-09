import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  CheckCircle,
  Clock,
  DollarSign,
  Receipt,
  TrendingUp,
} from "lucide-react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import {
  ErrorState,
  Modal,
  Spinner,
  fmtDate,
  fmtMoney,
} from "../../components/UI";

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

  const original = (r: any) => Number(r.valor_original ?? r.valor ?? 0);
  const pagoLinha = (r: any) =>
    Number(r.valor_pago ?? (r.status === "pago" ? original(r) : 0));
  const saldo = (r: any) =>
    Number(r.saldo_aberto ?? (r.status === "pago" ? 0 : original(r)));

  const total = rows
    .filter((r) => r.status !== "cancelado")
    .reduce((s, r) => s + original(r), 0);
  const pago = rows.reduce((s, r) => s + pagoLinha(r), 0);
  const pendente = rows
    .filter((r) => r.status === "pendente")
    .reduce((s, r) => s + saldo(r), 0);
  const atrasado = rows
    .filter((r) => r.status === "atrasado")
    .reduce((s, r) => s + saldo(r), 0);

  const kpis = [
    {
      label: "Total contratado",
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
      label: "Saldo em aberto",
      value: fmtMoney(pendente),
      icon: Clock,
      color: "text-warn-500",
      bg: "bg-warn-50",
    },
    {
      label: "Saldo em atraso",
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
          Honorários, pagamentos realizados e saldo atual
        </p>
      </div>

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

      {atrasado > 0 && (
        <div className="bg-danger-50 border border-danger-200 rounded-xl p-4 flex items-start gap-3">
          <AlertCircle className="w-5 h-5 text-danger-500 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-danger-700">
              Saldo em atraso
            </p>
            <p className="text-xs text-danger-600 mt-0.5">
              Há {fmtMoney(atrasado)} de saldo vencido. Pagamentos parciais já
              registrados foram abatidos deste valor.
            </p>
          </div>
        </div>
      )}

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
            Nenhum lançamento financeiro.
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {rows.map((f) => {
              const [label, cor, bgcor] = ST[f.status] ?? [
                f.status,
                "text-slate-500",
                "bg-slate-50",
              ];
              const originalLinha = original(f);
              const pagoAtual = pagoLinha(f);
              const saldoAtual = saldo(f);
              return (
                <div
                  key={f.id ?? `${f.descricao}-${f.vencimento}`}
                  className="px-5 py-4 flex items-center justify-between gap-4"
                >
                  <div className="min-w-0">
                    <p className="text-sm font-medium text-slate-800 truncate">
                      {f.descricao}
                    </p>
                    {f.vencimento && (
                      <p className="text-xs text-slate-400 mt-0.5">
                        Venc. {fmtDate(f.vencimento)}
                      </p>
                    )}
                    {pagoAtual > 0 && saldoAtual > 0 && (
                      <p className="text-xs text-success-600 mt-1">
                        Já pago: {fmtMoney(pagoAtual)} · saldo:{" "}
                        {fmtMoney(saldoAtual)}
                      </p>
                    )}
                  </div>
                  <div className="text-right flex-shrink-0">
                    <p className="text-sm font-bold text-slate-800">
                      {saldoAtual > 0
                        ? fmtMoney(saldoAtual)
                        : fmtMoney(originalLinha)}
                    </p>
                    {saldoAtual > 0 && pagoAtual > 0 && (
                      <p className="text-[10px] text-slate-400">
                        de {fmtMoney(originalLinha)}
                      </p>
                    )}
                    <span
                      className={`inline-block text-xs font-medium px-2 py-0.5 rounded-full mt-1 ${cor} ${bgcor}`}
                    >
                      {label}
                    </span>
                    {pagoAtual > 0 && (
                      <button
                        onClick={() => setRecibo(f)}
                        className="block ml-auto mt-1 text-xs text-success-600 hover:underline inline-flex items-center gap-1"
                      >
                        <Receipt className="w-3 h-3" /> Ver pagamentos
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <Modal
        open={recibo !== null}
        onClose={() => setRecibo(null)}
        title="Resumo de pagamento"
        size="sm"
      >
        {recibo && (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-success-600">
              <CheckCircle className="w-5 h-5 flex-shrink-0" />
              <p className="text-sm font-semibold">Pagamentos registrados</p>
            </div>
            <div className="text-sm space-y-2">
              <div>
                <p className="text-xs text-slate-400">Descrição</p>
                <p className="text-slate-800 font-medium">{recibo.descricao}</p>
              </div>
              <div className="grid grid-cols-3 gap-2">
                <div>
                  <p className="text-xs text-slate-400">Original</p>
                  <p className="text-slate-800 font-semibold">
                    {fmtMoney(original(recibo))}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Pago</p>
                  <p className="text-success-700 font-semibold">
                    {fmtMoney(pagoLinha(recibo))}
                  </p>
                </div>
                <div>
                  <p className="text-xs text-slate-400">Saldo</p>
                  <p className="text-slate-800 font-semibold">
                    {fmtMoney(saldo(recibo))}
                  </p>
                </div>
              </div>
              {recibo.ultima_baixa && (
                <div>
                  <p className="text-xs text-slate-400">Última baixa</p>
                  <p className="text-slate-800">
                    {fmtDate(recibo.ultima_baixa)}
                  </p>
                </div>
              )}
            </div>
            <p className="text-xs text-slate-400">
              Este resumo reflete as baixas registradas no escritório. Para
              recibo fiscal/formal, solicite pelas Mensagens.
            </p>
          </div>
        )}
      </Modal>
    </div>
  );
}
