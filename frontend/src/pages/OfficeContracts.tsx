import { useState, useEffect, useCallback } from "react";
import {
  Plus,
  FileText,
  AlertTriangle,
  CheckCircle,
  Clock,
  Trash2,
  Edit2,
  X,
} from "lucide-react";
import api from "../lib/api";

interface Contract {
  id: string;
  title: string;
  counterparty: string;
  contract_type: string;
  status: string;
  start_date: string;
  end_date?: string;
  value?: number;
  description?: string;
  alert_days_before: number;
  created_at: string;
}

const STATUS_LABEL: Record<string, string> = {
  vigente: "Vigente",
  encerrado: "Encerrado",
  suspenso: "Suspenso",
  em_negociacao: "Em Negociação",
};
const STATUS_COLOR: Record<string, string> = {
  vigente: "bg-green-100 text-green-700",
  encerrado: "bg-slate-100 text-slate-500",
  suspenso: "bg-yellow-100 text-yellow-700",
  em_negociacao: "bg-blue-100 text-blue-700",
};
const TYPE_LABEL: Record<string, string> = {
  prestacao_servico: "Prestação de Serviço",
  locacao: "Locação",
  fornecimento: "Fornecimento",
  parceria: "Parceria",
  nda: "NDA",
  outro: "Outro",
};

function fmtDate(d?: string) {
  if (!d) return "—";
  return new Date(d + "T12:00:00").toLocaleDateString("pt-BR");
}
function fmtMoney(v?: number) {
  if (!v) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}
function daysUntil(d?: string) {
  if (!d) return null;
  const diff = Math.ceil(
    (new Date(d + "T12:00:00").getTime() - Date.now()) / 86400000,
  );
  return diff;
}

const EMPTY_FORM = {
  title: "",
  counterparty: "",
  contract_type: "prestacao_servico",
  status: "vigente",
  start_date: "",
  end_date: "",
  value: "",
  description: "",
  alert_days_before: "30",
};

