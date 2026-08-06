import { DragEvent, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Archive,
  CheckCircle2,
  FileArchive,
  FileImage,
  FileSpreadsheet,
  FileText,
  Loader2,
  PackageCheck,
  Plus,
  ScanLine,
  ShieldCheck,
  Trash2,
  UploadCloud,
} from "lucide-react";
import api from "../lib/api";
import { toast } from "./Toast";
import { detalheErro } from "../utils/erro";

export type EntradaUniversalResultado = {
  ok: boolean;
  batch_id: string;
  nivel_prontidao?: string;
  prontidao?: any;
  documentos?: any[];
  documentos_faltantes?: string[];
  comparacoes?: any[];
  pacote?: any[];
  classificacao?: any;
  identificacao_processual?: any;
  partes?: any;
  dados_pessoais?: any;
  resumo_executivo?: any;
  estrategia?: any;
  matriz_vicios_teses?: any[];
  datas_eventos?: any[];
  prazo?: any;
  dados_bancarios?: any;
  aviso?: string;
  /** Procedência da leitura por IA: modelo, provedor e id do log de auditoria. */
  ia?: {
    disponivel?: boolean;
    estrutura_valida?: boolean;
    modelo?: string | null;
    provider?: string | null;
    ai_log_id?: string | null;
    sem_base_verificavel?: boolean;
  };
  /** Fontes da base interna (RAG) consultadas para a análise. */
  fontes?: { titulo?: string; categoria?: string; fonte?: string }[];
  citacoes?: any;
  alertas_ia?: string[];
  /** Somente no navegador: mantém compatibilidade com o fluxo antigo de criação. */
  _arquivos_locais?: File[];
};

type Props = {
  modalidade?: string;
  caseId?: string;
  clientId?: string;
  texto?: string;
  onTextoChange?: (value: string) => void;
  onProcessado: (resultado: EntradaUniversalResultado) => void | Promise<void>;
  compact?: boolean;
  processarLabel?: string;
  titulo?: string;
  descricao?: string;
};

const ACCEPT = [
  ".pdf",
  ".docx",
  ".doc",
  ".jpg",
  ".jpeg",
  ".png",
  ".tiff",
  ".tif",
  ".webp",
  ".heic",
  ".heif",
  ".txt",
  ".xlsx",
  ".xls",
  ".csv",
  ".xml",
  ".zip",
].join(",");
const MAX_FILES = 60;
const MAX_TOTAL = 120 * 1024 * 1024;

