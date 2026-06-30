import { useEffect, useState } from "react";
import { Plus, Leaf, AlertTriangle } from "lucide-react";
import api from "../lib/api";
import type { EnvCase, Case, Paged } from "../types";
import { PageHeader, StatusBadge, Modal, Empty, Spinner, fmtDate, fmtMoney } from "../components/UI";

const ORGAOS = ["IBAMA","IEF_MG","SEMAD_MG","FEAM_MG","IGAM_MG","ICMBio","municipal","outro"];

export default function Ambiental() {
  const [data, setData] = useState<Paged<EnvCase> | null>(null);
  const [casos, setCasos] = useState<Case[]>([]);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<any>({ orgao_autuador: "IBAMA" });
  const [salvando, setSalvando] = useState(false);

  const load = () => api.get("/environmental/", { params: { page_size: 50 } }).then((r) => setData(r.data));
  useEffect(() => {
    load();
    api.get("/cases/", { params: { area: "ambiental", page_size: 100 } }).then((r) => setCasos(r.data.data));
  }, []);

  const salvar = async () => {
    if (!form.case_id || !form.numero_auto) { alert("Caso e nº do auto obrigatórios"); return; }
    setSalvando(true);
    try {
      await api.post("/environmental/", form);
      setModal(false); setForm({ orgao_autuador: "IBAMA" }); load();
    } catch (e: any) { alert(e.response?.data?.detail || "Erro"); }
    finally { setSalvando(false); }
  };

  const diasRestantes = (d?: string) => {
    if (!d) return null;
    const diff = Math.ceil((new Date(d + "T12:00:00").getTime() - Date.now()) / 86400000);
    return diff;
  };

  return (
    <div>
      <PageHeader title="Advocacia Ambiental"
        subtitle="Autos de infração · defesas · conversão de multas"
        actions={<button className="btn-gold" onClick={() => setModal(true)}><Plus size={16} /> Novo auto</button>} />

      <div className="mb-4 p-3 rounded-lg bg-green-50 text-green-800 text-xs flex items-center gap-2">
        <Leaf size={15} />
        Ao registrar a <strong>data de ciência</strong>, o prazo de defesa (20 dias — Decreto 6.514/08 art. 113)
        é calculado automaticamente com prorrogação legal, e uma deadline crítica é criada com margem interna de 2 dias úteis.
      </div>

      {!data ? <Spinner /> : data.data.length === 0 ? (
        <Empty message="Nenhum auto de infração registrado" />
      ) : (
        <div className="space-y-2">
          {data.data.map((e) => {
            const dias = diasRestantes(e.data_prazo_defesa);
            const critico = dias !== null && dias <= 5 && ["prazo_correndo","elaborando"].includes(e.status_defesa);
            return (
              <div key={e.id} className={`card p-4 flex flex-wrap items-center gap-4 ${critico ? "border-l-4 border-red-600 bg-red-50/40" : "border-l-4 border-green-600"}`}>
                <div className="flex-1 min-w-[200px]">
                  <div className="font-medium text-navy flex items-center gap-2">
                    Auto {e.numero_auto}
                    {critico && <AlertTriangle size={15} className="text-red-600" />}
                  </div>
                  <div className="text-xs text-slate-400">{e.orgao_autuador.replace(/_/g, "-")} · ciência: {fmtDate(e.data_ciencia)}</div>
                </div>
                <div className="text-sm">
                  <div className="text-xs text-slate-400">Multa</div>
                  <div className="font-semibold">{fmtMoney(e.valor_multa)}</div>
                </div>
                <div className="text-sm">
                  <div className="text-xs text-slate-400">Prazo defesa</div>
                  <div className={`font-bold ${critico ? "text-red-600" : "text-navy"}`}>
                    {fmtDate(e.data_prazo_defesa)}
                    {dias !== null && <span className="text-xs font-normal ml-1">({dias}d)</span>}
                  </div>
                </div>
                <StatusBadge value={e.status_defesa} />
              </div>
            );
          })}
        </div>
      )}

      <Modal open={modal} onClose={() => setModal(false)} title="Novo auto de infração" wide>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2"><label className="label">Caso (área ambiental) *</label>
            <select className="input" value={form.case_id || ""} onChange={(e) => setForm({ ...form, case_id: e.target.value })}>
              <option value="">Selecione o caso...</option>
              {casos.map((c) => <option key={c.id} value={c.id}>{c.numero_interno} — {c.titulo}</option>)}
            </select>
            {casos.length === 0 && (
              <p className="text-xs text-amber-600 mt-1">Crie antes um caso com área "ambiental"</p>
            )}
          </div>
          <div><label className="label">Órgão autuador *</label>
            <select className="input" value={form.orgao_autuador} onChange={(e) => setForm({ ...form, orgao_autuador: e.target.value })}>
              {ORGAOS.map((o) => <option key={o} value={o}>{o.replace(/_/g, "-")}</option>)}
            </select></div>
          <div><label className="label">Nº do auto *</label>
            <input className="input" value={form.numero_auto || ""} onChange={(e) => setForm({ ...form, numero_auto: e.target.value })} /></div>
          <div><label className="label">Data de ciência (dispara o prazo)</label>
            <input type="date" className="input" value={form.data_ciencia || ""}
              onChange={(e) => setForm({ ...form, data_ciencia: e.target.value })} /></div>
          <div><label className="label">Valor da multa (R$)</label>
            <input type="number" step="0.01" className="input" value={form.valor_multa || ""}
              onChange={(e) => setForm({ ...form, valor_multa: e.target.value })} /></div>
          <div className="sm:col-span-2"><label className="label">Espécie da infração</label>
            <input className="input" placeholder="ex: supressão de vegetação nativa sem autorização"
              value={form.especie_infracao || ""} onChange={(e) => setForm({ ...form, especie_infracao: e.target.value })} /></div>
          <div><label className="label">Dispositivo infringido</label>
            <input className="input" placeholder="ex: art. 50 Decreto 6.514/08"
              value={form.dispositivo_infringido || ""} onChange={(e) => setForm({ ...form, dispositivo_infringido: e.target.value })} /></div>
          <div><label className="label">Área degradada (ha)</label>
            <input type="number" step="0.01" className="input" value={form.area_degradada_ha || ""}
              onChange={(e) => setForm({ ...form, area_degradada_ha: e.target.value })} /></div>
        </div>
        <div className="flex justify-end mt-5">
          <button className="btn-primary" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando..." : "Registrar auto"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
