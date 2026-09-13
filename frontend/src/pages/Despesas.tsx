import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router";
import { Plus, Check, Trash2, RefreshCw, Filter, Download } from "lucide-react";
import api from "../lib/api";
import { toast } from "../components/Toast";
import {
  Modal,
  Button,
  fmtDate,
  Spinner,
  Empty,
  ErrorState,
  StatusBadge,
  ConfirmModal,
} from "../components/UI";

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

function fmtR$(v: number) {
  return (v ?? 0).toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
  });
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

const STATUS_VALIDOS = ["pendente", "pago", "cancelado"];

export default function Despesas({
  competencia,
}: {
  /** Competência (AAAA-MM) — controlada pelo FinanceiroWorkspace. */
  competencia?: string;
}) {
  const [items, setItems] = useState<Despesa[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>({ ...EMPTY_FORM });
  const [pendenteExcluir, setPendenteExcluir] = useState<string | null>(null);
  const [searchParams] = useSearchParams();

  // filters (status inicial pode vir do drill-down do dashboard: ?status=pendente)
  const [filterCat, setFilterCat] = useState("");
  const [filterStatus, setFilterStatus] = useState(() => {
    const s = searchParams.get("status");
    return s && STATUS_VALIDOS.includes(s) ? s : "";
  });
  const filterComp = competencia ?? "";

  async function exportCSV() {
    try {
      const resp = await api.get("/despesas/export/csv", {
        params: filterComp ? { competencia: filterComp } : {},
        responseType: "blob",
      });
      const blobUrl = URL.createObjectURL(resp.data as Blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = `despesas_${filterComp || "todas"}.csv`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(blobUrl);
    } catch {
      toast.error("Falha ao exportar as despesas em CSV.");
    }
  }

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const params: Record<string, string> = {};
      if (filterCat) params.categoria = filterCat;
      if (filterStatus) params.status = filterStatus;
      if (filterComp) params.competencia = filterComp;
      const res = await api.get("/despesas", { params });
      setItems(res.data ?? []);
    } catch {
      setError(true);
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

  function openExtra() {
    // Despesa extra usa o mesmo registro financeiro canônico; apenas começa
    // como variável, não recorrente e sem criar cadastro/tabela paralelos.
    setForm({
      ...EMPTY_FORM,
      categoria: "outro",
      tipo: "variavel",
      recorrente: false,
      competencia: filterComp,
    });
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
    try {
      if (editId) {
        await api.patch(`/despesas/${editId}`, payload);
      } else {
        await api.post("/despesas", payload);
      }
      setShowForm(false);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erro ao salvar a despesa");
    }
  }

  async function marcarPago(id: string) {
    try {
      await api.patch(`/despesas/${id}`, {
        status: "pago",
        pago_em: new Date().toISOString().split("T")[0],
      });
      load();
    } catch (e: any) {
      toast.error(
        e?.response?.data?.detail || "Erro ao marcar a despesa como paga",
      );
    }
  }

  function remove(id: string) {
    setPendenteExcluir(id);
  }

  async function confirmarExclusao() {
    if (!pendenteExcluir) return;
    try {
      await api.delete(`/despesas/${pendenteExcluir}`);
      setPendenteExcluir(null);
      load();
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || "Erro ao excluir a despesa");
    }
  }

  const totalPendente = items
    .filter((i) => i.status === "pendente")
    .reduce((s, i) => s + i.valor, 0);
  const totalPago = items
    .filter((i) => i.status === "pago")
    .reduce((s, i) => s + i.valor, 0);

  return (
    <div className="space-y-5">
      {/* Cabeçalho fica no FinanceiroWorkspace (título + competência única);
          aqui apenas as ações da aba. */}
      <div className="flex items-center justify-end gap-2 flex-wrap">
        <button onClick={exportCSV} className="btn-secondary text-sm">
          <Download className="w-4 h-4" /> CSV
        </button>
        <button onClick={openExtra} className="btn-secondary text-sm">
          <Plus className="w-4 h-4" /> Despesa extra
        </button>
        <button onClick={openNew} className="btn-primary">
          <Plus className="w-4 h-4" /> Nova Despesa
        </button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
        {[
          { label: "Pendente", value: totalPendente, cls: "text-warn-600" },
          {
            label: "Pago no período",
            value: totalPago,
            cls: "text-success-600",
          },
          {
            label: "Total lançado",
            value: totalPendente + totalPago,
            cls: "text-slate-800",
          },
        ].map(({ label, value, cls }) => (
          <div key={label} className="card p-4">
            <p className="text-xs text-slate-500 uppercase tracking-wide">
              {label}
            </p>
            <p className={`text-xl font-bold mt-1 ${cls}`}>{fmtR$(value)}</p>
          </div>
        ))}
      </div>

      <div className="card flex flex-wrap gap-3 items-center p-3">
        <Filter className="w-4 h-4 text-slate-400" />
        <select
          className="input w-auto py-1.5"
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
          className="input w-auto py-1.5"
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
        >
          <option value="">Todos os status</option>
          <option value="pendente">Pendente</option>
          <option value="pago">Pago</option>
          <option value="cancelado">Cancelado</option>
        </select>
        <Button
          onClick={load}
          variant="ghost"
          size="icon"
          className="ml-auto"
          aria-label="Atualizar"
          icon={
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          }
        />
      </div>

      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorState
          message="Não foi possível carregar as despesas. Tente novamente."
          onRetry={load}
        />
      ) : items.length === 0 ? (
        <Empty message="Nenhuma despesa encontrada" />
      ) : (
        <div className="card overflow-hidden">
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
                      <span className="ml-1.5 text-[10px] bg-primary-50 text-primary-600 px-1.5 py-0.5 rounded-full">
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
                    <StatusBadge value={d.status} />
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
                          className="p-1.5 rounded text-slate-300 hover:text-success-600 hover:bg-success-50"
                        >
                          <Check className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <button
                        onClick={() => remove(d.id)}
                        title="Excluir"
                        className="p-1.5 rounded text-slate-300 hover:text-danger-500 hover:bg-danger-50"
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

      <Modal
        open={showForm}
        onClose={() => setShowForm(false)}
        title={editId ? "Editar Despesa" : "Nova Despesa"}
      >
        <>
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Categoria *
                </label>
                <select
                  className="input"
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
                  className="input"
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
                className="input"
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
                  min="0.01"
                  className="input"
                  value={form.valor}
                  onChange={(e) => setForm({ ...form, valor: e.target.value })}
                />
                {form.valor.trim() !== "" && (parseFloat(form.valor) || 0) <= 0 && (
                  <p className="mt-1 text-xs text-amber-600">
                    Informe um valor maior que R$ 0,00.
                  </p>
                )}
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-600 mb-1">
                  Competência (AAAA-MM)
                </label>
                <input
                  type="month"
                  className="input"
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
                  className="input"
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
                  className="input"
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
                  className="input ml-auto w-auto py-1"
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
          <div className="flex gap-3 justify-end mt-5">
            <button onClick={() => setShowForm(false)} className="btn-ghost">
              Cancelar
            </button>
            <button
              onClick={save}
              disabled={!form.descricao || !form.valor || (parseFloat(form.valor) || 0) <= 0}
              className="btn-primary"
            >
              {editId ? "Salvar alterações" : "Criar despesa"}
            </button>
          </div>
        </>
      </Modal>

      <ConfirmModal
        open={pendenteExcluir !== null}
        onClose={() => setPendenteExcluir(null)}
        onConfirm={confirmarExclusao}
        title="Excluir"
        message="Excluir esta despesa? Esta ação não pode ser desfeita."
        confirmLabel="Excluir"
        variant="danger"
      />
    </div>
  );
}