const formatBytes = (value: number) => {
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 ** 2).toFixed(1)} MB`;
};

const iconFor = (name: string) => {
  const ext = name.toLowerCase().split(".").pop();
  if (
    ["jpg", "jpeg", "png", "tiff", "tif", "webp", "heic", "heif"].includes(
      ext || "",
    )
  )
    return FileImage;
  if (["xlsx", "xls", "csv"].includes(ext || "")) return FileSpreadsheet;
  if (ext === "zip") return FileArchive;
  return FileText;
};

const readiness = (nivel?: string) => {
  if (nivel === "apto_para_redacao")
    return {
      label: "Apto para redação",
      cls: "bg-success-50 text-success-800 ring-success-200",
      Icon: CheckCircle2,
    };
  if (nivel === "nao_apto_para_redacao")
    return {
      label: "Não apto para redação",
      cls: "bg-danger-50 text-danger-800 ring-danger-200",
      Icon: AlertTriangle,
    };
  return {
    label: "Apto com ressalvas",
    cls: "bg-warn-50 text-warn-800 ring-warn-200",
    Icon: AlertTriangle,
  };
};

export default function EntradaUniversalDocumentos({
  modalidade,
  caseId,
  clientId,
  texto = "",
  onTextoChange,
  onProcessado,
  compact = false,
  processarLabel = "Importar, ler e organizar",
  titulo = "Entrada Universal de Documentos",
  descricao = "Envie vários documentos de uma vez. O original é preservado antes do OCR, e cada página mantém origem e confiança.",
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resultado, setResultado] = useState<EntradaUniversalResultado | null>(
    null,
  );
  const [localTexto, setLocalTexto] = useState(texto);
  const totalBytes = useMemo(
    () => files.reduce((sum, file) => sum + file.size, 0),
    [files],
  );
  const textValue = onTextoChange ? texto : localTexto;
  const updateText = (value: string) =>
    onTextoChange ? onTextoChange(value) : setLocalTexto(value);

  const adicionar = (incoming: FileList | File[]) => {
    const list = Array.from(incoming);
    setFiles((current) => {
      const unique = new Map(
        current.map((file) => [
          `${file.name}:${file.size}:${file.lastModified}`,
          file,
        ]),
      );
      list.forEach((file) =>
        unique.set(`${file.name}:${file.size}:${file.lastModified}`, file),
      );
      const next = Array.from(unique.values());
      if (next.length > MAX_FILES) {
        toast.error(`O lote aceita no máximo ${MAX_FILES} arquivos.`);
        return current;
      }
      if (next.reduce((sum, file) => sum + file.size, 0) > MAX_TOTAL) {
        toast.error("O lote não pode ultrapassar 120 MB.");
        return current;
      }
      return next;
    });
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files?.length) adicionar(event.dataTransfer.files);
  };

  const processar = async () => {
    if (!files.length && textValue.trim().length < 40) {
      toast.error("Envie ao menos um documento ou informe texto suficiente.");
      return;
    }
    const form = new FormData();
    files.forEach((file) => form.append("files", file));
    if (modalidade) form.append("modalidade", modalidade);
    if (caseId) form.append("case_id", caseId);
    if (clientId) form.append("client_id", clientId);
    if (textValue.trim()) form.append("texto", textValue.trim());
    form.append("confidencialidade", "normal");
    setLoading(true);
    setResultado(null);
    try {
      const { data } = await api.post<EntradaUniversalResultado>(
        "/entrada-universal/processar",
        form,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      );
      const resultadoComArquivos: EntradaUniversalResultado = {
        ...data,
        _arquivos_locais: [...files],
      };
      setResultado(data);
      await onProcessado(resultadoComArquivos);
      toast.success(
        `${data.documentos?.length || 0} documento(s) processado(s) e preservado(s) no GED.`,
      );
    } catch (error: unknown) {
      toast.error(
        detalheErro(error, "Falha ao processar o pacote documental."),
      );
    } finally {
      setLoading(false);
    }
  };

  const status = readiness(resultado?.nivel_prontidao);
  const StatusIcon = status.Icon;

  return (
    <section
      className={`rounded-2xl border border-primary-100 bg-white dark:border-white/10 dark:bg-white/[0.03] ${compact ? "p-4" : "p-5"}`}
    >
      <div className="flex flex-col justify-between gap-3 md:flex-row md:items-start">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-primary-700">
            <ScanLine className="h-4 w-4" /> Importação obrigatória e auditável
          </div>
          <h3 className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">
            {titulo}
          </h3>
          <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-500 dark:text-slate-300">
            {descricao}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5 text-[10px] text-slate-500">
          <span className="rounded-full bg-slate-100 px-2 py-1">PDF/Word</span>
          <span className="rounded-full bg-slate-100 px-2 py-1">
            Fotos/HEIC
          </span>
          <span className="rounded-full bg-slate-100 px-2 py-1">Planilhas</span>
          <span className="rounded-full bg-slate-100 px-2 py-1">ZIP</span>
        </div>
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        className="hidden"
        onChange={(event) => {
          if (event.target.files) adicionar(event.target.files);
          event.target.value = "";
        }}
      />

      <div
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`mt-4 rounded-2xl border-2 border-dashed p-5 text-center transition ${dragging ? "border-primary-500 bg-primary-50" : "border-slate-200 bg-slate-50/70 dark:border-white/10 dark:bg-white/[0.02]"}`}
      >
        <UploadCloud className="mx-auto h-8 w-8 text-primary-600" />
        <p className="mt-2 text-sm font-medium text-slate-900 dark:text-white">
          Arraste documentos ou selecione vários arquivos
        </p>
        <p className="mt-1 text-xs text-slate-500">
          Até 60 arquivos e 120 MB por lote. ZIP é descompactado com validação
          de segurança.
        </p>
        <button
          type="button"
          className="btn-secondary mt-3 inline-flex items-center gap-2"
          onClick={() => inputRef.current?.click()}
          disabled={loading}
        >
          <Plus className="h-4 w-4" /> Selecionar arquivos
        </button>
      </div>

      {files.length > 0 && (
        <div className="mt-3 rounded-xl border border-slate-200 dark:border-white/10">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2 text-xs dark:border-white/10">
            <span className="font-semibold text-slate-700 dark:text-slate-200">
              {files.length} arquivo(s)
            </span>
            <span className="text-slate-500">{formatBytes(totalBytes)}</span>
          </div>
          <div className="max-h-48 divide-y divide-slate-100 overflow-y-auto dark:divide-white/10">
            {files.map((file, index) => {
              const Icon = iconFor(file.name);
              return (
                <div
                  key={`${file.name}:${file.size}:${file.lastModified}`}
                  className="flex items-center gap-3 px-3 py-2"
                >
                  <Icon className="h-4 w-4 shrink-0 text-primary-600" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-xs font-medium text-slate-800 dark:text-slate-100">
                      {index + 1}. {file.name}
                    </p>
                    <p className="text-[10px] text-slate-400">
                      {formatBytes(file.size)}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="rounded-lg p-1.5 text-slate-400 hover:bg-danger-50 hover:text-danger-600"
                    onClick={() =>
                      setFiles((current) =>
                        current.filter((item) => item !== file),
                      )
                    }
                    aria-label={`Remover ${file.name}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-3">
        <label className="label">Informações complementares do advogado</label>
        <textarea
          className="input min-h-24 w-full"
          value={textValue}
          onChange={(event) => updateText(event.target.value)}
          placeholder="Acrescente fatos que não constam dos arquivos. O sistema identificará esse conteúdo como informação fornecida pelo advogado."
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-gold inline-flex items-center gap-2"
          disabled={loading}
          onClick={processar}
        >
          {loading ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Archive className="h-4 w-4" />
          )}
          {loading ? "Preservando, lendo e analisando…" : processarLabel}
        </button>
        {files.length > 0 && (
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={() => setFiles([])}
            disabled={loading}
          >
            Limpar seleção
          </button>
        )}
      </div>

      {resultado && (
        <div className="mt-5 space-y-4 border-t border-slate-200 pt-4 dark:border-white/10">
          <div
            className={`flex items-start gap-3 rounded-xl p-3 ring-1 ${status.cls}`}
          >
            <StatusIcon className="mt-0.5 h-5 w-5 shrink-0" />
            <div>
              <p className="text-sm font-semibold">{status.label}</p>
              <p className="mt-0.5 text-xs">
                {resultado.prontidao?.justificativa ||
                  "Revisão humana obrigatória."}
              </p>
              <p className="mt-1 text-[10px] opacity-75">
                Lote: {resultado.batch_id}
              </p>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {(resultado.documentos || []).map((doc: any, index: number) => (
              <article
                key={doc.id || `${doc.filename}-${index}`}
                className="rounded-xl border border-slate-200 p-3 dark:border-white/10"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-xs font-semibold text-slate-900 dark:text-white">
                      {index + 1}. {doc.filename}
                    </p>
                    <p className="mt-0.5 text-[10px] text-slate-500">
                      {doc.classification?.nome ||
                        doc.classification?.tipo ||
                        "Não classificado"}
                    </p>
                  </div>
                  {doc.duplicate_of_document_id && (
                    <span className="rounded-full bg-warn-50 px-2 py-0.5 text-[10px] font-semibold text-warn-700">
                      duplicado
                    </span>
                  )}
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-slate-500">
                  <span>
                    {doc.page_count || doc.paginas?.length || 0} página(s)
                  </span>
                  <span>•</span>
                  <span>
                    confiança {Math.round((doc.confianca_media ?? 0) * 100)}%
                  </span>
                  <span>•</span>
                  <span>{doc.extraction_status || "concluído"}</span>
                </div>
                {(doc.paginas || []).some(
                  (page: any) => page.requer_revisao,
                ) && (
                  <p className="mt-2 flex items-center gap-1 text-[10px] font-medium text-warn-700">
                    <AlertTriangle className="h-3 w-3" /> Há página com leitura
                    a conferir.
                  </p>
                )}
              </article>
            ))}
          </div>

          {(resultado.documentos_faltantes || []).length > 0 && (
            <div className="rounded-xl border border-danger-200 bg-danger-50 p-3">
              <p className="text-xs font-semibold text-danger-800">
                Documentos obrigatórios ausentes
              </p>
              <ul className="mt-2 space-y-1 text-xs text-danger-700">
                {resultado.documentos_faltantes?.map((item) => (
                  <li key={item}>• {item}</li>
                ))}
              </ul>
            </div>
          )}

          {(resultado.comparacoes || []).length > 0 && (
            <div className="rounded-xl border border-warn-200 bg-warn-50 p-3">
              <p className="text-xs font-semibold text-warn-900">
                Divergências encontradas entre documentos
              </p>
              <div className="mt-2 space-y-2">
                {resultado.comparacoes?.map((item: any, index: number) => (
                  <div
                    key={index}
                    className="rounded-lg bg-white/70 p-2 text-xs text-warn-800"
                  >
                    <b>{item.titulo}</b>
                    <p className="mt-1 text-[11px]">
                      {(item.detalhes || [])
                        .map(
                          (detail: any) =>
                            `${detail.documento}: ${(detail.valores || []).join(", ")}`,
                        )
                        .join(" | ")}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {(resultado.pacote || []).length > 0 && (
            <div className="rounded-xl border border-slate-200 p-3 dark:border-white/10">
              <p className="flex items-center gap-2 text-xs font-semibold text-slate-900 dark:text-white">
                <PackageCheck className="h-4 w-4 text-primary-600" /> Pacote
                jurídico preparado
              </p>
              <div className="mt-2 grid gap-1.5 md:grid-cols-2">
                {resultado.pacote?.map((item: any) => (
                  <div
                    key={item.codigo}
                    className="flex items-center justify-between rounded-lg bg-slate-50 px-2.5 py-2 text-xs dark:bg-white/[0.04]"
                  >
                    <span>{item.nome}</span>
                    <span
                      className={`rounded-full px-2 py-0.5 text-[10px] font-semibold ${item.status === "disponivel" ? "bg-success-50 text-success-700" : "bg-slate-200 text-slate-600"}`}
                    >
                      {item.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
          <div className="rounded-xl border border-slate-200 p-3 dark:border-white/10">
            <p className="flex items-center gap-2 text-xs font-semibold text-slate-900 dark:text-white">
              <ShieldCheck className="h-4 w-4 text-primary-600" /> Procedência
              da leitura por IA
            </p>
            {resultado.ia?.disponivel === false ? (
              <p className="mt-2 text-[11px] text-warn-800">
                A interpretação por IA ficou indisponível. A extração
                determinística e os originais no GED foram preservados.
              </p>
            ) : (
              <>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-600 dark:text-slate-300">
                  <span>
                    Modelo:{" "}
                    <b className="font-medium">
                      {resultado.ia?.modelo || "não informado"}
                    </b>
                  </span>
                  <span>
                    Provedor:{" "}
                    <b className="font-medium">
                      {resultado.ia?.provider || "não informado"}
                    </b>
                  </span>
                  <span>
                    Log de auditoria:{" "}
                    <b className="font-mono font-medium">
                      {resultado.ia?.ai_log_id || "não registrado"}
                    </b>
                  </span>
                </div>
                {resultado.ia?.estrutura_valida === false && (
                  <p className="mt-2 flex items-start gap-1 text-[11px] font-medium text-danger-700">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" /> A IA
                    não devolveu leitura estruturada: área, partes, datas, prazo
                    e teses não foram preenchidos. Preencha o caso manualmente.
                  </p>
                )}
                <p className="mt-2 text-[11px] font-medium text-slate-700 dark:text-slate-200">
                  Fontes da base interna consultadas
                </p>
                {(resultado.fontes || []).length > 0 ? (
                  <ul className="mt-1 space-y-1 text-[11px] text-slate-600 dark:text-slate-300">
                    {resultado.fontes?.map((fonte, index) => (
                      <li key={`${fonte.titulo}-${index}`}>
                        • {fonte.titulo || "sem título"}
                        {fonte.categoria ? ` — ${fonte.categoria}` : ""}
                        {fonte.fonte ? ` (${fonte.fonte})` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-[11px] text-warn-800">
                    Nenhuma fonte da base interna respaldou esta leitura — ela
                    se apoia apenas nos documentos enviados. Confira toda norma,
                    prazo ou precedente antes de usar.
                  </p>
                )}
                {resultado.ia?.sem_base_verificavel && (
                  <div className="mt-2 flex items-start gap-2 rounded bg-warn-50 p-2 dark:bg-warn-900/20">
                    <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-warn-700 dark:text-warn-400" />
                    <p className="text-[11px] text-warn-700 dark:text-warn-400">
                      A IA mencionou normas, prazos ou precedentes que não foram
                      verificados em fontes internas. Use com cautela.
                    </p>
                  </div>
                )}
                {(resultado.citacoes || []).length > 0 && (
                  <div className="mt-2">
                    <p className="text-[11px] font-medium text-slate-700 dark:text-slate-200">
                      Citações
                    </p>
                    <ul className="mt-1 space-y-1 text-[11px] text-slate-600 dark:text-slate-300">
                      {resultado.citacoes?.map(
                        (citacao: string, index: number) => (
                          <li key={index} className="ml-2">
                            • {citacao}
                          </li>
                        ),
                      )}
                    </ul>
                  </div>
                )}
                {(resultado.alertas_ia || []).length > 0 && (
                  <ul className="mt-2 space-y-1 text-[11px] text-warn-800">
                    {resultado.alertas_ia?.map((alerta, index) => (
                      <li key={index} className="flex items-start gap-1">
                        <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                        {alerta}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>

          <p className="text-[11px] text-slate-500">{resultado.aviso}</p>
        </div>
      )}
    </section>
  );
}
