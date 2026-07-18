import { lazy, Suspense, useEffect } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useParams,
} from "react-router-dom";
import { ToastContainer } from "./components/Toast";
import { Spinner } from "./components/UI";
import ErrorBoundary from "./components/ErrorBoundary";
import EntradaUniversalGlobal from "./components/EntradaUniversalGlobal";
import Layout from "./components/Layout";
import PortalLayout from "./components/PortalLayout";
import {
  PortalOnly,
  Protected,
  RoleOnly,
  StaffOnly,
} from "./components/RouteGuards";
import { LEGACY_REDIRECTS, STAFF_ROUTES } from "./config/moduleRegistry";
import { useAuth } from "./stores/auth";
import Login from "./pages/LoginModern";

const RecuperarSenha = lazy(() => import("./pages/RecuperarSenha"));
const RedefinirSenha = lazy(() => import("./pages/RedefinirSenha"));
const TrocarSenha = lazy(() => import("./pages/TrocarSenha"));
const PortalDashboard = lazy(() => import("./pages/portal/PortalDashboard"));
const PortalCasos = lazy(() => import("./pages/portal/PortalCasos"));
const PortalCasoDetalhe = lazy(
  () => import("./pages/portal/PortalCasoDetalhe"),
);
const PortalFinanceiro = lazy(() => import("./pages/portal/PortalFinanceiro"));
const PortalAssinaturas = lazy(
  () => import("./pages/portal/PortalAssinaturas"),
);
const PortalMensagens = lazy(() => import("./pages/portal/PortalMensagens"));
const PortalDocumentos = lazy(() => import("./pages/portal/PortalDocumentos"));
const NotFound = lazy(() => import("./pages/NotFound"));

// Alias antigo /clientes/:clientId/dossie removido de STAFF_ROUTES; como
// LEGACY_REDIRECTS só suporta caminhos estáticos, o segmento dinâmico
// precisa desse redirect dedicado para não virar 404 para quem tinha
// a URL salva.
function ClienteDossieRedirect() {
  const { clientId } = useParams();
  return <Navigate to={`/clientes/${clientId}`} replace />;
}

function RouteFallback() {
  return (
    <div className="min-h-screen grid place-items-center bg-canvas">
      <Spinner />
    </div>
  );
}

export default function App() {
  const bootstrap = useAuth((state) => state.bootstrap);

  useEffect(() => {
    void bootstrap();
  }, [bootstrap]);

  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Suspense fallback={<RouteFallback />}>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route path="/recuperar-senha" element={<RecuperarSenha />} />
            <Route path="/redefinir-senha" element={<RedefinirSenha />} />
            <Route
              path="/trocar-senha"
              element={
                <Protected>
                  <TrocarSenha />
                </Protected>
              }
            />

            <Route
              path="/portal"
              element={
                <Protected>
                  <PortalOnly>
                    <PortalLayout />
                  </PortalOnly>
                </Protected>
              }
            >
              <Route index element={<PortalDashboard />} />
              <Route path="casos" element={<PortalCasos />} />
              <Route path="casos/:id" element={<PortalCasoDetalhe />} />
              <Route path="financeiro" element={<PortalFinanceiro />} />
              <Route path="assinaturas" element={<PortalAssinaturas />} />
              <Route path="mensagens" element={<PortalMensagens />} />
              <Route path="documentos" element={<PortalDocumentos />} />
            </Route>

            <Route
              element={
                <Protected>
                  <StaffOnly>
                    <>
                      <Layout />
                      <EntradaUniversalGlobal />
                    </>
                  </StaffOnly>
                </Protected>
              }
            >
              {STAFF_ROUTES.map((module) => {
                const Component = module.component;
                const content = <Component />;
                return (
                  <Route
                    key={module.key}
                    path={module.path}
                    element={
                      module.roles ? (
                        <RoleOnly roles={module.roles}>{content}</RoleOnly>
                      ) : (
                        content
                      )
                    }
                  />
                );
              })}

              {LEGACY_REDIRECTS.map((redirect) => (
                <Route
                  key={redirect.from}
                  path={redirect.from}
                  element={<Navigate to={redirect.to} replace />}
                />
              ))}

              <Route
                path="/clientes/:clientId/dossie"
                element={<ClienteDossieRedirect />}
              />
            </Route>

            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </ErrorBoundary>
      <ToastContainer />
    </BrowserRouter>
  );
}
