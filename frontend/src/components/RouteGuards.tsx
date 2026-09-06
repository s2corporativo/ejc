import { useEffect, type ReactElement } from "react";
import { Navigate, useLocation } from "react-router";
import { Spinner } from "./UI";
import { toast } from "./Toast";
import { useAuth } from "../stores/auth";

export const MENSAGEM_ACESSO_NEGADO =
  "Você não tem permissão para acessar esta área. Voltamos para a página inicial.";

/** FE-06: avisa UMA vez (efeito, não no render) antes do redirect silencioso. */
function useAvisoAcessoNegado(negado: boolean) {
  useEffect(() => {
    if (negado) toast.info(MENSAGEM_ACESSO_NEGADO);
  }, [negado]);
}

function RouteLoading() {
  return (
    <div className="min-h-screen grid place-items-center bg-canvas">
      <Spinner />
    </div>
  );
}

export function Protected({ children }: { children: ReactElement }) {
  const { status, user } = useAuth();
  const location = useLocation();

  if (status === "initializing") return <RouteLoading />;
  if (status !== "authenticated" || !user) {
    return (
      <Navigate
        to="/login"
        replace
        state={{ from: `${location.pathname}${location.search}` }}
      />
    );
  }
  return children;
}

export function StaffOnly({ children }: { children: ReactElement }) {
  const { status, user } = useAuth();
  if (status === "initializing") return <RouteLoading />;
  if (user?.role === "cliente_externo") {
    return <Navigate to="/portal" replace />;
  }
  return children;
}

export function PortalOnly({ children }: { children: ReactElement }) {
  const { status, user } = useAuth();
  if (status === "initializing") return <RouteLoading />;
  if (user?.role !== "cliente_externo") {
    return <Navigate to="/" replace />;
  }
  return children;
}

export function RoleOnly({
  roles,
  children,
}: {
  roles: readonly string[];
  children: ReactElement;
}) {
  const { status, user } = useAuth();
  const negado =
    status !== "initializing" && (!user?.role || !roles.includes(user.role));
  useAvisoAcessoNegado(negado);
  if (status === "initializing") return <RouteLoading />;
  if (negado) return <Navigate to="/" replace />;
  return children;
}

export function PermissionOnly({
  permissions,
  children,
}: {
  permissions: readonly string[];
  children: ReactElement;
}) {
  const { status, user } = useAuth();
  const current = new Set(user?.permissions ?? []);
  const negado =
    status !== "initializing" &&
    user?.role !== "superadmin" &&
    !permissions.every((permission) => current.has(permission));
  useAvisoAcessoNegado(negado);
  if (status === "initializing") return <RouteLoading />;
  if (negado) return <Navigate to="/" replace />;
  return children;
}
