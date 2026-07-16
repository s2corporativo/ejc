import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  Archive,
  ArrowRight,
  CheckCircle2,
  Download,
  FileSearch,
  FileText,
  FolderInput,
  Loader2,
  Plus,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../stores/auth";
import {
  Badge,
  Button,
  EmptyState,
  PageHeader,
  SectionCard,
  StatCard,
  StatusBadge,
} from "../components/UI";

type Documento = {
  id: string;
  nome_original: string;
  tipo_documento?: string | null;
  size_bytes: number;
  ocr_utilizado: boolean;
};

type Relatorio = {
  aviso?: string;
  identificacao?: Record<string, unknown>;
  sintese_executiva?: string;
  partes?: unknown[];
  cronologia?: Array<Record<string, unknown>>;
  fatos_provas?: Array<Record<string, unknown>>;
  pedidos?: unknown[];
  provas?: unknown[];
  contradicoes?: unknown[];
  decisoes?: unknown[];
  prazos_potenciais?: unknown[];
  riscos?: unknown[];
  teses?: unknown[];
  pontos_fortes?: unknown[];
  pontos_fracos?: unknown[];
  proximos_passos?: unknown[];
  documentos_pendentes?: unknown[];
  [key: string]: unknown;
};

type Analise = {
  id: string;
  titulo: string;
  potencial_cliente?: string | null;
  numero_processo?: string | null;
  area?: string | null;
  fase?: string | null;
  tribunal?: string | null;
  status: string;
  risco_nivel?: string | null;
  prazo_urgente: boolean;
  relatorio: Relatorio;
  revisao_humana: Record<string, unknown>;
  alertas_conflito: unknown[];
  convertido_case_id?: string | null;
  documentos: Documento[];
  created_at?: string;
  updated_at?: string;
};

type Stats = {
  total: number;
  pendentes_conferencia: number;
  convertidos: number;
  por_status: Record<string, number>;
};

type ConversionPreview = {
  casos_possivelmente_duplicados: Array<Record<string, unknown>>;
  clientes_possivelmente_duplicados: Array<Record<string, unknown>>;
  alertas_conflito: unknown[];
  documentos_disponiveis: Array<{ id: string; nome: string; tipo?: string }>;
  prazos_potenciais: unknown[];
  tarefas_sugeridas: unknown[];
  bloqueia: boolean;
};

const AREAS = [
  "civil",
  "trabalhista",
  "consumidor",
  "familia",
  "criminal",
  "previdenciario",
  "empresarial",
  "tributario",
  "administrativo",
  "bancario",
  "imobiliario",
  "sucessoes",
  "ambiental",
  "digital_lgpd",
  "transito",
];

const CONVERSION_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
]);

const humanize = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());

const stringify = (value: unknown) => {
  if (value == null) return "—";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const preferred =
      record.valor ?? record.texto ?? record.descricao ?? record.titulo ?? record.nome;
    if (preferred != null) return stringify(preferred);
  }
  return JSON.stringify(value);
};

