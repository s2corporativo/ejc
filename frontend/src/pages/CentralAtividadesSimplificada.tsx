import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import {
  AlertTriangle,
  Bell,
  Calculator,
  CalendarDays,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Filter,
  Gavel,
  Inbox,
  MapPin,
  MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
  UserRound,
  Users,
} from "lucide-react";

import { ConfirmModal, ErrorState, Modal, Spinner } from "../components/UI";
import { toast } from "../components/Toast";
import api, { confirmarPrazo } from "../lib/api";
import { addCaseContext, readCaseContext } from "../lib/caseContext";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import {
  AvisoCapturaEmCurso,
  PrazoSugeridoModal,
  SimularPrazoModal,
  SuspensaoFormModal,
  usePodeGerirSuspensoes,
  type SugestaoAberta,
} from "./CentralAtividades/acoesLegadas";
import {
  atividadeFinalizada,
  correspondeBusca,
  detectarConflitosAgendaLegada,
  pertenceCaixaEntrada,
  precisaConferencia,
  situacaoOperacional,
  type FonteAtividade,
} from "./CentralAtividades/simplificacao";

type Aba = "hoje" | "proximos" | "entrada" | "calendario";
type Escopo = "todos" | "meus" | "equipe";
type CategoriaNovo = "prazo" | "tarefa" | "compromisso";

type ItemTipo =
  | "prazo"
  | "tarefa"
  | "suspensao"
  | "intimacao"
  | "audiencia"
  | "reuniao"
  | "compromisso"
  | "diligencia";

interface Responsavel {
  id: string;
  nome: string;
  role?: string;
}

interface Activity {
  id: string;
  fonte: FonteAtividade;
  tipo: ItemTipo;
  titulo: string;
  descricao?: string;
  date?: string;
  status: string;
  case_id?: string;
  caso_titulo?: string;
  responsavel_id?: string;
  prioridade?: string;
  dias_restantes?: number;
  urgencia?: string;
  hora?: string;
  local?: string;
  ciencia_confirmada?: boolean;
  confirmado?: boolean;
  calculado_por?: string;
  conferido_por?: string;
  conferido_em?: string;
  regime_calculo?: string;
  termo_inicial?: string;
}

interface AgendaRaw {
  id: string;
  tipo?: string;
  data_evento?: string;
  hora?: string;
  local?: string;
  responsavel_id?: string;
  concluido?: boolean;
}

interface FormNovo {
  categoria: CategoriaNovo;
  titulo: string;
  data: string;
  prioridade: string;
  descricao: string;
  responsavel_id: string;
  tipo_evento: string;
  hora: string;
  local: string;
  tipo_prazo: string;
  regime_calculo: string;
  termo_inicial: string;
  data_publicacao: string;
  base_legal: string;
}

const PRAZOS_PAGE_SIZE = 200;
const PRAZOS_MAX_PAGINAS = 10;

const TIPO_LABEL: Record<ItemTipo, string> = {
  prazo: "Prazo",
  tarefa: "Tarefa",
  suspensao: "Suspensão",
  intimacao: "Intimação",
  audiencia: "Audiência",
  reuniao: "Reunião",
  compromisso: "Compromisso",
  diligencia: "Diligência",
};

const ABAS: { key: Aba; label: string; icon: typeof Clock3 }[] = [
  { key: "hoje", label: "Hoje", icon: Clock3 },
  { key: "proximos", label: "Próximos", icon: CalendarDays },
  { key: "entrada", label: "Caixa de Entrada", icon: Inbox },
  { key: "calendario", label: "Calendário", icon: CalendarDays },
];

function apiErro(e: unknown, fallback: string): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response
    ?.data?.detail;
  return typeof detail === "string" ? detail : fallback;
}

function mapAgendaTipo(tipo?: string): ItemTipo {
  if (["audiencia", "reuniao", "compromisso", "diligencia"].includes(tipo ?? ""))
    return tipo as ItemTipo;
  return "compromisso";
}

function dataPtBr(value?: string) {
  if (!value) return "Sem data";
  const base = value.slice(0, 10);
  const [ano, mes, dia] = base.split("-");
  return ano && mes && dia ? `${dia}/${mes}/${ano}` : value;
}

function relativo(dias?: number) {
  if (dias === undefined || dias === null) return "";
  if (dias < 0) return `${Math.abs(dias)}d em atraso`;
  if (dias === 0) return "Hoje";
  if (dias === 1) return "Amanhã";
  return `em ${dias}d`;
}

function statusLabel(item: Activity) {
  const situacao = situacaoOperacional(item.status);
  if (situacao === "concluido") return "Concluído";
  if (situacao === "cancelado") return "Cancelado";
  if (situacao === "andamento") return "Em andamento";
  if ((item.dias_restantes ?? 0) < 0) return "Atrasado";
  if (precisaConferencia(item)) return "Aguardando conferência";
  return "Pendente";
}

function statusClass(item: Activity) {
  const label = statusLabel(item);
  if (label === "Concluído") return "bg-success-50 text-success-700 border-success-200";
  if (label === "Atrasado") return "bg-danger-50 text-danger-700 border-danger-200";
  if (label === "Aguardando conferência") return "bg-warn-50 text-warn-800 border-warn-200";
  if (label === "Em andamento") return "bg-primary-50 text-primary-700 border-primary-200";
  return "bg-slate-50 text-slate-600 border-slate-200";
}

function iconFor(item: Activity) {
  if (item.tipo === "audiencia") return Gavel;
  if (item.tipo === "reuniao") return Users;
  if (item.tipo === "diligencia") return MapPin;
  if (item.tipo === "intimacao") return Bell;
  if (item.fonte === "prazo") return Clock3;
  if (item.fonte === "tarefa") return CheckCircle2;
  return CalendarDays;
}

