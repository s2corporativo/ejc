import { useState } from "react";
import { FileText, ShieldCheck } from "lucide-react";
import type { DptCompany } from "./api";
import DptPortalGuard from "./DptPortalGuard";
import { getDptExecutiveReport, type DptExecutiveReport } from "./reportApi";

export default function DptReports({ companies }: { companies: DptCompany[] }) {
  const [clientId, setClientId] = useState(companies[0]?.id || "");
  const [days, setDays] = useState(30);
  const [report, setReport] = useState<DptExecutiveReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  async function generate() {
    if (!clientId) return;
    setLoading(true);
    setError(false);
    setReport(null);
    try {
      setReport(await getDptExecutiveReport(clientId, days));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex items-start gap-3">
          <FileText className="mt-0.5 h-5 w-5 text-amber-600" />
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Relatório Executivo Empresarial
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Rascunho determinístico por período. Nenhum envio ao cliente
              ocorre nesta tela.
            </p>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <select
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm dark:border-white/10 dark:bg-slate-950"
          >
            {companies.map((company) => (
              <option key={company.id} value={company.id}>
                {company.nome}
              </option>
            ))}
          </select>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm dark:border-white/10 dark:bg-slate-950"
          >
            <option value={7}>7 dias</option>
            <option value={30}>30 dias</option>
            <option value={60}>60 dias</option>
            <option value={90}>90 dias</option>
          </select>
        </div>
        <button
          type="button"
          onClick={() => void generate()}
          disabled={!clientId || loading}
          className="mt-4 rounded-xl bg-slate-950 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-white dark:text-slate-950"
        >
          {loading ? "Gerando…" : "Gerar rascunho"}
        </button>
      </section>
      {error ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          Não foi possível montar o relatório; nenhum conteúdo foi inventado.
        </div>
      ) : null}
      {report ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wide text-amber-700">
                {report.status}
              </div>
              <h3 className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">
                {report.empresa}
              </h3>
            </div>
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-1 text-xs font-semibold text-amber-700">
              <ShieldCheck className="h-3.5 w-3.5" /> Revisão obrigatória
            </span>
          </div>
          <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Riscos", report.principais_riscos.length],
              ["Providências", report.providencias_futuras.length],
              ["Casos", report.casos.length],
              [
                "Mudanças relevantes",
                report.mudancas_juridicas_relevantes.length,
              ],
            ].map(([label, value]) => (
              <div
                key={String(label)}
                className="rounded-xl bg-slate-50 p-3 dark:bg-white/[0.03]"
              >
                <div className="text-xs text-slate-400">{label}</div>
                <div className="mt-1 text-2xl font-semibold text-slate-900 dark:text-white">
                  {value}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <div>
              <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
                Recomendações
              </h4>
              <ul className="mt-2 space-y-2 text-sm text-slate-600 dark:text-slate-300">
                {report.recomendacoes.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            </div>
            <div>
              <h4 className="text-sm font-semibold text-slate-900 dark:text-white">
                Próximos passos
              </h4>
              <ul className="mt-2 space-y-2 text-sm text-slate-600 dark:text-slate-300">
                {report.proximos_passos.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            </div>
          </div>
          <p className="mt-5 rounded-xl border border-slate-200 p-3 text-xs leading-5 text-slate-500 dark:border-white/10">
            {report.nota}
          </p>
        </section>
      ) : null}
      <DptPortalGuard />
    </div>
  );
}
