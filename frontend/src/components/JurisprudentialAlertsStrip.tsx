import {
  AlertTriangle,
  ChevronRight,
  ExternalLink,
  Gavel,
  Radar,
} from "lucide-react";
import { Link } from "react-router";

type AlertKind = "Jurisprudência" | "Repetitivo" | "Precedente administrativo" | "Legislação";

type LegalAlert = {
  id: string;
  tribunal: string;
  referencia: string;
  data: string;
  area: string;
  prioridade: "P0" | "P1";
  kind: AlertKind;
  estado: string;
  titulo: string;
  resumo: string;
  impacto: string;
  acao: string;
  fonte: string;
};

/**
 * Bootstrap curado do Radar Jurídico no dashboard principal.
 *
 * Os registros abaixo foram conferidos em fontes oficiais em 07/09/2026.
 * Eles são somente informativos e não alteram teses, casos, processos ou
 * peças automaticamente. A decisão de revisão/validação permanece humana.
 * Quando o Radar Jurisprudencial canônico persistir eventos, este componente
 * deve consumir essa API em vez desta curadoria estática.
 */
const ALERTAS: LegalAlert[] = [
  {
    id: "stj-tema-1177",
    tribunal: "STJ",
    referencia: "Tema 1.177",
    data: "01/09/2026",
    area: "Processo Civil / Coletivo",
    prioridade: "P0",
    kind: "Jurisprudência",
    estado: "Repetitivo julgado — tese vinculante",
    titulo: "ACP sindical: honorários sucumbenciais contra a União",
    resumo:
      "A Primeira Seção fixou que, por simetria, a isenção do art. 18 da Lei 7.347/1985 impede a condenação da União, quando vencida em ação civil pública ajuizada por sindicato, ao pagamento de honorários sucumbenciais, salvo comprovada má-fé.",
    impacto:
      "Enfraquece teses de ataque que peçam honorários contra a União apenas pela procedência da ACP e fortalece a defesa fazendária.",
    acao:
      "Criar/atualizar a tese ACP > sindicato > honorários > União e marcar como repetitivo obrigatório (CPC, art. 927, III).",
    fonte: "https://scon.stj.jus.br/SCON/GetPDFINFJ?edicao=0899",
  },
  {
    id: "stj-tema-1473",
    tribunal: "STJ",
    referencia: "Tema 1.473",
    data: "31/08/2026",
    area: "Tributário / Simples Nacional",
    prioridade: "P1",
    kind: "Repetitivo",
    estado: "Afetado — tese de mérito ainda não fixada",
    titulo: "Gorjetas e base de cálculo do Simples Nacional",
    resumo:
      "A Primeira Seção afetou os REsp 2.239.211/PE, 2.239.811/PB e 2.261.206/CE para definir se gorjetas recebidas e repassadas aos empregados integram a base de cálculo do Simples Nacional.",
    impacto:
      "A matéria deve ser tratada como controvertida; não é seguro apresentar inclusão ou exclusão das gorjetas como entendimento consolidado.",
    acao:
      "Cadastrar como PENDING_BINDING_PRECEDENT e disparar revalidação quando o mérito do repetitivo for julgado.",
    fonte: "https://scon.stj.jus.br/SCON/GetPDFINFJ?edicao=0899",
  },
  {
    id: "tcu-acordao-2321-2026",
    tribunal: "TCU",
    referencia: "Acórdão 2321/2026-Plenário",
    data: "02/09/2026",
    area: "Administrativo / Licitações",
    prioridade: "P0",
    kind: "Precedente administrativo",
    estado: "Precedente administrativo relevante",
    titulo: "Conflito de interesses e avaliação objetiva de amostras",
    resumo:
      "O TCU reconheceu conflito de interesses em licitação com participação de empresa do mesmo grupo econômico de prestadora de apoio técnico ao órgão e apontou vícios na avaliação de amostras realizada sem critérios objetivos e somente na fase recursal.",
    impacto:
      "Fortalece impugnações e recursos sobre impedimento objetivo, segregação de funções e nulidade de avaliação de amostras sem critérios previamente definidos.",
    acao:
      "Criar/atualizar teses sobre arts. 9º e 14 da Lei 14.133/2021 e sobre critérios objetivos para amostras; não classificar como precedente judicial vinculante.",
    fonte: "https://pesquisa.apps.tcu.gov.br/resultado/acordao-completo/Integridade",
  },
  {
    id: "decreto-13108-2026",
    tribunal: "PRESIDÊNCIA DA REPÚBLICA",
    referencia: "Decreto 13.108/2026",
    data: "01/09/2026",
    area: "Consumidor / Eventos",
    prioridade: "P1",
    kind: "Legislação",
    estado: "Norma nova — vigência parcialmente escalonada",
    titulo: "Comercialização de ingressos para eventos",
    resumo:
      "O decreto regulamenta o CDC para venda de ingressos, inclusive em sites e aplicativos, com deveres de transparência, prevenção de aquisição massiva automatizada, rastreabilidade e repressão à revenda especulativa.",
    impacto:
      "Cria novos fundamentos normativos para teses de consumidor sobre taxas, transparência, segurança, revenda e responsabilidade de comercializadores de ingressos.",
    acao:
      "Criar o núcleo Consumidor > Eventos > Ingressos e observar a vigência específica dos dispositivos antes de usar a norma em peças.",
    fonte: "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/d13108.htm",
  },
  {
    id: "decreto-13109-2026",
    tribunal: "PRESIDÊNCIA DA REPÚBLICA",
    referencia: "Decreto 13.109/2026",
    data: "01/09/2026",
    area: "Consumidor / Eventos",
    prioridade: "P1",
    kind: "Legislação",
    estado: "Norma vigente",
    titulo: "Acesso à água potável em eventos",
    resumo:
      "O decreto garante entrada com recipientes de água, sujeita a restrições de segurança, e exige disponibilização gratuita de água potável em eventos com previsão superior a mil participantes.",
    impacto:
      "Reforça teses consumeristas e de responsabilidade de organizadores de eventos, inclusive quanto a práticas abusivas e dever de segurança.",
    acao:
      "Adicionar ao Banco de Teses de consumidor/eventos e relacionar a responsabilidade civil, administrativa e aos deveres de informação e segurança.",
    fonte: "https://www.planalto.gov.br/ccivil_03/_ato2023-2026/2026/decreto/d13109.htm",
  },
];

