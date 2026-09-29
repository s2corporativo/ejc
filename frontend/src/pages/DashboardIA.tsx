import { useState } from "react";
import api from "../lib/api";
import { ErrorState, PageHeader, Spinner, fmtMoney } from "../components/UI";
import { Kpi, KpiGrid } from "../components/Dashboards";
import { mensagemDaFalha, useCarregar } from "../lib/useCarregar";

export default function DashboardIA() {
  const [dias, setDias] = useState(30);
  // E4: erro de carga vira ErrorState com "Tentar novamente" — antes virava um
  // painel de zeros indistinguível de "nenhuma chamada no período".
  const carga = useCarregar<any>(
    () => api.get(`/ia-saude/dashboard?dias=${dias}`).then((r) => r.data),
    [dias],
    { fallbackErro: "Não foi possível carregar a saúde da IA." },
  );
  const d = carga.dados;

  if (carga.carregando)
    return (
      <div className="flex justify-center py-20">
        <Spinner />
      </div>
    );

  // KPIs usam o componente canônico do design system (auditoria §2.6 #3:
  // havia um `Kpi` local duplicando components/Dashboards.tsx).
  const blocos: [string, any][] = [
    ["Por modelo", d?.por_modelo],
    ["Por tipo de uso", d?.por_tipo_uso],
    ["Por status de revisão", d?.por_status_hitl],
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Inteligência"
        title="Saúde da IA"
        subtitle="Uso, custo e aproveitamento (revisão do advogado) das chamadas de IA — LGPD/OAB"
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

      {carga.estado === "falhou" ? (
        <ErrorState
          title="Não foi possível carregar a saúde da IA"
          message={mensagemDaFalha(carga)}
          onRetry={carga.recarregar}
        />
      ) : (
        <>
          <KpiGrid cols={4} className="mb-5">
            <Kpi label="Chamadas" value={d?.total_chamadas ?? 0} />
            <Kpi label="Custo (R$)" value={fmtMoney(d?.custo_total_brl)} />
            <Kpi
              label="Aproveitamento"
              value={
                d?.taxa_aproveitamento_pct != null
                  ? `${d.taxa_aproveitamento_pct}%`
                  : "—"
              }
            />
            <Kpi
              label="PII removida"
              value={d?.chamadas_com_pii_removida ?? 0}
            />
          </KpiGrid>

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
        </>
      )}
    </div>
  );
}
