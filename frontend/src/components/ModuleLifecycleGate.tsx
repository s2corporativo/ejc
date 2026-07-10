import { useEffect } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { AlertTriangle, ArrowLeft, Route } from "lucide-react";
import { lifecycleForPath, safeReplacementRoute } from "../lib/moduleLifecycle";
import { useModuleLifecycleStore } from "../stores/moduleLifecycle";

export default function ModuleLifecycleGate({
  children,
}: {
  children: React.ReactNode;
}) {
  const location = useLocation();
  const { settings, loaded, load } = useModuleLifecycleStore();

  useEffect(() => {
    void load();
  }, [load]);

  if (!loaded) return <>{children}</>;

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
