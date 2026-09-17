import type { ReactElement } from "react";
import { Navigate, useLocation } from "react-router";
import { Spinner } from "./UI";
import { useAuth } from "../stores/auth";

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
  if (status === "initializing") return <RouteLoading />;
  if (!user?.role || !roles.includes(user.role)) {
    return <Navigate to="/" replace />;
  }
  return children;
}
