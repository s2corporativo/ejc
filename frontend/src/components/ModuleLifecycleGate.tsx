import { useEffect } from "react";
import { Link, Navigate, useLocation } from "react-router";
import { AlertTriangle, ArrowLeft, Route } from "lucide-react";
import { lifecycleForPath, safeReplacementRoute } from "../lib/moduleLifecycle";
import {
  MODULE_LIFECYCLE_TIMEOUT_MS,
  useModuleLifecycleStore,
} from "../stores/moduleLifecycle";
import { Spinner } from "./UI";

export default function ModuleLifecycleGate({
  children,
}: {
  children: React.ReactNode;
}) {
  const location = useLocation();
  const { settings, loaded, load, liberarPorTimeout } =
    useModuleLifecycleStore();

  useEffect(() => {
    void load();
  }, [load]);

  // Teto de bloqueio: os children do gate são o <Outlet/> global, então um
  // request pendente para sempre inutilizaria a aplicação inteira. Esgotado o
  // limite, libera pelo mesmo caminho do catch do store (manifesto local).
  // Dispara uma única vez — `liberarPorTimeout` é idempotente e o efeito só
  // reagenda quando `loaded` muda, sem loop de re-render.
  useEffect(() => {
    if (loaded) return;
    const t = setTimeout(liberarPorTimeout, MODULE_LIFECYCLE_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, [loaded, liberarPorTimeout]);

  if (!loaded) {
    // FLX-023: enquanto o lifecycle não carrega, NÃO monta a página — sem
    // isso, um módulo desabilitado montava e disparava requests antes do
    // bloqueio. O load() do store é fail-open (termina com loaded=true mesmo
    // em erro de rede) e o timeout acima cobre o request pendente, então este
    // placeholder nunca fica preso.
    return (
      <div className="grid min-h-[40vh] place-items-center">
        <Spinner />
      </div>
    );
  }

  const lifecycle = lifecycleForPath(location.pathname, settings);
  if (!lifecycle || (lifecycle.enabled && lifecycle.status !== "disabled")) {
    return <>{children}</>;
  }

  const replacement = safeReplacementRoute(
    location.pathname,
    lifecycle.replacement_route,
  );
  if (replacement) {
    return (
      <Navigate
        to={replacement}
        replace
        state={{
          moduleDisabled: lifecycle.module_key,
          reason: lifecycle.reason,
        }}
      />
    );
  }

  return (
    <div className="mx-auto max-w-2xl py-12">
      <div className="card p-8 text-center">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-warn-50 text-warn-700">
          <AlertTriangle className="h-7 w-7" />
        </span>
        <h1 className="mt-5 text-xl font-semibold text-slate-900">
          Módulo temporariamente indisponível
        </h1>
        <p className="mt-2 text-sm leading-6 text-slate-500">
          {lifecycle.reason ||
            "Este módulo foi desabilitado pela administração do EJC."}
        </p>
        {lifecycle.removal_date && (
          <p className="mt-2 text-xs text-slate-400">
            Data de remoção planejada: {lifecycle.removal_date}
          </p>
        )}
        <div className="mt-6 flex justify-center gap-2">
          <Link to="/" className="btn-primary">
            <ArrowLeft className="h-4 w-4" /> Voltar ao Dashboard
          </Link>
          <Link to="/ajuda" className="btn-secondary">
            <Route className="h-4 w-4" /> Central de Ajuda
          </Link>
        </div>
      </div>
    </div>
  );
}
