import { useState, useEffect, useCallback } from "react";
import { Plus, Check, CreditCard, Trash2, X } from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";

interface Withdrawal {
  id: string;
  partner_id: string;
  gross_value: number;
  case_expenses: number;
  net_value: number;
  partner_share: number;
  description?: string;
  period_reference?: string;
  status: string;
  approved_at?: string;
  paid_at?: string;
  created_at: string;
}

const STATUS_COLOR: Record<string, string> = {
  pendente: "bg-yellow-100 text-yellow-700",
  aprovado: "bg-blue-100 text-blue-700",
  pago: "bg-green-100 text-green-700",
  cancelado: "bg-red-100 text-red-700",
};

function fmtR$(v: number) {
  return (
    v?.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }) ?? "—"
  );
}
function fmtDate(d?: string) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("pt-BR");
}

const EMPTY = {
  gross_value: "",
  case_expenses: "0",
  description: "",
  period_reference: "",
};

export default function PartnerWithdrawals() {
  const { user } = useAuth();
  const [data, setData] = useState<Withdrawal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...EMPTY });
  const isPrivileged = ["superadmin", "socio"].includes(user?.role ?? "");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get("/v1/partner-withdrawals");
      setData(res.data.data ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save() {
    await api.post("/v1/partner-withdrawals", {
      gross_value: parseFloat(form.gross_value),
      case_expenses: parseFloat(form.case_expenses || "0"),
      description: form.description || undefined,
      period_reference: form.period_reference || undefined,
    });
    setShowForm(false);
    setForm({ ...EMPTY });
    load();
  }

  async function approve(id: string) {
    await api.patch(`/v1/partner-withdrawals/${id}/approve`);
    load();
  }

  async function pay(id: string) {
    await api.patch(`/v1/partner-withdrawals/${id}/pay`);
    load();
  }

  async function remove(id: string) {
    if (!window.confirm("Excluir solicitação?")) return;
    await api.delete(`/v1/partner-withdrawals/${id}`);
    load();
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="eyebrow mb-2">Financeiro</div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950">
            Saques de Sócios
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Solicitações de retirada com aprovação
          </p>
        </div>
        {isPrivileged && (
          <button
            onClick={() => setShowForm(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
          >
            <Plus className="w-4 h-4" /> Nova Solicitação
          </button>
        )}
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-400">Carregando...</div>
      ) : data.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          Nenhuma solicitação encontrada
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Período</th>
                <th className="px-4 py-3 text-right">Bruto</th>
                <th className="px-4 py-3 text-right">Despesas</th>
                <th className="px-4 py-3 text-right">Líquido</th>
                <th className="px-4 py-3 text-right">Cota (50%)</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Data</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((w) => (
                <tr key={w.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-700">
                    {w.period_reference || "—"}
                  </td>
                  <td className="px-4 py-3 text-right text-slate-600">
                    {fmtR$(w.gross_value)}
                  </td>
                  <td className="px-4 py-3 text-right text-red-500">
                    {fmtR$(w.case_expenses)}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-slate-800">
                    {fmtR$(w.net_value)}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-blue-700">
                    {fmtR$(w.partner_share)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLOR[w.status] ?? "bg-slate-100 text-slate-500"}`}
                    >
                      {w.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-400">
                    {fmtDate(w.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    {isPrivileged && (
                      <div className="flex gap-1">
                        {w.status === "pendente" && (
                          <button
                            onClick={() => approve(w.id)}
                            title="Aprovar"
                            className="p-1.5 rounded text-slate-400 hover:text-blue-600 hover:bg-blue-50"
                          >
                            <Check className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {w.status === "aprovado" && (
                          <button
                            onClick={() => pay(w.id)}
                            title="Marcar como pago"
                            className="p-1.5 rounded text-slate-400 hover:text-green-600 hover:bg-green-50"
                          >
                            <CreditCard className="w-3.5 h-3.5" />
                          </button>
                        )}
                        {w.status === "pendente" && (
                          <button
                            onClick={() => remove(w.id)}
                            title="Excluir"
                            className="p-1.5 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <h2 className="font-semibold text-slate-800">
                Nova Solicitação de Saque
              </h2>
              <button
                onClick={() => setShowForm(false)}
                className="p-1 rounded hover:bg-slate-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Valor Bruto (R$)
                  </label>
                  <input
                    type="number"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.gross_value}
                    onChange={(e) =>
                      setForm({ ...form, gross_value: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Despesas do Caso (R$)
                  </label>
                  <input
                    type="number"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.case_expenses}
                    onChange={(e) =>
                      setForm({ ...form, case_expenses: e.target.value })
                    }
                  />
                </div>
              </div>
              {form.gross_value && (
                <div className="bg-blue-50 rounded-lg p-3 text-sm text-blue-800">
                  Cota estimada (50%):{" "}
                  <strong>
                    {(
                      ((parseFloat(form.gross_value) || 0) -
                        (parseFloat(form.case_expenses) || 0)) *
                      0.5
                    ).toLocaleString("pt-BR", {
                      style: "currency",
                      currency: "BRL",
                    })}
                  </strong>
                </div>
              )}
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Período de referência (ex: 2026-06)
                </label>
                <input
                  type="text"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  placeholder="AAAA-MM"
                  value={form.period_reference}
                  onChange={(e) =>
                    setForm({ ...form, period_reference: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Descrição
                </label>
                <textarea
                  rows={2}
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm resize-none"
                  value={form.description}
                  onChange={(e) =>
                    setForm({ ...form, description: e.target.value })
                  }
                />
              </div>
            </div>
            <div className="p-5 border-t border-slate-100 flex gap-3 justify-end">
              <button
                onClick={() => setShowForm(false)}
                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancelar
              </button>
              <button
                onClick={save}
                disabled={!form.gross_value}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                Solicitar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
