// Taxonomia canônica de tipos de caso e catálogo de prescrição/decadência.
//
// Extraído do monólito Casos.tsx (auditoria §2.6 #10): dados e catálogos
// puros, sem dependência de React — reutilizáveis por testes e por qualquer
// tela que precise rotular tipos de caso.
import { FileSignature, Gavel, Handshake } from "lucide-react";

export const CASE_TYPES = [
  { k: "judicial", l: "Judicial", icon: Gavel },
  { k: "extrajudicial", l: "Extrajudicial", icon: Handshake },
  { k: "consultoria", l: "Consultoria", icon: FileSignature },
];

export const CASE_TYPE_LABEL: Record<string, string> = {
  judicial: "Judicial",
  extrajudicial: "Extrajudicial",
  consultoria: "Consultoria",
};

export const CASE_TYPE_COLOR: Record<string, string> = {
  judicial: "bg-primary-100 text-primary-700",
  extrajudicial: "bg-warn-100 text-warn-700",
  consultoria: "bg-ai-100 text-ai-700",
};

export const EXTRAJ_TYPES = [
  { k: "notificacao", l: "Notificação" },
  { k: "acordo", l: "Acordo" },
  { k: "contrato", l: "Contrato" },
  { k: "parecer", l: "Parecer" },
  { k: "due_diligence", l: "Due Diligence" },
  { k: "negociacao", l: "Negociação" },
];

// Catálogo de prescrição/decadência — espelha app/services/calc/prescricao.py.
// As chaves (k) DEVEM ser idênticas às do backend: ele recusa qualquer outra.
// Enviando { tipo_acao_prescricao: k, data_fato_prescricao } o backend calcula data_prescricao.
export const PRESCRICAO: {
  grupo: string;
  itens: { k: string; nm: string; base: string }[];
}[] = [
  {
    grupo: "Cível (Código Civil)",
    itens: [
      {
        k: "civel_geral",
        nm: "Prescrição geral — pretensões pessoais (10 anos)",
        base: "CC art. 205",
      },
      {
        k: "reparacao_civil",
        nm: "Reparação civil extracontratual (3 anos)",
        base: "CC art. 206 §3º V",
      },
      {
        k: "cobranca_liquida",
        nm: "Cobrança de dívida líquida (5 anos)",
        base: "CC art. 206 §5º I",
      },
      {
        k: "honorarios_profissionais",
        nm: "Honorários de profissional liberal (5 anos)",
        base: "CC art. 206 §5º II",
      },
      {
        k: "enriquecimento_sem_causa",
        nm: "Enriquecimento sem causa (3 anos)",
        base: "CC art. 206 §3º IV",
      },
      {
        k: "seguro",
        nm: "Segurado × segurador (1 ano)",
        base: "CC art. 206 §1º II",
      },
      {
        k: "alugueis",
        nm: "Cobrança de aluguéis (3 anos)",
        base: "CC art. 206 §3º I",
      },
    ],
  },
  {
    grupo: "Consumidor (CDC)",
    itens: [
      {
        k: "cdc_reparacao_fato",
        nm: "Acidente de consumo / fato do produto (5 anos)",
        base: "CDC art. 27",
      },
      {
        k: "cdc_vicio_nao_duravel",
        nm: "Vício — produto NÃO durável (30 dias · decadência)",
        base: "CDC art. 26 I",
      },
      {
        k: "cdc_vicio_duravel",
        nm: "Vício — produto durável (90 dias · decadência)",
        base: "CDC art. 26 II",
      },
    ],
  },
  {
    grupo: "Trabalhista (CF/CLT)",
    itens: [
      {
        k: "trabalhista_quinquenal",
        nm: "Créditos trabalhistas — quinquenal (5 anos)",
        base: "CF art. 7º XXIX",
      },
      {
        k: "trabalhista_bienal",
        nm: "Créditos trabalhistas — bienal pós-contrato (2 anos)",
        base: "CLT art. 11",
      },
    ],
  },
  {
    grupo: "Tributário (CTN)",
    itens: [
      {
        k: "tributario_decadencia",
        nm: "Decadência do lançamento (5 anos · decadência)",
        base: "CTN art. 173 I",
      },
      {
        k: "tributario_prescricao",
        nm: "Prescrição da cobrança (5 anos)",
        base: "CTN art. 174",
      },
    ],
  },
];