function prioridadeClasses(prioridade: LegalAlert["prioridade"]) {
  if (prioridade === "P0") {
    return "bg-red-50 text-red-700 dark:bg-red-400/10 dark:text-red-200";
  }
  return "bg-amber-50 text-amber-800 dark:bg-amber-400/10 dark:text-amber-200";
}

export default function JurisprudentialAlertsStrip() {
  return (
    <section
      aria-labelledby="alertas-juridicos-title"
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
                id="alertas-juridicos-title"
                className="text-xs font-semibold text-slate-950 dark:text-white"
              >
                Radar Jurídico — atualizações da semana
              </h2>
              <span className="rounded-full border border-amber-200 bg-white px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-amber-800 dark:border-amber-400/20 dark:bg-white/[0.04] dark:text-amber-200">
                {ALERTAS.length} relevantes
              </span>
            </div>
            <p className="mt-0.5 text-[10px] text-slate-500 dark:text-slate-400">
              STF/STJ/TST/TJMG/TRT3/TRF6/TNU/TCU/CARF + legislação · fontes oficiais conferidas em 07/09/2026 · revisão humana obrigatória.
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

      <div className="grid gap-px bg-slate-100 dark:bg-white/10 xl:grid-cols-2">
        {ALERTAS.map((alerta) => (
          <article
            key={alerta.id}
            className="bg-white px-4 py-4 dark:bg-slate-950/70"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span
                className={`rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.12em] ${prioridadeClasses(alerta.prioridade)}`}
              >
                {alerta.prioridade}
              </span>
              <span className="rounded-full border border-slate-200 px-2 py-0.5 text-[9px] font-semibold text-slate-600 dark:border-white/10 dark:text-slate-300">
                {alerta.kind}
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
          Nenhum aviso altera automaticamente tese, processo, estratégia ou peça. Mudança de status jurídico exige validação humana no Banco de Teses canônico.
        </span>
      </div>
    </section>
  );
}
