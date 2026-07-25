import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Archive,
  Bot,
  CheckCircle2,
  FileText,
  FolderPlus,
  Gavel,
  Loader2,
  MessageSquarePlus,
  Paperclip,
  Plus,
  Scale,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
  UploadCloud,
  X,
} from "lucide-react";
import api from "../lib/api";
import { classificarDocumento } from "../utils/documento";
import Markdown from "../components/Markdown";
import { Badge, Button, EmptyState, PageHeader } from "../components/UI";

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

type Documento = {
  id: string;
  nome_original: string;
  tipo_documento?: string | null;
};

type Relatorio = {
  sintese_executiva?: string;
  fatos_provas?: unknown[];
  contradicoes?: unknown[];
  riscos?: unknown[];
  documentos_pendentes?: unknown[];
  teses?: unknown[];
  partes?: unknown[];
  provas?: unknown[];
  proximos_passos?: unknown[];
  [key: string]: unknown;
};

type Analise = {
  id: string;
  titulo: string;
  potencial_cliente?: string | null;
  area?: string | null;
  status: string;
  risco_nivel?: string | null;
  prazo_urgente?: boolean;
  relatorio?: Relatorio;
  revisao_humana?: Record<string, unknown>;
  convertido_case_id?: string | null;
  documentos?: Documento[];
  updated_at?: string;
};

type ClientCandidate = {
  id: string | null;
  nome: string;
  cpf?: boolean;
  cnpj?: boolean;
  protegido?: boolean;
};

type CaseCandidate = {
  id: string | null;
  titulo: string;
  numero_processo?: string | null;
  protegido?: boolean;
};

type ConflictAlert = {
  tipo?: string;
  nome?: string;
  mensagem?: string;
  client_id?: string;
  case_id?: string;
  protegido?: boolean;
};

type ConversionPreview = {
  bloqueia?: boolean;
  alertas_conflito?: ConflictAlert[];
  casos_possivelmente_duplicados?: CaseCandidate[];
  clientes_possivelmente_duplicados?: ClientCandidate[];
  documentos_disponiveis?: Array<{ id: string; nome: string }>;
};

type ClientSearchResult = {
  id: string;
  nome?: string;
  nome_exibicao?: string;
  razao_social?: string;
  tipo?: string;
};

const AREAS = [
  "civil",
  "trabalhista",
  "consumidor",
  "familia",
  "penal",
  "administrativo",
  "tributario",
  "empresarial",
  "ambiental",
  "bancario",
  "imobiliario",
  "previdenciario",
  "digital_lgpd",
  "transito",
];

