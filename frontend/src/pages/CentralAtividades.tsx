import { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { PageHeader, Spinner, Empty, EmptyState, ErrorState } from "../components/UI";
import { toast } from "../components/Toast";
import {
  Calendar,
  Clock,
  CheckCircle,
  Filter,
  List,
  LayoutGrid,
  Bell,
  FileText,
  Gavel,
  Pause,
  ClipboardList,
  Users,
  MapPin,
  Plus,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { Modal } from "../components/UI";

type ItemType =
  | "prazo"
  | "tarefa"
  | "suspensao"
  | "intimacao"
  | "audiencia"
  | "reuniao"
  | "compromisso"
  | "diligencia";

export type ActivityView = "lista" | "calendario" | "timeline" | "kanban";

export function isActivityView(value: string | null): value is ActivityView {
  return ["lista", "calendario", "timeline", "kanban"].includes(value ?? "");
}

interface Activity {
  id: string;
  tipo: ItemType;
  titulo: string;
  descricao?: string;
  date: string;
  dias_restantes?: number;
  urgencia?: string;
  status: string;
  case_id?: string;
  caso_titulo?: string;
}

function fmtDate(d: string) {
  if (!d) return "—";
  const dt = new Date(d.includes("T") ? d : d + "T12:00:00");
  return dt.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function fmtRelative(dias?: number) {
  if (dias === undefined || dias === null) return "";
  if (dias < 0) return `${Math.abs(dias)}d atraso`;
  if (dias === 0) return "Hoje";
  if (dias === 1) return "Amanhã";
  return `em ${dias}d`;
}

const URGENCIA_COLOR: Record<string, string> = {
  vencido: "text-danger-700 bg-danger-50 border-danger-200",
  critico: "text-orange-700 bg-orange-50 border-orange-200",
  atencao: "text-yellow-700 bg-yellow-50 border-yellow-200",
  normal: "text-slate-600 bg-white border-slate-200",
};

const TIPO_CONFIG: Record<
  ItemType,
  { label: string; icon: React.ElementType; color: string }
> = {
  prazo: { label: "Prazo", icon: Clock, color: "text-danger-600" },
  tarefa: { label: "Tarefa", icon: ClipboardList, color: "text-primary-600" },
  suspensao: { label: "Suspensão", icon: Pause, color: "text-ai-600" },
  intimacao: { label: "Intimação", icon: Bell, color: "text-warn-600" },
  audiencia: { label: "Audiência", icon: Gavel, color: "text-rose-600" },
  reuniao: { label: "Reunião", icon: Users, color: "text-cyan-600" },
  compromisso: {
    label: "Compromisso",
    icon: Calendar,
    color: "text-primary-600",
  },
  diligencia: { label: "Diligência", icon: MapPin, color: "text-success-600" },
};

function ActivityRow({ item }: { item: Activity }) {
  const cfg = TIPO_CONFIG[item.tipo];
  const Icon = cfg.icon;
  const urg = item.urgencia ?? "normal";
  return (
    <div
      className={`flex items-start gap-3 px-4 py-3 border-b border-slate-100 hover:bg-slate-50/60 transition-colors last:border-0 ${urg === "vencido" ? "bg-danger-50/30" : urg === "critico" ? "bg-orange-50/20" : ""}`}
    >
      <div className={`mt-0.5 flex-shrink-0 ${cfg.color}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-start justify-between gap-2">
          <p className="text-sm text-slate-800 font-medium leading-snug">
            {item.titulo}
          </p>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span
              className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${URGENCIA_COLOR[urg]}`}
            >
              {fmtRelative(item.dias_restantes)}
            </span>
            <span className="text-[10px] text-slate-400 uppercase font-medium">
              {cfg.label}
            </span>
          </div>
        </div>
        {item.caso_titulo && (
          <p className="text-xs text-slate-400 mt-0.5 truncate">
            {item.caso_titulo}
          </p>
        )}
        {item.descricao && (
          <p className="text-xs text-slate-500 mt-0.5 truncate">
            {item.descricao}
          </p>
        )}
        <p className="text-[10px] text-slate-400 mt-1">{fmtDate(item.date)}</p>
      </div>
    </div>
  );
}

function CalendarView({ items }: { items: Activity[] }) {
  const today = new Date();
  const [month, setMonth] = useState(today.getMonth());
  const [year, setYear] = useState(today.getFullYear());

  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const firstDay = new Date(year, month, 1).getDay();

  const itemsByDay = useMemo(() => {
    const map: Record<string, Activity[]> = {};
    items.forEach((item) => {
      const d = item.date?.slice(0, 10);
      if (d) map[d] = [...(map[d] ?? []), item];
    });
    return map;
  }, [items]);

  const monthNames = [
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
  ];
  const dayNames = ["Dom", "Seg", "Ter", "Qua", "Qui", "Sex", "Sáb"];

  function prevMonth() {
    if (month === 0) {
      setMonth(11);
      setYear((y) => y - 1);
    } else setMonth((m) => m - 1);
  }

  function nextMonth() {
    if (month === 11) {
      setMonth(0);
      setYear((y) => y + 1);
    } else setMonth((m) => m + 1);
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <button
          onClick={prevMonth}
          aria-label="Mês anterior"
          title="Mês anterior"
          className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors text-slate-500"
        >
          ◂
        </button>
        <h3 className="font-semibold text-slate-800">
          {monthNames[month]} {year}
        </h3>
        <button
          onClick={nextMonth}
          aria-label="Próximo mês"
          title="Próximo mês"
          className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors text-slate-500"
        >
          ▸
        </button>
      </div>
      <div className="p-3">
        <div className="grid grid-cols-7 gap-1 mb-1">
          {dayNames.map((d) => (
            <div
              key={d}
              className="text-center text-[10px] font-semibold text-slate-400 py-1"
            >
              {d}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-1">
          {Array.from({ length: firstDay }).map((_, i) => (
            <div key={`e${i}`} />
          ))}
          {Array.from({ length: daysInMonth }).map((_, i) => {
            const day = i + 1;
            const key = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
            const dayItems = itemsByDay[key] ?? [];
            const isToday =
              day === today.getDate() &&
              month === today.getMonth() &&
              year === today.getFullYear();
            const hasUrgent = dayItems.some((it) =>
              ["vencido", "critico"].includes(it.urgencia ?? ""),
            );
            return (
              <div
                key={day}
                className={`relative min-h-[44px] rounded-lg p-1 text-center cursor-default
                ${isToday ? "bg-primary-600 text-white" : dayItems.length > 0 ? "bg-slate-50 hover:bg-slate-100" : ""}
                transition-colors`}
                title={dayItems.map((it) => it.titulo).join(", ")}
              >
                <span
                  className={`text-xs font-medium ${isToday ? "text-white" : "text-slate-700"}`}
                >
                  {day}
                </span>
                {dayItems.length > 0 && (
                  <div className="flex flex-wrap gap-0.5 justify-center mt-0.5">
                    {dayItems.slice(0, 3).map((it, idx) => (
                      <div
                        key={idx}
                        className={`w-1.5 h-1.5 rounded-full ${
                          it.tipo === "prazo"
                            ? hasUrgent
                              ? "bg-danger-500"
                              : "bg-danger-300"
                            : it.tipo === "tarefa"
                              ? "bg-primary-400"
                              : it.tipo === "suspensao"
                                ? "bg-ai-400"
                                : "bg-warn-400"
                        }`}
                      />
                    ))}
                    {dayItems.length > 3 && (
                      <span className="text-[9px] text-slate-500">
                        +{dayItems.length - 3}
                      </span>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function TimelineView({ items }: { items: Activity[] }) {
  const grupos: { titulo: string; cor: string; itens: Activity[] }[] = [
    {
      titulo: "Vencidos",
      cor: "bg-danger-500",
      itens: items.filter((i) => (i.dias_restantes ?? 1) < 0),
    },
    {
      titulo: "Hoje",
      cor: "bg-orange-500",
      itens: items.filter((i) => i.dias_restantes === 0),
    },
    {
      titulo: "Próximos 7 dias",
      cor: "bg-warn-500",
      itens: items.filter(
        (i) => (i.dias_restantes ?? 99) > 0 && (i.dias_restantes ?? 99) <= 7,
      ),
    },
    {
      titulo: "Depois",
      cor: "bg-slate-400",
      itens: items.filter((i) => (i.dias_restantes ?? 99) > 7),
    },
    {
      titulo: "Sem data",
      cor: "bg-slate-300",
      itens: items.filter(
        (i) => i.dias_restantes === undefined || i.dias_restantes === null,
      ),
    },
  ].filter((g) => g.itens.length > 0);

  if (items.length === 0) {
    return (
      <EmptyState
        icon={CheckCircle}
        title="Nenhuma atividade na linha do tempo"
      />
    );
  }

  return (
    <div className="card p-5">
      <div className="relative pl-6">
        <div className="absolute left-2 top-1 bottom-1 w-px bg-slate-200" />
        {grupos.map((g) => (
          <div key={g.titulo} className="mb-6 last:mb-0">
            <div className="flex items-center gap-2 mb-3 -ml-6">
              <span
                className={`w-4 h-4 rounded-full ${g.cor} ring-4 ring-white relative z-10`}
              />
              <span className="text-sm font-semibold text-slate-700">
                {g.titulo}
              </span>
              <span className="text-xs text-slate-400">({g.itens.length})</span>
            </div>
            <div className="space-y-2">
              {g.itens.map((item) => {
                const cfg = TIPO_CONFIG[item.tipo];
                const Icon = cfg.icon;
                return (
                  <div
                    key={`${item.tipo}-${item.id}`}
                    className="flex items-start gap-2.5 bg-slate-50/60 rounded-lg px-3 py-2"
                  >
                    <Icon
                      className={`w-4 h-4 mt-0.5 flex-shrink-0 ${cfg.color}`}
                    />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-slate-700 truncate">
                        {item.titulo}
                      </p>
                      {item.caso_titulo && (
                        <p className="text-xs text-slate-400 truncate">
                          {item.caso_titulo}
                        </p>
                      )}
                    </div>
                    <span className="text-xs text-slate-400 flex-shrink-0">
                      {fmtRelative(item.dias_restantes)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function KanbanAtividades({ items }: { items: Activity[] }) {
  const tipos: ItemType[] = [
    "prazo",
    "audiencia",
    "tarefa",
    "reuniao",
    "compromisso",
    "diligencia",
    "suspensao",
    "intimacao",
  ];
  const cols = tipos
    .map((t) => ({
      tipo: t,
      cfg: TIPO_CONFIG[t],
      itens: items.filter((i) => i.tipo === t),
    }))
    .filter((col) => col.itens.length > 0);
  if (items.length === 0) {
    return <Empty message="Nada na agenda" />;
  }
  return (
    <div className="flex gap-3 overflow-x-auto pb-3">
      {cols.map(({ tipo, cfg, itens }) => {
        const Icon = cfg.icon;
        return (
          <div key={tipo} className="flex-shrink-0 w-64 bg-slate-50 rounded-xl">
            <div className="px-3 py-2.5 flex items-center gap-2 border-b border-slate-200">
              <Icon className={`w-4 h-4 ${cfg.color}`} />
              <span className="text-sm font-semibold text-slate-700">
                {cfg.label}
              </span>
              <span className="ml-auto text-[11px] text-slate-400 bg-slate-900/[0.05] rounded-full px-1.5 dark:bg-white/[0.07]">
                {itens.length}
              </span>
            </div>
            <div className="p-2 space-y-2 max-h-[60vh] overflow-y-auto">
              {itens.map((it) => (
                <div
                  key={`${it.tipo}-${it.id}`}
                  className={`bg-white rounded-lg border p-2.5 ${it.urgencia === "vencido" ? "border-danger-200" : "border-slate-200"}`}
                >
                  <p className="text-sm text-slate-700">{it.titulo}</p>
                  {it.caso_titulo && (
                    <p className="text-xs text-slate-400 mt-0.5 truncate">
                      {it.caso_titulo}
                    </p>
                  )}
                  <p
                    className={`text-[11px] mt-1 ${it.urgencia === "vencido" ? "text-danger-600 font-semibold" : "text-slate-400"}`}
                  >
                    {fmtRelative(it.dias_restantes)}
                  </p>
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function CentralAtividades() {
  const [searchParams, setSearchParams] = useSearchParams();
  const rawView = searchParams.get("view");
  const view: ActivityView = isActivityView(rawView) ? rawView : "lista";
  const setView = (next: ActivityView) => {
    const params = new URLSearchParams(searchParams);
    params.set("view", next);
    setSearchParams(params, { replace: true });
  };

  const [items, setItems] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({ tipo: "reuniao", data_evento: "" });
  const [filterTipo, setFilterTipo] = useState<ItemType | "todos">("todos");
  const [filterUrgencia, setFilterUrgencia] = useState<string>("todos");

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const r = await api.get("/atividades", {
        params: { apenas_pendentes: false },
      });
      const all: Activity[] = asList(r.data).map((a: any) => ({
        id: a.id,
        tipo: a.tipo as ItemType,
        titulo: a.titulo,
        descricao: a.descricao,
        date: a.date,
        dias_restantes: a.dias_restantes ?? undefined,
        urgencia: a.urgencia ?? "normal",
        status: a.status,
        case_id: a.case_id,
        caso_titulo: a.caso_titulo,
      }));
      setItems(all);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const salvarEvento = async () => {
    if (!form.titulo?.trim() || !form.data_evento) {
      toast.error("Título e data são obrigatórios");
      return;
    }
    try {
      await api.post("/agenda-eventos/", form);
      setModal(false);
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao salvar evento");
    }
  };

  const filtered = items.filter((item) => {
    if (filterTipo !== "todos" && item.tipo !== filterTipo) return false;
    if (filterUrgencia !== "todos" && item.urgencia !== filterUrgencia)
      return false;
    return true;
  });

  const stats = {
    vencido: items.filter((i) => i.urgencia === "vencido").length,
    critico: items.filter((i) => i.urgencia === "critico").length,
    atencao: items.filter((i) => i.urgencia === "atencao").length,
    normal: items.filter((i) => i.urgencia === "normal").length,
  };

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <PageHeader
        title="Central de Atividades"
        subtitle="Prazos, tarefas, suspensões e intimações em uma única tela"
        actions={
          <>
            <button
              onClick={() => setView("lista")}
              aria-label="Visualização em lista"
              title="Lista"
              className={`p-2 rounded-lg transition-colors ${view === "lista" ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-500 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
            >
              <List className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("calendario")}
              aria-label="Visualização em calendário"
              title="Calendário"
              className={`p-2 rounded-lg transition-colors ${view === "calendario" ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-500 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
            >
              <Calendar className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("timeline")}
              aria-label="Visualização em timeline"
              title="Timeline"
              className={`p-2 rounded-lg transition-colors ${view === "timeline" ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-500 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
            >
              <FileText className="w-4 h-4" />
            </button>
            <button
              onClick={() => setView("kanban")}
              aria-label="Visualização em quadro"
              title="Quadro"
              className={`p-2 rounded-lg transition-colors ${view === "kanban" ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-500 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => {
                setForm({ tipo: "reuniao", data_evento: "" });
                setModal(true);
              }}
              className="flex items-center gap-1 px-3 py-2 bg-success-600 text-white rounded-lg text-sm hover:bg-success-700"
            >
              <Plus className="w-4 h-4" /> Novo evento
            </button>
          </>
        }
      />

      <div className="grid grid-cols-4 gap-3 mb-5">
        {[
          {
            key: "vencido",
            label: "Vencidos",
            color: "bg-danger-50 border-danger-200 text-danger-700",
          },
          {
            key: "critico",
            label: "Críticos (≤3d)",
            color: "bg-orange-50 border-orange-200 text-orange-700",
          },
          {
            key: "atencao",
            label: "Atenção (≤7d)",
            color: "bg-yellow-50 border-yellow-200 text-yellow-700",
          },
          {
            key: "normal",
            label: "Em dia",
            color: "bg-green-50 border-green-200 text-green-700",
          },
        ].map(({ key, label, color }) => (
          <button
            key={key}
            onClick={() =>
              setFilterUrgencia(filterUrgencia === key ? "todos" : key)
            }
            className={`border rounded-xl p-3 text-left transition-all hover:shadow-sm ${color} ${filterUrgencia === key ? "ring-2 ring-offset-1 ring-slate-400" : ""}`}
          >
            <div className="text-2xl font-bold">
              {stats[key as keyof typeof stats]}
            </div>
            <div className="text-xs font-medium mt-0.5">{label}</div>
          </button>
        ))}
      </div>

      <div className="flex gap-2 mb-4 flex-wrap">
        <div className="flex items-center gap-1 text-xs text-slate-500 mr-1">
          <Filter className="w-3.5 h-3.5" /> Tipo:
        </div>
        {(
          [
            "todos",
            "prazo",
            "audiencia",
            "tarefa",
            "reuniao",
            "compromisso",
            "diligencia",
            "suspensao",
            "intimacao",
          ] as const
        ).map((t) => (
          <button
            key={t}
            onClick={() => setFilterTipo(t)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${filterTipo === t ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
          >
            {t === "todos" ? "Todos" : TIPO_CONFIG[t]?.label}
          </button>
        ))}
      </div>

      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorState
          message="Não foi possível carregar as atividades. Verifique sua conexão e tente novamente."
          onRetry={load}
        />
      ) : view === "calendario" ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2">
            <CalendarView items={filtered} />
          </div>
          <div className="card overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100">
              <p className="text-sm font-semibold text-slate-700">
                Próximas atividades
              </p>
            </div>
            <div className="overflow-y-auto max-h-80">
              {filtered.slice(0, 20).map((item) => (
                <ActivityRow key={`${item.tipo}-${item.id}`} item={item} />
              ))}
            </div>
          </div>
        </div>
      ) : view === "kanban" ? (
        <KanbanAtividades items={filtered} />
      ) : view === "timeline" ? (
        <TimelineView items={filtered} />
      ) : (
        <div className="card overflow-hidden">
          {filtered.length === 0 ? (
            <div className="py-16 text-center">
              <CheckCircle className="w-10 h-10 text-success-400 mx-auto mb-3" />
              <p className="text-slate-500 font-medium">
                Nenhuma atividade encontrada
              </p>
              <p className="text-slate-400 text-sm mt-1">
                Todos os prazos, tarefas e suspensões estão em dia
              </p>
            </div>
          ) : (
            filtered.map((item) => (
              <ActivityRow key={`${item.tipo}-${item.id}`} item={item} />
            ))
          )}
        </div>
      )}

      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title="Novo evento de agenda"
      >
        <div className="space-y-3">
          <input
            className="input w-full text-sm"
            placeholder="Título *"
            value={form.titulo ?? ""}
            onChange={(e) => setForm({ ...form, titulo: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-2">
            <select
              className="input text-sm"
              value={form.tipo}
              onChange={(e) => setForm({ ...form, tipo: e.target.value })}
            >
              <option value="reuniao">Reunião</option>
              <option value="compromisso">Compromisso</option>
              <option value="diligencia">Diligência</option>
              <option value="audiencia">Audiência</option>
              <option value="outro">Outro</option>
            </select>
            <input
              type="date"
              className="input text-sm"
              value={form.data_evento}
              onChange={(e) =>
                setForm({ ...form, data_evento: e.target.value })
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input
              className="input text-sm"
              placeholder="Hora (ex: 14:30)"
              value={form.hora ?? ""}
              onChange={(e) => setForm({ ...form, hora: e.target.value })}
            />
            <input
              className="input text-sm"
              placeholder="Local"
              value={form.local ?? ""}
              onChange={(e) => setForm({ ...form, local: e.target.value })}
            />
          </div>
          <textarea
            className="input w-full text-sm"
            rows={2}
            placeholder="Descrição"
            value={form.descricao ?? ""}
            onChange={(e) => setForm({ ...form, descricao: e.target.value })}
          />
          <div className="flex gap-2 justify-end">
            <button onClick={() => setModal(false)} className="btn-ghost">
              Cancelar
            </button>
            <button
              onClick={salvarEvento}
              className="px-4 py-2 bg-success-600 text-white text-sm rounded-lg hover:bg-success-700"
            >
              Salvar
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
