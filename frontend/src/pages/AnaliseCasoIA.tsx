import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { Link } from "react-router-dom";
import {
  Archive,
  ArchiveRestore,
  Bot,
  ClipboardPaste,
  FileText,
  Loader2,
  MoreVertical,
  Paperclip,
  Pencil,
  Plus,
  Scale,
  Send,
  SquarePen,
  StopCircle,
  Trash2,
  X,
} from "lucide-react";
import api from "../lib/api";
import { asList } from "../lib/list";
import { streamSSE, SSEHttpError, type SSEEvent } from "../lib/stream";
import Markdown from "../components/Markdown";
import { toast } from "../components/Toast";
import {
  AIFactualityLegend,
  AISurface,
  Badge,
  Button,
  ConfirmModal,
  Dropdown,
  EmptyState,
  ErrorState,
  HumanValidationStatus,
  IANotice,
  Modal,
  PageHeader,
  SectionCard,
  Spinner,
  Textarea,
  cn,
} from "../components/UI";
import type { Case } from "../types";

// ── Contrato do módulo "Análise de Caso IA" ──────────────────────────────────
// Chat multi-turno com IA no papel de advogado sênior. As chamadas REST vão
// pelo cliente axios (baseURL /api/v1 → path SEM /api). O streaming da resposta
// usa streamSSE com o path ABSOLUTO real (/api/analise-caso-ia/...), espelhando
// AgenteIA.tsx. Toda saída da IA nasce rascunho — revisão humana obrigatória.

type Papel = "user" | "assistant";
type Nivel = "padrao" | "alto" | "maximo";

interface SessaoOut {
  id: string;
  case_id: string | null;
  titulo: string;
  nivel: Nivel;
  area: string | null;
  arquivada: boolean;
  created_at: string;
  updated_at: string;
}

interface SessaoResumo extends SessaoOut {
  total_mensagens: number;
  ultima_mensagem_preview: string | null;
  ultima_atividade: string;
}

interface MensagemOut {
  id: string;
  sessao_id: string;
  papel: Papel;
  conteudo: string;
  anexo_nome: string | null;
  ai_log_id: string | null;
  is_rascunho: boolean;
  created_at: string;
}

interface SessaoDetalhe extends SessaoOut {
  mensagens: MensagemOut[];
}

// Bolha local: a MensagemOut do servidor acrescida do estado de streaming e dos
// metadados do evento `concluido` (modelo/tokens/custo/relatório de citações).
interface MensagemLocal extends MensagemOut {
  streaming?: boolean;
  cancelada?: boolean;
  modelo?: string | null;
  provedor?: string | null;
  tokens_input?: number | null;
  tokens_output?: number | null;
  custo_estimado_brl?: number | null;
  citacoes?: Record<string, unknown> | null;
}

const NIVEIS: Array<{ value: Nivel; label: string }> = [
  { value: "padrao", label: "Padrão (rápido)" },
  { value: "alto", label: "Alto (recomendado)" },
  { value: "maximo", label: "Máximo (mais profundo)" },
];

const NIVEL_LABEL: Record<Nivel, string> = {
  padrao: "Padrão",
  alto: "Alto",
  maximo: "Máximo",
};

const EXTENSOES_DOC = ".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff,.webp";

