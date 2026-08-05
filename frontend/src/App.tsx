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
import FlowEnhancements from "./components/FlowEnhancements";
import Layout from "./components/Layout";
import LegacyRedirect from "./components/LegacyRedirect";
import PortalLayout from "./components/PortalLayout";
import PremiumShellOverlay from "./components/PremiumShellOverlay";
import ProviderPanelShortcut from "./components/ProviderPanelShortcut";
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
const Configurar2FA = lazy(() => import("./pages/Configurar2FA"));
const AgendaDia = lazy(() => import("./pages/AgendaDia"));
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
const PainelProvedoresIA = lazy(() => import("./pages/PainelProvedoresIA"));
const NotFound = lazy(() => import("./pages/NotFound"));

// Alias antigo /clientes/:clientId/dossie removido de STAFF_ROUTES; como
// LEGACY_REDIRECTS só suporta caminhos estáticos, o segmento dinâmico
// precisa desse redirect dedicado para não virar 404 para quem tinha
// a URL salva.
function ClienteDossieRedirect() {
  const { clientId } = useParams();
  return <Navigate to={`/clientes/${clientId}`} replace />;
}

function SalaDeGuerraLegacyRedirect() {
  const { caseId } = useParams();
  return <Navigate to={`/casos/${caseId}?tab=teses`} replace />;
}

function AreaAtuacaoLegacyRedirect() {
  const { slug } = useParams();
  return <Navigate to={`/areas-de-atuacao/${slug}`} replace />;
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
              path="/configurar-2fa"
              element={
                <Protected>
                  <Configurar2FA />
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
                      <PremiumShellOverlay />
                      <EntradaUniversalGlobal />
                      <FlowEnhancements />
                      <ProviderPanelShortcut />
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

              {/* Subrota contextual da agenda semanal: usa os mesmos dados e
                  permanece sob os guards globais de equipe. */}
              <Route path="/atividades/dia/:date" element={<AgendaDia />} />

              {/* Subrota contextual da Governança da IA: deliberadamente não é
                  um novo módulo/menu; permanece protegida pelos mesmos papéis. */}
              <Route
                path="/ia-governanca/provedores"
                element={
                  <RoleOnly roles={["superadmin", "admin", "socio"]}>
                    <PainelProvedoresIA />
                  </RoleOnly>
                }
              />

              {/* FLX-029: LegacyRedirect mescla a query/hash de origem com o
                  destino (params embutidos no destino vencem em conflito). */}
              {LEGACY_REDIRECTS.map((redirect) => (
                <Route
                  key={redirect.from}
                  path={redirect.from}
                  element={<LegacyRedirect to={redirect.to} />}
                />
              ))}

              <Route
                path="/clientes/:clientId/dossie"
                element={<ClienteDossieRedirect />}
              />
              <Route
                path="/casos/:caseId/sala-de-guerra"
                element={<SalaDeGuerraLegacyRedirect />}
              />
              <Route
                path="/ramos/:slug"
                element={<AreaAtuacaoLegacyRedirect />}
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
