import DashboardUltra from "./DashboardUltra";

// Entrada estável da rota principal. Mantemos a classe-raiz legada apenas como
// contrato de compatibilidade para os smokes responsivos existentes; o visual
// e os componentes renderizados continuam sendo integralmente do dashboard v2.
export default function Dashboard() {
  return (
    <div className="ejc-dashboard-premium">
      <DashboardUltra />
    </div>
  );
}
