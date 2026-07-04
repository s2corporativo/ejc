import { useEffect, useState, useCallback } from "react";
import {
  Plus,
  Trash2,
  CalendarDays,
  LayoutGrid,
  List,
  RefreshCw,
  User,
  CheckCircle,
  Clock,
  AlertCircle,
} from "lucide-react";
import api from "../lib/api";
import { Modal } from "../components/UI";

const COLS = [
  {
    id: "a_fazer",
    label: "A fazer",
    color: "border-slate-300",
    bg: "bg-slate-50",
  },
  {
    id: "fazendo",
    label: "Em andamento",
    color: "border-warn-400",
    bg: "bg-warn-50/50",
  },
  {
    id: "concluida",
    label: "Concluídas",
    color: "border-success-400",
    bg: "bg-success-50/50",
  },
];

const PRIO_COLOR: Record<string, string> = {
  alta: "bg-danger-100 text-danger-700",
  media: "bg-warn-100 text-warn-700",
  baixa: "bg-slate-100 text-slate-500",
};

const PRIO_ICON: Record<string, React.ReactNode> = {
  alta: <AlertCircle className="w-3 h-3" />,
  media: <Clock className="w-3 h-3" />,
  baixa: <CheckCircle className="w-3 h-3" />,
};

function isVencida(data_limite?: string) {
  if (!data_limite) return false;
  return new Date(data_limite + "T23:59") < new Date();
}

