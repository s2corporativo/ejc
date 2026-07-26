/**
 * Sala Jurídica Conversacional (V1) — porta de entrada da IA no EJC.
 *
 * Layout em 3 colunas (validado em protótipo): sessões à esquerda, área de
 * trabalho livre + chat ao centro, estado jurídico consolidado à direita.
 * Toda IA passa pelo backend (/api/sala-juridica/*), que roda o núcleo único
 * (sanitização LGPD → RAG → AILog → HITL) — esta tela nunca chama modelo.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Archive,
  Copy,
  Download,
  FolderInput,
  Link2,
  Loader2,
  MessageSquareText,
  Paperclip,
  PenLine,
  Plus,
  RefreshCw,
  Scale,
  Send,
  Star,
  UploadCloud,
} from "lucide-react";
import api from "../lib/api";
import Markdown from "../components/Markdown";
import { useAuth } from "../stores/auth";
import { toast } from "../components/Toast";
import {
  AIFactualityLegend,
  Badge,
  Button,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Textarea,
  cn,
} from "../components/UI";

type Mensagem = {
  id: string;
  autor: "user" | "ia";
  modo: string;
  conteudo: string;
  modelo?: string | null;
  agente?: string | null;
  fontes: Array<{ titulo?: string; categoria?: string; fonte?: string }>;
  alertas: string[];
  custo_estimado?: number | null;
  estado_versao?: number | null;
  created_at?: string | null;
};

type Anexo = {
  id: string;
  nome_original: string;
  size_bytes: number;
  ocr_utilizado: boolean;
  tipo_documento?: string | null;
};

type Estado = {
  versao: number;
  resumo?: string | null;
  estado: Record<string, Array<Record<string, unknown>>>;
  origem?: string | null;
};

type Sessao = {
  id: string;
  titulo: string;
  status: string;
  favorita: boolean;
  cliente_potencial?: string | null;
  area_sugerida?: string | null;
  workspace_versao: number;
  convertido_case_id?: string | null;
  frozen: boolean;
  custo_ia_total: number;
  updated_at?: string | null;
  workspace_texto?: string | null;
  mensagens?: Mensagem[];
  anexos?: Anexo[];
  estado?: Estado | null;
};

const STATUS_LABEL: Record<string, string> = {
  em_analise: "Em análise",
  aguardando_documentos: "Aguardando docs",
  pronta_para_caso: "Pronta p/ caso",
  convertida_em_caso: "Convertida",
  arquivada: "Arquivada",
};

const MODOS: Array<{ valor: string; rotulo: string }> = [
  { valor: "conversa_livre", rotulo: "Conversa livre" },
  { valor: "organizar_fatos", rotulo: "Organizar fatos" },
  { valor: "analisar_provas", rotulo: "Analisar provas" },
  { valor: "detectar_contradicoes", rotulo: "Detectar contradições" },
  { valor: "estrategia_da_parte", rotulo: "Estratégia da parte" },
  { valor: "simular_defesa", rotulo: "Simular defesa" },
  { valor: "julgar_caso", rotulo: "Julgar o caso" },
  { valor: "pesquisar_direito", rotulo: "Pesquisar direito" },
  { valor: "elaborar_documento", rotulo: "Elaborar documento" },
  { valor: "revisar_documento", rotulo: "Revisar documento" },
];

// Ações rápidas: preenchem modo + comando prontos; o advogado revisa/edita o
// texto antes de enviar (nada dispara IA sem clique explícito em Enviar).
const ACOES_RAPIDAS: Array<{ rotulo: string; modo: string; comando: string }> =
  [
    {
      rotulo: "Analisar caso",
      modo: "organizar_fatos",
      comando:
        "Analise juridicamente este caso: identifique os fatos relevantes, os pontos controvertidos, a área do Direito e o procedimento aplicável.",
    },
    {
      rotulo: "Criar estratégia",
      modo: "estrategia_da_parte",
      comando:
        "Crie a estratégia para a parte que representamos: teses favoráveis e contrárias, fragilidades, provas faltantes e próximos passos.",
    },
    {
      rotulo: "Elaborar defesa",
      modo: "elaborar_documento",
      comando:
        "Elabore a contestação/defesa completa. Antes de redigir, confirme o que não estiver evidente (polo, objetivo, fase, prazo, juízo).",
    },
    {
      rotulo: "Criar petição",
      modo: "elaborar_documento",
      comando:
        "Transforme esta análise em uma petição completa, com endereçamento, qualificação, fatos, fundamentos, pedidos e valor da causa. Lacunas viram campos [A PREENCHER].",
    },
    {
      rotulo: "Revisar peça",
      modo: "revisar_documento",
      comando:
        "Revise tecnicamente a peça colada na área de trabalho: coerência, fatos, pedidos, fundamentação, competência, valores e contradições.",
    },
    {
      rotulo: "Resumir documentos",
      modo: "organizar_fatos",
      comando:
        "Resuma os documentos anexados, indicando partes, datas, valores, pedidos, prazos e o que está faltando.",
    },
    {
      rotulo: "Criar cronologia",
      modo: "organizar_fatos",
      comando:
        "Monte a cronologia dos fatos, distinguindo comprovado, alegado, inferido e controvertido.",
    },
    {
      rotulo: "Identificar riscos",
      modo: "detectar_contradicoes",
      comando:
        "Localize inconsistências, riscos e fragilidades do caso (processuais, probatórios e financeiros).",
    },
    {
      rotulo: "Listar provas",
      modo: "analisar_provas",
      comando:
        "Liste as provas disponíveis e as provas necessárias, relacionando cada fato à respectiva prova.",
    },
    {
      rotulo: "Pesquisar fundamentos",
      modo: "pesquisar_direito",
      comando:
        "Pesquise os fundamentos jurídicos aplicáveis (legislação e precedentes com fonte verificável).",
    },
    {
      rotulo: "Calcular valores",
      modo: "organizar_fatos",
      comando:
        "Calcule os pedidos e valores envolvidos, explicitando premissas, índices e o que depende de perícia ou confirmação.",
    },
    {
      rotulo: "Perguntas do caso",
      modo: "conversa_livre",
      comando:
        "Faça as perguntas necessárias para completar as informações do caso antes de qualquer peça.",
    },
  ];

const ABAS_ESTADO = [
  "fatos",
  "provas",
  "contradicoes",
  "teses",
  "riscos",
  "pendencias",
  "cronologia",
  "fontes",
] as const;

const CLASSIFICACAO_COR: Record<string, string> = {
  comprovado: "bg-emerald-100 text-emerald-800",
  alegado: "bg-amber-100 text-amber-800",
  inferido: "bg-sky-100 text-sky-800",
  controvertido: "bg-violet-100 text-violet-800",
  ausente: "bg-red-100 text-red-800",
  superado: "bg-gray-200 text-gray-500 line-through",
};

export default function SalaJuridica() {
  const { user } = useAuth();
  const [sessoes, setSessoes] = useState<Sessao[]>([]);
  const [ativa, setAtiva] = useState<Sessao | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [texto, setTexto] = useState("");
  const [modo, setModo] = useState("conversa_livre");
  const [workspace, setWorkspace] = useState("");
  const [abaEstado, setAbaEstado] =
    useState<(typeof ABAS_ESTADO)[number]>("fatos");
  const [busca, setBusca] = useState("");
  const [wizardAberto, setWizardAberto] = useState(false);
  const [convClienteBusca, setConvClienteBusca] = useState("");
  const [convClientes, setConvClientes] = useState<
    Array<{ id: string; nome?: string | null; razao_social?: string | null }>
  >([]);
  const [convClienteId, setConvClienteId] = useState<string | null>(null);
  const [convNovoCliente, setConvNovoCliente] = useState("");
  const [convArea, setConvArea] = useState("civil");
  const [convTitulo, setConvTitulo] = useState("");
  const [convConflito, setConvConflito] = useState(false);
  const [convRevisado, setConvRevisado] = useState(false);
  const [convertendo, setConvertendo] = useState(false);
  const [vincAberto, setVincAberto] = useState(false);
  const [vincBusca, setVincBusca] = useState("");
  const [vincCasos, setVincCasos] = useState<
    Array<{ id: string; titulo?: string; numero_interno?: string }>
  >([]);
  const [vincCaseId, setVincCaseId] = useState<string | null>(null);
  const [vincRevisado, setVincRevisado] = useState(false);
  const [vinculando, setVinculando] = useState(false);
  const [exportando, setExportando] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);
  const autosaveRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const carregarLista = useCallback(async () => {
    const { data } = await api.get<Sessao[]>("/sala-juridica");
    setSessoes(data);
    return data;
  }, []);

  const abrirSessao = useCallback(async (id: string) => {
    const { data } = await api.get<Sessao>(`/sala-juridica/${id}`);
    setAtiva(data);
    setWorkspace(data.workspace_texto ?? "");
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const lista = await carregarLista();
        if (lista.length > 0) await abrirSessao(lista[0].id);
      } catch {
        toast.error("Falha ao carregar a Sala Jurídica");
      } finally {
        setCarregando(false);
      }
    })();
  }, [carregarLista, abrirSessao, toast]);

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight });
  }, [ativa?.mensagens?.length]);

  const novaSessao = async () => {
    const { data } = await api.post<Sessao>("/sala-juridica", {
      titulo: `Nova análise — ${new Date().toLocaleDateString("pt-BR")}`,
    });
    await carregarLista();
    await abrirSessao(data.id);
  };

  // Autosave da área livre (debounce 1,2s) — nunca grava sessão congelada.
  const aoEditarWorkspace = (valor: string) => {
    setWorkspace(valor);
    if (!ativa || ativa.frozen) return;
    if (autosaveRef.current) clearTimeout(autosaveRef.current);
    autosaveRef.current = setTimeout(async () => {
      try {
        await api.patch(`/sala-juridica/${ativa.id}`, {
          workspace_texto: valor,
        });
      } catch {
        toast.error("Falha no salvamento automático");
      }
    }, 1200);
  };

  const enviar = async () => {
    if (!ativa || !texto.trim() || enviando) return;
    const conteudo = texto.trim();
    setTexto("");
    setEnviando(true);
    setAtiva((s) =>
      s
        ? {
            ...s,
            mensagens: [
              ...(s.mensagens ?? []),
              {
                id: `tmp-${Date.now()}`,
                autor: "user",
                modo,
                conteudo,
                fontes: [],
                alertas: [],
              },
            ],
          }
        : s,
    );
    try {
      await api.post(`/sala-juridica/${ativa.id}/mensagens`, {
        conteudo,
        modo,
      });
      await abrirSessao(ativa.id);
      await carregarLista();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Falha ao enviar a mensagem";
      toast.error(String(detail));
      setTexto(conteudo);
    } finally {
      setEnviando(false);
    }
  };

  const anexar = async (files: FileList | null) => {
    if (!ativa || !files?.length) return;
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    try {
      const { data } = await api.post(
        `/sala-juridica/${ativa.id}/anexos`,
        form,
        {
          headers: { "Content-Type": "multipart/form-data" },
        },
      );
      const anexados = (data?.anexados ?? []).length;
      toast.success(`${anexados} documento(s) anexado(s) e extraído(s)`);
      await abrirSessao(ativa.id);
    } catch {
      toast.error("Falha no upload dos documentos");
    }
  };

  const alternarFavorita = async (s: Sessao) => {
    await api.patch(`/sala-juridica/${s.id}`, { favorita: !s.favorita });
    await carregarLista();
  };

  const arquivar = async () => {
    if (!ativa) return;
    await api.post(`/sala-juridica/${ativa.id}/saida`, { acao: "arquivar" });
    toast.success("Análise arquivada");
    await carregarLista();
  };

  const abrirWizard = () => {
    if (!ativa) return;
    setConvTitulo(ativa.titulo);
    setConvNovoCliente(ativa.cliente_potencial ?? "");
    setConvClienteId(null);
    setConvConflito(false);
    setConvRevisado(false);
    setWizardAberto(true);
  };

  const buscarClientes = async (termo: string) => {
    setConvClienteBusca(termo);
    if (termo.trim().length < 2) {
      setConvClientes([]);
      return;
    }
    try {
      const { data } = await api.get("/clients", {
        params: { search: termo.trim(), page_size: 8 },
      });
      setConvClientes(data?.items ?? data ?? []);
    } catch {
      setConvClientes([]);
    }
  };

  const converterEmCaso = async () => {
    if (!ativa || convertendo) return;
    setConvertendo(true);
    try {
      const { data } = await api.post(`/sala-juridica/${ativa.id}/converter`, {
        client_id: convClienteId,
        novo_cliente_nome: convClienteId
          ? null
          : convNovoCliente.trim() || null,
        area: convArea,
        titulo_caso: convTitulo.trim(),
        advogado_responsavel_id: user?.id,
        confirmo_conflito_verificado: convConflito,
        confirmo_dados_revisados: convRevisado,
      });
      toast.success(
        data?.ja_convertido
          ? "Análise já estava convertida"
          : "Caso criado — análise congelada para auditoria",
      );
      setWizardAberto(false);
      await abrirSessao(ativa.id);
      await carregarLista();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Falha na conversão";
      toast.error(String(detail));
    } finally {
      setConvertendo(false);
    }
  };

  const exportarSessao = async (formato: "pdf" | "docx") => {
    if (!ativa || exportando) return;
    setExportando(true);
    try {
      const { data } = await api.get(`/sala-juridica/${ativa.id}/exportar`, {
        params: { formato },
        responseType: "blob",
      });
      const url = URL.createObjectURL(data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `sala-juridica-${ativa.id.slice(0, 8)}.${formato}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Falha na exportação");
    } finally {
      setExportando(false);
    }
  };

  const copiarMensagem = async (conteudo: string) => {
    await navigator.clipboard.writeText(conteudo);
    toast.success("Copiado");
  };

  // Leva o texto gerado para a área livre — de lá o advogado edita à vontade
  // (o autosave versiona a alteração como qualquer edição manual).
  const levarParaEditor = (conteudo: string) => {
    const novo = workspace.trim() ? `${workspace}\n\n${conteudo}` : conteudo;
    aoEditarWorkspace(novo);
    toast.success("Enviado para a área de trabalho");
  };

  const regenerar = async () => {
    if (!ativa || enviando) return;
    const ultima = [...(ativa.mensagens ?? [])]
      .reverse()
      .find((m) => m.autor === "user");
    if (!ultima) return;
    setModo(ultima.modo);
    setTexto(ultima.conteudo);
    toast.info("Comando recuperado — ajuste se quiser e clique em Enviar");
  };

  const buscarCasos = async (termo: string) => {
    setVincBusca(termo);
    if (termo.trim().length < 2) {
      setVincCasos([]);
      return;
    }
    try {
      const { data } = await api.get("/cases", {
        params: { search: termo.trim(), page_size: 10 },
      });
      setVincCasos(data?.items ?? data ?? []);
    } catch {
      setVincCasos([]);
    }
  };

  const vincularCaso = async () => {
    if (!ativa || !vincCaseId || vinculando) return;
    setVinculando(true);
    try {
      await api.post(`/sala-juridica/${ativa.id}/vincular-caso`, {
        case_id: vincCaseId,
        confirmo_dados_revisados: vincRevisado,
      });
      toast.success("Análise vinculada ao caso — congelada para auditoria");
      setVincAberto(false);
      await abrirSessao(ativa.id);
      await carregarLista();
    } catch (err: unknown) {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Falha ao vincular";
      toast.error(String(detail));
    } finally {
      setVinculando(false);
    }
  };

  const sessoesFiltradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return sessoes;
    return sessoes.filter(
      (s) =>
        s.titulo.toLowerCase().includes(q) ||
        (s.cliente_potencial ?? "").toLowerCase().includes(q),
    );
  }, [sessoes, busca]);

  const grupos = useMemo(() => {
    const ordem = [
      "em_analise",
      "aguardando_documentos",
      "pronta_para_caso",
      "convertida_em_caso",
      "arquivada",
    ];
    return ordem
      .map((st) => ({
        status: st,
        itens: sessoesFiltradas.filter((s) => s.status === st),
      }))
      .filter((g) => g.itens.length > 0);
  }, [sessoesFiltradas]);

  const estadoAtual = ativa?.estado?.estado ?? {};

  if (carregando) {
    return (
      <div className="flex h-64 items-center justify-center text-gray-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Carregando a Sala
        Jurídica…
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Sala Jurídica"
        subtitle="Converse livremente — o EJC estrutura fatos, provas e estratégia por trás da tela. Conteúdo de IA é rascunho sujeito a revisão humana (OAB)."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={!ativa || exportando}
              onClick={() => void exportarSessao("pdf")}
            >
              <Download className="h-4 w-4" /> PDF
            </Button>
            <Button
              variant="secondary"
              disabled={!ativa || exportando}
              onClick={() => void exportarSessao("docx")}
            >
              <Download className="h-4 w-4" /> DOCX
            </Button>
            <Button
              variant="secondary"
              onClick={arquivar}
              disabled={!ativa || ativa.frozen}
            >
              <Archive className="h-4 w-4" /> Arquivar
            </Button>
            <Button
              variant="secondary"
              disabled={!ativa || ativa.frozen}
              onClick={() => {
                setVincCaseId(null);
                setVincRevisado(false);
                setVincBusca("");
                setVincCasos([]);
                setVincAberto(true);
              }}
            >
              <Link2 className="h-4 w-4" /> Vincular a caso
            </Button>
            <Button
              variant="secondary"
              disabled={!ativa || ativa.frozen}
              onClick={abrirWizard}
            >
              <FolderInput className="h-4 w-4" /> Transformar em caso
            </Button>
            <Button onClick={novaSessao}>
              <Plus className="h-4 w-4" /> Nova análise
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 lg:grid-cols-[280px_1fr_320px]">
        {/* ── Coluna esquerda: sessões ─────────────────────────────────── */}
        <aside className="space-y-3">
          <Input
            placeholder="Pesquisar análises…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
          />
          {grupos.length === 0 && (
            <EmptyState
              icon={MessageSquareText}
              title="Nenhuma análise"
              message="Crie uma nova análise para começar."
            />
          )}
          {grupos.map((g) => (
            <div key={g.status}>
              <p className="mb-1 text-[11px] font-bold uppercase tracking-wide text-gray-500">
                {STATUS_LABEL[g.status]} · {g.itens.length}
              </p>
              {g.itens.map((s) => (
                <button
                  key={s.id}
                  onClick={() => abrirSessao(s.id)}
                  className={cn(
                    "mb-1 w-full rounded-lg border p-2 text-left text-sm transition",
                    ativa?.id === s.id
                      ? "border-primary-300 bg-primary-50"
                      : "border-gray-200 bg-white hover:border-gray-300",
                  )}
                >
                  <span className="flex items-start justify-between gap-1">
                    <span className="font-medium leading-tight">
                      {s.titulo}
                    </span>
                    <Star
                      className={cn(
                        "h-4 w-4 shrink-0",
                        s.favorita
                          ? "fill-amber-400 text-amber-400"
                          : "text-gray-300",
                      )}
                      onClick={(e) => {
                        e.stopPropagation();
                        void alternarFavorita(s);
                      }}
                    />
                  </span>
                  <span className="mt-1 flex flex-wrap gap-1">
                    <Badge tone="blue">{s.area_sugerida ?? "sem área"}</Badge>
                    {s.custo_ia_total > 0 && (
                      <Badge tone="slate">
                        R$ {s.custo_ia_total.toFixed(2)}
                      </Badge>
                    )}
                    {s.frozen && <Badge tone="amber">congelada</Badge>}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </aside>

        {/* ── Centro: área livre + chat ────────────────────────────────── */}
        <section className="flex min-h-[70vh] flex-col gap-3">
          {ativa ? (
            <>
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
                <div className="flex items-center justify-between border-b border-gray-100 px-3 py-2 text-xs text-gray-500">
                  <span className="font-semibold text-gray-700">
                    Área de trabalho livre
                  </span>
                  <span>
                    v{ativa.workspace_versao} · salvamento automático
                    {ativa.frozen && " · congelada (auditoria)"}
                  </span>
                </div>
                <Textarea
                  className="min-h-[160px] w-full resize-y border-0 focus:ring-0"
                  placeholder="Cole fatos, narrativas do cliente, rascunhos, trechos de peças…"
                  value={workspace}
                  disabled={ativa.frozen}
                  onChange={(e) => aoEditarWorkspace(e.target.value)}
                />
              </div>

              <div
                ref={chatRef}
                className="flex-1 space-y-3 overflow-y-auto rounded-xl border border-gray-200 bg-gray-50 p-3"
              >
                {(ativa.mensagens ?? []).length === 0 && (
                  <EmptyState
                    icon={MessageSquareText}
                    title="Comece a conversa"
                    message='Ex.: "Analise juridicamente este caso. Represento a ré."'
                  />
                )}
                {(ativa.mensagens ?? []).map((m) => (
                  <div
                    key={m.id}
                    className={cn(
                      "rounded-lg border p-3 text-sm",
                      m.autor === "user"
                        ? "border-blue-100 bg-blue-50"
                        : "border-gray-200 bg-white shadow-sm",
                    )}
                  >
                    <p className="mb-1 flex flex-wrap items-center gap-2 text-[11px] font-semibold text-gray-500">
                      {m.autor === "user"
                        ? (user?.full_name ?? "Você")
                        : "Sala Jurídica · IA"}
                      <Badge tone="blue">{m.modo.replace(/_/g, " ")}</Badge>
                      {m.autor === "ia" && m.modelo && (
                        <Badge tone="slate">{m.modelo}</Badge>
                      )}
                      {m.estado_versao != null && (
                        <Badge tone="green">estado v{m.estado_versao}</Badge>
                      )}
                    </p>
                    {m.autor === "ia" ? (
                      <Markdown source={m.conteudo} />
                    ) : (
                      <p className="whitespace-pre-wrap">{m.conteudo}</p>
                    )}
                    {m.autor === "ia" && m.fontes.length > 0 && (
                      <p className="mt-2 flex flex-wrap gap-1">
                        {m.fontes.map((f, i) => (
                          <Badge key={i} tone="amber">
                            {f.titulo ?? f.fonte ?? "fonte"}
                          </Badge>
                        ))}
                      </p>
                    )}
                    {m.autor === "ia" && m.alertas.length > 0 && (
                      <ul className="mt-2 list-disc pl-5 text-xs text-amber-700">
                        {m.alertas.map((a, i) => (
                          <li key={i}>{a}</li>
                        ))}
                      </ul>
                    )}
                    {m.autor === "ia" && (
                      <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                        <button
                          className="flex items-center gap-1 text-gray-500 hover:text-gray-800"
                          onClick={() => void copiarMensagem(m.conteudo)}
                        >
                          <Copy className="h-3 w-3" /> Copiar
                        </button>
                        <button
                          className="flex items-center gap-1 text-gray-500 hover:text-gray-800"
                          disabled={ativa.frozen}
                          onClick={() => levarParaEditor(m.conteudo)}
                        >
                          <PenLine className="h-3 w-3" /> Levar para o editor
                        </button>
                        <button
                          className="flex items-center gap-1 text-gray-500 hover:text-gray-800"
                          disabled={ativa.frozen || enviando}
                          onClick={() => void regenerar()}
                        >
                          <RefreshCw className="h-3 w-3" /> Regenerar
                        </button>
                      </div>
                    )}
                  </div>
                ))}
                {enviando && (
                  <p className="flex items-center gap-2 text-sm text-gray-500">
                    <Loader2 className="h-4 w-4 animate-spin" /> Analisando
                    (sanitização → RAG → validação → AILog)…
                  </p>
                )}
              </div>

              <div className="rounded-xl border border-gray-200 bg-white p-2 shadow-sm">
                <div className="mb-1 flex flex-wrap gap-1">
                  {ACOES_RAPIDAS.map((a) => (
                    <button
                      key={a.rotulo}
                      disabled={ativa.frozen || enviando}
                      onClick={() => {
                        setModo(a.modo);
                        setTexto(a.comando);
                      }}
                      className="rounded-full border border-primary-200 bg-primary-50 px-2 py-0.5 text-[11px] font-semibold text-primary-800 hover:bg-primary-100 disabled:opacity-50"
                      title={a.comando}
                    >
                      {a.rotulo}
                    </button>
                  ))}
                </div>
                <Textarea
                  className="min-h-[56px] w-full resize-none border-0 focus:ring-0"
                  placeholder="Converse livremente ou dê um comando jurídico…"
                  value={texto}
                  disabled={ativa.frozen || enviando}
                  onChange={(e) => setTexto(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      void enviar();
                    }
                  }}
                />
                <div className="mt-1 flex flex-wrap items-center gap-2">
                  <input
                    ref={fileRef}
                    type="file"
                    multiple
                    hidden
                    onChange={(e) => void anexar(e.target.files)}
                  />
                  <Button
                    variant="secondary"
                    disabled={ativa.frozen}
                    onClick={() => fileRef.current?.click()}
                  >
                    <Paperclip className="h-4 w-4" /> Anexar
                  </Button>
                  <Select
                    value={modo}
                    onChange={(e) => setModo(e.target.value)}
                    className="max-w-[220px]"
                  >
                    {MODOS.map((m) => (
                      <option key={m.valor} value={m.valor}>
                        {m.rotulo}
                      </option>
                    ))}
                  </Select>
                  <span className="ml-auto">
                    <Button
                      onClick={() => void enviar()}
                      disabled={ativa.frozen || enviando}
                    >
                      <Send className="h-4 w-4" /> Enviar
                    </Button>
                  </span>
                </div>
              </div>
              <AIFactualityLegend />
            </>
          ) : (
            <EmptyState
              icon={Scale}
              title="Selecione ou crie uma análise"
              message="A Sala Jurídica é a porta de entrada conversacional do EJC."
            />
          )}
        </section>

        {/* ── Direita: anexos + estado jurídico ────────────────────────── */}
        <aside className="space-y-3">
          <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
            <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <UploadCloud className="h-4 w-4" /> Documentos (
              {ativa?.anexos?.length ?? 0})
            </p>
            {(ativa?.anexos ?? []).map((a) => (
              <p
                key={a.id}
                className="mb-1 flex items-center justify-between text-xs"
              >
                <span className="truncate">{a.nome_original}</span>
                <Badge tone={a.ocr_utilizado ? "green" : "slate"}>
                  {a.ocr_utilizado ? "OCR" : "texto"}
                </Badge>
              </p>
            ))}
            {(ativa?.anexos ?? []).length === 0 && (
              <p className="text-xs text-gray-400">Nenhum documento anexado.</p>
            )}
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-3 shadow-sm">
            <p className="mb-2 text-sm font-semibold">
              Estado jurídico{" "}
              {ativa?.estado ? (
                <Badge tone="green">v{ativa.estado.versao}</Badge>
              ) : (
                <Badge tone="slate">vazio</Badge>
              )}
            </p>
            <div className="mb-2 flex flex-wrap gap-1">
              {ABAS_ESTADO.map((aba) => (
                <button
                  key={aba}
                  onClick={() => setAbaEstado(aba)}
                  className={cn(
                    "rounded px-2 py-0.5 text-[11px] font-semibold",
                    abaEstado === aba
                      ? "bg-primary-100 text-primary-800"
                      : "bg-gray-100 text-gray-500 hover:bg-gray-200",
                  )}
                >
                  {aba}
                </button>
              ))}
            </div>
            {(estadoAtual[abaEstado] ?? []).length === 0 ? (
              <p className="text-xs text-gray-400">
                Sem itens em “{abaEstado}”. A curadoria fina é do advogado
                (PATCH /estado); fontes acumulam automaticamente a cada
                resposta.
              </p>
            ) : (
              (estadoAtual[abaEstado] ?? []).map((item, i) => (
                <div
                  key={i}
                  className="mb-1 rounded border border-gray-100 p-2 text-xs"
                >
                  <span
                    className={cn(
                      "mr-1 rounded px-1.5 py-0.5 text-[10px] font-bold",
                      CLASSIFICACAO_COR[String(item.classificacao ?? "")] ??
                        "bg-gray-100 text-gray-600",
                    )}
                  >
                    {String(
                      item.classificacao ??
                        item.nivel ??
                        item.tipo ??
                        abaEstado,
                    )}
                  </span>
                  {String(
                    item.texto ??
                      item.descricao ??
                      item.nome ??
                      item.titulo ??
                      item.evento ??
                      "",
                  )}
                </div>
              ))
            )}
          </div>
        </aside>
      </div>

      {/* ── Modal: vincular a caso EXISTENTE ──────────────────────────── */}
      {vincAberto && ativa && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-lg rounded-xl bg-white p-5 shadow-xl">
            <h2 className="mb-1 text-lg font-bold text-primary-900">
              Vincular a caso existente
            </h2>
            <p className="mb-4 text-xs text-slate-500">
              A análise será congelada para auditoria e passa a integrar o
              histórico do caso selecionado (cliente herdado do caso).
            </p>
            <Input
              placeholder="Buscar caso por título ou número…"
              value={vincBusca}
              onChange={(e) => void buscarCasos(e.target.value)}
            />
            {vincCasos.length > 0 && (
              <div className="mt-1 max-h-56 overflow-y-auto rounded border border-slate-200">
                {vincCasos.map((c) => (
                  <button
                    key={c.id}
                    className={cn(
                      "block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50",
                      vincCaseId === c.id && "bg-primary-50 font-semibold",
                    )}
                    onClick={() => setVincCaseId(c.id)}
                  >
                    {c.numero_interno ? `${c.numero_interno} · ` : ""}
                    {c.titulo ?? c.id}
                  </button>
                ))}
              </div>
            )}
            <label className="mt-4 flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={vincRevisado}
                onChange={(e) => setVincRevisado(e.target.checked)}
              />
              Revisei fatos, provas e documentos desta análise antes do vínculo.
            </label>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="secondary" onClick={() => setVincAberto(false)}>
                Cancelar
              </Button>
              <Button
                disabled={vinculando || !vincCaseId || !vincRevisado}
                onClick={() => void vincularCaso()}
              >
                {vinculando ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Link2 className="h-4 w-4" />
                )}
                Confirmar vínculo
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ── Wizard de conversão em caso (conferência obrigatória) ─────── */}
      {wizardAberto && ativa && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
          <div className="max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl">
            <h2 className="mb-1 text-lg font-bold text-primary-900">
              Transformar em caso — conferência obrigatória
            </h2>
            <p className="mb-4 text-xs text-slate-500">
              Após a conversão, a análise é congelada para auditoria e o caso
              recebe cliente, documentos, estado probatório e histórico.
            </p>

            <p className="mb-1 text-xs font-bold uppercase text-slate-500">
              1 · Cliente
            </p>
            <Input
              placeholder="Buscar cliente por nome, CPF ou CNPJ…"
              value={convClienteBusca}
              onChange={(e) => void buscarClientes(e.target.value)}
            />
            {convClientes.length > 0 && (
              <div className="mt-1 rounded border border-slate-200">
                {convClientes.map((c) => (
                  <button
                    key={c.id}
                    className={cn(
                      "block w-full px-3 py-1.5 text-left text-sm hover:bg-slate-50",
                      convClienteId === c.id && "bg-primary-50 font-semibold",
                    )}
                    onClick={() => setConvClienteId(c.id)}
                  >
                    {c.nome ?? c.razao_social ?? c.id}
                  </button>
                ))}
              </div>
            )}
            <p className="my-2 text-center text-[11px] text-slate-400">
              — ou criar novo cliente —
            </p>
            <Input
              placeholder="Nome do novo cliente"
              value={convNovoCliente}
              disabled={convClienteId != null}
              onChange={(e) => setConvNovoCliente(e.target.value)}
            />
            {convClienteId != null && (
              <button
                className="mt-1 text-xs text-primary-700 underline"
                onClick={() => setConvClienteId(null)}
              >
                limpar seleção e criar novo cliente
              </button>
            )}

            <p className="mb-1 mt-4 text-xs font-bold uppercase text-slate-500">
              2 · Caso
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              <Input
                placeholder="Título do caso"
                value={convTitulo}
                onChange={(e) => setConvTitulo(e.target.value)}
              />
              <Select
                value={convArea}
                onChange={(e) => setConvArea(e.target.value)}
              >
                {[
                  "civil",
                  "trabalhista",
                  "consumidor",
                  "familia",
                  "ambiental",
                  "criminal",
                  "previdenciario",
                  "empresarial",
                  "tributario",
                  "administrativo",
                  "bancario",
                  "imobiliario",
                ].map((a) => (
                  <option key={a} value={a}>
                    {a}
                  </option>
                ))}
              </Select>
            </div>
            <p className="mt-1 text-xs text-slate-500">
              Responsável: {user?.full_name} (você)
            </p>

            <p className="mb-1 mt-4 text-xs font-bold uppercase text-slate-500">
              3 · Confirmações
            </p>
            <label className="mb-1 flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={convConflito}
                onChange={(e) => setConvConflito(e.target.checked)}
              />
              Verifiquei conflito de interesses e duplicidade de casos.
            </label>
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={convRevisado}
                onChange={(e) => setConvRevisado(e.target.checked)}
              />
              Revisei fatos, provas, pendências e documentos desta análise.
            </label>

            <div className="mt-5 flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => setWizardAberto(false)}
              >
                Cancelar
              </Button>
              <Button
                disabled={
                  convertendo ||
                  !convConflito ||
                  !convRevisado ||
                  !convTitulo.trim() ||
                  (convClienteId == null && !convNovoCliente.trim())
                }
                onClick={() => void converterEmCaso()}
              >
                {convertendo ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <FolderInput className="h-4 w-4" />
                )}
                Confirmar conversão
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
