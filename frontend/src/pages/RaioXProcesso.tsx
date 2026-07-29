import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  AlertTriangle,
  Archive,
  ArrowRight,
  CheckCircle2,
  Download,
  FileSearch,
  FileText,
  Filter,
  FolderInput,
  Loader2,
  Plus,
  RefreshCw,
  ScanSearch,
  Scale,
  ShieldCheck,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
} from "lucide-react";
import api, {
  analiseAdvogadoContextual,
  analiseAdvogadoPorAnalise,
  type AnaliseAdvogadoResult,
} from "../lib/api";
import Markdown from "../components/Markdown";
import { useAuth } from "../stores/auth";
import {
  AIFactualityLegend,
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
  sintese_executiva_revisada?: string;
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
  rito_jornada?: Record<string, unknown>;
  avaliacao_risco?: Record<string, unknown>;
  risco_nivel?: string;
  prazo_urgente?: boolean;
  [key: string]: unknown;
};

type Analise = {
  id: string;
  titulo: string;
  potencial_cliente?: string | null;
  numero_processo?: string | null;
  area?: string | null;
  subarea?: string | null;
  rito?: string | null;
  fase?: string | null;
  tribunal?: string | null;
  orgao?: string | null;
  unidade?: string | null;
  posicao_cliente?: string | null;
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
  urgentes?: number;
  risco_elevado_ou_critico?: number;
  por_status: Record<string, number>;
};

type ConversionPreview = {
  casos_possivelmente_duplicados: Array<Record<string, unknown>>;
  clientes_possivelmente_duplicados: Array<Record<string, unknown>>;
  alertas_conflito: unknown[];
  documentos_disponiveis: Array<{ id: string; nome: string; tipo?: string }>;
  prazos_potenciais: unknown[];
  tarefas_sugeridas: unknown[];
  risco_nivel?: string;
  prazo_urgente?: boolean;
  rito_jornada?: Record<string, unknown>;
  bloqueia: boolean;
};

type Area = { slug: string; nome: string; ativo?: boolean };
type ContextualAction = {
  id: string;
  name: string;
  display_name: string;
  description?: string;
  reason: string;
  requires_case: boolean;
};

type ReviewFields = {
  numero_processo: string;
  area: string;
  subarea: string;
  rito: string;
  fase: string;
  tribunal: string;
  orgao: string;
  unidade: string;
  posicao_cliente: string;
  sintese: string;
};

const FALLBACK_AREAS: Area[] = [
  ["civil", "Direito Cível"],
  ["trabalhista", "Direito Trabalhista"],
  ["consumidor", "Direito do Consumidor"],
  ["familia", "Direito de Família"],
  ["sucessoes", "Direito das Sucessões"],
  ["ambiental", "Direito Ambiental"],
  ["criminal", "Direito Penal"],
  ["previdenciario", "Direito Previdenciário"],
  ["empresarial", "Direito Empresarial"],
  ["tributario", "Direito Tributário"],
  ["administrativo", "Direito Administrativo"],
  ["licitacoes", "Licitações e Contratos"],
  ["bancario", "Direito Bancário"],
  ["imobiliario", "Direito Imobiliário"],
  ["constitucional", "Direito Constitucional"],
  ["digital_lgpd", "Direito Digital e LGPD"],
  ["transito", "Direito de Trânsito"],
  ["saude", "Direito da Saúde"],
  ["medico", "Direito Médico"],
  ["agrario", "Direito Agrário"],
  ["agronegocio", "Direito do Agronegócio"],
  ["eleitoral", "Direito Eleitoral"],
  ["internacional", "Direito Internacional"],
  ["contratual", "Direito Contratual"],
  ["societario", "Direito Societário"],
].map(([slug, nome]) => ({ slug, nome }));

const CONVERSION_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
]);

// Estados em que o backend (raio_x.py::converter) aceita transformar o Raio-X
// em caso. O fluxo padrão termina em "aguardando_conferencia"; exigir só
// "analise_concluida" (estado que o back nunca persiste) deixava o botão
// eternamente inerte — o usuário clicava e nada acontecia.
const STATUS_CONVERTIVEIS = new Set([
  "aguardando_conferencia",
  "em_analise",
  "analise_concluida",
]);

const humanize = (value: string) =>
  value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

const stringify = (value: unknown): string => {
  if (value == null) return "—";
  if (typeof value === "string" || typeof value === "number")
    return String(value);
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "object") {
    const record = value as Record<string, unknown>;
    const preferred =
      record.valor ??
      record.texto ??
      record.descricao ??
      record.titulo ??
      record.nome ??
      record.evento ??
      record.fato ??
      record.comando ??
      record.mensagem;
    if (preferred != null) {
      const complements = [record.data, record.estado, record.tipo]
        .filter(Boolean)
        .map(String)
        .join(" · ");
      return complements
        ? `${stringify(preferred)} · ${complements}`
        : stringify(preferred);
    }
  }
  return JSON.stringify(value);
};

