// ── Aba Timeline/Andamentos do caso (extraída de CasoDetalhe.tsx — Tela C) ───
// Composer inline no topo (Bloco 3): registra andamento via
// POST /cases/{id}/movimentos (schema MovimentoCreate: tipo + descricao) e
// recarrega a linha do tempo. O timesheet existente permanece abaixo, seguido
// de despesas processuais (F3.2 / Issue #806) — mesmo desenho de
// "lançar cru, faturar depois" do timesheet, mas em /despesas-processuais
// (NÃO confundir com /despesas — overhead do escritório, RBAC diferente).
import { useEffect, useState } from "react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Empty, fmtDate } from "../../components/UI";
import LinhaDoTempoProcessual from "../../components/visual/LinhaDoTempoProcessual";

const CATEGORIAS_DESPESA = [
  { value: "custas", label: "Custas" },
  { value: "diligencia", label: "Diligência" },
  { value: "copias", label: "Cópias" },
  { value: "deslocamento", label: "Deslocamento" },
  { value: "pericia", label: "Perícia" },
  { value: "correios", label: "Correios" },
  { value: "outro", label: "Outro" },
];

function hoje(): string {
  return new Date().toISOString().slice(0, 10);
}

function errDetail(e: any, fallback: string): string {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d) return d;
  if (d && typeof d === "object")
    return d.mensagem ?? JSON.stringify(d).slice(0, 200);
  return fallback;
}

// Valores aceitos por case_movimentos.tipo (models/case.py: CaseMovimento).
const TIPOS_MOVIMENTO = [
  { value: "nota", label: "Nota" },
  { value: "peticao", label: "Petição" },
  { value: "decisao", label: "Decisão" },
  { value: "audiencia", label: "Audiência" },
];

