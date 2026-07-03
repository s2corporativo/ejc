import { toast } from "../components/Toast";
import { useEffect, useState } from "react";
import { Plus, Calculator, CheckCircle2, BadgeCheck } from "lucide-react";
import api from "../lib/api";
import type { Deadline, Paged } from "../types";
import {
  PageHeader,
  StatusBadge,
  Modal,
  Empty,
  Spinner,
  fmtDate,
} from "../components/UI";

export default function Prazos() {
  const [data, setData] = useState<Paged<Deadline> | null>(null);
  const [statusF, setStatusF] = useState("pendente");
  const [modal, setModal] = useState(false);
  const [calcModal, setCalcModal] = useState(false);
  const [form, setForm] = useState<any>({
    tipo: "processual",
    prioridade: "media",
    dias_uteis: true,
  });
  const [calc, setCalc] = useState<any>({ dias: 15, dias_uteis: true });
  const [calcResp, setCalcResp] = useState<any>(null);
  const [salvando, setSalvando] = useState(false);

  const load = () =>
    api
      .get("/deadlines/", {
        params: { status: statusF || undefined, page_size: 100 },
      })
      .then((r) => setData(r.data));
  useEffect(() => {
    load();
  }, [statusF]);

  const calcular = async () => {
    if (!calc.data_inicio) return;
    const { data } = await api.post("/deadlines/calcular", calc);
    setCalcResp(data);
  };

  const salvar = async () => {
    if (!form.titulo) {
      toast.error("Título obrigatório");
      return;
    }
    setSalvando(true);
    try {
      // toast.prazo
      await api.post("/deadlines/", form);
      setModal(false);
      setForm({ tipo: "processual", prioridade: "media", dias_uteis: true });
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Erro");
    } finally {
      setSalvando(false);
    }
  };

  const concluir = async (id: string) => {
    await api.patch(`/deadlines/${id}`, { status: "concluido" });
    load();
  };
  const darCiencia = async (id: string) => {
    await api.post(`/deadlines/${id}/ciencia`);
    load();
  };

  const urgClass: Record<string, string> = {
    vencido: "border-l-4 border-danger-600 bg-danger-50/50",
    critico: "border-l-4 border-danger-500",
    atencao: "border-l-4 border-warn-400",
    normal: "border-l-4 border-slate-200",
  };

  return (
    <div>
      <PageHeader
        title="Prazos"
        subtitle={`${data?.total ?? 0} prazos`}
        actions={
          <>
            <button
              className="btn-ghost"
              onClick={() => {
                setCalcModal(true);
                setCalcResp(null);
              }}
            >
              <Calculator size={16} /> Calculadora
            </button>
            <button className="btn-gold" onClick={() => setModal(true)}>
              <Plus size={16} /> Novo prazo
            </button>
          </>
        }
      />

      <div className="flex gap-2 mb-4">
        {["pendente", "concluido", "vencido", ""].map((s) => (
          <button
            key={s}
            onClick={() => setStatusF(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium ${statusF === s ? "bg-navy text-white" : "bg-white border border-slate-200 text-slate-600"}`}
          >
            {s || "Todos"}
          </button>
        ))}
      </div>

      {!data ? (
        <Spinner />
      ) : data.data.length === 0 ? (
        <Empty message="Nenhum prazo nesta categoria" />
      ) : (
        <div className="space-y-2">
          {data.data.map((d: any) => (
            <div
              key={d.id}
              className={`card p-4 flex flex-wrap items-center gap-4 ${urgClass[d.urgencia] || ""}`}
            >
              <div className="flex-1 min-w-[200px]">
                <div className="font-medium text-navy flex items-center gap-2">
                  {d.titulo}
                  {d.ciencia_confirmada && (
                    <BadgeCheck size={15} className="text-success-600" />
                  )}
                </div>
                <div className="text-xs text-slate-400">
                  {d.base_legal || d.tipo}
                </div>
              </div>
              <div className="text-sm">
                <div
                  className={`font-bold ${d.urgencia === "vencido" || d.urgencia === "critico" ? "text-danger-600" : "text-navy"}`}
                >
                  {fmtDate(d.data_prazo)}
                </div>
                <div className="text-xs text-slate-400">
                  {d.dias_restantes < 0
                    ? `${-d.dias_restantes}d vencido`
                    : `${d.dias_restantes}d restantes`}
                </div>
              </div>
              <StatusBadge value={d.status} />
              {d.status === "pendente" && (
                <div className="flex gap-1">
                  {!d.ciencia_confirmada && (
                    <button
                      className="btn-ghost text-xs px-2 py-1"
                      title="Confirmar ciência"
                      onClick={() => darCiencia(d.id)}
                    >
                      Ciência
                    </button>
                  )}
                  <button
                    className="btn-ghost text-xs px-2 py-1 text-success-700"
                    title="Concluir"
                    onClick={() => concluir(d.id)}
                  >
                    <CheckCircle2 size={15} />
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Modal calculadora */}
      <Modal
        open={calcModal}
        onClose={() => setCalcModal(false)}
        title="Calculadora de prazos"
      >
        <div className="space-y-4">
          <div>
            <label className="label">Data da intimação/ciência</label>
            <input
              type="date"
              className="input"
              value={calc.data_inicio || ""}
              onChange={(e) =>
                setCalc({ ...calc, data_inicio: e.target.value })
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label">Dias</label>
              <input
                type="number"
                className="input"
                value={calc.dias}
                onChange={(e) => setCalc({ ...calc, dias: +e.target.value })}
              />
            </div>
            <div>
              <label className="label">Contagem</label>
              <select
                className="input"
                value={calc.dias_uteis ? "u" : "c"}
                onChange={(e) =>
                  setCalc({ ...calc, dias_uteis: e.target.value === "u" })
                }
              >
                <option value="u">Dias úteis (CPC)</option>
                <option value="c">Dias corridos (admin)</option>
              </select>
            </div>
          </div>
          <button
            className="btn-primary w-full justify-center"
            onClick={calcular}
          >
            Calcular
          </button>
          {calcResp && (
            <div className="p-4 rounded-lg bg-navy-100 text-center">
              <div className="text-2xl font-bold text-navy">
                {fmtDate(calcResp.data_vencimento)}
              </div>
              <div className="text-xs text-slate-500 mt-1">{calcResp.modo}</div>
              <div className="text-xs text-slate-500">
                {calcResp.dias_uteis_restantes} dias úteis até lá
              </div>
            </div>
          )}
        </div>
      </Modal>

      {/* Modal novo prazo */}
      <Modal
        open={modal}
        onClose={() => setModal(false)}
        title="Novo prazo"
        wide
      >
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="sm:col-span-2">
            <label className="label">Título *</label>
            <input
              className="input"
              value={form.titulo || ""}
              onChange={(e) => setForm({ ...form, titulo: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Data da intimação</label>
            <input
              type="date"
              className="input"
              value={form.data_intimacao || ""}
              onChange={(e) =>
                setForm({ ...form, data_intimacao: e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Dias de prazo (calcula automático)</label>
            <input
              type="number"
              className="input"
              value={form.dias_prazo || ""}
              onChange={(e) =>
                setForm({ ...form, dias_prazo: +e.target.value })
              }
            />
          </div>
          <div>
            <label className="label">Contagem</label>
            <select
              className="input"
              value={form.dias_uteis ? "u" : "c"}
              onChange={(e) =>
                setForm({ ...form, dias_uteis: e.target.value === "u" })
              }
            >
              <option value="u">Dias úteis</option>
              <option value="c">Dias corridos</option>
            </select>
          </div>
          <div>
            <label className="label">OU data fatal direta</label>
            <input
              type="date"
              className="input"
              value={form.data_prazo || ""}
              onChange={(e) => setForm({ ...form, data_prazo: e.target.value })}
            />
          </div>
          <div>
            <label className="label">Prioridade</label>
            <select
              className="input"
              value={form.prioridade}
              onChange={(e) => setForm({ ...form, prioridade: e.target.value })}
            >
              <option value="baixa">Baixa</option>
              <option value="media">Média</option>
              <option value="alta">Alta</option>
              <option value="critica">Crítica</option>
            </select>
          </div>
          <div>
            <label className="label">Base legal</label>
            <input
              className="input"
              placeholder="ex: CPC art. 335"
              value={form.base_legal || ""}
              onChange={(e) => setForm({ ...form, base_legal: e.target.value })}
            />
          </div>
        </div>
        <div className="flex justify-end mt-5">
          <button className="btn-primary" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando..." : "Criar prazo"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
