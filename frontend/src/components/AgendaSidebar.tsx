// ── Agenda da sidebar ───────────────────────────────────────────────────────
// Mini-calendário do mês corrente logo ABAIXO do menu lateral, entre a
// navegação e o rodapé institucional.
//
// Fonte única de dados: GET /atividades (VIEW vw_atividades) — o mesmo
// endpoint que a Central de Atividades consome, para não inventar uma segunda
// agenda. Contrato verificado em backend/app/routers/atividades.py:
//   resposta {"data": [{ id, tipo, titulo, data→"date", status, case_id,
//                        caso_titulo, dias_restantes, urgencia, ... }]}
// A coluna `data` da view é `::date`, então `date` chega como "YYYY-MM-DD";
// mesmo assim comparamos por `slice(0, 10)`, como já faz o DashboardUltra.
//
// Estado assíncrono por `useCarregar` — falhar NÃO pode virar "vazio": o widget
// mostra erro com "Tentar novamente". Dado ausente é "—", nunca zero falso.
//
// Rotas: o dia selecionado abre a lista inline; o item navega para o caso
// (`/casos/:id`) quando há `case_id`, senão para a Agenda do Dia
// (`/atividades/dia/:date`). Ambas já existem em src/config/moduleRegistry.tsx.
import { useCallback, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameDay,
  isSameMonth,
  isToday,
  startOfDay,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import {
  AlertCircle,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Loader2,
} from "lucide-react";
import api from "../lib/api";
import { mensagemDaFalha, useCarregar } from "../lib/useCarregar";

export interface AtividadeAgenda {
  id: string;
  tipo?: string | null;
  titulo?: string | null;
  /** "YYYY-MM-DD" (a view expõe `::date`). */
  date?: string | null;
  status?: string | null;
  case_id?: string | null;
  caso_titulo?: string | null;
  dias_restantes?: number | null;
}

const VAZIO = "—";
const DIAS_SEMANA = ["D", "S", "T", "Q", "Q", "S", "S"];
const STEP_TECLADO: Record<string, number> = {
  ArrowLeft: -1,
  ArrowRight: 1,
  ArrowUp: -7,
  ArrowDown: 7,
};

/** Extrai a lista do envelope `{"data": [...]}` do backend. */
async function carregarAtividades(): Promise<AtividadeAgenda[]> {
  const resposta = await api.get("/atividades", {
    params: { apenas_pendentes: false },
  });
  const envelope = resposta.data as { data?: unknown } | null;
  return Array.isArray(envelope?.data)
    ? (envelope.data as AtividadeAgenda[])
    : [];
}

function chaveDia(d: Date): string {
  return format(d, "yyyy-MM-dd");
}

/** Rótulo acessível do dia — nunca só o número ("2"), que é ambíguo no leitor de tela. */
function rotuloDia(d: Date, quantidade: number): string {
  const base = new Intl.DateTimeFormat("pt-BR", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(d);
  if (quantidade === 0) return `${base} — nenhum item`;
  return `${base} — ${quantidade} ${quantidade === 1 ? "item" : "itens"}`;
}

export default function AgendaSidebar({ colapsado }: { colapsado?: boolean }) {
  const navegar = useNavigate();
  const [mes, setMes] = useState(() => startOfMonth(new Date()));
  const [diaSelecionado, setDiaSelecionado] = useState<string | null>(null);
  const gradeRef = useRef<HTMLDivElement | null>(null);

  const carga = useCarregar<AtividadeAgenda[]>(carregarAtividades, []);

  /** Índice de dia → itens. Só entra o que tem data; item sem data é "—", não erro. */
  const porDia = useMemo(() => {
    const mapa = new Map<string, AtividadeAgenda[]>();
    for (const item of carga.dados ?? []) {
      const chave = item.date?.slice(0, 10);
      if (!chave) continue;
      const lista = mapa.get(chave);
      if (lista) lista.push(item);
      else mapa.set(chave, [item]);
    }
    return mapa;
  }, [carga.dados]);

  const dias = useMemo(() => {
    const inicio = startOfWeek(startOfMonth(mes), { locale: ptBR });
    const fim = endOfWeek(endOfMonth(mes), { locale: ptBR });
    return eachDayOfInterval({ start: inicio, end: fim });
  }, [mes]);

  const itensDoDia = diaSelecionado ? (porDia.get(diaSelecionado) ?? []) : [];

  // Enquanto o mês visível não tem nenhum item, "quantos neste mês" é
  // desconhecido, não zero — o cabeçalho mostra VAZIO em vez de mentir.
  const totalNoMes = dias.reduce(
    (soma, d) =>
      soma + (isSameMonth(d, mes) ? (porDia.get(chaveDia(d))?.length ?? 0) : 0),
    0,
  );
  const mesTemItens = carga.estado === "ok" || carga.estado === "carregando";

  const focar = useCallback((alvo: Date) => {
    const botao = gradeRef.current?.querySelector<HTMLButtonElement>(
      `[data-dia="${chaveDia(alvo)}"]`,
    );
    botao?.focus();
  }, []);

  const selecionar = useCallback((dia: Date) => {
    const chave = chaveDia(dia);
    setDiaSelecionado((atual) => (atual === chave ? null : chave));
  }, []);

  const aoTeclar = useCallback(
    (evento: React.KeyboardEvent<HTMLButtonElement>, dia: Date) => {
      if (evento.key in STEP_TECLADO) {
        evento.preventDefault();
        const destino = new Date(dia);
        destino.setDate(destino.getDate() + STEP_TECLADO[evento.key]);
        // Navegar para o mês vizinho mantém o dia focado e visível.
        if (!isSameMonth(destino, mes)) setMes(startOfMonth(destino));
        setDiaSelecionado(chaveDia(destino));
        requestAnimationFrame(() => focar(destino));
        return;
      }
      if (evento.key === "PageUp" || evento.key === "PageDown") {
        evento.preventDefault();
        const destino = addMonths(dia, evento.key === "PageUp" ? -1 : 1);
        setMes(startOfMonth(destino));
        setDiaSelecionado(chaveDia(destino));
        requestAnimationFrame(() => focar(destino));
        return;
      }
      if (evento.key === "Home" || evento.key === "End") {
        evento.preventDefault();
        const destino = startOfWeek(dia, { locale: ptBR });
        if (evento.key === "End") destino.setDate(destino.getDate() + 6);
        setDiaSelecionado(chaveDia(destino));
        requestAnimationFrame(() => focar(destino));
        return;
      }
      if (evento.key === "Enter" || evento.key === " ") {
        evento.preventDefault();
        selecionar(dia);
      }
    },
    [focar, mes, selecionar],
  );

  const abrirItem = useCallback(
    (item: AtividadeAgenda) => {
      const chave = item.date?.slice(0, 10) ?? diaSelecionado;
      // Caso primeiro: é onde o usuário espera agir. Sem caso, cai na
      // Agenda do Dia (rota real do registry).
      if (item.case_id) navegar(`/casos/${item.case_id}`);
      else if (chave) navegar(`/atividades/dia/${chave}`);
    },
    [diaSelecionado, navegar],
  );

  // Colapsado: o mês inteiro não cabe em 4.75rem. Em vez de espremer (quebra o
  // layout), o widget vira um único botão que leva à Prazos e Agenda.
  if (colapsado) {
    return (
      <div className="px-3 pb-2">
        <button
          type="button"
          className="icon-btn ejc-sidebar-agenda__collapsed"
          onClick={() => navegar("/atividades")}
          aria-label="Abrir Prazos e Agenda"
          title="Prazos e Agenda"
        >
          <CalendarDays className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <section
      className="ejc-sidebar-agenda"
      aria-labelledby="ejc-sidebar-agenda-titulo"
      onKeyDown={(e) => {
        if (e.key === "Escape" && diaSelecionado) setDiaSelecionado(null);
      }}
    >
      <div className="ejc-sidebar-agenda__head">
        <h2
          id="ejc-sidebar-agenda-titulo"
          className="ejc-sidebar-agenda__title"
        >
          <CalendarDays className="h-4 w-4" aria-hidden="true" />
          Agenda
        </h2>
        <div className="ejc-sidebar-agenda__nav">
          <button
            type="button"
            className="ejc-sidebar-agenda__nav-btn"
            onClick={() => setMes((m) => subMonths(m, 1))}
            aria-label="Mês anterior"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            className="ejc-sidebar-agenda__nav-btn"
            onClick={() => {
              const hoje = startOfDay(new Date());
              setMes(startOfMonth(hoje));
              setDiaSelecionado(chaveDia(hoje));
              requestAnimationFrame(() => focar(hoje));
            }}
            aria-label="Ir para o mês atual"
            title="Ir para hoje"
          >
            <CalendarDays className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            className="ejc-sidebar-agenda__nav-btn"
            onClick={() => setMes((m) => addMonths(m, 1))}
            aria-label="Próximo mês"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </div>

      <p className="ejc-sidebar-agenda__mes" aria-live="polite">
        {format(mes, "MMMM 'de' yyyy", { locale: ptBR })}
        <span className="ejc-sidebar-agenda__total">
          {mesTemItens ? `${totalNoMes} no mês` : VAZIO}
        </span>
      </p>

      {carga.estado === "falhou" ? (
        <div className="ejc-sidebar-agenda__erro" role="alert">
          <AlertCircle className="h-4 w-4 shrink-0" aria-hidden="true" />
          <p>{mensagemDaFalha(carga)}</p>
          <button
            type="button"
            className="ejc-sidebar-agenda__retry"
            onClick={carga.recarregar}
          >
            Tentar novamente
          </button>
        </div>
      ) : (
        <>
          <div
            className="ejc-sidebar-agenda__grade"
            role="grid"
            aria-label={`Calendário de ${format(mes, "MMMM 'de' yyyy", { locale: ptBR })}`}
            ref={gradeRef}
          >
            <div role="row" className="ejc-sidebar-agenda__semana">
              {DIAS_SEMANA.map((d, i) => (
                <span key={`${d}-${i}`} role="columnheader" aria-label={["Domingo", "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado"][i]}>
                  {d}
                </span>
              ))}
            </div>
            <div role="rowgroup">
              {Array.from({ length: dias.length / 7 }, (_, semana) => (
                <div role="row" key={semana} className="ejc-sidebar-agenda__linha">
                  {dias.slice(semana * 7, semana * 7 + 7).map((dia) => {
                    const chave = chaveDia(dia);
                    const itens = porDia.get(chave) ?? [];
                    const selecionado = chave === diaSelecionado;
                    return (
                      <button
                        key={chave}
                        type="button"
                        role="gridcell"
                        data-dia={chave}
                        data-testid={`dia-${chave}`}
                        aria-selected={selecionado}
                        aria-label={rotuloDia(dia, itens.length)}
                        // Roving tabindex: um único ponto de entrada na grade
                        // (W3C grid pattern) em vez de 42 tab stops.
                        tabIndex={selecionado || (!diaSelecionado && isToday(dia)) ? 0 : -1}
                        className={[
                          "ejc-sidebar-agenda__dia",
                          !isSameMonth(dia, mes) && "is-outro-mes",
                          isToday(dia) && "is-hoje",
                          selecionado && "is-selecionado",
                          itens.length > 0 && "is-com-itens",
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        onClick={() => selecionar(dia)}
                        onKeyDown={(e) => aoTeclar(e, dia)}
                      >
                        {format(dia, "d")}
                      </button>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>

          {carga.carregando && (
            <p className="ejc-sidebar-agenda__status" role="status">
              <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" />
              Carregando agenda…
            </p>
          )}

          {carga.estado === "vazio" && (
            <p className="ejc-sidebar-agenda__status">
              Nenhum prazo ou compromisso no seu escopo.
            </p>
          )}

          {diaSelecionado && (
            <div className="ejc-sidebar-agenda__lista">
              <h3 className="ejc-sidebar-agenda__lista-titulo">
                {new Intl.DateTimeFormat("pt-BR", {
                  weekday: "long",
                  day: "2-digit",
                  month: "short",
                }).format(new Date(`${diaSelecionado}T12:00:00`))}
              </h3>
              {itensDoDia.length === 0 ? (
                <p className="ejc-sidebar-agenda__status">
                  Nenhum item neste dia. Selecione um dia com marcador.
                </p>
              ) : (
                <ul>
                  {itensDoDia.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="ejc-sidebar-agenda__item"
                        onClick={() => abrirItem(item)}
                      >
                        <span className="ejc-sidebar-agenda__item-titulo">
                          {item.titulo?.trim() || VAZIO}
                        </span>
                        <span className="ejc-sidebar-agenda__item-caso">
                          {item.caso_titulo?.trim() ||
                            (item.case_id ? VAZIO : "Sem caso vinculado")}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
