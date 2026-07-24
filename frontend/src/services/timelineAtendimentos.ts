import api from "../lib/api";
import type { TimelineEvento } from "../types/visualLaw";

type AtendimentoTipo =
  | "reuniao_presencial"
  | "reuniao_virtual"
  | "ligacao"
  | "email"
  | "whatsapp"
  | "protocolo"
  | "visita"
  | "outros";

interface AtendimentoTimelineItem {
  id: string;
  case_id?: string | null;
  tipo: AtendimentoTipo;
  data_atendimento: string;
  resumo: string;
  solicitacao?: string | null;
  solicitacao_atendida: boolean;
  solicitacao_atrasada?: boolean;
  proximo_passo?: string | null;
  contato_status?: "iniciado" | "confirmado" | "nao_concluido";
}

interface AtendimentoTimelineResponse {
  items?: AtendimentoTimelineItem[];
}

export interface ResumoAtendimentosCaso {
  total: number;
  pendentes: number;
  atrasados: number;
  atendidos: number;
}

export interface TimelineAtendimentosResult {
  eventos: TimelineEvento[];
  resumo: ResumoAtendimentosCaso;
}

const TIPO_LABEL: Record<AtendimentoTipo, string> = {
  reuniao_presencial: "Reunião presencial",
  reuniao_virtual: "Reunião virtual",
  ligacao: "Ligação",
  email: "E-mail",
  whatsapp: "WhatsApp",
  protocolo: "Protocolo",
  visita: "Visita",
  outros: "Atendimento",
};

function textoSeguro(value?: string | null, limite = 500): string | null {
  const limpo = (value || "").replace(/\s+/g, " ").trim();
  if (!limpo) return null;
  return limpo.length > limite ? `${limpo.slice(0, limite).trim()}…` : limpo;
}

function eventoAtendimento(
  item: AtendimentoTimelineItem,
  caseId: string,
): TimelineEvento | null {
  if (item.case_id !== caseId) return null;
  if (!item.data_atendimento || Number.isNaN(Date.parse(item.data_atendimento))) {
    return null;
  }

  const resumo = textoSeguro(item.resumo);
  if (!resumo) return null;

  const partes = [resumo];
  const solicitacao = textoSeguro(item.solicitacao);
  if (solicitacao) {
    const status = item.solicitacao_atrasada
      ? "atrasada"
      : item.solicitacao_atendida
        ? "atendida"
        : "pendente";
    partes.push(`Solicitação ${status}: ${solicitacao}`);
  }
  const proximoPasso = textoSeguro(item.proximo_passo);
  if (proximoPasso) partes.push(`Próximo passo: ${proximoPasso}`);

  return {
    data: item.data_atendimento,
    categoria: "atendimento",
    tipo: item.tipo,
    descricao: partes.join(" · "),
  };
}

export function normalizarAtendimentosCaso(
  payload: AtendimentoTimelineResponse,
  caseId: string,
): TimelineAtendimentosResult {
  const idEsperado = caseId.trim();
  if (!idEsperado) {
    return {
      eventos: [],
      resumo: { total: 0, pendentes: 0, atrasados: 0, atendidos: 0 },
    };
  }

  const items = Array.isArray(payload.items) ? payload.items : [];
  const escopo = items.filter((item) => item?.case_id === idEsperado);
  const eventos = escopo
    .map((item) => eventoAtendimento(item, idEsperado))
    .filter((evento): evento is TimelineEvento => evento !== null)
    .sort((a, b) => Date.parse(b.data) - Date.parse(a.data));

  const comSolicitacao = escopo.filter((item) => textoSeguro(item.solicitacao));
  return {
    eventos,
    resumo: {
      total: eventos.length,
      pendentes: comSolicitacao.filter(
        (item) => !item.solicitacao_atendida && !item.solicitacao_atrasada,
      ).length,
      atrasados: comSolicitacao.filter(
        (item) => !item.solicitacao_atendida && item.solicitacao_atrasada,
      ).length,
      atendidos: comSolicitacao.filter((item) => item.solicitacao_atendida)
        .length,
    },
  };
}

export async function carregarAtendimentosCaso(
  caseId: string,
): Promise<TimelineAtendimentosResult> {
  const id = caseId.trim();
  if (!id) return normalizarAtendimentosCaso({}, "");

  const { data } = await api.get<AtendimentoTimelineResponse>("/atendimentos", {
    params: {
      case_id: id,
      page: 1,
      per_page: 100,
    },
  });
  return normalizarAtendimentosCaso(data, id);
}
