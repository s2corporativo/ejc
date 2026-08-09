import Pecas from "../Pecas";

/**
 * A aba do Caso reutiliza o workspace completo de Peças.
 *
 * O filtro não é duplicado aqui: `useCasoFiltro` reconhece `/casos/:id`
 * imediatamente e mantém o workspace preso ao caso enquanto o usuário estiver
 * nessa rota. Assim editor, IA, templates, ficha, revisão HITL, PDF e protocolo
 * usam exatamente o mesmo código da fila global `/pecas`, sem duas regras de
 * negócio concorrentes.
 */
export default function TabPecas({ caseId: _caseId }: { caseId: string }) {
  return <Pecas />;
}