function CalendarGrid({ items }: { items: Activity[] }) {
  const hoje = new Date();
  const [cursor, setCursor] = useState(
    new Date(hoje.getFullYear(), hoje.getMonth(), 1),
  );
  const ano = cursor.getFullYear();
  const mes = cursor.getMonth();
  const primeiro = new Date(ano, mes, 1).getDay();
  const total = new Date(ano, mes + 1, 0).getDate();
  const porDia = useMemo(() => {
    const map = new Map<string, Activity[]>();
    for (const item of items) {
      const key = item.date?.slice(0, 10);
      if (!key) continue;
      map.set(key, [...(map.get(key) ?? []), item]);
    }
    return map;
  }, [items]);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white overflow-hidden">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <button
          className="btn-ghost"
          onClick={() => setCursor(new Date(ano, mes - 1, 1))}
        >
          Anterior
        </button>
        <strong className="text-sm text-slate-800">
          {cursor.toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}
        </strong>
        <button
          className="btn-ghost"
          onClick={() => setCursor(new Date(ano, mes + 1, 1))}
        >
          Próximo
        </button>
      </div>
      <div className="grid grid-cols-7 border-b border-slate-100 text-center text-[11px] font-semibold text-slate-400">
        {['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'].map((d) => (
          <div key={d} className="py-2">{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {Array.from({ length: primeiro }).map((_, idx) => (
          <div key={`vazio-${idx}`} className="min-h-24 border-b border-r border-slate-100" />
        ))}
        {Array.from({ length: total }).map((_, idx) => {
          const dia = idx + 1;
          const key = `${ano}-${String(mes + 1).padStart(2, '0')}-${String(dia).padStart(2, '0')}`;
          const diaItems = porDia.get(key) ?? [];
          const atual =
            ano === hoje.getFullYear() && mes === hoje.getMonth() && dia === hoje.getDate();
          return (
            <div key={key} className="min-h-24 border-b border-r border-slate-100 p-2">
              <span className={`inline-flex h-6 w-6 items-center justify-center rounded-full text-xs font-semibold ${atual ? 'bg-primary-900 text-white' : 'text-slate-600'}`}>
                {dia}
              </span>
              <div className="mt-1 space-y-1">
                {diaItems.slice(0, 3).map((item) => (
                  <div
                    key={`${item.fonte}-${item.id}`}
                    className="truncate rounded bg-slate-50 px-1.5 py-1 text-[10px] text-slate-600"
                    title={item.titulo}
                  >
                    {item.hora ? `${item.hora} · ` : ''}{item.titulo}
                  </div>
                ))}
                {diaItems.length > 3 && (
                  <div className="text-[10px] text-slate-400">+{diaItems.length - 3} itens</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function DeadlineFlow({ item }: { item: Activity }) {
  if (item.fonte !== "prazo" || item.prioridade !== "critica") return null;
  const passos = [
    { label: "Calculado", ok: Boolean(item.calculado_por) },
    { label: "Conferido", ok: Boolean(item.conferido_por) },
    { label: "Execução", ok: !atividadeFinalizada(item) },
    { label: "Conclusão", ok: situacaoOperacional(item.status) === "concluido" },
  ];
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5" aria-label="Fluxo do prazo crítico">
      {passos.map((passo, idx) => (
        <div key={passo.label} className="flex items-center gap-1.5">
          <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${passo.ok ? 'border-success-200 bg-success-50 text-success-700' : 'border-slate-200 bg-slate-50 text-slate-400'}`}>
            {passo.ok ? '✓ ' : '○ '}{passo.label}
          </span>
          {idx < passos.length - 1 && <span className="text-slate-300">→</span>}
        </div>
      ))}
    </div>
  );
}

export default function CentralAtividadesSimplificada() {
  const [searchParams, setSearchParams] = useSearchParams();
  const user = useAuth((state) => state.user) as { id?: string; role?: string } | null;
  const contextCaseId = readCaseContext(searchParams);
  const rawTab = searchParams.get("atividade_tab") as Aba | null;
  const tab: Aba = ["hoje", "proximos", "entrada", "calendario"].includes(rawTab ?? "")
    ? (rawTab as Aba)
    : "hoje";
  const podeGerirSuspensoes = usePodeGerirSuspensoes();

  const [items, setItems] = useState<Activity[]>([]);
  const [agendaRaw, setAgendaRaw] = useState<AgendaRaw[]>([]);
  const [responsaveis, setResponsaveis] = useState<Responsavel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [busca, setBusca] = useState("");
  const [escopo, setEscopo] = useState<Escopo>("todos");
  const [filtrosAbertos, setFiltrosAbertos] = useState(false);
  const [filtroTipo, setFiltroTipo] = useState<string>("todos");
  const [filtroSituacao, setFiltroSituacao] = useState<string>("todos");
  const [filtroUrgencia, setFiltroUrgencia] = useState<string>("todos");
  const [filtroResponsavel, setFiltroResponsavel] = useState<string>("");
  const [menuNovo, setMenuNovo] = useState(false);
  const [menuFerramentas, setMenuFerramentas] = useState(false);
  const [menuItem, setMenuItem] = useState<string | null>(null);
  const [modalNovo, setModalNovo] = useState(false);
  const [maisOpcoes, setMaisOpcoes] = useState(false);
  const [form, setForm] = useState<FormNovo>({
    categoria: "compromisso",
    titulo: "",
    data: "",
    prioridade: "media",
    descricao: "",
    responsavel_id: "",
    tipo_evento: "compromisso",
    hora: "",
    local: "",
    tipo_prazo: "processual",
    regime_calculo: "",
    termo_inicial: "",
    data_publicacao: "",
    base_legal: "",
  });
  const [reagendar, setReagendar] = useState<{ item: Activity; data: string } | null>(null);
  const [atribuir, setAtribuir] = useState<{ item: Activity; responsavel_id: string } | null>(null);
  const [excluir, setExcluir] = useState<Activity | null>(null);
  const [excluindo, setExcluindo] = useState(false);
  const [sugestao, setSugestao] = useState<SugestaoAberta | null>(null);
  const [sugerindo, setSugerindo] = useState<string | null>(null);
  const [capturando, setCapturando] = useState(false);
  const [simulando, setSimulando] = useState(false);
  const [novaSuspensao, setNovaSuspensao] = useState(false);
  const [exportando, setExportando] = useState(false);

  const setTab = (next: Aba) => {
    const params = new URLSearchParams(searchParams);
    params.set("atividade_tab", next);
    params.delete("tipo");
    params.delete("view");
    setSearchParams(params, { replace: true });
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [ativR, agendaR, prazosR] = await Promise.allSettled([
        api.get("/atividades", { params: { apenas_pendentes: false } }),
        api.get("/agenda-eventos/", { params: { page_size: 500 } }),
        api.get("/deadlines/", {
          params: { status: "", page: 1, page_size: PRAZOS_PAGE_SIZE },
        }),
      ]);
      if (ativR.status !== "fulfilled") {
        setError(true);
        return;
      }

      const agenda = agendaR.status === "fulfilled" ? asList(agendaR.value.data) as AgendaRaw[] : [];
      setAgendaRaw(agenda);
      const agendaMap: Record<string, AgendaRaw> = {};
      agenda.forEach((a) => (agendaMap[a.id] = a));

      const prazoMap: Record<string, any> = {};
      if (prazosR.status === "fulfilled") {
        asList(prazosR.value.data).forEach((p: any) => (prazoMap[p.id] = p));
        const total = Number(prazosR.value.data?.total ?? 0);
        const feedIds = new Set<string>(
          asList(ativR.value.data)
            .filter((a: any) => a.tipo === "prazo")
            .map((a: any) => a.id),
        );
        const paginas = Math.min(Math.ceil(total / PRAZOS_PAGE_SIZE), PRAZOS_MAX_PAGINAS);
        if ([...feedIds].some((id) => !prazoMap[id]) && paginas > 1) {
          const extras = await Promise.allSettled(
            Array.from({ length: paginas - 1 }, (_, i) =>
              api.get("/deadlines/", {
                params: { status: "", page: i + 2, page_size: PRAZOS_PAGE_SIZE },
              }),
            ),
          );
          extras.forEach((r) => {
            if (r.status === "fulfilled")
              asList(r.value.data).forEach((p: any) => (prazoMap[p.id] = p));
          });
        }
      }

      setItems(
        asList(ativR.value.data).map((a: any): Activity => {
          const fonte: FonteAtividade = a.tipo === "agenda" ? "agenda" : a.tipo;
          const evento = fonte === "agenda" ? agendaMap[a.id] : undefined;
          const prazo = fonte === "prazo" ? prazoMap[a.id] : undefined;
          return {
            id: a.id,
            fonte,
            tipo: fonte === "agenda" ? mapAgendaTipo(a.subtipo ?? evento?.tipo) : (a.tipo as ItemTipo),
            titulo: a.titulo,
            descricao: a.descricao ?? undefined,
            date: a.date ?? undefined,
            status: a.status ?? "pendente",
            case_id: a.case_id ?? undefined,
            caso_titulo: a.caso_titulo ?? undefined,
            responsavel_id: a.responsavel_id ?? undefined,
            prioridade: a.prioridade ?? undefined,
            dias_restantes: a.dias_restantes ?? undefined,
            urgencia: a.urgencia ?? "normal",
            hora: evento?.hora ?? undefined,
            local: evento?.local ?? undefined,
            ciencia_confirmada: prazo?.ciencia_confirmada,
            confirmado: prazo?.confirmado,
            calculado_por: prazo?.calculado_por ?? undefined,
            conferido_por: prazo?.conferido_por ?? undefined,
            conferido_em: prazo?.conferido_em ?? undefined,
            regime_calculo: prazo?.regime_calculo ?? undefined,
            termo_inicial: prazo?.termo_inicial ?? undefined,
          };
        }),
      );
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    api.get("/atendimentos/responsaveis")
      .then((r) => setResponsaveis(asList(r.data)))
      .catch(() => setResponsaveis([]));
  }, []);

  const nomeDe = useCallback(
    (id?: string) => responsaveis.find((r) => r.id === id)?.nome,
    [responsaveis],
  );

  const conflitos = useMemo(() => detectarConflitosAgendaLegada(agendaRaw), [agendaRaw]);
  const abertos = useMemo(() => items.filter((item) => !atividadeFinalizada(item)), [items]);
  const radar = useMemo(() => ({
    hoje: abertos.filter((i) => i.dias_restantes === 0).length,
    conferencia: abertos.filter(precisaConferencia).length,
    intimacoes: abertos.filter((i) => i.fonte === "intimacao").length,
    conflitos: conflitos.length,
  }), [abertos, conflitos]);

  const filtrados = useMemo(() => {
    let base = items.filter((item) => {
      if (escopo === "meus" && user?.id && item.responsavel_id !== user.id) return false;
      if (escopo === "equipe" && user?.id && (!item.responsavel_id || item.responsavel_id === user.id)) return false;
      if (filtroTipo !== "todos" && item.tipo !== filtroTipo && item.fonte !== filtroTipo) return false;
      if (filtroSituacao !== "todos" && situacaoOperacional(item.status) !== filtroSituacao) return false;
      if (filtroUrgencia !== "todos" && item.urgencia !== filtroUrgencia) return false;
      if (filtroResponsavel && item.responsavel_id !== filtroResponsavel) return false;
      return correspondeBusca(item, busca, nomeDe(item.responsavel_id));
    });

    if (tab === "hoje")
      base = base.filter((item) => !atividadeFinalizada(item) && (item.dias_restantes ?? 1) <= 0);
    else if (tab === "proximos")
      base = base.filter((item) => !atividadeFinalizada(item) && ((item.dias_restantes ?? 1) > 0 || item.dias_restantes == null));
    else if (tab === "entrada") base = base.filter(pertenceCaixaEntrada);

    return [...base].sort((a, b) => {
      const da = a.date ?? "9999-12-31";
      const db = b.date ?? "9999-12-31";
      return da.localeCompare(db);
    });
  }, [items, escopo, filtroTipo, filtroSituacao, filtroUrgencia, filtroResponsavel, busca, nomeDe, tab, user?.id]);

  const abrirNovo = (categoria: CategoriaNovo) => {
    setMenuNovo(false);
    setMaisOpcoes(false);
    setForm({
      categoria,
      titulo: "",
      data: "",
      prioridade: "media",
      descricao: "",
      responsavel_id: "",
      tipo_evento: "compromisso",
      hora: "",
      local: "",
      tipo_prazo: "processual",
      regime_calculo: "",
      termo_inicial: "",
      data_publicacao: "",
      base_legal: "",
    });
    setModalNovo(true);
  };

  const salvarNovo = async () => {
    if (!form.titulo.trim()) return toast.error("Título é obrigatório");
    try {
      if (form.categoria === "prazo") {
        if (!form.data) return toast.error("Data final do prazo é obrigatória");
        if (form.tipo_prazo === "processual" && !form.regime_calculo)
          return toast.error("Informe o regime do prazo processual");
        if (form.prioridade === "critica" && form.tipo_prazo === "processual" && !form.termo_inicial) {
          setMaisOpcoes(true);
          return toast.error("Prazo processual crítico exige termo inicial explícito");
        }
        if (form.data_publicacao && form.termo_inicial && form.data_publicacao > form.termo_inicial)
          return toast.error("Publicação não pode ser posterior ao termo inicial");
        if (form.termo_inicial && form.termo_inicial > form.data)
          return toast.error("Termo inicial não pode ser posterior ao vencimento");
        await api.post("/deadlines/", addCaseContext({
          titulo: form.titulo.trim(),
          tipo: form.tipo_prazo,
          prioridade: form.prioridade,
          data_prazo: form.data,
          descricao: form.descricao || undefined,
          responsavel_id: form.responsavel_id || undefined,
          regime_calculo: form.tipo_prazo === "processual" ? form.regime_calculo : undefined,
          termo_inicial: form.termo_inicial || undefined,
          data_publicacao: form.data_publicacao || undefined,
          base_legal: form.base_legal || undefined,
        }, contextCaseId));
        toast.success("Prazo criado");
      } else if (form.categoria === "tarefa") {
        await api.post("/tasks/", addCaseContext({
          titulo: form.titulo.trim(),
          prioridade: form.prioridade,
          data_limite: form.data || undefined,
          descricao: form.descricao || undefined,
          responsavel_id: form.responsavel_id || undefined,
        }, contextCaseId));
        toast.success("Tarefa criada");
      } else {
        if (!form.data) return toast.error("Data do compromisso é obrigatória");
        const { data } = await api.post("/agenda-eventos/", addCaseContext({
          titulo: form.titulo.trim(),
          tipo: form.tipo_evento,
          data_evento: form.data,
          hora: form.hora || undefined,
          local: form.local || undefined,
          descricao: form.descricao || undefined,
        }, contextCaseId));
        const quantidade = Array.isArray(data?.conflito_agenda) ? data.conflito_agenda.length : 0;
        if (quantidade) toast.error(`Compromisso salvo com ${quantidade} coincidência(s) de horário.`);
        else toast.success("Compromisso criado");
      }
      setModalNovo(false);
      load();
    } catch (e) {
      toast.error(apiErro(e, "Erro ao salvar"));
    }
  };

  const concluir = async (item: Activity) => {
    try {
      if (item.fonte === "prazo") await api.patch(`/deadlines/${item.id}`, { status: "concluido" });
      else if (item.fonte === "tarefa") await api.patch(`/tasks/${item.id}`, { status: "concluida" });
      else if (item.fonte === "agenda") await api.patch(`/agenda-eventos/${item.id}`, { concluido: true });
      else if (item.fonte === "intimacao") await api.post(`/intimacoes/${item.id}/processar`);
      else return toast.info("Suspensões são regras do calendário jurídico");
      toast.success(item.fonte === "intimacao" ? "Intimação tratada" : "Item concluído");
      load();
    } catch (e) { toast.error(apiErro(e, "Erro ao concluir")); }
  };

  const darCiencia = async (item: Activity) => {
    try {
      await api.post(`/deadlines/${item.id}/ciencia`);
      toast.success("Ciência registrada");
      load();
    } catch (e) { toast.error(apiErro(e, "Erro ao registrar ciência")); }
  };

  const conferirPrazo = async (item: Activity) => {
    try {
      await confirmarPrazo(item.id);
      toast.success(item.prioridade === "critica" ? "Conferência registrada" : "Prazo confirmado");
      load();
    } catch (e) { toast.error(apiErro(e, "Não foi possível conferir o prazo")); }
  };

  const abrirPrazoSugerido = async (item: Activity) => {
    setSugerindo(item.id);
    try {
      const { data } = await api.get(`/intimacoes/${item.id}/prazo-sugerido`);
      setSugestao({ id: item.id, titulo: item.titulo, dados: data });
    } catch (e) { toast.error(apiErro(e, "Não foi possível revisar a sugestão")); }
    finally { setSugerindo(null); }
  };

  const capturarIntimacoes = async () => {
    setCapturando(true);
    try {
      const { data } = await api.post("/intimacoes/capturar-agora");
      toast.success(data.detail || "Busca de intimações concluída");
      load();
    } catch (e) { toast.error(apiErro(e, "Não foi possível buscar intimações agora")); }
    finally { setCapturando(false); }
  };

  const salvarReagendamento = async () => {
    if (!reagendar?.data) return toast.error("Informe a nova data");
    try {
      if (reagendar.item.fonte === "prazo") await api.patch(`/deadlines/${reagendar.item.id}`, { data_prazo: reagendar.data });
      else if (reagendar.item.fonte === "tarefa") await api.patch(`/tasks/${reagendar.item.id}`, { data_limite: reagendar.data });
      else if (reagendar.item.fonte === "agenda") await api.patch(`/agenda-eventos/${reagendar.item.id}`, { data_evento: reagendar.data });
      else return toast.info("Este item não permite reagendamento");
      toast.success("Data atualizada");
      setReagendar(null);
      load();
    } catch (e) { toast.error(apiErro(e, "Erro ao reagendar")); }
  };

  const salvarAtribuicao = async () => {
    if (!atribuir?.responsavel_id) return toast.error("Escolha o responsável");
    try {
      if (atribuir.item.fonte === "prazo") await api.patch(`/deadlines/${atribuir.item.id}`, { responsavel_id: atribuir.responsavel_id });
      else if (atribuir.item.fonte === "tarefa") await api.patch(`/tasks/${atribuir.item.id}`, { responsavel_id: atribuir.responsavel_id });
      else return toast.info("Atribuição direta está disponível para prazos e tarefas");
      toast.success("Responsável atualizado");
      setAtribuir(null);
      load();
    } catch (e) { toast.error(apiErro(e, "Erro ao atribuir responsável")); }
  };

  const confirmarExclusao = async () => {
    if (!excluir) return;
    setExcluindo(true);
    try {
      if (excluir.fonte === "tarefa") await api.delete(`/tasks/${excluir.id}`);
      else if (excluir.fonte === "suspensao" && podeGerirSuspensoes) await api.delete(`/suspensoes/${excluir.id}`);
      else return toast.info("A exclusão não está disponível para este item");
      toast.success(excluir.fonte === "tarefa" ? "Tarefa excluída" : "Suspensão removida");
      setExcluir(null);
      load();
    } catch (e) { toast.error(apiErro(e, "Erro ao excluir")); }
    finally { setExcluindo(false); }
  };

  const exportarCsv = async () => {
    setExportando(true);
    try {
      const r = await api.get("/deadlines/export.csv", {
        params: { status: "", case_id: contextCaseId },
        responseType: "blob",
      });
      const url = URL.createObjectURL(r.data as Blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "prazos.csv";
      a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Falha ao exportar os prazos"); }
    finally { setExportando(false); }
  };

  const renderItem = (item: Activity) => {
    const Icon = iconFor(item);
    const finalizado = atividadeFinalizada(item);
    const podeReagendar = ["prazo", "tarefa", "agenda"].includes(item.fonte) && !finalizado;
    const podeAtribuir = ["prazo", "tarefa"].includes(item.fonte) && responsaveis.length > 0 && !finalizado;
    const key = `${item.fonte}-${item.id}`;
    return (
      <article key={key} className="border-b border-slate-100 px-4 py-4 last:border-b-0">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 rounded-xl bg-slate-50 p-2 text-slate-500"><Icon className="h-4 w-4" /></div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-400">{TIPO_LABEL[item.tipo]}</span>
              <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold ${statusClass(item)}`}>{statusLabel(item)}</span>
              {item.prioridade === "critica" && <span className="rounded-full bg-danger-50 px-2 py-0.5 text-[10px] font-semibold text-danger-700">Crítico</span>}
            </div>
            <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
              <h3 className="text-sm font-semibold text-slate-800">{item.titulo}</h3>
              {item.case_id && item.caso_titulo && <Link className="text-xs text-primary-600 hover:underline" to={`/casos/${item.case_id}`}>{item.caso_titulo}</Link>}
            </div>
            <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
              <span>{dataPtBr(item.date)} {item.hora ? `· ${item.hora}` : ''}</span>
              {item.dias_restantes !== undefined && <span className={(item.dias_restantes ?? 0) < 0 ? 'font-semibold text-danger-600' : ''}>{relativo(item.dias_restantes)}</span>}
              {nomeDe(item.responsavel_id) && <span className="inline-flex items-center gap-1"><UserRound className="h-3 w-3" />{nomeDe(item.responsavel_id)}</span>}
              {item.local && <span>{item.local}</span>}
            </div>
            <DeadlineFlow item={item} />
          </div>
          <div className="flex shrink-0 items-center gap-1.5">
            {item.fonte === "intimacao" && !finalizado && (
              <button disabled={sugerindo === item.id} onClick={() => abrirPrazoSugerido(item)} className="btn-secondary text-xs">Revisar prazo</button>
            )}
            {precisaConferencia(item) && (
              <button onClick={() => conferirPrazo(item)} className="btn-secondary text-xs">{item.prioridade === "critica" ? "Conferir" : "Confirmar"}</button>
            )}
            {!finalizado && item.fonte !== "suspensao" && (
              <button onClick={() => concluir(item)} className="btn-primary text-xs">Concluir</button>
            )}
            <div className="relative">
              <button aria-label="Mais ações" title="Mais ações" onClick={() => setMenuItem(menuItem === key ? null : key)} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100">
                <MoreHorizontal className="h-4 w-4" />
              </button>
              {menuItem === key && (
                <div className="absolute right-0 z-30 mt-1 w-48 rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
                  {item.fonte === "prazo" && !finalizado && item.ciencia_confirmada !== true && (
                    <button className="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-50" onClick={() => { setMenuItem(null); darCiencia(item); }}>Dar ciência</button>
                  )}
                  {podeReagendar && <button className="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-50" onClick={() => { setMenuItem(null); setReagendar({ item, data: item.date?.slice(0,10) ?? '' }); }}>Reagendar</button>}
                  {podeAtribuir && <button className="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-50" onClick={() => { setMenuItem(null); setAtribuir({ item, responsavel_id: item.responsavel_id ?? '' }); }}>Atribuir responsável</button>}
                  {(item.fonte === "tarefa" || (item.fonte === "suspensao" && podeGerirSuspensoes)) && (
                    <button className="w-full rounded-lg px-3 py-2 text-left text-xs text-danger-600 hover:bg-danger-50" onClick={() => { setMenuItem(null); setExcluir(item); }}>Excluir</button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </article>
    );
  };

  return (
    <div className="mx-auto max-w-7xl px-6 py-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">Central operacional</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">Atividades</h1>
          <p className="mt-1 text-sm text-slate-500">Prazos, tarefas, compromissos e entradas jurídicas em um único fluxo.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <button onClick={() => setMenuFerramentas((v) => !v)} className="btn-secondary inline-flex items-center gap-2 text-sm">
              <Settings2 className="h-4 w-4" /> Ferramentas <ChevronDown className="h-3.5 w-3.5" />
            </button>
            {menuFerramentas && (
              <div className="absolute right-0 z-40 mt-1 w-56 rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
                <button onClick={() => { setMenuFerramentas(false); setSimulando(true); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-50"><Calculator className="h-4 w-4" /> Simular prazo</button>
                <button onClick={() => { setMenuFerramentas(false); capturarIntimacoes(); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-50"><RefreshCw className="h-4 w-4" /> Buscar intimações</button>
                <button disabled={exportando} onClick={() => { setMenuFerramentas(false); exportarCsv(); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-50"><Clock3 className="h-4 w-4" /> Exportar prazos CSV</button>
                {podeGerirSuspensoes && <button onClick={() => { setMenuFerramentas(false); setNovaSuspensao(true); }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs hover:bg-slate-50"><ShieldCheck className="h-4 w-4" /> Calendário jurídico</button>}
              </div>
            )}
          </div>
          <div className="relative">
            <button onClick={() => setMenuNovo((v) => !v)} className="btn-primary inline-flex items-center gap-2 text-sm"><Plus className="h-4 w-4" /> Novo <ChevronDown className="h-3.5 w-3.5" /></button>
            {menuNovo && (
              <div className="absolute right-0 z-40 mt-1 w-44 rounded-xl border border-slate-200 bg-white p-1 shadow-lg">
                <button className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => abrirNovo("prazo")}>Prazo</button>
                <button className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => abrirNovo("tarefa")}>Tarefa</button>
                <button className="w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-slate-50" onClick={() => abrirNovo("compromisso")}>Compromisso</button>
              </div>
            )}
          </div>
        </div>
      </div>

      {capturando && <div className="mt-4"><AvisoCapturaEmCurso /></div>}

      <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <button onClick={() => setTab("hoje")} className="rounded-2xl border border-danger-100 bg-white p-4 text-left hover:shadow-sm"><div className="text-2xl font-semibold text-danger-700">{radar.hoje}</div><div className="text-xs font-medium text-slate-500">Vencendo hoje</div></button>
        <button onClick={() => setTab("entrada")} className="rounded-2xl border border-warn-100 bg-white p-4 text-left hover:shadow-sm"><div className="text-2xl font-semibold text-warn-700">{radar.conferencia}</div><div className="text-xs font-medium text-slate-500">Aguardando conferência</div></button>
        <button onClick={() => setTab("entrada")} className="rounded-2xl border border-primary-100 bg-white p-4 text-left hover:shadow-sm"><div className="text-2xl font-semibold text-primary-700">{radar.intimacoes}</div><div className="text-xs font-medium text-slate-500">Intimações pendentes</div></button>
        <button onClick={() => setTab("calendario")} title="Enquanto a Agenda v2 não estiver migrada, a detecção usa mesma data e mesmo horário inicial." className="rounded-2xl border border-slate-200 bg-white p-4 text-left hover:shadow-sm"><div className="text-2xl font-semibold text-slate-700">{radar.conflitos}</div><div className="text-xs font-medium text-slate-500">Coincidências de agenda</div></button>
      </div>

      <div className="mt-5 flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-3 lg:flex-row lg:items-center">
        <div className="flex flex-wrap gap-1">
          {ABAS.map(({ key, label, icon: Icon }) => (
            <button key={key} onClick={() => setTab(key)} className={`inline-flex items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium ${tab === key ? 'bg-primary-900 text-white' : 'text-slate-600 hover:bg-slate-50'}`}><Icon className="h-4 w-4" />{label}</button>
          ))}
        </div>
        <div className="relative min-w-0 flex-1 lg:ml-2">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
          <input value={busca} onChange={(e) => setBusca(e.target.value)} className="input w-full pl-9 text-sm" placeholder="Buscar atividade, caso ou responsável..." />
        </div>
        <div className="flex items-center gap-1 rounded-xl bg-slate-50 p-1">
          {([['todos','Todos'],['meus','Meus'],['equipe','Equipe']] as const).map(([key,label]) => <button key={key} onClick={() => setEscopo(key)} className={`rounded-lg px-2.5 py-1.5 text-xs font-medium ${escopo === key ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500'}`}>{label}</button>)}
        </div>
        <button onClick={() => setFiltrosAbertos((v) => !v)} className="btn-secondary inline-flex items-center gap-2 text-xs"><Filter className="h-3.5 w-3.5" /> Filtros</button>
      </div>

      {filtrosAbertos && (
        <div className="mt-2 grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-3 sm:grid-cols-2 lg:grid-cols-4">
          <select className="input text-sm" value={filtroTipo} onChange={(e) => setFiltroTipo(e.target.value)}><option value="todos">Todos os tipos</option>{Object.entries(TIPO_LABEL).map(([k,v]) => <option key={k} value={k}>{v}</option>)}</select>
          <select className="input text-sm" value={filtroSituacao} onChange={(e) => setFiltroSituacao(e.target.value)}><option value="todos">Todas as situações</option><option value="pendente">Pendente</option><option value="andamento">Em andamento</option><option value="concluido">Concluído</option><option value="cancelado">Cancelado</option></select>
          <select className="input text-sm" value={filtroUrgencia} onChange={(e) => setFiltroUrgencia(e.target.value)}><option value="todos">Todas as urgências</option><option value="vencido">Vencido</option><option value="critico">Crítico</option><option value="atencao">Atenção</option><option value="normal">Normal</option></select>
          <select className="input text-sm" value={filtroResponsavel} onChange={(e) => setFiltroResponsavel(e.target.value)}><option value="">Todos os responsáveis</option>{responsaveis.map((r) => <option key={r.id} value={r.id}>{r.nome}</option>)}</select>
        </div>
      )}

      <div className="mt-4">
        {loading ? <Spinner /> : error ? <ErrorState message="Não foi possível carregar as atividades." onRetry={load} /> : tab === "calendario" ? <CalendarGrid items={filtrados} /> : (
          <div className="overflow-visible rounded-2xl border border-slate-200 bg-white">
            {filtrados.length ? filtrados.map(renderItem) : <div className="px-6 py-16 text-center"><CheckCircle2 className="mx-auto h-9 w-9 text-success-400" /><p className="mt-3 text-sm font-medium text-slate-600">Nenhuma atividade encontrada</p><p className="mt-1 text-xs text-slate-400">Ajuste os filtros ou crie uma nova atividade.</p></div>}
          </div>
        )}
      </div>

      {tab === "entrada" && conflitos.length > 0 && (
        <div className="mt-4 rounded-2xl border border-warn-200 bg-warn-50 p-4 text-sm text-warn-800">
          <div className="flex items-start gap-2"><AlertTriangle className="mt-0.5 h-4 w-4" /><div><strong>{conflitos.length} coincidência(s) de agenda detectada(s).</strong><p className="mt-1 text-xs text-warn-700">Esta verificação ainda usa data + horário inicial. A sobreposição real de intervalos será ativada somente após a migration temporal da Agenda v2.</p></div></div>
        </div>
      )}

      <Modal open={modalNovo} onClose={() => setModalNovo(false)} title={form.categoria === "prazo" ? "Novo prazo" : form.categoria === "tarefa" ? "Nova tarefa" : "Novo compromisso"}>
        <div className="space-y-3">
          {contextCaseId && <div className="rounded-lg border border-primary-100 bg-primary-50 px-3 py-2 text-xs text-primary-700">Será vinculado ao caso atualmente aberto.</div>}
          <input className="input w-full text-sm" placeholder="Título *" value={form.titulo} onChange={(e) => setForm({ ...form, titulo: e.target.value })} />
          {form.categoria === "compromisso" && <select className="input w-full text-sm" value={form.tipo_evento} onChange={(e) => setForm({ ...form, tipo_evento: e.target.value })}><option value="compromisso">Compromisso</option><option value="audiencia">Audiência</option><option value="reuniao">Reunião</option><option value="diligencia">Diligência</option><option value="outro">Outro</option></select>}
          {form.categoria === "prazo" && <div className="grid grid-cols-2 gap-2"><select className="input text-sm" value={form.tipo_prazo} onChange={(e) => setForm({ ...form, tipo_prazo: e.target.value })}><option value="processual">Processual</option><option value="administrativo">Administrativo</option><option value="interno">Interno</option><option value="prescricao">Prescrição</option></select><select className="input text-sm" value={form.prioridade} onChange={(e) => setForm({ ...form, prioridade: e.target.value })}><option value="baixa">Prioridade baixa</option><option value="media">Prioridade média</option><option value="alta">Prioridade alta</option><option value="critica">Prioridade crítica</option></select></div>}
          {form.categoria === "tarefa" && <select className="input w-full text-sm" value={form.prioridade} onChange={(e) => setForm({ ...form, prioridade: e.target.value })}><option value="baixa">Prioridade baixa</option><option value="media">Prioridade média</option><option value="alta">Prioridade alta</option></select>}
          <div className="grid grid-cols-2 gap-2"><input type="date" className="input text-sm" value={form.data} onChange={(e) => setForm({ ...form, data: e.target.value })} />{form.categoria === "compromisso" ? <input type="time" className="input text-sm" value={form.hora} onChange={(e) => setForm({ ...form, hora: e.target.value })} /> : form.categoria === "prazo" && form.tipo_prazo === "processual" ? <select className="input text-sm" value={form.regime_calculo} onChange={(e) => setForm({ ...form, regime_calculo: e.target.value })}><option value="">Regime *</option><option value="civel">Cível / CPC</option><option value="trabalhista">Trabalhista / CLT</option><option value="penal">Penal / CPP</option></select> : <div />}</div>
          {form.categoria === "prazo" && form.prioridade === "critica" && form.tipo_prazo === "processual" && <div><label className="mb-1 block text-xs font-medium text-slate-600">Termo inicial *</label><input type="date" className="input w-full text-sm" value={form.termo_inicial} onChange={(e) => setForm({ ...form, termo_inicial: e.target.value })} /><p className="mt-1 text-[11px] text-slate-400">Prazo crítico permanece sujeito a segunda conferência.</p></div>}
          <button className="inline-flex items-center gap-1 text-xs font-medium text-primary-700" onClick={() => setMaisOpcoes((v) => !v)}><ChevronDown className={`h-3.5 w-3.5 transition-transform ${maisOpcoes ? 'rotate-180' : ''}`} /> Mais opções</button>
          {maisOpcoes && <div className="space-y-3 rounded-xl bg-slate-50 p-3">{form.categoria === "compromisso" && <input className="input w-full text-sm" placeholder="Local" value={form.local} onChange={(e) => setForm({ ...form, local: e.target.value })} />}{form.categoria !== "compromisso" && responsaveis.length > 0 && <select className="input w-full text-sm" value={form.responsavel_id} onChange={(e) => setForm({ ...form, responsavel_id: e.target.value })}><option value="">Responsável atual</option>{responsaveis.map((r) => <option key={r.id} value={r.id}>{r.nome}</option>)}</select>}{form.categoria === "prazo" && <><div><label className="mb-1 block text-xs font-medium text-slate-600">Publicação oficial</label><input type="date" className="input w-full text-sm" value={form.data_publicacao} onChange={(e) => setForm({ ...form, data_publicacao: e.target.value })} /></div>{!(form.prioridade === "critica" && form.tipo_prazo === "processual") && <div><label className="mb-1 block text-xs font-medium text-slate-600">Termo inicial</label><input type="date" className="input w-full text-sm" value={form.termo_inicial} onChange={(e) => setForm({ ...form, termo_inicial: e.target.value })} /></div>}<input className="input w-full text-sm" placeholder="Base legal" value={form.base_legal} onChange={(e) => setForm({ ...form, base_legal: e.target.value })} /></>}<textarea className="input min-h-20 w-full text-sm" placeholder="Descrição / observações" value={form.descricao} onChange={(e) => setForm({ ...form, descricao: e.target.value })} /></div>}
          {form.categoria === "compromisso" && <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-[11px] text-slate-500">Duração, recorrência e lembretes avançados já possuem motor temporal preparado, mas só serão persistidos após a migration da Agenda v2 ser legalmente liberada.</div>}
          <div className="flex justify-end gap-2"><button className="btn-ghost" onClick={() => setModalNovo(false)}>Cancelar</button><button className="btn-primary" onClick={salvarNovo}>Salvar</button></div>
        </div>
      </Modal>

      <Modal open={reagendar !== null} onClose={() => setReagendar(null)} title="Reagendar">
        {reagendar && <div className="space-y-3"><p className="text-sm text-slate-600">{reagendar.item.titulo}</p><input type="date" className="input w-full" value={reagendar.data} onChange={(e) => setReagendar({ ...reagendar, data: e.target.value })} /><div className="flex justify-end gap-2"><button className="btn-ghost" onClick={() => setReagendar(null)}>Cancelar</button><button className="btn-primary" onClick={salvarReagendamento}>Salvar</button></div></div>}
      </Modal>

      <Modal open={atribuir !== null} onClose={() => setAtribuir(null)} title="Atribuir responsável">
        {atribuir && <div className="space-y-3"><p className="text-sm text-slate-600">{atribuir.item.titulo}</p><select className="input w-full" value={atribuir.responsavel_id} onChange={(e) => setAtribuir({ ...atribuir, responsavel_id: e.target.value })}><option value="">Selecione...</option>{responsaveis.map((r) => <option key={r.id} value={r.id}>{r.nome}{r.role ? ` (${r.role})` : ''}</option>)}</select><div className="flex justify-end gap-2"><button className="btn-ghost" onClick={() => setAtribuir(null)}>Cancelar</button><button className="btn-primary" onClick={salvarAtribuicao}>Salvar</button></div></div>}
      </Modal>

      <ConfirmModal open={excluir !== null} onClose={() => setExcluir(null)} onConfirm={confirmarExclusao} title={excluir?.fonte === "suspensao" ? "Remover suspensão" : "Excluir tarefa"} message={excluir ? `“${excluir.titulo}” será removido. Confirme para continuar.` : undefined} confirmLabel="Confirmar" loading={excluindo} />
      <PrazoSugeridoModal sugestao={sugestao} onClose={() => setSugestao(null)} onResolvido={load} />
      <SimularPrazoModal open={simulando} onClose={() => setSimulando(false)} />
      <SuspensaoFormModal open={novaSuspensao} onClose={() => setNovaSuspensao(false)} onCriada={load} />
    </div>
  );
}
