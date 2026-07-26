import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Archive,
  Briefcase,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Copy,
  Download,
  FileSearch,
  FileText,
  FolderInput,
  Link2,
  Loader2,
  Menu,
  MessageCircle,
  MessageSquareText,
  Paperclip,
  PenLine,
  Plus,
  RefreshCw,
  Scale,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Star,
  UploadCloud,
  X,
} from "lucide-react";
import api from "../lib/api";
import { AREAS_FALLBACK } from "../lib/areaCatalog";
import Markdown from "../components/Markdown";
import { useAuth } from "../stores/auth";
import { toast } from "../components/Toast";
import {
  AIFactualityLegend,
  Badge,
  Button,
  EmptyState,
  Input,
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
  fontes?: Array<{ titulo?: string; fonte?: string }>;
  alertas?: string[];
  estado_versao?: number | null;
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

type TipoInicio = "livre" | "relato" | "documentos";
type AbaDireita = "visao" | "documentos" | "inteligencia";
type AbaEstado =
  | "fatos"
  | "provas"
  | "contradicoes"
  | "teses"
  | "riscos"
  | "pendencias"
  | "cronologia"
  | "fontes";

type AcaoRapida = {
  rotulo: string;
  modo: string;
  comando: string;
};

const STATUS_LABEL: Record<string, string> = {
  em_analise: "Em análise",
  aguardando_documentos: "Aguardando documentos",
  pronta_para_caso: "Pronta para caso",
  convertida_em_caso: "Convertida em caso",
  arquivada: "Arquivada",
};

const MODOS = [
  ["conversa_livre", "Conversa livre"],
  ["organizar_fatos", "Organizar fatos"],
  ["analisar_provas", "Analisar provas"],
  ["detectar_contradicoes", "Detectar contradições"],
  ["estrategia_da_parte", "Estratégia da parte"],
  ["simular_defesa", "Simular contraparte"],
  ["julgar_caso", "Visão do julgador"],
  ["pesquisar_direito", "Pesquisar direito"],
  ["elaborar_documento", "Elaborar documento"],
  ["revisar_documento", "Revisar documento"],
] as const;

const ACOES_RAPIDAS: AcaoRapida[] = [
  {
    rotulo: "Analisar caso",
    modo: "organizar_fatos",
    comando:
      "Analise juridicamente este caso. Identifique fatos relevantes, pontos controvertidos, área do Direito, competência, procedimento aplicável, riscos e informações que ainda precisam ser confirmadas.",
  },
  {
    rotulo: "Raio-X documental",
    modo: "analisar_provas",
    comando:
      "Faça um Raio-X técnico dos documentos anexados. Identifique partes, datas, valores, pedidos, decisões, prazos potenciais, fatos comprovados, alegações, contradições, riscos, documentos ausentes e próximos passos. Não invente dados e indique a origem de cada conclusão.",
  },
  {
    rotulo: "Criar estratégia",
    modo: "estrategia_da_parte",
    comando:
      "Crie a estratégia para a parte que representamos: tese principal, teses alternativas, fundamentos, provas indispensáveis, argumentos contrários prováveis, riscos e próximos passos.",
  },
  {
    rotulo: "Simular defesa",
    modo: "simular_defesa",
    comando:
      "Atue como advogado da parte contrária. Ataque os pontos frágeis, apresente preliminares e objeções prováveis e indique como devemos responder a cada uma.",
  },
  {
    rotulo: "Visão do juiz",
    modo: "julgar_caso",
    comando:
      "Analise o caso sob a perspectiva de um julgador: fatos controvertidos, distribuição do ônus da prova, questões processuais, fundamentos relevantes e cenários possíveis, sem prometer resultado.",
  },
  {
    rotulo: "Criar petição",
    modo: "elaborar_documento",
    comando:
      "Transforme a análise em uma minuta de petição completa. Antes de redigir, confirme polo, objetivo, fase, prazo e juízo quando não estiverem evidentes. Lacunas devem aparecer como [A PREENCHER].",
  },
  {
    rotulo: "Elaborar defesa",
    modo: "elaborar_documento",
    comando:
      "Elabore uma minuta completa de contestação ou defesa. Confirme previamente a posição processual, objetivo, fase, prazo e documentos essenciais. Não invente fatos nem fundamentos.",
  },
  {
    rotulo: "Revisar peça",
    modo: "revisar_documento",
    comando:
      "Revise tecnicamente a peça inserida na área de trabalho: coerência, fatos, competência, legitimidade, pedidos, fundamentação, valores, precedentes, contradições e possíveis resíduos de outro caso.",
  },
  {
    rotulo: "Criar cronologia",
    modo: "organizar_fatos",
    comando:
      "Monte a cronologia dos fatos e documentos. Diferencie comprovado, alegado, inferido, controvertido, ausente e superado.",
  },
  {
    rotulo: "Listar provas",
    modo: "analisar_provas",
    comando:
      "Liste as provas disponíveis e as provas necessárias. Relacione cada fato à respectiva prova, indique a força probatória aparente e destaque o que depende de perícia ou confirmação.",
  },
  {
    rotulo: "Identificar riscos",
    modo: "detectar_contradicoes",
    comando:
      "Localize inconsistências, riscos e fragilidades processuais, probatórias, materiais e financeiras. Classifique por gravidade e indique a medida de redução de risco.",
  },
  {
    rotulo: "Perguntas do caso",
    modo: "conversa_livre",
    comando:
      "Faça somente as perguntas necessárias para completar as informações do caso antes de qualquer conclusão ou elaboração de documento. Organize as perguntas por prioridade.",
  },
];

const ABAS_ESTADO: AbaEstado[] = [
  "fatos",
  "provas",
  "contradicoes",
  "teses",
  "riscos",
  "pendencias",
  "cronologia",
  "fontes",
];

const CLASSIFICACAO_COR: Record<string, string> = {
  comprovado: "bg-emerald-100 text-emerald-800",
  alegado: "bg-amber-100 text-amber-800",
  inferido: "bg-sky-100 text-sky-800",
  controvertido: "bg-violet-100 text-violet-800",
  ausente: "bg-red-100 text-red-800",
  superado: "bg-slate-200 text-slate-500 line-through",
  baixo: "bg-emerald-100 text-emerald-800",
  medio: "bg-amber-100 text-amber-800",
  moderado: "bg-amber-100 text-amber-800",
  alto: "bg-red-100 text-red-800",
  critico: "bg-red-100 text-red-800",
};

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());
}

function formatDate(value?: string | null) {
  if (!value) return "Sem atualização";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Sem atualização";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatMoney(value?: number | null) {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value || 0));
}