const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2)}`;

const stringify = (value: unknown): string => {
  if (value == null) return "—";
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (typeof value === "boolean") return value ? "Sim" : "Não";
  if (typeof value === "object") {
    const item = value as Record<string, unknown>;
    const preferred =
      item.fato ??
      item.descricao ??
      item.texto ??
      item.titulo ??
      item.nome ??
      item.valor;
    if (preferred != null) return stringify(preferred);
  }
  return JSON.stringify(value);
};

const getMessages = (analise: Analise | null): ChatMessage[] => {
  const raw = analise?.revisao_humana?.conversa;
  return Array.isArray(raw) ? (raw as ChatMessage[]) : [];
};

const normalizeClient = (item: ClientSearchResult): ClientCandidate => ({
  id: item.id,
  nome:
    item.nome_exibicao || item.nome || item.razao_social || "Cliente sem nome",
  protegido: false,
});

const extractNames = (analise: Analise): string[] => {
  const names = new Set<string>();
  const add = (value: unknown) => {
    if (typeof value === "string") {
      const clean = value.trim();
      if (clean.length >= 4 && clean.length <= 255) names.add(clean);
      return;
    }
    if (Array.isArray(value)) {
      value.forEach(add);
      return;
    }
    if (value && typeof value === "object") {
      const object = value as Record<string, unknown>;
      [
        object.nome,
        object.razao_social,
        object.parte,
        object.advogado,
        object.representante,
        object.testemunha,
      ].forEach(add);
    }
  };
  add(analise.potencial_cliente);
  add(analise.relatorio?.partes);
  return Array.from(names).slice(0, 40);
};

export default function SalaAnaliseJuridica() {
  const navigate = useNavigate();
  const fileRef = useRef<HTMLInputElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const [items, setItems] = useState<Analise[]>([]);
  const [selected, setSelected] = useState<Analise | null>(null);
  const [search, setSearch] = useState("");
  const [prompt, setPrompt] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newClient, setNewClient] = useState("");
  const [showConvert, setShowConvert] = useState(false);
  const [preview, setPreview] = useState<ConversionPreview | null>(null);
  const [clientSearch, setClientSearch] = useState("");
  const [clientOptions, setClientOptions] = useState<ClientCandidate[]>([]);
  const [searchingClients, setSearchingClients] = useState(false);
  const [conversion, setConversion] = useState({
    clientMode: "novo",
    clientId: "",
    clientName: "",
    clientDocument: "",
    caseTitle: "",
    area: "civil",
    confirmDuplicate: false,
    confirmConflict: false,
  });

  const messages = useMemo(() => getMessages(selected), [selected]);

  const loadList = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/raio-x/", {
        params: { page_size: 100 },
      });
      const list = Array.isArray(data) ? data : data?.data || [];
      setItems(list);
      setSelected((current) => {
        if (!current) return list[0] || null;
        return (
          list.find((item: Analise) => item.id === current.id) ||
          list[0] ||
          null
        );
      });
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Não foi possível carregar as análises.",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshSelected = useCallback(async (id: string) => {
    const { data } = await api.get(`/raio-x/${id}`);
    setSelected(data);
    setItems((current) =>
      current.map((item) => (item.id === id ? data : item)),
    );
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, busy]);

  useEffect(() => {
    if (!showConvert || conversion.clientMode !== "existente") return;
    const term = clientSearch.trim();
    if (term.length < 2) return;

    const timer = window.setTimeout(async () => {
      setSearchingClients(true);
      try {
        const { data } = await api.get("/clients", {
          params: { search: term, page_size: 20 },
        });
        const raw = Array.isArray(data)
          ? data
          : data?.data || data?.items || [];
        const searched = raw.map(normalizeClient);
        setClientOptions((current) => {
          const merged = [...current, ...searched];
          return merged.filter(
            (item, index) =>
              item.id &&
              merged.findIndex((other) => other.id === item.id) === index,
          );
        });
      } catch (err: any) {
        setError(
          err?.response?.data?.detail ||
            "Não foi possível pesquisar clientes autorizados.",
        );
      } finally {
        setSearchingClients(false);
      }
    }, 350);

    return () => window.clearTimeout(timer);
  }, [clientSearch, conversion.clientMode, showConvert]);

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();
    if (!term) return items;
    return items.filter((item) =>
      [item.titulo, item.potencial_cliente, item.area].some((value) =>
        String(value || "")
          .toLowerCase()
          .includes(term),
      ),
    );
  }, [items, search]);

  const duplicateCases = preview?.casos_possivelmente_duplicados || [];
  const conflictAlerts = preview?.alertas_conflito || [];
  const hasDuplicates = duplicateCases.length > 0;
  const hasConflicts = conflictAlerts.length > 0;

  const createAnalysis = async () => {
    if (newTitle.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post("/raio-x/", {
        titulo: newTitle.trim(),
        potencial_cliente: newClient.trim() || null,
        retention_days: 365,
      });
      const welcome: ChatMessage = {
        id: uid(),
        role: "assistant",
        content:
          "Análise preliminar criada. Relate os fatos e anexe as provas disponíveis. Vou separar fatos comprovados, alegações, contradições, riscos e documentos faltantes.",
        created_at: new Date().toISOString(),
      };
      const updated = await api.patch(`/raio-x/${data.id}`, {
        status: "em_analise",
        revisao_humana: { conversa: [welcome] },
      });
      setItems((current) => [updated.data, ...current]);
      setSelected(updated.data);
      setNewTitle("");
      setNewClient("");
      setShowCreate(false);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Não foi possível criar a análise.",
      );
    } finally {
      setBusy(false);
    }
  };

  const persistMessages = async (next: ChatMessage[]) => {
    if (!selected) return;
    const previousReview = selected.revisao_humana || {};
    const { data } = await api.patch(`/raio-x/${selected.id}`, {
      status: selected.status === "novo" ? "em_analise" : selected.status,
      revisao_humana: { ...previousReview, conversa: next },
    });
    setSelected(data);
    setItems((current) =>
      current.map((item) => (item.id === data.id ? data : item)),
    );
  };

  const sendMessage = async () => {
    if (!selected || !prompt.trim() || busy) return;
    const userMessage: ChatMessage = {
      id: uid(),
      role: "user",
      content: prompt.trim(),
      created_at: new Date().toISOString(),
    };
    const next = [...messages, userMessage];
    setPrompt("");
    setBusy(true);
    setError(null);
    try {
      await persistMessages(next);
      const context = {
        titulo: selected.titulo,
        cliente: selected.potencial_cliente,
        area: selected.area,
        relatorio_documental: selected.relatorio || {},
        documentos: selected.documentos || [],
        conversa: next.slice(-12),
      };
      const { data } = await api.post("/ai/core/analyze", {
        domain: selected.area || "civil",
        mensagem:
          "CONTEXTO DA SALA DE ANÁLISE JURÍDICA:\n" +
          JSON.stringify(context) +
          "\n\nPERGUNTA/INSTRUÇÃO ATUAL DO ADVOGADO:\n" +
          userMessage.content,
        case_id: null,
        params: {
          nomes_proteger: extractNames(selected),
          origem_raio_x: selected.id,
        },
        module_key: "sala-analise-juridica",
        surface: "sala_analise",
        usar_rag: true,
        nivel_inteligencia: "alto",
      });
      const content =
        data?.conteudo ||
        data?.resposta ||
        data?.analise ||
        data?.texto ||
        JSON.stringify(data, null, 2);
      const assistantMessage: ChatMessage = {
        id: uid(),
        role: "assistant",
        content: String(content),
        created_at: new Date().toISOString(),
      };
      await persistMessages([...next, assistantMessage]);
    } catch (err: any) {
      const detail =
        err?.response?.data?.detail ||
        "A análise jurídica não pôde ser concluída.";
      setError(typeof detail === "string" ? detail : JSON.stringify(detail));
    } finally {
      setBusy(false);
    }
  };

  const uploadFiles = async (files: FileList | null) => {
    if (!selected || !files?.length) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      Array.from(files).forEach((file) => form.append("files", file));
      await api.post(`/raio-x/${selected.id}/documentos/analisar`, form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await refreshSelected(selected.id);
      const systemMessage: ChatMessage = {
        id: uid(),
        role: "assistant",
        content: `${files.length} arquivo(s) recebido(s) e processado(s). O painel de fatos, contradições, riscos e pendências foi atualizado.`,
        created_at: new Date().toISOString(),
      };
      await persistMessages([...messages, systemMessage]);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao analisar os arquivos.");
    } finally {
      if (fileRef.current) fileRef.current.value = "";
      setBusy(false);
    }
  };

  const openConversion = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.get(
        `/raio-x/${selected.id}/conversao/preview`,
      );
      setPreview(data);
      const authorizedCandidates = (
        data?.clientes_possivelmente_duplicados || []
      ).filter((item: ClientCandidate) => item.id && !item.protegido);
      setClientOptions(authorizedCandidates);
      setClientSearch(selected.potencial_cliente || "");
      setConversion({
        clientMode: authorizedCandidates.length === 1 ? "existente" : "novo",
        clientId:
          authorizedCandidates.length === 1 ? authorizedCandidates[0].id : "",
        clientName: selected.potencial_cliente || "",
        clientDocument: "",
        caseTitle: selected.titulo,
        area: selected.area || "civil",
        confirmDuplicate: false,
        confirmConflict: false,
      });
      setShowConvert(true);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "Não foi possível preparar a conversão.",
      );
    } finally {
      setBusy(false);
    }
  };

  const convertToCase = async () => {
    if (!selected) return;
    setBusy(true);
    setError(null);
    try {
      const documentIds = (selected.documentos || []).map((doc) => doc.id);
      // P0-473: classificar e validar DV ANTES do envio — nunca truncar.
      const documento = classificarDocumento(conversion.clientDocument);
      if (conversion.clientMode === "novo" && documento.tipo === "erro") {
        setError(documento.mensagem);
        setBusy(false);
        return;
      }
      const payload = {
        cliente:
          conversion.clientMode === "existente"
            ? { modo: "existente", client_id: conversion.clientId }
            : {
                modo: "novo",
                nome: conversion.clientName,
                cpf: documento.tipo === "cpf" ? documento.cpf : null,
                cnpj: documento.tipo === "cnpj" ? documento.cnpj : null,
              },
        caso: {
          titulo: conversion.caseTitle,
          area: conversion.area,
          prioridade: selected.prazo_urgente ? "critica" : "media",
          descricao_fatos:
            selected.relatorio?.sintese_executiva ||
            messages
              .map((message) => `${message.role}: ${message.content}`)
              .join("\n\n"),
          case_type: "judicial",
        },
        documento_ids: documentIds,
        transferir_prazos: false,
        transferir_tarefas: true,
        duplicate_confirmed: !hasDuplicates || conversion.confirmDuplicate,
        conflict_confirmed: !hasConflicts || conversion.confirmConflict,
        confirmacao: "TRANSFORMAR EM CASO DO ESCRITÓRIO",
      };
      const { data } = await api.post(
        `/raio-x/${selected.id}/converter`,
        payload,
      );
      const caseId = data?.case_id || data?.caso?.id || data?.id;
      if (caseId) navigate(`/casos/${caseId}`);
      else await refreshSelected(selected.id);
    } catch (err: any) {
      setError(
        err?.response?.data?.detail || "A conversão não pôde ser concluída.",
      );
    } finally {
      setBusy(false);
    }
  };

  const report: Relatorio = selected?.relatorio ?? {};

  return (
    <div className="flex h-[calc(100vh-5.5rem)] min-h-[720px] flex-col gap-4">
      <PageHeader
        title="Sala de Análise Jurídica"
        subtitle="Converse com a IA, anexe provas, confronte versões e transforme a análise validada em caso."
      />

      {error && (
        <div className="flex items-start justify-between rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            aria-label="Fechar"
          >
            <X size={16} />
          </button>
        </div>
      )}

      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm xl:grid-cols-[280px_minmax(0,1fr)_340px]">
        <aside className="flex min-h-0 flex-col border-b border-slate-200 bg-slate-50/70 xl:border-b-0 xl:border-r">
          <div className="space-y-3 border-b border-slate-200 p-4">
            <Button className="w-full" onClick={() => setShowCreate(true)}>
              <MessageSquarePlus size={16} /> Nova análise
            </Button>
            <div className="relative">
              <Search
                className="absolute left-3 top-2.5 text-slate-400"
                size={16}
              />
              <input
                className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-9 pr-3 text-sm outline-none focus:border-slate-400"
                placeholder="Pesquisar análises"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {loading ? (
              <div className="flex justify-center p-8">
                <Loader2 className="animate-spin" />
              </div>
            ) : !filtered.length ? (
              <EmptyState
                icon={Scale}
                title="Nenhuma análise"
                message="Crie uma sala para iniciar a investigação jurídica."
              />
            ) : (
              <div className="space-y-1">
                {filtered.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    onClick={() => void refreshSelected(item.id)}
                    className={`w-full rounded-xl p-3 text-left transition ${selected?.id === item.id ? "bg-slate-900 text-white" : "hover:bg-white"}`}
                  >
                    <div className="line-clamp-2 text-sm font-semibold">
                      {item.titulo}
                    </div>
                    <div
                      className={`mt-1 text-xs ${selected?.id === item.id ? "text-slate-300" : "text-slate-500"}`}
                    >
                      {item.potencial_cliente || "Sem cliente definido"}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      <span
                        className={`rounded-full px-2 py-0.5 text-[10px] ${selected?.id === item.id ? "bg-white/10" : "bg-slate-200"}`}
                      >
                        {item.status.replace(/_/g, " ")}
                      </span>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>

        <main className="flex min-h-0 flex-col bg-white">
          {!selected ? (
            <div className="flex h-full items-center justify-center p-8">
              <EmptyState
                icon={Bot}
                title="Selecione ou crie uma análise"
                message="A conversa ficará vinculada ao dossiê preliminar e às provas anexadas."
              />
            </div>
          ) : (
            <>
              <header className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4">
                <div>
                  <h2 className="font-semibold text-slate-950">
                    {selected.titulo}
                  </h2>
                  <div className="mt-1 flex flex-wrap gap-2 text-xs text-slate-500">
                    <span>
                      {selected.potencial_cliente ||
                        "Cliente ainda não definido"}
                    </span>
                    {selected.area && (
                      <Badge tone="blue">{selected.area}</Badge>
                    )}
                    {selected.risco_nivel && (
                      <Badge
                        tone={
                          selected.risco_nivel === "critico" ? "red" : "amber"
                        }
                      >
                        {selected.risco_nivel}
                      </Badge>
                    )}
                  </div>
                </div>
                <div className="flex gap-2">
                  <input
                    ref={fileRef}
                    type="file"
                    multiple
                    className="hidden"
                    onChange={(event) => void uploadFiles(event.target.files)}
                  />
                  <Button
                    variant="secondary"
                    onClick={() => fileRef.current?.click()}
                    disabled={busy}
                  >
                    <UploadCloud size={16} /> Provas
                  </Button>
                  <Button
                    onClick={() => void openConversion()}
                    disabled={busy || selected.status === "convertido_em_caso"}
                  >
                    <FolderPlus size={16} /> Transformar em caso
                  </Button>
                </div>
              </header>

              <div className="min-h-0 flex-1 overflow-y-auto bg-slate-50/40 px-4 py-5 sm:px-8">
                <div className="mx-auto max-w-3xl space-y-5">
                  {!messages.length && (
                    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-600">
                      Relate os fatos, indique sua dúvida jurídica ou anexe
                      documentos para iniciar.
                    </div>
                  )}
                  {messages.map((message) => (
                    <div
                      key={message.id}
                      className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      <div
                        className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm shadow-sm ${message.role === "user" ? "bg-slate-900 text-white" : "border border-slate-200 bg-white text-slate-800"}`}
                      >
                        {message.role === "assistant" ? (
                          <Markdown source={message.content} />
                        ) : (
                          <div className="whitespace-pre-wrap">
                            {message.content}
                          </div>
                        )}
                        <div className="mt-2 text-[10px] text-slate-400">
                          {new Date(message.created_at).toLocaleString("pt-BR")}
                        </div>
                      </div>
                    </div>
                  ))}
                  {busy && (
                    <div className="flex items-center gap-2 text-sm text-slate-500">
                      <Loader2 className="animate-spin" size={16} /> Analisando
                      fatos e provas…
                    </div>
                  )}
                  <div ref={bottomRef} />
                </div>
              </div>

              <footer className="border-t border-slate-200 bg-white p-4">
                <div className="mx-auto flex max-w-3xl items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-slate-500">
                  <button
                    type="button"
                    className="rounded-xl p-2 text-slate-500 hover:bg-slate-100"
                    onClick={() => fileRef.current?.click()}
                    title="Anexar provas"
                    aria-label="Anexar provas"
                  >
                    <Paperclip size={19} />
                  </button>
                  <textarea
                    className="max-h-40 min-h-[44px] flex-1 resize-none border-0 px-2 py-2 text-sm outline-none"
                    placeholder="Descreva os fatos ou peça uma análise jurídica…"
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void sendMessage();
                      }
                    }}
                  />
                  <button
                    className="rounded-xl bg-slate-900 p-3 text-white disabled:opacity-40"
                    onClick={() => void sendMessage()}
                    disabled={!prompt.trim() || busy}
                    title="Enviar"
                    aria-label="Enviar mensagem"
                  >
                    <Send size={17} />
                  </button>
                </div>
                <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-slate-400">
                  A conversa usa o Núcleo Único de IA, com pseudonimização,
                  AILog e revisão humana obrigatória.
                </p>
              </footer>
            </>
          )}
        </main>

        <aside className="min-h-0 overflow-y-auto border-t border-slate-200 bg-slate-50/70 p-4 xl:border-l xl:border-t-0">
          <div className="mb-4 flex items-center gap-2">
            <Sparkles size={18} className="text-slate-700" />
            <h3 className="font-semibold text-slate-900">
              Estado atual da análise
            </h3>
          </div>
          {!selected ? (
            <p className="text-sm text-slate-500">
              Selecione uma análise para ver o dossiê estruturado.
            </p>
          ) : (
            <div className="space-y-4">
              <Panel
                title="Síntese"
                icon={FileText}
                items={
                  report.sintese_executiva ? [report.sintese_executiva] : []
                }
              />
              <Panel
                title="Fatos e provas"
                icon={CheckCircle2}
                items={report.fatos_provas}
              />
              <Panel
                title="Contradições"
                icon={AlertTriangle}
                items={report.contradicoes}
                tone="amber"
              />
              <Panel
                title="Riscos"
                icon={ShieldAlert}
                items={report.riscos}
                tone="red"
              />
              <Panel
                title="Documentos faltantes"
                icon={Paperclip}
                items={report.documentos_pendentes}
              />
              <Panel
                title="Próximos passos"
                icon={Gavel}
                items={report.proximos_passos}
              />
              {!!selected.documentos?.length && (
                <div className="rounded-xl border border-slate-200 bg-white p-3">
                  <div className="mb-2 text-sm font-semibold">
                    Provas anexadas
                  </div>
                  <ul className="space-y-1 text-xs text-slate-600">
                    {selected.documentos.map((document) => (
                      <li key={document.id}>• {document.nome_original}</li>
                    ))}
                  </ul>
                </div>
              )}
              <Button
                variant="secondary"
                className="w-full"
                disabled={selected.status === "convertido_em_caso"}
                onClick={() => {
                  void api
                    .post(`/raio-x/${selected.id}/arquivar`)
                    .then(loadList);
                }}
              >
                <Archive size={16} /> Arquivar análise
              </Button>
            </div>
          )}
        </aside>
      </div>

      {showCreate && (
        <Modal
          title="Nova análise preliminar"
          onClose={() => setShowCreate(false)}
        >
          <label className="text-sm font-medium">Título da análise</label>
          <input
            className="mt-1 w-full rounded-lg border p-2"
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            placeholder="Ex.: Acidente da Hilux — DF-345"
          />
          <label className="mt-4 block text-sm font-medium">
            Cliente ou interessado
          </label>
          <input
            className="mt-1 w-full rounded-lg border p-2"
            value={newClient}
            onChange={(event) => setNewClient(event.target.value)}
            placeholder="Opcional"
          />
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowCreate(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => void createAnalysis()}
              disabled={busy || newTitle.trim().length < 3}
            >
              <Plus size={16} /> Criar sala
            </Button>
          </div>
        </Modal>
      )}

      {showConvert && selected && (
        <Modal
          title="Transformar análise em caso"
          onClose={() => setShowConvert(false)}
          wide
        >
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
            Confira os dados antes de criar o cadastro oficial. A conversa
            original e a inteligência preliminar serão preservadas para
            auditoria e revisão.
          </div>

          {hasDuplicates && (
            <ReviewBlock title="Possíveis casos duplicados" tone="red">
              {duplicateCases.map((item, index) => (
                <div
                  key={`${item.id || "protegido"}-${index}`}
                  className="rounded-lg bg-white/70 p-2"
                >
                  <strong>{item.titulo}</strong>
                  {item.numero_processo && (
                    <span> — {item.numero_processo}</span>
                  )}
                  {item.protegido && (
                    <div className="text-xs">
                      Os dados estão protegidos; solicite revisão à gestão.
                    </div>
                  )}
                </div>
              ))}
            </ReviewBlock>
          )}

          {hasConflicts && (
            <ReviewBlock title="Alertas de conflito" tone="red">
              {conflictAlerts.map((item, index) => (
                <div
                  key={`${item.tipo || "alerta"}-${index}`}
                  className="rounded-lg bg-white/70 p-2"
                >
                  <strong>{item.nome || "Correspondência identificada"}</strong>
                  <div>
                    {item.mensagem || "Revisão obrigatória antes da conversão."}
                  </div>
                </div>
              ))}
            </ReviewBlock>
          )}

          {!!preview?.clientes_possivelmente_duplicados?.length && (
            <ReviewBlock
              title="Possíveis clientes correspondentes"
              tone="amber"
            >
              {preview.clientes_possivelmente_duplicados.map((item, index) => (
                <div
                  key={`${item.id || "protegido"}-${index}`}
                  className="rounded-lg bg-white/70 p-2"
                >
                  {item.nome}
                  {item.protegido && (
                    <div className="text-xs">
                      Registro protegido: não é selecionável por esta carteira.
                    </div>
                  )}
                </div>
              ))}
            </ReviewBlock>
          )}

          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="text-sm font-medium">Cliente</label>
              <select
                className="mt-1 w-full rounded-lg border p-2"
                value={conversion.clientMode}
                onChange={(event) =>
                  setConversion({
                    ...conversion,
                    clientMode: event.target.value,
                    clientId: "",
                  })
                }
              >
                <option value="novo">Criar novo cliente</option>
                <option value="existente">
                  Usar cliente existente autorizado
                </option>
              </select>
            </div>

            {conversion.clientMode === "existente" ? (
              <div className="sm:col-span-2">
                <label className="text-sm font-medium">
                  Pesquisar cliente autorizado
                </label>
                <div className="relative mt-1">
                  <Search
                    className="absolute left-3 top-3 text-slate-400"
                    size={16}
                  />
                  <input
                    className="w-full rounded-lg border py-2.5 pl-9 pr-9"
                    value={clientSearch}
                    onChange={(event) => setClientSearch(event.target.value)}
                    placeholder="Digite ao menos 2 caracteres do nome"
                  />
                  {searchingClients && (
                    <Loader2
                      className="absolute right-3 top-3 animate-spin text-slate-400"
                      size={16}
                    />
                  )}
                </div>
                <select
                  className="mt-2 w-full rounded-lg border p-2"
                  value={conversion.clientId}
                  onChange={(event) =>
                    setConversion({
                      ...conversion,
                      clientId: event.target.value,
                    })
                  }
                >
                  <option value="">Selecione um cliente</option>
                  {clientOptions
                    .filter((item) => item.id)
                    .map((item) => (
                      <option key={item.id as string} value={item.id as string}>
                        {item.nome}
                      </option>
                    ))}
                </select>
                {!clientOptions.some((item) => item.id) && (
                  <p className="mt-2 text-xs text-slate-500">
                    Nenhum cliente autorizado localizado. Pesquise outro nome ou
                    utilize “Criar novo cliente”.
                  </p>
                )}
              </div>
            ) : (
              <>
                <div>
                  <label className="text-sm font-medium">
                    Nome ou razão social
                  </label>
                  <input
                    className="mt-1 w-full rounded-lg border p-2"
                    value={conversion.clientName}
                    onChange={(event) =>
                      setConversion({
                        ...conversion,
                        clientName: event.target.value,
                      })
                    }
                  />
                </div>
                <div>
                  <label className="text-sm font-medium">CPF ou CNPJ</label>
                  <input
                    className="mt-1 w-full rounded-lg border p-2"
                    inputMode="numeric"
                    value={conversion.clientDocument}
                    onChange={(event) =>
                      setConversion({
                        ...conversion,
                        clientDocument: event.target.value,
                      })
                    }
                    placeholder="O sistema identifica PF ou PJ pela quantidade de dígitos"
                  />
                </div>
              </>
            )}

            <div>
              <label className="text-sm font-medium">Título do caso</label>
              <input
                className="mt-1 w-full rounded-lg border p-2"
                value={conversion.caseTitle}
                onChange={(event) =>
                  setConversion({
                    ...conversion,
                    caseTitle: event.target.value,
                  })
                }
              />
            </div>
            <div>
              <label className="text-sm font-medium">Área jurídica</label>
              <select
                className="mt-1 w-full rounded-lg border p-2"
                value={conversion.area}
                onChange={(event) =>
                  setConversion({ ...conversion, area: event.target.value })
                }
              >
                {AREAS.map((area) => (
                  <option key={area} value={area}>
                    {area.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="mt-4 space-y-2 text-sm">
            {hasDuplicates && (
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={conversion.confirmDuplicate}
                  onChange={(event) =>
                    setConversion({
                      ...conversion,
                      confirmDuplicate: event.target.checked,
                    })
                  }
                />
                <span>
                  Li os casos possivelmente duplicados acima e confirmo que a
                  abertura deve prosseguir.
                </span>
              </label>
            )}
            {hasConflicts && (
              <label className="flex items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-1"
                  checked={conversion.confirmConflict}
                  onChange={(event) =>
                    setConversion({
                      ...conversion,
                      confirmConflict: event.target.checked,
                    })
                  }
                />
                <span>
                  Li os alertas de conflito acima e confirmo que a revisão ética
                  necessária foi realizada.
                </span>
              </label>
            )}
          </div>

          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setShowConvert(false)}>
              Cancelar
            </Button>
            <Button
              onClick={() => void convertToCase()}
              disabled={
                busy ||
                !conversion.caseTitle.trim() ||
                (conversion.clientMode === "novo"
                  ? !conversion.clientName.trim()
                  : !conversion.clientId) ||
                (hasDuplicates && !conversion.confirmDuplicate) ||
                (hasConflicts && !conversion.confirmConflict)
              }
            >
              <FolderPlus size={16} /> Confirmar e criar caso
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function ReviewBlock({
  title,
  tone,
  children,
}: {
  title: string;
  tone: "red" | "amber";
  children: ReactNode;
}) {
  const classes =
    tone === "red"
      ? "border-red-200 bg-red-50 text-red-900"
      : "border-amber-200 bg-amber-50 text-amber-900";
  return (
    <div className={`mt-3 space-y-2 rounded-xl border p-3 text-sm ${classes}`}>
      <div className="font-semibold">{title}</div>
      {children}
    </div>
  );
}

function Panel({
  title,
  icon: Icon,
  items,
  tone = "slate",
}: {
  title: string;
  icon: typeof FileText;
  items?: unknown[];
  tone?: "slate" | "amber" | "red";
}) {
  const border =
    tone === "red"
      ? "border-red-200"
      : tone === "amber"
        ? "border-amber-200"
        : "border-slate-200";
  return (
    <div className={`rounded-xl border ${border} bg-white p-3`}>
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold text-slate-900">
        <Icon size={15} /> {title}
      </div>
      {!items?.length ? (
        <p className="text-xs text-slate-400">
          Nenhum item identificado com segurança.
        </p>
      ) : (
        <ul className="space-y-2 text-xs text-slate-600">
          {items.slice(0, 8).map((item, index) => (
            <li key={index} className="rounded-lg bg-slate-50 p-2">
              {stringify(item)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4"
      onMouseDown={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`max-h-[90vh] w-full overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl ${wide ? "max-w-3xl" : "max-w-lg"}`}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Fechar">
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
