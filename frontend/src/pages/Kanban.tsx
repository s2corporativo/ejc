import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown } from "lucide-react";
import api from "../lib/api";
import { Spinner } from "../components/UI";

interface KanbanCol {
  id: string;
  name: string;
  legal_area: string;
  position: number;
  color?: string;
}

interface Caso {
  id: string;
  titulo: string;
  numero_interno?: string;
  area?: string;
  prioridade?: string;
  kanban_column?: string;
  fase?: string;
  cliente_nome?: string;
  case_type?: string;
}

const PRIO_COLOR: Record<string, string> = {
  critica: "bg-red-100 text-red-700",
  alta: "bg-orange-100 text-orange-700",
  media: "bg-amber-100 text-amber-700",
  baixa: "bg-slate-100 text-slate-500",
};

const COL_COLOR: Record<string, string> = {
  blue: "border-t-blue-400",
  green: "border-t-emerald-400",
  yellow: "border-t-amber-400",
  red: "border-t-red-400",
  purple: "border-t-purple-400",
  slate: "border-t-slate-400",
  orange: "border-t-orange-400",
};

const AREAS = [
  { key: "default", label: "Judicial" },
  { key: "extrajudicial", label: "Extrajudicial" },
  { key: "consultoria", label: "Consultoria" },
];

// Mapeia a aba de fluxo (legal_area das colunas) para o case_type dos casos
const AREA_TO_TYPE: Record<string, string> = {
  default: "judicial",
  extrajudicial: "extrajudicial",
  consultoria: "consultoria",
};

