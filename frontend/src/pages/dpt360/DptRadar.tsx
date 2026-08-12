import { useEffect, useState } from "react";
import { ExternalLink, Radar, ShieldAlert } from "lucide-react";
import { getDptRadarToday, type DptRadarToday } from "./radarApi";

const AREA_ORDER = [
  "tributario",
  "ambiental",
  "administrativo",
  "trabalhista",
  "lgpd_ia",
  "geral",
];

function orderedAreas(data: DptRadarToday): Array<[string, number]> {
  return Object.entries(data.por_area).sort(([left], [right]) => {
    const leftIndex = AREA_ORDER.indexOf(left);
    const rightIndex = AREA_ORDER.indexOf(right);
    const safeLeft = leftIndex < 0 ? AREA_ORDER.length : leftIndex;
    const safeRight = rightIndex < 0 ? AREA_ORDER.length : rightIndex;
    return safeLeft - safeRight || left.localeCompare(right, "pt-BR");
  });
}

export default function DptRadar() {
  const [data, setData] = useState<DptRadarToday | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    void getDptRadarToday(24)
      .then((value) => active && setData(value))
      .catch(() => active && setError(true));
    return () => {
      active = false;
    };
  }, []);

  if (error)
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
        Radar indisponível. Nenhuma mudança jurídica foi presumida.
      </div>
    );
  if (!data)
    return (
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-sm text-slate-500">
        Carregando Radar Jurídico…
      </div>
    );

  const areas = orderedAreas(data);

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <div className="flex items-start gap-3">
          <span className="grid h-11 w-11 place-items-center rounded-xl bg-slate-950 text-amber-300">
            <Radar className="h-5 w-5" />
          </span>
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Radar Jurídico — Hoje
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              {data.total_publicacoes} publicação(ões) coletada(s) nas últimas{" "}
              {data.periodo_horas}h
              {data.cobertura === "parcial" && (
                <span className="ml-2 inline-block rounded-full bg-amber-100 px-2 py-1 text-xs font-semibold text-amber-800 dark:bg-amber-400/10 dark:text-amber-200">
                  Classificação parcial
                </span>
              )} · {data.empresas_potencialmente_impactadas}{" "}
              empresa(s) com possível impacto objetivo.
            </p>
            <p className="mt-1 text-xs text-slate-400">
              {data.publicacoes_classificadas} de {data.total_publicacoes}{" "}
              publicação(ões) foram classificadas para área/impacto nesta
              execução; a lista detalhada exibe até 100 itens.
            </p>
          </div>
        </div>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">
          {areas.length ? (
            areas.map(([area, total]) => (
              <div
                key={area}
                className="rounded-xl bg-slate-50 p-3 dark:bg-white/[0.03]"
              >
                <div className="text-xs font-semibold capitalize text-slate-500">
                  {area.replace(/_/g, "/")}
                </div>
                <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-white">
                  {total}
                </div>
              </div>
            ))
          ) : (
            <div className="text-sm text-slate-400">
              Nenhuma área classificada no período.
            </div>
          )}
        </div>
        <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50/60 p-3 text-xs leading-5 text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200">
          <ShieldAlert className="mr-1 inline h-3.5 w-3.5" />
          {data.regra_impacto} Vigência permanece “a confirmar” até a
          reconciliação do gate #895.
        </div>
      </section>

      <section className="space-y-3">
        {data.itens.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-slate-200 bg-white p-8 text-sm text-slate-500">
            Nenhuma publicação foi localizada no período consultado.
          </div>
        ) : (
          data.itens.map((item) => (
            <article
              key={item.id}
              className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]"
            >
              <div className="flex flex-wrap items-center gap-2 text-[10px] font-semibold uppercase tracking-wide text-slate-400">
                <span>{item.area}</span>
                <span>•</span>
                <span>{item.fonte || "fonte não rotulada"}</span>
                <span>•</span>
                <span>Vigência: {item.vigencia}</span>
              </div>
              <h3 className="mt-2 text-base font-semibold text-slate-900 dark:text-white">
                {item.titulo || "Publicação sem título"}
              </h3>
              {item.resumo ? (
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  {item.resumo}
                </p>
              ) : null}
              {item.impactos.length ? (
                <div className="mt-3 space-y-2">
                  {item.impactos.map((impact) => (
                    <div
                      key={impact.client_id}
                      className="rounded-xl border border-amber-200 bg-amber-50/50 p-3 text-xs text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100"
                    >
                      <strong>{impact.empresa}</strong> — possível impacto,
                      aderência {impact.aderencia}. {impact.fundamento}
                    </div>
                  ))}
                </div>
              ) : null}
              {item.link ? (
                <a
                  href={item.link}
                  target="_blank"
                  rel="noreferrer"
                  className="mt-3 inline-flex items-center gap-1 text-xs font-semibold text-amber-700"
                >
                  Abrir fonte <ExternalLink className="h-3 w-3" />
                </a>
              ) : null}
            </article>
          ))
        )}
      </section>
    </div>
  );
}
