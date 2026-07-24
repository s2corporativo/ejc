import { useSearchParams } from "react-router-dom";
import RaioXContextual from "./RaioXContextual";
import SalaAnaliseJuridica from "./SalaAnaliseJuridica";

/**
 * Rota canônica /raio-x:
 * - sem case_id: Sala de Análise Jurídica preliminar e conversável;
 * - com case_id: preserva o Raio-X contextual de um caso oficial existente.
 */
export default function RaioXProcesso() {
  const [params] = useSearchParams();
  const caseId = params.get("case_id");
  return caseId ? (
    <RaioXContextual caseId={caseId} />
  ) : (
    <SalaAnaliseJuridica />
  );
}
