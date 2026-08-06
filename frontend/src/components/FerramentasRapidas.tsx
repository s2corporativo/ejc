import { Link } from "react-router";
import {
  ArrowRight,
  Banknote,
  Car,
  FileSignature,
  HardHat,
  Receipt,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { canRoleAccessPath } from "../config/moduleRegistry";
import { CANONICAL_ROUTES } from "../config/canonicalRoutes";
import { SectionCard } from "./UI";

type Atalho = {
  titulo: string;
  descricao: string;
  destino: string;
  icon: LucideIcon;
};

// Deep-links reais: os hubs de ramo vivem na rota canônica
// /areas-de-atuacao/<slug> (RamoBase via moduleRegistry "ramo-detalhe");
// os slugs vêm de pages/ramos/ramosConfig.ts. "Análise de contrato" abre
// o painel Defesas e Revisões em /ferramentas via query ?abrir=defesas.
export const ATALHOS_FERRAMENTAS: Atalho[] = [
  {
    titulo: "Cálculo trabalhista",
    descricao: "Verbas rescisórias, prazos e depósito recursal",
    destino: `${CANONICAL_ROUTES.areasAtuacao}/trabalhista`,
    icon: HardHat,
  },
  {
    titulo: "Juros bancários",
    descricao: "Revisão de juros, CET e contratos bancários",
    destino: `${CANONICAL_ROUTES.areasAtuacao}/bancario`,
    icon: Banknote,
  },
  {
    titulo: "Análise tributária",
    descricao: "Autos de infração, execução fiscal e defesas",
    destino: `${CANONICAL_ROUTES.areasAtuacao}/tributario`,
    icon: Receipt,
  },
  {
    titulo: "Multas de trânsito",
    descricao: "Defesa prévia, JARI, suspensão e cassação da CNH",
    destino: `${CANONICAL_ROUTES.areasAtuacao}/transito`,
    icon: Car,
  },
  {
    titulo: "Análise de contrato",
    descricao: "Cláusulas abusivas e revisões com cálculo rastreável",
    destino: "/ferramentas?abrir=defesas",
    icon: FileSignature,
  },
  {
    titulo: "Todas as ferramentas",
    descricao: "Hubs de todos os ramos, calculadoras e guias",
    destino: CANONICAL_ROUTES.areasAtuacao,
    icon: Wrench,
  },
];

/**
 * Atalhos de 1 clique do Dashboard para as ferramentas jurídicas que já
 * existem nos hubs de ramo e em "Mais Ferramentas". Sem chamadas de API —
 * apenas navegação. Visível somente para papéis com acesso a
 * /areas-de-atuacao (ROLES.juridico via moduleRegistry).
 */
export default function FerramentasRapidas({ role }: { role?: string }) {
  if (!canRoleAccessPath(role, CANONICAL_ROUTES.areasAtuacao)) return null;

  return (
    <SectionCard
      title="Ferramentas jurídicas"
      subtitle="Calculadoras e análises dos ramos, a um clique do plantão."
    >
      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {ATALHOS_FERRAMENTAS.map((atalho) => {
          const Icon = atalho.icon;
          return (
            <Link
              key={atalho.destino}
              to={atalho.destino}
              className="group flex items-start gap-3 rounded-xl border border-black/[0.04] bg-white p-3 transition-colors hover:bg-slate-50 dark:border-white/[0.07] dark:bg-white/[0.03] dark:hover:bg-white/[0.06]"
            >
              <div className="mt-0.5 rounded-lg bg-primary-50 p-2 text-primary-700 dark:bg-primary-400/10 dark:text-primary-300">
                <Icon className="h-4 w-4" aria-hidden="true" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {atalho.titulo}
                </div>
                <div className="mt-0.5 line-clamp-1 text-xs text-slate-500 dark:text-slate-400">
                  {atalho.descricao}
                </div>
              </div>
              <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-slate-300 transition-colors group-hover:text-primary-600 dark:text-slate-500 dark:group-hover:text-primary-300" />
            </Link>
          );
        })}
      </div>
    </SectionCard>
  );
}
