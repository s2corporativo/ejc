import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Archive,
  Bot,
  CheckCircle2,
  ChevronRight,
  FileSearch,
  FileUp,
  FolderInput,
  Gavel,
  Loader2,
  MessageSquareText,
  Plus,
  RefreshCw,
  Scale,
  Search,
  Send,
  ShieldAlert,
  Sparkles,
  Trash2,
  UploadCloud,
  UserRound,
  X,
} from "lucide-react";
import Markdown from "../components/Markdown";
import api from "../lib/api";
import { useAuth } from "../stores/auth";

type Documento = {
  id: string;
  nome_original: string;
  tipo_documento?: string | null;
  paginas?: number | null;
  ocr_utilizado?: boolean;
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
  prazo_urgente?: boolean;
  convertido_case_id?: string | null;
  relatorio?: Record<string, unknown>;
  documentos?: Documento[];
  created_at?: string;
  updated_at?: string;
};

type Mensagem = {
  id: string;
  role: "user" | "assistant";
  content: string;
  modo?: string;
  created_at?: string;
  fontes_usadas?: number;
  revisao_obrigatoria?: boolean;
};

type EstadoItem = Record<string, unknown> | string;

type EstadoAnalise = {
  versao?: number;
  atualizado_em?: string;
  sintese_atual?: string;
  fatos?: EstadoItem[];
  provas?: EstadoItem[];
  contradicoes?: EstadoItem[];
  questoes_juridicas?: EstadoItem[];
  riscos?: EstadoItem[];
  documentos_pendentes?: EstadoItem[];
  proximos_passos?: EstadoItem[];
  tese_favoravel?: EstadoItem[];
  tese_adversa?: EstadoItem[];
  visao_julgador?: string;
};

type SalaData = {
  analise_id: string;
  titulo: string;
  status: string;
  convertido_case_id?: string | null;
  conversa: Mensagem[];
  estado_analise: EstadoAnalise;
  ultima_consolidacao_em?: string | null;
  documentos: Documento[];
  aviso?: string;
};

type ConversionPreview = {
  casos_possivelmente_duplicados: Array<Record<string, unknown>>;
  clientes_possivelmente_duplicados: Array<Record<string, unknown>>;
  alertas_conflito: unknown[];
  documentos_disponiveis: Array<{ id: string; nome: string; tipo?: string }>;
  bloqueia: boolean;
};

type Modo =
  | "conversar"
  | "organizar_fatos"
  | "detectar_contradicoes"
  | "avaliar_provas"
  | "simular_defesa"
  | "julgar"
  | "listar_pendencias";

const QUICK_ACTIONS: Array<{
  mode: Modo;
  label: string;
  icon: typeof Scale;
  prompt: string;
}> = [
  {
    mode: "organizar_fatos",
    label: "Organizar fatos",
    icon: FileSearch,
    prompt:
      "Organize os fatos em ordem cronológica e classifique o que está comprovado, alegado, inferido, controvertido, ausente ou superado.",
  },
  {
    mode: "detectar_contradicoes",
    label: "Contradições",
    icon: AlertTriangle,
    prompt:
      "Faça um pente-fino em datas, valores, nomes, locais e versões e identifique todas as contradições documentais.",
  },
  {
    mode: "avaliar_provas",
    label: "Avaliar provas",
    icon: Scale,
    prompt:
      "Avalie a força de cada prova, o que ela demonstra, o que não demonstra e quais provas ainda faltam.",
  },
  {
    mode: "simular_defesa",
    label: "Simular defesa",
    icon: ShieldAlert,
    prompt:
      "Atue como advogado da parte contrária e apresente a defesa mais forte possível, inclusive preliminares e impugnações probatórias.",
  },
  {
    mode: "julgar",
    label: "Julgar",
    icon: Gavel,
    prompt:
      "Atue como magistrado imparcial e indique o que seria decidido agora, o que depende de instrução e o resultado juridicamente provável.",
  },
  {
    mode: "listar_pendencias",
    label: "Pendências",
    icon: CheckCircle2,
    prompt:
      "Liste todas as pendências documentais, técnicas, processuais e decisões humanas necessárias antes de ajuizar ou converter em caso.",
  },
];

const CONVERSION_ROLES = new Set([
  "superadmin",
  "admin",
  "socio",
  "advogado",
  "advogado_auxiliar",
]);

