import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  startOfMonth,
  startOfWeek,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import {
  BarChart3,
  BookOpen,
  Briefcase,
  CalendarClock,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderKanban,
  FilePlus2,
  Plus,
  Scale,
  Sparkles,
  Upload,
  Users,
  Zap,
} from "lucide-react";
import { Link, useNavigate } from "react-router";
import { toast } from "../components/Toast";
import { officeBranding } from "../config/officeBranding";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useAuth } from "../stores/auth";
import { EntradaInteligente } from "./EntradaUnica";

/**
 * Início canônico do EJC — referência visual premium DPT (18/09/2026).
 *
 * Composição idêntica ao mockup aprovado pelo Titular: saudação, hero da
 * Entrada Única, quatro sinais operacionais, Agenda e Prazos, Casos em
 * destaque, Acesso rápido e coluna lateral (manifesto, calendário, rotina e
 * citação institucional). Todos os números vêm de endpoints reais; fonte
 * indisponível degrada para "—" (nunca zero falso), espelhando o contrato do
 * GET /dashboard (campo `degradado`).
 */

type Atividade = {
  id?: string;
  tipo?: string;
  titulo?: string;
  date?: string | null;
  status?: string;
  case_id?: string | null;
  caso_titulo?: string | null;
  urgencia?: string;
  dias_restantes?: number | null;
};

type CasoResumo = {
  id?: string;
  titulo?: string;
  status?: string;
  area?: string;
  prioridade?: string;
  risco?: string | null;
  proxima_acao?: string | null;
  proxima_acao_prazo?: string | null;
  numero_processo?: string | null;
  numero_interno?: string | null;
  created_at?: string | null;
};

type Tarefa = {
  id: string;
  titulo?: string;
  status?: string;
  prioridade?: string;
  data_limite?: string | null;
  concluida_em?: string | null;
};

type Kpis = {
  casos?: { ativos?: number };
  clientes_ativos?: number;
};

type AbaAgenda = "hoje" | "amanha" | "semana";

const ROTULO_TIPO: Record<string, string> = {
  prazo: "Prazo",
  tarefa: "Tarefa",
  intimacao: "Intimação",
  movimentacao: "Movimentação",
  evento: "Agenda",
};

const DIAS_CURTOS = ["D", "S", "T", "Q", "Q", "S", "S"];

function horaDe(date?: string | null): string {
  if (!date) return "—";
  const m = date.match(/[T ](\d{2}:\d{2})/);
  return m ? m[1] : "—";
}

function pontoClasse(a: Atividade): string {
  if (a.tipo === "tarefa") return "is-green";
  if (a.tipo === "intimacao" || a.tipo === "movimentacao") return "is-blue";
  if (a.urgencia === "vencido" || a.urgencia === "critico") return "is-red";
  if (a.urgencia === "atencao") return "is-orange";
  return "is-gold";
}

function chipDeCaso(status?: string): { rotulo: string; classe: string } {
  if (status === "encerrado") return { rotulo: "Concluso", classe: "is-gold" };
  if (status === "arquivado") return { rotulo: "Arquivado", classe: "is-gray" };
  return { rotulo: "Em andamento", classe: "is-green" };
}

function dataDaAba(aba: AbaAgenda): string {
  const base =
    aba === "amanha" ? new Date(Date.now() + 86_400_000) : new Date();
  return format(base, "dd 'de' MMMM 'de' yyyy", { locale: ptBR });
}

function semanaDaAba(aba: AbaAgenda): string {
  if (aba !== "semana") return "";
  const inicio = new Date();
  const fim = new Date(Date.now() + 6 * 86_400_000);
  return `${format(inicio, "dd")} a ${format(fim, "dd 'de' MMMM", {
    locale: ptBR,
  })}`;
}

function saudacaoPorHora(): string {
  const hora = new Date().getHours();
  if (hora < 12) return "Bom dia";
  if (hora < 18) return "Boa tarde";
  return "Boa noite";
}

