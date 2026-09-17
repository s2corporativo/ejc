// Catálogo e regras do fluxo de Peças Jurídicas (auditoria §2.6 #10).
//
// Extraído do monólito Pecas.tsx: taxonomia de fases, tipos manuais, erros
// de blob/axios e utilitários puros — sem JSX e sem estado.
import type { LegalDoc } from "../../types";
import { fmtMoney } from "../../components/UI";
import type { FichaTriagemCampos } from "../../components/FichaTriagem";

export async function blobErrorDetail(e: any): Promise<string | undefined> {
  let detail = e.response?.data?.detail;
  if (!detail && e.response?.data instanceof Blob) {
    try {
      detail = JSON.parse(await e.response.data.text())?.detail;
    } catch {
      return undefined;
    }
  }
  return typeof detail === "object" && detail !== null
    ? (detail.mensagem ?? JSON.stringify(detail).slice(0, 200))
    : detail;
}

export function errDetail(e: any, fallback: string): string {
  const d = e?.response?.data?.detail;
  if (typeof d === "string" && d) return d;
  if (d && typeof d === "object")
    return d.mensagem ?? JSON.stringify(d).slice(0, 200);
  return fallback;
}

export const TIPOS_MANUAIS = [
  "peticao_inicial",
  "contestacao",
  "recurso",
  "contrarrazoes",
  "parecer",
  "contrato",
  "procuracao",
  "notificacao_extrajudicial",
  "defesa_ambiental",
  "outro",
];

export const STATUS_POS_APROVACAO = new Set([
  "aprovada",
  "final",
  "protocolada",
]);

export type FaseVisual =
  "elaboracao" | "revisao" | "aprovadas" | "protocoladas";

export const FASES: {
  key: FaseVisual;
  label: string;
  statuses: string[];
  descricao: string;
}[] = [
  {
    key: "elaboracao",
    label: "Em elaboração",
    statuses: ["rascunho", "em_revisao"],
    descricao: "Minutas e peças ainda em conferência",
  },
  {
    key: "revisao",
    label: "Revisadas",
    statuses: ["corrigida"],
    descricao: "Revisão registrada, aguardando aprovação",
  },
  {
    key: "aprovadas",
    label: "Aprovadas",
    statuses: ["aprovada", "final"],
    descricao: "Assinadas ou prontas para protocolo",
  },
  {
    key: "protocoladas",
    label: "Protocoladas",
    statuses: ["protocolada"],
    descricao: "Com protocolo registrado",
  },
];

export type CitacaoBloqueio = {
  mensagem?: string;
  politica?: string;
  score?: number;
  motivos?: string[];
  bloqueantes?: { rotulo?: string; aviso?: string; status?: string }[];
};

export function faseDaPeca(status: string): FaseVisual | "outro" {
  return FASES.find((f) => f.statuses.includes(status))?.key ?? "outro";
}

export function faseLabel(status: string): string {
  return FASES.find((f) => f.statuses.includes(status))?.label ?? status;
}

export const RISCO_TONE: Record<
  FichaTriagemCampos["risco_processual"],
  "green" | "amber" | "red"
> = {
  baixo: "green",
  medio: "amber",
  alto: "red",
};

export function fmtValorCausa(v: string): string {
  const n = Number(
    String(v)
      .replace(/[^\d.,-]/g, "")
      .replace(/\.(?=\d{3})/g, "")
      .replace(",", "."),
  );
  return Number.isFinite(n) && v.trim() !== "" ? fmtMoney(n) : v;
}

export function pecaValidacaoLabel(doc: LegalDoc): {
  label: string;
  tone: "slate" | "green" | "amber" | "red";
} {
  const v = doc.validacao_juridica;
  if (!v || v.status === "sem_validacao")
    return { label: "Não revisada", tone: "slate" as const };
  if (v.apto_fluxo)
    return { label: `Apta ${v.score ?? ""}/100`, tone: "green" as const };
  if (v.status === "pendente_revisao")
    return {
      label: `Atenção ${v.score ?? ""}/100`,
      tone: "amber" as const,
    };
  return { label: `Bloqueada ${v.score ?? ""}/100`, tone: "red" as const };
}