export default function OfficeContracts() {
  const [contracts, setContracts] = useState<Contract[]>([]);
  const [expiring, setExpiring] = useState<Contract[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Contract | null>(null);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [filterStatus, setFilterStatus] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [all, exp] = await Promise.all([
        api.get("/v1/office-contracts", {
          params: filterStatus ? { status: filterStatus } : {},
        }),
        api.get("/v1/office-contracts/expiring"),
      ]);
      setContracts(all.data.data || []);
      setExpiring(exp.data || []);
    } finally {
      setLoading(false);
    }
  }, [filterStatus]);

  useEffect(() => {
    load();
  }, [load]);

  function openNew() {
    setEditing(null);
    setForm({ ...EMPTY_FORM });
    setShowForm(true);
  }
  function openEdit(c: Contract) {
    setEditing(c);
    setForm({
      title: c.title,
      counterparty: c.counterparty,
      contract_type: c.contract_type,
      status: c.status,
      start_date: c.start_date?.slice(0, 10) || "",
      end_date: c.end_date?.slice(0, 10) || "",
      value: c.value?.toString() || "",
      description: c.description || "",
      alert_days_before: c.alert_days_before?.toString() || "30",
    });
    setShowForm(true);
  }

  async function save() {
    const payload = {
      ...form,
      value: form.value ? parseFloat(form.value) : undefined,
      alert_days_before: parseInt(form.alert_days_before),
      end_date: form.end_date || undefined,
    };
    if (editing) {
      await api.patch(`/v1/office-contracts/${editing.id}`, payload);
    } else {
      await api.post("/v1/office-contracts", payload);
    }
    setShowForm(false);
    load();
  }

  async function remove(id: string) {
    if (!window.confirm("Excluir contrato?")) return;
    await api.delete(`/v1/office-contracts/${id}`);
    load();
  }

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <div className="eyebrow mb-2">Financeiro</div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950">
            Contratos do Escritório
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Gestão de contratos operacionais e parcerias
          </p>
        </div>
        <button
          onClick={openNew}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
        >
          <Plus className="w-4 h-4" /> Novo Contrato
        </button>
      </div>

      {expiring.length > 0 && (
        <div className="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-2">
          <AlertTriangle className="w-4 h-4 text-yellow-600 mt-0.5 flex-shrink-0" />
          <div className="text-sm text-yellow-800">
            <strong>{expiring.length} contrato(s)</strong> vencendo nos próximos
            30 dias:{" "}
            {expiring
              .map((c) => `${c.title} (${fmtDate(c.end_date)})`)
              .join(", ")}
          </div>
        </div>
      )}

      <div className="flex gap-2 mb-4">
        {["", "vigente", "encerrado", "suspenso", "em_negociacao"].map((s) => (
          <button
            key={s}
            onClick={() => setFilterStatus(s)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${filterStatus === s ? "bg-blue-600 text-white border-blue-600" : "bg-white text-slate-600 border-slate-200 hover:border-blue-300"}`}
          >
            {s === "" ? "Todos" : STATUS_LABEL[s]}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-400">Carregando...</div>
      ) : contracts.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          <FileText className="w-10 h-10 mx-auto mb-2 opacity-30" />
          <p>Nenhum contrato encontrado</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Contrato</th>
                <th className="px-4 py-3 text-left">Contraparte</th>
                <th className="px-4 py-3 text-left">Tipo</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Vigência</th>
                <th className="px-4 py-3 text-left">Valor</th>
                <th className="px-4 py-3 text-left">Vence em</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {contracts.map((c) => {
                const days = daysUntil(c.end_date);
                return (
                  <tr
                    key={c.id}
                    className="hover:bg-slate-50 transition-colors"
                  >
                    <td className="px-4 py-3 font-medium text-slate-800">
                      {c.title}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {c.counterparty}
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {TYPE_LABEL[c.contract_type] || c.contract_type}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLOR[c.status] || "bg-slate-100 text-slate-500"}`}
                      >
                        {STATUS_LABEL[c.status] || c.status}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-500">
                      {fmtDate(c.start_date)} → {fmtDate(c.end_date)}
                    </td>
                    <td className="px-4 py-3 text-slate-600">
                      {fmtMoney(c.value)}
                    </td>
                    <td className="px-4 py-3">
                      {days === null ? (
                        <span className="text-slate-400">—</span>
                      ) : days < 0 ? (
                        <span className="text-red-600 flex items-center gap-1">
                          <X className="w-3 h-3" /> Vencido
                        </span>
                      ) : days <= 30 ? (
                        <span className="text-yellow-600 flex items-center gap-1">
                          <Clock className="w-3 h-3" /> {days}d
                        </span>
                      ) : (
                        <span className="text-green-600 flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" /> {days}d
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        <button
                          onClick={() => openEdit(c)}
                          className="p-1.5 rounded text-slate-400 hover:text-blue-600 hover:bg-blue-50"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                        </button>
                        <button
                          onClick={() => remove(c.id)}
                          className="p-1.5 rounded text-slate-400 hover:text-red-600 hover:bg-red-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <h2 className="font-semibold text-slate-800">
                {editing ? "Editar Contrato" : "Novo Contrato"}
              </h2>
              <button
                onClick={() => setShowForm(false)}
                className="p-1 rounded hover:bg-slate-100"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              {[
                { label: "Título", key: "title", type: "text" },
                { label: "Contraparte", key: "counterparty", type: "text" },
              ].map(({ label, key, type }) => (
                <div key={key}>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    {label}
                  </label>
                  <input
                    type={type}
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 outline-none"
                    value={(form as any)[key]}
                    onChange={(e) =>
                      setForm({ ...form, [key]: e.target.value })
                    }
                  />
                </div>
              ))}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Tipo
                  </label>
                  <select
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.contract_type}
                    onChange={(e) =>
                      setForm({ ...form, contract_type: e.target.value })
                    }
                  >
                    {Object.entries(TYPE_LABEL).map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Status
                  </label>
                  <select
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.status}
                    onChange={(e) =>
                      setForm({ ...form, status: e.target.value })
                    }
                  >
                    {Object.entries(STATUS_LABEL).map(([v, l]) => (
                      <option key={v} value={v}>
                        {l}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Início
                  </label>
                  <input
                    type="date"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.start_date}
                    onChange={(e) =>
                      setForm({ ...form, start_date: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Fim
                  </label>
                  <input
                    type="date"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.end_date}
                    onChange={(e) =>
                      setForm({ ...form, end_date: e.target.value })
                    }
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Valor (R$)
                  </label>
                  <input
                    type="number"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.value}
                    onChange={(e) =>
                      setForm({ ...form, value: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Alerta (dias antes)
                  </label>
                  <input
                    type="number"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.alert_days_before}
                    onChange={(e) =>
                      setForm({ ...form, alert_days_before: e.target.value })
                    }
                  />
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Descrição
                </label>
                <textarea
                  rows={3}
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
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                Salvar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
