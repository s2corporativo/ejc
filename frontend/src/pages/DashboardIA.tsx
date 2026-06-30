import { useEffect, useState } from "react";
import api from "../lib/api";
import { PageHeader, Spinner, fmtMoney } from "../components/UI";

export default function DashboardIA() {
  const [d, setD] = useState<any>(null);
  const [dias, setDias] = useState(30);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api
      .get(`/ia-saude/dashboard?dias=${dias}`)
      .then((r) => setD(r.data))
      .catch(() => setD(null))
      .finally(() => setLoading(false));
  }, [dias]);

  if (loading)
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );

  const Kpi = ({ label, val }: { label: string; val: any }) => (
    <div className="card p-4">
      <div className="text-xs text-slate-400">{label}</div>
      <div className="text-2xl font-serif text-navy mt-1">{val}</div>
    </div>
  );

  const blocos: [string, any][] = [
    ["Por modelo", d?.por_modelo],
    ["Por tipo de uso", d?.por_tipo_uso],
    ["Por status (HITL)", d?.por_status_hitl],
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Inteligência"
        title="Saúde da IA"
        subtitle="Uso, custo e aproveitamento (HITL) das chamadas de IA — LGPD/OAB"
        actions={
          <select
            className="input text-sm"
            value={dias}
            onChange={(e) => setDias(Number(e.target.value))}
          >
            <option value={7}>7 dias</option>
            <option value={30}>30 dias</option>
            <option value={90}>90 dias</option>
          </select>
        }
      />

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <Kpi label="Chamadas" val={d?.total_chamadas ?? 0} />
        <Kpi label="Custo (R$)" val={fmtMoney(d?.custo_total_brl)} />
        <Kpi
          label="Aproveitamento"
          val={
            d?.taxa_aproveitamento_pct != null
              ? `${d.taxa_aproveitamento_pct}%`
              : "—"
          }
        />
        <Kpi label="PII removida" val={d?.chamadas_com_pii_removida ?? 0} />
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {blocos.map(([titulo, obj], i) => (
          <div key={i} className="card p-4">
            <h3 className="font-semibold text-ink mb-2">{titulo}</h3>
            {Object.entries(obj || {}).length === 0 && (
              <p className="text-sm text-slate-400">Sem dados</p>
            )}
            {Object.entries(obj || {}).map(([k, v]) => (
              <div
                key={k}
                className="flex justify-between text-sm py-1 border-b border-bronze-50 last:border-0"
              >
                <span className="text-slate-600">{k}</span>
                <span className="font-semibold text-navy">{v as any}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
