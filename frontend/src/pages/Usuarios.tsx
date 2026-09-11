import { useEffect, useState } from "react";
import { toast } from "../components/Toast";
import { Pencil, Plus, UserX } from "lucide-react";
import api from "../lib/api";
import type { Paged, User } from "../types";
import {
  PageHeader,
  Modal,
  Empty,
  Spinner,
  ErrorState,
} from "../components/UI";


type NovoUsuarioForm = {
  email?: string;
  password?: string;
  full_name?: string;
  role: string;
  phone?: string;
  oab_number?: string;
  cpf?: string;
};

type EditUsuarioForm = {
  full_name?: string;
  role?: string;
  phone?: string;
  oab_number?: string;
  djen_oab_numero?: string;
  djen_oab_uf?: string;
  cpf?: string;
};

function detalheErro(e: unknown, fallback: string): string {
  const maybe = e as { response?: { data?: { detail?: unknown } } };
  return typeof maybe.response?.data?.detail === "string"
    ? maybe.response.data.detail
    : fallback;
}

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
  const [data, setData] = useState<Paged<User> | null>(null);
  const [erro, setErro] = useState(false);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<NovoUsuarioForm>({ role: "advogado" });
  const [salvando, setSalvando] = useState(false);
  const [editando, setEditando] = useState<User | null>(null);
  const [editForm, setEditForm] = useState<EditUsuarioForm>({});
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);

  const load = () => {
    setErro(false);
    return api
      .get("/users/")
      .then((r) => setData(r.data))
      .catch(() => setErro(true));
  };
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
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Erro"));
    } finally {
      setSalvando(false);
    }
  };

  const abrirEdicao = (u: User) => {
    setEditando(u);
    setEditForm({
      full_name: u.full_name,
      role: u.role,
      phone: u.phone || "",
      oab_number: u.oab_number || "",
      djen_oab_numero: u.djen_oab_numero || "",
      djen_oab_uf: u.djen_oab_uf || "",
      cpf: "",
    });
  };

  const salvarEdicao = async () => {
    if (!editando) return;
    if (!String(editForm.full_name || "").trim()) {
      toast.error("Nome completo é obrigatório");
      return;
    }
    setSalvandoEdicao(true);
    try {
      const payload: Record<string, unknown> = {
        full_name: String(editForm.full_name).trim(),
        role: editForm.role,
        phone: String(editForm.phone || "").trim() || null,
        oab_number: String(editForm.oab_number || "").trim() || null,
      };
      const djenNumero = String(editForm.djen_oab_numero || "").trim();
      const djenUf = String(editForm.djen_oab_uf || "").trim();
      const djenNumeroAtual = String(editando.djen_oab_numero || "").trim();
      const djenUfAtual = String(editando.djen_oab_uf || "").trim();
      if (djenNumero !== djenNumeroAtual || djenUf !== djenUfAtual) {
        payload.djen_oab_numero = djenNumero || null;
        payload.djen_oab_uf = djenUf || null;
      }
      if (String(editForm.cpf || "").trim()) payload.cpf = String(editForm.cpf).trim();
      await api.patch(`/users/${editando.id}`, payload);
      toast.success("Perfil atualizado");
      setEditando(null);
      setEditForm({});
      await load();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Erro ao atualizar perfil"));
    } finally {
      setSalvandoEdicao(false);
    }
  };

  const desativar = async (u: User) => {
    if (!confirm(`Desativar ${u.full_name}?`)) return;
    try {
      await api.delete(`/users/${u.id}`);
      load();
    } catch (e: unknown) {
      toast.error(detalheErro(e, "Erro ao desativar usuário"));
    }
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

      {erro ? (
        <ErrorState
          message="Não foi possível carregar os usuários. Tente novamente."
          onRetry={load}
        />
      ) : !data ? (
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
                <th className="px-4 py-3">CPF</th>
                <th className="px-4 py-3">Ativo</th>
                <th className="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {(Array.isArray(data.data) ? data.data : []).map((u: User) => (
                <tr key={u.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium text-navy">
                    {u.full_name}
                  </td>
                  <td className="px-4 py-3 text-slate-500">{u.email}</td>
                  <td className="px-4 py-3 capitalize text-xs">
                    {u.role.replace(/_/g, " ")}
                  </td>
                  <td className="px-4 py-3 text-xs">{u.oab_number || "—"}</td>
                  <td className="px-4 py-3 text-xs text-slate-500">{u.cpf_mascarado || "—"}</td>
                  <td className="px-4 py-3">{u.is_active ? "✅" : "—"}</td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <button
                      title="Editar perfil"
                      className="btn-ghost px-2 py-1"
                      onClick={() => abrirEdicao(u)}
                    >
                      <Pencil size={15} />
                    </button>
                    {u.is_active && (
                      <button
                        title="Desativar usuário"
                        className="btn-ghost px-2 py-1 text-danger-500"
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
            <label className="label">CPF</label>
            <input
              className="input"
              placeholder="000.000.000-00"
              inputMode="numeric"
              value={form.cpf || ""}
              onChange={(e) => setForm({ ...form, cpf: e.target.value })}
            />
            <p className="mt-1 text-xs text-slate-400">Armazenado cifrado; a listagem exibe apenas máscara.</p>
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

      <Modal
        open={Boolean(editando)}
        onClose={() => { setEditando(null); setEditForm({}); }}
        title="Editar perfil"
      >
        <div className="space-y-4">
          <div>
            <label className="label">Nome completo *</label>
            <input className="input" value={editForm.full_name || ""} onChange={(e) => setEditForm({ ...editForm, full_name: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Perfil</label>
              <select className="input" value={editForm.role || "advogado"} onChange={(e) => setEditForm({ ...editForm, role: e.target.value })}>
                {ROLES.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
              </select>
            </div>
            <div>
              <label className="label">OAB</label>
              <input className="input" value={editForm.oab_number || ""} onChange={(e) => setEditForm({ ...editForm, oab_number: e.target.value })} />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">OAB DJEN — número</label>
              <input className="input" inputMode="numeric" value={editForm.djen_oab_numero || ""} onChange={(e) => setEditForm({ ...editForm, djen_oab_numero: e.target.value })} />
            </div>
            <div>
              <label className="label">OAB DJEN — UF</label>
              <input className="input" maxLength={2} value={editForm.djen_oab_uf || ""} onChange={(e) => setEditForm({ ...editForm, djen_oab_uf: e.target.value.toUpperCase() })} />
            </div>
          </div>
          <div>
            <label className="label">CPF</label>
            <input className="input" placeholder={editando?.cpf_mascarado || "000.000.000-00"} inputMode="numeric" value={editForm.cpf || ""} onChange={(e) => setEditForm({ ...editForm, cpf: e.target.value })} />
            <p className="mt-1 text-xs text-slate-400">Deixe em branco para manter o CPF atual. O valor completo nunca é devolvido pela API.</p>
          </div>
          <div>
            <label className="label">WhatsApp / telefone</label>
            <input className="input" value={editForm.phone || ""} onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })} />
          </div>
          <button className="btn-primary w-full justify-center" disabled={salvandoEdicao} onClick={salvarEdicao}>
            {salvandoEdicao ? "Salvando..." : "Salvar perfil"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
