import { ArrowRight, LibraryBig } from "lucide-react";
import { Link } from "react-router";
import DptDiagnosis from "./DptDiagnosis";
import DptIntelligence from "./DptIntelligence";
import DptObligations from "./DptObligations";
import DptRadar from "./DptRadar";
import DptReports from "./DptReports";
import DptTools from "./DptTools";
import type { DptDashboard } from "./api";

const PLANNED: Record<
  string,
  { title: string; text: string; href?: string; hrefLabel?: string }
> = {
  biblioteca: {
    title: "Biblioteca Empresarial",
    text: "Legislação, jurisprudência, teses, modelos, checklists e memória institucional permanecem no conhecimento canônico, com segregação por escopo.",
    href: "/inteligencia?tab=conhecimento",
    hrefLabel: "Abrir Conhecimento",
  },
};

export default function DptFeatureRouter({
  name,
  data,
}: {
  name: string;
  data: DptDashboard;
}) {
  if (name === "inteligencia") {
    return <DptIntelligence companies={data.companies} initialAction="conselho" />;
  }
  if (name === "diagnostico") return <DptDiagnosis companies={data.companies} />;
  if (name === "radar") return <DptRadar />;
  if (name === "ferramentas") return <DptTools />;
  if (name === "obrigacoes") return <DptObligations data={data} />;
  if (name === "relatorios") return <DptReports companies={data.companies} />;

  const item = PLANNED[name] || PLANNED.biblioteca;
  return (
    <section className="min-h-[360px] rounded-2xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/40">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-slate-950 text-amber-300 dark:bg-white/10">
        <LibraryBig className="h-6 w-6" />
      </span>
      <h2 className="mt-5 text-2xl font-semibold text-slate-950 dark:text-white">
        {item.title}
      </h2>
      <p className="mt-3 max-w-3xl text-sm leading-7 text-slate-500 dark:text-slate-400">
        {item.text}
      </p>
      <div className="mt-6 rounded-xl border border-dashed border-slate-200 bg-slate-50/60 p-4 text-sm text-slate-500 dark:border-white/10 dark:bg-white/[0.03] dark:text-slate-400">
        <strong className="text-slate-700 dark:text-slate-200">Regra de governança:</strong>{" "}
        conteúdo de cliente permanece segregado e conhecimento interno continua
        versionado/aprovado nas bases canônicas.
      </div>
      {item.href ? (
        <Link
          to={item.href}
          className="mt-5 inline-flex items-center gap-2 rounded-xl border border-slate-200 px-4 py-2.5 text-sm font-semibold text-slate-700 dark:border-white/10 dark:text-slate-200"
        >
          {item.hrefLabel}
          <ArrowRight className="h-4 w-4" />
        </Link>
      ) : null}
    </section>
  );
}
