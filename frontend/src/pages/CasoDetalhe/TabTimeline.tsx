// ── Aba Timeline/Andamentos do caso (extraída de CasoDetalhe.tsx — Tela C) ───
// Composer inline no topo (Bloco 3): registra andamento via
// POST /cases/{id}/movimentos (schema MovimentoCreate: tipo + descricao) e
// recarrega a linha do tempo. O timesheet existente permanece abaixo.
import { useEffect, useState } from "react";
import api from "../../lib/api";
import { asList } from "../../lib/list";
import { toast } from "../../components/Toast";
import { Empty, fmtDate } from "../../components/UI";
import LinhaDoTempoProcessual from "../../components/visual/LinhaDoTempoProcessual";

function errDetail(e: any, fallback: string): string {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d) return d;
  if (d && typeof d === "object")
    return d.mensagem ?? JSON.stringify(d).slice(0, 200);
  return fallback;
}

function hojeLocalISO(): string {
  const agora = new Date();
  const ano = agora.getFullYear();
  const mes = String(agora.getMonth() + 1).padStart(2, "0");
  const dia = String(agora.getDate()).padStart(2, "0");
  return `${ano}-${mes}-${dia}`;
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
  const [salvandoHoras, setSalvandoHoras] = useState(false);
  // Composer de andamentos
  const [movTipo, setMovTipo] = useState("nota");
  const [movDescricao, setMovDescricao] = useState("");
  const [registrando, setRegistrando] = useState(false);
  // Recarrega a linha do tempo remontando o componente (ele busca no mount).
  const [timelineVersao, setTimelineVersao] = useState(0);

  const recarregarTimesheet = () =>
    api
      .get(`/timesheet/casos/${caseId}`)
      .then((r) => setTs(asList(r.data)))
      .catch(() => setTs([]));

  useEffect(() => {
    void recarregarTimesheet();
    // caseId é o gatilho canônico da releitura; a função apenas encapsula a chamada.
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
    const minutos = Math.round(tsForm.horas * 60);
    if (!Number.isFinite(minutos) || minutos <= 0) {
      toast.error("Informe uma quantidade válida de horas.");
      return;
    }

    setSalvandoHoras(true);
    try {
      await api.post("/timesheet", {
        case_id: caseId,
        data: hojeLocalISO(),
        minutos,
        descricao: tsForm.descricao.trim(),
        faturavel: true,
      });
      toast.success("Horas lançadas no caso.");
      setTsForm({ descricao: "", horas: 1 });
      setShowTsForm(false);
      await recarregarTimesheet();
    } catch (err: any) {
      toast.error(errDetail(err, "Não foi possível lançar as horas."));
    } finally {
      setSalvandoHoras(false);
    }
  };

  const totalHoras = ts.reduce((a, t) => a + (t.minutos ?? 0) / 60, 0);

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
              <button
                type="submit"
                disabled={salvandoHoras}
                className="btn-primary text-sm disabled:opacity-50"
              >
                {salvandoHoras ? "Salvando…" : "Salvar"}
              </button>
              <button
                type="button"
                onClick={() => setShowTsForm(false)}
                disabled={salvandoHoras}
                className="btn-secondary text-sm disabled:opacity-50"
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
    </div>
  );
}