export default function TabTimeline({ caseId }: { caseId: string }) {
  const [ts, setTs] = useState<any[]>([]);
  const [tsForm, setTsForm] = useState({ descricao: "", horas: 1 });
  const [showTsForm, setShowTsForm] = useState(false);
  // Composer de andamentos
  const [movTipo, setMovTipo] = useState("nota");
  const [movDescricao, setMovDescricao] = useState("");
  const [registrando, setRegistrando] = useState(false);
  // Recarrega a linha do tempo remontando o componente (ele busca no mount).
  const [timelineVersao, setTimelineVersao] = useState(0);

  const [despesas, setDespesas] = useState<any[]>([]);
  const [despesaForm, setDespesaForm] = useState({
    descricao: "",
    valor: 0,
    categoria: "outro",
  });
  const [showDespesaForm, setShowDespesaForm] = useState(false);

  const carregarTimesheet = () =>
    api
      .get(`/timesheet/casos/${caseId}`)
      .then((r) => setTs(asList(r.data)))
      .catch(() => setTs([]));

  const carregarDespesas = () =>
    api
      .get(`/despesas-processuais/casos/${caseId}`)
      .then((r) => setDespesas(asList(r.data)))
      .catch(() => setDespesas([]));

  useEffect(() => {
    carregarTimesheet();
    carregarDespesas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);

  const registrarMovimento = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!movDescricao.trim()) {
      toast.error("Descreva o andamento antes de registrar.");
      return;
    }
    setRegistrando(true);
    try {
      await api.post(`/cases/${caseId}/movimentos`, {
        tipo: movTipo,
        descricao: movDescricao.trim(),
      });
      toast.success("Andamento registrado no caso.");
      setMovDescricao("");
      setMovTipo("nota");
      setTimelineVersao((v) => v + 1);
    } catch (err: any) {
      toast.error(errDetail(err, "Não foi possível registrar o andamento."));
    } finally {
      setRegistrando(false);
    }
  };

  const addTimesheet = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      // Achado corrigido de passagem: o payload não incluía `data` nem
      // `minutos` (schema EntryIn exige os dois) — só `horas`, que o backend
      // não reconhece. O lançamento sempre voltava 422; nunca chegou a
      // gravar uma hora sequer em produção.
      await api.post("/timesheet/", {
        case_id: caseId,
        data: hoje(),
        minutos: Math.round((tsForm.horas || 0) * 60),
        descricao: tsForm.descricao,
      });
      setShowTsForm(false);
      setTsForm({ descricao: "", horas: 1 });
      carregarTimesheet();
    } catch (err: any) {
      toast.error(errDetail(err, "Não foi possível lançar as horas."));
    }
  };

  const addDespesa = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!despesaForm.descricao.trim() || !(despesaForm.valor > 0)) {
      toast.error("Informe a descrição e um valor maior que zero.");
      return;
    }
    try {
      await api.post("/despesas-processuais/", {
        case_id: caseId,
        data: hoje(),
        valor: despesaForm.valor,
        descricao: despesaForm.descricao.trim(),
        categoria: despesaForm.categoria,
      });
      toast.success("Despesa lançada.");
      setShowDespesaForm(false);
      setDespesaForm({ descricao: "", valor: 0, categoria: "outro" });
      carregarDespesas();
    } catch (err: any) {
      toast.error(errDetail(err, "Não foi possível lançar a despesa."));
    }
  };

  const totalHoras = ts.reduce((a, t) => a + (t.minutos ?? 0) / 60, 0);
  const totalDespesas = despesas.reduce((a, d) => a + Number(d.valor ?? 0), 0);

  return (
    <div className="space-y-6">
      {/* Composer inline — registrar andamento sem sair do caso */}
      <form onSubmit={registrarMovimento} className="card p-4 space-y-3">
        <h3 className="text-sm font-semibold text-slate-700">
          Registrar andamento
        </h3>
        <textarea
          className="input w-full min-h-[70px] text-sm"
          value={movDescricao}
          onChange={(e) => setMovDescricao(e.target.value)}
          placeholder="O que aconteceu neste caso? (ex.: juntada de petição, decisão publicada…)"
        />
        <div className="flex flex-wrap items-center justify-end gap-2">
          <select
            className="input text-sm py-1"
            value={movTipo}
            onChange={(e) => setMovTipo(e.target.value)}
            aria-label="Tipo do andamento"
          >
            {TIPOS_MOVIMENTO.map((t) => (
              <option key={t.value} value={t.value}>
                {t.label}
              </option>
            ))}
          </select>
          <button
            type="submit"
            disabled={registrando || !movDescricao.trim()}
            className="btn-primary text-sm disabled:opacity-50"
          >
            {registrando ? "Registrando…" : "Registrar andamento"}
          </button>
        </div>
      </form>

      <LinhaDoTempoProcessual
        key={`timeline-${timelineVersao}`}
        caseId={caseId}
      />

      <div>
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-semibold text-sm text-gray-500 uppercase">
            Timesheet ({totalHoras.toFixed(1)}h registradas)
          </h3>
          <button
            onClick={() => setShowTsForm(!showTsForm)}
            className="btn-secondary text-xs"
          >
            + Lançar horas
          </button>
        </div>
        {showTsForm && (
          <form onSubmit={addTimesheet} className="card p-4 space-y-3 mb-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="label">Atividade</label>
                <input
                  required
                  value={tsForm.descricao}
                  onChange={(e) =>
                    setTsForm((f) => ({ ...f, descricao: e.target.value }))
                  }
                  placeholder="Ex: Elaboração de petição..."
                  className="input w-full text-sm"
                />
              </div>
              <div>
                <label className="label">Horas</label>
                <input
                  type="number"
                  step="0.5"
                  min="0.5"
                  aria-label="Horas"
                  value={tsForm.horas}
                  onChange={(e) =>
                    setTsForm((f) => ({
                      ...f,
                      horas: parseFloat(e.target.value),
                    }))
                  }
                  className="input w-full text-sm"
                />
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary text-sm">
                Salvar
              </button>
              <button
                type="button"
                onClick={() => setShowTsForm(false)}
                className="btn-secondary text-sm"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}
        <div className="space-y-2">
          {ts.map((t, i) => (
            <div
              key={t.id ?? i}
              className="card p-3 flex flex-wrap justify-between items-center gap-2 text-sm"
            >
              <span className="min-w-0 flex-1 break-words text-gray-700">
                {t.descricao}
              </span>
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-gray-400 text-xs">{fmtDate(t.data)}</span>
                <span className="font-mono font-semibold text-primary-600">
                  {((t.minutos ?? 0) / 60).toFixed(1)}h
                </span>
              </div>
            </div>
          ))}
          {ts.length === 0 && !showTsForm && (
            <Empty message="Nenhuma hora lançada" />
          )}
        </div>
      </div>

      <div>
        <div className="flex justify-between items-center mb-3">
          <h3 className="font-semibold text-sm text-gray-500 uppercase">
            Despesas processuais (R$ {totalDespesas.toFixed(2)})
          </h3>
          <button
            onClick={() => setShowDespesaForm(!showDespesaForm)}
            className="btn-secondary text-xs"
          >
            + Lançar despesa
          </button>
        </div>
        {showDespesaForm && (
          <form onSubmit={addDespesa} className="card p-4 space-y-3 mb-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="col-span-2">
                <label className="label">Descrição</label>
                <input
                  required
                  value={despesaForm.descricao}
                  onChange={(e) =>
                    setDespesaForm((f) => ({
                      ...f,
                      descricao: e.target.value,
                    }))
                  }
                  placeholder="Ex: Cópias autenticadas do processo..."
                  className="input w-full text-sm"
                />
              </div>
              <div>
                <label className="label">Valor (R$)</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  aria-label="Valor (R$)"
                  value={despesaForm.valor || ""}
                  onChange={(e) =>
                    setDespesaForm((f) => ({
                      ...f,
                      valor: parseFloat(e.target.value) || 0,
                    }))
                  }
                  className="input w-full text-sm"
                />
              </div>
              <div>
                <label className="label">Categoria</label>
                <select
                  className="input w-full text-sm"
                  value={despesaForm.categoria}
                  onChange={(e) =>
                    setDespesaForm((f) => ({
                      ...f,
                      categoria: e.target.value,
                    }))
                  }
                >
                  {CATEGORIAS_DESPESA.map((c) => (
                    <option key={c.value} value={c.value}>
                      {c.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="flex gap-2">
              <button type="submit" className="btn-primary text-sm">
                Salvar
              </button>
              <button
                type="button"
                onClick={() => setShowDespesaForm(false)}
                className="btn-secondary text-sm"
              >
                Cancelar
              </button>
            </div>
          </form>
        )}
        <div className="space-y-2">
          {despesas.map((d, i) => (
            <div
              key={d.id ?? i}
              className="card p-3 flex flex-wrap justify-between items-center gap-2 text-sm"
            >
              <span className="min-w-0 flex-1 break-words text-gray-700">
                {d.descricao}
                {d.faturada && (
                  <span className="ml-2 text-xs text-emerald-600">
                    (faturada)
                  </span>
                )}
              </span>
              <div className="flex items-center gap-3 shrink-0">
                <span className="text-gray-400 text-xs">{fmtDate(d.data)}</span>
                <span className="font-mono font-semibold text-primary-600">
                  R$ {Number(d.valor ?? 0).toFixed(2)}
                </span>
              </div>
            </div>
          ))}
          {despesas.length === 0 && !showDespesaForm && (
            <Empty message="Nenhuma despesa lançada" />
          )}
        </div>
      </div>
    </div>
  );
}