function scoreCaso(caso: CasoResumo, atividades: Atividade[] | null): number {
  let score = 0;
  const status = (caso.status ?? "").toLowerCase();
  const prioridade = (caso.prioridade ?? "").toLowerCase();
  const risco = (caso.risco ?? "").toLowerCase();

  if (status === "encerrado" || status === "arquivado") score -= 100;
  else score += 40;

  if (prioridade === "urgente") score += 30;
  else if (prioridade === "alta") score += 20;

  if (risco === "critico" || risco === "crítico") score += 35;
  else if (risco === "alto") score += 25;

  if (caso.proxima_acao_prazo) {
    const prazo = Date.parse(caso.proxima_acao_prazo);
    if (!Number.isNaN(prazo)) {
      const dias = Math.ceil((prazo - Date.now()) / 86_400_000);
      if (dias < 0) score += 100;
      else if (dias === 0) score += 90;
      else if (dias <= 3) score += 70;
      else if (dias <= 7) score += 45;
      else if (dias <= 30) score += 15;
    }
  }

  for (const atividade of atividades ?? []) {
    if (!caso.id || atividade.case_id !== caso.id) continue;
    const dias = atividade.dias_restantes;
    if (atividade.urgencia === "vencido") score += 120;
    else if (atividade.urgencia === "critico") score += 95;
    else if (atividade.urgencia === "atencao") score += 55;
    if (dias !== null && dias !== undefined) {
      if (dias < 0) score += 120;
      else if (dias === 0) score += 85;
      else if (dias <= 3) score += 60;
      else if (dias <= 7) score += 35;
    }
  }

  return score;
}

function scoreTarefaHoje(tarefa: Tarefa, hoje: string): number {
  let score = 0;
  const prioridade = (tarefa.prioridade ?? "").toLowerCase();
  if (prioridade === "urgente") score += 50;
  else if (prioridade === "alta") score += 30;

  const limite = tarefa.data_limite?.slice(0, 10);
  if (!limite) score += 10;
  else if (limite < hoje) score += 80;
  else if (limite === hoje) score += 60;

  if (tarefa.status === "concluida") score -= 5;
  return score;
}

