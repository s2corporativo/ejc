import {
  AlertTriangle,
  ChevronRight,
  ExternalLink,
  Gavel,
  Radar,
} from "lucide-react";
import { Link } from "react-router";

/**
 * Bootstrap curado do Radar Jurisprudencial no dashboard principal.
 *
 * Estes registros são deliberadamente explícitos e auditáveis: foram
 * conferidos em fonte oficial em 31/08/2026 e NÃO alteram teses, casos ou
 * peças automaticamente. Quando o Radar Jurisprudencial canônico passar a
 * persistir eventos, este componente deve consumir essa API em vez desta
 * curadoria estática.
 */
const ALERTAS = [
  {
    id: "stj-tema-1469",
    tribunal: "STJ",
    referencia: "Tema 1.469",
    data: "28/08/2026",
    area: "Administrativo / Financeiro",
    prioridade: "ALTA",
    estado: "Repetitivo afetado — tese ainda não fixada",
    titulo: "Transferências voluntárias e pendências fiscais",
    resumo:
      "A Primeira Seção afetou os REsp 2.242.339 e 2.245.522 para definir o alcance das exceções de educação, saúde e assistência social nas transferências voluntárias e examinar a aplicação do art. 26 da Lei 10.522/2002.",
    impacto:
      "Não tratar como tese vinculante de mérito enquanto o repetitivo não for julgado.",
    acao:
      "Manter a tese relacionada como pendente de precedente vinculante e revalidar após o julgamento.",
    fonte:
      "https://www.stj.jus.br/sites/portalp/Paginas/Comunicacao/Noticias/2026/28082026-Repetitivo-discute-quais-acoes-permitem-transferencias-voluntarias-para-ente-com-pendencias-fiscais.aspx",
  },
  {
    id: "tcu-acordao-2218-2026",
    tribunal: "TCU",
    referencia: "Acórdão 2218/2026-Plenário",
    data: "19/08/2026",
    area: "Administrativo / Licitações",
    prioridade: "ALTA",
    estado: "Precedente administrativo relevante",
    titulo: "Limites da diligência na habilitação — art. 64 da Lei 14.133/2021",
    resumo:
      "O TCU distinguiu a apresentação posterior de documento que comprova condição já existente da criação extemporânea de requisito de habilitação inexistente no momento próprio.",
    impacto:
      "Reforça a distinção entre saneamento documental de condição preexistente e constituição posterior de requisito de habilitação.",
    acao:
      "Atualizar as teses de ataque e defesa sobre diligência, habilitação e formalismo moderado; não classificar como precedente judicial vinculante.",
    fonte: "https://portal.tcu.gov.br/imprensa/noticias/secao-das-sessoes",
  },
] as const;

export default function JurisprudentialAlertsStrip() {
  return (
    <section
      aria-labelledby="alertas-jurisprudenciais-title"
      className="mb-3 overflow-hidden rounded-2xl border border-amber-200/80 bg-white shadow-sm dark:border-amber-400/20 dark:bg-slate-950/55"
    >
      <div className="flex flex-col gap-3 border-b border-amber-100 bg-amber-50/70 px-4 py-3 dark:border-amber-400/10 dark:bg-amber-400/[0.06] sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-amber-100 text-amber-800 dark:bg-amber-400/10 dark:text-amber-200">
            <Gavel className="h-4 w-4" aria-hidden="true" />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2
                id="alertas-jurisprudenciais-title"
                className="text-xs font-semibold text-slate-950 dark:text-white"
              >
                Alertas jurisprudenciais
              </h2>
              <span className="rounded-full border border-amber-200 bg-white px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-amber-800 dark:border-amber-400/20 dark:bg-white/[0.04] dark:text-amber-200">
                2 relevantes
              </span>
            </div>
            <p className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400">
              Curadoria jurídica semanal · fontes oficiais conferidas em
              31/08/2026 · revisão humana obrigatória.
            </p>
          </div>
        </div>

        <Link
          to="/dpt360/radar"
          className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-amber-200 bg-white px-3 py-2 text-[10px] font-semibold text-amber-900 transition hover:bg-amber-100 dark:border-amber-400/20 dark:bg-white/[0.04] dark:text-amber-100 dark:hover:bg-amber-400/10"
        >
          <Radar className="h-3.5 w-3.5" aria-hidden="true" />
          Abrir Radar Jurídico
          <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        </Link>
      </div>

      <div className="grid gap-px bg-slate-100 dark:bg-white/10 lg:grid-cols-2">
        {ALERTAS.map((alerta) => (
          <article
            key={alerta.id}
            className="bg-white px-4 py-4 dark:bg-slate-950/70"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-red-50 px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.12em] text-red-700 dark:bg-red-400/10 dark:text-red-200">
                {alerta.prioridade}
              </span>
              <span className="text-[10px] font-semibold text-slate-700 dark:text-slate-200">
                {alerta.tribunal} · {alerta.referencia}
              </span>
              <span className="text-[10px] text-slate-400">{alerta.data}</span>
            </div>

            <h3 className="mt-2 text-sm font-semibold leading-5 text-slate-950 dark:text-white">
              {alerta.titulo}
            </h3>
            <p className="mt-1 text-[10px] font-medium uppercase tracking-[0.08em] text-slate-400">
              {alerta.area} · {alerta.estado}
            </p>
            <p className="mt-2 text-xs leading-5 text-slate-600 dark:text-slate-300">
              {alerta.resumo}
            </p>

            <div className="mt-3 rounded-xl border border-slate-100 bg-slate-50/80 p-3 dark:border-white/10 dark:bg-white/[0.03]">
              <p className="text-[10px] leading-4 text-slate-600 dark:text-slate-300">
                <strong className="text-slate-800 dark:text-slate-100">
                  Impacto no Banco de Teses:
                </strong>{" "}
                {alerta.impacto}
              </p>
              <p className="mt-1 text-[10px] leading-4 text-slate-600 dark:text-slate-300">
                <strong className="text-slate-800 dark:text-slate-100">
                  Ação recomendada:
                </strong>{" "}
                {alerta.acao}
              </p>
            </div>

            <a
              href={alerta.fonte}
              target="_blank"
              rel="noreferrer"
              className="mt-3 inline-flex items-center gap-1.5 text-[10px] font-semibold text-amber-800 hover:underline dark:text-amber-300"
            >
              Fonte oficial
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </article>
        ))}
      </div>

      <div className="flex items-start gap-2 border-t border-slate-100 px-4 py-2.5 text-[10px] leading-4 text-slate-500 dark:border-white/10 dark:text-slate-400">
        <AlertTriangle
          className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-600 dark:text-amber-300"
          aria-hidden="true"
        />
        <span>
          Nenhum aviso altera automaticamente tese, processo, estratégia ou
          peça. Mudança de status jurídico exige validação humana no Banco de
          Teses canônico.
        </span>
      </div>
    </section>
  );
}
