import { useEffect, useState } from "react";
import { ClipboardCheck, FileWarning } from "lucide-react";
import {
  getDptDiagnosticReadiness,
  type DptCompany,
  type DptDiagnosticKind,
  type DptDiagnosticReadiness,
} from "./api";
import DptIntelligence from "./DptIntelligence";

const KINDS: Array<{ value: DptDiagnosticKind; label: string }> = [
  { value: "completo", label: "Completo" },
  { value: "tributario", label: "Tributário" },
  { value: "ambiental", label: "Ambiental" },
  { value: "administrativo", label: "Administrativo" },
  { value: "trabalhista", label: "Trabalhista" },
  { value: "contratual", label: "Contratual" },
  { value: "lgpd", label: "LGPD" },
  { value: "governanca_ia", label: "Governança de IA" },
];

export default function DptDiagnosis({
  companies,
}: {
  companies: DptCompany[];
}) {
  const [clientId, setClientId] = useState(companies[0]?.id || "");
  const [kind, setKind] = useState<DptDiagnosticKind>("completo");
  const [readiness, setReadiness] = useState<DptDiagnosticReadiness | null>(
    null,
  );
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!companies.some((company) => company.id === clientId)) {
      setClientId(companies[0]?.id || "");
    }
  }, [companies, clientId]);

  useEffect(() => {
    if (!clientId) return;
    let active = true;
    setReadiness(null);
    setError(false);
    void getDptDiagnosticReadiness(clientId, kind)
      .then((data) => active && setReadiness(data))
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, [clientId, kind]);

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex items-start gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-slate-950 text-amber-300 dark:bg-white/10">
            <ClipboardCheck className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Diagnóstico Jurídico Empresarial 360
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-400">
              Primeiro verifica evidências e lacunas nos registros canônicos;
              depois a IA estrutura a análise em rascunho para revisão.
            </p>
          </div>
        </div>
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Empresa
            <select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm dark:border-white/10 dark:bg-slate-950"
            >
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.nome}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-semibold text-slate-600 dark:text-slate-300">
            Tipo de diagnóstico
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as DptDiagnosticKind)}
              className="mt-1.5 w-full rounded-xl border border-slate-200 bg-white px-3 py-2.5 text-sm dark:border-white/10 dark:bg-slate-950"
            >
              {KINDS.map((item) => (
                <option key={item.value} value={item.value}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {error ? (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            Não foi possível verificar as evidências disponíveis.
          </div>
        ) : null}
        {readiness ? (
          <div className="mt-5 grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
            {readiness.areas.map((area) => (
              <div
                key={area.area}
                className="rounded-xl border border-slate-100 bg-slate-50/60 p-4 dark:border-white/10 dark:bg-white/[0.03]"
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-semibold capitalize text-slate-900 dark:text-white">
                    {area.area.replaceAll("_", " ")}
                  </span>
                  <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                    {area.estado === "com_evidencias"
                      ? "Com evidências"
                      : "Não avaliado"}
                  </span>
                </div>
                <p className="mt-3 text-xs text-slate-500">
                  Evidências localizadas:{" "}
                  {
                    area.evidencias_disponiveis.filter(
                      (evidence) => evidence.presente,
                    ).length
                  }
                </p>
                {area.lacunas_preliminares.length ? (
                  <div className="mt-2 flex items-start gap-2 text-xs leading-5 text-amber-700 dark:text-amber-300">
                    <FileWarning className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                    Lacunas preliminares: {area.lacunas_preliminares.join(", ")}
                    .
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        ) : null}
        {readiness ? (
          <div className="mt-4 rounded-xl border border-slate-200 bg-slate-50/60 p-3 text-xs leading-5 text-slate-500 dark:border-white/10 dark:bg-white/[0.03]">
            Persistência estruturada de diagnóstico não foi criada nesta pilha
            porque a governança Alembic exige migration partindo diretamente da
            main. O AILog/HITL da análise continua ativo.{" "}
            {readiness.motivo_persistencia}
          </div>
        ) : null}
      </section>

      <DptIntelligence
        companies={companies}
        initialAction="diagnostico"
        initialClientId={clientId}
      />
    </div>
  );
}