function fmtQuando(iso?: string | null): string {
  if (!iso) return "";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return "";
  return data.toLocaleString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function detalheErro(e: unknown, fallback: string): string {
  const err = e as { response?: { data?: { detail?: unknown } } };
  const detail = err?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

// Relatório do citation gate — estrutura livre; renderizado de forma defensiva
// (nunca dangerouslySetInnerHTML). Preserva o gate anti-alucinação na UI.
function CitacoesBloco({
  citacoes,
}: {
  citacoes?: Record<string, unknown> | null;
}) {
  if (!citacoes || Object.keys(citacoes).length === 0) return null;
  return (
    <details className="mt-2 rounded-lg border border-slate-200 bg-white/70 p-2 dark:border-white/10 dark:bg-white/[0.03]">
      <summary className="cursor-pointer text-xs font-medium text-slate-600 dark:text-slate-300">
        Verificação de citações (gate anti-alucinação)
      </summary>
      <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-5 text-slate-600 dark:text-slate-300">
        {JSON.stringify(citacoes, null, 2)}
      </pre>
    </details>
  );
}

function Bolha({ msg }: { msg: MensagemLocal }) {
  const isUser = msg.papel === "user";
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-tr-sm bg-ai-600 px-4 py-2.5 text-sm text-white shadow-sm">
          {msg.anexo_nome && (
            <span className="mb-1.5 inline-flex items-center gap-1.5 rounded-full bg-white/20 px-2 py-0.5 text-[11px] font-medium">
              <FileText className="h-3 w-3" /> {msg.anexo_nome}
            </span>
          )}
          <p className="whitespace-pre-wrap break-words leading-relaxed">
            {msg.conteudo}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start gap-2">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-ai-600 text-white">
        <Bot className="h-4 w-4" />
      </div>
      <div className="min-w-0 max-w-[85%] rounded-2xl rounded-tl-sm border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-800 shadow-sm dark:border-white/10 dark:bg-white/[0.04] dark:text-slate-200">
        {msg.streaming && !msg.conteudo ? (
          <div className="flex items-center gap-2 text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" /> O advogado de IA está
            analisando…
          </div>
        ) : (
          <>
            <Markdown source={msg.conteudo} />
            {msg.streaming && (
              <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-ai-500 align-middle" />
            )}
          </>
        )}

        {!msg.streaming && msg.conteudo && (
          <div className="mt-3 space-y-2 border-t border-slate-200 pt-2 dark:border-white/10">
            <div className="flex flex-wrap items-center gap-1.5">
              {msg.is_rascunho && <Badge tone="amber">Rascunho</Badge>}
              <HumanValidationStatus value="nao revisado" />
              {msg.cancelada && <Badge tone="slate">Interrompida</Badge>}
              {typeof msg.custo_estimado_brl === "number" &&
                msg.custo_estimado_brl > 0 && (
                  <Badge tone="slate">
                    R$ {msg.custo_estimado_brl.toFixed(4)}
                  </Badge>
                )}
              {msg.modelo && (
                <span className="text-[11px] text-slate-400">
                  {msg.provedor ? `${msg.provedor} · ` : ""}
                  {msg.modelo}
                </span>
              )}
            </div>
            <CitacoesBloco citacoes={msg.citacoes} />
          </div>
        )}
      </div>
    </div>
  );
}

export default function AnaliseCasoIA() {
  // Lista de sessões (coluna esquerda)
  const [sessoes, setSessoes] = useState<SessaoResumo[]>([]);
  const [carregandoLista, setCarregandoLista] = useState(true);
  const [erroLista, setErroLista] = useState(false);
  const [mostrarArquivadas, setMostrarArquivadas] = useState(false);

  // Sessão aberta + thread de mensagens (coluna direita)
  const [sessaoAtual, setSessaoAtual] = useState<SessaoDetalhe | null>(null);
  const [mensagens, setMensagens] = useState<MensagemLocal[]>([]);
  const [carregandoSessao, setCarregandoSessao] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [erroChat, setErroChat] = useState<string | null>(null);
  const [uploadBusy, setUploadBusy] = useState(false);

  // Composer
  const [input, setInput] = useState("");
  const [textoColado, setTextoColado] = useState("");
  const [colarAberto, setColarAberto] = useState(false);

  // Modal "Nova análise"
  const [modalNova, setModalNova] = useState(false);
  const [criando, setCriando] = useState(false);
  const [novoTitulo, setNovoTitulo] = useState("");
  const [novoNivel, setNovoNivel] = useState<Nivel>("alto");
  const [novaArea, setNovaArea] = useState("");
  const [novoCaso, setNovoCaso] = useState("");
  const [casos, setCasos] = useState<Case[]>([]);

  // Renomear / apagar
  const [renomearAlvo, setRenomearAlvo] = useState<SessaoResumo | null>(null);
  const [renomearTitulo, setRenomearTitulo] = useState("");
  const [apagarAlvo, setApagarAlvo] = useState<SessaoResumo | null>(null);
  const [apagando, setApagando] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const threadRef = useRef<HTMLDivElement | null>(null);

  const carregarSessoes = useCallback(async () => {
    setCarregandoLista(true);
    setErroLista(false);
    try {
      const { data } = await api.get("/analise-caso-ia/sessoes", {
        params: { arquivadas: mostrarArquivadas },
      });
      setSessoes(asList<SessaoResumo>(data));
    } catch {
      setErroLista(true);
    } finally {
      setCarregandoLista(false);
    }
  }, [mostrarArquivadas]);

  useEffect(() => {
    void carregarSessoes();
  }, [carregarSessoes]);

  // Casos do usuário para o seletor opcional ao criar a sessão (endpoint já
  // existente GET /cases). Falha silenciosa: o vínculo de caso é opcional.
  useEffect(() => {
    api
      .get("/cases/", { params: { page_size: 200 } })
      .then(({ data }) => setCasos(asList<Case>(data)))
      .catch(() => setCasos([]));
  }, []);

  // Autoscroll ao fim da thread quando chegam mensagens/deltas.
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [mensagens, carregandoSessao]);

  const abrirSessao = useCallback(async (id: string) => {
    abortRef.current?.abort();
    setCarregandoSessao(true);
    setErroChat(null);
    try {
      const { data } = await api.get<SessaoDetalhe>(
        `/analise-caso-ia/sessoes/${id}`,
      );
      setSessaoAtual(data);
      setMensagens((data.mensagens || []).map((m) => ({ ...m })));
    } catch (e) {
      toast.error(detalheErro(e, "Não foi possível abrir a análise."));
    } finally {
      setCarregandoSessao(false);
    }
  }, []);

  const criarSessao = async () => {
    setCriando(true);
    try {
      const body = {
        titulo: novoTitulo.trim() || undefined,
        nivel: novoNivel,
        area: novaArea.trim() || undefined,
        case_id: novoCaso || null,
      };
      const { data } = await api.post<SessaoOut>(
        "/analise-caso-ia/sessoes",
        body,
      );
      setModalNova(false);
      setNovoTitulo("");
      setNovaArea("");
      setNovoCaso("");
      setNovoNivel("alto");
      await carregarSessoes();
      await abrirSessao(data.id);
    } catch (e) {
      toast.error(detalheErro(e, "Não foi possível criar a análise."));
    } finally {
      setCriando(false);
    }
  };

  const enviar = async () => {
    const sessao = sessaoAtual;
    if (!sessao || streaming || uploadBusy) return;
    const conteudo = input.trim();
    if (conteudo.length < 2) {
      toast.error("Escreva sua pergunta ou instrução para a IA.");
      return;
    }
    const colado = textoColado.trim();
    const tmpUser = `tmp-user-${Date.now()}`;
    const tmpAi = `tmp-ai-${Date.now()}`;

    setMensagens((prev) => [
      ...prev,
      {
        id: tmpUser,
        sessao_id: sessao.id,
        papel: "user",
        conteudo,
        anexo_nome: colado ? "Texto colado" : null,
        ai_log_id: null,
        is_rascunho: false,
        created_at: new Date().toISOString(),
      },
      {
        id: tmpAi,
        sessao_id: sessao.id,
        papel: "assistant",
        conteudo: "",
        anexo_nome: null,
        ai_log_id: null,
        is_rascunho: true,
        created_at: new Date().toISOString(),
        streaming: true,
      },
    ]);
    setInput("");
    setTextoColado("");
    setColarAberto(false);
    setErroChat(null);
    setStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;

    const removerBolhaAi = () =>
      setMensagens((prev) => prev.filter((m) => m.id !== tmpAi));

    // Erro ANTES do stream persistir a msg do usuário (streamSSE lança:
    // SSEHttpError 403/429/422 ou falha de rede). Como o backend não gravou
    // nada, removemos também a bolha temporária do usuário — evita órfã visível.
    // Não usar no evento SSE `erro`: lá o `inicio` já persistiu a msg do usuário.
    const removerBolhasTemp = () =>
      setMensagens((prev) =>
        prev.filter((m) => m.id !== tmpAi && m.id !== tmpUser),
      );

    const onEvent = (evt: SSEEvent) => {
      const d = evt.data;
      switch (evt.event) {
        case "inicio":
          if (d.mensagem_user_id) {
            setMensagens((prev) =>
              prev.map((m) =>
                m.id === tmpUser ? { ...m, id: String(d.mensagem_user_id) } : m,
              ),
            );
          }
          break;
        case "chunk":
          if (typeof d.delta === "string") {
            setMensagens((prev) =>
              prev.map((m) =>
                m.id === tmpAi ? { ...m, conteudo: m.conteudo + d.delta } : m,
              ),
            );
          }
          break;
        case "concluido":
          setMensagens((prev) =>
            prev.map((m) =>
              m.id === tmpAi
                ? {
                    ...m,
                    id: d.mensagem_id ? String(d.mensagem_id) : m.id,
                    conteudo:
                      typeof d.conteudo === "string" ? d.conteudo : m.conteudo,
                    ai_log_id: d.ai_log_id ?? null,
                    is_rascunho: d.is_rascunho ?? true,
                    modelo: d.modelo ?? null,
                    provedor: d.provedor ?? null,
                    tokens_input: d.tokens_input ?? null,
                    tokens_output: d.tokens_output ?? null,
                    custo_estimado_brl: d.custo_estimado_brl ?? null,
                    citacoes: (d.citacoes as Record<string, unknown>) ?? null,
                    streaming: false,
                  }
                : m,
            ),
          );
          // 1ª mensagem: o backend auto-gera o título da sessão e o envia no
          // `concluido`. Reflete no cabeçalho (AISurface title) sem esperar reabrir.
          if (typeof d.titulo === "string" && d.titulo.trim()) {
            setSessaoAtual((s) => (s ? { ...s, titulo: d.titulo } : s));
          }
          break;
        case "erro":
          setErroChat(String(d.detail || "Falha ao gerar a resposta."));
          removerBolhaAi();
          break;
        default:
          break;
      }
    };

    try {
      await streamSSE(
        `/api/analise-caso-ia/sessoes/${sessao.id}/mensagem`,
        { conteudo, texto_colado: colado || null },
        { onEvent, signal: controller.signal },
      );
    } catch (e) {
      const err = e as { name?: string };
      if (err?.name === "AbortError") {
        // Cancelado pelo usuário: preserva o parcial já digitado.
        setMensagens((prev) =>
          prev.map((m) =>
            m.id === tmpAi ? { ...m, streaming: false, cancelada: true } : m,
          ),
        );
      } else if (e instanceof SSEHttpError && e.status === 403) {
        setErroChat("Seu perfil não tem acesso a esta análise ou caso.");
        removerBolhasTemp();
      } else if (e instanceof SSEHttpError && e.status === 429) {
        setErroChat("Muitas solicitações à IA. Aguarde alguns instantes.");
        removerBolhasTemp();
      } else {
        setErroChat(
          (e as { message?: string })?.message || "Falha ao conectar à IA.",
        );
        removerBolhasTemp();
      }
    } finally {
      setStreaming(false);
      abortRef.current = null;
      void carregarSessoes();
    }
  };

  const cancelar = () => abortRef.current?.abort();

  const anexarDocumento = async (file: File) => {
    const sessao = sessaoAtual;
    if (!sessao) return;
    setUploadBusy(true);
    setErroChat(null);
    const form = new FormData();
    form.append("file", file);
    try {
      const { data } = await api.post<MensagemOut>(
        `/analise-caso-ia/sessoes/${sessao.id}/documento`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      setMensagens((prev) => [...prev, { ...data }]);
      toast.success(
        "Documento anexado e lido (OCR). Já pode perguntar sobre ele.",
      );
      void carregarSessoes();
    } catch (e) {
      toast.error(
        detalheErro(
          e,
          "Não foi possível ler o documento (OCR vazio ou formato inválido).",
        ),
      );
    } finally {
      setUploadBusy(false);
    }
  };

  const onEscolherArquivo = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void anexarDocumento(file);
  };

  const salvarRenomear = async () => {
    if (!renomearAlvo) return;
    const titulo = renomearTitulo.trim();
    if (!titulo) return;
    try {
      const { data } = await api.patch<SessaoOut>(
        `/analise-caso-ia/sessoes/${renomearAlvo.id}`,
        { titulo },
      );
      setRenomearAlvo(null);
      setSessaoAtual((s) =>
        s && s.id === data.id ? { ...s, titulo: data.titulo } : s,
      );
      await carregarSessoes();
    } catch (e) {
      toast.error(detalheErro(e, "Não foi possível renomear a análise."));
    }
  };

  const alternarArquivar = async (s: SessaoResumo) => {
    try {
      await api.patch(`/analise-caso-ia/sessoes/${s.id}`, {
        arquivada: !s.arquivada,
      });
      if (sessaoAtual?.id === s.id) {
        setSessaoAtual(null);
        setMensagens([]);
      }
      await carregarSessoes();
    } catch (e) {
      toast.error(detalheErro(e, "Não foi possível arquivar a análise."));
    }
  };

  const confirmarApagar = async () => {
    if (!apagarAlvo) return;
    setApagando(true);
    try {
      await api.delete(`/analise-caso-ia/sessoes/${apagarAlvo.id}`);
      if (sessaoAtual?.id === apagarAlvo.id) {
        setSessaoAtual(null);
        setMensagens([]);
      }
      setApagarAlvo(null);
      await carregarSessoes();
    } catch (e) {
      toast.error(detalheErro(e, "Não foi possível apagar a análise."));
    } finally {
      setApagando(false);
    }
  };

  const onComposerKeyDown = (e: ReactKeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void enviar();
    }
  };

  const casoDaSessao = useMemo(
    () => casos.find((c) => c.id === sessaoAtual?.case_id) || null,
    [casos, sessaoAtual],
  );

  const abrirModalNova = () => {
    setNovoTitulo("");
    setNovaArea("");
    setNovoCaso("");
    setNovoNivel("alto");
    setModalNova(true);
  };

  return (
    <div className="space-y-4">
      <PageHeader
        eyebrow="Núcleo de IA jurídica"
        title="Análise de Caso IA"
        subtitle="Converse com a IA no papel de advogado sênior: importe documentos (OCR), cole o texto do caso ou vincule um caso existente. Toda resposta é rascunho — revisão humana obrigatória (OAB)."
        actions={
          <Button
            variant="ai"
            onClick={abrirModalNova}
            icon={<SquarePen className="h-4 w-4" />}
          >
            Nova análise
          </Button>
        }
      />

      <IANotice>
        A IA atua como assistente. Cada resposta nasce como rascunho sujeito a
        conferência do advogado responsável — nenhuma saída substitui a análise
        profissional.
      </IANotice>

      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        {/* ── ESQUERDA · lista de análises ─────────────────────────────── */}
        <SectionCard
          title="Suas análises"
          actions={
            <button
              type="button"
              onClick={() => setMostrarArquivadas((v) => !v)}
              className="text-xs font-medium text-ai-700 hover:text-ai-800 dark:text-ai-300"
            >
              {mostrarArquivadas ? "Ver ativas" : "Ver arquivadas"}
            </button>
          }
        >
          <Button
            variant="ai"
            className="mb-3 w-full"
            onClick={abrirModalNova}
            icon={<Plus className="h-4 w-4" />}
          >
            Nova análise
          </Button>

          {carregandoLista ? (
            <div className="py-8">
              <Spinner />
            </div>
          ) : erroLista ? (
            <ErrorState
              title="Falha ao carregar"
              message="Não foi possível listar suas análises."
              onRetry={() => void carregarSessoes()}
            />
          ) : sessoes.length === 0 ? (
            <EmptyState
              icon={Scale}
              title={
                mostrarArquivadas
                  ? "Nenhuma análise arquivada"
                  : "Nenhuma análise ainda"
              }
              message={
                mostrarArquivadas
                  ? "As análises que você arquivar aparecerão aqui."
                  : "Crie a primeira análise para conversar com a IA sobre um caso."
              }
            />
          ) : (
            <ul className="space-y-1">
              {sessoes.map((s) => {
                const ativa = sessaoAtual?.id === s.id;
                return (
                  <li
                    key={s.id}
                    className={cn(
                      "group flex items-center gap-1 rounded-lg border transition-colors",
                      ativa
                        ? "border-ai-200 bg-ai-50 dark:border-ai-500/30 dark:bg-ai-500/10"
                        : "border-transparent hover:bg-slate-50 dark:hover:bg-white/[0.04]",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => void abrirSessao(s.id)}
                      className="min-w-0 flex-1 px-2.5 py-2 text-left"
                    >
                      <div className="flex items-center gap-1.5">
                        <span className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">
                          {s.titulo}
                        </span>
                        {s.arquivada && (
                          <Archive className="h-3 w-3 shrink-0 text-slate-400" />
                        )}
                      </div>
                      <p className="mt-0.5 truncate text-xs text-slate-500">
                        {s.ultima_mensagem_preview || "Sem mensagens ainda"}
                      </p>
                      <p className="mt-0.5 text-[11px] text-slate-400">
                        {s.total_mensagens} msg ·{" "}
                        {fmtQuando(s.ultima_atividade)}
                      </p>
                    </button>
                    <div className="pr-1 opacity-60 transition-opacity group-hover:opacity-100">
                      <Dropdown label={<MoreVertical className="h-4 w-4" />}>
                        <button
                          type="button"
                          onClick={() => {
                            setRenomearAlvo(s);
                            setRenomearTitulo(s.titulo);
                          }}
                          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/[0.06]"
                        >
                          <Pencil className="h-3.5 w-3.5" /> Renomear
                        </button>
                        <button
                          type="button"
                          onClick={() => void alternarArquivar(s)}
                          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-white/[0.06]"
                        >
                          {s.arquivada ? (
                            <>
                              <ArchiveRestore className="h-3.5 w-3.5" />{" "}
                              Desarquivar
                            </>
                          ) : (
                            <>
                              <Archive className="h-3.5 w-3.5" /> Arquivar
                            </>
                          )}
                        </button>
                        <button
                          type="button"
                          onClick={() => setApagarAlvo(s)}
                          className="flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-sm text-danger-600 hover:bg-danger-50 dark:hover:bg-danger-500/10"
                        >
                          <Trash2 className="h-3.5 w-3.5" /> Apagar
                        </button>
                      </Dropdown>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </SectionCard>

        {/* ── DIREITA · thread do chat ─────────────────────────────────── */}
        <AISurface
          title={sessaoAtual ? sessaoAtual.titulo : "Análise de Caso IA"}
          subtitle="A IA responde como advogado sênior brasileiro. Rascunho sujeito a revisão humana obrigatória."
          actions={
            sessaoAtual ? (
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="purple">
                  Nível {NIVEL_LABEL[sessaoAtual.nivel]}
                </Badge>
                {sessaoAtual.area && (
                  <Badge tone="slate">{sessaoAtual.area}</Badge>
                )}
                {casoDaSessao && (
                  <Link
                    to={`/casos/${casoDaSessao.id}`}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-medium text-slate-600 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-200"
                  >
                    <Scale className="h-3 w-3" /> {casoDaSessao.titulo}
                  </Link>
                )}
              </div>
            ) : undefined
          }
        >
          <div className="flex h-[64vh] flex-col">
            {!sessaoAtual ? (
              <div className="flex flex-1 items-center justify-center">
                <EmptyState
                  icon={Bot}
                  title="Selecione ou crie uma análise"
                  message="Abra uma análise à esquerda ou clique em “Nova análise” para começar a conversar com a IA."
                  action={
                    <Button
                      variant="ai"
                      onClick={abrirModalNova}
                      icon={<SquarePen className="h-4 w-4" />}
                    >
                      Nova análise
                    </Button>
                  }
                />
              </div>
            ) : carregandoSessao ? (
              <div className="flex flex-1 items-center justify-center">
                <Spinner />
              </div>
            ) : (
              <>
                <AIFactualityLegend className="mb-3 shrink-0" />
                <div
                  ref={threadRef}
                  className="flex-1 space-y-4 overflow-y-auto pr-1"
                >
                  {mensagens.length === 0 ? (
                    <EmptyState
                      icon={Bot}
                      title="Comece a conversa"
                      message="Faça uma pergunta, anexe um documento ou cole o texto do caso para a IA analisar."
                    />
                  ) : (
                    mensagens.map((m) => <Bolha key={m.id} msg={m} />)
                  )}
                </div>

                {/* Composer */}
                <div className="mt-3 shrink-0 border-t border-slate-100 pt-3 dark:border-white/10">
                  {erroChat && (
                    <div className="mb-2 flex items-start justify-between gap-2 rounded-lg border border-danger-200 bg-danger-50 px-3 py-2 text-xs text-danger-700">
                      <span>{erroChat}</span>
                      <button
                        type="button"
                        onClick={() => setErroChat(null)}
                        aria-label="Fechar aviso"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}

                  {colarAberto && (
                    <div className="mb-2">
                      <Textarea
                        value={textoColado}
                        onChange={(e) => setTextoColado(e.target.value)}
                        rows={4}
                        placeholder="Cole aqui o texto do caso (será enviado como contexto na próxima mensagem, sem aparecer inteiro na bolha)."
                      />
                    </div>
                  )}
                  {!colarAberto && textoColado.trim() && (
                    <div className="mb-2 inline-flex items-center gap-2 rounded-full bg-ai-50 px-3 py-1 text-xs text-ai-700 dark:bg-ai-500/10 dark:text-ai-200">
                      <ClipboardPaste className="h-3.5 w-3.5" />
                      Texto colado anexado ({textoColado.trim().length} caract.)
                      <button
                        type="button"
                        onClick={() => setTextoColado("")}
                        aria-label="Remover texto colado"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  )}

                  <div className="flex items-end gap-2">
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => fileRef.current?.click()}
                        disabled={uploadBusy || streaming}
                        title="Anexar documento (OCR)"
                        className="flex h-9 w-9 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50 disabled:opacity-50 dark:border-white/10 dark:hover:bg-white/[0.06]"
                      >
                        {uploadBusy ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : (
                          <Paperclip className="h-4 w-4" />
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => setColarAberto((v) => !v)}
                        disabled={streaming}
                        title="Colar texto do caso"
                        className={cn(
                          "flex h-9 w-9 items-center justify-center rounded-lg border text-slate-500 hover:bg-slate-50 disabled:opacity-50 dark:hover:bg-white/[0.06]",
                          colarAberto
                            ? "border-ai-300 bg-ai-50 text-ai-700 dark:border-ai-500/40 dark:bg-ai-500/10"
                            : "border-slate-200 dark:border-white/10",
                        )}
                      >
                        <ClipboardPaste className="h-4 w-4" />
                      </button>
                      <input
                        ref={fileRef}
                        type="file"
                        accept={EXTENSOES_DOC}
                        className="hidden"
                        onChange={onEscolherArquivo}
                      />
                    </div>

                    <Textarea
                      value={input}
                      onChange={(e) => setInput(e.target.value)}
                      onKeyDown={onComposerKeyDown}
                      rows={2}
                      disabled={streaming}
                      placeholder="Pergunte ao advogado de IA (Enter envia, Shift+Enter quebra linha)…"
                      className="min-h-[2.5rem] flex-1"
                    />

                    {streaming ? (
                      <Button
                        variant="danger"
                        onClick={cancelar}
                        icon={<StopCircle className="h-4 w-4" />}
                      >
                        Parar
                      </Button>
                    ) : (
                      <Button
                        variant="ai"
                        onClick={() => void enviar()}
                        disabled={uploadBusy}
                        icon={<Send className="h-4 w-4" />}
                      >
                        Enviar
                      </Button>
                    )}
                  </div>
                </div>
              </>
            )}
          </div>
        </AISurface>
      </div>

      {/* ── Modal · Nova análise ──────────────────────────────────────── */}
      <Modal
        open={modalNova}
        onClose={() => setModalNova(false)}
        title="Nova análise de caso"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalNova(false)}>
              Cancelar
            </Button>
            <Button
              variant="ai"
              onClick={() => void criarSessao()}
              disabled={criando}
              icon={
                criando ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <SquarePen className="h-4 w-4" />
                )
              }
            >
              Criar e abrir
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              Título (opcional)
            </label>
            <input
              value={novoTitulo}
              onChange={(e) => setNovoTitulo(e.target.value)}
              className="input w-full"
              placeholder="Ex.: Rescisão indireta — Cliente X"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-600">
                Profundidade da IA
              </label>
              <select
                value={novoNivel}
                onChange={(e) => setNovoNivel(e.target.value as Nivel)}
                className="input w-full"
              >
                {NIVEIS.map((n) => (
                  <option key={n.value} value={n.value}>
                    {n.label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-medium text-slate-600">
                Área (opcional)
              </label>
              <input
                value={novaArea}
                onChange={(e) => setNovaArea(e.target.value)}
                className="input w-full"
                placeholder="Ex.: Trabalhista"
              />
            </div>
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-600">
              Vincular a um caso (opcional)
            </label>
            <select
              value={novoCaso}
              onChange={(e) => setNovoCaso(e.target.value)}
              className="input w-full"
            >
              <option value="">Sem vínculo — análise avulsa</option>
              {casos.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.titulo}
                  {c.numero_processo ? ` · ${c.numero_processo}` : ""}
                </option>
              ))}
            </select>
            <p className="mt-1 text-[11px] text-slate-400">
              Ao vincular, a IA recebe o contexto do dossiê do caso e o acesso é
              verificado conforme suas permissões.
            </p>
          </div>
        </div>
      </Modal>

      {/* ── Modal · Renomear ──────────────────────────────────────────── */}
      <Modal
        open={Boolean(renomearAlvo)}
        onClose={() => setRenomearAlvo(null)}
        title="Renomear análise"
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => setRenomearAlvo(null)}>
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={() => void salvarRenomear()}
              disabled={!renomearTitulo.trim()}
            >
              Salvar
            </Button>
          </>
        }
      >
        <input
          value={renomearTitulo}
          onChange={(e) => setRenomearTitulo(e.target.value)}
          className="input w-full"
          placeholder="Novo título"
          autoFocus
        />
      </Modal>

      {/* ── Confirmar apagar ──────────────────────────────────────────── */}
      <ConfirmModal
        open={Boolean(apagarAlvo)}
        onClose={() => setApagarAlvo(null)}
        onConfirm={() => void confirmarApagar()}
        title="Apagar análise"
        message={`A análise “${apagarAlvo?.titulo ?? ""}” e todas as suas mensagens serão removidas. Esta ação não pode ser desfeita.`}
        confirmLabel="Apagar"
        loading={apagando}
      />
    </div>
  );
}
