import Sociedade from "./Sociedade";
import ErrorBoundary from "../components/ErrorBoundary";
import { PageHeader } from "../components/UI";

export default function SociedadeWorkspace() {
  return (
    <div className="space-y-5">
      <PageHeader
        eyebrow="Gestão do escritório"
        title="Sociedade"
        subtitle="Sócios, participações, distribuições de lucros e retiradas em área segregada do caixa operacional."
      />
      <ErrorBoundary>
        <Sociedade />
      </ErrorBoundary>
    </div>
  );
}
