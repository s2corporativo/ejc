import { useEffect, useState } from "react";
import { Trash2, RotateCcw } from "lucide-react";
import api from "../lib/api";
import { PageHeader } from "../components/UI";

const ENTIDADES = [
  ["clients", "Clientes"],
  ["cases", "Casos"],
  ["deadlines", "Prazos"],
  ["documents", "Documentos"],
  ["legal_docs", "Peças"],
  ["fees", "Honorários"],
  ["tasks", "Tarefas"],
  ["procuracoes", "Procurações"],
  ["environmental_cases", "Ambiental"],
];

export default function Lixeira() {
  const [ent, setEnt] = useState("clients");
  const [rows, setRows] = useState<any[]>([]);

  const load = () =>
    api.get(`/trash/?entidade=${ent}`).then((r) => setRows(r.data.data));
  useEffect(() => {
    load();
  }, [ent]);

  const restaurar = async (id: string) => {
    await api.post(`/trash/${ent}/${id}/restaurar`);
    load();
  };

  return (
    <div>
      <PageHeader title="Lixeira" />
      <div className="flex gap-2 flex-wrap mb-4">
        {ENTIDADES.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setEnt(id)}
            className={`px-3 py-1.5 rounded-lg text-sm ${
              ent === id
                ? "bg-navy text-white"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="card divide-y divide-slate-100">
        {rows.length === 0 && (
          <div className="p-10 text-center text-slate-400">
            <Trash2 className="mx-auto mb-2" /> Lixeira vazia
          </div>
        )}
        {rows.map((r) => (
          <div
            key={r.id}
            className="p-4 flex items-center justify-between gap-3"
          >
            <div>
              <div className="text-sm font-medium">{r.rotulo}</div>
              <div className="text-xs text-slate-400">
                Excluído em {new Date(r.excluido_em).toLocaleString("pt-BR")}
              </div>
            </div>
            <button
              className="btn-primary text-xs"
              onClick={() => restaurar(r.id)}
            >
              <RotateCcw size={13} /> Restaurar
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