export default function Kanban() {
  const [area, setArea] = useState("default");
  const [cols, setCols] = useState<KanbanCol[]>([]);
  const [casos, setCasos] = useState<Caso[]>([]);
  const [loading, setLoading] = useState(true);
  const [dragId, setDragId] = useState<string | null>(null);
  const [overCol, setOverCol] = useState<string | null>(null);
  const nav = useNavigate();

  const loadCols = useCallback(async (a: string) => {
    const res = await api.get(`/v1/kanban-columns?legal_area=${a}`);
    setCols(res.data ?? []);
  }, []);

  const loadCasos = useCallback(async () => {
    const res = await api.get("/cases/?page_size=300");
    setCasos(res.data?.data ?? res.data?.items ?? []);
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([loadCols(area), loadCasos()]).finally(() => setLoading(false));
  }, [area, loadCols, loadCasos]);

  const getColKey = (c: Caso, colName: string, flowList?: Caso[]) => {
    // Casos já posicionados: respeitam o kanban_column SE pertencer a este fluxo
    const colNames = cols.map((k) => k.name);
    if (c.kanban_column && colNames.includes(c.kanban_column))
      return c.kanban_column === colName;
    // fallback: casos sem coluna válida vão para a primeira coluna deste fluxo
    return cols.length > 0 && cols[0].name === colName;
  };

  const moverParaColuna = async (caseId: string, colName: string) => {
    setOverCol(null);
    const pos = casos.filter(
      (c) =>
        c.kanban_column === colName &&
        (c.case_type || "judicial") === AREA_TO_TYPE[area],
    ).length;
    setCasos((prev) =>
      prev.map((c) => (c.id === caseId ? { ...c, kanban_column: colName } : c)),
    );
    try {
      await api.patch(`/v1/cases/${caseId}/kanban`, {
        kanban_column: colName,
        kanban_position: pos,
      });
    } catch {
      await loadCasos();
    }
  };

  if (loading)
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 pt-6 pb-3 flex items-center justify-between flex-shrink-0">
        <div>
          <h1 className="text-xl font-bold text-slate-800">Kanban de Casos</h1>
          <p className="text-slate-500 text-sm mt-0.5">
            Gestão visual do fluxo processual
          </p>
        </div>
        {/* Area tabs */}
        <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
          {AREAS.map((a) => (
            <button
              key={a.key}
              onClick={() => setArea(a.key)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                area === a.key
                  ? "bg-white text-slate-800 shadow-sm"
                  : "text-slate-500 hover:text-slate-700"
              }`}
            >
              {a.label}
            </button>
          ))}
        </div>
      </div>

      {/* Board */}
      <div className="flex-1 overflow-x-auto px-6 pb-6">
        <div
          className="flex gap-3 h-full"
          style={{ minWidth: `${cols.length * 220}px` }}
        >
          {cols.map((col) => {
            const doFluxo = casos.filter(
              (c) => (c.case_type || "judicial") === AREA_TO_TYPE[area],
            );
            const lista = doFluxo.filter((c) =>
              getColKey(c, col.name, doFluxo),
            );
            const topColor =
              COL_COLOR[col.color ?? "slate"] ?? "border-t-slate-400";
            return (
              <div
                key={col.id}
                onDragOver={(e) => {
                  e.preventDefault();
                  setOverCol(col.name);
                }}
                onDragLeave={() =>
                  setOverCol((v) => (v === col.name ? null : v))
                }
                onDrop={() => dragId && moverParaColuna(dragId, col.name)}
                className={`flex flex-col rounded-xl border-t-2 ${topColor} bg-slate-50 border border-slate-200 w-52 flex-shrink-0 transition-all ${
                  overCol === col.name ? "ring-2 ring-blue-300 bg-blue-50" : ""
                }`}
              >
                {/* Column header */}
                <div className="px-3 py-2.5 flex items-center justify-between border-b border-slate-200">
                  <span className="text-xs font-semibold text-slate-700 truncate">
                    {col.name}
                  </span>
                  <span className="text-[11px] font-semibold text-slate-400 bg-white border border-slate-200 rounded-full px-1.5 py-0.5 flex-shrink-0">
                    {lista.length}
                  </span>
                </div>
                {/* Cards */}
                <div className="flex-1 overflow-y-auto p-2 space-y-2">
                  {lista.map((c) => (
                    <div
                      key={c.id}
                      draggable
                      onDragStart={() => setDragId(c.id)}
                      onDragEnd={() => setDragId(null)}
                      className={`bg-white rounded-lg border border-slate-200 p-2.5 cursor-grab active:cursor-grabbing shadow-sm hover:shadow-md transition-shadow group ${
                        dragId === c.id ? "opacity-50" : ""
                      }`}
                    >
                      <p className="text-xs font-medium text-slate-800 leading-snug mb-1.5 line-clamp-2">
                        {c.titulo}
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {c.numero_interno && (
                          <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
                            #{c.numero_interno}
                          </span>
                        )}
                        {c.prioridade && (
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded ${PRIO_COLOR[c.prioridade] ?? "bg-slate-100 text-slate-500"}`}
                          >
                            {c.prioridade}
                          </span>
                        )}
                      </div>
                      {c.cliente_nome && (
                        <p className="text-[10px] text-slate-400 mt-1 truncate">
                          {c.cliente_nome}
                        </p>
                      )}
                      {/* Quick move select */}
                      <div className="mt-1.5 opacity-0 group-hover:opacity-100 transition-opacity">
                        <div className="relative">
                          <select
                            className="w-full text-[10px] border border-slate-200 rounded px-1.5 py-0.5 bg-white appearance-none pr-4 text-slate-500"
                            value={c.kanban_column ?? ""}
                            onChange={(e) =>
                              moverParaColuna(c.id, e.target.value)
                            }
                            onClick={(e) => e.stopPropagation()}
                          >
                            <option value="" disabled>
                              Mover para...
                            </option>
                            {cols.map((cl) => (
                              <option key={cl.id} value={cl.name}>
                                {cl.name}
                              </option>
                            ))}
                          </select>
                          <ChevronDown className="absolute right-1 top-0.5 w-2.5 h-2.5 text-slate-400 pointer-events-none" />
                        </div>
                      </div>
                      <button
                        onClick={() => nav(`/casos/${c.id}`)}
                        className="mt-1.5 w-full text-[10px] text-blue-600 hover:underline text-left opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        Abrir caso →
                      </button>
                    </div>
                  ))}
                  {lista.length === 0 && (
                    <div className="flex items-center justify-center h-20 text-xs text-slate-300">
                      Vazio
                    </div>
                  )}
                </div>
              </div>
            );
          })}
          {cols.length === 0 && (
            <div className="flex-1 flex items-center justify-center text-slate-400">
              Nenhuma coluna configurada para esta área
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
