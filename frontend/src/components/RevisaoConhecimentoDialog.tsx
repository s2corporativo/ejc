// ── Revisão humana de documento da base de conhecimento (C8/C9) ──────────────
// Aprovar/rejeitar conhecimento para o RAG é decisão jurídica: o revisor
// precisa VER o documento e registrar notas. O diálogo carrega
// `GET /rag/governanca/docs/{id}` (metadados, autoridade, situação, citação,
// qualidade e os campos textuais de `extra`), exige `notas` e registra a
// decisão pelo endpoint audit-logado `POST /rag/governanca/docs/{id}/revisar`.
// Quando o chamador informa `confidence_level`, o PATCH legado de curadoria
// (`/ia-governanca/rag-curadoria/{id}`) ajusta só a confiança — nunca é ele
// que "aprova".
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import api from "../lib/api";
import { mensagemErroHttp } from "../lib/iaErro";
import { Modal, Spinner } from "./UI";

export type DecisaoRevisao = "aprovar" | "rejeitar";

export type DocumentoRevisao = {
  id: string;
  titulo: string;
  categoria?: string | null;
  fonte?: string | null;
  tribunal?: string | null;
  versao?: number;
  status_indexacao?: string;
  extra?: Record<string, unknown>;
  autoridade?: { code?: string; label?: string; official?: boolean };
  situacao_juridica?: { code?: string; label?: string };
  frescor?: { status?: string; days?: number | null };
  qualidade?: { score?: number; status?: string; issues?: string[] };
  metricas?: { chunks?: number; chars?: number; embedded?: number };
  citacao?: Record<string, unknown> | string | null;
};

export type RevisaoConhecimentoProps = {
  docId: string | null;
  decisao: DecisaoRevisao;
  /** Confiança a gravar via PATCH de curadoria (só quando informado). */
  confidenceLevel?: "alta" | "media" | "baixa";
  onFechar: () => void;
  onConcluido: () => void;
};

export const ERRO_NOTAS_OBRIGATORIAS =
  "Registre as notas da revisão: o que foi conferido e por que o documento pode (ou não) alimentar a IA.";

const CAMPOS_TEXTO_EXTRA: Array<[string, string]> = [
  ["ementa", "Ementa"],
  ["tese_extraida", "Tese extraída"],
  ["resumo", "Resumo"],
  ["texto_preview", "Prévia do texto"],
  ["descricao", "Descrição"],
  ["observacoes", "Observações"],
];

function trechosDoExtra(extra: Record<string, unknown> | undefined) {
  if (!extra) return [] as Array<[string, string]>;
  return CAMPOS_TEXTO_EXTRA.flatMap(([chave, rotulo]) => {
    const valor = extra[chave];
    return typeof valor === "string" && valor.trim()
      ? [[rotulo, valor.slice(0, 4000)] as [string, string]]
      : [];
  });
}

function citacaoTexto(citacao: DocumentoRevisao["citacao"]): string {
  if (!citacao) return "";
  if (typeof citacao === "string") return citacao;
  const texto = (citacao as { texto?: unknown; formatada?: unknown }).texto;
  const formatada = (citacao as { formatada?: unknown }).formatada;
  if (typeof texto === "string") return texto;
  if (typeof formatada === "string") return formatada;
  return "";
}

/**
 * Registra a decisão: POST revisar (audit-logado) e, se pedido, PATCH de
 * confiança. Exportada para teste e para reuso fora do diálogo.
 */
export async function registrarRevisaoConhecimento(args: {
  docId: string;
  decisao: DecisaoRevisao;
  notas: string;
  confidenceLevel?: "alta" | "media" | "baixa";
}) {
  const aprovado = args.decisao === "aprovar";
  await api.post(`/rag/governanca/docs/${args.docId}/revisar`, {
    aprovado,
    notas: args.notas,
  });
  if (args.confidenceLevel) {
    await api.patch(`/ia-governanca/rag-curadoria/${args.docId}`, {
      confidence_level: args.confidenceLevel,
      rag_status: aprovado ? "aprovado" : "recusado",
      notas: args.notas,
    });
  }
}

