import React, { useEffect, useState } from "react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Empty, fmtDate } from "../../components/UI";

export default function TabMemoria({ caseId }: { caseId: string }) {
  const [itens, setItens] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    tipo: "tese_vencedora",
    titulo: "",
    conteudo: "",
    resultado: "favoravel",
    area_direito: "",
  });
  const TIPOS: Record<string, string> = {
    tese_vencedora: "Tese Vencedora",
    estrategia: "Estratégia",
    peticao: "Petição",
    recurso: "Recurso",
    parecer: "Parecer",
    contrato: "Contrato",
    decisao: "Decisão",
    acordo: "Acordo",
  };
  const RES: Record<string, string> = {
    favoravel: "text-green-700 bg-green-100",
    desfavoravel: "text-danger-700 bg-danger-100",
    parcial: "text-yellow-700 bg-yellow-100",
    acordo: "text-primary-700 bg-primary-100",
    em_andamento: "text-gray-700 bg-gray-100",
  };

  const carregar = () =>
    api
      .get(`/memoria-institucional?case_id=${caseId}`)
      .then((r) => setItens(asList(r.data)))
      .catch(() => {});
  useEffect(() => {
    carregar();
  }, [caseId]);

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post("/memoria-institucional", { ...form, case_id: caseId });
    setShowForm(false);
    setForm({
      tipo: "tese_vencedora",
      titulo: "",
      conteudo: "",
      resultado: "favoravel",
      area_direito: "",
    });
    carregar();
  };
  const remover = async (id: string) => {
    if (!confirm("Remover este registro de memória?")) return;
    try {
      await api.delete(`/memoria-institucional/${id}`);
      setItens((p) => p.filter((x) => x.id !== id));
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover registro");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="font-semibold">
          Memória Institucional ({itens.length})
        </h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary text-sm"
        >
          + Registrar
        </button>
      </div>
      <p className="text-xs text-gray-400">
        O que funcionou neste caso — para reaproveitar em casos futuros.
      </p>
      {showForm && (
        <form onSubmit={salvar} className="card p-4 space-y-3">
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <label className="label">Tipo</label>
              <select
                value={form.tipo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, tipo: e.target.value }))
                }
                className="input w-full"
              >
                {Object.entries(TIPOS).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Resultado</label>
              <select
                value={form.resultado}
                onChange={(e) =>
                  setForm((f) => ({ ...f, resultado: e.target.value }))
                }
                className="input w-full"
              >
                {Object.keys(RES).map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </div>
            <div className="col-span-2">
              <label className="label">Título *</label>
              <input
                required
                value={form.titulo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, titulo: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div className="col-span-2">
              <label className="label">Conteúdo *</label>
              <textarea
                required
                rows={3}
                value={form.conteudo}
                onChange={(e) =>
                  setForm((f) => ({ ...f, conteudo: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Área do Direito</label>
              <input
                value={form.area_direito}
                onChange={(e) =>
                  setForm((f) => ({ ...f, area_direito: e.target.value }))
                }
                className="input w-full"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <button type="submit" className="btn-primary text-sm">
              Salvar
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="btn-secondary text-sm"
            >
              Cancelar
            </button>
          </div>
        </form>
      )}
      <div className="space-y-2">
        {itens.map((m) => (
          <div key={m.id} className="card p-4">
            <div className="flex justify-between items-start">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1 flex-wrap">
                  <span className="font-medium text-sm">{m.titulo}</span>
                  <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full">
                    {TIPOS[m.tipo] || m.tipo}
                  </span>
                  {m.resultado && (
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${RES[m.resultado] || "bg-gray-100"}`}
                    >
                      {m.resultado}
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-600 leading-relaxed">
                  {m.conteudo}
                </p>
                <p className="text-xs text-gray-400 mt-1">
                  {m.area_direito} · {fmtDate(m.created_at)}
                </p>
              </div>
              <button
                onClick={() => remover(m.id)}
                className="text-danger-400 hover:text-danger-600 text-xs ml-4"
              >
                Remover
              </button>
            </div>
          </div>
        ))}
        {itens.length === 0 && !showForm && (
          <Empty message="Nenhum registro de memória para este caso" />
        )}
      </div>
    </div>
  );
}