const itemText = (item: EstadoItem): string => {
  if (typeof item === "string") return item;
  const preferred =
    item.texto ??
    item.fato ??
    item.descricao ??
    item.titulo ??
    item.valor ??
    item.nome;
  return preferred ? String(preferred) : JSON.stringify(item);
};

const itemMeta = (item: EstadoItem): string[] => {
  if (typeof item === "string") return [];
  return [
    item.classificacao,
    item.confianca,
    item.forca,
    item.impacto,
    item.nivel,
    item.criticidade,
    item.prioridade,
    item.status,
  ]
    .filter(Boolean)
    .map(String);
};

const formatDate = (value?: string | null) => {
  if (!value) return "";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? ""
    : new Intl.DateTimeFormat("pt-BR", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(date);
};

function StateSection({
  title,
  items,
  tone = "slate",
}: {
  title: string;
  items?: EstadoItem[];
  tone?: "slate" | "amber" | "red" | "blue" | "green";
}) {
  const toneClass = {
    slate: "border-slate-200 bg-slate-50",
    amber: "border-amber-200 bg-amber-50",
    red: "border-red-200 bg-red-50",
    blue: "border-blue-200 bg-blue-50",
    green: "border-emerald-200 bg-emerald-50",
  }[tone];
  return (
    <section className={`rounded-2xl border p-3 ${toneClass}`}>
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-bold uppercase tracking-[0.12em] text-slate-700">
          {title}
        </h3>
        <span className="rounded-full bg-white/80 px-2 py-0.5 text-[11px] font-semibold text-slate-500">
          {items?.length || 0}
        </span>
      </div>
      {!items?.length ? (
        <p className="text-xs leading-relaxed text-slate-500">
          Nenhum item consolidado com segurança.
        </p>
      ) : (
        <div className="space-y-2">
          {items.slice(0, 12).map((item, index) => (
            <div
              key={`${title}-${index}`}
              className="rounded-xl border border-white/80 bg-white/90 p-2.5 text-xs text-slate-700 shadow-sm"
            >
              <p className="leading-relaxed">{itemText(item)}</p>
              {itemMeta(item).length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {itemMeta(item).map((meta) => (
                    <span
                      key={meta}
                      className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-500"
                    >
                      {meta.replaceAll("_", " ")}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default function SalaAnaliseJuridica() {
  const user = useAuth((state) => state.user);
  const canConvert = CONVERSION_ROLES.has(String(user?.role || ""));
  const endRef = useRef<HTMLDivElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const [items, setItems] = useState<Analise[]>([]);
  const [selected, setSelected] = useState<Analise | null>(null);
  const [sala, setSala] = useState<SalaData | null>(null);
  const [search, setSearch] = useState("");
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newClient, setNewClient] = useState("");

  const [showConversion, setShowConversion] = useState(false);
  const [conversion, setConversion] = useState<ConversionPreview | null>(null);
  const [existingClientId, setExistingClientId] = useState("");
  const [newClientName, setNewClientName] = useState("");
  const [newClientCpf, setNewClientCpf] = useState("");
  const [caseTitle, setCaseTitle] = useState("");
  const [caseArea, setCaseArea] = useState("civil");
  const [confirmDuplicate, setConfirmDuplicate] = useState(false);
  const [confirmConflict, setConfirmConflict] = useState(false);
  const [confirmText, setConfirmText] = useState("");

  const loadList = useCallback(async () => {
    const { data } = await api.get("/raio-x/", {
      params: { page_size: 100, search: search.trim() || undefined },
    });
    setItems(data.data || []);
  }, [search]);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        setLoading(true);
        await loadList();
      } catch (err: any) {
        if (active)
          setError(
            err?.response?.data?.detail ||
              "Não foi possível carregar as análises preliminares.",
          );
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [loadList]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [sala?.conversa.length, busy]);

  const openAnalysis = async (id: string) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const [{ data: detail }, { data: room }] = await Promise.all([
        api.get<Analise>(`/raio-x/${id}`),
        api.get<SalaData>(`/raio-x/${id}/sala`),
      ]);
      setSelected(detail);
      setSala(room);
      setCaseTitle(detail.titulo);
      setCaseArea(detail.area || "civil");
      setNewClientName(detail.potencial_cliente || "");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao abrir a análise.");
    } finally {
      setBusy(false);
    }
  };

  const refreshSelected = async () => {
    if (!selected) return;
    await openAnalysis(selected.id);
    await loadList();
  };

  const createAnalysis = async () => {
    if (newTitle.trim().length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post<Analise>("/raio-x/", {
        titulo: newTitle.trim(),
        potencial_cliente: newClient.trim() || null,
      });
      setShowCreate(false);
      setNewTitle("");
      setNewClient("");
      await loadList();
      await openAnalysis(data.id);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao criar a análise.");
    } finally {
      setBusy(false);
    }
  };

  const sendMessage = async (
    textOverride?: string,
    modeOverride: Modo = "conversar",
  ) => {
    if (!selected || !sala || busy || selected.convertido_case_id) return;
    const message = (textOverride ?? input).trim();
    if (!message) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    if (!textOverride) setInput("");
    const optimistic: Mensagem = {
      id: `local-${Date.now()}`,
      role: "user",
      content: message,
      modo: modeOverride,
      created_at: new Date().toISOString(),
    };
    setSala((current) =>
      current
        ? { ...current, conversa: [...current.conversa, optimistic] }
        : current,
    );
    try {
      const { data } = await api.post(`/raio-x/${selected.id}/mensagens`, {
        mensagem: message,
        modo: modeOverride,
      });
      setSala((current) => {
        if (!current) return current;
        const withoutOptimistic = current.conversa.filter(
          (item) => item.id !== optimistic.id,
        );
        return {
          ...current,
          conversa: [
            ...withoutOptimistic,
            optimistic,
            data.mensagem as Mensagem,
          ],
          estado_analise: data.estado_analise,
        };
      });
    } catch (err: any) {
      setSala((current) =>
        current
          ? {
              ...current,
              conversa: current.conversa.filter(
                (item) => item.id !== optimistic.id,
              ),
            }
          : current,
      );
      setError(
        err?.response?.data?.detail ||
          "A análise jurídica não pôde ser concluída.",
      );
      if (!textOverride) setInput(message);
    } finally {
      setBusy(false);
    }
  };

  const consolidate = async () => {
    if (!selected || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post(`/raio-x/${selected.id}/consolidar`, {
        instrucao_adicional: null,
      });
      setSala((current) =>
        current
          ? {
              ...current,
              conversa: [...current.conversa, data.mensagem],
              estado_analise: data.estado_analise,
              ultima_consolidacao_em: new Date().toISOString(),
            }
          : current,
      );
      setNotice("Estado atual da análise consolidado.");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao consolidar a análise.");
    } finally {
      setBusy(false);
    }
  };

  const uploadFiles = async (files: FileList | null) => {
    if (!selected || !files?.length) return;
    setUploading(true);
    setError(null);
    const body = new FormData();
    Array.from(files).forEach((file) => body.append("files", file));
    try {
      const { data } = await api.post(
        `/raio-x/${selected.id}/documentos/analisar`,
        body,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      const errors = data.erros?.length ? ` ${data.erros.length} erro(s).` : "";
      setNotice(`Documentos processados.${errors}`);
      await refreshSelected();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao processar documentos.");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const clearConversation = async () => {
    if (!selected || !window.confirm("Reiniciar a conversa e o estado consolidado? Os documentos serão preservados.")) return;
    setBusy(true);
    try {
      const { data } = await api.delete(`/raio-x/${selected.id}/mensagens`);
      setSala((current) =>
        current
          ? {
              ...current,
              conversa: [],
              estado_analise: data.estado_analise,
              ultima_consolidacao_em: null,
            }
          : current,
      );
      setNotice("Conversa reiniciada; documentos preservados.");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao reiniciar a conversa.");
    } finally {
      setBusy(false);
    }
  };

  const archive = async () => {
    if (!selected || !window.confirm("Arquivar esta análise preliminar?")) return;
    setBusy(true);
    try {
      await api.post(`/raio-x/${selected.id}/arquivar`);
      setSelected(null);
      setSala(null);
      await loadList();
      setNotice("Análise arquivada.");
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao arquivar a análise.");
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
      setConfirmDuplicate(false);
      setConfirmConflict(false);
      setConfirmText("");
      setShowConversion(true);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao preparar a conversão.");
    } finally {
      setBusy(false);
    }
  };

  const convert = async () => {
    if (!selected || !conversion) return;
    const hasDuplicate = conversion.casos_possivelmente_duplicados.length > 0;
    const hasConflict = conversion.alertas_conflito.length > 0;
    const confirmed =
      confirmText === "TRANSFORMAR EM CASO DO ESCRITÓRIO" &&
      (!hasDuplicate || confirmDuplicate) &&
      (!hasConflict || confirmConflict);
    if (!confirmed) return;
    if (!existingClientId && newClientName.trim().length < 3) {
      setError("Informe o cliente existente ou o nome do novo cliente.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const { data } = await api.post(`/raio-x/${selected.id}/converter`, {
        cliente: existingClientId
          ? { modo: "existente", client_id: existingClientId }
          : {
              modo: "novo",
              nome: newClientName.trim(),
              cpf: newClientCpf.trim() || null,
            },
        caso: {
          titulo: caseTitle.trim() || selected.titulo,
          area: caseArea || "civil",
          numero_processo: selected.numero_processo || null,
          tribunal: selected.tribunal || null,
          descricao_fatos:
            sala?.estado_analise?.sintese_atual ||
            String(selected.relatorio?.sintese_executiva || ""),
          prioridade: selected.prazo_urgente ? "critica" : "media",
        },
        documento_ids: conversion.documentos_disponiveis.map((doc) => doc.id),
        transferir_prazos: false,
        transferir_tarefas: true,
        duplicate_confirmed: confirmDuplicate,
        conflict_confirmed: confirmConflict,
        confirmacao: confirmText,
      });
      window.location.assign(`/casos/${data.case_id}`);
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Falha ao transformar em caso.");
    } finally {
      setBusy(false);
    }
  };

  const filteredItems = useMemo(() => {
    const query = search.trim().toLocaleLowerCase("pt-BR");
    if (!query) return items;
    return items.filter((item) =>
      [item.titulo, item.potencial_cliente, item.numero_processo]
        .filter(Boolean)
        .some((value) =>
          String(value).toLocaleLowerCase("pt-BR").includes(query),
        ),
    );
  }, [items, search]);

  const converted = Boolean(selected?.convertido_case_id);
  const state = sala?.estado_analise || {};

  if (loading) {
    return (
      <div className="grid min-h-[65vh] place-items-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary-600" />
      </div>
    );
  }

  return (
    <div className="-m-4 flex min-h-[calc(100vh-4rem)] flex-col bg-slate-100 lg:-m-6">
      <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 lg:px-6">
        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="rounded-2xl bg-slate-950 p-2.5 text-white">
            <Scale className="h-5 w-5" />
          </div>
          <div className="min-w-0">
            <h1 className="truncate text-lg font-bold text-slate-950">
              Sala de Análise Jurídica
            </h1>
            <p className="truncate text-xs text-slate-500">
              Conversa livre por fora; fatos, provas, riscos e contradições estruturados por dentro.
            </p>
          </div>
        </div>
        {selected && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => void consolidate()}
              disabled={busy || converted}
              className="inline-flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />
              Consolidar
            </button>
            {canConvert && !converted && (
              <button
                onClick={() => void openConversion()}
                disabled={busy}
                className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-800 disabled:opacity-50"
              >
                <FolderInput className="h-4 w-4" /> Transformar em caso
              </button>
            )}
            {converted && (
              <button
                onClick={() =>
                  window.location.assign(`/casos/${selected.convertido_case_id}`)
                }
                className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-semibold text-white"
              >
                Abrir caso <ChevronRight className="h-4 w-4" />
              </button>
            )}
          </div>
        )}
      </header>

      {error && (
        <div className="mx-4 mt-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700 lg:mx-6">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">{error}</span>
          <button onClick={() => setError(null)} aria-label="Fechar erro">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}
      {notice && (
        <div className="mx-4 mt-3 flex items-start gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700 lg:mx-6">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
          <span className="flex-1">{notice}</span>
          <button onClick={() => setNotice(null)} aria-label="Fechar aviso">
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      <div className="grid min-h-0 flex-1 xl:grid-cols-[286px_minmax(0,1fr)_350px]">
        <aside className="border-r border-slate-200 bg-white p-3 xl:overflow-y-auto">
          <button
            onClick={() => setShowCreate(true)}
            className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl bg-primary-600 px-3 py-2.5 text-sm font-bold text-white hover:bg-primary-700"
          >
            <Plus className="h-4 w-4" /> Nova análise
          </button>
          <div className="relative mb-3">
            <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Buscar análises"
              className="w-full rounded-xl border border-slate-200 py-2 pl-9 pr-3 text-sm outline-none focus:border-primary-400"
            />
          </div>
          <div className="space-y-1.5">
            {filteredItems.map((item) => {
              const active = item.id === selected?.id;
              return (
                <button
                  key={item.id}
                  onClick={() => void openAnalysis(item.id)}
                  className={`w-full rounded-xl border p-3 text-left transition ${
                    active
                      ? "border-primary-200 bg-primary-50"
                      : "border-transparent hover:border-slate-200 hover:bg-slate-50"
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <MessageSquareText
                      className={`mt-0.5 h-4 w-4 shrink-0 ${active ? "text-primary-600" : "text-slate-400"}`}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-sm font-semibold text-slate-900">
                        {item.titulo}
                      </div>
                      <div className="mt-1 truncate text-xs text-slate-500">
                        {item.potencial_cliente || "Cliente não definido"}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {item.risco_nivel && (
                          <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-700">
                            {item.risco_nivel}
                          </span>
                        )}
                        {item.convertido_case_id && (
                          <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-semibold uppercase text-emerald-700">
                            caso criado
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </button>
              );
            })}
            {!filteredItems.length && (
              <div className="rounded-xl border border-dashed border-slate-200 p-5 text-center text-sm text-slate-500">
                Nenhuma análise encontrada.
              </div>
            )}
          </div>
        </aside>

        <main className="flex min-h-[560px] min-w-0 flex-col bg-white">
          {!selected || !sala ? (
            <div className="grid flex-1 place-items-center p-8 text-center">
              <div className="max-w-xl">
                <div className="mx-auto mb-5 grid h-16 w-16 place-items-center rounded-3xl bg-slate-950 text-white shadow-lg">
                  <Bot className="h-8 w-8" />
                </div>
                <h2 className="text-2xl font-bold text-slate-950">
                  Comece por uma dúvida, fato ou documento
                </h2>
                <p className="mt-3 leading-relaxed text-slate-600">
                  A Sala organiza a consulta preliminar, confronta as provas,
                  identifica contradições, simula a defesa e permite converter o
                  resultado em caso somente após sua confirmação.
                </p>
                <button
                  onClick={() => setShowCreate(true)}
                  className="mt-6 inline-flex items-center gap-2 rounded-xl bg-primary-600 px-5 py-3 font-bold text-white"
                >
                  <Plus className="h-5 w-5" /> Criar primeira análise
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-3 border-b border-slate-100 px-4 py-3 lg:px-6">
                <div className="min-w-0 flex-1">
                  <h2 className="truncate font-bold text-slate-950">
                    {selected.titulo}
                  </h2>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {selected.potencial_cliente || "Cliente não definido"} · {sala.documentos.length} documento(s)
                    {sala.ultima_consolidacao_em
                      ? ` · consolidado em ${formatDate(sala.ultima_consolidacao_em)}`
                      : ""}
                  </p>
                </div>
                <input
                  ref={fileRef}
                  type="file"
                  multiple
                  accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff,.webp"
                  className="hidden"
                  onChange={(event) => void uploadFiles(event.target.files)}
                />
                <button
                  onClick={() => fileRef.current?.click()}
                  disabled={uploading || converted}
                  className="inline-flex items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  {uploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <UploadCloud className="h-4 w-4" />
                  )}
                  Anexar provas
                </button>
                <button
                  onClick={() => void clearConversation()}
                  disabled={busy || converted}
                  title="Reiniciar conversa"
                  className="rounded-xl border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 disabled:opacity-50"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
                <button
                  onClick={() => void archive()}
                  disabled={busy || converted}
                  title="Arquivar análise"
                  className="rounded-xl border border-slate-200 p-2 text-slate-500 hover:bg-slate-50 disabled:opacity-50"
                >
                  <Archive className="h-4 w-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto px-4 py-5 lg:px-8">
                {!sala.conversa.length && (
                  <div className="mx-auto max-w-2xl rounded-3xl border border-slate-200 bg-slate-50 p-6">
                    <div className="flex items-center gap-3">
                      <div className="rounded-2xl bg-slate-950 p-2.5 text-white">
                        <Sparkles className="h-5 w-5" />
                      </div>
                      <div>
                        <h3 className="font-bold text-slate-950">
                          Análise preliminar pronta
                        </h3>
                        <p className="text-sm text-slate-500">
                          Relate os fatos, faça uma pergunta ou use uma ação rápida.
                        </p>
                      </div>
                    </div>
                    <div className="mt-5 grid gap-2 sm:grid-cols-2">
                      {QUICK_ACTIONS.slice(0, 4).map((action) => (
                        <button
                          key={action.mode}
                          onClick={() =>
                            void sendMessage(action.prompt, action.mode)
                          }
                          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white p-3 text-left text-sm font-semibold text-slate-700 hover:border-primary-300 hover:bg-primary-50"
                        >
                          <action.icon className="h-4 w-4 text-primary-600" />
                          {action.label}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                <div className="mx-auto max-w-3xl space-y-5">
                  {sala.conversa.map((message) => (
                    <div
                      key={message.id}
                      className={`flex gap-3 ${message.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                      {message.role === "assistant" && (
                        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-slate-950 text-white">
                          <Bot className="h-4 w-4" />
                        </div>
                      )}
                      <div
                        className={`max-w-[88%] rounded-2xl px-4 py-3 text-sm shadow-sm ${
                          message.role === "user"
                            ? "bg-primary-600 text-white"
                            : "border border-slate-200 bg-white text-slate-700"
                        }`}
                      >
                        {message.role === "assistant" ? (
                          <Markdown source={message.content} />
                        ) : (
                          <p className="whitespace-pre-wrap leading-relaxed">
                            {message.content}
                          </p>
                        )}
                        <div
                          className={`mt-2 flex flex-wrap items-center gap-2 text-[10px] ${
                            message.role === "user"
                              ? "text-white/70"
                              : "text-slate-400"
                          }`}
                        >
                          {message.modo && (
                            <span>{message.modo.replaceAll("_", " ")}</span>
                          )}
                          {message.fontes_usadas !== undefined && (
                            <span>· {message.fontes_usadas} fonte(s) RAG</span>
                          )}
                          {message.created_at && (
                            <span>· {formatDate(message.created_at)}</span>
                          )}
                        </div>
                      </div>
                      {message.role === "user" && (
                        <div className="mt-1 grid h-8 w-8 shrink-0 place-items-center rounded-xl bg-primary-100 text-primary-700">
                          <UserRound className="h-4 w-4" />
                        </div>
                      )}
                    </div>
                  ))}
                  {busy && (
                    <div className="flex items-center gap-3 text-sm text-slate-500">
                      <div className="grid h-8 w-8 place-items-center rounded-xl bg-slate-950 text-white">
                        <Bot className="h-4 w-4" />
                      </div>
                      <div className="flex items-center gap-2 rounded-2xl border border-slate-200 bg-white px-4 py-3">
                        <Loader2 className="h-4 w-4 animate-spin" />
                        Analisando fatos, provas e riscos…
                      </div>
                    </div>
                  )}
                  <div ref={endRef} />
                </div>
              </div>

              <div className="border-t border-slate-200 bg-white px-4 py-3 lg:px-8">
                <div className="mx-auto max-w-3xl">
                  <div className="mb-2 flex gap-2 overflow-x-auto pb-1">
                    {QUICK_ACTIONS.map((action) => (
                      <button
                        key={action.mode}
                        onClick={() => void sendMessage(action.prompt, action.mode)}
                        disabled={busy || converted}
                        className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:border-primary-300 hover:text-primary-700 disabled:opacity-50"
                      >
                        <action.icon className="h-3.5 w-3.5" /> {action.label}
                      </button>
                    ))}
                  </div>
                  <div className="flex items-end gap-2 rounded-2xl border border-slate-300 bg-white p-2 shadow-sm focus-within:border-primary-400 focus-within:ring-2 focus-within:ring-primary-100">
                    <textarea
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" && !event.shiftKey) {
                          event.preventDefault();
                          void sendMessage();
                        }
                      }}
                      disabled={busy || converted}
                      rows={2}
                      placeholder={
                        converted
                          ? "Análise convertida. Continue no workspace do caso."
                          : "Descreva fatos, acrescente uma prova ou faça uma pergunta jurídica…"
                      }
                      className="max-h-40 min-h-[48px] flex-1 resize-none border-0 bg-transparent px-2 py-2 text-sm outline-none placeholder:text-slate-400 disabled:opacity-60"
                    />
                    <button
                      onClick={() => void sendMessage()}
                      disabled={busy || !input.trim() || converted}
                      className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-primary-600 text-white hover:bg-primary-700 disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      <Send className="h-4 w-4" />
                    </button>
                  </div>
                  <p className="mt-1.5 text-center text-[10px] text-slate-400">
                    Rascunho interno com revisão humana obrigatória. A IA não protocola nem altera o caso oficial.
                  </p>
                </div>
              </div>
            </>
          )}
        </main>

        <aside className="border-l border-slate-200 bg-slate-50 p-3 xl:overflow-y-auto">
          {!selected || !sala ? (
            <div className="rounded-2xl border border-dashed border-slate-300 p-5 text-center text-sm text-slate-500">
              O estado jurídico da análise aparecerá aqui.
            </div>
          ) : (
            <div className="space-y-3">
              <section className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-primary-600" />
                  <h2 className="text-sm font-bold text-slate-950">
                    Estado atual da análise
                  </h2>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-slate-600">
                  {state.sintese_atual || "Síntese ainda não consolidada."}
                </p>
                <div className="mt-3 flex flex-wrap gap-2 text-[10px] font-semibold uppercase text-slate-500">
                  <span className="rounded-full bg-slate-100 px-2 py-1">
                    versão {state.versao || 1}
                  </span>
                  {selected.prazo_urgente && (
                    <span className="rounded-full bg-red-100 px-2 py-1 text-red-700">
                      prazo urgente
                    </span>
                  )}
                </div>
              </section>

              <StateSection title="Fatos" items={state.fatos} tone="blue" />
              <StateSection
                title="Contradições"
                items={state.contradicoes}
                tone="red"
              />
              <StateSection title="Riscos" items={state.riscos} tone="amber" />
              <StateSection
                title="Documentos pendentes"
                items={state.documentos_pendentes}
                tone="amber"
              />
              <StateSection
                title="Próximos passos"
                items={state.proximos_passos}
                tone="green"
              />

              <section className="rounded-2xl border border-slate-200 bg-white p-4">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-[0.12em] text-slate-700">
                    Provas anexadas
                  </h3>
                  <FileUp className="h-4 w-4 text-slate-400" />
                </div>
                {!sala.documentos.length ? (
                  <p className="text-xs text-slate-500">
                    Nenhum documento anexado.
                  </p>
                ) : (
                  <div className="space-y-2">
                    {sala.documentos.map((doc) => (
                      <div
                        key={doc.id}
                        className="rounded-xl border border-slate-100 bg-slate-50 p-2.5"
                      >
                        <p className="truncate text-xs font-semibold text-slate-700">
                          {doc.nome_original}
                        </p>
                        <p className="mt-1 text-[10px] text-slate-400">
                          {doc.tipo_documento || "não classificado"}
                          {doc.paginas ? ` · ${doc.paginas} pág.` : ""}
                          {doc.ocr_utilizado ? " · OCR" : ""}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              {state.visao_julgador && (
                <section className="rounded-2xl border border-violet-200 bg-violet-50 p-4">
                  <div className="flex items-center gap-2 text-violet-800">
                    <Gavel className="h-4 w-4" />
                    <h3 className="text-xs font-bold uppercase tracking-[0.12em]">
                      Visão do julgador
                    </h3>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-violet-900">
                    {state.visao_julgador}
                  </p>
                </section>
              )}
            </div>
          )}
        </aside>
      </div>

      {showCreate && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-slate-950/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-slate-950">Nova análise</h2>
                <p className="text-sm text-slate-500">
                  Ainda não será criado cliente nem caso oficial.
                </p>
              </div>
              <button onClick={() => setShowCreate(false)}>
                <X className="h-5 w-5 text-slate-400" />
              </button>
            </div>
            <div className="mt-5 space-y-4">
              <label className="block text-sm font-semibold text-slate-700">
                Título da análise
                <input
                  value={newTitle}
                  onChange={(event) => setNewTitle(event.target.value)}
                  placeholder="Ex.: Acidente da Hilux no viaduto"
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-primary-400"
                />
              </label>
              <label className="block text-sm font-semibold text-slate-700">
                Potencial cliente
                <input
                  value={newClient}
                  onChange={(event) => setNewClient(event.target.value)}
                  placeholder="Opcional"
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal outline-none focus:border-primary-400"
                />
              </label>
            </div>
            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setShowCreate(false)}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600"
              >
                Cancelar
              </button>
              <button
                onClick={() => void createAnalysis()}
                disabled={busy || newTitle.trim().length < 3}
                className="inline-flex items-center gap-2 rounded-xl bg-primary-600 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
              >
                {busy && <Loader2 className="h-4 w-4 animate-spin" />} Criar análise
              </button>
            </div>
          </div>
        </div>
      )}

      {showConversion && conversion && selected && (
        <div className="fixed inset-0 z-50 grid place-items-center overflow-y-auto bg-slate-950/60 p-4 backdrop-blur-sm">
          <div className="my-6 w-full max-w-2xl rounded-3xl bg-white p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-xl font-bold text-slate-950">
                  Transformar em caso
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Revise o cliente, a classificação e os alertas antes de criar o cadastro oficial.
                </p>
              </div>
              <button onClick={() => setShowConversion(false)}>
                <X className="h-5 w-5 text-slate-400" />
              </button>
            </div>

            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              <label className="text-sm font-semibold text-slate-700">
                ID de cliente existente
                <input
                  value={existingClientId}
                  onChange={(event) => setExistingClientId(event.target.value)}
                  placeholder="Deixe vazio para criar novo"
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal"
                />
              </label>
              <label className="text-sm font-semibold text-slate-700">
                Nome do novo cliente
                <input
                  value={newClientName}
                  onChange={(event) => setNewClientName(event.target.value)}
                  disabled={Boolean(existingClientId)}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal disabled:bg-slate-100"
                />
              </label>
              <label className="text-sm font-semibold text-slate-700">
                CPF do novo cliente
                <input
                  value={newClientCpf}
                  onChange={(event) => setNewClientCpf(event.target.value)}
                  disabled={Boolean(existingClientId)}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal disabled:bg-slate-100"
                />
              </label>
              <label className="text-sm font-semibold text-slate-700">
                Área jurídica
                <input
                  value={caseArea}
                  onChange={(event) => setCaseArea(event.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal"
                />
              </label>
              <label className="text-sm font-semibold text-slate-700 sm:col-span-2">
                Título do caso
                <input
                  value={caseTitle}
                  onChange={(event) => setCaseTitle(event.target.value)}
                  className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal"
                />
              </label>
            </div>

            {conversion.casos_possivelmente_duplicados.length > 0 && (
              <label className="mt-5 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <input
                  type="checkbox"
                  checked={confirmDuplicate}
                  onChange={(event) => setConfirmDuplicate(event.target.checked)}
                  className="mt-1"
                />
                <span>
                  Existem {conversion.casos_possivelmente_duplicados.length} caso(s) possivelmente duplicado(s). Revisei e autorizo prosseguir.
                </span>
              </label>
            )}
            {conversion.alertas_conflito.length > 0 && (
              <label className="mt-3 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-900">
                <input
                  type="checkbox"
                  checked={confirmConflict}
                  onChange={(event) => setConfirmConflict(event.target.checked)}
                  className="mt-1"
                />
                <span>
                  Existem {conversion.alertas_conflito.length} alerta(s) de possível conflito. Realizei a conferência humana e autorizo prosseguir.
                </span>
              </label>
            )}

            <label className="mt-5 block text-sm font-semibold text-slate-700">
              Confirmação obrigatória
              <input
                value={confirmText}
                onChange={(event) => setConfirmText(event.target.value)}
                placeholder="TRANSFORMAR EM CASO DO ESCRITÓRIO"
                className="mt-1.5 w-full rounded-xl border border-slate-200 px-3 py-2.5 font-normal"
              />
            </label>

            <div className="mt-6 flex justify-end gap-2">
              <button
                onClick={() => setShowConversion(false)}
                className="rounded-xl border border-slate-200 px-4 py-2 text-sm font-semibold text-slate-600"
              >
                Cancelar
              </button>
              <button
                onClick={() => void convert()}
                disabled={
                  busy ||
                  confirmText !== "TRANSFORMAR EM CASO DO ESCRITÓRIO" ||
                  (conversion.casos_possivelmente_duplicados.length > 0 &&
                    !confirmDuplicate) ||
                  (conversion.alertas_conflito.length > 0 && !confirmConflict)
                }
                className="inline-flex items-center gap-2 rounded-xl bg-slate-950 px-4 py-2 text-sm font-bold text-white disabled:opacity-40"
              >
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                Confirmar e criar caso
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
