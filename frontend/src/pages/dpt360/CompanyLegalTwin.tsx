import { useEffect, useState } from "react";
import { ArrowRight, Building2, FileSearch, ShieldCheck } from "lucide-react";
import { Link } from "react-router";
import { ErrorState, Spinner } from "../../components/UI";
import { getDptCompanyProfile, type DptCompanyProfile } from "./api";

export default function CompanyLegalTwin({ clientId }: { clientId: string }) {
  const [profile, setProfile] = useState<DptCompanyProfile | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    setError(false);
    setProfile(null);
    void getDptCompanyProfile(clientId)
      .then((data) => {
        if (active) setProfile(data);
      })
      .catch(() => {
        if (active) setError(true);
      });
    return () => {
      active = false;
    };
  }, [clientId]);

  if (error) {
    return <ErrorState message="Não foi possível carregar o Perfil Jurídico Vivo desta empresa." />;
  }
  if (!profile) {
    return (
      <div className="grid min-h-[180px] place-items-center rounded-2xl border border-slate-200 bg-white dark:border-white/10 dark:bg-white/[0.03]">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
              <Building2 className="h-4 w-4 text-amber-600" /> DPT Legal Twin
            </div>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-500 dark:text-slate-400">
              Representação factual construída a partir dos registros canônicos do EJC. Ela não cria um segundo cadastro e não transforma ausência de registro em regularidade jurídica.
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-700 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-300">
            <ShieldCheck className="h-3.5 w-3.5" /> Projeção rastreável
          </span>
        </div>

        <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {profile.twin.map((item) => (
            <div key={item.key} className="rounded-xl border border-slate-100 bg-slate-50/60 p-4 dark:border-white/10 dark:bg-white/[0.03]">
              <div className="flex items-start justify-between gap-3">
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.label}</div>
                <span className={`rounded-full px-2 py-1 text-[10px] font-semibold uppercase tracking-wide ${item.status === "com_dados" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-400/10 dark:text-emerald-300" : "bg-slate-100 text-slate-500 dark:bg-white/10 dark:text-slate-300"}`}>
                  {item.status === "com_dados" ? "Com dados" : item.status === "nao_aplicavel" ? "N/A" : "Sem dados"}
                </span>
              </div>
              <div className="mt-3 text-2xl font-semibold text-slate-950 dark:text-white">{item.registros}</div>
              {item.note ? <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">{item.note}</p> : null}
              {item.canonical_path ? (
                <Link to={item.canonical_path} className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-300">
                  Abrir fonte <ArrowRight className="h-3 w-3" />
                </Link>
              ) : null}
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
          <FileSearch className="h-4 w-4 text-amber-600" /> Saúde jurídica por área
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {profile.health.map((item) => (
            <div key={item.area} className="rounded-xl border border-slate-100 p-4 dark:border-white/10">
              <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">{item.area}</div>
              <div className="mt-2 text-xs font-semibold uppercase tracking-wide text-slate-400">{item.classificacao}</div>
              <p className="mt-2 text-xs leading-5 text-slate-500 dark:text-slate-400">{item.justificativa}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