function ReportList({ title, items }: { title: string; items?: unknown[] }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <h3 className="text-sm font-semibold text-slate-950 dark:text-white">
        {title}
      </h3>
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

function RiskBadge({
  value,
  urgent,
}: {
  value?: string | null;
  urgent?: boolean;
}) {
  const normalized = String(value || "não classificado");
  const tone =
    normalized === "critico"
      ? "red"
      : normalized === "elevado"
        ? "amber"
        : normalized === "baixo"
          ? "green"
          : "blue";
  return (
    <div className="flex flex-wrap gap-2">
      <Badge tone={tone}>{humanize(normalized)}</Badge>
      {urgent && <Badge tone="red">Prazo potencialmente urgente</Badge>}
    </div>
  );
}

export default function RaioXProcesso() {
  const [searchParams] = useSearchParams();
  const contextualCaseId = searchParams.get("case_id");
  const user = useAuth((state) => state.user);
  const canConvert = CONVERSION_ROLES.has(String(user?.role || ""));

  const [areas, setAreas] = useState<Area[]>(FALLBACK_AREAS);
  const [items, setItems] = useState<Analise[]>([]);
  const [stats, setStats] = useState<Stats>({
    total: 0,
    pendentes_conferencia: 0,
    convertidos: 0,
    urgentes: 0,
    risco_elevado_ou_critico: 0,
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
  const [search, setSearch] = useState("");
  const [riskFilter, setRiskFilter] = useState("");
  const [urgentFilter, setUrgentFilter] = useState(false);

  const [review, setReview] = useState<ReviewFields>({
    numero_processo: "",
    area: "civil",
    subarea: "",
    rito: "",
    fase: "",
    tribunal: "",
    orgao: "",
    unidade: "",
    posicao_cliente: "",
    sintese: "",
  });

  const [actions, setActions] = useState<ContextualAction[]>([]);
  const [actionResult, setActionResult] = useState("");
  const [runningAction, setRunningAction] = useState<string | null>(null);

  // Análise "advogado sênior" (IA agêntica) — operação cara, SOMENTE leitura.
  const [advResult, setAdvResult] = useState<AnaliseAdvogadoResult | null>(
    null,
  );
  const [advLoading, setAdvLoading] = useState(false);
  // Erro exibido DENTRO do card da análise (o banner global fica fora da
  // viewport quando o botão está no fim da página).
  const [advError, setAdvError] = useState<string | null>(null);

  const [conversion, setConversion] = useState<ConversionPreview | null>(null);
  const [showConversion, setShowConversion] = useState(false);
  const [existingClientId, setExistingClientId] = useState("");
  const [newClientName, setNewClientName] = useState("");
  const [newClientCpf, setNewClientCpf] = useState("");
  const [caseTitle, setCaseTitle] = useState("");
  const [transferDeadlines, setTransferDeadlines] = useState(false);
  const [transferTasks, setTransferTasks] = useState(false);
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([]);
  const [confirmDuplicate, setConfirmDuplicate] = useState(false);
  const [confirmConflict, setConfirmConflict] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  useEffect(() => {
    api
      .get("/areas")
      .then(({ data }) => {
        const list = Array.isArray(data) ? data : data?.areas;
        if (Array.isArray(list) && list.length) {
          setAreas(list.filter((item: Area) => item.ativo !== false));
        }
      })
      .catch(() => undefined);
  }, []);

  const loadList = useCallback(async () => {
    const params: Record<string, unknown> = { page_size: 100 };
    if (search.trim()) params.search = search.trim();
    if (riskFilter) params.risco = riskFilter;
    if (urgentFilter) params.urgente = true;
    const [{ data: list }, { data: metric }] = await Promise.all([
      api.get("/raio-x/", { params }),
      api.get("/raio-x/stats"),
    ]);
    setItems(list.data || []);
    setStats(metric);
  }, [search, riskFilter, urgentFilter]);

  useEffect(() => {
    let active = true;
    void (async () => {
      setLoading(true);
      setError(null);
      try {
        if (contextualCaseId) {
          const { data } = await api.get(
            `/raio-x/contextual/${contextualCaseId}`,
          );
          if (active) setContextual(data);
        } else {
          await loadList();
        }
      } catch (err: any) {
        if (active)
          setError(
            err?.response?.data?.detail ||
              "Não foi possível carregar o Raio-X.",
          );
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [contextualCaseId, loadList]);

  useEffect(() => {
    setAdvResult(null);
    const identification = selected?.relatorio?.identificacao || {};
    setReview({
      numero_processo: String(
        selected?.numero_processo || identification.numero_processo || "",
      ),
      area: String(selected?.area || identification.area || "civil"),
      subarea: String(selected?.subarea || identification.subarea || ""),
      rito: String(selected?.rito || identification.rito || ""),
      fase: String(
        selected?.fase ||
          identification.fase ||
          identification.etapa_atual ||
          "",
      ),
      tribunal: String(selected?.tribunal || identification.tribunal || ""),
      orgao: String(selected?.orgao || identification.orgao || ""),
      unidade: String(selected?.unidade || identification.unidade || ""),
      posicao_cliente: String(
        selected?.posicao_cliente || identification.posicao_cliente || "",
      ),
      sintese: String(
        selected?.revisao_humana?.sintese_revisada ||
          selected?.relatorio?.sintese_executiva_revisada ||
          selected?.relatorio?.sintese_executiva ||
          "",
      ),
    });
    if (selected) {
      setCaseTitle(selected.titulo);
      setNewClientName(selected.potencial_cliente || "");
    }
  }, [selected]);

  const report = contextual || selected?.relatorio;
  const identification = report?.identificacao || {};
  const sourceCount = useMemo(
    () => selected?.documentos?.length || 0,
    [selected],
  );

  useEffect(() => {
    if (!report) {
      setActions([]);
      return;
    }
    const documentType = selected?.documentos?.[0]?.tipo_documento || undefined;
    api
      .get("/ai/skills/contextual", {
        params: {
          surface: "processos",
          case_id: contextualCaseId || undefined,
          area:
            String(identification.area || selected?.area || "") || undefined,
          phase:
            String(identification.etapa_atual || selected?.fase || "") ||
            undefined,
          document_type: documentType,
          limit: 6,
        },
      })
      .then(({ data }) => setActions(data.actions || []))
      .catch(() => setActions([]));
  }, [
    report,
    selected,
    contextualCaseId,
    identification.area,
    identification.etapa_atual,
  ]);

  const detail = async (id: string) => {
    setBusy(true);
    setError(null);
    setActionResult("");
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
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      );
      setSelected(data.analise);
      setFiles([]);
      const notes = [
        data.duplicados?.length
          ? `${data.duplicados.length} duplicado(s) ignorado(s)`
          : "",
        data.erros?.length ? `${data.erros.length} arquivo(s) com erro` : "",
      ].filter(Boolean);
      setMessage(
        `Análise concluída.${notes.length ? ` ${notes.join("; ")}.` : ""}`,
      );
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
    try {
      const response = await api.get(
        `/raio-x/${selected.id}/documentos/${documento.id}/download`,
        {
          responseType: "blob",
        },
      );
      const href = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = documento.nome_original;
      anchor.click();
      URL.revokeObjectURL(href);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Não foi possível baixar o documento.",
      );
    } finally {
      setBusy(false);
    }
  };

  const exportReport = async (format: "pdf" | "docx") => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const response = await api.get(`/raio-x/${selected.id}/exportar`, {
        params: { formato: format },
        responseType: "blob",
      });
      const href = URL.createObjectURL(response.data);
      const anchor = document.createElement("a");
      anchor.href = href;
      anchor.download = `raio-x-${selected.id}.${format}`;
      anchor.click();
      URL.revokeObjectURL(href);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail ||
          `Falha ao exportar ${format.toUpperCase()}.`,
      );
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
        numero_processo: review.numero_processo || null,
        area: review.area,
        subarea: review.subarea || null,
        rito: review.rito || null,
        fase: review.fase || null,
        tribunal: review.tribunal || null,
        orgao: review.orgao || null,
        unidade: review.unidade || null,
        posicao_cliente: review.posicao_cliente || null,
        revisao_humana: {
          ...selected.revisao_humana,
          identificacao: {
            numero_processo: review.numero_processo || null,
            area: review.area,
            subarea: review.subarea || null,
            rito: review.rito || null,
            fase: review.fase || null,
            tribunal: review.tribunal || null,
            orgao: review.orgao || null,
            unidade: review.unidade || null,
            posicao_cliente: review.posicao_cliente || null,
          },
          sintese_revisada: review.sintese,
          conferido_em: new Date().toISOString(),
        },
      });
      setSelected(data);
      setMessage(
        "Conferência humana salva. O relatório está pronto para decisão.",
      );
      await loadList();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao salvar conferência.");
    } finally {
      setBusy(false);
    }
  };

  const reconsolidate = async (reprocess: boolean) => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post(
        `/raio-x/${selected.id}/reanalisar`,
        null,
        {
          params: { reprocessar: reprocess },
        },
      );
      setSelected(data.analise || data);
      setMessage(
        reprocess
          ? `Documentos reprocessados.${data.erros?.length ? ` ${data.erros.length} erro(s).` : ""}`
          : "Relatório reconsolidado com os dados existentes.",
      );
      await loadList();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Falha ao reprocessar a análise.",
      );
    } finally {
      setBusy(false);
    }
  };

  const executeAction = async (action: ContextualAction) => {
    if (!report) return;
    setRunningAction(action.name);
    setError(null);
    try {
      const query = [
        "Execute a ação sobre o relatório preliminar abaixo. Separe fatos, inferências, ausências, riscos, fontes e recomendação. Não invente dados.",
        JSON.stringify(report).slice(0, 10500),
      ].join("\n\n");
      const { data } = await api.post("/ai/skills/execute", {
        skill_name: action.name,
        query,
        case_id: contextualCaseId || null,
        usar_rag: Boolean(contextualCaseId),
        surface: "processos",
        area: String(identification.area || selected?.area || "") || null,
        phase:
          String(identification.etapa_atual || selected?.fase || "") || null,
      });
      setActionResult(data.conteudo || "Resultado sem conteúdo.");
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "A ação com IA não pôde ser executada.",
      );
    } finally {
      setRunningAction(null);
    }
  };

  // Análise do advogado (IA): contextual (caso) ou por documentos (analise_id).
  // Roles idênticos a canConvert (backend _permitido_ia_advogado exclui estagiário).
  const runAdvogadoIA = async () => {
    if (!report || advLoading) return;
    setAdvLoading(true);
    setAdvResult(null);
    setAdvError(null);
    try {
      const data = contextualCaseId
        ? await analiseAdvogadoContextual(contextualCaseId)
        : selected
          ? await analiseAdvogadoPorAnalise(selected.id)
          : null;
      if (data) setAdvResult(data);
    } catch (err: any) {
      // 409 (análise preliminar sem caso vinculado), 403 (perfil), 429 etc. —
      // exibido junto do botão, dentro do card da análise.
      setAdvError(
        err?.response?.data?.detail ||
          "Não foi possível gerar a análise do advogado (IA).",
      );
    } finally {
      setAdvLoading(false);
    }
  };

  const saveActionResult = async () => {
    if (!selected || !actionResult.trim()) return;
    const previous = Array.isArray(selected.revisao_humana?.analises_ia)
      ? (selected.revisao_humana.analises_ia as unknown[])
      : [];
    try {
      const { data } = await api.patch<Analise>(`/raio-x/${selected.id}`, {
        revisao_humana: {
          ...selected.revisao_humana,
          analises_ia: [
            ...previous,
            {
              conteudo: actionResult,
              salvo_em: new Date().toISOString(),
              revisao_obrigatoria: true,
            },
          ],
        },
      });
      setSelected(data);
      setMessage("Resultado salvo na revisão interna do Raio-X.");
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Falha ao salvar resultado da IA.",
      );
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

  const requiresDuplicateConfirmation = Boolean(
    conversion?.casos_possivelmente_duplicados.length,
  );
  const requiresConflictConfirmation = Boolean(
    conversion?.alertas_conflito.length,
  );
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
          area: review.area,
          numero_processo: review.numero_processo || null,
          tribunal: review.tribunal || null,
          descricao_fatos:
            review.sintese || selected.relatorio?.sintese_executiva,
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
      setMessage(
        "Caso oficial criado com trilha de auditoria. Redirecionando…",
      );
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
    try {
      await api.post(`/raio-x/${selected.id}/${mode}`);
      setSelected(null);
      setMessage(
        mode === "arquivar" ? "Análise arquivada." : "Análise descartada.",
      );
      await loadList();
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "A operação não pôde ser concluída.",
      );
    } finally {
      setBusy(false);
    }
  };

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
        eyebrow={
          contextualCaseId
            ? "Inteligência contextual"
            : "Análise preliminar isolada"
        }
        title={
          contextualCaseId
            ? `Raio-X · ${String(identification.titulo || "Caso")}`
            : "Raio-X do Processo"
        }
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
            <div className="flex flex-wrap gap-2">
              {/* Rota alternativa de entrada: quem prefere ANALISAR
                  CONVERSANDO (e não só ler documentos) vai para a Sala. */}
              <Link to="/sala-juridica">
                <Button variant="secondary">Analisar conversando</Button>
              </Link>
              <Button onClick={() => setCreating(true)}>
                <Plus className="h-4 w-4" /> Nova análise
              </Button>
            </div>
          )
        }
      />

      <div className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-400/20 dark:bg-amber-400/10 dark:text-amber-100">
        <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0" />
        <div>
          <strong>Ambiente preliminar:</strong> nenhum prazo, rito, conflito ou
          conclusão altera o caso oficial antes da revisão humana.
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
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard
              label="Análises"
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
              label="Urgentes"
              value={stats.urgentes || 0}
              icon={<ShieldCheck className="h-5 w-5" />}
              tone="amber"
            />
            <StatCard
              label="Risco elevado/crítico"
              value={stats.risco_elevado_ou_critico || 0}
              icon={<Filter className="h-5 w-5" />}
              tone="amber"
            />
            <StatCard
              label="Convertidas"
              value={stats.convertidos}
              icon={<FolderInput className="h-5 w-5" />}
              tone="green"
            />
          </div>

          <SectionCard
            title="Análises preliminares"
            subtitle="Registros separados da carteira oficial do escritório."
          >
            <div className="mb-4 grid gap-3 md:grid-cols-[1fr_180px_auto]">
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && void loadList()}
                placeholder="Buscar título, cliente ou número"
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/[0.04]"
              />
              <select
                value={riskFilter}
                onChange={(event) => setRiskFilter(event.target.value)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-slate-900"
              >
                <option value="">Todos os riscos</option>
                <option value="baixo">Baixo</option>
                <option value="moderado">Moderado</option>
                <option value="elevado">Elevado</option>
                <option value="critico">Crítico</option>
              </select>
              <div className="flex gap-2">
                <Button
                  variant={urgentFilter ? "primary" : "secondary"}
                  onClick={() => setUrgentFilter((value) => !value)}
                >
                  Somente urgentes
                </Button>
                <Button variant="secondary" onClick={() => void loadList()}>
                  Filtrar
                </Button>
              </div>
            </div>
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
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                        {item.potencial_cliente && (
                          <span>{item.potencial_cliente}</span>
                        )}
                        {item.numero_processo && (
                          <span>• {item.numero_processo}</span>
                        )}
                        {item.area && <Badge tone="blue">{item.area}</Badge>}
                        <RiskBadge
                          value={item.risco_nivel}
                          urgent={item.prazo_urgente}
                        />
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
          <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-float dark:border-white/10 dark:bg-slate-900">
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
                <Button
                  onClick={() => void create()}
                  disabled={busy || newTitle.trim().length < 3}
                >
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
                    <CheckCircle2 className="h-5 w-5" /> Convertido e preservado
                    para auditoria.
                  </span>
                  <Link
                    to={`/casos/${selected.convertido_case_id}`}
                    className="font-semibold"
                  >
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
                        : "Selecione PDF, DOCX, TXT ou imagens"}
                    </span>
                    <input
                      type="file"
                      multiple
                      className="hidden"
                      accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff,.webp"
                      onChange={(event) =>
                        setFiles(Array.from(event.target.files || []))
                      }
                    />
                  </label>
                  <Button
                    onClick={() => void upload()}
                    disabled={!files.length || busy}
                  >
                    {busy ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Sparkles className="h-4 w-4" />
                    )}{" "}
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
                      className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1.5 text-xs text-slate-700 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200"
                    >
                      <FileText className="h-3.5 w-3.5" /> {doc.nome_original}
                    </button>
                  ))}
                </div>
              )}
            </SectionCard>
          )}

          <AIFactualityLegend />

          <div className="grid gap-5 xl:grid-cols-[1.4fr_0.6fr]">
            <div className="space-y-5">
              <SectionCard
                title="Síntese executiva"
                subtitle={
                  report.aviso || "Conteúdo sujeito à conferência humana."
                }
              >
                <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-200">
                  {String(
                    report.sintese_executiva_revisada ||
                      report.sintese_executiva ||
                      "Síntese não disponível.",
                  )}
                </p>
              </SectionCard>

              <SectionCard title="Risco e jornada processual">
                <RiskBadge
                  value={String(
                    report.risco_nivel || selected?.risco_nivel || "",
                  )}
                  urgent={Boolean(
                    report.prazo_urgente || selected?.prazo_urgente,
                  )}
                />
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <ReportList
                    title="Avaliação de risco"
                    items={
                      report.avaliacao_risco
                        ? [report.avaliacao_risco]
                        : report.riscos
                    }
                  />
                  <ReportList
                    title="Rito e próximas etapas"
                    items={report.rito_jornada ? [report.rito_jornada] : []}
                  />
                </div>
              </SectionCard>

              <div className="grid gap-4 md:grid-cols-2">
                <ReportList title="Partes" items={report.partes} />
                <ReportList title="Pedidos" items={report.pedidos} />
                <ReportList title="Provas" items={report.provas} />
                <ReportList
                  title="Prazos potenciais"
                  items={report.prazos_potenciais || (report as any).prazos}
                />
                <ReportList
                  title="Decisões e determinações"
                  items={report.decisoes}
                />
                <ReportList title="Contradições" items={report.contradicoes} />
                <ReportList
                  title="Pontos fortes"
                  items={report.pontos_fortes}
                />
                <ReportList
                  title="Pontos frágeis"
                  items={report.pontos_fracos}
                />
                <ReportList
                  title="Próximos passos"
                  items={report.proximos_passos}
                />
                <ReportList
                  title="Documentos pendentes"
                  items={report.documentos_pendentes}
                />
              </div>

              <SectionCard title="Cronologia e matriz fato × prova">
                <div className="grid gap-4 md:grid-cols-2">
                  <ReportList title="Cronologia" items={report.cronologia} />
                  <ReportList
                    title="Fato × prova"
                    items={report.fatos_provas}
                  />
                </div>
              </SectionCard>

              <SectionCard
                title="Ações com IA"
                subtitle="Somente ações compatíveis com a área, fase e documento reconhecido."
              >
                {!actions.length ? (
                  <p className="text-sm text-slate-500">
                    Nenhuma ação contextual disponível com os dados atuais.
                  </p>
                ) : (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {actions.map((action) => (
                      <button
                        key={action.id}
                        onClick={() => void executeAction(action)}
                        disabled={Boolean(runningAction)}
                        className="rounded-xl border border-slate-200 p-3 text-left hover:border-primary-400 disabled:opacity-50 dark:border-white/10"
                      >
                        <div className="flex items-center gap-2 font-medium">
                          <Sparkles className="h-4 w-4 text-primary-600" />{" "}
                          {action.display_name}
                        </div>
                        <p className="mt-1 text-xs text-slate-500">
                          {action.reason}
                        </p>
                        {runningAction === action.name && (
                          <Loader2 className="mt-2 h-4 w-4 animate-spin" />
                        )}
                      </button>
                    ))}
                  </div>
                )}
                {actionResult && (
                  <div className="mt-4 rounded-xl border border-primary-200 bg-primary-50/40 p-4 dark:border-primary-400/20 dark:bg-primary-400/10">
                    <p className="whitespace-pre-wrap text-sm leading-7">
                      {actionResult}
                    </p>
                    {!contextualCaseId && selected && (
                      <Button
                        className="mt-3"
                        variant="secondary"
                        onClick={() => void saveActionResult()}
                      >
                        Salvar na revisão interna
                      </Button>
                    )}
                  </div>
                )}
              </SectionCard>

              {canConvert && (
                <SectionCard
                  title="Análise do advogado sênior (IA)"
                  subtitle="Parecer estratégico FIRAC movido pelo agente (dossiê + precedentes). Somente leitura; nada é alterado no caso. Operação cara — rascunho sujeito a revisão humana (OAB)."
                  actions={
                    <Button
                      variant="ai"
                      onClick={() => void runAdvogadoIA()}
                      disabled={advLoading}
                    >
                      {advLoading ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Scale className="h-4 w-4" />
                      )}
                      Análise do advogado (IA)
                    </Button>
                  }
                >
                  {!advResult && !advLoading && !advError && (
                    <p className="text-sm text-slate-500">
                      Gere um parecer do caso como faria um advogado sênior
                      antes de definir a estratégia.
                    </p>
                  )}
                  {advLoading && (
                    <div className="flex items-center gap-2 text-sm text-slate-500">
                      <Loader2 className="h-4 w-4 animate-spin" /> O agente está
                      analisando o caso… pode levar alguns instantes.
                    </div>
                  )}
                  {advError && !advLoading && (
                    <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                      {advError}
                    </div>
                  )}
                  {advResult && advResult.status === "indisponivel" && (
                    <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                      <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
                      Recurso de IA do agente desativado no servidor
                      (AI_AGENT_ENABLED). Solicite a ativação à administração.
                    </div>
                  )}
                  {advResult &&
                    advResult.status !== "ok" &&
                    advResult.status !== "indisponivel" && (
                      <div className="flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                        Não foi possível concluir a análise
                        {advResult.detalhe ? ` (${advResult.detalhe})` : ""}.
                      </div>
                    )}
                  {advResult &&
                    advResult.status === "ok" &&
                    advResult.analise && (
                      <div className="space-y-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge tone="amber">RASCUNHO</Badge>
                          {advResult.revisao_obrigatoria && (
                            <Badge tone="orange">
                              Revisão humana obrigatória
                            </Badge>
                          )}
                          {typeof advResult.custo_estimado_brl === "number" &&
                            advResult.custo_estimado_brl > 0 && (
                              <Badge tone="slate">
                                R$ {advResult.custo_estimado_brl.toFixed(4)}
                              </Badge>
                            )}
                          {advResult.critica_adversarial?.disponivel &&
                            typeof advResult.critica_adversarial
                              .nota_robustez === "number" && (
                              <Badge tone="blue">
                                Robustez (2ª IA):{" "}
                                {advResult.critica_adversarial.nota_robustez}
                              </Badge>
                            )}
                        </div>
                        <Markdown
                          source={advResult.analise}
                          className="max-h-[32rem] overflow-auto rounded-xl bg-slate-50 p-4 text-sm leading-7 text-slate-800 dark:bg-white/[0.04] dark:text-slate-200"
                        />
                        {!!advResult.alertas?.length && (
                          <ul className="space-y-1 text-xs text-warn-700">
                            {advResult.alertas.map((a, index) => (
                              <li
                                key={index}
                                className="flex items-start gap-1.5"
                              >
                                <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />{" "}
                                {a}
                              </li>
                            ))}
                          </ul>
                        )}
                        {advResult.critica_adversarial?.disponivel &&
                          advResult.critica_adversarial.relatorio && (
                            <details className="rounded-xl border border-slate-200 p-3 dark:border-white/10">
                              <summary className="cursor-pointer text-sm font-medium text-slate-700 dark:text-slate-200">
                                Crítica adversarial (2ª IA)
                              </summary>
                              <p className="mt-2 whitespace-pre-wrap text-xs leading-6 text-slate-600 dark:text-slate-300">
                                {advResult.critica_adversarial.relatorio}
                              </p>
                            </details>
                          )}
                      </div>
                    )}
                </SectionCard>
              )}
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
                  subtitle="Corrija área, rito, fase e dados essenciais antes da conversão."
                >
                  <div className="space-y-3">
                    <label className="block text-sm font-medium">
                      Número do processo
                      <input
                        value={review.numero_processo}
                        onChange={(event) =>
                          setReview((value) => ({
                            ...value,
                            numero_processo: event.target.value,
                          }))
                        }
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
                      />
                    </label>
                    <label className="block text-sm font-medium">
                      Área
                      <select
                        value={review.area}
                        onChange={(event) =>
                          setReview((value) => ({
                            ...value,
                            area: event.target.value,
                          }))
                        }
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 dark:border-white/10 dark:bg-slate-900"
                      >
                        {areas.map((area) => (
                          <option key={area.slug} value={area.slug}>
                            {area.nome}
                          </option>
                        ))}
                      </select>
                    </label>
                    {(
                      [
                        ["subarea", "Subárea"],
                        ["rito", "Rito"],
                        ["fase", "Fase ou etapa"],
                        ["tribunal", "Tribunal"],
                        ["orgao", "Órgão"],
                        ["unidade", "Unidade"],
                        ["posicao_cliente", "Posição do potencial cliente"],
                      ] as const
                    ).map(([field, label]) => (
                      <label key={field} className="block text-sm font-medium">
                        {label}
                        <input
                          value={review[field]}
                          onChange={(event) =>
                            setReview((value) => ({
                              ...value,
                              [field]: event.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 dark:border-white/10 dark:bg-white/[0.04]"
                        />
                      </label>
                    ))}
                    <label className="block text-sm font-medium">
                      Síntese revisada
                      <textarea
                        rows={8}
                        value={review.sintese}
                        onChange={(event) =>
                          setReview((value) => ({
                            ...value,
                            sintese: event.target.value,
                          }))
                        }
                        className="mt-1 w-full rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/[0.04]"
                      />
                    </label>
                    <Button
                      className="w-full"
                      onClick={() => void saveReview()}
                      disabled={busy}
                    >
                      <CheckCircle2 className="h-4 w-4" /> Salvar conferência
                    </Button>
                  </div>
                </SectionCard>
              )}

              <SectionCard title="Ações">
                <div className="space-y-2">
                  {!contextual && selected && (
                    <>
                      <div className="grid grid-cols-2 gap-2">
                        <Button
                          variant="secondary"
                          onClick={() => void exportReport("pdf")}
                        >
                          <Download className="h-4 w-4" /> PDF
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={() => void exportReport("docx")}
                        >
                          <Download className="h-4 w-4" /> Word
                        </Button>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <Button
                          variant="ghost"
                          onClick={() => void reconsolidate(false)}
                        >
                          <RefreshCw className="h-4 w-4" /> Reconsolidar
                        </Button>
                        <Button
                          variant="ghost"
                          onClick={() => void reconsolidate(true)}
                        >
                          <RefreshCw className="h-4 w-4" /> Reprocessar
                        </Button>
                      </div>
                    </>
                  )}
                  {!contextual &&
                    selected &&
                    !selected.convertido_case_id &&
                    canConvert && (
                      <>
                        <Button
                          className="w-full"
                          onClick={() => void openConversion()}
                          disabled={!STATUS_CONVERTIVEIS.has(selected.status)}
                        >
                          <FolderInput className="h-4 w-4" /> Transformar em
                          caso
                        </Button>
                        {!STATUS_CONVERTIVEIS.has(selected.status) && (
                          <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-700 dark:bg-amber-500/[0.08] dark:text-amber-300">
                            A conversão libera quando a análise está conferível
                            (status atual: {humanize(selected.status)}). Conclua
                            o processamento e a conferência do Raio-X antes de
                            transformar em caso.
                          </p>
                        )}
                      </>
                    )}
                  {!contextual &&
                    selected &&
                    !selected.convertido_case_id &&
                    !canConvert && (
                      <p className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-white/[0.04] dark:text-slate-300">
                        Seu perfil pode revisar o Raio-X, mas a conversão deve
                        ser feita por advogado autorizado ou pela gestão.
                      </p>
                    )}
                  {!contextual && selected && !selected.convertido_case_id && (
                    <div className="grid grid-cols-2 gap-2">
                      <Button
                        variant="ghost"
                        onClick={() => void archive("arquivar")}
                      >
                        <Archive className="h-4 w-4" /> Arquivar
                      </Button>
                      <Button
                        variant="danger"
                        onClick={() => void archive("descartar")}
                      >
                        <Trash2 className="h-4 w-4" /> Descartar
                      </Button>
                    </div>
                  )}
                </div>
              </SectionCard>
            </div>
          </div>
        </>
      )}

      {showConversion && selected && conversion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl border border-slate-200 bg-white p-6 shadow-float dark:border-white/10 dark:bg-slate-900">
            <div className="flex items-start justify-between">
              <div>
                <h2 className="text-xl font-semibold">
                  Transformar em caso do escritório
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Revise duplicidades, conflito, cliente, documentos e itens a
                  transferir.
                </p>
              </div>
              <button
                onClick={() => setShowConversion(false)}
                aria-label="Fechar"
              >
                <X />
              </button>
            </div>

            {conversion.bloqueia && (
              <div className="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                Existem alertas de duplicidade ou conflito. A confirmação é
                obrigatória e ficará registrada.
              </div>
            )}
            <div className="mt-4">
              <RiskBadge
                value={conversion.risco_nivel}
                urgent={conversion.prazo_urgente}
              />
            </div>

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
                <h3 className="text-sm font-semibold">
                  Clientes semelhantes encontrados
                </h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  {conversion.clientes_possivelmente_duplicados.map(
                    (client, index) => (
                      <button
                        type="button"
                        key={String(client.id || index)}
                        onClick={() =>
                          setExistingClientId(String(client.id || ""))
                        }
                        className="rounded-lg border border-slate-200 px-3 py-2 text-left text-xs hover:border-primary-400 dark:border-white/10"
                      >
                        <strong>{String(client.nome || "Cliente")}</strong>
                        <span className="ml-2 text-slate-500">
                          {String(client.id || "")}
                        </span>
                      </button>
                    ),
                  )}
                </div>
              </div>
            )}

            {!!conversion.alertas_conflito.length && (
              <ReportList
                title="Alertas de conflito a revisar"
                items={conversion.alertas_conflito}
              />
            )}

            <div className="mt-5 rounded-xl bg-slate-50 p-4 text-sm dark:bg-white/[0.04]">
              <h3 className="font-semibold">Documentos a incorporar ao GED</h3>
              <div className="mt-3 space-y-2">
                {conversion.documentos_disponiveis.map((doc) => (
                  <label key={doc.id} className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedDocumentIds.includes(doc.id)}
                      onChange={() =>
                        setSelectedDocumentIds((current) =>
                          current.includes(doc.id)
                            ? current.filter((item) => item !== doc.id)
                            : [...current, doc.id],
                        )
                      }
                    />
                    <span>{doc.nome}</span>
                    {doc.tipo && <Badge tone="blue">{doc.tipo}</Badge>}
                  </label>
                ))}
              </div>
            </div>

            <div className="mt-4 space-y-3 rounded-xl bg-slate-50 p-4 text-sm dark:bg-white/[0.04]">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={transferDeadlines}
                  onChange={(event) =>
                    setTransferDeadlines(event.target.checked)
                  }
                />{" "}
                Transferir prazos como rascunho não confirmado
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={transferTasks}
                  onChange={(event) => setTransferTasks(event.target.checked)}
                />{" "}
                Transferir próximos passos como tarefas
              </label>
            </div>

            {requiresDuplicateConfirmation && (
              <label className="mt-4 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <input
                  className="mt-1"
                  type="checkbox"
                  checked={confirmDuplicate}
                  onChange={(event) =>
                    setConfirmDuplicate(event.target.checked)
                  }
                />{" "}
                Revisei a possível duplicidade e autorizo a continuidade.
              </label>
            )}
            {requiresConflictConfirmation && (
              <label className="mt-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-900">
                <input
                  className="mt-1"
                  type="checkbox"
                  checked={confirmConflict}
                  onChange={(event) => setConfirmConflict(event.target.checked)}
                />{" "}
                Realizei a análise humana de conflito e autorizo a continuidade.
              </label>
            )}

            <label className="mt-4 block text-sm font-medium">
              Confirmação textual
              <input
                value={confirmText}
                onChange={(event) => setConfirmText(event.target.value)}
                className="mt-1 w-full rounded-xl border px-3 py-2 dark:bg-white/[0.04]"
                placeholder="TRANSFORMAR EM CASO DO ESCRITÓRIO"
              />
            </label>

            <div className="mt-6 flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => setShowConversion(false)}
              >
                Cancelar
              </Button>
              <Button
                onClick={() => void convert()}
                disabled={!conversionConfirmed || busy}
              >
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} Confirmar
                conversão
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
