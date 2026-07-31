import { useEffect, useState } from "react";
import { toast } from "../../components/Toast";
import api from "../../lib/api";
import MatrizRisco from "../../components/visual/MatrizRisco";
import { fmtDate } from "../../components/UI";

export default function TabRisco({ caseId }: { caseId: string }) {
  const [data, setData] = useState<any>(null);
  const [recalc, setRecalc] = useState(false);
  const NIVEL: Record<
    string,
    { c: string; bg: string; border: string; bar: string }
  > = {
    incompleto: {
      c: "text-gray-700",
      bg: "bg-gray-50",
      border: "border-gray-300",
      bar: "bg-gray-400",
    },
    baixo: {
      c: "text-green-700",
      bg: "bg-green-50",
      border: "border-green-200",
      bar: "bg-green-500",
    },
    medio: {
      c: "text-yellow-700",
      bg: "bg-yellow-50",
      border: "border-yellow-200",
      bar: "bg-yellow-500",
    },
    alto: {
      c: "text-orange-700",
      bg: "bg-orange-50",
      border: "border-orange-200",
      bar: "bg-orange-500",
    },
    critico: {
      c: "text-danger-700",
      bg: "bg-danger-50",
      border: "border-danger-200",
      bar: "bg-danger-500",
    },
  };
  const FATORES: Record<string, string> = {
    prazo_vencido: "Prazo Vencido",
    audiencia_perdida: "Audiência Perdida",
    sem_documentos: "Sem documentos anexados",
    triagem_incompleta: "Triagem incompleta",
    valor_alto: "Valor Alto (>500k)",
    valor_medio: "Valor Médio (>100k)",
    processo_antigo: "Processo Antigo (+3 anos)",
  };

  useEffect(() => {
    api
      .get(`/cases/${caseId}/indice-risco`)
      .then((r) => setData(r.data))
      .catch(() => {});
  }, [caseId]);

  const recalcular = async () => {
    setRecalc(true);
    try {
      await api.post(`/cases/${caseId}/indice-risco/recalcular`);
      api
        .get(`/cases/${caseId}/indice-risco`)
        .then((r) => setData(r.data))
        .catch(() => {});
    } catch (e: any) {
      toast.error(e.response?.data?.detail || "Falha no recálculo");
    } finally {
      setRecalc(false);
    }
  };

  const nivel = data?.atual?.risco_nivel as string | undefined;
  const cfg = nivel ? NIVEL[nivel] : null;
  const indice = Number(data?.atual?.indice_risco ?? 0);
  const fatores = Object.entries(data?.atual?.risco_fatores ?? {}).filter(
    ([, v]) => Boolean(v),
  );

  return (
    <div className="space-y-5">
      <MatrizRisco caseId={caseId} />
      <div className="flex justify-between items-center">
        <h2 className="font-semibold">Índice de Risco</h2>
        <button
          onClick={recalcular}
          disabled={recalc}
          className="btn-secondary text-sm"
        >
          {recalc ? "Calculando..." : "↻ Recalcular"}
        </button>
      </div>
      <div
        className={`card p-5 border ${cfg?.border ?? "border-gray-200"} ${cfg?.bg ?? ""}`}
      >
        <div className="flex items-center gap-6">
          <div className="text-center min-w-[80px]">
            <div className={`text-6xl font-black ${cfg?.c ?? "text-gray-900"}`}>
              {indice}
            </div>
            <div className="text-sm text-gray-400">/100</div>
          </div>
          <div className="flex-1">
            <div
              className={`text-xl font-bold ${cfg?.c ?? "text-gray-400"} mb-2 capitalize`}
            >
              {nivel === "incompleto"
                ? "Triagem incompleta"
                : `Risco ${nivel ?? "—"}`}
            </div>
            <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all ${cfg?.bar ?? "bg-gray-400"}`}
                style={{ width: `${indice}%` }}
              />
            </div>
            {nivel === "incompleto" ? (
              <p
                role="status"
                className="mt-2 text-sm font-medium text-gray-700"
              >
                Não há documentos anexados suficientes para uma avaliação
                conclusiva. Revise a triagem e as evidências antes de usar este
                índice em uma decisão jurídica.
              </p>
            ) : (
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>Baixo 0–25</span>
                <span>Médio 26–50</span>
                <span>Alto 51–75</span>
                <span>Crítico 76–100</span>
              </div>
            )}
          </div>
        </div>
        {fatores.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {fatores.map(([f]) => (
              <span
                key={f}
                className="text-xs bg-white border border-orange-200 text-orange-700 px-2 py-0.5 rounded-full"
              >
                ⚠ {FATORES[f] || f}
              </span>
            ))}
          </div>
        )}
        {!nivel && (
          <p className="text-center text-gray-400 text-sm mt-2">
            Clique em "Recalcular" para calcular o índice
          </p>
        )}
      </div>
      {data?.historico?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
            Histórico
          </p>
          <div className="space-y-1">
            {(data.historico as any[]).map((h, i) => (
              <div
                key={i}
                className="flex justify-between items-center p-3 card text-sm"
              >
                <span className="text-gray-500">{fmtDate(h.created_at)}</span>
                <span className={`font-bold ${NIVEL[h.nivel]?.c ?? ""}`}>
                  {h.indice} — {h.nivel}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
