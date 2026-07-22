import React, { useEffect, useState } from "react";
import { toast } from "../../components/Toast";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { Empty } from "../../components/UI";

export default function TabPartes({ caseId }: { caseId: string }) {
  const [partes, setPartes] = useState<any[]>([]);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    tipo: "autor",
    nome: "",
    cpf_cnpj: "",
    email: "",
    telefone: "",
    representante_legal: "",
    oab: "",
  });
  const TIPOS: Record<string, string> = {
    autor: "Autor",
    reu: "Réu",
    terceiro_interessado: "Terceiro",
    litisconsorte_ativo: "Litisconsorte Ativo",
    litisconsorte_passivo: "Litisconsorte Passivo",
    assistente: "Assistente",
    amicus_curiae: "Amicus Curiae",
    mp: "MP",
    perito: "Perito",
  };

  useEffect(() => {
    api
      .get(`/cases/${caseId}/partes`)
      .then((r) => setPartes(asList(r.data)))
      .catch(() => {});
  }, [caseId]);

  const salvar = async (e: React.FormEvent) => {
    e.preventDefault();
    await api.post(`/cases/${caseId}/partes`, form);
    setShowForm(false);
    api
      .get(`/cases/${caseId}/partes`)
      .then((r) => setPartes(asList(r.data)))
      .catch(() => {});
  };

  const remover = async (id: string) => {
    if (!confirm("Remover esta parte?")) return;
    try {
      await api.delete(`/cases/${caseId}/partes/${id}`);
      setPartes((p) => p.filter((x) => x.id !== id));
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro ao remover parte");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="font-semibold text-gray-900">
          Partes Processuais ({partes.length})
        </h2>
        <button
          onClick={() => setShowForm(!showForm)}
          className="btn-primary text-sm"
        >
          + Adicionar
        </button>
      </div>
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
              <label className="label">Nome *</label>
              <input
                required
                value={form.nome}
                onChange={(e) =>
                  setForm((f) => ({ ...f, nome: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">CPF/CNPJ</label>
              <input
                value={form.cpf_cnpj}
                onChange={(e) =>
                  setForm((f) => ({ ...f, cpf_cnpj: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Email</label>
              <input
                type="email"
                value={form.email}
                onChange={(e) =>
                  setForm((f) => ({ ...f, email: e.target.value }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">Representante Legal</label>
              <input
                value={form.representante_legal}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    representante_legal: e.target.value,
                  }))
                }
                className="input w-full"
              />
            </div>
            <div>
              <label className="label">OAB</label>
              <input
                value={form.oab}
                onChange={(e) =>
                  setForm((f) => ({ ...f, oab: e.target.value }))
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
        {partes.map((p) => (
          <div key={p.id} className="card p-4 flex justify-between items-start">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-medium text-sm">{p.nome}</span>
                <span className="text-xs bg-primary-100 text-primary-700 px-2 py-0.5 rounded-full">
                  {TIPOS[p.tipo] || p.tipo}
                </span>
              </div>
              <div className="text-xs text-gray-500 flex flex-wrap gap-x-3">
                {p.cpf_cnpj && <span>{p.cpf_cnpj}</span>}
                {p.email && <span>{p.email}</span>}
                {p.representante_legal && (
                  <span>
                    Adv: {p.representante_legal}
                    {p.oab ? ` (OAB ${p.oab})` : ""}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={() => remover(p.id)}
              className="text-danger-400 hover:text-danger-600 text-xs ml-4"
            >
              Remover
            </button>
          </div>
        ))}
        {partes.length === 0 && !showForm && (
          <Empty message="Nenhuma parte cadastrada" />
        )}
      </div>
    </div>
  );
}
