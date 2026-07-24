import { useMemo } from "react";

/** Campos guiados por tipo de peça — fonte: peca_workflow_service._CAMPOS_GUIADOS */
const CAMPOS_GUIADOS: Record<string, string[]> = {
  peticao_inicial: ["partes", "fatos", "pretensao", "competencia", "provas", "pedidos"],
  contestacao: [
    "autor", "reu", "pretensao_autor", "fatos_impugnados",
    "preliminares", "provas_defesa", "prescricao_decadencia",
    "possibilidade_acordo", "pedidos",
  ],
  replica: ["sintese_contestacao", "preliminares_impugnadas", "fatos_novos", "provas", "pedidos"],
  apelacao: [
    "decisao_recorrida", "capitulos_impugnados", "tempestividade",
    "preparo_gratuidade", "razoes_reforma_anulacao", "pedidos",
  ],
  agravo: [
    "decisao_agravada", "cabimento", "tempestividade",
    "urgencia_recursal", "razoes_reforma", "pedidos",
  ],
  recurso_ordinario: [
    "sentenca_recorrida", "capitulos_impugnados", "tempestividade",
    "preparo", "razoes_reforma", "pedidos",
  ],
  contrato: [
    "partes", "objeto", "obrigacoes", "valores_pagamento",
    "prazo_vigencia", "rescisao", "foro",
  ],
  notificacao: [
    "notificante", "notificado", "fatos", "obrigacao_exigida",
    "prazo_cumprimento", "consequencias_inadimplemento",
  ],
  parecer: [
    "consulente", "quesitos", "fatos_documentos", "premissas",
    "riscos", "conclusao_solicitada",
  ],
};
const FALLBACK_CAMPOS = ["partes", "fatos", "provas", "pedidos"];

const CAMPO_LABEL: Record<string, string> = {
  partes: "Partes envolvidas",
  fatos: "Fatos da causa",
  pretensao: "Pretensão do autor",
  competencia: "Competência do juízo",
  provas: "Provas disponíveis",
  pedidos: "Pedidos",
  autor: "Autor (nome completo/Razão Social)",
  reu: "Réu (nome completo/Razão Social)",
  pretensao_autor: "Pretensão do autor",
  fatos_impugnados: "Fatos impugnados",
  preliminares: "Preliminares",
  provas_defesa: "Provas da defesa",
  prescricao_decadencia: "Prescrição/Decadência",
  possibilidade_acordo: "Possibilidade de acordo",
  sintese_contestacao: "Síntese da contestação",
  preliminares_impugnadas: "Preliminares impugnadas",
  fatos_novos: "Fatos novos",
  decisao_recorrida: "Decisão recorrida",
  capitulos_impugnados: "Capítulos impugnados",
  tempestividade: "Tempestividade",
  preparo_gratuidade: "Preparo/Gratuidade",
  razoes_reforma_anulacao: "Razões de reforma/anulação",
  decisao_agravada: "Decisão agravada",
  cabimento: "Cabimento",
  urgencia_recursal: "Urgência recursal",
  razoes_reforma: "Razões de reforma",
  sentenca_recorrida: "Sentença recorrida",
  preparo: "Preparo",
  objeto: "Objeto do contrato",
  obrigacoes: "Obrigações das partes",
  valores_pagamento: "Valores e pagamento",
  prazo_vigencia: "Prazo de vigência",
  rescisao: "Rescisão",
  foro: "Foro/Arbitramento",
  notificante: "Notificante",
  notificado: "Notificado",
  obrigacao_exigida: "Obrigação exigida",
  prazo_cumprimento: "Prazo para cumprimento",
  consequencias_inadimplemento: "Consequências do inadimplemento",
  consulente: "Consulente",
  quesitos: "Quesitos",
  fatos_documentos: "Fatos e documentos",
  premissas: "Premissas",
  riscos: "Riscos identificados",
  conclusao_solicitada: "Conclusão solicitada",
};

const CAMPO_PLACEHOLDER: Record<string, string> = {
  partes: "Ex.: Maria da Silva (autora) vs. Empresa XYZ Ltda. (réu)",
  fatos: "Descreva cronologicamente os fatos relevantes...",
  pretensao: "O que o autor quer obter com esta ação...",
  competencia: "Ex.: Justiça Estadual — Vara Cível, Foro de Betim/MG",
  provas: "Documentos, testemunhos, perícias disponíveis...",
  pedidos: "Liste os pedidos principais e subsidiários...",
  autor: "Nome completo ou Razão Social do autor",
  reu: "Nome completo ou Razão Social do réu",
  preliminares: "Ex.: Incompetência, ilegitimidade, carência da ação...",
  prescricao_decadencia: "Prazo prescricional, termo inicial, causa interruptiva...",
  decisao_recorrida: "Ementa ou resumo da decisão atacada...",
  capitulos_impugnados: "Quais pontos da sentença são combatidos...",
  objeto: "Objeto principal do contrato...",
  obrigacoes: "Obrigações de cada parte...",
  valores_pagamento: "Valores, forma e periodicidade...",
  prazo_vigencia: "Duração do contrato e condições de prorrogação...",
  rescisao: "Causais de rescisão e efeitos...",
  foro: "Foro eleito e cláusula de eleição de domicílio...",
  consulente: "Nome do consulente/empresa...",
  quesitos: "Perguntas técnicas que orientam o parecer...",
};

interface Props {
  tipoPeca: string;
  respostas: Record<string, string>;
  onChange: (campo: string, valor: string) => void;
}

export default function GuiadoForm({ tipoPeca, respostas, onChange }: Props) {
  const campos = useMemo(
    () => CAMPOS_GUIADOS[tipoPeca] || FALLBACK_CAMPOS,
    [tipoPeca],
  );

  const preenchidos = campos.filter((c) => (respostas[c] || "").trim().length > 0);
  const progresso = campos.length > 0 ? Math.round((preenchidos.length / campos.length) * 100) : 0;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>Formulário guiado — {campos.length} campos</span>
        <span className={progresso === 100 ? "font-semibold text-green-600" : ""}>
          {preenchidos.length}/{campos.length} preenchidos
        </span>
      </div>

      <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all ${
            progresso === 100 ? "bg-green-500" : "bg-primary-400"
          }`}
          style={{ width: `${progresso}%` }}
        />
      </div>

      {campos.map((campo) => (
        <div key={campo}>
          <label className="label text-xs">
            {CAMPO_LABEL[campo] || campo.replace(/_/g, " ")}
            {(campo === "fatos" || campo === "pedidos" || campo === "pretensao") && (
              <span className="ml-1 text-danger-500">*</span>
            )}
          </label>
          <textarea
            rows={campo === "fatos" || campo === "pedidos" ? 4 : 2}
            className="input w-full text-sm"
            value={respostas[campo] || ""}
            onChange={(e) => onChange(campo, e.target.value)}
            placeholder={CAMPO_PLACEHOLDER[campo] || `Informe ${campo.replace(/_/g, " ")}...`}
          />
        </div>
      ))}

      {progresso < 100 && (
        <p className="text-[11px] text-amber-600">
          Campos obrigatórios marcados com * devem ser preenchidos antes de gerar a peça no modo guiado.
        </p>
      )}
    </div>
  );
}
