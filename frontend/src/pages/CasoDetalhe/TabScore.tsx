import { useState } from "react";
import { toast } from "../../components/Toast";
import api from "../../lib/api";
import { ErrorState, Spinner, fmtDate } from "../../components/UI";
import { asList } from "../../lib/list";
import { mensagemErroHttp } from "../../lib/iaErro";
import { useCarregar } from "../../lib/useCarregar";

export default function TabScore({ caseId }: { caseId: string }) {
  const carga = useCarregar<any[]>(
    () => api.get(`/cases/${caseId}/score-juridico`).then((r) => asList(r.data)),
    [caseId],
    { fallbackErro: "Não foi possível carregar o score jurídico." },
  );
  const scores = carga.dados ?? [];
  const [calc, setCalc] = useState(false);
  const DIMS = [
    { k: "pedido", l: "Pedido", max: 15 },
    { k: "causa_de_pedir", l: "Causa de Pedir", max: 15 },
    { k: "fundamentacao", l: "Fundamentação", max: 20 },
    { k: "provas", l: "Provas", max: 20 },
    { k: "jurisprudencia", l: "Jurisprudência", max: 15 },
    { k: "documentos_obrigatorios", l: "Documentos Obrigatórios", max: 10 },
    { k: "conformidade_formal", l: "Conformidade Formal", max: 5 },
  ];

  const calcular = async () => {
    setCalc(true);
    try {
      await api.post(`/cases/${caseId}/score-juridico/calcular`);
      carga.recarregar();
    } catch (e) {
      toast.error(mensagemErroHttp(e, "Falha no cálculo"));
    } finally {
      setCalc(false);
    }
  };

  if (carga.estado === "carregando" && !carga.dados)
    return (
      <div className="flex justify-center py-10">
        <Spinner />
      </div>
    );
  if (carga.estado === "falhou")
    return (
      <ErrorState
        title="Não foi possível carregar o score jurídico"
        message={carga.erro ?? undefined}
        onRetry={carga.recarregar}
      />
    );

  const top = scores[0];
  const getBarColor = (pct: number) =>
    pct >= 80
      ? "bg-green-500"
      : pct >= 60
        ? "bg-primary-500"
        : pct >= 40
          ? "bg-yellow-500"
          : "bg-danger-500";
  const getLabel = (t: number) =>
    t >= 80
      ? { l: "Excelente", c: "text-green-600" }
      : t >= 60
        ? { l: "Bom", c: "text-primary-600" }
        : t >= 40
          ? { l: "Regular", c: "text-yellow-600" }
          : { l: "Fraco", c: "text-danger-600" };

  return (
    <div className="space-y-5">
      <div className="flex justify-between items-center">
        <h2 className="font-semibold">Score Jurídico</h2>
        <button
          onClick={calcular}
          disabled={calc}
          className="btn-primary flex items-center gap-1 text-sm"
        >
          {calc ? (
            <>
              <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin inline-block" />
              Calculando...
            </>
          ) : (
            "⚡ Calcular com IA"
          )}
        </button>
      </div>
      {top ? (
        <>
          <div className="card p-5">
            <div className="flex items-start gap-6 mb-4">
              <div className="text-center min-w-[80px]">
                <div className="text-2xl font-bold text-gray-900">
                  {top.total}
                </div>
                <div className="text-sm text-gray-400">/100</div>
                <div
                  className={`text-sm font-semibold mt-1 ${getLabel(top.total).c}`}
                >
                  {getLabel(top.total).l}
                </div>
              </div>
              <div className="flex-1 space-y-2">
                {DIMS.map((d) => {
                  const v = Number(top[d.k] ?? 0);
                  const pct = Math.round((v / d.max) * 100);
                  return (
                    <div key={d.k}>
                      <div className="flex justify-between text-xs mb-0.5">
                        <span className="text-gray-600">{d.l}</span>
                        <span className="text-gray-400 font-mono">
                          {v}/{d.max}
                        </span>
                      </div>
                      <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full ${getBarColor(pct)}`}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
            {top.recomendacoes && (
              <div className="bg-warn-50 border border-warn-200 rounded-lg p-3 mt-3">
                <p className="text-xs font-semibold text-warn-800 mb-1">
                  Recomendações da IA
                </p>
                <ul className="space-y-0.5">
                  {(typeof top.recomendacoes === "string"
                    ? JSON.parse(top.recomendacoes)
                    : (top.recomendacoes as string[])
                  ).map((r: string, i: number) => (
                    <li key={i} className="text-xs text-warn-700">
                      • {r}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            <p className="text-xs text-warn-500 mt-2">
              ⚠️ Gerado por IA — revisão humana obrigatória
            </p>
          </div>
          {scores.length > 1 && (
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase mb-2">
                Histórico
              </p>
              <div className="space-y-1">
                {scores.slice(1).map((s) => (
                  <div
                    key={s.id}
                    className="flex justify-between items-center p-3 card text-sm"
                  >
                    <span className="text-gray-500">
                      {fmtDate(s.created_at)}
                    </span>
                    <span className={`font-bold ${getLabel(s.total).c}`}>
                      {s.total}/100 — {getLabel(s.total).l}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : (
        <div className="text-center py-16 text-gray-400">
          <p className="text-2xl mb-2">📊</p>
          <p>Nenhum score calculado ainda</p>
          <p className="text-xs mt-1">
            Clique em "Calcular com IA" para analisar a qualidade jurídica do
            caso
          </p>
        </div>
      )}
    </div>
  );
}
