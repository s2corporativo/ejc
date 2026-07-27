import { useEffect, type ReactElement } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { Spinner } from "./UI";
import { toast } from "./Toast";
import { useAuth } from "../stores/auth";

function RouteLoading() {
  return (
    <div className="min-h-screen grid place-items-center bg-canvas">
      <Spinner />
    </div>
  );
}

/**
 * Redirecionamento de acesso negado COM feedback: em vez do <Navigate>
 * silencioso (que parecia bug — a tela "não abria"), avisa o usuário por
 * toast e então redireciona. Não altera nenhuma regra de acesso.
 */
function DeniedRedirect({
  to,
  message,
}: {
  to: string;
  message: string;
}): ReactElement {
  useEffect(() => {
    toast.info(message);
  }, [message]);
  return <Navigate to={to} replace />;
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
    return (
      <DeniedRedirect
        to="/portal"
        message="Esta área é da equipe do escritório — você foi levado ao Portal do Cliente."
      />
    );
  }
  return children;
}

export function PortalOnly({ children }: { children: ReactElement }) {
  const { status, user } = useAuth();
  if (status === "initializing") return <RouteLoading />;
  if (user?.role !== "cliente_externo") {
    return (
      <DeniedRedirect
        to="/"
        message="O Portal é exclusivo de clientes externos — você foi levado ao Início."
      />
    );
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
  if (status === "initializing") return <RouteLoading />;
  if (!user?.role || !roles.includes(user.role)) {
    return (
      <DeniedRedirect
        to="/"
        message="Seu perfil não tem acesso a este módulo — você foi levado ao Início."
      />
    );
  }
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
  if (status === "initializing") return <RouteLoading />;
  if (user?.role === "superadmin") return children;
  const current = new Set(user?.permissions ?? []);
  if (!permissions.every((permission) => current.has(permission))) {
    return (
      <DeniedRedirect
        to="/"
        message="Seu perfil não tem acesso a este módulo — você foi levado ao Início."
      />
    );
  }
  return children;
}
