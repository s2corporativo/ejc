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
  CalendarClock,
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderKanban,
  Plus,
  Scale,
  Sparkles,
  Upload,
  Users,
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
  numero_processo?: string | null;
  numero_interno?: string | null;
};

type Tarefa = { id: string; titulo?: string; status?: string };

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
  if (status === "encerrado") return { rotulo: "Conclusão", classe: "is-gold" };
  if (status === "arquivado") return { rotulo: "Arquivado", classe: "is-gray" };
  return { rotulo: "Em andamento", classe: "is-green" };
}

function saudacaoPorHora(): string {
  const hora = new Date().getHours();
  if (hora < 12) return "Bom dia";
  if (hora < 18) return "Boa tarde";
  return "Boa noite";
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
  const [mesOffset, setMesOffset] = useState(0);

  const carregar = useCallback(async () => {
    const inicioDocs = format(
      new Date(Date.now() - 7 * 24 * 60 * 60 * 1000),
      "yyyy-MM-dd",
    );
    const [rKpis, rAtiv, rCasos, rDocs, rTarefas] = await Promise.allSettled([
      api.get("/dashboard/"),
      api.get("/atividades", { params: { apenas_pendentes: true } }),
      api.get("/cases/", { params: { page: 1, page_size: 4 } }),
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
    const novoStatus = tarefa.status === "concluida" ? "pendente" : "concluida";
    setTarefas((atual) =>
      (atual ?? []).map((item) =>
        item.id === tarefa.id ? { ...item, status: novoStatus } : item,
      ),
    );
    try {
      await api.patch(`/tasks/${tarefa.id}`, { status: novoStatus });
    } catch {
      setTarefas((atual) =>
        (atual ?? []).map((item) =>
          item.id === tarefa.id ? { ...item, status: tarefa.status } : item,
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
    const dentroDaAba = atividades.filter((a) => {
      const d = a.dias_restantes;
      if (aba === "hoje") return d === 0;
      if (aba === "amanha") return d === 1;
      return d !== null && d !== undefined && d >= 2 && d <= 7;
    });
    return dentroDaAba.slice(0, 6);
  }, [atividades, aba]);

  const rotinaPendentes = useMemo(
    () =>
      (tarefas ?? []).filter((t) => t.status !== "concluida").slice(0, 5),
    [tarefas],
  );
  const rotinaConcluidas = useMemo(() => {
    const pendentesIds = new Set(rotinaPendentes.map((t) => t.id));
    return (tarefas ?? [])
      .filter((t) => t.status === "concluida" && !pendentesIds.has(t.id))
      .slice(0, Math.max(0, 5 - rotinaPendentes.length));
  }, [tarefas, rotinaPendentes]);

  const rotinaTotal = (tarefas ?? []).length;
  const rotinaFeitas =
    rotinaTotal - (tarefas ?? []).filter((t) => t.status !== "concluida").length;

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
            <Sparkles />
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
            <h3>Agenda e Prazos</h3>
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
                  onClick={() => setAba(valor)}
                >
                  {rotulo}
                </button>
              ))}
            </div>
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
            <h3>Casos em destaque</h3>
            <Link to="/casos" className="ejc-dash__panel-more">
              Ver todos <ChevronRight aria-hidden="true" />
            </Link>
          </div>
          <ul className="ejc-dash__cases">
            {casos === null ? (
              <li className="ejc-dash__empty">Casos indisponíveis agora.</li>
            ) : casos.length === 0 ? (
              <li className="ejc-dash__empty">Nenhum caso cadastrado ainda.</li>
            ) : (
              casos.map((c) => {
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
          <Sparkles aria-hidden="true" />
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
              return (
                <button
                  key={chave}
                  type="button"
                  className={classes.join(" ")}
                  aria-current={
                    chave === format(new Date(), "yyyy-MM-dd")
                      ? "date"
                      : undefined
                  }
                  onClick={() => navigate(`/atividades/dia/${chave}`)}
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
