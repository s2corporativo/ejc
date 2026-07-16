import { toast } from "../components/Toast";
import { useEffect, useState } from "react";
import {
  Plus,
  Calculator,
  CheckCircle2,
  BadgeCheck,
  Download,
  Sparkles,
} from "lucide-react";
import api, { confirmarPrazo } from "../lib/api";
import type { Deadline, Paged } from "../types";
import {
  PageHeader,
  StatusBadge,
  Badge,
  Modal,
  Empty,
  ErrorState,
  Spinner,
  fmtDate,
} from "../components/UI";
import CaseFilterChip from "../components/CaseFilterChip";
import { useCasoFiltro } from "../contexts/useCasoFiltro";

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
  const [error, setError] = useState(false);

  // Modo Caso: `?caso=` na URL vence; sem query, o caso ativo preenche.
  // GET /deadlines/ já aceita case_id (link /prazos?caso= da jornada).
  const { casoFiltro, casoFiltroNome, removerFiltro } = useCasoFiltro();

  const load = () => {
    setError(false);
    return api
      .get("/deadlines/", {
        params: {
          status: statusF || undefined,
          case_id: casoFiltro,
          page_size: 100,
        },
      })
      .then((r) => setData(r.data))
      .catch(() => setError(true));
  };
  useEffect(() => {
    load();
  }, [statusF, casoFiltro]);

  const calcular = async () => {
    if (!calc.data_inicio) return;
    const { data } = await api.post("/deadlines/calcular", calc);
    setCalcResp(data);
  };

  const exportarCsv = async () => {
    try {
      // Via api client (injeta o JWT); baixa como blob e dispara o download.
      const r = await api.get("/deadlines/export.csv", {
        params: { status: statusF || undefined, case_id: casoFiltro },
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "prazos.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Falha ao exportar o CSV.");
    }
  };

  const salvar = async () => {
    if (!form.titulo) {
      toast.error("Título obrigatório");
      return;
    }
    setSalvando(true);
    try {
      // toast.prazo
      // Modo Caso: novo prazo nasce vinculado ao caso filtrado (visível no
      // aviso do modal); sem filtro ativo, comportamento inalterado.
      await api.post("/deadlines/", { ...form, case_id: casoFiltro });
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
  const [confirmando, setConfirmando] = useState<string | null>(null);
  const confirmar = async (id: string) => {
    setConfirmando(id);
    try {
      await confirmarPrazo(id);
      toast.success("Prazo confirmado.");
      load();
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha ao confirmar o prazo.");
    } finally {
      setConfirmando(null);
    }
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
            <button className="btn-ghost" onClick={exportarCsv}>
              <Download size={16} /> Exportar CSV
            </button>
            <button className="btn-gold" onClick={() => setModal(true)}>
              <Plus size={16} /> Novo prazo
            </button>
          </>
        }
      />

      <div className="flex flex-wrap items-center gap-2 mb-4">
        {["pendente", "concluido", "vencido", ""].map((s) => (
          <button
            key={s}
            onClick={() => setStatusF(s)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium ${statusF === s ? "bg-navy text-white" : "bg-slate-900/[0.05] text-slate-600 hover:bg-slate-900/[0.09] dark:bg-white/[0.07] dark:text-slate-300"}`}
          >
            {s || "Todos"}
          </button>
        ))}
        {casoFiltro && (
          <CaseFilterChip nome={casoFiltroNome} onRemove={removerFiltro} />
        )}
      </div>

      {error ? (
        <ErrorState
          message="Não foi possível carregar os prazos. Tente novamente."
          onRetry={load}
        />
      ) : !data ? (
        <Spinner />
      ) : !Array.isArray(data.data) || data.data.length === 0 ? (
        <Empty message="Nenhum prazo nesta categoria" />
      ) : (
        <div className="space-y-2">
          {(Array.isArray(data.data) ? data.data : []).map((d: any) => (
            <div
              key={d.id}
              className={`card p-4 flex flex-wrap items-center gap-3 sm:gap-4 ${urgClass[d.urgencia] || ""}`}
            >
              <div className="flex-1 min-w-[180px]">
                <div className="font-medium text-navy flex items-center gap-2 flex-wrap">
                  {d.titulo}
                  {d.ciencia_confirmada && (
                    <BadgeCheck size={15} className="text-success-600" />
                  )}
                  {!d.confirmado && (
                    <Badge tone="amber" className="gap-1">
                      {d.origem === "importacao_ia" && <Sparkles size={11} />}
                      {d.origem === "importacao_ia"
                        ? "Sugerido pela IA — a confirmar"
                        : "A confirmar"}
                    </Badge>
                  )}
                </div>
                <div className="text-xs text-slate-400">
                  {d.base_legal || d.tipo}
                  {!d.confirmado && (
                    <span className="text-warn-600">
                      {" "}
                      · já ativo e alertando, precisa de conferência humana
                    </span>
                  )}
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
              {!d.confirmado && (
                <button
                  className="btn-gold text-xs px-2.5 py-1"
                  title="Confirmar este prazo sugerido"
                  disabled={confirmando === d.id}
                  onClick={() => confirmar(d.id)}
                >
                  {confirmando === d.id ? "Confirmando..." : "Confirmar"}
                </button>
              )}
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
                onChange={(e) => {
                  const u = e.target.value === "u";
                  setCalc({
                    ...calc,
                    dias_uteis: u,
                    dobro: u ? calc.dobro : false,
                  });
                }}
              >
                <option value="u">Dias úteis (CPC)</option>
                <option value="c">Dias corridos (admin)</option>
              </select>
            </div>
          </div>
          {calc.dias_uteis && (
            <label className="flex items-center gap-2 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={!!calc.dobro}
                onChange={(e) => setCalc({ ...calc, dobro: e.target.checked })}
              />
              Prazo em dobro (Fazenda Pública, MP, Defensoria — CPC 183/229)
            </label>
          )}
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
        <div className="flex flex-wrap items-center justify-between gap-3 mt-5">
          <span className="text-xs text-slate-400">
            {casoFiltro
              ? `Será vinculado ao caso: ${casoFiltroNome || "caso filtrado"}`
              : ""}
          </span>
          <button className="btn-primary" disabled={salvando} onClick={salvar}>
            {salvando ? "Salvando..." : "Criar prazo"}
          </button>
        </div>
      </Modal>
    </div>
  );
}
