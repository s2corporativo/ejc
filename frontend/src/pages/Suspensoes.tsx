import { useEffect, useState } from "react";
import { CalendarOff, Plus, Trash2, Calculator } from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import { PageHeader, Spinner, Empty, Modal, fmtDate } from "../components/UI";

const ADMIN = ["superadmin", "admin", "socio"];

export default function Suspensoes() {
  const { user } = useAuth();
  const isAdmin = user && ADMIN.includes(user.role);

  const [lista, setLista] = useState<any[] | null>(null);
  const [tribunais, setTribunais] = useState<string[]>([]);
  const [modal, setModal] = useState(false);

  // formulário de nova suspensão
  const [form, setForm] = useState<any>({
    tribunal: "",
    data_inicio: "",
    data_fim: "",
    motivo: "",
    ato_normativo: "",
  });
  const [erro, setErro] = useState("");

  // simulador
  const [sim, setSim] = useState<any>({
    data_inicio: "",
    dias: 15,
    contagem: "uteis",
    tribunal: "",
  });
  const [simRes, setSimRes] = useState<any>(null);
  const [simLoad, setSimLoad] = useState(false);

  const carregar = () =>
    api
      .get("/suspensoes/")
      .then((r) => setLista(r.data.data))
      .catch(() => setLista([]));

  useEffect(() => {
    carregar();
    api
      .get("/suspensoes/tribunais")
      .then((r) => setTribunais(r.data.tribunais))
      .catch(() => {});
  }, []);

  const salvar = async () => {
    setErro("");
    try {
      await api.post("/suspensoes/", form);
      setModal(false);
      setForm({
        tribunal: "",
        data_inicio: "",
        data_fim: "",
        motivo: "",
        ato_normativo: "",
      });
      carregar();
    } catch (e: any) {
      setErro(e.response?.data?.detail || "Falha ao salvar");
    }
  };

  const remover = async (id: string) => {
    if (!confirm("Remover esta suspensão?")) return;
    await api.delete(`/suspensoes/${id}`);
    carregar();
  };

  const simular = async () => {
    setSimLoad(true);
    setSimRes(null);
    try {
      const { data } = await api.post("/suspensoes/simular", {
        ...sim,
        tribunal: sim.tribunal || null,
      });
      setSimRes(data);
    } catch (e: any) {
      setSimRes({ erro: e.response?.data?.detail || "Falha no cálculo" });
    } finally {
      setSimLoad(false);
    }
  };

  return (
    <div>
      <PageHeader
        eyebrow="Agenda & prazos"
        title="Suspensões de prazo"
        subtitle="Períodos em que cada tribunal suspende a contagem de prazos (portarias, recesso, feriados forenses)."
        actions={
          isAdmin && (
            <button className="btn-primary" onClick={() => setModal(true)}>
              <Plus size={16} /> Nova suspensão
            </button>
          )
        }
      />

      {/* Simulador de prazo */}
      <div className="card p-5 mb-6">
        <div className="flex items-center gap-2 mb-4">
          <Calculator size={18} className="text-gold-dark" />
          <h2 className="font-serif font-semibold text-navy text-lg">
            Simular prazo
          </h2>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3 items-end">
          <div>
            <label className="label">Início (ciência)</label>
            <input
              type="date"
              className="input"
              value={sim.data_inicio}
              onChange={(e) => setSim({ ...sim, data_inicio: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Dias</label>
            <input
              type="number"
              min={1}
              className="input"
              value={sim.dias}
              onChange={(e) => setSim({ ...sim, dias: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="label">Contagem</label>
            <select
              className="input"
              value={sim.contagem}
              onChange={(e) => setSim({ ...sim, contagem: e.target.value })}
            >
              <option value="uteis">Dias úteis</option>
              <option value="corridos">Dias corridos</option>
            </select>
          </div>
          <div>
            <label className="label">Tribunal (opcional)</label>
            <select
              className="input"
              value={sim.tribunal}
              onChange={(e) => setSim({ ...sim, tribunal: e.target.value })}
            >
              <option value="">— nenhum —</option>
              {tribunais.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </div>
          <button
            className="btn-gold"
            disabled={!sim.data_inicio || simLoad}
            onClick={simular}
          >
            {simLoad ? "Calculando…" : "Calcular"}
          </button>
        </div>

        {simRes && !simRes.erro && (
          <div className="mt-4 rounded-lg bg-navy-50 border border-navy-100 p-4">
            <div className="text-sm text-slate-500">Vencimento estimado</div>
            <div className="text-2xl font-serif font-semibold text-navy">
              {fmtDate(simRes.data_vencimento)}
            </div>
            <div className="text-xs text-slate-500 mt-1">
              {simRes.base_legal}
            </div>
            <div className="text-xs text-gold-dark mt-2">{simRes.aviso}</div>
          </div>
        )}
        {simRes?.erro && (
          <div className="mt-4 px-3 py-2 rounded-lg bg-danger-50 text-danger-700 text-sm ring-1 ring-inset ring-danger-200">
            {simRes.erro}
          </div>
        )}
      </div>

      {/* Lista de suspensões */}
      {lista === null ? (
        <Spinner />
      ) : lista.length === 0 ? (
        <Empty
          icon={CalendarOff}
          message="Nenhuma suspensão cadastrada. Registre as portarias de suspensão de prazo dos tribunais em que o escritório atua."
        />
      ) : (
        <div className="card overflow-hidden">
          <table className="table">
            <thead>
              <tr>
                <th>Tribunal</th>
                <th>Período</th>
                <th>Dias</th>
                <th>Motivo</th>
                <th>Ato</th>
                {isAdmin && <th></th>}
              </tr>
            </thead>
            <tbody>
              {lista.map((s) => (
                <tr key={s.id}>
                  <td>
                    <span className="badge badge-info">{s.tribunal}</span>
                  </td>
                  <td>
                    {fmtDate(s.data_inicio)} – {fmtDate(s.data_fim)}
                  </td>
                  <td>{s.dias}</td>
                  <td>{s.motivo}</td>
                  <td className="text-slate-500">{s.ato_normativo || "—"}</td>
                  {isAdmin && (
                    <td className="text-right">
                      <button
                        className="p-1.5 rounded-lg text-slate-400 hover:text-danger-600 hover:bg-danger-50"
                        onClick={() => remover(s.id)}
                        aria-label="Remover"
                      >
                        <Trash2 size={16} />
                      </button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Modal nova suspensão */}
      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title="Nova suspensão de prazo"
      >
        {erro && (
          <div className="mb-4 px-3 py-2 rounded-lg bg-danger-50 text-danger-700 text-sm ring-1 ring-inset ring-danger-200">
            {erro}
          </div>
        )}
        <div className="space-y-4">
          <div>
            <label className="label">Tribunal</label>
            <input
              className="input"
              list="tribunais"
              value={form.tribunal}
              placeholder="Ex.: TJMG"
              onChange={(e) => setForm({ ...form, tribunal: e.target.value })}
            />
            <datalist id="tribunais">
              {tribunais.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Início</label>
              <input
                type="date"
                className="input"
                value={form.data_inicio}
                onChange={(e) =>
                  setForm({ ...form, data_inicio: e.target.value })
                }
              />
            </div>
            <div>
              <label className="label">Fim</label>
              <input
                type="date"
                className="input"
                value={form.data_fim}
                onChange={(e) => setForm({ ...form, data_fim: e.target.value })}
              />
            </div>
          </div>
          <div>
            <label className="label">Motivo</label>
            <input
              className="input"
              value={form.motivo}
              placeholder="Ex.: Recesso forense"
              onChange={(e) => setForm({ ...form, motivo: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Ato normativo (opcional)</label>
            <input
              className="input"
              value={form.ato_normativo}
              placeholder="Ex.: Portaria 1234/2026-TJMG"
              onChange={(e) =>
                setForm({ ...form, ato_normativo: e.target.value })
              }
            />
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button className="btn-ghost" onClick={() => setModal(false)}>
              Cancelar
            </button>
            <button
              className="btn-primary"
              disabled={
                !form.tribunal ||
                !form.data_inicio ||
                !form.data_fim ||
                !form.motivo
              }
              onClick={salvar}
            >
              Salvar
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
