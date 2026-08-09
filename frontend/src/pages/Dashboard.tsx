import { BellRing, ChevronRight, Network } from "lucide-react";
import { Link } from "react-router";
import { useAuth } from "../stores/auth";
import DashboardUltra from "./DashboardUltra";

const PAPEIS_PJE = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
]);

/**
 * Entrada estável da rota principal.
 *
 * O acesso PJe é deliberadamente apresentado como comunicação/consulta:
 * - intimações já são operadas pela Central (/atividades?tipo=intimacao);
 * - sincronização MNI é contextual ao caso e protegida por ownership;
 * - peticionamento eletrônico NÃO está implementado nesta fase do backend.
 *
 * As implementações anteriores do dashboard permanecem preservadas para
 * rollback sem alteração de rotas ou contratos de API.
 */
export default function Dashboard() {
  const user = useAuth((state) => state.user);
  const podeUsarPje = Boolean(user?.role && PAPEIS_PJE.has(user.role));

  return (
    <div>
      {podeUsarPje && (
        <div className="mb-3 flex flex-col gap-3 rounded-2xl border border-slate-200/80 bg-white/90 px-4 py-3 shadow-sm backdrop-blur dark:border-white/10 dark:bg-slate-950/55 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-slate-950 text-[#e5ce7f] dark:bg-white/10">
              <Network className="h-4 w-4" aria-hidden="true" />
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <strong className="text-xs font-semibold text-slate-900 dark:text-white">
                  PJe / Comunicações processuais
                </strong>
                <span className="rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-amber-800 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-200">
                  consulta e captura
                </span>
              </div>
              <p className="mt-0.5 truncate text-[10px] text-slate-500 dark:text-slate-400">
                Intimações Comunica PJe/DJEN e sincronização processual
                vinculada ao caso.
              </p>
            </div>
          </div>

          <Link
            to="/atividades?tipo=intimacao"
            className="inline-flex shrink-0 items-center justify-center gap-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-[10px] font-semibold text-slate-700 transition hover:border-amber-300 hover:bg-amber-50 hover:text-amber-900 dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-200 dark:hover:border-amber-300/30 dark:hover:bg-amber-300/10"
          >
            <BellRing className="h-3.5 w-3.5" aria-hidden="true" />
            Abrir intimações
            <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        </div>
      )}

      <DashboardUltra />
    </div>
  );
}
