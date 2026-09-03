/**
 * Sala Jurídica Conversacional (V1) — porta de entrada da IA no EJC.
 *
 * Layout chat-first (V1.1): a conversa domina a tela numa coluna ampla e
 * centralizada; sessões e estado jurídico são painéis recolhíveis.
 * Toda IA passa pelo backend (/api/sala-juridica/*), que roda o núcleo único.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import {
  AlertTriangle,
  Archive,
  ChevronDown,
  ChevronRight,
  Copy,
  Download,
  FolderInput,
  Link2,
  Loader2,
  MessageSquareText,
  Paperclip,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRightClose,
  PanelRightOpen,
  PenLine,
  Plus,
  RefreshCw,
  Scale,
  Send,
  Star,
  UploadCloud,
} from "lucide-react";
import api from "../lib/api";
import { AREAS_FALLBACK } from "../lib/areaCatalog";
import { mensagemErroHttp } from "../lib/iaErro";
import { LatestRequestGate } from "../lib/latestRequest";
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

type CitacaoItem = { trecho?: string; tipo?: string; status?: string };

const STATUS_CITACAO_LABEL: Record<string, string> = {
  identificada: "não conferida na base oficial",
  suspeita: "suspeita de erro",
  generica: "citação genérica, sem base específica",
  possivelmente_desatualizada: "possivelmente desatualizada",
};
const humanizarStatusCitacao = (status?: string) =>
  status ? (STATUS_CITACAO_LABEL[status] ?? status) : "";

type Mensagem = {
  id: string;
  autor: "user" | "ia";
  modo: string;
  conteudo: string;
  modelo?: string | null;
  agente?: string | null;
  fontes: Array<{ titulo?: string; categoria?: string; fonte?: string }>;
  alertas: string[];
  citacoes?: CitacaoItem[];
  custo_estimado?: number | null;
  estado_versao?: number | null;
  created_at?: string | null;
};

type CriticaAdversarial = {
  disponivel: boolean;
  relatorio?: string | null;
  nota_robustez?: number | null;
  provider_diverso?: boolean;
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

type PreviewConversao = {
  alertas_conflito: Array<{
    tipo: string;
    nome?: string | null;
    mensagem: string;
    protegido: boolean;
  }>;
  clientes_possivelmente_duplicados: Array<{
    id: string | null;
    nome: string;
    protegido: boolean;
  }>;
  casos_ativos_do_cliente: Array<{
    id: string | null;
    titulo: string;
    numero_interno?: string | null;
    protegido: boolean;
  }>;
  bloqueia: boolean;
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
  const navigate = useNavigate();
  const [sessoes, setSessoes] = useState<Sessao[]>([]);
  const [ativa, setAtiva] = useState<Sessao | null>(null);
  const [criticas, setCriticas] = useState<Record<string, CriticaAdversarial>>(
    {},
  );
  const [carregando, setCarregando] = useState(true);
  const [enviando, setEnviando] = useState(false);
  const [texto, setTexto] = useState("");
  const [modo, setModo] = useState("conversa_livre");
  const [workspace, setWorkspace] = useState("");
  const [abaEstado, setAbaEstado] =
    useState<(typeof ABAS_ESTADO)[number]>("fatos");
  const [busca, setBusca] = useState("");
  const [limite, setLimite] = useState(50);
  const [wizardAberto, setWizardAberto] = useState(false);
  const [convClienteBusca, setConvClienteBusca] = useState("");
  const [convClientes, setConvClientes] = useState<
    Array<{ id: string; nome?: string | null; razao_social?: string | null }>
  >([]);
  const [convClienteId, setConvClienteId] = useState<string | null>(null);
  const [convNovoCliente, setConvNovoCliente] = useState("");
  const [convArea, setConvArea] = useState("civil");
  const [convTitulo, setConvTitulo] = useState("");
  const [convFatos, setConvFatos] = useState("");
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
  const [painelSessoes, setPainelSessoes] = useState(true);
  const [painelEstado, setPainelEstado] = useState(true);
  const [workspaceAberto, setWorkspaceAberto] = useState(false);
  const [convPreview, setConvPreview] = useState<PreviewConversao | null>(null);
  const [convDuplicado, setConvDuplicado] = useState(false);

  const chatRef = useRef<HTMLDivElement>(null);
  const autosaveRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const convBloqueioServidorRef = useRef(false);
  const autosavePendenteRef = useRef<{
    sessaoId: string;
    valor: string;
  } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const buscaRef = useRef("");
  const limiteRef = useRef(50);
  const buscaInicialRef = useRef(true);
  const listaGateRef = useRef(new LatestRequestGate());
  const sessaoGateRef = useRef(new LatestRequestGate());
  const previewGateRef = useRef(new LatestRequestGate());
  const clientesGateRef = useRef(new LatestRequestGate());
  const casosGateRef = useRef(new LatestRequestGate());
  const sessaoIntencaoRef = useRef<string | null>(null);

  useEffect(
    () => () => {
      listaGateRef.current.invalidate();
      sessaoGateRef.current.invalidate();
      previewGateRef.current.invalidate();
      clientesGateRef.current.invalidate();
      casosGateRef.current.invalidate();
      if (autosaveRef.current) clearTimeout(autosaveRef.current);
    },
    [],
  );

  const carregarLista = useCallback(
    async (opts?: { q?: string; limit?: number }): Promise<Sessao[] | null> => {
      const token = listaGateRef.current.begin();
      const q = (opts?.q ?? buscaRef.current).trim().slice(0, 200);
      const limit = opts?.limit ?? limiteRef.current;
      const params: Record<string, string | number> = { limit };
      if (q) params.q = q;
      const { data } = await api.get<Sessao[]>("/sala-juridica", { params });
      if (!listaGateRef.current.isCurrent(token)) return null;
      setSessoes(data);
      return data;
    },
    [],
  );

  const abrirSessao = useCallback(async (id: string): Promise<boolean> => {
    sessaoIntencaoRef.current = id;
    const token = sessaoGateRef.current.begin();
    const { data } = await api.get<Sessao>(`/sala-juridica/${id}`);
    if (!sessaoGateRef.current.isCurrent(token)) return false;
    setAtiva(data);
    setWorkspace(data.workspace_texto ?? "");
    setWorkspaceAberto(Boolean(data.workspace_texto?.trim()));
    return true;
  }, []);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      try {
        const lista = await carregarLista();
        if (mounted && lista?.length) await abrirSessao(lista[0].id);
      } catch {
        if (mounted) toast.error("Falha ao carregar a Sala Jurídica");
      } finally {
        if (mounted) setCarregando(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [carregarLista, abrirSessao, toast]);

  useEffect(() => {
    chatRef.current?.scrollTo({ top: chatRef.current.scrollHeight });
  }, [ativa?.mensagens?.length]);

  useEffect(() => {
    buscaRef.current = busca;
    if (buscaInicialRef.current) {
      buscaInicialRef.current = false;
      return;
    }
    const t = setTimeout(() => {
      carregarLista().catch(() => toast.error("Falha ao pesquisar análises"));
    }, 400);
    return () => clearTimeout(t);
  }, [busca, carregarLista]);

  const carregarMais = async () => {
    const novoLimite = Math.min(limite + 50, 200);
    setLimite(novoLimite);
    limiteRef.current = novoLimite;
    try {
      await carregarLista({ limit: novoLimite });
    } catch {
      toast.error("Falha ao carregar mais análises");
    }
  };

  const novaSessao = async () => {
    const { data } = await api.post<Sessao>("/sala-juridica", {
      titulo: `Nova análise — ${new Date().toLocaleDateString("pt-BR")}`,
    });
    await carregarLista();
    await abrirSessao(data.id);
  };

  const aoEditarWorkspace = (valor: string) => {
    setWorkspace(valor);
    if (!ativa || ativa.frozen) return;
    autosavePendenteRef.current = { sessaoId: ativa.id, valor };
    if (autosaveRef.current) clearTimeout(autosaveRef.current);
    const sessaoId = ativa.id;
    autosaveRef.current = setTimeout(async () => {
      try {
        await api.patch(`/sala-juridica/${sessaoId}`, {
          workspace_texto: valor,
        });
        if (
          autosavePendenteRef.current?.sessaoId === sessaoId &&
          autosavePendenteRef.current.valor === valor
        ) {
          autosavePendenteRef.current = null;
        }
      } catch {
        toast.error("Falha no salvamento automático");
      }
    }, 1200);
  };

  const descarregarAutosave = async (sessao: Sessao): Promise<boolean> => {
    const pendente = autosavePendenteRef.current;
    if (!pendente || pendente.sessaoId !== sessao.id || sessao.frozen)
      return true;
    if (autosaveRef.current) clearTimeout(autosaveRef.current);
    autosavePendenteRef.current = null;
    try {
      await api.patch(`/sala-juridica/${sessao.id}`, {
        workspace_texto: pendente.valor,
      });
      return true;
    } catch {
      autosavePendenteRef.current = pendente;
      toast.error(
        "O workspace não foi salvo. A mensagem não foi enviada para evitar análise com contexto desatualizado.",
      );
      return false;
    }
  };

  const enviar = async () => {
    if (!ativa || !texto.trim() || enviando) return;
    const sessaoId = ativa.id;
    const conteudo = texto.trim();
    setTexto("");
    setEnviando(true);

    const workspacePersistido = await descarregarAutosave(ativa);
    if (!workspacePersistido) {
      setTexto(conteudo);
      setEnviando(false);
      return;
    }

    setAtiva((s) =>
      s?.id === sessaoId
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
      const { data } = await api.post(`/sala-juridica/${sessaoId}/mensagens`, {
        conteudo,
        modo,
      });
      const critica = data?.critica_adversarial as CriticaAdversarial | null;
      const idMsgIa = data?.mensagem_ia?.id as string | undefined;
      if (critica?.disponivel && idMsgIa) {
        setCriticas((prev) => ({ ...prev, [idMsgIa]: critica }));
      }
      if (sessaoIntencaoRef.current === sessaoId) {
        await abrirSessao(sessaoId);
      }
      await carregarLista();
    } catch (err: unknown) {
      toast.error(mensagemErroHttp(err, "Falha ao enviar a mensagem"));
      if (sessaoIntencaoRef.current === sessaoId) setTexto(conteudo);
    } finally {
      setEnviando(false);
    }
  };

  const anexar = async (files: FileList | null) => {
    if (!ativa || !files?.length) return;
    const sessaoId = ativa.id;
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    try {
      const { data } = await api.post(
        `/sala-juridica/${sessaoId}/anexos`,
        form,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      const anexados = (data?.anexados ?? []).length;
      toast.success(`${anexados} documento(s) anexado(s) e extraído(s)`);
      if (sessaoIntencaoRef.current === sessaoId) await abrirSessao(sessaoId);
    } catch (err: unknown) {
      toast.error(mensagemErroHttp(err, "Falha no upload dos documentos"));
    }
  };

  const alternarFavorita = async (s: Sessao) => {
    try {
      await api.patch(`/sala-juridica/${s.id}`, { favorita: !s.favorita });
      await carregarLista();
    } catch (err: unknown) {
      toast.error(mensagemErroHttp(err, "Falha ao atualizar favorita"));
    }
  };

  const arquivar = async () => {
    if (!ativa) return;
    try {
      await api.post(`/sala-juridica/${ativa.id}/saida`, { acao: "arquivar" });
      toast.success("Análise arquivada");
      await carregarLista();
    } catch (err: unknown) {
      toast.error(mensagemErroHttp(err, "Falha ao arquivar a análise"));
    }
  };

  // Último degrau do pré-preenchimento dos fatos: o que o próprio advogado
  // escreveu na sessão. `estado.resumo` vem de uma extração de IA declarada
  // fail-soft no backend (`_extrair_estado` devolve None se o provider estiver
  // fora, e integração de IA no EJC nasce desligada); `workspace_texto` só
  // existe se alguém digitou nele. Quando os dois faltam, a caixa abria VAZIA
  // e o caso nascia com `descricao_fatos = NULL` — enquanto o relato dos fatos
  // estava ali, nas mensagens. Perder os fatos é perder o insumo de
  // `case_context`, do dossiê e da geração de peça.
  const fatosDasMensagens = (sessao: Sessao): string =>
    (sessao.mensagens ?? [])
      .filter((m) => m.autor === "user")
      .map((m) => m.conteudo.trim())
      .filter(Boolean)
      .join("\n\n");

  const abrirWizard = () => {
    if (!ativa) return;
    setConvTitulo(ativa.titulo);
    setConvFatos(
      (
        ativa.estado?.resumo ||
        ativa.workspace_texto ||
        fatosDasMensagens(ativa) ||
        ""
      ).slice(0, 10_000),
    );
    setConvArea(ativa.area_sugerida || "civil");
    setConvNovoCliente(ativa.cliente_potencial ?? "");
    setConvClienteId(null);
    setConvConflito(false);
    setConvRevisado(false);
    setConvDuplicado(false);
    convBloqueioServidorRef.current = false;
    previewGateRef.current.invalidate();
    setConvPreview(null);
    setWizardAberto(true);
  };

  useEffect(() => {
    if (!wizardAberto || !ativa) {
      previewGateRef.current.invalidate();
      return;
    }
    const sessaoId = ativa.id;
    const nome = convClienteId ? null : convNovoCliente.trim() || null;
    const gate = previewGateRef.current;
    const t = setTimeout(async () => {
      const token = gate.begin();
      try {
        const { data } = await api.get<PreviewConversao>(
          `/sala-juridica/${sessaoId}/conversao/preview`,
          {
            params: {
              ...(nome ? { nome_cliente: nome } : {}),
              ...(convClienteId ? { client_id: convClienteId } : {}),
            },
          },
        );
        if (!gate.isCurrent(token)) return;
        const temAchados =
          data.alertas_conflito.length > 0 ||
          data.clientes_possivelmente_duplicados.length > 0 ||
          data.casos_ativos_do_cliente.length > 0 ||
          data.bloqueia;
        setConvPreview((prev) =>
          convBloqueioServidorRef.current && !temAchados ? prev : data,
        );
      } catch {
        /* preview indisponível não impede o wizard; servidor ainda barra */
      }
    }, 400);
    return () => {
      clearTimeout(t);
      gate.invalidate();
    };
  }, [wizardAberto, ativa, convClienteId, convNovoCliente]);

  const temDuplicidade = Boolean(
    convPreview &&
    (convClienteId == null
      ? convPreview.clientes_possivelmente_duplicados.length > 0
      : convPreview.casos_ativos_do_cliente.length > 0),
  );

  const buscarClientes = async (termo: string) => {
    setConvClienteBusca(termo);
    const token = clientesGateRef.current.begin();
    const normalizado = termo.trim();
    if (normalizado.length < 2) {
      setConvClientes([]);
      return;
    }
    try {
      // Barra final: sem ela o backend responde 307 para /api/clients/ (prefixo
      // legado, com header Deprecation) — um round-trip extra por busca.
      const { data } = await api.get("/clients/", {
        params: { search: normalizado, page_size: 8 },
      });
      if (!clientesGateRef.current.isCurrent(token)) return;
      const lista = data?.data ?? data?.items ?? data;
      setConvClientes(Array.isArray(lista) ? lista : []);
    } catch {
      if (clientesGateRef.current.isCurrent(token)) setConvClientes([]);
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
        descricao: convFatos.trim() || null,
        advogado_responsavel_id: user?.id,
        confirmo_conflito_verificado: convConflito,
        confirmo_dados_revisados: convRevisado,
        conflict_confirmed: convConflito,
        duplicate_confirmed: convDuplicado,
      });
      const docs = (data?.documentos_transferidos ?? []).length;
      toast.success(
        data?.ja_convertido
          ? "Análise já estava convertida"
          : `Caso criado${docs ? ` com ${docs} documento(s)` : ""} — análise congelada para auditoria`,
      );
      setWizardAberto(false);
      if (data?.case_id) {
        navigate(`/casos/${data.case_id}`);
        return;
      }
      if (sessaoIntencaoRef.current === ativa.id) await abrirSessao(ativa.id);
      await carregarLista();
    } catch (err: unknown) {
      const detail = (
        err as {
          response?: {
            data?: {
              detail?:
                string | ({ mensagem?: string } & Partial<PreviewConversao>);
            };
          };
        }
      )?.response?.data?.detail;
      if (detail && typeof detail === "object") {
        convBloqueioServidorRef.current = true;
        setConvPreview((prev) => ({
          alertas_conflito:
            detail.alertas_conflito ?? prev?.alertas_conflito ?? [],
          clientes_possivelmente_duplicados:
            detail.clientes_possivelmente_duplicados ??
            prev?.clientes_possivelmente_duplicados ??
            [],
          casos_ativos_do_cliente:
            detail.casos_ativos_do_cliente ??
            prev?.casos_ativos_do_cliente ??
            [],
          bloqueia: true,
        }));
      }
      toast.error(mensagemErroHttp(err, "Falha na conversão"));
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
    } catch (err: unknown) {
      toast.error(mensagemErroHttp(err, "Falha na exportação"));
    } finally {
      setExportando(false);
    }
  };

  const copiarMensagem = async (conteudo: string) => {
    await navigator.clipboard.writeText(conteudo);
    toast.success("Copiado");
  };

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
    const token = casosGateRef.current.begin();
    const normalizado = termo.trim();
    if (normalizado.length < 2) {
      setVincCasos([]);
      return;
    }
    try {
      // Barra final: evita o 307 para o prefixo legado (ver busca de clientes).
      const { data } = await api.get("/cases/", {
        params: { search: normalizado, page_size: 10 },
      });
      if (!casosGateRef.current.isCurrent(token)) return;
      const lista = data?.data ?? data?.items ?? data;
      setVincCasos(Array.isArray(lista) ? lista : []);
    } catch {
      if (casosGateRef.current.isCurrent(token)) setVincCasos([]);
    }
  };

  const vincularCaso = async () => {
    if (!ativa || !vincCaseId || vinculando) return;
    setVinculando(true);
    try {
      const { data } = await api.post(
        `/sala-juridica/${ativa.id}/vincular-caso`,
        {
          case_id: vincCaseId,
          confirmo_dados_revisados: vincRevisado,
        },
      );
      toast.success(
        data?.ja_convertido
          ? "Análise já estava vinculada a um caso — abrindo o caso vinculado"
          : "Análise vinculada ao caso — congelada para auditoria",
      );
      setVincAberto(false);
      navigate(`/casos/${data?.case_id ?? vincCaseId}`);
      return;
    } catch (err: unknown) {
      toast.error(mensagemErroHttp(err, "Falha ao vincular"));
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

      <div
        className={cn(
          "grid gap-4",
          painelSessoes &&
            painelEstado &&
            "lg:grid-cols-[260px_minmax(0,1fr)_320px]",
          painelSessoes &&
            !painelEstado &&
            "lg:grid-cols-[260px_minmax(0,1fr)]",
          !painelSessoes &&
            painelEstado &&
            "lg:grid-cols-[minmax(0,1fr)_320px]",
          !painelSessoes && !painelEstado && "lg:grid-cols-1",
        )}
      >
        {painelSessoes && (
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
                    onClick={() => void abrirSessao(s.id)}
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
            {sessoes.length >= limite && limite < 200 && (
              <Button
                variant="secondary"
                className="w-full"
                onClick={() => void carregarMais()}
              >
                Carregar mais
              </Button>
            )}
          </aside>
        )}

        <section className="flex min-h-[78vh] flex-col gap-3">
          <div className="flex items-center gap-2 text-xs text-gray-500">
            <button
              className="rounded p-1 hover:bg-gray-100"
              title={painelSessoes ? "Ocultar análises" : "Mostrar análises"}
              onClick={() => setPainelSessoes((v) => !v)}
            >
              {painelSessoes ? (
                <PanelLeftClose className="h-4 w-4" />
              ) : (
                <PanelLeftOpen className="h-4 w-4" />
              )}
            </button>
            <span className="truncate font-semibold text-gray-700">
              {ativa?.titulo ?? "Sala Jurídica"}
            </span>
            {ativa?.frozen && <Badge tone="amber">congelada</Badge>}
            <button
              className="ml-auto rounded p-1 hover:bg-gray-100"
              title={
                painelEstado
                  ? "Ocultar estado jurídico"
                  : "Mostrar estado jurídico"
              }
              onClick={() => setPainelEstado((v) => !v)}
            >
              {painelEstado ? (
                <PanelRightClose className="h-4 w-4" />
              ) : (
                <PanelRightOpen className="h-4 w-4" />
              )}
            </button>
          </div>
          {ativa ? (
            <>
              {ativa.frozen && ativa.convertido_case_id && (
                <div className="flex flex-wrap items-center gap-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
                  <FolderInput className="h-4 w-4 shrink-0" />
                  <span>
                    Esta análise foi convertida em caso e está congelada para
                    auditoria.
                  </span>
                  <Link
                    to={`/casos/${ativa.convertido_case_id}`}
                    className="font-semibold underline underline-offset-2"
                  >
                    Abrir o caso →
                  </Link>
                </div>
              )}
              <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
                <button
                  className="flex w-full items-center justify-between px-3 py-2 text-xs text-gray-500"
                  onClick={() => setWorkspaceAberto((v) => !v)}
                >
                  <span className="flex items-center gap-1 font-semibold text-gray-700">
                    {workspaceAberto ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                    Área de trabalho livre
                    {!workspaceAberto && workspace.trim() && (
                      <Badge tone="slate">com conteúdo</Badge>
                    )}
                  </span>
                  <span>
                    v{ativa.workspace_versao} · salvamento automático
                    {ativa.frozen && " · congelada (auditoria)"}
                  </span>
                </button>
                {workspaceAberto && (
                  <Textarea
                    className="min-h-[160px] w-full resize-y border-0 border-t border-gray-100 focus:ring-0"
                    placeholder="Cole fatos, narrativas do cliente, rascunhos, trechos de peças…"
                    value={workspace}
                    disabled={ativa.frozen}
                    onChange={(e) => aoEditarWorkspace(e.target.value)}
                  />
                )}
              </div>

              <div
                ref={chatRef}
                className="flex-1 overflow-y-auto rounded-xl border border-gray-200 bg-gray-50 p-3"
              >
                <div className="mx-auto w-full max-w-3xl space-y-3">
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
                          ? "ml-auto w-fit max-w-[88%] border-primary-100 bg-primary-50 dark:border-primary-900 dark:bg-primary-950/40"
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
                      {m.autor === "ia" &&
                        (m.citacoes ?? []).some(
                          (c) => c.status !== "verificada",
                        ) && (
                          <div className="mt-2 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800">
                            <p className="font-semibold">
                              Citações não confirmadas na base oficial —
                              conferir antes de usar:
                            </p>
                            <ul className="mt-1 list-disc pl-4">
                              {(m.citacoes ?? [])
                                .filter((c) => c.status !== "verificada")
                                .map((c, i) => (
                                  <li key={i}>
                                    {c.trecho ?? c.tipo ?? "citação"}
                                    {c.status
                                      ? ` (${humanizarStatusCitacao(c.status)})`
                                      : ""}
                                  </li>
                                ))}
                            </ul>
                          </div>
                        )}
                      {m.autor === "ia" && criticas[m.id] && (
                        <div className="mt-2 rounded border border-ai-200 bg-ai-50 p-2 text-xs text-ai-800">
                          <p className="font-semibold">
                            Crítica adversarial (Modo Duas IAs)
                            {criticas[m.id].nota_robustez != null &&
                              ` — robustez ${criticas[m.id].nota_robustez}/100`}
                          </p>
                          {criticas[m.id].relatorio && (
                            <p className="mt-1">{criticas[m.id].relatorio}</p>
                          )}
                        </div>
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
              </div>

              <div className="mx-auto w-full max-w-3xl rounded-xl border border-gray-200 bg-white p-2 shadow-sm">
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
                  <span className="ml-auto flex items-center gap-2">
                    <span className="hidden text-[11px] text-gray-400 sm:inline">
                      Enter envia · Shift+Enter quebra linha
                    </span>
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
              message="A Sala Jurídica é a porta de entrada conversacional do EJC: converse sobre o caso, anexe documentos e converta em caso quando estiver madura. Tem só um lote de documentos para ler? Use o Raio-X."
              action={
                <div className="flex flex-wrap justify-center gap-2">
                  <Button onClick={() => void novaSessao()}>
                    <Plus className="h-4 w-4" /> Nova análise
                  </Button>
                  <Link to="/raio-x">
                    <Button variant="secondary">Ir para o Raio-X</Button>
                  </Link>
                </div>
              }
            />
          )}
        </section>

        {painelEstado && (
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
                <p className="text-xs text-gray-400">
                  Nenhum documento anexado.
                </p>
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
        )}
      </div>

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

            {convPreview && convPreview.alertas_conflito.length > 0 && (
              <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-3">
                <p className="mb-1 flex items-center gap-1 text-xs font-bold text-red-800">
                  <AlertTriangle className="h-3.5 w-3.5" />
                  Alertas de conflito de interesses (
                  {convPreview.alertas_conflito.length})
                </p>
                <ul className="list-disc pl-4 text-xs text-red-700">
                  {convPreview.alertas_conflito.map((a, i) => (
                    <li key={i}>
                      <span className="font-semibold">{a.nome ?? "—"}</span>:{" "}
                      {a.mensagem}
                    </li>
                  ))}
                </ul>
              </div>
            )}

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
                    onClick={() => {
                      convBloqueioServidorRef.current = false;
                      setConvDuplicado(false);
                      setConvClienteId(c.id);
                    }}
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
              onChange={(e) => {
                convBloqueioServidorRef.current = false;
                setConvDuplicado(false);
                setConvNovoCliente(e.target.value);
              }}
            />
            {convClienteId != null && (
              <button
                className="mt-1 text-xs text-primary-700 underline"
                onClick={() => {
                  convBloqueioServidorRef.current = false;
                  setConvDuplicado(false);
                  setConvClienteId(null);
                }}
              >
                limpar seleção e criar novo cliente
              </button>
            )}
            {convPreview &&
              convClienteId == null &&
              convPreview.clientes_possivelmente_duplicados.length > 0 && (
                <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <p className="mb-1 text-xs font-bold text-amber-800">
                    Cliente possivelmente já cadastrado
                  </p>
                  {convPreview.clientes_possivelmente_duplicados.map((c, i) =>
                    c.id ? (
                      <button
                        key={i}
                        className="block text-xs text-amber-800 underline"
                        onClick={() => setConvClienteId(c.id)}
                      >
                        usar “{c.nome}” em vez de criar novo
                      </button>
                    ) : (
                      <p key={i} className="text-xs text-amber-700">
                        {c.nome} (revisão da gestão necessária)
                      </p>
                    ),
                  )}
                </div>
              )}
            {convPreview &&
              convClienteId != null &&
              convPreview.casos_ativos_do_cliente.length > 0 && (
                <div className="mt-2 rounded-lg border border-amber-200 bg-amber-50 p-3">
                  <p className="mb-1 text-xs font-bold text-amber-800">
                    Este cliente já possui caso ativo — confira se não é o mesmo
                    assunto
                  </p>
                  {convPreview.casos_ativos_do_cliente.map((c, i) => (
                    <p key={i} className="text-xs text-amber-700">
                      {c.numero_interno ? `${c.numero_interno} · ` : ""}
                      {c.titulo}
                    </p>
                  ))}
                  <p className="mt-1 text-[11px] text-amber-700">
                    Se for o mesmo assunto, prefira “Vincular a caso” em vez de
                    criar um caso novo.
                  </p>
                </div>
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
                {AREAS_FALLBACK.map((a) => (
                  <option key={a.slug} value={a.slug}>
                    {a.nome}
                  </option>
                ))}
              </Select>
            </div>
            <textarea
              className="input mt-2 h-28 w-full text-sm"
              placeholder="Fatos do caso (pré-preenchidos da análise — confira e ajuste)"
              maxLength={10_000}
              value={convFatos}
              onChange={(e) => setConvFatos(e.target.value)}
            />
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
            {temDuplicidade && (
              <label className="mt-1 flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={convDuplicado}
                  onChange={(e) => setConvDuplicado(e.target.checked)}
                />
                {convClienteId == null
                  ? "Conferi os possíveis duplicados e confirmo a criação de um novo cliente."
                  : "Conferi os casos ativos do cliente e confirmo que este é um caso NOVO."}
              </label>
            )}

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
                  (convClienteId == null && !convNovoCliente.trim()) ||
                  (temDuplicidade && !convDuplicado)
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
