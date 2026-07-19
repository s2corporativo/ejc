import KnowledgeGovernancePanel from "../components/KnowledgeGovernancePanel";
import Conhecimento from "./Conhecimento";

export default function ConhecimentoGovernado() {
  return (
    <div className="space-y-6">
      <KnowledgeGovernancePanel />
      <Conhecimento />
    </div>
  );
}
