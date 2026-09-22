import { lazy, Suspense, useEffect, type ReactNode } from "react";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useParams,
} from "react-router";
import { ToastContainer } from "./components/Toast";
import { Spinner } from "./components/UI";
import ErrorBoundary from "./components/ErrorBoundary";
import LayoutReference from "./components/LayoutReference";
import LegacyRedirect from "./components/LegacyRedirect";
import ProviderPanelShortcut from "./components/ProviderPanelShortcut";
import {
  PortalOnly,
  Protected,
  RoleOnly,
  StaffOnly,
} from "./components/RouteGuards";
import {
  LEGACY_REDIRECTS,
  PORTAL_ROUTES,
  ROLES,
  STAFF_ROUTES,
  type ModuleRoute,
} from "./config/moduleRegistry";
import { useAuth } from "./stores/auth";
const Login = lazy(() => import("./pages/Login"));
const EntradaUniversalGlobal = lazy(
  () => import("./components/EntradaUniversalGlobal"),
);
const FlowEnhancements = lazy(() => import("./components/FlowEnhancements"));
const PortalLayout = lazy(() => import("./components/PortalLayout"));
const RecuperarSenha = lazy(() => import("./pages/RecuperarSenha"));
const RedefinirSenha = lazy(() => import("./pages/RedefinirSenha"));
const TrocarSenha = lazy(() => import("./pages/TrocarSenha"));
const Configurar2FA = lazy(() => import("./pages/Configurar2FA"));
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

function renderModuleRoute(module: ModuleRoute, element: ReactNode) {
  // subPaths (auditoria §2.6 #7): sub-rotas internas do MESMO módulo
  // compartilham o elemento — ex. /dpt360/* monta o mesmo workspace de /dpt360.
  return [module.path, ...(module.subPaths ?? [])].map((path) => (
    <Route key={`${module.key}:${path}`} path={path} element={element} />
  ));
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
              {/* Rotas do portal definidas no moduleRegistry (PORTAL_ROUTES) —
                  a navegação do PortalLayout deriva da MESMA lista. */}
              {PORTAL_ROUTES.map((module) => {
                const Component = module.component;
                return module.index ? (
                  <Route key={module.key} index element={<Component />} />
                ) : (
                  <Route
                    key={module.key}
                    path={module.path}
                    element={<Component />}
                  />
                );
              })}
            </Route>

            <Route
              element={
                <Protected>
                  <StaffOnly>
                    <>
                      <LayoutReference />
                      <EntradaUniversalGlobal />
                      <FlowEnhancements />
                      <ProviderPanelShortcut />
                    </>
                  </StaffOnly>
                </Protected>
              }
            >
              {STAFF_ROUTES.map((module) => {
                // /casos/novo permanece registrado no catálogo para
                // compatibilidade e integridade, porém já não é outra tela de
                // criação. Todo deep-link histórico converge para /entrada e
                // LegacyRedirect preserva modo, client_id, query e hash.
                if (module.key === "caso-novo") {
                  const redirecionamento = <LegacyRedirect to="/entrada" />;
                  return renderModuleRoute(
                    module,
                    module.roles ? (
                      <RoleOnly roles={module.roles}>
                        {redirecionamento}
                      </RoleOnly>
                    ) : (
                      redirecionamento
                    ),
                  );
                }

                const Component = module.component;
                const content = <Component />;
                return renderModuleRoute(
                  module,
                  module.roles ? (
                    <RoleOnly roles={module.roles}>{content}</RoleOnly>
                  ) : (
                    content
                  ),
                );
              })}

              {/* Subrota contextual da Governança da IA: deliberadamente não é
                  um novo módulo/menu; permanece protegida pelos mesmos papéis. */}
              <Route
                path="/ia-governanca/provedores"
                element={
                  <RoleOnly roles={ROLES.gestores}>
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
