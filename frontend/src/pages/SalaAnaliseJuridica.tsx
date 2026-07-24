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

type ConversionPreview = {
  bloqueia?: boolean;
  alertas_conflito?: unknown[];
  casos_possivelmente_duplicados?: unknown[];
  clientes_possivelmente_duplicados?: unknown[];
  documentos_disponiveis?: Array<{ id: string; nome: string }>;
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
  if (typeof value === "string" || typeof value === "number")
    return String(value);
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
  const [conversion, setConversion] = useState({
    clientMode: "novo",
    clientId: "",
    clientName: "",
    clientCpf: "",
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
      const { data } = await api.post("/ai/analisar-caso", {
        descricao_fatos:
          "CONTEXTO DA SALA DE ANÁLISE JURÍDICA:\n" +
          JSON.stringify(context) +
          "\n\nPERGUNTA/INSTRUÇÃO ATUAL DO ADVOGADO:\n" +
          userMessage.content,
        area: selected.area || "civil",
        case_id: null,
        nomes_proteger: selected.potencial_cliente
          ? [selected.potencial_cliente]
          : [],
      });
      const content =
        data?.resposta ||
        data?.analise ||
        data?.texto ||
        data?.resultado ||
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
      setConversion((current) => ({
        ...current,
        caseTitle: selected.titulo,
        clientName: selected.potencial_cliente || "",
        area: selected.area || "civil",
      }));
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
      const payload = {
        cliente:
          conversion.clientMode === "existente"
            ? { modo: "existente", client_id: conversion.clientId }
            : {
                modo: "novo",
                nome: conversion.clientName,
                cpf: conversion.clientCpf || null,
              },
        caso: {
          titulo: conversion.caseTitle,
          area: conversion.area,
          prioridade: selected.prazo_urgente ? "critica" : "media",
          descricao_fatos:
            selected.relatorio?.sintese_executiva ||
            messages.map((m) => `${m.role}: ${m.content}`).join("\n\n"),
          case_type: "judicial",
        },
        documento_ids: documentIds,
        transferir_prazos: false,
        transferir_tarefas: true,
        duplicate_confirmed: conversion.confirmDuplicate,
        conflict_confirmed: conversion.confirmConflict,
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
          <button onClick={() => setError(null)} aria-label="Fechar">
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
                    onChange={(e) => void uploadFiles(e.target.files)}
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
                        <div
                          className={`mt-2 text-[10px] ${message.role === "user" ? "text-slate-400" : "text-slate-400"}`}
                        >
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
                    className="rounded-xl p-2 text-slate-500 hover:bg-slate-100"
                    onClick={() => fileRef.current?.click()}
                    title="Anexar provas"
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
                  >
                    <Send size={17} />
                  </button>
                </div>
                <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-slate-400">
                  Saída preliminar sujeita à revisão do advogado. Hipóteses e
                  fontes não verificadas devem ser confirmadas antes do uso
                  externo.
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
                  <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
                    <FileText size={15} /> Provas anexadas
                  </div>
                  <ul className="space-y-1 text-xs text-slate-600">
                    {selected.documentos.map((doc) => (
                      <li key={doc.id} className="truncate">
                        • {doc.nome_original}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <Button
                variant="secondary"
                className="w-full"
                onClick={() =>
                  void api
                    .post(`/raio-x/${selected.id}/arquivar`)
                    .then(loadList)
                }
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
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="Ex.: Acidente da Hilux — DF-345"
          />
          <label className="mt-4 block text-sm font-medium">
            Cliente ou interessado
          </label>
          <input
            className="mt-1 w-full rounded-lg border p-2"
            value={newClient}
            onChange={(e) => setNewClient(e.target.value)}
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
            original permanecerá preservada para auditoria.
          </div>
          {preview?.bloqueia && (
            <div className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-800">
              A prévia identificou impedimentos. Revise conflitos e duplicidades
              antes de confirmar.
            </div>
          )}
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <div>
              <label className="text-sm font-medium">Cliente</label>
              <select
                className="mt-1 w-full rounded-lg border p-2"
                value={conversion.clientMode}
                onChange={(e) =>
                  setConversion({ ...conversion, clientMode: e.target.value })
                }
              >
                <option value="novo">Criar novo cliente</option>
                <option value="existente">Usar cliente existente</option>
              </select>
            </div>
            {conversion.clientMode === "existente" ? (
              <div>
                <label className="text-sm font-medium">ID do cliente</label>
                <input
                  className="mt-1 w-full rounded-lg border p-2"
                  value={conversion.clientId}
                  onChange={(e) =>
                    setConversion({ ...conversion, clientId: e.target.value })
                  }
                />
              </div>
            ) : (
              <div>
                <label className="text-sm font-medium">Nome do cliente</label>
                <input
                  className="mt-1 w-full rounded-lg border p-2"
                  value={conversion.clientName}
                  onChange={(e) =>
                    setConversion({ ...conversion, clientName: e.target.value })
                  }
                />
              </div>
            )}
            {conversion.clientMode === "novo" && (
              <div>
                <label className="text-sm font-medium">CPF/CNPJ</label>
                <input
                  className="mt-1 w-full rounded-lg border p-2"
                  value={conversion.clientCpf}
                  onChange={(e) =>
                    setConversion({ ...conversion, clientCpf: e.target.value })
                  }
                />
              </div>
            )}
            <div>
              <label className="text-sm font-medium">Título do caso</label>
              <input
                className="mt-1 w-full rounded-lg border p-2"
                value={conversion.caseTitle}
                onChange={(e) =>
                  setConversion({ ...conversion, caseTitle: e.target.value })
                }
              />
            </div>
            <div>
              <label className="text-sm font-medium">Área jurídica</label>
              <select
                className="mt-1 w-full rounded-lg border p-2"
                value={conversion.area}
                onChange={(e) =>
                  setConversion({ ...conversion, area: e.target.value })
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
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={conversion.confirmDuplicate}
                onChange={(e) =>
                  setConversion({
                    ...conversion,
                    confirmDuplicate: e.target.checked,
                  })
                }
              />{" "}
              Conferi possíveis duplicidades.
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={conversion.confirmConflict}
                onChange={(e) =>
                  setConversion({
                    ...conversion,
                    confirmConflict: e.target.checked,
                  })
                }
              />{" "}
              Conferi possíveis conflitos de interesse.
            </label>
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
                  : !conversion.clientId.trim())
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
        className={`max-h-[90vh] w-full overflow-y-auto rounded-2xl bg-white p-5 shadow-2xl ${wide ? "max-w-3xl" : "max-w-lg"}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold">{title}</h2>
          <button onClick={onClose}>
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
