import { useState, useEffect, useCallback } from "react";
import { Calendar, Repeat } from "lucide-react";
import api from "../lib/api";
import { apiErrorMessage } from "../lib/apiError";
import { Spinner, ErrorState } from "../components/UI";
import { toast } from "../components/Toast";
import {
  FINANCE_CATEGORY_LABELS,
  formatCurrency,
  nextFinanceCompetence,
} from "../lib/financeiro";

interface Despesa {
  id: string;
  categoria: string;
  descricao: string;
  valor: number;
  recorrencia: string;
  competencia?: string;
  status: string;
}

const CAT_LABEL = FINANCE_CATEGORY_LABELS;

export default function DespesasRecorrentes() {
  const [recorrentes, setRecorrentes] = useState<Despesa[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [targetComp, setTargetComp] = useState(nextFinanceCompetence);
  const [generating, setGenerating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await api.get("/despesas", {
        params: { recorrente: true },
      });
      setRecorrentes(
        (res.data ?? []).filter(
          (d: Despesa & { recorrente: boolean }) => d.recorrente,
        ),
      );
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const total = recorrentes.reduce((s, d) => s + d.valor, 0);

  const gerar = async () => {
    if (generating || !targetComp || recorrentes.length === 0) return;
    setGenerating(true);
    try {
      const { data } = await api.post("/despesas/recorrentes/gerar", {
        competencia: targetComp,
      });
      toast.success(
        String(data?.gerados ?? 0) +
          " lançamento(s) gerado(s); " +
          String(data?.ignorados ?? 0) +
          " já existiam.",
      );
      await load();
    } catch (e: unknown) {
      toast.error(
        apiErrorMessage(e, "Não foi possível gerar as despesas recorrentes."),
      );
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <h2 className="font-semibold text-slate-800 mb-3 flex items-center gap-2">
          <Repeat className="w-4 h-4 text-primary-500" />
          Gerar lançamentos para novo mês
        </h2>
        <div className="flex flex-wrap items-center gap-4">
          <div className="input flex w-auto items-center gap-2">
            <Calendar className="w-4 h-4 text-slate-400" />
            <input
              type="month"
              className="text-sm text-slate-700 outline-none bg-transparent"
              value={targetComp}
              onChange={(e) => setTargetComp(e.target.value)}
            />
          </div>
          <button
            type="button"
            disabled={generating || recorrentes.length === 0}
            className="btn-primary"
            onClick={gerar}
          >
            {generating
              ? "Gerando..."
              : "Gerar " + recorrentes.length + " lançamento(s)"}
          </button>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          A geração é idempotente: lançamentos existentes são ignorados.
        </p>
      </div>

      <div className="rounded-xl bg-slate-900/[0.04] p-4 flex items-center justify-between dark:bg-white/[0.06]">
        <span className="text-sm text-slate-600">
          {recorrentes.length} despesas recorrentes cadastradas
        </span>
        <span className="font-semibold text-slate-800">
          Total mensal: {formatCurrency(total)}
        </span>
      </div>

      {loading ? (
        <Spinner />
      ) : error ? (
        <ErrorState
          message="Não foi possível carregar as despesas recorrentes. Tente novamente."
          onRetry={load}
        />
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
              <tr>
                <th className="px-4 py-3 text-left">Categoria</th>
                <th className="px-4 py-3 text-left">Descrição</th>
                <th className="px-4 py-3 text-left">Recorrência</th>
                <th className="px-4 py-3 text-right">Valor</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {recorrentes.map((d) => (
                <tr key={d.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 text-slate-500">
                    {CAT_LABEL[d.categoria] ?? d.categoria}
                  </td>
                  <td className="px-4 py-3 text-slate-800 font-medium">
                    {d.descricao}
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs bg-primary-50 text-primary-600 px-2 py-0.5 rounded-full capitalize">
                      {d.recorrencia}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-slate-800">
                    {formatCurrency(d.valor)}
                  </td>
                </tr>
              ))}
              {recorrentes.length === 0 && (
                <tr>
                  <td
                    colSpan={4}
                    className="px-4 py-10 text-center text-slate-400"
                  >
                    Nenhuma despesa recorrente cadastrada. Crie despesas com a
                    opção "Recorrente" em Despesas.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
