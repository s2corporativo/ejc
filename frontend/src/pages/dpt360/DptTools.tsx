import { ArrowRight, CheckCircle2, CircleSlash2 } from "lucide-react";
import { Link } from "react-router";

const TOOLS = [
  {
    area: "Tributário",
    available: true,
    items: [
      "Leitor de XML fiscal / NF-e",
      "Recuperação de créditos",
      "Relatório fiscal em PDF",
    ],
    evidence: "Backend confirmado: /api/tributario/fiscal/*",
    href: "/areas-de-atuacao/tributario",
  },
  {
    area: "Administrativo e Licitações",
    available: true,
    items: [
      "Mandado de segurança",
      "Reajuste de contrato administrativo",
      "Análise empresarial pelo Motor Jurídico",
    ],
    evidence:
      "Ferramentas administrativas confirmadas no EJC; PNCP está desativado nesta base.",
    href: "/areas-de-atuacao/administrativo",
  },
  {
    area: "Ambiental",
    available: true,
    items: [
      "Estratégia de auto de infração",
      "Licenciamento",
      "TAC ambiental",
      "Reserva legal",
      "Crimes ambientais",
    ],
    evidence:
      "Backend confirmado: /api/ambiental/estrategia/* + vertical ambiental existente.",
    href: "/areas-de-atuacao/ambiental",
  },
  {
    area: "Trabalhista Empresarial",
    available: true,
    items: [
      "Liquidação de sentença",
      "Cálculo determinístico com Selic real",
      "Radar de passivo via casos/documentos",
    ],
    evidence: "Backend confirmado: /api/trabalhista/liquidacao/*",
    href: "/areas-de-atuacao/trabalhista",
  },
  {
    area: "LGPD",
    available: true,
    items: ["ROPA por cliente", "Avaliação de risco", "RIPD em Visual Law"],
    evidence:
      "Backend confirmado: /api/lgpd/registros/*, com escopo por cliente e audit log.",
    href: "/areas-de-atuacao/digital_lgpd",
  },
  {
    area: "Governança de IA",
    available: true,
    items: [
      "Governança central de provedores",
      "Sanitização",
      "HITL",
      "Logs de IA",
    ],
    evidence:
      "Núcleo e governança de IA já existentes; inventário empresarial específico será enriquecido depois da persistência canônica.",
    href: "/governanca-ia",
  },
  {
    area: "PNCP / captura de licitações",
    available: false,
    items: ["Consulta/captura PNCP"],
    evidence:
      "A main atual registra PNCP como removido/desativado. O DPT não recria um conector paralelo.",
    href: "/areas-de-atuacao/administrativo",
  },
] as const;

export default function DptTools() {
  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]">
        <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
          Ferramentas Empresariais
        </h2>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          Catálogo de capacidades já existentes no EJC. O DPT funciona como
          cockpit e não cria calculadoras ou verticais duplicadas.
        </p>
      </section>
      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {TOOLS.map((tool) => (
          <section
            key={tool.area}
            className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-white/[0.03]"
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="font-semibold text-slate-900 dark:text-white">
                {tool.area}
              </h3>
              {tool.available ? (
                <CheckCircle2 className="h-4 w-4 text-emerald-600" />
              ) : (
                <CircleSlash2 className="h-4 w-4 text-slate-400" />
              )}
            </div>
            <ul className="mt-3 space-y-1.5 text-sm text-slate-600 dark:text-slate-300">
              {tool.items.map((item) => (
                <li key={item}>• {item}</li>
              ))}
            </ul>
            <p className="mt-3 text-xs leading-5 text-slate-400">
              {tool.evidence}
            </p>
            <Link
              to={tool.href}
              className="mt-4 inline-flex items-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-300"
            >
              Abrir workspace canônico <ArrowRight className="h-3 w-3" />
            </Link>
          </section>
        ))}
      </div>
    </div>
  );
}