function getError(error: unknown, fallback: string) {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    ?.response?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

function getItemText(item: Record<string, unknown>) {
  return String(
    item.texto ??
      item.descricao ??
      item.nome ??
      item.titulo ??
      item.evento ??
      item.fato ??
      item.valor ??
      "",
  );
}

function Modal({
  children,
  onClose,
  wide = false,
}: {
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className={cn(
          "max-h-[90vh] w-full overflow-y-auto rounded-2xl border border-white/70 bg-white p-5 shadow-2xl",
          wide ? "max-w-3xl" : "max-w-xl",
        )}
      >
        {children}
      </div>
    </div>
  );
}

export default function SalaJuridicaWorkspace() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [sessoes, setSessoes] = useState<Sessao[]>([]);
  const [ativa, setAtiva] = useState<Sessao | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [anexando, setAnexando] = useState(false);
  const [texto, setTexto] = useState("");
  const [modo, setModo] = useState("conversa_livre");
  const [workspace, setWorkspace] = useState("");
  const [workspaceAberto, setWorkspaceAberto] = useState(true);
  const [abaDireita, setAbaDireita] = useState<AbaDireita>("visao");
  const [abaEstado, setAbaEstado] = useState<AbaEstado>("fatos");
  const [painelDireitoAberto, setPainelDireitoAberto] = useState(true);
  const [menuAberto, setMenuAberto] = useState(true);
  const [busca, setBusca] = useState("");
  const [limite, setLimite] = useState(50);
  const [modalNovo, setModalNovo] = useState(false);
  const [modalAcoes, setModalAcoes] = useState(false);
  const [exportando, setExportando] = useState(false);

  const [vincAberto, setVincAberto] = useState(false);
  const [vincBusca, setVincBusca] = useState("");
  const [vincCasos, setVincCasos] = useState<
    Array<{ id: string; titulo?: string; numero_interno?: string }>
  >([]);
  const [vincCaseId, setVincCaseId] = useState<string | null>(null);
  const [vincRevisado, setVincRevisado] = useState(false);
  const [vinculando, setVinculando] = useState(false);

  const [convAberto, setConvAberto] = useState(false);
  const [convBusca, setConvBusca] = useState("");
  const [convClientes, setConvClientes] = useState<
    Array<{ id: string; nome?: string | null; razao_social?: string | null }>
  >([]);
  const [convClienteId, setConvClienteId] = useState<string | null>(null);
  const [convNovoCliente, setConvNovoCliente] = useState("");
  const [convTitulo, setConvTitulo] = useState("");
  const [convArea, setConvArea] = useState("civil");
  const [convConflito, setConvConflito] = useState(false);
  const [convRevisado, setConvRevisado] = useState(false);
  const [convertendo, setConvertendo] = useState(false);

  const chatRef = useRef<HTMLDivElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const autosaveRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const autosavePendente = useRef<{ sessaoId: string; valor: string } | null>(
    null,
  );
  const buscaRef = useRef("");
  const limiteRef = useRef(50);
  const buscaInicial = useRef(true);

  const carregarLista = useCallback(async (q?: string, limit?: number) => {
    const termo = (q ?? buscaRef.current).trim().slice(0, 200);
    const pageSize = limit ?? limiteRef.current;
    const params: Record<string, string | number> = { limit: pageSize };
    if (termo) params.q = termo;
    const { data } = await api.get<Sessao[]>("/sala-juridica", { params });
    setSessoes(data);
    return data;
  }, []);

  const abrirSessao = useCallback(async (id: string) => {
    const { data } = await api.get<Sessao>(`/sala-juridica/${id}`);
    setAtiva(data);
    setWorkspace(data.workspace_texto ?? "");
    setMenuAberto(false);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const lista = await carregarLista();
        if (lista.length) await abrirSessao(lista[0].id);
      } catch {
        toast.error("Falha ao carregar a Sala Jurídica");
      } finally {
        setCarregando(false);
      }
    })();
  }, [abrirSessao, carregarLista]);

  useEffect(() => {
    chatRef.current?.scrollTo({
      top: chatRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [ativa?.mensagens?.length, enviando]);

  useEffect(() => {
    buscaRef.current = busca;
    if (buscaInicial.current) {
      buscaInicial.current = false;
      return;
    }
    const timer = setTimeout(() => {
      void carregarLista().catch(() =>
        toast.error("Falha ao pesquisar conversas"),
      );
    }, 400);
    return () => clearTimeout(timer);
  }, [busca, carregarLista]);

  useEffect(
    () => () => {
      if (autosaveRef.current) clearTimeout(autosaveRef.current);
    },
    [],
  );

  const criarSessao = async (tipo: TipoInicio) => {
    const data = new Date().toLocaleDateString("pt-BR");
    const config = {
      livre: {
        titulo: `Nova conversa — ${data}`,
        modo: "conversa_livre",
        comando: "",
        workspace: null,
      },
      relato: {
        titulo: `Triagem jurídica — ${data}`,
        modo: "organizar_fatos",
        comando:
          "Analise o relato inserido na área de trabalho. Organize os fatos, identifique urgência, área do Direito, competência possível, riscos, documentos necessários e faça as perguntas que faltam antes de concluir.",
        workspace:
          "RELATO DO CASO\n\nDescreva o que aconteceu, quando, quem está envolvido, valores, documentos disponíveis e o resultado esperado pelo cliente.\n",
      },
      documentos: {
        titulo: `Raio-X documental — ${data}`,
        modo: "analisar_provas",
        comando:
          "Faça um Raio-X técnico dos documentos anexados. Separe fatos comprovados, alegações, contradições, prazos potenciais, riscos, documentos faltantes e próximos passos.",
        workspace: null,
      },
    }[tipo];

    try {
      const response = await api.post<Sessao>("/sala-juridica", {
        titulo: config.titulo,
        workspace_texto: config.workspace,
      });
      setModalNovo(false);
      setModo(config.modo);
      setTexto(config.comando);
      await carregarLista();
      await abrirSessao(response.data.id);
      setWorkspaceAberto(tipo === "relato");
      if (tipo === "documentos") {
        setAbaDireita("documentos");
        setPainelDireitoAberto(true);
        setTimeout(() => fileRef.current?.click(), 150);
      }
    } catch (error) {
      toast.error(getError(error, "Falha ao criar nova conversa"));
    }
  };

  const salvarWorkspace = (valor: string) => {
    setWorkspace(valor);
    if (!ativa || ativa.frozen) return;
    autosavePendente.current = { sessaoId: ativa.id, valor };
    if (autosaveRef.current) clearTimeout(autosaveRef.current);
    autosaveRef.current = setTimeout(async () => {
      try {
        await api.patch(`/sala-juridica/${ativa.id}`, {
          workspace_texto: valor,
        });
        if (
          autosavePendente.current?.sessaoId === ativa.id &&
          autosavePendente.current.valor === valor
        ) {
          autosavePendente.current = null;
        }
      } catch {
        toast.error("Falha no salvamento automático");
      }
    }, 1200);
  };

  const descarregarAutosave = async () => {
    if (!ativa || ativa.frozen) return;
    const pendente = autosavePendente.current;
    if (!pendente || pendente.sessaoId !== ativa.id) return;
    if (autosaveRef.current) clearTimeout(autosaveRef.current);
    autosavePendente.current = null;
    await api.patch(`/sala-juridica/${ativa.id}`, {
      workspace_texto: pendente.valor,
    });
  };

  const enviar = async () => {
    if (!ativa || !texto.trim() || enviando || ativa.frozen) return;
    const conteudo = texto.trim();
    setTexto("");
    setEnviando(true);
    try {
      await descarregarAutosave();
      setAtiva((sessao) =>
        sessao
          ? {
              ...sessao,
              mensagens: [
                ...(sessao.mensagens ?? []),
                {
                  id: `tmp-${Date.now()}`,
                  autor: "user",
                  modo,
                  conteudo,
                },
              ],
            }
          : sessao,
      );
      await api.post(`/sala-juridica/${ativa.id}/mensagens`, {
        conteudo,
        modo,
      });
      await abrirSessao(ativa.id);
      await carregarLista();
    } catch (error) {
      setTexto(conteudo);
      toast.error(getError(error, "Falha ao enviar a mensagem"));
      await abrirSessao(ativa.id).catch(() => undefined);
    } finally {
      setEnviando(false);
    }
  };

  const anexar = async (files: FileList | null) => {
    if (!ativa || !files?.length || ativa.frozen) return;
    setAnexando(true);
    const form = new FormData();
    Array.from(files).forEach((file) => form.append("files", file));
    try {
      const response = await api.post(
        `/sala-juridica/${ativa.id}/anexos`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      const anexados = response.data?.anexados?.length ?? 0;
      const duplicados = response.data?.duplicados?.length ?? 0;
      const erros = response.data?.erros?.length ?? 0;
      toast.success(
        [
          `${anexados} anexado(s)`,
          duplicados ? `${duplicados} duplicado(s)` : "",
          erros ? `${erros} com erro` : "",
        ]
          .filter(Boolean)
          .join(" · "),
      );
      await abrirSessao(ativa.id);
      setAbaDireita("documentos");
      setPainelDireitoAberto(true);
    } catch (error) {
      toast.error(getError(error, "Falha no upload dos documentos"));
    } finally {
      setAnexando(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const alternarFavorita = async (sessao: Sessao) => {
    try {
      await api.patch(`/sala-juridica/${sessao.id}`, {
        favorita: !sessao.favorita,
      });
      await carregarLista();
      if (ativa?.id === sessao.id) {
        setAtiva((atual) =>
          atual ? { ...atual, favorita: !atual.favorita } : atual,
        );
      }
    } catch {
      toast.error("Falha ao atualizar favorito");
    }
  };

  const arquivar = async () => {
    if (!ativa || ativa.frozen) return;
    try {
      await api.post(`/sala-juridica/${ativa.id}/saida`, { acao: "arquivar" });
      toast.success("Conversa arquivada");
      const lista = await carregarLista();
      const proxima = lista.find((sessao) => sessao.id !== ativa.id);
      if (proxima) await abrirSessao(proxima.id);
      else setAtiva(null);
    } catch (error) {
      toast.error(getError(error, "Falha ao arquivar a conversa"));
    }
  };

  const exportar = async (formato: "pdf" | "docx") => {
    if (!ativa || exportando) return;
    setExportando(true);
    try {
      const response = await api.get(`/sala-juridica/${ativa.id}/exportar`, {
        params: { formato },
        responseType: "blob",
      });
      const url = URL.createObjectURL(response.data as Blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `sala-juridica-${ativa.id.slice(0, 8)}.${formato}`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Falha na exportação");
    } finally {
      setExportando(false);
    }
  };

  const buscarCasos = async (termo: string) => {
    setVincBusca(termo);
    if (termo.trim().length < 2) {
      setVincCasos([]);
      return;
    }
    try {
      const response = await api.get("/cases", {
        params: { search: termo.trim(), page_size: 10 },
      });
      const lista = response.data?.data ?? response.data?.items ?? response.data;
      setVincCasos(Array.isArray(lista) ? lista : []);
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
      toast.success("Conversa vinculada e congelada para auditoria");
      setVincAberto(false);
      await abrirSessao(ativa.id);
      await carregarLista();
    } catch (error) {
      toast.error(getError(error, "Falha ao vincular"));
    } finally {
      setVinculando(false);
    }
  };

  const abrirConversao = () => {
    if (!ativa) return;
    setConvTitulo(ativa.titulo);
    setConvNovoCliente(ativa.cliente_potencial ?? "");
    setConvClienteId(null);
    setConvBusca("");
    setConvClientes([]);
    setConvConflito(false);
    setConvRevisado(false);
    setConvAberto(true);
  };

  const buscarClientes = async (termo: string) => {
    setConvBusca(termo);
    if (termo.trim().length < 2) {
      setConvClientes([]);
      return;
    }
    try {
      const response = await api.get("/clients", {
        params: { search: termo.trim(), page_size: 8 },
      });
      const lista = response.data?.data ?? response.data?.items ?? response.data;
      setConvClientes(Array.isArray(lista) ? lista : []);
    } catch {
      setConvClientes([]);
    }
  };

  const converter = async () => {
    if (!ativa || convertendo || !user?.id) return;
    setConvertendo(true);
    try {
      const descricao =
        ativa.estado?.resumo || workspace.slice(0, 10000).trim() || null;
      const response = await api.post(`/sala-juridica/${ativa.id}/converter`, {
        client_id: convClienteId,
        novo_cliente_nome: convClienteId
          ? null
          : convNovoCliente.trim() || null,
        area: convArea,
        titulo_caso: convTitulo.trim(),
        descricao,
        advogado_responsavel_id: user.id,
        confirmo_conflito_verificado: convConflito,
        confirmo_dados_revisados: convRevisado,
      });
      toast.success(
        response.data?.ja_convertido
          ? "A conversa já estava convertida"
          : "Caso criado e conversa congelada para auditoria",
      );
      setConvAberto(false);
      await abrirSessao(ativa.id);
      await carregarLista();
      if (response.data?.case_id) navigate(`/casos/${response.data.case_id}`);
    } catch (error) {
      toast.error(getError(error, "Falha na conversão"));
    } finally {
      setConvertendo(false);
    }
  };

  const copiar = async (conteudo: string) => {
    try {
      await navigator.clipboard.writeText(conteudo);
      toast.success("Conteúdo copiado");
    } catch {
      toast.error("Não foi possível copiar");
    }
  };

  const levarAoEditor = (conteudo: string) => {
    salvarWorkspace(workspace.trim() ? `${workspace}\n\n${conteudo}` : conteudo);
    setWorkspaceAberto(true);
    toast.success("Conteúdo enviado para a área de trabalho");
  };

  const reutilizarComando = () => {
    const ultima = [...(ativa?.mensagens ?? [])]
      .reverse()
      .find((mensagem) => mensagem.autor === "user");
    if (!ultima) return;
    setModo(ultima.modo);
    setTexto(ultima.conteudo);
    toast.info("Comando recuperado para revisão");
  };

  const selecionarAcao = (acao: AcaoRapida) => {
    setModo(acao.modo);
    setTexto(acao.comando);
    setModalAcoes(false);
  };

  const sessoesFiltradas = useMemo(() => {
    const termo = busca.trim().toLowerCase();
    if (!termo) return sessoes;
    return sessoes.filter(
      (sessao) =>
        sessao.titulo.toLowerCase().includes(termo) ||
        (sessao.cliente_potencial ?? "").toLowerCase().includes(termo),
    );
  }, [busca, sessoes]);

  const grupos = useMemo(() => {
    const ordem = [
      "em_analise",
      "aguardando_documentos",
      "pronta_para_caso",
      "convertida_em_caso",
      "arquivada",
    ];
    return ordem
      .map((status) => ({
        status,
        itens: sessoesFiltradas.filter((sessao) => sessao.status === status),
      }))
      .filter((grupo) => grupo.itens.length);
  }, [sessoesFiltradas]);

  const estadoAtual = ativa?.estado?.estado ?? {};
  const totalEstado = ABAS_ESTADO.reduce(
    (total, aba) => total + (estadoAtual[aba]?.length ?? 0),
    0,
  );

  if (carregando) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center text-slate-500">
        <Loader2 className="mr-2 h-5 w-5 animate-spin" /> Abrindo a Sala
        Jurídica…
      </div>
    );
  }

  return (
    <div className="-mx-2 -mt-2 space-y-3 sm:-mx-3">
      <header className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              className="flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200 bg-slate-50 text-slate-600 xl:hidden"
              onClick={() => setMenuAberto(true)}
              aria-label="Abrir conversas"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-900 text-white">
              <Scale className="h-5 w-5" />
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h1 className="truncate text-lg font-bold text-slate-950">
                  Sala Jurídica
                </h1>
                <Badge tone="ai">
                  <Sparkles className="mr-1 h-3 w-3" /> Chat jurídico
                </Badge>
              </div>
              <p className="truncate text-xs text-slate-500">
                Pergunte, analise, escreva e revise livremente
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {ativa?.convertido_case_id && (
              <Button
                variant="secondary"
                size="sm"
                onClick={() => navigate(`/casos/${ativa.convertido_case_id}`)}
              >
                <Briefcase className="h-3.5 w-3.5" /> Abrir caso
              </Button>
            )}
            <Button
              variant="secondary"
              size="sm"
              disabled={!ativa || exportando}
              onClick={() => void exportar("docx")}
            >
              <Download className="h-3.5 w-3.5" /> DOCX
            </Button>
            <Button size="sm" onClick={() => setModalNovo(true)}>
              <Plus className="h-3.5 w-3.5" /> Nova conversa
            </Button>
            <button
              type="button"
              className="flex h-8 w-8 items-center justify-center rounded-lg border border-slate-200 text-slate-500 hover:bg-slate-50"
              onClick={() => setPainelDireitoAberto((value) => !value)}
              aria-label="Alternar painel lateral"
            >
              {painelDireitoAberto ? (
                <ChevronRight className="h-4 w-4" />
              ) : (
                <ChevronLeft className="h-4 w-4" />
              )}
            </button>
          </div>
        </div>
      </header>

      <div
        className={cn(
          "grid min-h-[calc(100vh-170px)] gap-3",
          painelDireitoAberto
            ? "xl:grid-cols-[300px_minmax(0,1fr)_340px]"
            : "xl:grid-cols-[300px_minmax(0,1fr)]",
        )}
      >
        <aside
          className={cn(
            "fixed inset-y-0 left-0 z-40 w-[88vw] max-w-[320px] overflow-y-auto border-r border-slate-200 bg-white p-3 shadow-2xl transition-transform xl:static xl:z-auto xl:w-auto xl:max-w-none xl:translate-x-0 xl:rounded-2xl xl:border xl:shadow-sm",
            menuAberto ? "translate-x-0" : "-translate-x-full",
          )}
        >
          <div className="mb-3 flex items-center justify-between xl:hidden">
            <p className="text-sm font-semibold text-slate-900">Conversas</p>
            <button
              type="button"
              className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
              onClick={() => setMenuAberto(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <Button className="mb-3 w-full" onClick={() => setModalNovo(true)}>
            <Plus className="h-4 w-4" /> Iniciar trabalho jurídico
          </Button>

          <div className="relative mb-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <Input
              value={busca}
              onChange={(event) => setBusca(event.target.value)}
              placeholder="Pesquisar conversas…"
              className="pl-9"
            />
          </div>

          <div className="space-y-4">
            {!grupos.length && (
              <EmptyState
                icon={MessageSquareText}
                title="Nenhuma conversa"
                message="Inicie um trabalho jurídico para começar."
              />
            )}
            {grupos.map((grupo) => (
              <div key={grupo.status}>
                <div className="mb-1.5 flex items-center justify-between px-1">
                  <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                    {STATUS_LABEL[grupo.status] ?? humanize(grupo.status)}
                  </p>
                  <span className="text-[10px] text-slate-400">
                    {grupo.itens.length}
                  </span>
                </div>
                <div className="space-y-1.5">
                  {grupo.itens.map((sessao) => (
                    <button
                      key={sessao.id}
                      type="button"
                      onClick={() => void abrirSessao(sessao.id)}
                      className={cn(
                        "group w-full rounded-xl border p-3 text-left transition",
                        ativa?.id === sessao.id
                          ? "border-primary-200 bg-primary-50"
                          : "border-transparent bg-slate-50 hover:border-slate-200 hover:bg-white",
                      )}
                    >
                      <span className="flex items-start justify-between gap-2">
                        <span className="line-clamp-2 text-sm font-semibold text-slate-800">
                          {sessao.titulo}
                        </span>
                        <Star
                          className={cn(
                            "h-4 w-4 shrink-0",
                            sessao.favorita
                              ? "fill-amber-400 text-amber-400"
                              : "text-slate-300",
                          )}
                          onClick={(event) => {
                            event.stopPropagation();
                            void alternarFavorita(sessao);
                          }}
                        />
                      </span>
                      <span className="mt-2 flex flex-wrap gap-1">
                        <Badge tone="blue">
                          {sessao.area_sugerida ?? "Área aberta"}
                        </Badge>
                        {sessao.frozen && <Badge tone="amber">Auditada</Badge>}
                      </span>
                      <span className="mt-2 block text-[10px] text-slate-400">
                        {formatDate(sessao.updated_at)}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            ))}

            {sessoes.length >= limite && limite < 200 && (
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => {
                  const novo = Math.min(limite + 50, 200);
                  setLimite(novo);
                  limiteRef.current = novo;
                  void carregarLista(undefined, novo);
                }}
              >
                Carregar mais
              </Button>
            )}
          </div>
        </aside>

        <main className="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
          {ativa ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="truncate text-sm font-bold text-slate-950">
                      {ativa.titulo}
                    </h2>
                    <Badge tone={ativa.frozen ? "amber" : "green"}>
                      {ativa.frozen ? "Somente leitura" : "Em trabalho"}
                    </Badge>
                  </div>
                  <p className="mt-0.5 text-[11px] text-slate-400">
                    {ativa.cliente_potencial
                      ? `Cliente potencial: ${ativa.cliente_potencial}`
                      : "Conversa jurídica livre"}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
                    disabled={ativa.frozen}
                    onClick={() => {
                      setVincCaseId(null);
                      setVincBusca("");
                      setVincCasos([]);
                      setVincRevisado(false);
                      setVincAberto(true);
                    }}
                    title="Vincular a caso"
                  >
                    <Link2 className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
                    disabled={ativa.frozen}
                    onClick={abrirConversao}
                    title="Transformar em caso"
                  >
                    <FolderInput className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 disabled:opacity-40"
                    disabled={ativa.frozen}
                    onClick={() => void arquivar()}
                    title="Arquivar"
                  >
                    <Archive className="h-4 w-4" />
                  </button>
                </div>
              </div>

              <section className="border-b border-slate-100 bg-slate-50/50">
                <button
                  type="button"
                  className="flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left"
                  onClick={() => setWorkspaceAberto((value) => !value)}
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <PenLine className="h-4 w-4 text-primary-600" />
                    <span className="text-xs font-semibold text-slate-700">
                      Área de trabalho
                    </span>
                    <span className="truncate text-[10px] text-slate-400">
                      fatos, notas e rascunhos
                    </span>
                  </span>
                  <span className="flex items-center gap-2 text-[10px] text-slate-400">
                    v{ativa.workspace_versao} · autosave
                    <ChevronDown
                      className={cn(
                        "h-3.5 w-3.5 transition",
                        workspaceAberto && "rotate-180",
                      )}
                    />
                  </span>
                </button>
                {workspaceAberto && (
                  <Textarea
                    value={workspace}
                    disabled={ativa.frozen}
                    onChange={(event) => salvarWorkspace(event.target.value)}
                    placeholder="Cole fatos, narrativa do cliente, trechos de peças ou notas de trabalho…"
                    className="min-h-[150px] w-full resize-y rounded-none border-x-0 border-b-0 border-t border-slate-100 bg-white px-4 py-3 font-mono text-[13px] leading-6 focus:ring-0"
                  />
                )}
              </section>

              <div
                ref={chatRef}
                className="min-h-[320px] flex-1 space-y-5 overflow-y-auto bg-gradient-to-b from-white to-slate-50/60 px-4 py-5 sm:px-6"
              >
                {!ativa.mensagens?.length && (
                  <div className="mx-auto max-w-2xl py-10 text-center">
                    <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary-900 text-white">
                      <Scale className="h-7 w-7" />
                    </div>
                    <h3 className="mt-4 text-lg font-bold text-slate-950">
                      Como posso ajudar neste trabalho jurídico?
                    </h3>
                    <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-slate-500">
                      Faça qualquer pergunta ou requisição. A Sala utiliza a área
                      de trabalho e os documentos anexados como contexto.
                    </p>
                    <div className="mt-5 flex flex-wrap justify-center gap-2">
                      {ACOES_RAPIDAS.slice(0, 4).map((acao) => (
                        <button
                          key={acao.rotulo}
                          type="button"
                          className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:border-primary-200 hover:bg-primary-50 hover:text-primary-800"
                          onClick={() => selecionarAcao(acao)}
                        >
                          {acao.rotulo}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {(ativa.mensagens ?? []).map((mensagem) => (
                  <article
                    key={mensagem.id}
                    className={cn(
                      "flex gap-3",
                      mensagem.autor === "user" && "justify-end",
                    )}
                  >
                    {mensagem.autor === "ia" && (
                      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary-900 text-white">
                        <Scale className="h-4 w-4" />
                      </div>
                    )}
                    <div
                      className={cn(
                        "min-w-0 max-w-[92%] rounded-2xl border px-4 py-3 text-sm sm:max-w-[85%]",
                        mensagem.autor === "user"
                          ? "rounded-br-md border-primary-200 bg-primary-50"
                          : "rounded-bl-md border-slate-200 bg-white shadow-sm",
                      )}
                    >
                      <div className="mb-2 flex flex-wrap items-center gap-1.5 text-[10px] font-semibold text-slate-400">
                        <span>
                          {mensagem.autor === "user"
                            ? user?.full_name ?? "Você"
                            : "Sala Jurídica"}
                        </span>
                        <Badge tone={mensagem.autor === "ia" ? "ai" : "blue"}>
                          {MODOS.find(([value]) => value === mensagem.modo)?.[1] ??
                            humanize(mensagem.modo)}
                        </Badge>
                        {mensagem.modelo && <Badge tone="slate">{mensagem.modelo}</Badge>}
                        {mensagem.estado_versao != null && (
                          <Badge tone="green">v{mensagem.estado_versao}</Badge>
                        )}
                      </div>
                      {mensagem.autor === "ia" ? (
                        <Markdown source={mensagem.conteudo} />
                      ) : (
                        <p className="whitespace-pre-wrap leading-6">
                          {mensagem.conteudo}
                        </p>
                      )}

                      {!!mensagem.fontes?.length && (
                        <div className="mt-3 flex flex-wrap gap-1 border-t border-slate-100 pt-3">
                          {mensagem.fontes.map((fonte, index) => (
                            <Badge key={index} tone="amber">
                              {fonte.titulo ?? fonte.fonte ?? "Fonte"}
                            </Badge>
                          ))}
                        </div>
                      )}

                      {!!mensagem.alertas?.length && (
                        <ul className="mt-3 rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                          {mensagem.alertas.map((alerta, index) => (
                            <li key={index}>• {alerta}</li>
                          ))}
                        </ul>
                      )}

                      {mensagem.autor === "ia" && (
                        <div className="mt-3 flex flex-wrap gap-3 border-t border-slate-100 pt-2 text-[11px]">
                          <button
                            type="button"
                            className="flex items-center gap-1 text-slate-500 hover:text-slate-900"
                            onClick={() => void copiar(mensagem.conteudo)}
                          >
                            <Copy className="h-3 w-3" /> Copiar
                          </button>
                          <button
                            type="button"
                            className="flex items-center gap-1 text-slate-500 hover:text-slate-900 disabled:opacity-40"
                            disabled={ativa.frozen}
                            onClick={() => levarAoEditor(mensagem.conteudo)}
                          >
                            <PenLine className="h-3 w-3" /> Levar ao editor
                          </button>
                          <button
                            type="button"
                            className="flex items-center gap-1 text-slate-500 hover:text-slate-900 disabled:opacity-40"
                            disabled={ativa.frozen || enviando}
                            onClick={reutilizarComando}
                          >
                            <RefreshCw className="h-3 w-3" /> Reutilizar comando
                          </button>
                        </div>
                      )}
                    </div>
                  </article>
                ))}

                {enviando && (
                  <div className="flex gap-3">
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-primary-900 text-white">
                      <Scale className="h-4 w-4" />
                    </div>
                    <div className="rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-3 text-sm text-slate-500 shadow-sm">
                      <span className="flex items-center gap-2">
                        <Loader2 className="h-4 w-4 animate-spin" /> Analisando com
                        LGPD, RAG e validação…
                      </span>
                    </div>
                  </div>
                )}
              </div>

              <section className="border-t border-slate-200 bg-white p-3 sm:p-4">
                <div className="mb-2 flex flex-wrap gap-1.5">
                  {ACOES_RAPIDAS.slice(0, 5).map((acao) => (
                    <button
                      key={acao.rotulo}
                      type="button"
                      disabled={ativa.frozen || enviando}
                      onClick={() => selecionarAcao(acao)}
                      className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-[11px] font-semibold text-slate-600 hover:border-primary-200 hover:bg-primary-50 hover:text-primary-800 disabled:opacity-40"
                    >
                      {acao.rotulo}
                    </button>
                  ))}
                  <button
                    type="button"
                    disabled={ativa.frozen || enviando}
                    onClick={() => setModalAcoes(true)}
                    className="rounded-full border border-dashed border-slate-300 px-2.5 py-1 text-[11px] font-semibold text-slate-500 hover:border-primary-300 hover:text-primary-700 disabled:opacity-40"
                  >
                    Mais comandos
                  </button>
                </div>

                <div className="rounded-2xl border border-slate-200 bg-white shadow-sm focus-within:border-primary-300 focus-within:ring-2 focus-within:ring-primary-100">
                  <textarea
                    value={texto}
                    disabled={ativa.frozen || enviando}
                    onChange={(event) => setTexto(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" && !event.shiftKey) {
                        event.preventDefault();
                        void enviar();
                      }
                    }}
                    placeholder="Pergunte ou dê qualquer comando jurídico…"
                    className="min-h-[76px] w-full resize-none rounded-t-2xl border-0 bg-transparent px-4 py-3 text-sm leading-6 outline-none placeholder:text-slate-400"
                  />
                  <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 px-2 py-2">
                    <input
                      ref={fileRef}
                      type="file"
                      multiple
                      hidden
                      onChange={(event) => void anexar(event.target.files)}
                    />
                    <button
                      type="button"
                      disabled={ativa.frozen || anexando}
                      onClick={() => fileRef.current?.click()}
                      className="flex h-8 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold text-slate-500 hover:bg-slate-100 hover:text-slate-800 disabled:opacity-40"
                    >
                      {anexando ? (
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      ) : (
                        <Paperclip className="h-3.5 w-3.5" />
                      )}
                      Anexar
                    </button>
                    <Select
                      value={modo}
                      onChange={(event) => setModo(event.target.value)}
                      className="h-8 min-w-[190px] border-0 bg-slate-50 py-0 text-xs font-semibold focus:ring-0"
                    >
                      {MODOS.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </Select>
                    <Button
                      className="ml-auto"
                      disabled={ativa.frozen || enviando || !texto.trim()}
                      onClick={() => void enviar()}
                    >
                      {enviando ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                      Enviar
                    </Button>
                  </div>
                </div>
                <div className="mt-2">
                  <AIFactualityLegend />
                </div>
              </section>
            </>
          ) : (
            <div className="flex min-h-[650px] items-center justify-center p-6">
              <div className="max-w-2xl text-center">
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-primary-900 text-white">
                  <Scale className="h-8 w-8" />
                </div>
                <h2 className="mt-5 text-2xl font-bold text-slate-950">
                  Inicie um trabalho jurídico
                </h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  A Sala funciona como um chat completo. Os atalhos apenas
                  organizam o ponto de partida e não limitam a conversa.
                </p>
                <Button className="mt-5" onClick={() => setModalNovo(true)}>
                  <Plus className="h-4 w-4" /> Escolher início
                </Button>
              </div>
            </div>
          )}
        </main>

        {painelDireitoAberto && (
          <aside className="overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="grid grid-cols-3 border-b border-slate-100 bg-slate-50 p-1">
              {([
                ["visao", "Visão", ShieldCheck],
                ["documentos", "Arquivos", FileText],
                ["inteligencia", "Inteligência", Sparkles],
              ] as const).map(([value, label, Icon]) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setAbaDireita(value)}
                  className={cn(
                    "flex h-9 items-center justify-center gap-1.5 rounded-lg text-[11px] font-semibold",
                    abaDireita === value
                      ? "bg-white text-primary-900 shadow-sm"
                      : "text-slate-500 hover:bg-white/70",
                  )}
                >
                  <Icon className="h-3.5 w-3.5" /> {label}
                </button>
              ))}
            </div>

            <div className="max-h-[calc(100vh-220px)] overflow-y-auto p-4">
              {!ativa ? (
                <EmptyState
                  icon={Scale}
                  title="Sem conversa ativa"
                  message="Selecione ou inicie uma conversa."
                />
              ) : abaDireita === "visao" ? (
                <div className="space-y-4">
                  <div className="rounded-xl border border-slate-200 bg-slate-50 p-3">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="text-[10px] font-bold uppercase tracking-wide text-slate-400">
                          Situação
                        </p>
                        <p className="mt-1 text-sm font-bold text-slate-900">
                          {STATUS_LABEL[ativa.status] ?? humanize(ativa.status)}
                        </p>
                      </div>
                      <Badge tone={ativa.frozen ? "amber" : "green"}>
                        {ativa.frozen ? "Auditada" : "Editável"}
                      </Badge>
                    </div>
                    <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                      <div className="rounded-lg bg-white p-2">
                        <p className="text-[10px] text-slate-400">Mensagens</p>
                        <p className="font-bold">{ativa.mensagens?.length ?? 0}</p>
                      </div>
                      <div className="rounded-lg bg-white p-2">
                        <p className="text-[10px] text-slate-400">Documentos</p>
                        <p className="font-bold">{ativa.anexos?.length ?? 0}</p>
                      </div>
                      <div className="rounded-lg bg-white p-2">
                        <p className="text-[10px] text-slate-400">Itens jurídicos</p>
                        <p className="font-bold">{totalEstado}</p>
                      </div>
                      <div className="rounded-lg bg-white p-2">
                        <p className="text-[10px] text-slate-400">Custo IA</p>
                        <p className="font-bold">{formatMoney(ativa.custo_ia_total)}</p>
                      </div>
                    </div>
                  </div>

                  {ativa.estado?.resumo && (
                    <div className="rounded-xl border border-primary-100 bg-primary-50 p-3">
                      <p className="text-[10px] font-bold uppercase tracking-wide text-primary-700">
                        Síntese consolidada
                      </p>
                      <p className="mt-2 text-xs leading-5 text-slate-700">
                        {ativa.estado.resumo}
                      </p>
                    </div>
                  )}

                  <div className="space-y-2">
                    <Button
                      variant="secondary"
                      className="w-full justify-start"
                      disabled={ativa.frozen}
                      onClick={() => {
                        setVincCaseId(null);
                        setVincBusca("");
                        setVincCasos([]);
                        setVincRevisado(false);
                        setVincAberto(true);
                      }}
                    >
                      <Link2 className="h-4 w-4" /> Vincular a caso
                    </Button>
                    <Button
                      className="w-full justify-start"
                      disabled={ativa.frozen}
                      onClick={abrirConversao}
                    >
                      <FolderInput className="h-4 w-4" /> Transformar em caso
                    </Button>
                    <div className="grid grid-cols-2 gap-2">
                      <Button
                        variant="secondary"
                        disabled={exportando}
                        onClick={() => void exportar("pdf")}
                      >
                        PDF
                      </Button>
                      <Button
                        variant="secondary"
                        disabled={exportando}
                        onClick={() => void exportar("docx")}
                      >
                        DOCX
                      </Button>
                    </div>
                  </div>
                </div>
              ) : abaDireita === "documentos" ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-bold text-slate-900">
                        Documentos
                      </p>
                      <p className="text-[11px] text-slate-400">
                        OCR e extração automática
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={ativa.frozen || anexando}
                      onClick={() => fileRef.current?.click()}
                      className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary-900 text-white disabled:opacity-40"
                    >
                      {anexando ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <UploadCloud className="h-4 w-4" />
                      )}
                    </button>
                  </div>

                  {!ativa.anexos?.length ? (
                    <button
                      type="button"
                      disabled={ativa.frozen}
                      onClick={() => fileRef.current?.click()}
                      className="w-full rounded-xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center hover:border-primary-300 hover:bg-primary-50 disabled:opacity-40"
                    >
                      <UploadCloud className="mx-auto h-7 w-7 text-slate-400" />
                      <span className="mt-2 block text-xs font-semibold text-slate-600">
                        Anexar documentos
                      </span>
                    </button>
                  ) : (
                    <div className="space-y-2">
                      {ativa.anexos.map((anexo) => (
                        <div
                          key={anexo.id}
                          className="rounded-xl border border-slate-200 p-3"
                        >
                          <div className="flex gap-2">
                            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100">
                              <FileText className="h-4 w-4 text-slate-500" />
                            </div>
                            <div className="min-w-0">
                              <p className="truncate text-xs font-semibold text-slate-800">
                                {anexo.nome_original}
                              </p>
                              <div className="mt-1 flex flex-wrap gap-1">
                                <Badge tone={anexo.ocr_utilizado ? "green" : "slate"}>
                                  {anexo.ocr_utilizado ? "OCR" : "Texto"}
                                </Badge>
                                {anexo.tipo_documento && (
                                  <Badge tone="blue">
                                    {humanize(anexo.tipo_documento)}
                                  </Badge>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {!!ativa.anexos?.length && !ativa.frozen && (
                    <Button
                      variant="secondary"
                      className="w-full"
                      onClick={() => selecionarAcao(ACOES_RAPIDAS[1])}
                    >
                      <FileSearch className="h-4 w-4" /> Preparar Raio-X
                    </Button>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-bold text-slate-900">
                        Estado jurídico
                      </p>
                      <p className="text-[11px] text-slate-400">
                        Estrutura consolidada e versionada
                      </p>
                    </div>
                    <Badge tone={ativa.estado ? "green" : "slate"}>
                      {ativa.estado ? `v${ativa.estado.versao}` : "Vazio"}
                    </Badge>
                  </div>

                  <div className="flex flex-wrap gap-1">
                    {ABAS_ESTADO.map((aba) => (
                      <button
                        key={aba}
                        type="button"
                        onClick={() => setAbaEstado(aba)}
                        className={cn(
                          "rounded-lg px-2 py-1 text-[10px] font-semibold",
                          abaEstado === aba
                            ? "bg-primary-900 text-white"
                            : "bg-slate-100 text-slate-500",
                        )}
                      >
                        {humanize(aba)}
                      </button>
                    ))}
                  </div>

                  {!estadoAtual[abaEstado]?.length ? (
                    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-5 text-center">
                      <Sparkles className="mx-auto h-6 w-6 text-slate-300" />
                      <p className="mt-2 text-xs font-semibold text-slate-500">
                        Sem itens em “{humanize(abaEstado)}”
                      </p>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {estadoAtual[abaEstado].map((item, index) => {
                        const classificacao = String(
                          item.classificacao ??
                            item.nivel ??
                            item.tipo ??
                            abaEstado,
                        );
                        return (
                          <div
                            key={index}
                            className="rounded-xl border border-slate-200 p-3 text-xs leading-5 text-slate-700"
                          >
                            <span
                              className={cn(
                                "mb-1.5 inline-flex rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase",
                                CLASSIFICACAO_COR[classificacao] ??
                                  "bg-slate-100 text-slate-600",
                              )}
                            >
                              {humanize(classificacao)}
                            </span>
                            <p>{getItemText(item)}</p>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>
          </aside>
        )}
      </div>

      {modalNovo && (
        <Modal onClose={() => setModalNovo(false)} wide>
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wide text-primary-700">
                Nova atividade
              </p>
              <h2 className="mt-1 text-xl font-bold text-slate-950">
                Como deseja começar?
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Todas as opções abrem a mesma Sala Jurídica e o chat permanece
                livre durante todo o trabalho.
              </p>
            </div>
            <button
              type="button"
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
              onClick={() => setModalNovo(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-5 grid gap-3 sm:grid-cols-2">
            {([
              {
                id: "livre" as const,
                title: "Conversa jurídica livre",
                text: "Pergunte, analise, escreva ou revise sem roteiro obrigatório.",
                icon: MessageCircle,
              },
              {
                id: "relato" as const,
                title: "Relatar um caso",
                text: "Cole o relato e deixe o EJC organizar fatos, urgência e lacunas.",
                icon: ClipboardList,
              },
              {
                id: "documentos" as const,
                title: "Analisar documentos",
                text: "Anexe autos, contratos ou provas e faça um Raio-X técnico.",
                icon: FileSearch,
              },
            ]).map((item) => {
              const Icon = item.icon;
              return (
                <button
                  key={item.id}
                  type="button"
                  className="rounded-2xl border border-slate-200 p-4 text-left hover:border-primary-200 hover:bg-primary-50"
                  onClick={() => void criarSessao(item.id)}
                >
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-600">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="mt-3 block text-sm font-bold text-slate-900">
                    {item.title}
                  </span>
                  <span className="mt-1 block text-xs leading-5 text-slate-500">
                    {item.text}
                  </span>
                </button>
              );
            })}
            <button
              type="button"
              className="rounded-2xl border border-slate-200 p-4 text-left hover:border-primary-200 hover:bg-primary-50"
              onClick={() => {
                setModalNovo(false);
                navigate("/casos");
              }}
            >
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-600">
                <Briefcase className="h-5 w-5" />
              </span>
              <span className="mt-3 block text-sm font-bold text-slate-900">
                Abrir caso existente
              </span>
              <span className="mt-1 block text-xs leading-5 text-slate-500">
                Continue o trabalho no contexto oficial do caso.
              </span>
            </button>
          </div>
        </Modal>
      )}

      {modalAcoes && (
        <Modal onClose={() => setModalAcoes(false)} wide>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-xl font-bold text-slate-950">
                Comandos jurídicos
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                O comando apenas preenche a mensagem; você pode editar antes de
                enviar.
              </p>
            </div>
            <button
              type="button"
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
              onClick={() => setModalAcoes(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            {ACOES_RAPIDAS.map((acao) => (
              <button
                key={acao.rotulo}
                type="button"
                className="rounded-xl border border-slate-200 p-3 text-left hover:border-primary-200 hover:bg-primary-50"
                onClick={() => selecionarAcao(acao)}
              >
                <span className="block text-sm font-bold text-slate-900">
                  {acao.rotulo}
                </span>
                <span className="mt-1 line-clamp-3 block text-xs leading-5 text-slate-500">
                  {acao.comando}
                </span>
              </button>
            ))}
          </div>
        </Modal>
      )}

      {vincAberto && ativa && (
        <Modal onClose={() => setVincAberto(false)}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-950">
                Vincular a caso existente
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                A conversa será congelada para auditoria.
              </p>
            </div>
            <button
              type="button"
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
              onClick={() => setVincAberto(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <Input
            className="mt-4"
            value={vincBusca}
            onChange={(event) => void buscarCasos(event.target.value)}
            placeholder="Buscar caso por título ou número…"
          />
          {!!vincCasos.length && (
            <div className="mt-2 max-h-56 overflow-y-auto rounded-xl border border-slate-200">
              {vincCasos.map((caso) => (
                <button
                  key={caso.id}
                  type="button"
                  className={cn(
                    "block w-full border-b border-slate-100 px-3 py-2 text-left text-sm last:border-0 hover:bg-slate-50",
                    vincCaseId === caso.id && "bg-primary-50 font-semibold",
                  )}
                  onClick={() => setVincCaseId(caso.id)}
                >
                  {caso.numero_interno ? `${caso.numero_interno} · ` : ""}
                  {caso.titulo ?? caso.id}
                </button>
              ))}
            </div>
          )}
          <label className="mt-4 flex items-start gap-2 rounded-xl bg-slate-50 p-3 text-sm">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={vincRevisado}
              onChange={(event) => setVincRevisado(event.target.checked)}
            />
            Revisei fatos, provas e documentos antes do vínculo.
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
        </Modal>
      )}

      {convAberto && ativa && (
        <Modal onClose={() => setConvAberto(false)} wide>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-950">
                Transformar conversa em caso
              </h2>
              <p className="mt-1 text-xs text-slate-500">
                A revisão e a verificação de conflito são obrigatórias.
              </p>
            </div>
            <button
              type="button"
              className="rounded-lg p-2 text-slate-400 hover:bg-slate-100"
              onClick={() => setConvAberto(false)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <div className="mt-5 space-y-5">
            <section>
              <p className="mb-2 text-[10px] font-bold uppercase text-slate-400">
                1 · Cliente
              </p>
              <Input
                value={convBusca}
                onChange={(event) => void buscarClientes(event.target.value)}
                placeholder="Buscar cliente por nome, CPF ou CNPJ…"
              />
              {!!convClientes.length && (
                <div className="mt-2 max-h-44 overflow-y-auto rounded-xl border border-slate-200">
                  {convClientes.map((cliente) => (
                    <button
                      key={cliente.id}
                      type="button"
                      className={cn(
                        "block w-full border-b border-slate-100 px-3 py-2 text-left text-sm last:border-0 hover:bg-slate-50",
                        convClienteId === cliente.id &&
                          "bg-primary-50 font-semibold",
                      )}
                      onClick={() => setConvClienteId(cliente.id)}
                    >
                      {cliente.nome ?? cliente.razao_social ?? cliente.id}
                    </button>
                  ))}
                </div>
              )}
              <p className="my-2 text-center text-[10px] text-slate-400">
                — ou criar novo cliente —
              </p>
              <Input
                value={convNovoCliente}
                disabled={convClienteId != null}
                onChange={(event) => setConvNovoCliente(event.target.value)}
                placeholder="Nome do novo cliente"
              />
              {convClienteId && (
                <button
                  type="button"
                  className="mt-1 text-xs font-semibold text-primary-700 hover:underline"
                  onClick={() => setConvClienteId(null)}
                >
                  Limpar seleção e criar novo cliente
                </button>
              )}
            </section>

            <section>
              <p className="mb-2 text-[10px] font-bold uppercase text-slate-400">
                2 · Caso
              </p>
              <div className="grid gap-2 sm:grid-cols-2">
                <Input
                  value={convTitulo}
                  onChange={(event) => setConvTitulo(event.target.value)}
                  placeholder="Título do caso"
                />
                <Select
                  value={convArea}
                  onChange={(event) => setConvArea(event.target.value)}
                >
                  {AREAS_FALLBACK.map((area) => (
                    <option key={area.slug} value={area.slug}>
                      {area.nome}
                    </option>
                  ))}
                </Select>
              </div>
            </section>

            <section className="space-y-2">
              <p className="text-[10px] font-bold uppercase text-slate-400">
                3 · Confirmações
              </p>
              <label className="flex items-start gap-2 rounded-xl bg-slate-50 p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={convConflito}
                  onChange={(event) => setConvConflito(event.target.checked)}
                />
                Verifiquei conflito de interesses e possível duplicidade.
              </label>
              <label className="flex items-start gap-2 rounded-xl bg-slate-50 p-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={convRevisado}
                  onChange={(event) => setConvRevisado(event.target.checked)}
                />
                Revisei fatos, provas, pendências e documentos.
              </label>
            </section>
          </div>

          <div className="mt-5 flex justify-end gap-2">
            <Button variant="secondary" onClick={() => setConvAberto(false)}>
              Cancelar
            </Button>
            <Button
              disabled={
                convertendo ||
                !convConflito ||
                !convRevisado ||
                !convTitulo.trim() ||
                (!convClienteId && !convNovoCliente.trim())
              }
              onClick={() => void converter()}
            >
              {convertendo ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <FolderInput className="h-4 w-4" />
              )}
              Confirmar conversão
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
