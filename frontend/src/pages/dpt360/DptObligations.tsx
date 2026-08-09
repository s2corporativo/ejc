import { CalendarClock, ChevronRight } from "lucide-react";
import { Link } from "react-router";
import type { DptDashboard } from "./api";

export default function DptObligations({ data }: { data: DptDashboard }) {
  const companyByCase = new Map(
    data.cases.map((caseItem) => [
      caseItem.id,
      data.companies.find((company) => company.id === caseItem.client_id)
        ?.nome || "Empresa",
    ]),
  );
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex items-start gap-3">
          <CalendarClock className="mt-0.5 h-5 w-5 text-amber-600" />
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Agenda de Obrigações Empresariais
            </h2>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              Nesta pilha, a visão consolida somente prazos canônicos vinculados
              a casos empresariais. Licenças, TACs, condicionantes e obrigações
              contratuais recorrentes ainda não recebem persistência própria
              para não criar migration incompatível.
            </p>
          </div>
        </div>
      </section>
      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-slate-900 dark:text-white">
            Prazos empresariais canônicos
          </h3>
          <span className="text-xs text-slate-400">
            {data.deadlines.length}
          </span>
        </div>
        {data.deadlines.length === 0 ? (
          <p className="mt-4 text-sm text-slate-500">
            Nenhum prazo empresarial pendente foi localizado.
          </p>
        ) : (
          <div className="mt-3 divide-y divide-slate-100 dark:divide-white/10">
            {data.deadlines.map((item) => (
              <Link
                key={item.id}
                to={`/atividades?tipo=prazo&caso=${item.case_id}`}
                className="flex items-center justify-between gap-3 py-3"
              >
                <div>
                  <div className="text-sm font-semibold text-slate-900 dark:text-white">
                    {item.titulo}
                  </div>
                  <div className="mt-1 text-xs text-slate-400">
                    {companyByCase.get(item.case_id)} · {item.data_prazo} ·{" "}
                    {item.status}
                  </div>
                </div>
                <ChevronRight className="h-4 w-4 text-slate-300" />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