function ReportList({ title, items }: { title: string; items?: unknown[] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <h3 className="text-sm font-semibold text-slate-950 dark:text-white">{title}</h3>
      {!items?.length ? (
        <p className="mt-2 text-sm text-slate-500">
          Nenhum item identificado com segurança.
        </p>
      ) : (
        <ul className="mt-3 space-y-2 text-sm text-slate-700 dark:text-slate-200">
          {items.map((item, index) => (
            <li
              key={index}
              className="rounded-lg bg-slate-50 px-3 py-2 dark:bg-white/[0.04]"
            >
              {stringify(item)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function RaioXProcesso() {
  const [searchParams] = useSearchParams();
  const contextualCaseId = searchParams.get("case_id");
  const user = useAuth((state) => state.user);
  const canConvert = CONVERSION_ROLES.has(String(user?.role || ""));

  const [items, setItems] = useState<Analise[]>([]);
  const [stats, setStats] = useState<Stats>({
    total: 0,
    pendentes_conferencia: 0,
    convertidos: 0,
    por_status: {},
  });
  const [selected, setSelected] = useState<Analise | null>(null);
  const [contextual, setContextual] = useState<Relatorio | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newClient, setNewClient] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [reviewText, setReviewText] = useState("");
  const [conversion, setConversion] = useState<ConversionPreview | null>(null);
  const [showConversion, setShowConversion] = useState(false);
  const [existingClientId, setExistingClientId] = useState("");
  const [newClientName, setNewClientName] = useState("");
  const [newClientCpf, setNewClientCpf] = useState("");
  const [caseTitle, setCaseTitle] = useState("");
  const [caseArea, setCaseArea] = useState("civil");
  const [caseNumber, setCaseNumber] = useState("");
  const [transferDeadlines, setTransferDeadlines] = useState(false);
  const [transferTasks, setTransferTasks] = useState(false);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [confirmDuplicate, setConfirmDuplicate] = useState(false);
  const [confirmConflict, setConfirmConflict] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  const loadList = useCallback(async () => {
    const [{ data: list }, { data: metric }] = await Promise.all([
      api.get("/raio-x/", { params: { page_size: 100 } }),
      api.get("/raio-x/stats"),
    ]);
    setItems(list.data || []);
    setStats(metric);
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        if (contextualCaseId) {
          const { data } = await api.get(`/raio-x/contextual/${contextualCaseId}`);
          if (active) setContextual(data);
        } else {
          await loadList();
        }
      } catch (err: any) {
        if (active) {
          setError(err?.response?.data?.detail || "Não foi possível carregar o Raio-X.");
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [contextualCaseId, loadList]);

  useEffect(() => {
    setReviewText(
      String(
        selected?.revisao_humana?.sintese_revisada ||
          selected?.relatorio?.sintese_executiva ||
          "",
      ),
    );
    if (selected) {
      setCaseTitle(selected.titulo);
      setCaseArea(selected.area || "civil");
      setCaseNumber(selected.numero_processo || "");
      setNewClientName(selected.potencial_cliente || "");
    }
  }, [selected]);

  const detail = async (id: string) => {
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.get<Analise>(`/raio-x/${id}`);
      setSelected(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao abrir a análise.");
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (newTitle.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post<Analise>("/raio-x/", {
        titulo: newTitle.trim(),
        potencial_cliente: newClient.trim() || null,
      });
      setSelected(data);
      setCreating(false);
      setNewTitle("");
      setNewClient("");
      await loadList();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao criar análise.");
    } finally {
      setBusy(false);
    }
  };

  const upload = async () => {
    if (!selected || !files.length) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    try {
      const { data } = await api.post(
        `/raio-x/${selected.id}/documentos/analisar`,
        body,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      setSelected(data.analise);
      setFiles([]);
      const notes = [
        data.duplicados?.length
          ? `${data.duplicados.length} duplicado(s) ignorado(s)`
          : "",
        data.erros?.length ? `${data.erros.length} arquivo(s) com erro` : "",
      ].filter(Boolean);
      setMessage(`Análise concluída.${notes.length ? ` ${notes.join("; ")}.` : ""}`);
      await loadList();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao analisar documentos.");
    } finally {
      setBusy(false);
    }
  };

  const downloadDocument = async (documento: Documento) => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const response = await api.get(
        `/raio-x/${selected.id}/documentos/${documento.id}/download`,
        { responseType: "blob" },
      );
      const href = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = documento.nome_original;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(href);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Não foi possível baixar o documento.");
    } finally {
      setBusy(false);
    }
  };

  const saveReview = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.patch<Analise>(`/raio-x/${selected.id}`, {
        status: "analise_concluida",
        numero_processo: caseNumber || null,
        area: caseArea,
        revisao_humana: {
          ...selected.revisao_humana,
          sintese_revisada: reviewText,
          conferido_em: new Date().toISOString(),
        },
      });
      setSelected(data);
      setMessage("Conferência humana salva. O relatório está pronto para decisão.");
      await loadList();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao salvar conferência.");
    } finally {
      setBusy(false);
    }
  };

  const openConversion = async () => {
    if (!selected || !canConvert) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.get<ConversionPreview>(
        `/raio-x/${selected.id}/conversao/preview`,
      );
      setConversion(data);
      setSelectedDocumentIds(data.documentos_disponiveis.map((doc) => doc.id));
      setConfirmDuplicate(false);
      setConfirmConflict(false);
      setConfirmText("");
      setExistingClientId("");
      setShowConversion(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao preparar a conversão.");
    } finally {
      setBusy(false);
    }
  };

  const toggleDocument = (id: string) => {
    setSelectedDocumentIds((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    );
  };

  const requiresDuplicateConfirmation =
    Boolean(conversion?.casos_possivelmente_duplicados.length);
  const requiresConflictConfirmation = Boolean(conversion?.alertas_conflito.length);
  const conversionConfirmed =
    confirmText === "TRANSFORMAR EM CASO DO ESCRITÓRIO" &&
    (!requiresDuplicateConfirmation || confirmDuplicate) &&
    (!requiresConflictConfirmation || confirmConflict);

  const convert = async () => {
    if (!selected || !conversion || !canConvert || !conversionConfirmed) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post(`/raio-x/${selected.id}/converter`, {
        cliente: existingClientId
          ? { modo: "existente", client_id: existingClientId }
          : { modo: "novo", nome: newClientName, cpf: newClientCpf || null },
        caso: {
          titulo: caseTitle,
          area: caseArea,
          numero_processo: caseNumber || null,
          descricao_fatos: reviewText || selected.relatorio?.sintese_executiva,
          prioridade: selected.prazo_urgente ? "critica" : "media",
        },
        documento_ids: selectedDocumentIds,
        transferir_prazos: transferDeadlines,
        transferir_tarefas: transferTasks,
        duplicate_confirmed: confirmDuplicate,
        conflict_confirmed: confirmConflict,
        confirmacao: confirmText,
      });
      setShowConversion(false);
      setMessage("Caso oficial criado com trilha de auditoria. Redirecionando…");
      window.location.assign(`/casos/${data.case_id}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao converter em caso.");
    } finally {
      setBusy(false);
    }
  };

  const archive = async (mode: "arquivar" | "descartar") => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/raio-x/${selected.id}/${mode}`);
      setSelected(null);
      setMessage(mode === "arquivar" ? "Análise arquivada." : "Análise descartada.");
      await loadList();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "A operação não pôde ser concluída.");
    } finally {
      setBusy(false);
    }
  };

  const exportReport = () => {
    if (!report) return;
    const blob = new Blob([JSON.stringify(report, null, 2)], {
      type: "application/json",
    });
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = href;
    anchor.download = `raio-x-${selected?.id || contextualCaseId || "processo"}.json`;
    anchor.click();
    URL.revokeObjectURL(href);
  };

  const report = contextual || selected?.relatorio;
  const identification = report?.identificacao || {};
  const contextTitle = contextualCaseId
    ? String(identification.titulo || "Caso")
    : null;
  const sourceCount = useMemo(() => selected?.documentos?.length || 0, [selected]);

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow={contextualCaseId ? "Inteligência contextual" : "Análise preliminar isolada"}
        title={contextualCaseId ? `Raio-X · ${contextTitle}` : "Raio-X do Processo"}
        subtitle={
          contextualCaseId
            ? "Leitura estratégica do caso existente, sem criar ou converter cadastros."
            : "Analise documentos externos antes de decidir se o escritório deve aceitar e cadastrar o caso."
        }
        actions={
          contextualCaseId ? (
            <Link to={`/casos/${contextualCaseId}`}>
              <Button variant="secondary">Voltar ao caso</Button>
            </Link>
          ) : (
            <Button onClick={() => setCreating(true)}>
              <Plus className="h-4 w-4" /> Nova análise
            </Button>
          )
        }
      />

      <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <strong>Ambiente preliminar:</strong> nada aqui altera clientes, casos,
          indicadores, prazos ou tarefas oficiais antes da confirmação humana.
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}
      {message && (
        <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700">
          {message}
        </div>
      )}

      {!contextualCaseId && !selected && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard
              label="Análises preliminares"
              value={stats.total}
              icon={<ScanSearch className="h-5 w-5" />}
            />
            <StatCard
              label="Aguardando conferência"
              value={stats.pendentes_conferencia}
              icon={<FileSearch className="h-5 w-5" />}
              tone="amber"
            />
            <StatCard
              label="Convertidas em caso"
              value={stats.convertidos}
              icon={<FolderInput className="h-5 w-5" />}
              tone="green"
            />
          </div>
          <SectionCard
            title="Análises recentes"
            subtitle="Registros separados da carteira oficial do escritório."
          >
            {!items.length ? (
              <EmptyState
                title="Nenhuma análise preliminar"
                message="Crie um Raio-X e envie um ou mais documentos."
                icon={ScanSearch}
              />
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-white/10">
                {items.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => void detail(item.id)}
                    className="flex w-full items-center gap-3 px-2 py-4 text-left hover:bg-slate-50 dark:hover:bg-white/[0.03]"
                  >
                    <div className="rounded-xl bg-primary-50 p-2.5 text-primary-600 dark:bg-primary-400/10">
                      <ScanSearch className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-semibold text-slate-950 dark:text-white">
                        {item.titulo}
                      </div>
                      <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                        {item.potencial_cliente && <span>{item.potencial_cliente}</span>}
                        {item.numero_processo && <span>• {item.numero_processo}</span>}
                        {item.area && <Badge tone="blue">{item.area}</Badge>}
                      </div>
                    </div>
                    <StatusBadge value={item.status} />
                    <ArrowRight className="h-4 w-4 text-slate-400" />
                  </button>
                ))}
              </div>
            )}
          </SectionCard>
        </>
      )}

      {creating && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl dark:bg-slate-900">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Nova análise preliminar</h2>
              <button onClick={() => setCreating(false)} aria-label="Fechar">
                <X />
              </button>
            </div>
            <div className="mt-5 space-y-4">
              <label className="block text-sm font-medium">
                Título
                <input
                  value={newTitle}
                  onChange={(event) => setNewTitle(event.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
                  placeholder="Ex.: Processo recebido para avaliação"
                />
              </label>
              <label className="block text-sm font-medium">
                Potencial cliente
                <input
                  value={newClient}
                  onChange={(event) => setNewClient(event.target.value)}
                  className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
                  placeholder="Opcional"
                />
              </label>
              <div className="flex justify-end gap-2">
                <Button variant="secondary" onClick={() => setCreating(false)}>
                  Cancelar
                </Button>
                <Button onClick={() => void create()} disabled={busy || newTitle.trim().length < 3}>
                  {busy && <Loader2 className="h-4 w-4 animate-spin" />} Criar
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {(selected || contextual) && report && (
        <>
          {!contextual && selected && (
            <SectionCard
              title={selected.titulo}
              subtitle={`${sourceCount} documento(s) · ${humanize(selected.status)}`}
              actions={
                <Button variant="ghost" onClick={() => setSelected(null)}>
                  <X className="h-4 w-4" /> Fechar
                </Button>
              }
            >
              {selected.convertido_case_id ? (
                <div className="flex items-center justify-between rounded-xl bg-emerald-50 p-4 text-emerald-800">
                  <span className="flex items-center gap-2">
                    <CheckCircle2 className="h-5 w-5" /> Convertido com sucesso e
                    preservado para auditoria.
                  </span>
                  <Link to={`/casos/${selected.convertido_case_id}`} className="font-semibold">
                    Abrir caso
                  </Link>
                </div>
              ) : (
                <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
                  <label className="flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed border-primary-200 bg-primary-50/40 p-4 text-sm text-primary-800 dark:border-primary-400/30 dark:bg-primary-400/10 dark:text-primary-100">
                    <UploadCloud className="h-6 w-6" />
                    <span className="flex-1">
                      {files.length
                        ? `${files.length} arquivo(s) selecionado(s)`
                        : "Selecione PDF, DOCX, TXT ou imagens (múltiplos arquivos)"}
                    </span>
                    <input
                      type="file"
                      multiple
                      className="hidden"
                      accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff,.webp"
                      onChange={(event) => setFiles(Array.from(event.target.files || []))}
                    />
                  </label>
                  <Button onClick={() => void upload()} disabled={!files.length || busy}>
                    {busy ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}
                    Analisar lote
                  </Button>
                </div>
              )}
              {!!selected.documentos.length && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {selected.documentos.map((doc) => (
                    <button
                      key={doc.id}
                      type="button"
                      onClick={() => void downloadDocument(doc)}
                      className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200 dark:hover:bg-white/15"
                    >
                      <FileText className="h-3.5 w-3.5" />
                      {doc.nome_original}
                    </button>
                  ))}
                </div>
              )}
            </SectionCard>
          )}

          <div className="grid gap-5 xl:grid-cols-[1.4fr_0.6fr]">
            <div className="space-y-5">
              <SectionCard
                title="Síntese executiva"
                subtitle={report.aviso || "Conteúdo sujeito à conferência humana."}
              >
                <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-200">
                  {String(report.sintese_executiva || "Síntese não disponível.")}
                </p>
              </SectionCard>
              <div className="grid gap-4 md:grid-cols-2">
                <ReportList title="Partes" items={report.partes} />
                <ReportList title="Pedidos" items={report.pedidos} />
                <ReportList title="Provas" items={report.provas} />
                <ReportList title="Riscos" items={report.riscos} />
                <ReportList
                  title="Prazos potenciais"
                  items={report.prazos_potenciais || (report as any).prazos}
                />
                <ReportList title="Próximos passos" items={report.proximos_passos} />
              </div>
              <SectionCard title="Cronologia e matriz de conferência">
                <div className="grid gap-4 md:grid-cols-2">
                  <ReportList title="Cronologia" items={report.cronologia} />
                  <ReportList title="Fato × prova" items={report.fatos_provas} />
                </div>
              </SectionCard>
            </div>

            <div className="space-y-5">
              <SectionCard title="Identificação">
                <dl className="space-y-3 text-sm">
                  {Object.entries(identification).map(([key, value]) => (
                    <div
                      key={key}
                      className="flex justify-between gap-3 border-b border-slate-100 pb-2 dark:border-white/10"
                    >
                      <dt className="text-slate-500">{humanize(key)}</dt>
                      <dd className="text-right font-medium text-slate-900 dark:text-white">
                        {stringify(value)}
                      </dd>
                    </div>
                  ))}
                </dl>
              </SectionCard>

              {!contextual && selected && !selected.convertido_case_id && (
                <SectionCard
                  title="Conferência humana"
                  subtitle="Corrija o resultado antes de qualquer conversão."
                >
                  <div className="space-y-3">
                    <label className="block text-sm font-medium">
                      Número do processo
                      <input
                        value={caseNumber}
                        onChange={(event) => setCaseNumber(event.target.value)}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Área
                      <select
                        value={caseArea}
                        onChange={(event) => setCaseArea(event.target.value)}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 dark:border-white/10 dark:bg-slate-900"
                      >
                        {AREAS.map((area) => (
                          <option key={area}>{area}</option>
                        ))}
                      </select>
                    </label>
                    <label className="block text-sm font-medium">
                      Síntese revisada
                      <textarea
                        rows={8}
                        value={reviewText}
                        onChange={(event) => setReviewText(event.target.value)}
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/[0.04]"
                      />
                    </label>
                    <Button className="w-full" onClick={() => void saveReview()} disabled={busy}>
                      <CheckCircle2 className="h-4 w-4" /> Salvar conferência
                    </Button>
                  </div>
                </SectionCard>
              )}

              <SectionCard title="Ações">
                <div className="space-y-2">
                  <Button variant="secondary" className="w-full" onClick={exportReport}>
                    <Download className="h-4 w-4" /> Exportar relatório
                  </Button>
                  <Link to="/inteligencia" className="block">
                    <Button variant="ai" className="w-full">
                      <Sparkles className="h-4 w-4" /> Abrir IA contextual
                    </Button>
                  </Link>
                  {!contextual &&
                    selected &&
                    !selected.convertido_case_id &&
                    canConvert && (
                      <Button
                        className="w-full"
                        onClick={() => void openConversion()}
                        disabled={selected.status !== "analise_concluida"}
                      >
                        <FolderInput className="h-4 w-4" /> Transformar em caso
                      </Button>
                    )}
                  {!contextual &&
                    selected &&
                    !selected.convertido_case_id &&
                    !canConvert && (
                      <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-white/[0.04] dark:text-slate-300">
                        Seu perfil pode revisar o Raio-X, mas a conversão em caso oficial
                        deve ser feita por advogado autorizado ou pela gestão.
                      </p>
                    )}
                  {!contextual && selected && !selected.convertido_case_id && (
                    <div className="grid grid-cols-2 gap-2">
                      <Button variant="ghost" onClick={() => void archive("arquivar")}>
                        <Archive className="h-4 w-4" /> Arquivar
                      </Button>
                      <Button variant="danger" onClick={() => void archive("descartar")}>
                        <Trash2 className="h-4 w-4" /> Descartar
                      </Button>
                    </div>
                  )}
                  {!contextual && selected && (
                    <Button
                      variant="ghost"
                      className="w-full"
                      onClick={() =>
                        void api
                          .post(`/raio-x/${selected.id}/reanalisar`)
                          .then((response) => setSelected(response.data))
                      }
                    >
                      <RefreshCw className="h-4 w-4" /> Reconsolidar
                    </Button>
                  )}
                </div>
              </SectionCard>
            </div>
          </div>
        </>
      )}

      {showConversion && selected && conversion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-semibold">Transformar em caso do escritório</h2>
                <p className="mt-1 text-sm text-slate-500">
                  Revise duplicidades, cliente, documentos e itens a transferir.
                </p>
              </div>
              <button onClick={() => setShowConversion(false)} aria-label="Fechar">
                <X />
              </button>
            </div>

            {(conversion.bloqueia || requiresDuplicateConfirmation) && (
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                Existem alertas de duplicidade ou conflito. A confirmação abaixo é
                obrigatória e ficará registrada na trilha de auditoria.
              </div>
            )}

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <label className="block text-sm font-medium">
                Cliente existente
                <input
                  value={existingClientId}
                  onChange={(event) => setExistingClientId(event.target.value)}
                  className="mt-1 w-full rounded-xl border px-3 py-2 dark:bg-white/[0.04]"
                  placeholder="Selecione abaixo ou informe o ID"
                />
              </label>
              <label className="block text-sm font-medium">
                Nome do novo cliente
                <input
                  value={newClientName}
                  onChange={(event) => setNewClientName(event.target.value)}
                  disabled={Boolean(existingClientId)}
                  className="mt-1 w-full rounded-xl border px-3 py-2 disabled:opacity-50 dark:bg-white/[0.04]"
                />
              </label>
              <label className="block text-sm font-medium">
                CPF do novo cliente
                <input
                  value={newClientCpf}
                  onChange={(event) => setNewClientCpf(event.target.value)}
                  disabled={Boolean(existingClientId)}
                  className="mt-1 w-full rounded-xl border px-3 py-2 disabled:opacity-50 dark:bg-white/[0.04]"
                />
              </label>
              <label className="block text-sm font-medium">
                Título do caso
                <input
                  value={caseTitle}
                  onChange={(event) => setCaseTitle(event.target.value)}
                  className="mt-1 w-full rounded-xl border px-3 py-2 dark:bg-white/[0.04]"
                />
              </label>
            </div>

            {!!conversion.clientes_possivelmente_duplicados.length && (
              <div className="mt-4 rounded-xl border border-slate-200 p-4 dark:border-white/10">
                <h3 className="text-sm font-semibold">Clientes semelhantes encontrados</h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  {conversion.clientes_possivelmente_duplicados.map((client, index) => (
                    <button
                      type="button"
                      key={String(client.id || index)}
                      onClick={() => setExistingClientId(String(client.id || ""))}
                      className="rounded-lg border border-slate-200 px-3 py-2 text-left text-xs hover:border-primary-400 dark:border-white/10"
                    >
                      <strong>{String(client.nome || "Cliente")}</strong>
                      <span className="ml-2 text-slate-500">{String(client.id || "")}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mt-5 rounded-xl bg-slate-50 p-4 text-sm dark:bg-white/[0.04]">
              <h3 className="font-semibold">Documentos a incorporar ao GED</h3>
              <div className="mt-3 space-y-2">
                {conversion.documentos_disponiveis.map((doc) => (
                  <label key={doc.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedDocumentIds.includes(doc.id)}
                      onChange={() => toggleDocument(doc.id)}
                    />
                    <span>{doc.nome}</span>
                    {doc.tipo && <Badge tone="blue">{doc.tipo}</Badge>}
                  </label>
                ))}
                {!conversion.documentos_disponiveis.length && (
                  <p className="text-slate-500">Nenhum documento será transferido.</p>
                )}
              </div>
            </div>

            <div className="mt-4 space-y-3 rounded-xl bg-slate-50 p-4 text-sm dark:bg-white/[0.04]">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={transferDeadlines}
                  onChange={(event) => setTransferDeadlines(event.target.checked)}
                />
                Transferir prazos identificados como rascunho não confirmado
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={transferTasks}
                  onChange={(event) => setTransferTasks(event.target.checked)}
                />
                Transferir próximos passos como tarefas
              </label>
            </div>

            {requiresDuplicateConfirmation && (
              <label className="mt-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <input
                  className="mt-1"
                  type="checkbox"
                  checked={confirmDuplicate}
                  onChange={(event) => setConfirmDuplicate(event.target.checked)}
                />
                <span>
                  Revisei os casos possivelmente duplicados e confirmo conscientemente a
                  criação de um novo caso.
                </span>
              </label>
            )}

            {requiresConflictConfirmation && (
              <label className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-900">
                <input
                  className="mt-1"
                  type="checkbox"
                  checked={confirmConflict}
                  onChange={(event) => setConfirmConflict(event.target.checked)}
                />
                <span>
                  Revisei o alerta de conflito de interesses e confirmo que a conversão
                  está autorizada.
                </span>
              </label>
            )}

            <label className="mt-5 block text-sm font-medium">
              Digite exatamente{" "}
              <code className="rounded bg-slate-100 px-1">
                TRANSFORMAR EM CASO DO ESCRITÓRIO
              </code>
              <input
                value={confirmText}
                onChange={(event) => setConfirmText(event.target.value)}
                className="mt-2 w-full rounded-xl border px-3 py-2 dark:bg-white/[0.04]"
              />
            </label>

            <div className="mt-6 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setShowConversion(false)}>
                Cancelar
              </Button>
              <Button onClick={() => void convert()} disabled={busy || !conversionConfirmed}>
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} Confirmar conversão
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
