import { useEffect, useState } from "react";
import { toast } from "../components/Toast";
import { Plus, UserX } from "lucide-react";
import api from "../lib/api";
import type { User } from "../types";
import { PageHeader, Modal, Empty, Spinner } from "../components/UI";

const ROLES = [
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
  "estagiario",
  "secretaria",
  "financeiro",
];

export default function Usuarios() {
  const [data, setData] = useState<any>(null);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({ role: "advogado" });
  const [salvando, setSalvando] = useState(false);

  const load = () =>
    api
      .get("/users/")
      .then((r) => setData(r.data))
      .catch(() => setData({ data: [] }));
  useEffect(() => {
    load();
  }, []);

  const salvar = async () => {
    if (!form.email || !form.password || !form.full_name) {
      toast.error("Email, senha e nome obrigatórios");
      return;
    }
    setSalvando(true);
    try {
      await api.post("/users/", form);
      setModal(false);
      setForm({ role: "advogado" });
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro");
    } finally {
      setSalvando(false);
    }
  };

  const desativar = async (u: User) => {
    if (!confirm(`Desativar ${u.full_name}?`)) return;
    await api.delete(`/users/${u.id}`);
    load();
  };

  return (
    <div>
      <PageHeader
        title="Usuários"
        subtitle="Equipe do escritório"
        actions={
          <button className="btn-gold" onClick={() => setModal(true)}>
            <Plus size={16} /> Novo usuário
          </button>
        }
      />

      {!data ? (
        <Spinner />
      ) : data.data.length === 0 ? (
        <Empty message="Nenhum usuário" />
      ) : (
        <div className="card overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-400">
              <tr>
                <th className="px-4 py-3">Nome</th>
                <th className="px-4 py-3">E-mail</th>
                <th className="px-4 py-3">Perfil</th>
                <th className="px-4 py-3">OAB</th>
                <th className="px-4 py-3">Ativo</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.data.map((u: User) => (
                <tr key={u.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-navy">
                    {u.full_name}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{u.email}</td>
                  <td className="px-4 py-3 capitalize text-xs">
                    {u.role.replace(/_/g, " ")}
                  </td>
                  <td className="px-4 py-3 text-xs">{u.oab_number || "—"}</td>
                  <td className="px-4 py-3">{u.is_active ? "✅" : "—"}</td>
                  <td className="px-4 py-3">
                    {u.is_active && (
                      <button
                        className="btn-ghost px-2 py-1 text-red-500"
                        onClick={() => desativar(u)}
                      >
                        <UserX size={15} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Novo usuário">
        <div className="space-y-4">
          <div>
            <label className="label">Nome completo *</label>
            <input
              className="input"
              value={form.full_name || ""}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            />
          </div>
          <div>
            <label className="label">E-mail *</label>
            <input
              type="email"
              className="input"
              value={form.email || ""}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Senha inicial * (mín. 8)</label>
            <input
              type="password"
              className="input"
              value={form.password || ""}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Perfil</label>
              <select
                className="input"
                value={form.role}
                onChange={(e) => setForm({ ...form, role: e.target.value })}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {r.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">OAB</label>
              <input
                className="input"
                placeholder="OAB/MG 000000"
                value={form.oab_number || ""}
                onChange={(e) =>
                  setForm({ ...form, oab_number: e.target.value })
                }
              />
            </div>
          </div>
          <div>
            <label className="label">WhatsApp (p/ alertas)</label>
            <input
              className="input"
              placeholder="5531999999999"
              value={form.phone || ""}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </div>
          <button
            className="btn-primary w-full justify-center"
            disabled={salvando}
            onClick={salvar}
          >
            {salvando ? "Criando..." : "Criar usuário"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
