import { ToastContainer } from "./components/Toast";
import { lazy, Suspense } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "./stores/auth";
import { Spinner } from "./components/UI";
import ErrorBoundary from "./components/ErrorBoundary";

// Eager: necessários no primeiro paint / leves
import Layout from "./components/Layout";
import PortalLayout from "./components/PortalLayout";
import Login from "./pages/LoginModern";

/** Lê o usuário salvo em localStorage sem estourar se o JSON estiver corrompido. */
function readStoredUser(): { role?: string } | null {
  try {
    return JSON.parse(localStorage.getItem("ejc_user") || "null");
  } catch {
    return null;
  }
}

// Lazy: carregados sob demanda (reduz o bundle inicial)
const RecuperarSenha = lazy(() => import("./pages/RecuperarSenha"));
const RedefinirSenha = lazy(() => import("./pages/RedefinirSenha"));
const TrocarSenha = lazy(() => import("./pages/TrocarSenha"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Clientes = lazy(() => import("./pages/Clientes"));
const Casos = lazy(() => import("./pages/Casos"));
const CasoDetalhe = lazy(() => import("./pages/CasoDetalhe"));
const Prazos = lazy(() => import("./pages/Prazos"));
const Suspensoes = lazy(() => import("./pages/Suspensoes"));
const GestaoDocumental = lazy(() => import("./pages/GestaoDocumental"));
const Pecas = lazy(() => import("./pages/Pecas"));
const RamoBase = lazy(() => import("./pages/ramos/RamoBase"));
const RamosHub = lazy(() => import("./pages/RamosHub"));
const OfficeContracts = lazy(() => import("./pages/OfficeContracts"));
const PartnerWithdrawals = lazy(() => import("./pages/PartnerWithdrawals"));
const CentralAtividades = lazy(() => import("./pages/CentralAtividades"));
const FinanceiroWorkspace = lazy(() => import("./pages/FinanceiroWorkspace"));
const DataJudBusca = lazy(() => import("./pages/DataJudBusca"));
const DespesasRecorrentes = lazy(() => import("./pages/DespesasRecorrentes"));
const CRMLeads = lazy(() => import("./pages/CRMLeads"));
const IA = lazy(() => import("./pages/IA"));
const Conhecimento = lazy(() => import("./pages/Conhecimento"));
const Auditoria = lazy(() => import("./pages/Auditoria"));
const MapaModulos = lazy(() => import("./pages/MapaModulos"));
const Usuarios = lazy(() => import("./pages/Usuarios"));
const Tarefas = lazy(() => import("./pages/Tarefas"));
const Intimacoes = lazy(() => import("./pages/Intimacoes"));
const Lixeira = lazy(() => import("./pages/Lixeira"));
const Jurimetria = lazy(() => import("./pages/Jurimetria"));
const CentralRelacionamento = lazy(
  () => import("./pages/CentralRelacionamento"),
);
const KnowledgeHub = lazy(() => import("./pages/KnowledgeHub"));
const Noticias = lazy(() => import("./pages/Noticias"));
const Kanban = lazy(() => import("./pages/Kanban"));
const Agenda = lazy(() => import("./pages/Agenda"));
const AssistenteIA = lazy(() => import("./pages/AssistenteIA"));
const Checklists = lazy(() => import("./pages/Checklists"));
const Prompts = lazy(() => import("./pages/Prompts"));
const DossieCliente = lazy(() => import("./pages/DossieCliente"));
const Biblioteca = lazy(() => import("./pages/Biblioteca"));
const MemoriaInstitucional = lazy(() => import("./pages/MemoriaInstitucional"));
const SalaDeGuerra = lazy(() => import("./pages/SalaDeGuerra"));
const Workflow = lazy(() => import("./pages/Workflow"));
const Produtividade = lazy(() => import("./pages/Produtividade"));
const DiarioOficial = lazy(() => import("./pages/DiarioOficial"));
const Assinaturas = lazy(() => import("./pages/Assinaturas"));
const Ajuda = lazy(() => import("./pages/Ajuda"));
const Configuracoes = lazy(() => import("./pages/Configuracoes"));
const Whatsapp = lazy(() => import("./pages/Whatsapp"));
const DashboardIA = lazy(() => import("./pages/DashboardIA"));
const GovernancaIA = lazy(() => import("./pages/GovernancaIA"));
const ConteudoJuridico = lazy(() => import("./pages/ConteudoJuridico"));
const Wiki = lazy(() => import("./pages/Wiki"));
const InteligenciaWorkspace = lazy(
  () => import("./pages/InteligenciaWorkspace"),
);
const FerramentasIA = lazy(() => import("./pages/FerramentasIA"));
const VictoryVault = lazy(() => import("./pages/VictoryVault"));
const RadarRegulatorio = lazy(() => import("./pages/RadarRegulatorio"));
const RadarCompliance = lazy(() => import("./pages/RadarCompliance"));
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
const NotFound = lazy(() => import("./pages/NotFound"));

const GESTAO_FINANCEIRO_ROLES = ["superadmin", "admin", "socio", "financeiro"];

function Protected({ children }: { children: JSX.Element }) {
  const token = localStorage.getItem("ejc_access");
  return token ? children : <Navigate to="/login" replace />;
}

/** Cliente externo só navega no /portal — staff não entra no portal */
function StaffOnly({ children }: { children: JSX.Element }) {
  const u = readStoredUser();
  if (u?.role === "cliente_externo") return <Navigate to="/portal" replace />;
  return children;
}

/** Restringe rota a roles específicos — UX complementar ao RBAC do backend */
function RoleOnly({
  roles,
  children,
}: {
  roles: string[];
  children: JSX.Element;
}) {
  const u = readStoredUser();
  if (!u || !u.role || !roles.includes(u.role))
    return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  useAuth();
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Suspense
          fallback={
            <div className="min-h-screen grid place-items-center">
              <Spinner />
            </div>
          }
        >
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

            {/* ── Portal do Cliente ── */}
            <Route
              path="/portal"
              element={
                <Protected>
                  <PortalLayout />
                </Protected>
              }
            >
              <Route index element={<PortalDashboard />} />
              <Route path="casos" element={<PortalCasos />} />
              <Route path="casos/:id" element={<PortalCasoDetalhe />} />
              <Route path="financeiro" element={<PortalFinanceiro />} />
              <Route path="assinaturas" element={<PortalAssinaturas />} />
              <Route path="mensagens" element={<PortalMensagens />} />
            </Route>

            {/* ── Sistema interno (staff) ── */}
            <Route
              element={
                <Protected>
                  <StaffOnly>
                    <Layout />
                  </StaffOnly>
                </Protected>
              }
            >
              <Route path="/" element={<Dashboard />} />
              <Route path="/clientes" element={<Clientes />} />
              <Route path="/clientes/:clientId" element={<DossieCliente />} />
              <Route
                path="/clientes/:clientId/dossie"
                element={<DossieCliente />}
              />
              <Route path="/casos" element={<Casos />} />
              <Route path="/casos/:id" element={<CasoDetalhe />} />
              <Route path="/prazos" element={<Prazos />} />
              <Route path="/suspensoes" element={<Suspensoes />} />
              <Route path="/tarefas" element={<Tarefas />} />
              <Route path="/intimacoes" element={<Intimacoes />} />
              <Route path="/documentos" element={<GestaoDocumental />} />
              <Route path="/pecas" element={<Pecas />} />
              <Route
                path="/honorarios"
                element={<Navigate to="/financeiro?tab=honorarios" replace />}
              />
              <Route
                path="/ambiental"
                element={<Navigate to="/ramos/ambiental" replace />}
              />
              <Route
                path="/data-room"
                element={<Navigate to="/documentos" replace />}
              />
              <Route
                path="/dashboard-executivo"
                element={<Navigate to="/" replace />}
              />
              <Route path="/jurimetria" element={<Jurimetria />} />
              <Route
                path="/central-relacionamento"
                element={<CentralRelacionamento />}
              />
              <Route path="/knowledge-hub" element={<KnowledgeHub />} />
              <Route path="/biblioteca" element={<Biblioteca />} />
              <Route path="/memoria" element={<MemoriaInstitucional />} />
              <Route
                path="/casos/:caseId/sala-de-guerra"
                element={<SalaDeGuerra />}
              />
              <Route path="/produtividade" element={<Produtividade />} />
              <Route path="/ajuda" element={<Ajuda />} />
              <Route path="/configuracoes" element={<Configuracoes />} />
              <Route path="/noticias" element={<Noticias />} />
              <Route
                path="/ia-saude"
                element={
                  <RoleOnly roles={["superadmin", "admin", "socio"]}>
                    <DashboardIA />
                  </RoleOnly>
                }
              />
              <Route
                path="/ia-governanca"
                element={
                  <RoleOnly roles={["superadmin", "admin", "socio"]}>
                    <GovernancaIA />
                  </RoleOnly>
                }
              />
              <Route path="/conteudo-juridico" element={<ConteudoJuridico />} />
              <Route path="/wiki" element={<Wiki />} />
              <Route path="/inteligencia" element={<InteligenciaWorkspace />} />
              <Route path="/ferramentas-ia" element={<FerramentasIA />} />
              <Route path="/victory-vault" element={<VictoryVault />} />
              <Route path="/radar-regulatorio" element={<RadarRegulatorio />} />
              <Route
                path="/compliance/radar"
                element={
                  <RoleOnly
                    roles={["superadmin", "admin", "socio", "advogado"]}
                  >
                    <RadarCompliance />
                  </RoleOnly>
                }
              />
              <Route path="/kanban" element={<Kanban />} />
              <Route path="/agenda" element={<Agenda />} />
              <Route path="/assistente-ia" element={<AssistenteIA />} />
              <Route path="/checklists" element={<Checklists />} />
              <Route path="/prompts" element={<Prompts />} />
              <Route path="/diario-oficial" element={<DiarioOficial />} />
              <Route path="/assinaturas" element={<Assinaturas />} />
              <Route path="/workflow" element={<Workflow />} />
              <Route
                path="/sociedade"
                element={<Navigate to="/financeiro?tab=societaria" replace />}
              />
              <Route path="/ramos" element={<RamosHub />} />
              <Route path="/ramos/:slug" element={<RamoBase />} />
              <Route path="/office-contracts" element={<OfficeContracts />} />
              <Route
                path="/partner-withdrawals"
                element={<PartnerWithdrawals />}
              />
              <Route path="/atividades" element={<CentralAtividades />} />
              <Route
                path="/financeiro"
                element={
                  <RoleOnly roles={GESTAO_FINANCEIRO_ROLES}>
                    <FinanceiroWorkspace />
                  </RoleOnly>
                }
              />
              <Route
                path="/financeiro-dashboard"
                element={<Navigate to="/financeiro" replace />}
              />
              <Route
                path="/despesas"
                element={<Navigate to="/financeiro?tab=despesas" replace />}
              />
              <Route path="/datajud" element={<DataJudBusca />} />
              <Route
                path="/despesas-recorrentes"
                element={
                  <RoleOnly roles={GESTAO_FINANCEIRO_ROLES}>
                    <DespesasRecorrentes />
                  </RoleOnly>
                }
              />
              <Route path="/crm-leads" element={<CRMLeads />} />
              <Route path="/whatsapp" element={<Whatsapp />} />
              <Route
                path="/ia"
                element={
                  <RoleOnly
                    roles={[
                      "superadmin",
                      "admin",
                      "socio",
                      "advogado",
                      "advogado_auxiliar",
                      "estagiario",
                    ]}
                  >
                    <IA />
                  </RoleOnly>
                }
              />
              <Route
                path="/conhecimento"
                element={
                  <RoleOnly roles={["superadmin", "admin", "socio"]}>
                    <Conhecimento />
                  </RoleOnly>
                }
              />
              <Route
                path="/auditoria"
                element={
                  <RoleOnly roles={["superadmin", "admin", "socio"]}>
                    <Auditoria />
                  </RoleOnly>
                }
              />
              <Route
                path="/mapa-modulos"
                element={
                  <RoleOnly roles={["superadmin", "admin", "socio"]}>
                    <MapaModulos />
                  </RoleOnly>
                }
              />
              <Route
                path="/usuarios"
                element={
                  <RoleOnly roles={["superadmin", "admin"]}>
                    <Usuarios />
                  </RoleOnly>
                }
              />
              <Route
                path="/lixeira"
                element={
                  <RoleOnly roles={["superadmin", "admin", "socio"]}>
                    <Lixeira />
                  </RoleOnly>
                }
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