export default function Tarefas() {
  const [tasks, setTasks] = useState<any[]>([]);
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [editTask, setEditTask] = useState<any | null>(null);
  const [form, setForm] = useState<any>({ titulo: "", prioridade: "media" });
  const [drag, setDrag] = useState<string | null>(null);
  const [view, setView] = useState<"kanban" | "list">("kanban");
  const [filterPrio, setFilterPrio] = useState("");
  const [filterResp, setFilterResp] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [t, u] = await Promise.allSettled([
        api.get("/tasks/"),
        api.get("/users/?page_size=50"),
      ]);
      if (t.status === "fulfilled") setTasks(t.value.data?.data ?? []);
      if (u.status === "fulfilled") setUsers(u.value.data?.data ?? []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = tasks.filter(
    (t) =>
      (!filterPrio || t.prioridade === filterPrio) &&
      (!filterResp || t.responsavel_id === filterResp),
  );

  const openNew = () => {
    setEditTask(null);
    setForm({ titulo: "", prioridade: "media" });
    setModal(true);
  };

  const openEdit = (t: any) => {
    setEditTask(t);
    setForm({
      titulo: t.titulo,
      prioridade: t.prioridade,
      descricao: t.descricao,
      data_limite: t.data_limite,
      responsavel_id: t.responsavel_id,
    });
    setModal(true);
  };

  const salvar = async () => {
    if (!form.titulo.trim()) return;
    if (editTask) {
      await api.patch(`/tasks/${editTask.id}`, form);
    } else {
      await api.post("/tasks/", form);
    }
    setModal(false);
    load();
  };

  const mover = async (id: string, status: string) => {
    await api.patch(`/tasks/${id}`, { status });
    load();
  };

  const remover = async (id: string) => {
    if (!confirm("Remover tarefa?")) return;
    await api.delete(`/tasks/${id}`);
    load();
  };

  const nomeUser = (id?: string) =>
    users.find((u) => u.id === id)?.full_name?.split(" ")[0] ?? null;

  const nomeCompletoUser = (id?: string) =>
    users.find((u) => u.id === id)?.full_name ?? undefined;

  const stats = {
    total: tasks.length,
    fazer: tasks.filter((t) => t.status === "a_fazer").length,
    fazendo: tasks.filter((t) => t.status === "fazendo").length,
    concluida: tasks.filter((t) => t.status === "concluida").length,
    vencidas: tasks.filter(
      (t) => t.status !== "concluida" && isVencida(t.data_limite),
    ).length,
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">Tarefas</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            {stats.total} total · {stats.fazendo} em andamento ·{" "}
            {stats.vencidas > 0 && (
              <span className="text-danger-600 font-medium">
                {stats.vencidas} vencidas
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={load} className="btn-secondary p-2">
            <RefreshCw
              className={`w-4 h-4 text-slate-400 ${loading ? "animate-spin" : ""}`}
            />
          </button>
          <div className="flex border border-slate-200 rounded-lg overflow-hidden">
            <button
              onClick={() => setView("kanban")}
              className={`p-2 ${view === "kanban" ? "bg-slate-100" : "hover:bg-slate-50"}`}
            >
              <LayoutGrid className="w-4 h-4 text-slate-500" />
            </button>
            <button
              onClick={() => setView("list")}
              className={`p-2 ${view === "list" ? "bg-slate-100" : "hover:bg-slate-50"}`}
            >
              <List className="w-4 h-4 text-slate-500" />
            </button>
          </div>
          <button onClick={openNew} className="btn-primary text-sm px-3 py-2">
            <Plus className="w-4 h-4" /> Nova tarefa
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-2 flex-wrap">
        <select
          className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          value={filterPrio}
          onChange={(e) => setFilterPrio(e.target.value)}
        >
          <option value="">Toda prioridade</option>
          <option value="alta">Alta</option>
          <option value="media">Média</option>
          <option value="baixa">Baixa</option>
        </select>
        <select
          className="border border-slate-200 rounded-lg px-3 py-1.5 text-sm bg-white"
          value={filterResp}
          onChange={(e) => setFilterResp(e.target.value)}
        >
          <option value="">Todos responsáveis</option>
          {users.map((u) => (
            <option key={u.id} value={u.id}>
              {u.full_name}
            </option>
          ))}
        </select>
      </div>

      {/* Kanban view */}
      {view === "kanban" && (
        <div className="grid md:grid-cols-3 gap-4">
          {COLS.map((col) => {
            const colTasks = filtered.filter((t) => t.status === col.id);
            return (
              <div
                key={col.id}
                className={`rounded-xl ${col.bg} border-t-4 ${col.color} p-3 min-h-[320px]`}
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => drag && mover(drag, col.id)}
              >
                <div className="flex items-center justify-between mb-3 px-1">
                  <span className="font-semibold text-sm text-slate-700">
                    {col.label}
                  </span>
                  <span className="text-xs bg-white border border-slate-200 px-2 py-0.5 rounded-full text-slate-500">
                    {colTasks.length}
                  </span>
                </div>
                <div className="space-y-2">
                  {colTasks.map((t) => (
                    <div
                      key={t.id}
                      draggable
                      onDragStart={() => setDrag(t.id)}
                      onClick={() => openEdit(t)}
                      className={`bg-white rounded-lg border p-3 cursor-pointer hover:shadow-sm transition-shadow ${
                        isVencida(t.data_limite) && t.status !== "concluida"
                          ? "border-danger-200"
                          : "border-slate-200"
                      }`}
                    >
                      <div className="flex justify-between items-start gap-2">
                        <p className="text-sm font-medium text-slate-800 leading-snug">
                          {t.titulo}
                        </p>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            remover(t.id);
                          }}
                          className="flex-shrink-0 text-slate-300 hover:text-danger-500 p-0.5"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                      {t.descricao && (
                        <p className="text-xs text-slate-400 mt-1 line-clamp-2">
                          {t.descricao}
                        </p>
                      )}
                      <div className="flex items-center gap-2 mt-2 flex-wrap">
                        <span
                          className={`flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${PRIO_COLOR[t.prioridade]}`}
                        >
                          {PRIO_ICON[t.prioridade]} {t.prioridade}
                        </span>
                        {t.data_limite && (
                          <span
                            className={`text-[10px] flex items-center gap-1 ${isVencida(t.data_limite) ? "text-danger-500 font-semibold" : "text-slate-400"}`}
                          >
                            <CalendarDays className="w-2.5 h-2.5" />
                            {new Date(
                              t.data_limite + "T12:00",
                            ).toLocaleDateString("pt-BR")}
                          </span>
                        )}
                        {t.responsavel_id && (
                          <span
                            title={nomeCompletoUser(t.responsavel_id)}
                            className="text-[10px] text-slate-400 flex items-center gap-1"
                          >
                            <User className="w-2.5 h-2.5 shrink-0" />{" "}
                            <span className="truncate max-w-[7rem]">
                              {nomeUser(t.responsavel_id)}
                            </span>
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* List view */}
      {view === "list" && (
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-400 text-left">
              <tr>
                <th className="px-4 py-3">Tarefa</th>
                <th className="px-4 py-3">Prioridade</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Prazo</th>
                <th className="px-4 py-3">Responsável</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-slate-400"
                  >
                    Nenhuma tarefa
                  </td>
                </tr>
              ) : (
                filtered.map((t) => (
                  <tr
                    key={t.id}
                    className="hover:bg-slate-50 cursor-pointer"
                    onClick={() => openEdit(t)}
                  >
                    <td className="px-4 py-3">
                      <p className="font-medium text-slate-800">{t.titulo}</p>
                      {t.descricao && (
                        <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">
                          {t.descricao}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${PRIO_COLOR[t.prioridade]}`}
                      >
                        {t.prioridade}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <select
                        className="text-xs border border-slate-200 rounded-lg px-2 py-1 bg-white"
                        value={t.status}
                        onClick={(e) => e.stopPropagation()}
                        onChange={(e) => mover(t.id, e.target.value)}
                      >
                        {COLS.map((c) => (
                          <option key={c.id} value={c.id}>
                            {c.label}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      {t.data_limite ? (
                        <span
                          className={`text-xs ${isVencida(t.data_limite) && t.status !== "concluida" ? "text-danger-600 font-semibold" : "text-slate-500"}`}
                        >
                          {new Date(
                            t.data_limite + "T12:00",
                          ).toLocaleDateString("pt-BR")}
                        </span>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {nomeUser(t.responsavel_id) ?? "—"}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          remover(t.id);
                        }}
                        className="text-slate-300 hover:text-danger-500"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal */}
      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title={editTask ? "Editar tarefa" : "Nova tarefa"}
      >
        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-500 mb-1">
              Título *
            </label>
            <input
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
              placeholder="Título da tarefa"
              value={form.titulo}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">
              Descrição
            </label>
            <textarea
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-300"
              rows={2}
              placeholder="Detalhe opcional..."
              value={form.descricao ?? ""}
              onChange={(e) => setForm({ ...form, descricao: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-500 mb-1">
                Prioridade
              </label>
              <select
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                value={form.prioridade}
                onChange={(e) =>
                  setForm({ ...form, prioridade: e.target.value })
                }
              >
                <option value="baixa">Baixa</option>
                <option value="media">Média</option>
                <option value="alta">Alta</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-500 mb-1">Prazo</label>
              <input
                type="date"
                className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
                value={form.data_limite ?? ""}
                onChange={(e) =>
                  setForm({ ...form, data_limite: e.target.value })
                }
              />
            </div>
          </div>
          <div>
            <label className="block text-xs text-slate-500 mb-1">
              Responsável
            </label>
            <select
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"
              value={form.responsavel_id ?? ""}
              onChange={(e) =>
                setForm({
                  ...form,
                  responsavel_id: e.target.value || undefined,
                })
              }
            >
              <option value="">Nenhum</option>
              {users.map((u) => (
                <option key={u.id} value={u.id}>
                  {u.full_name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-2 justify-end pt-1">
            <button
              onClick={() => setModal(false)}
              className="btn-ghost text-sm px-4 py-2"
            >
              Cancelar
            </button>
            <button onClick={salvar} className="btn-primary text-sm px-4 py-2">
              {editTask ? "Salvar" : "Criar"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
