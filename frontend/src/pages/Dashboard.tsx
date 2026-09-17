import DashboardUltra from "./DashboardUltra";

/**
 * Entrada canônica da página inicial do EJC.
 *
 * O DashboardUltra concentra a hierarquia operacional definida para o Início:
 * marca, ajuizamento, riscos de prazo, comunicações processuais, Entrada Única
 * e Radar Jurídico. Rotas e capacidades especializadas continuam acessíveis
 * pelos respectivos workspaces, sem duplicar widgets nesta casca.
 */
export default function Dashboard() {
  return (
    <div>
      <h1 className="sr-only">
        Início — Entrada Única, ajuizamento, riscos de prazo e comunicações
        processuais
      </h1>
      <DashboardUltra />
    </div>
  );
}
