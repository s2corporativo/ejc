import { useState, useEffect, useCallback } from "react";
import {
  Plus,
  X,
  Check,
  Trash2,
  RefreshCw,
  Filter,
  Download,
} from "lucide-react";
import api from "../lib/api";

interface Despesa {
  id: string;
  categoria: string;
  subcategoria?: string;
  tipo: "fixo" | "variavel";
  descricao: string;
  valor: number;
  vencimento?: string;
  pago_em?: string;
  recorrente: boolean;
  recorrencia?: string;
  status: "pendente" | "pago" | "cancelado";
  competencia?: string;
  created_at: string;
}

const CATEGORIAS = [
  "infraestrutura",
  "tecnologia",
  "pessoal",
  "oab",
  "marketing",
  "operacao",
  "fiscal",
  "investimento",
  "outro",
];

const CAT_LABEL: Record<string, string> = {
  infraestrutura: "Infraestrutura",
  tecnologia: "Tecnologia",
  pessoal: "Pessoal / Pró-labore",
  oab: "OAB / Anuidade",
  marketing: "Marketing",
  operacao: "Operação",
  fiscal: "Fiscal / Contab.",
  investimento: "Investimento",
  outro: "Outros",
};

const STATUS_COLOR: Record<string, string> = {
  pendente: "bg-yellow-100 text-yellow-700",
  pago: "bg-emerald-100 text-emerald-700",
  cancelado: "bg-slate-100 text-slate-500",
};

