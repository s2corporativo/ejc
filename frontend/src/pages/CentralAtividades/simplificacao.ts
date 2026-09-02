export type FonteAtividade =
  | "prazo"
  | "tarefa"
  | "agenda"
  | "intimacao"
  | "suspensao";

export type SituacaoOperacional =
  | "pendente"
  | "andamento"
  | "concluido"
  | "cancelado";

export interface AtividadeSimplificada {
  id: string;
  fonte: FonteAtividade;
  titulo: string;
  descricao?: string | null;
  date?: string | null;
  status?: string | null;
  caso_titulo?: string | null;
  responsavel_id?: string | null;
  prioridade?: string | null;
  confirmado?: boolean;
  conferido_por?: string | null;
  dias_restantes?: number | null;
}

export interface AgendaEventoLegado {
  id: string;
  data_evento?: string | null;
  hora?: string | null;
  responsavel_id?: string | null;
  concluido?: boolean | null;
}

export interface ConflitoAgendaLegado {
  chave: string;
  data: string;
  hora: string;
  responsavel_id: string;
  ids: string[];
}

export function situacaoOperacional(status?: string | null): SituacaoOperacional {
  const valor = (status ?? "").trim().toLowerCase();
  if (valor === "cancelado") return "cancelado";
  if (["concluido", "concluida", "tratada"].includes(valor)) return "concluido";
  if (valor === "fazendo") return "andamento";
  return "pendente";
}

export function atividadeFinalizada(item: Pick<AtividadeSimplificada, "status">): boolean {
  const situacao = situacaoOperacional(item.status);
  return situacao === "concluido" || situacao === "cancelado";
}

export function precisaConferencia(
  item: Pick<
    AtividadeSimplificada,
    "fonte" | "prioridade" | "confirmado" | "conferido_por" | "status"
  >,
): boolean {
  if (item.fonte !== "prazo" || atividadeFinalizada(item)) return false;
  if (item.confirmado === false) return true;
  return item.prioridade === "critica" && !item.conferido_por;
}

export function pertenceCaixaEntrada(item: AtividadeSimplificada): boolean {
  if (atividadeFinalizada(item)) return false;
  if (item.fonte === "intimacao") return true;
  if (precisaConferencia(item)) return true;
  return (item.dias_restantes ?? 0) < 0 && ["prazo", "tarefa"].includes(item.fonte);
}

export function detectarConflitosAgendaLegada(
  eventos: AgendaEventoLegado[],
): ConflitoAgendaLegado[] {
  const grupos = new Map<string, ConflitoAgendaLegado>();

  for (const evento of eventos) {
    if (evento.concluido) continue;
    const data = (evento.data_evento ?? "").slice(0, 10);
    const hora = (evento.hora ?? "").trim();
    const responsavel = (evento.responsavel_id ?? "").trim();
    if (!data || !hora || !responsavel) continue;

    const chave = `${responsavel}|${data}|${hora}`;
    const atual = grupos.get(chave) ?? {
      chave,
      data,
      hora,
      responsavel_id: responsavel,
      ids: [],
    };
    atual.ids.push(evento.id);
    grupos.set(chave, atual);
  }

  return [...grupos.values()].filter((grupo) => grupo.ids.length > 1);
}

export function correspondeBusca(
  item: AtividadeSimplificada,
  termo: string,
  nomeResponsavel?: string,
): boolean {
  const q = termo.trim().toLocaleLowerCase("pt-BR");
  if (!q) return true;
  return [item.titulo, item.descricao, item.caso_titulo, nomeResponsavel]
    .filter(Boolean)
    .some((valor) => String(valor).toLocaleLowerCase("pt-BR").includes(q));
}
