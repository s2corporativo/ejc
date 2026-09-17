// Regras e payloads do intake documental de Casos (auditoria §2.6 #10).
//
// Extraído do monólito Casos.tsx: helpers puros e de rede usados pela página —
// sem JSX — para que a página orquestre e estes módulos façam o trabalho.
import api, { type VincularLoteResult } from "../../lib/api";
import { toast } from "../../components/Toast";
import { areaLabel } from "../../lib/areas";
import { CASE_TYPE_LABEL } from "./casosCatalogo";

/**
 * O vínculo de lote pode retornar 200 com `conflitos` (itens que apontam para
 * documento de outro caso sem arquivo clonável — ex.: ausente/externo). Isso
 * NÃO é sucesso pleno: avisa o usuário quais documentos ficaram de fora e onde
 * resolvê-los, em vez de seguir em silêncio.
 */
export function avisarConflitosDeVinculo(vinc: VincularLoteResult) {
  const conflitos = vinc?.conflitos ?? [];
  if (conflitos.length === 0) return;
  const nomes = conflitos
    .slice(0, 3)
    .map((c) => c.filename)
    .join(", ");
  const extra = conflitos.length > 3 ? ` e mais ${conflitos.length - 3}` : "";
  toast.error(
    `${conflitos.length} documento(s) do lote não puderam ser vinculados ao caso ` +
      `(${nomes}${extra}). Eles permanecem na Entrada Universal/GED de origem — ` +
      `verifique e anexe manualmente pelo caso.`,
  );
}

// Upload do documento importado para a GED, vinculado ao caso. Reutilizado no
// fluxo normal de criação e no retry de recuperação (reanexar) — sem recriar.
export async function anexarDocumento(
  caseId: string,
  clientId: string | undefined,
  arquivo: File,
  tituloDoc: string,
  tipoDoc?: string,
): Promise<void> {
  const fd = new FormData();
  fd.append("file", arquivo);
  fd.append("titulo", tituloDoc);
  if (tipoDoc) fd.append("tipo", tipoDoc);
  fd.append("case_id", caseId);
  if (clientId) fd.append("client_id", clientId);
  await api.post("/documents/upload", fd, {
    headers: { "Content-Type": "multipart/form-data" },
  });
}

export interface ResumoRevisao {
  principais: { label: string; valor: string }[];
  aplicar: { label: string; valor: string }[];
  ausentes: string[];
  alertas: string[];
}

const txtResumo = (v: unknown): string => (v == null ? "" : String(v).trim());

// Resumo de revisão 100% client-side (form + _extracao) — NÃO chama o backend.
// Alimenta o passo "Revisar dados" ANTES de confirmar a criação do caso, para
// que nada seja gravado sem a conferência do advogado (fluxograma documental).
export function montarResumoRevisao(
  form: Record<string, any>,
  clienteLabel: string,
): ResumoRevisao {
  const ex = (form?._extracao || {}) as Record<string, any>;
  const partes = (ex.partes || {}) as Record<string, any>;
  const classificacao = (ex.classificacao || {}) as Record<string, any>;

  const principais = [
    { label: "Título", valor: txtResumo(form?.titulo) || "—" },
    { label: "Cliente", valor: clienteLabel || "—" },
    {
      label: "Área",
      valor: areaLabel(form?.area) || txtResumo(form?.area) || "—",
    },
    { label: "Tipo", valor: CASE_TYPE_LABEL[form?.case_type] || "—" },
    { label: "Nº do processo", valor: txtResumo(form?.numero_processo) || "—" },
  ];

  const aplicar: { label: string; valor: string }[] = [];
  const push = (label: string, valor: unknown) => {
    const s = txtResumo(valor);
    if (s) aplicar.push({ label, valor: s });
  };
  push("Autor (parte)", partes.autor);
  push("Réu / parte contrária", partes.reu || form?.parte_contraria);
  push("Subárea", classificacao.subarea);
  push("Rito", classificacao.rito);
  push("Fase", classificacao.fase);
  push("Tribunal", form?.tribunal);
  push("Comarca", form?.comarca);
  push("Vara", form?.vara);
  if (txtResumo(form?.valor_causa))
    push("Valor da causa", `R$ ${form.valor_causa}`);

  const ausentes: string[] = [];
  if (!txtResumo(form?.titulo)) ausentes.push("Título");
  if (!txtResumo(form?.numero_processo)) ausentes.push("Número do processo");
  if (!txtResumo(form?.parte_contraria) && !txtResumo(partes.reu))
    ausentes.push("Parte contrária");
  if (!txtResumo(form?.valor_causa)) ausentes.push("Valor da causa");

  const alertas: string[] = [];
  if (
    txtResumo(form?.tipo_acao_prescricao) &&
    txtResumo(form?.data_fato_prescricao)
  ) {
    alertas.push(
      "Prazo prescricional/decadencial será calculado na criação — confira suspensões e interrupções (CC arts. 197–204).",
    );
  }
  const etapas = classificacao?.jornada?.proximas_etapas;
  if (Array.isArray(etapas) && etapas.length) {
    alertas.push(`Próximas etapas sugeridas pela IA: ${etapas.join(" → ")}.`);
  }
  return { principais, aplicar, ausentes, alertas };
}

// E02 (auditoria funcional): erros 422 do FastAPI/Pydantic chegam como
// {detail: [{loc, msg}]} — extrair o nome do campo para o usuário corrigir
// exatamente o ponto em vez de receber a string bruta do validador.
export function classificarErroCriacao(e: any): string {
  const resp = e?.response?.data;
  const status = e?.response?.status;
  const detail = resp?.detail;
  if (Array.isArray(detail) && detail.length) {
    return detail
      .map((d: any) => {
        const loc = Array.isArray(d?.loc) ? d.loc : [];
        const campo = loc.length ? String(loc[loc.length - 1]) : null;
        const rotulo = campo ? campo.replace(/_/g, " ") : null;
        return rotulo ? `${rotulo}: ${String(d.msg ?? d)}` : String(d.msg ?? d);
      })
      .join("; ");
  }
  if (typeof detail === "string" && detail) return detail;
  if (status === 422 || status === 400)
    return "Algum campo está em formato inválido ou ausente. Revise os campos destacados e tente novamente.";
  return e?.response?.data?.detail || "Erro ao salvar";
}
