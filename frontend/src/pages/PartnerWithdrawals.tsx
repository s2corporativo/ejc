import { useState, useEffect, useCallback } from "react";
import { Plus, Check, CreditCard, Trash2 } from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import { Modal, PageHeader, fmtMoney, fmtDate } from "../components/UI";
import { toast } from "../components/Toast";

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

// Status reais gravados pelo backend (pt-BR): pendente/aprovado/pago/rejeitado
const STATUS_COLOR: Record<string, string> = {
  pendente: "bg-yellow-100 text-yellow-700",
  aprovado: "bg-primary-100 text-primary-700",
  pago: "bg-green-100 text-green-700",
  rejeitado: "bg-danger-100 text-danger-700",
};
const STATUS_LABEL: Record<string, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  pago: "Pago",
  rejeitado: "Rejeitado",
};

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
    try {
      await api.delete(`/v1/partner-withdrawals/${id}`);
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao excluir solicitação");
    }
  }

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <PageHeader
        eyebrow="Financeiro"
        title="Saques de Sócios"
        subtitle="Solicitações de retirada com aprovação"
        actions={
          isPrivileged ? (
            <button onClick={() => setShowForm(true)} className="btn-primary">
              <Plus className="w-4 h-4" /> Nova Solicitação
            </button>
          ) : undefined
        }
      />

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
                    {fmtMoney(w.gross_value)}
                  </td>
                  <td className="px-4 py-3 text-right text-danger-500">
                    {fmtMoney(w.case_expenses)}
                  </td>
                  <td className="px-4 py-3 text-right font-medium text-slate-800">
                    {fmtMoney(w.net_value)}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-primary-700">
                    {fmtMoney(w.partner_share)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLOR[w.status] ?? "bg-slate-100 text-slate-500"}`}
                    >
                      {STATUS_LABEL[w.status] ?? w.status}
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
                            className="p-1.5 rounded text-slate-400 hover:text-primary-600 hover:bg-primary-50"
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
                            className="p-1.5 rounded text-slate-400 hover:text-danger-600 hover:bg-danger-50"
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

      <Modal
        open={showForm}
        onClose={() => setShowForm(false)}
        title="Nova Solicitação de Saque"
      >
        <div className="space-y-4">
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
            <div className="bg-primary-50 rounded-lg p-3 text-sm text-primary-800">
              Cota estimada (50%):{" "}
              <strong>
                {fmtMoney(
                  ((parseFloat(form.gross_value) || 0) -
                    (parseFloat(form.case_expenses) || 0)) *
                    0.5,
                )}
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
          <div className="flex gap-3 justify-end pt-2 border-t border-slate-100 mt-2">
            <button onClick={() => setShowForm(false)} className="btn-ghost">
              Cancelar
            </button>
            <button
              onClick={save}
              disabled={!form.gross_value}
              className="btn-primary"
            >
              Solicitar
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