export default function DashboardUltra() {
  const user = useAuth((state) => state.user);
  const navigate = useNavigate();

  const [carregado, setCarregado] = useState(false);
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [atividades, setAtividades] = useState<Atividade[] | null>(null);
  const [casos, setCasos] = useState<CasoResumo[] | null>(null);
  const [documentosRecentes, setDocumentosRecentes] = useState<number | null>(
    null,
  );
  const [tarefas, setTarefas] = useState<Tarefa[] | null>(null);
  const [aba, setAba] = useState<AbaAgenda>("hoje");
  const [diaSelecionado, setDiaSelecionado] = useState<string | null>(null);
  const [mesOffset, setMesOffset] = useState(0);

  const carregar = useCallback(async () => {
    const inicioDocs = format(
      new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
      "yyyy-MM-dd",
    );
    const [rKpis, rAtiv, rCasos, rDocs, rTarefas] = await Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/atividades", { params: { apenas_pendentes: true } }),
      api.get("/cases/", { params: { page: 1, page_size: 20 } }),
      api.get("/documents/", {
        params: { page: 1, page_size: 1, data_inicio: inicioDocs },
      }),
      api.get("/tasks/", { params: { minhas: true } }),
    ]);
    setKpis(rKpis.status === "fulfilled" ? (rKpis.value.data as Kpis) : null);
    setAtividades(
      rAtiv.status === "fulfilled" ? asList<Atividade>(rAtiv.value.data) : null,
    );
    setCasos(
      rCasos.status === "fulfilled"
        ? asList<CasoResumo>(rCasos.value.data)
        : null,
    );
    setDocumentosRecentes(
      rDocs.status === "fulfilled"
        ? ((rDocs.value.data as { total?: number })?.total ?? null)
        : null,
    );
    setTarefas(
      rTarefas.status === "fulfilled" ? asList<Tarefa>(rTarefas.value.data) : null,
    );
    setCarregado(true);
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const alternarTarefa = useCallback(async (tarefa: Tarefa) => {
    const novoStatus = tarefa.status === "concluida" ? "a_fazer" : "concluida";
    const novoConcluidaEm =
      novoStatus === "concluida" ? new Date().toISOString() : null;
    setTarefas((atual) =>
      (atual ?? []).map((item) =>
        item.id === tarefa.id
          ? { ...item, status: novoStatus, concluida_em: novoConcluidaEm }
          : item,
      ),
    );
    try {
      await api.patch(`/tasks/${tarefa.id}`, { status: novoStatus });
    } catch {
      setTarefas((atual) =>
        (atual ?? []).map((item) =>
          item.id === tarefa.id
            ? {
                ...item,
                status: tarefa.status,
                concluida_em: tarefa.concluida_em ?? null,
              }
            : item,
        ),
      );
      toast.error("Não foi possível atualizar a tarefa.");
    }
  }, []);

  const primeiroNome = user?.full_name?.trim().split(/\s+/)[0] || "usuário";

  const prazosHoje = useMemo(() => {
    if (!atividades) return null;
    return atividades.filter(
      (a) => a.tipo === "prazo" && a.dias_restantes === 0,
    ).length;
  }, [atividades]);

  const agendaFiltrada = useMemo(() => {
    if (!atividades) return null;
    if (diaSelecionado) {
      return atividades
        .filter((a) => a.date?.slice(0, 10) === diaSelecionado)
        .slice(0, 6);
    }
    const dentroDaAba = atividades.filter((a) => {
      const d = a.dias_restantes;
      if (aba === "hoje") return d === 0;
      if (aba === "amanha") return d === 1;
      return d !== null && d !== undefined && d >= 2 && d <= 7;
    });
    return dentroDaAba.slice(0, 6);
  }, [atividades, aba, diaSelecionado]);

  const casosEmDestaque = useMemo(() => {
    if (!casos) return null;
    return casos
      .map((caso, index) => ({
        caso,
        index,
        score: scoreCaso(caso, atividades),
      }))
      .sort((a, b) => {
        if (b.score !== a.score) return b.score - a.score;
        const aCriado = Date.parse(a.caso.created_at ?? "") || 0;
        const bCriado = Date.parse(b.caso.created_at ?? "") || 0;
        if (bCriado !== aCriado) return bCriado - aCriado;
        return a.index - b.index;
      })
      .slice(0, 4)
      .map(({ caso }) => caso);
  }, [casos, atividades]);

  const hoje = format(new Date(), "yyyy-MM-dd");
  const rotinaHoje = useMemo(() => {
    if (!tarefas) return [];
    return tarefas
      .filter((tarefa) => {
        if (tarefa.status === "concluida") {
          return tarefa.concluida_em?.slice(0, 10) === hoje;
        }
        const limite = tarefa.data_limite?.slice(0, 10);
        return !limite || limite <= hoje;
      })
      .sort((a, b) => scoreTarefaHoje(b, hoje) - scoreTarefaHoje(a, hoje))
      .slice(0, 5);
  }, [tarefas, hoje]);

  const rotinaPendentes = rotinaHoje.filter((t) => t.status !== "concluida");
  const rotinaConcluidas = rotinaHoje.filter((t) => t.status === "concluida");
  const rotinaTotal = rotinaHoje.length;
  const rotinaFeitas = rotinaConcluidas.length;

  const mesVisivel = useMemo(
    () => addMonths(startOfMonth(new Date()), mesOffset),
    [mesOffset],
  );
  const diasDoMes = useMemo(() => {
    const inicio = startOfWeek(startOfMonth(mesVisivel), { weekStartsOn: 0 });
    const fim = endOfWeek(endOfMonth(mesVisivel), { weekStartsOn: 0 });
    return eachDayOfInterval({ start: inicio, end: fim });
  }, [mesVisivel]);
  const diasComAtividade = useMemo(() => {
    if (!atividades) return new Set<string>();
    return new Set(
      atividades
        .filter((a) => a.date)
        .map((a) => (a.date as string).slice(0, 10)),
    );
  }, [atividades]);

  const canUseLegal = useMemo(() => {
    const roles = new Set(["superadmin", "admin", "socio", "advogado"]);
    return roles.has(user?.role || "");
  }, [user?.role]);
  const canUseEntry = useMemo(() => {
    const roles = new Set([
      "superadmin",
      "admin",
      "socio",
      "advogado",
      "secretaria",
    ]);
    return roles.has(user?.role || "");
  }, [user?.role]);

  const valorOuTraco = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : String(v);

  return (
    <div className="ejc-dash">
      <header className="ejc-dash__greeting" aria-label="Saudação do dia">
        <div>
          <h1>
            {saudacaoPorHora()}, {primeiroNome}!
          </h1>
          <p>Disciplina hoje. Grandes conquistas sempre.</p>
        </div>
        <div className="ejc-dash__greeting-tag" aria-hidden="true">
          <span>Conhecimento</span>
          <span>Estratégia</span>
          <span>Resultados reais</span>
        </div>
      </header>

      <section
        className="ejc-dash__entry"
        aria-label="Entrada Única"
      >
        <div className="ejc-dash__entry-head">
          <span className="ejc-dash__entry-icon" aria-hidden="true">
            <FilePlus2 />
          </span>
          <div className="ejc-dash__entry-copy">
            <h2>Entrada Única</h2>
            <p>Descreva o caso, envie documentos ou inicie um atendimento.</p>
          </div>
          <span className="ejc-dash__entry-tag" aria-hidden="true">
            Uma solução.
            <br />
            Todas as possibilidades.
          </span>
        </div>

        {canUseLegal ? (
          <div className="ejc-dash__entry-body">
            <EntradaInteligente embedded />
          </div>
        ) : canUseEntry ? (
          <div className="ejc-dash__entry-body ejc-dash__entry-body--plain">
            <p>
              Use a Entrada Única para cadastro manual de cliente e caso, sem
              depender de IA.
            </p>
            <Link to="/entrada" className="ejc-dash__entry-cta">
              Abrir Entrada Única
            </Link>
          </div>
        ) : (
          <div className="ejc-dash__entry-body ejc-dash__entry-body--plain">
            <p>A Entrada Única está disponível apenas aos perfis autorizados.</p>
          </div>
        )}

        {canUseEntry && (
          <div className="ejc-dash__entry-chips">
            {canUseLegal && (
              <Link to="/casos/novo" className="ejc-dash__chip">
                <Plus aria-hidden="true" /> Novo caso
              </Link>
            )}
            <Link to="/cadastro-manual" className="ejc-dash__chip">
              <Users aria-hidden="true" /> Novo cliente
            </Link>
            <Link to="/documentos" className="ejc-dash__chip">
              <Upload aria-hidden="true" /> Enviar documentos
            </Link>
            {canUseLegal && (
              <Link to="/entrada" className="ejc-dash__chip">
                <Sparkles aria-hidden="true" /> Analisar
              </Link>
            )}
          </div>
        )}
      </section>

      <section className="ejc-dash__stats" aria-label="Sinais do escritório">
        <Link
          to="/atividades?tipo=prazo"
          className="ejc-dash__stat is-dark"
          aria-label={`Prazos hoje: ${valorOuTraco(prazosHoje)}`}
        >
          <span className="ejc-dash__stat-icon" aria-hidden="true">
            <CalendarClock />
          </span>
          <strong>{valorOuTraco(prazosHoje)}</strong>
          <small>Prazos hoje</small>
          <ChevronRight className="ejc-dash__stat-chev" aria-hidden="true" />
        </Link>
        <Link
          to="/clientes"
          className="ejc-dash__stat"
          aria-label={`Clientes ativos: ${valorOuTraco(kpis?.clientes_ativos)}`}
        >
          <span className="ejc-dash__stat-icon" aria-hidden="true">
            <Users />
          </span>
          <strong>{valorOuTraco(kpis?.clientes_ativos)}</strong>
          <small>Clientes ativos</small>
          <ChevronRight className="ejc-dash__stat-chev" aria-hidden="true" />
        </Link>
        <Link
          to="/casos"
          className="ejc-dash__stat"
          aria-label={`Casos em andamento: ${valorOuTraco(kpis?.casos?.ativos)}`}
        >
          <span className="ejc-dash__stat-icon" aria-hidden="true">
            <FolderKanban />
          </span>
          <strong>{valorOuTraco(kpis?.casos?.ativos)}</strong>
          <small>Casos em andamento</small>
          <ChevronRight className="ejc-dash__stat-chev" aria-hidden="true" />
        </Link>
        <Link
          to="/documentos"
          className="ejc-dash__stat"
          aria-label={`Documentos recentes: ${valorOuTraco(documentosRecentes)}`}
        >
          <span className="ejc-dash__stat-icon" aria-hidden="true">
            <FileText />
          </span>
          <strong>{valorOuTraco(documentosRecentes)}</strong>
          <small>Documentos recentes</small>
          <ChevronRight className="ejc-dash__stat-chev" aria-hidden="true" />
        </Link>
      </section>

      <div className="ejc-dash__panels">
        <section className="ejc-dash__panel" aria-label="Agenda e Prazos">
          <div className="ejc-dash__panel-head">
            <div className="ejc-dash__panel-title">
              <span className="ejc-dash__panel-ico" aria-hidden="true">
                <CalendarDays />
              </span>
              <h3>Agenda e Prazos</h3>
            </div>
            <Link to="/atividades" className="ejc-dash__panel-more">
              Ver todos <ChevronRight aria-hidden="true" />
            </Link>
          </div>
          <div className="ejc-dash__panel-tools">
            <div className="ejc-dash__tabs" role="tablist" aria-label="Período">
              {(
                [
                  ["hoje", "Hoje"],
                  ["amanha", "Amanhã"],
                  ["semana", "Esta semana"],
                ] as const
              ).map(([valor, rotulo]) => (
                <button
                  key={valor}
                  type="button"
                  role="tab"
                  aria-selected={aba === valor}
                  className={aba === valor ? "is-active" : ""}
                  onClick={() => {
                    setDiaSelecionado(null);
                    setAba(valor);
                  }}
                >
                  {rotulo}
                </button>
              ))}
            </div>
            {diaSelecionado ? (
              <button
                type="button"
                className="ejc-dash__date-filter"
                onClick={() => setDiaSelecionado(null)}
                aria-label="Remover filtro de data"
              >
                {format(new Date(`${diaSelecionado}T12:00:00`), "dd/MM/yyyy")}
                <span aria-hidden="true">×</span>
              </button>
            ) : (
              <p className="ejc-dash__panel-date" aria-hidden="true">
                {aba === "semana" ? (
                  <strong>{semanaDaAba(aba)}</strong>
                ) : (
                  <>
                    <strong>{dataDaAba(aba)}</strong>
                    <span>
                      {format(
                        aba === "amanha"
                          ? new Date(Date.now() + 86_400_000)
                          : new Date(),
                        "EEEE",
                        { locale: ptBR },
                      )}
                    </span>
                  </>
                )}
              </p>
            )}
          </div>
          <ol className="ejc-dash__timeline">
            {agendaFiltrada === null ? (
              <li className="ejc-dash__empty">Agenda indisponível agora.</li>
            ) : agendaFiltrada.length === 0 ? (
              <li className="ejc-dash__empty">
                Nada na agenda para o período.
              </li>
            ) : (
              agendaFiltrada.map((a) => (
                <li key={a.id ?? `${a.tipo}-${a.titulo}`}>
                  <button
                    type="button"
                    onClick={() =>
                      a.case_id
                        ? navigate(`/casos/${a.case_id}`)
                        : navigate("/atividades")
                    }
                  >
                    <time>{horaDe(a.date)}</time>
                    <span className={`ejc-dash__dot ${pontoClasse(a)}`} />
                    <span className="ejc-dash__item">
                      <strong>{a.titulo || "Atividade"}</strong>
                      <small>
                        {a.caso_titulo
                          ? a.caso_titulo
                          : ROTULO_TIPO[a.tipo ?? ""] ?? "Atividade"}
                      </small>
                    </span>
                    <ChevronRight aria-hidden="true" />
                  </button>
                </li>
              ))
            )}
          </ol>
        </section>

        <section className="ejc-dash__panel" aria-label="Casos em destaque">
          <div className="ejc-dash__panel-head">
            <div className="ejc-dash__panel-title">
              <span className="ejc-dash__panel-ico" aria-hidden="true">
                <Briefcase />
              </span>
              <h3>Casos em destaque</h3>
            </div>
            <Link to="/casos" className="ejc-dash__panel-more">
              Ver todos <ChevronRight aria-hidden="true" />
            </Link>
          </div>
          <ul className="ejc-dash__cases">
            {casosEmDestaque === null ? (
              <li className="ejc-dash__empty">Casos indisponíveis agora.</li>
            ) : casosEmDestaque.length === 0 ? (
              <li className="ejc-dash__empty">Nenhum caso cadastrado ainda.</li>
            ) : (
              casosEmDestaque.map((c) => {
                const chip = chipDeCaso(c.status);
                const meta =
                  c.numero_processo
                    ? `Proc. nº ${c.numero_processo}`
                    : c.numero_interno
                      ? `Caso ${c.numero_interno}`
                      : "";
                return (
                  <li key={c.id ?? c.titulo}>
                    <button
                      type="button"
                      onClick={() => c.id && navigate(`/casos/${c.id}`)}
                    >
                      <span className={`ejc-dash__case-chip ${chip.classe}`}>
                        {chip.rotulo}
                      </span>
                      <strong>{c.titulo || "Caso sem título"}</strong>
                      <small>
                        {[
                          meta,
                          c.area
                            ? c.area.charAt(0).toUpperCase() + c.area.slice(1)
                            : "",
                          c.proxima_acao ? `Próxima: ${c.proxima_acao}` : "",
                        ]
                          .filter(Boolean)
                          .join("  ·  ")}
                      </small>
                      <ChevronRight aria-hidden="true" />
                    </button>
                  </li>
                );
              })
            )}
          </ul>
        </section>
      </div>

      <section className="ejc-dash__quick" aria-label="Acesso rápido">
        <div className="ejc-dash__quick-head">
          <Zap aria-hidden="true" />
          <strong>Acesso rápido</strong>
        </div>
        <div className="ejc-dash__quick-items">
          <Link to="/casos/novo">
            <span aria-hidden="true">
              <Plus />
            </span>
            Novo caso
          </Link>
          <Link to="/cadastro-manual">
            <span aria-hidden="true">
              <Users />
            </span>
            Novo cliente
          </Link>
          <Link to="/pecas">
            <span aria-hidden="true">
              <FileText />
            </span>
            Gerar documento
          </Link>
          <Link to="/inteligencia?tab=pesquisa">
            <span aria-hidden="true">
              <Scale />
            </span>
            Consultar jurisprudência
          </Link>
          <Link to="/teses">
            <span aria-hidden="true">
              <BookOpen />
            </span>
            Buscar no banco de teses
          </Link>
          <Link to="/financeiro">
            <span aria-hidden="true">
              <BarChart3 />
            </span>
            Relatório financeiro
          </Link>
        </div>
      </section>

      <aside className="ejc-dash__side" aria-label="Painel lateral">
        <div className="ejc-dash__manifesto">
          <img
            src="/brand/dashboard-themis.jpg"
            alt=""
            aria-hidden="true"
            loading="lazy"
          />
          <p>
            Direito
            <br />
            que constrói
            <br />
            possibilidades.
          </p>
        </div>

        <div className="ejc-dash__calendar">
          <div className="ejc-dash__calendar-head">
            <strong>
              {(() => {
                const mes = format(mesVisivel, "MMMM 'de' yyyy", {
                  locale: ptBR,
                });
                return mes.charAt(0).toUpperCase() + mes.slice(1);
              })()}
            </strong>
            <span>
              <button
                type="button"
                aria-label="Mês anterior"
                onClick={() => setMesOffset((v) => v - 1)}
              >
                <ChevronLeft aria-hidden="true" />
              </button>
              <button
                type="button"
                aria-label="Mês seguinte"
                onClick={() => setMesOffset((v) => v + 1)}
              >
                <ChevronRight aria-hidden="true" />
              </button>
            </span>
          </div>
          <div className="ejc-dash__calendar-grid" role="grid">
            {DIAS_CURTOS.map((d, i) => (
              <span key={`${d}-${i}`} className="ejc-dash__calendar-dow">
                {d}
              </span>
            ))}
            {diasDoMes.map((dia) => {
              const chave = format(dia, "yyyy-MM-dd");
              const temAtividade = diasComAtividade.has(chave);
              const classes = ["ejc-dash__calendar-day"];
              if (!isSameMonth(dia, mesVisivel)) classes.push("is-out");
              if (temAtividade) classes.push("has-event");
              if (diaSelecionado === chave) classes.push("is-selected");
              return (
                <button
                  key={chave}
                  type="button"
                  className={classes.join(" ")}
                  aria-label={format(dia, "dd/MM/yyyy")}
                  aria-pressed={diaSelecionado === chave}
                  aria-current={
                    chave === format(new Date(), "yyyy-MM-dd")
                      ? "date"
                      : undefined
                  }
                  onClick={() =>
                    setDiaSelecionado((atual) => (atual === chave ? null : chave))
                  }
                >
                  {format(dia, "d")}
                  {temAtividade && <i aria-hidden="true" />}
                </button>
              );
            })}
          </div>
        </div>

        <div className="ejc-dash__routine">
          <div className="ejc-dash__routine-head">
            <strong>Minha rotina hoje</strong>
            <small>
              {carregado && tarefas
                ? `${rotinaFeitas} de ${rotinaTotal} concluídas`
                : "carregando…"}
            </small>
          </div>
          <div className="ejc-dash__routine-bar" aria-hidden="true">
            <i
              style={{
                width:
                  rotinaTotal > 0
                    ? `${Math.round((rotinaFeitas / rotinaTotal) * 100)}%`
                    : "0%",
              }}
            />
          </div>
          <ul>
            {rotinaPendentes.map((t) => (
              <li key={t.id}>
                <button type="button" onClick={() => void alternarTarefa(t)}>
                  <span className="ejc-dash__check" aria-hidden="true" />
                  {t.titulo || "Tarefa"}
                </button>
              </li>
            ))}
            {rotinaConcluidas.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  className="is-done"
                  onClick={() => void alternarTarefa(t)}
                >
                  <span className="ejc-dash__check" aria-hidden="true" />
                  {t.titulo || "Tarefa"}
                </button>
              </li>
            ))}
            {carregado && tarefas && rotinaTotal === 0 && (
              <li className="ejc-dash__empty">Nenhuma tarefa sua por agora.</li>
            )}
          </ul>
        </div>

        <div className="ejc-dash__quote">
          <span aria-hidden="true">“</span>
          <p>Segurança jurídica é base para grandes conquistas.</p>
          <div className="ejc-dash__quote-brand">
            <img src={officeBranding.logoPath} alt="" aria-hidden="true" />
            <small>{officeBranding.officeName}</small>
          </div>
        </div>
      </aside>

      <footer className="ejc-dash__footer">
        <span>
          {officeBranding.officeName} <i aria-hidden="true">|</i> São
          Paulo - SP
        </span>
        <span className="ejc-dash__footer-tag">
          <i aria-hidden="true" /> Mais que soluções. Parcerias duradouras.
        </span>
      </footer>
    </div>
  );
}
