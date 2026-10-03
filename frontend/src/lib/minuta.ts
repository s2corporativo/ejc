export const ETAPAS_MINUTA = [
  { num: 1, titulo: "Identificando tipo de peça" },
  { num: 2, titulo: "Estruturando enquadramento" },
  { num: 3, titulo: "Buscando fundamentos legais" },
  { num: 4, titulo: "Analisando jurisprudência" },
  { num: 5, titulo: "Organizando argumentos" },
  { num: 6, titulo: "Identificando riscos" },
  { num: 7, titulo: "Montando documento completo" },
];
export type StatusEtapa = "aguardando" | "em_andamento" | "concluido";

export function statusEtapa(status: unknown): StatusEtapa {
  return status === "em_andamento" ? "em_andamento" : "concluido";
}