export function RevisaoConhecimentoDialog({
  docId,
  decisao,
  confidenceLevel,
  onFechar,
  onConcluido,
}: RevisaoConhecimentoProps) {
  const [doc, setDoc] = useState<DocumentoRevisao | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [notas, setNotas] = useState("");
  const [erro, setErro] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (!docId) {
      setDoc(null);
      setNotas("");
      setErro(null);
      setErroCarga(null);
      return;
    }
    let ativo = true;
    setCarregando(true);
    setErroCarga(null);
    api
      .get(`/rag/governanca/docs/${docId}`)
      .then((r) => {
        if (ativo) setDoc(r.data as DocumentoRevisao);
      })
      .catch((e) => {
        if (ativo)
          setErroCarga(
            mensagemErroHttp(e, "Não foi possível abrir o documento."),
          );
      })
      .finally(() => {
        if (ativo) setCarregando(false);
      });
    return () => {
      ativo = false;
    };
  }, [docId]);

  const confirmar = async () => {
    if (!docId) return;
    const texto = notas.trim();
    if (!texto) {
      setErro(ERRO_NOTAS_OBRIGATORIAS);
      return;
    }
    setEnviando(true);
    setErro(null);
    try {
      await registrarRevisaoConhecimento({
        docId,
        decisao,
        notas: texto,
        confidenceLevel,
      });
      setNotas("");
      onConcluido();
    } catch (e) {
      setErro(mensagemErroHttp(e, "Não foi possível registrar a revisão."));
    } finally {
      setEnviando(false);
    }
  };

  const aprovar = decisao === "aprovar";
  const trechos = trechosDoExtra(doc?.extra);
  const citacao = citacaoTexto(doc?.citacao);

  return (
    <Modal
      open={docId !== null}
      onClose={onFechar}
      title={
        aprovar
          ? "Aprovar documento para a IA"
          : "Rejeitar documento da base de conhecimento"
      }
      size="lg"
      footer={
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="btn-secondary text-sm"
            onClick={onFechar}
            disabled={enviando}
          >
            Cancelar
          </button>
          <button
            type="button"
            className={`${aprovar ? "btn-primary" : "btn-danger"} inline-flex items-center gap-1 text-sm`}
            onClick={() => void confirmar()}
            disabled={enviando || carregando || Boolean(erroCarga)}
          >
            {aprovar ? <CheckCircle2 size={14} /> : <XCircle size={14} />}
            {enviando
              ? "Registrando…"
              : aprovar
                ? confidenceLevel
                  ? `Aprovar (confiança ${confidenceLevel})`
                  : "Aprovar"
                : "Rejeitar"}
          </button>
        </div>
      }
    >
      <div className="space-y-3 text-sm">
        {carregando && (
          <div className="flex items-center gap-2 text-slate-500">
            <Spinner /> Carregando documento…
          </div>
        )}
        {erroCarga && (
          <p role="alert" className="text-danger-600">
            {erroCarga}
          </p>
        )}
        {doc && (
          <>
            <div>
              <h3 className="font-semibold text-navy">{doc.titulo}</h3>
              <p className="text-xs text-slate-500">
                {[doc.categoria, doc.tribunal, doc.fonte]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
              <div>
                <dt className="text-slate-400">Autoridade</dt>
                <dd className="font-medium text-slate-700">
                  {doc.autoridade?.label ?? doc.autoridade?.code ?? "—"}
                  {doc.autoridade?.official ? " (oficial)" : ""}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Situação jurídica</dt>
                <dd className="font-medium text-slate-700">
                  {doc.situacao_juridica?.label ??
                    doc.situacao_juridica?.code ??
                    "—"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Qualidade</dt>
                <dd className="font-medium text-slate-700">
                  {doc.qualidade?.score != null
                    ? `${doc.qualidade.score} · ${doc.qualidade.status ?? ""}`
                    : "—"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Indexação</dt>
                <dd className="font-medium text-slate-700">
                  {doc.metricas?.chunks ?? 0} blocos ·{" "}
                  {doc.metricas?.chars ?? 0} caracteres
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Versão</dt>
                <dd className="font-medium text-slate-700">
                  {doc.versao ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="text-slate-400">Frescor</dt>
                <dd className="font-medium text-slate-700">
                  {doc.frescor?.status ?? "—"}
                </dd>
              </div>
            </dl>
            {doc.qualidade?.issues && doc.qualidade.issues.length > 0 && (
              <div className="flex items-start gap-2 rounded-lg border border-warn-200 bg-warn-50 p-2 text-xs text-warn-800">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <ul className="list-disc pl-4">
                  {doc.qualidade.issues.map((issue, i) => (
                    <li key={i}>{issue}</li>
                  ))}
                </ul>
              </div>
            )}
            {citacao && (
              <p className="rounded border border-slate-200 bg-slate-50 p-2 text-xs text-slate-700">
                <span className="font-semibold">Citação: </span>
                {citacao}
              </p>
            )}
            {trechos.length > 0 ? (
              <div className="max-h-72 space-y-2 overflow-auto rounded-lg border border-slate-200 bg-white p-3">
                {trechos.map(([rotulo, valor]) => (
                  <div key={rotulo}>
                    <p className="text-[11px] font-semibold uppercase text-slate-500">
                      {rotulo}
                    </p>
                    <p className="whitespace-pre-wrap text-xs leading-relaxed text-slate-700">
                      {valor}
                    </p>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-500">
                Este documento não tem trecho textual nos metadados — confira o
                original pela fonte indicada acima antes de decidir.
              </p>
            )}
          </>
        )}
        <label className="block">
          <span className="label">Notas da revisão *</span>
          <textarea
            className="input w-full"
            rows={3}
            value={notas}
            onChange={(e) => setNotas(e.target.value)}
            placeholder={
              aprovar
                ? "Ex.: ementa conferida no site do TJMG em DD/MM; vigente; adequada para consumidor/JEC."
                : "Ex.: decisão superada por súmula posterior; não deve alimentar a IA."
            }
            aria-label="Notas da revisão"
          />
        </label>
        {erro && (
          <p role="alert" className="text-xs text-danger-600">
            {erro}
          </p>
        )}
        <p className="text-xs text-slate-500">
          A decisão fica registrada em auditoria (REVISAO_CONHECIMENTO) com seu
          usuário, data e estas notas.
        </p>
      </div>
    </Modal>
  );
}