function fmtR$(v: number) {
  return (v ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
}
function fmtDate(d?: string) {
  if (!d) return "—";
  return new Date(d + "T12:00:00").toLocaleDateString("pt-BR");
}

interface FormState {
  categoria: string;
  subcategoria: string;
  tipo: "fixo" | "variavel";
  descricao: string;
  valor: string;
  vencimento: string;
  recorrente: boolean;
  recorrencia: string;
  status: "pendente" | "pago" | "cancelado";
  competencia: string;
}

const EMPTY_FORM: FormState = {
  categoria: "operacao",
  subcategoria: "",
  tipo: "fixo",
  descricao: "",
  valor: "",
  vencimento: "",
  recorrente: false,
  recorrencia: "mensal",
  status: "pendente",
  competencia: "",
};

export default function Despesas() {
  const [items, setItems] = useState<Despesa[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>({ ...EMPTY_FORM });

  // filters
  const [filterCat, setFilterCat] = useState("");
  const [filterStatus, setFilterStatus] = useState("");
  const [filterComp, setFilterComp] = useState(() => {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
  });

  function exportCSV() {
    const token = localStorage.getItem("ejc_access");
    const comp = filterComp ? `?competencia=${filterComp}` : "";
    const url = `/v1/despesas/export/csv${comp}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `despesas_${filterComp || "todas"}.csv`;
    // pass auth via fetch then blob
    fetch(url, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const blobUrl = URL.createObjectURL(blob);
        a.href = blobUrl;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      });
  }

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (filterCat) params.categoria = filterCat;
      if (filterStatus) params.status = filterStatus;
      if (filterComp) params.competencia = filterComp;
      const res = await api.get("/v1/despesas", { params });
      setItems(res.data ?? []);
    } finally {
      setLoading(false);
    }
  }, [filterCat, filterStatus, filterComp]);

  useEffect(() => {
    load();
  }, [load]);

  function openNew() {
    setForm({ ...EMPTY_FORM, competencia: filterComp });
    setEditId(null);
    setShowForm(true);
  }

  function openEdit(d: Despesa) {
    setForm({
      categoria: d.categoria,
      subcategoria: d.subcategoria ?? "",
      tipo: d.tipo,
      descricao: d.descricao,
      valor: String(d.valor),
      vencimento: d.vencimento ?? "",
      recorrente: d.recorrente,
      recorrencia: d.recorrencia ?? "mensal",
      status: d.status,
      competencia: d.competencia ?? "",
    });
    setEditId(d.id);
    setShowForm(true);
  }

  async function save() {
    const payload = {
      ...form,
      valor: parseFloat(form.valor) || 0,
      vencimento: form.vencimento || undefined,
      subcategoria: form.subcategoria || undefined,
      competencia: form.competencia || undefined,
      recorrencia: form.recorrente ? form.recorrencia : undefined,
    };
    if (editId) {
      await api.patch(`/v1/despesas/${editId}`, payload);
    } else {
      await api.post("/v1/despesas", payload);
    }
    setShowForm(false);
    load();
  }

  async function marcarPago(id: string) {
    await api.patch(`/v1/despesas/${id}`, {
      status: "pago",
      pago_em: new Date().toISOString().split("T")[0],
    });
    load();
  }

  async function remove(id: string) {
    if (!window.confirm("Excluir despesa?")) return;
    await api.delete(`/v1/despesas/${id}`);
    load();
  }

  const totalPendente = items
    .filter((i) => i.status === "pendente")
    .reduce((s, i) => s + i.valor, 0);
  const totalPago = items
    .filter((i) => i.status === "pago")
    .reduce((s, i) => s + i.valor, 0);

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="eyebrow mb-2">Financeiro</div>
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950">
            Despesas do Escritório
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Controle de custos fixos e variáveis
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={exportCSV}
            className="flex items-center gap-2 px-3 py-2 border border-slate-200 text-slate-600 rounded-lg hover:bg-slate-50 text-sm"
          >
            <Download className="w-4 h-4" /> CSV
          </button>
          <button
            onClick={openNew}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm font-medium"
          >
            <Plus className="w-4 h-4" /> Nova Despesa
          </button>
        </div>
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Pendente", value: totalPendente, cls: "text-amber-600" },
          {
            label: "Pago no período",
            value: totalPago,
            cls: "text-emerald-600",
          },
          {
            label: "Total lançado",
            value: totalPendente + totalPago,
            cls: "text-slate-800",
          },
        ].map(({ label, value, cls }) => (
          <div
            key={label}
            className="bg-white rounded-xl border border-slate-200 p-4"
          >
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              {label}
            </p>
            <p className={`text-xl font-bold mt-1 ${cls}`}>{fmtR$(value)}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 items-center bg-white p-3 rounded-xl border border-slate-200">
        <Filter className="w-4 h-4 text-slate-400" />
        <select
          className="text-sm border border-slate-200 rounded px-2 py-1.5"
          value={filterCat}
          onChange={(e) => setFilterCat(e.target.value)}
        >
          <option value="">Todas as categorias</option>
          {CATEGORIAS.map((c) => (
            <option key={c} value={c}>
              {CAT_LABEL[c]}
            </option>
          ))}
        </select>
        <select
          className="text-sm border border-slate-200 rounded px-2 py-1.5"
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
        >
          <option value="">Todos os status</option>
          <option value="pendente">Pendente</option>
          <option value="pago">Pago</option>
          <option value="cancelado">Cancelado</option>
        </select>
        <input
          type="month"
          className="text-sm border border-slate-200 rounded px-2 py-1.5"
          value={filterComp}
          onChange={(e) => setFilterComp(e.target.value)}
        />
        <button
          onClick={load}
          className="ml-auto p-1.5 text-slate-400 hover:text-slate-600"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {/* Table */}
      {loading ? (
        <div className="text-center py-12 text-slate-400">Carregando...</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12 text-slate-400">
          Nenhuma despesa encontrada
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Categoria</th>
                <th className="px-4 py-3 text-left">Descrição</th>
                <th className="px-4 py-3 text-left">Tipo</th>
                <th className="px-4 py-3 text-right">Valor</th>
                <th className="px-4 py-3 text-left">Vencimento</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((d) => (
                <tr
                  key={d.id}
                  className="hover:bg-slate-50 cursor-pointer"
                  onClick={() => openEdit(d)}
                >
                  <td className="px-4 py-3 text-slate-600">
                    {CAT_LABEL[d.categoria] ?? d.categoria}
                  </td>
                  <td className="px-4 py-3 text-slate-800 font-medium">
                    {d.descricao}
                    {d.recorrente && (
                      <span className="ml-1.5 text-[10px] bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full">
                        Recorrente
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-500 capitalize">
                    {d.tipo}
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-800">
                    {fmtR$(d.valor)}
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {fmtDate(d.vencimento)}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLOR[d.status] ?? "bg-slate-100 text-slate-500"}`}
                    >
                      {d.status}
                    </span>
                  </td>
                  <td
                    className="px-4 py-3"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <div className="flex gap-1">
                      {d.status === "pendente" && (
                        <button
                          onClick={() => marcarPago(d.id)}
                          title="Marcar como pago"
                          className="p-1.5 rounded text-slate-300 hover:text-emerald-600 hover:bg-emerald-50"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => remove(d.id)}
                        title="Excluir"
                        className="p-1.5 rounded text-slate-300 hover:text-red-500 hover:bg-red-50"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between sticky top-0 bg-white">
              <h2 className="font-semibold text-slate-800">
                {editId ? "Editar Despesa" : "Nova Despesa"}
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
                    Categoria *
                  </label>
                  <select
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.categoria}
                    onChange={(e) =>
                      setForm({ ...form, categoria: e.target.value })
                    }
                  >
                    {CATEGORIAS.map((c) => (
                      <option key={c} value={c}>
                        {CAT_LABEL[c]}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Tipo
                  </label>
                  <select
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.tipo}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        tipo: e.target.value as "fixo" | "variavel",
                      })
                    }
                  >
                    <option value="fixo">Fixo</option>
                    <option value="variavel">Variável</option>
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Descrição *
                </label>
                <input
                  type="text"
                  className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                  value={form.descricao}
                  onChange={(e) =>
                    setForm({ ...form, descricao: e.target.value })
                  }
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Valor (R$) *
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.valor}
                    onChange={(e) =>
                      setForm({ ...form, valor: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Competência (AAAA-MM)
                  </label>
                  <input
                    type="month"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.competencia}
                    onChange={(e) =>
                      setForm({ ...form, competencia: e.target.value })
                    }
                  />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Vencimento
                  </label>
                  <input
                    type="date"
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.vencimento}
                    onChange={(e) =>
                      setForm({ ...form, vencimento: e.target.value })
                    }
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-600 mb-1">
                    Status
                  </label>
                  <select
                    className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                    value={form.status}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        status: e.target.value as Despesa["status"],
                      })
                    }
                  >
                    <option value="pendente">Pendente</option>
                    <option value="pago">Pago</option>
                    <option value="cancelado">Cancelado</option>
                  </select>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="checkbox"
                  id="recorrente"
                  className="rounded"
                  checked={form.recorrente}
                  onChange={(e) =>
                    setForm({ ...form, recorrente: e.target.checked })
                  }
                />
                <label htmlFor="recorrente" className="text-sm text-slate-700">
                  Despesa recorrente
                </label>
                {form.recorrente && (
                  <select
                    className="ml-auto text-sm border border-slate-200 rounded px-2 py-1"
                    value={form.recorrencia}
                    onChange={(e) =>
                      setForm({ ...form, recorrencia: e.target.value })
                    }
                  >
                    <option value="mensal">Mensal</option>
                    <option value="trimestral">Trimestral</option>
                    <option value="anual">Anual</option>
                  </select>
                )}
              </div>
            </div>
            <div className="p-5 border-t border-slate-100 flex gap-3 justify-end sticky bottom-0 bg-white">
              <button
                onClick={() => setShowForm(false)}
                className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancelar
              </button>
              <button
                onClick={save}
                disabled={!form.descricao || !form.valor}
                className="px-4 py-2 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
              >
                {editId ? "Salvar alterações" : "Criar despesa"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
