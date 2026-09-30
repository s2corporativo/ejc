// ── Agenda da sidebar — mini-calendário do mês corrente ──────────────────────
// Widget de leitura rápida, inserido abaixo dos itens de navegação. Não é
// dialog: a lista do dia selecionado abre inline, dentro da própria sidebar.
// Sem modal, sem focus trap — a navegação é por roving tabindex (padrão W3C
// de grid), com um único tab stop e setas para percorrer os dias.
//
// Dados: GET /atividades (envelope { data: [] } — desempacotado por asList).
// A coluna `date` da vw_atividades é ::date, então chega como "YYYY-MM-DD".
import { useMemo, useRef, useState, type KeyboardEvent } from "react";
import { Link } from "react-router";
import { CalendarDays, ChevronLeft, ChevronRight } from "lucide-react";
import {
  addMonths,
  eachDayOfInterval,
  endOfMonth,
  endOfWeek,
  format,
  isSameMonth,
  isToday,
  startOfMonth,
  startOfWeek,
  subMonths,
} from "date-fns";
import { ptBR } from "date-fns/locale";
import api from "../lib/api";
import { asList } from "../lib/list";
import { useCarregar } from "../lib/useCarregar";
import { cn } from "./UI";

type Atividade = {
  id?: string;
  tipo?: string;
  titulo?: string;
  date?: string | null;
  status?: string;
  case_id?: string | null;
  caso_titulo?: string | null;
};

const DIAS_SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];
const CHAVE = (d: Date) => format(d, "yyyy-MM-dd");

/** Célula da grade: dia real ou vazio inerte de completeza. */
type CelulaGrade = { dia: Date | null; vazia: boolean };

/** Rótulo acessível do dia: nome do dia + data por extenso + contagem real. */
function rotuloDia(dia: Date, total: number): string {
  const data = format(dia, "EEEE, dd 'de' MMMM", { locale: ptBR });
  if (total === 0) return `${data} — sem itens`;
  return `${data} — ${total} ${total === 1 ? "item" : "itens"}`;
}

export default function AgendaSidebar({
  navCollapsed = false,
}: {
  navCollapsed?: boolean;
}) {
  const hoje = useMemo(() => new Date(), []);
  const [mesVisivel, setMesVisivel] = useState(() => startOfMonth(hoje));
  const [diaSelecionado, setDiaSelecionado] = useState(() => CHAVE(hoje));
  const [listaAberta, setListaAberta] = useState(false);
  const gradeRef = useRef<HTMLDivElement | null>(null);

  const atividades = useCarregar<Atividade[]>(
    () =>
      api
        .get("/atividades", { params: { apenas_pendentes: false } })
        .then((r) => asList<Atividade>(r.data)),
    [],
  );

  /** Agrupa por dia (YYYY-MM-DD). Atividade sem data não entra em dia nenhum. */
  const porDia = useMemo(() => {
    const mapa = new Map<string, Atividade[]>();
    for (const a of atividades.dados ?? []) {
      if (!a?.date) continue;
      const chave = String(a.date).slice(0, 10);
      const lista = mapa.get(chave);
      if (lista) lista.push(a);
      else mapa.set(chave, [a]);
    }
    return mapa;
  }, [atividades.dados]);

  const proximosCompromissos = useMemo(() => {
    const hojeChave = CHAVE(hoje);
    return (atividades.dados ?? [])
      .filter((atividade) => {
        if (!atividade?.date) return false;
        return String(atividade.date).slice(0, 10) > hojeChave;
      })
      .sort((a, b) => String(a.date ?? "").localeCompare(String(b.date ?? "")))
      .slice(0, 3);
  }, [atividades.dados, hoje]);

  // Grade de 6 semanas: é o que o calendário mensal precisa caber sem mudar
  // de altura ao navegar de um mês para outro. As células de completeza não
  // repetem datas (repetir geraria rótulos duplicados para o leitor de tela):
  // são vazios inertes, fora da ordem de tabulação e da navegação por setas.
  const grade = useMemo(() => {
    const inicio = startOfWeek(startOfMonth(mesVisivel), { weekStartsOn: 1 });
    const fim = endOfWeek(endOfMonth(mesVisivel), { weekStartsOn: 1 });
    const celulas: CelulaGrade[] = eachDayOfInterval({
      start: inicio,
      end: fim,
    }).map((dia) => ({ dia, vazia: false }));
    while (celulas.length < 42) celulas.push({ dia: null, vazia: true });
    return celulas;
  }, [mesVisivel]);

  /** Primeira célula navegável a partir de `de`, no sentido indicado. */
  const proximaCelula = (de: number, passo: number): number | null => {
    for (let i = de + passo; i >= 0 && i < grade.length; i += passo) {
      if (!grade[i].vazia) return i;
    }
    return null;
  };

  const totalDoDia = (dia: Date) => porDia.get(CHAVE(dia))?.length ?? 0;

  // Colapso: 4.75rem não comporta um mês. Mostramos só o ícone dourado, que
  // leva à agenda — espremer a grade quebraria o layout em vez de degradar.
  if (navCollapsed) {
    return (
      <div className="ejc-sidebar-agenda is-collapsed">
        <Link
          to="/atividades"
          className="ejc-sidebar-agenda__compact icon-btn"
          aria-label="Abrir a agenda do escritório"
          title="Agenda"
        >
          <CalendarDays className="h-5 w-5" aria-hidden="true" />
        </Link>
      </div>
    );
  }

  const chaveSelecionada = diaSelecionado;
  const itensSelecionados = porDia.get(chaveSelecionada) ?? [];
  const indiceSelecionado = grade.findIndex(
    (c) => c.dia && CHAVE(c.dia) === chaveSelecionada,
  );
  // Roving tabindex: um único tab stop, no dia selecionado (ou no 1º real).
  const indiceFoco = indiceSelecionado >= 0 ? indiceSelecionado : 0;

  const focar = (indice: number) => {
    const alvo =
      gradeRef.current?.querySelectorAll<HTMLButtonElement>(
        '[role="gridcell"]',
      )[indice];
    alvo?.focus();
  };

  const irPara = (dia: Date) => {
    setDiaSelecionado(CHAVE(dia));
    if (!isSameMonth(dia, mesVisivel)) setMesVisivel(startOfMonth(dia));
  };

  const alternarLista = (dia: Date) => {
    const chave = CHAVE(dia);
    setDiaSelecionado(chave);
    setListaAberta((v) => (chave === chaveSelecionada ? !v : true));
  };

  const aoTeclar = (
    e: KeyboardEvent<HTMLButtonElement>,
    indice: number,
    dia: Date,
  ) => {
    const naLinha = indice % 7;
    let proximo: number | null = null;
    switch (e.key) {
      case "ArrowRight":
        proximo = proximaCelula(indice, 1);
        break;
      case "ArrowLeft":
        proximo = proximaCelula(indice, -1);
        break;
      case "ArrowDown":
        proximo = proximaCelula(indice, 7);
        break;
      case "ArrowUp":
        proximo = proximaCelula(indice, -7);
        break;
      case "Home":
        for (let i = indice - naLinha; i < grade.length; i += 1) {
          if (!grade[i].vazia) {
            proximo = i;
            break;
          }
        }
        break;
      case "End":
        for (
          let i = Math.min(grade.length - 1, indice - naLinha + 6);
          i >= 0;
          i -= 1
        ) {
          if (!grade[i].vazia) {
            proximo = i;
            break;
          }
        }
        break;
      case "PageDown":
        e.preventDefault();
        irPara(addMonths(dia, 1));
        return;
      case "PageUp":
        e.preventDefault();
        irPara(subMonths(dia, 1));
        return;
      case "Enter":
      case " ":
        e.preventDefault();
        alternarLista(dia);
        return;
      case "Escape":
        if (listaAberta) {
          e.preventDefault();
          setListaAberta(false);
        }
        return;
      default:
        return;
    }
    e.preventDefault();
    if (proximo !== null) focar(proximo);
  };

  return (
    <section className="ejc-sidebar-agenda" aria-label="Agenda do escritório">
      <header className="ejc-sidebar-agenda__head">
        <div>
          <p className="ejc-sidebar-agenda__title">Agenda</p>
          <p className="ejc-sidebar-agenda__month" aria-live="polite">
            {format(mesVisivel, "MMMM 'de' yyyy", { locale: ptBR })}
          </p>
        </div>
        <div className="ejc-sidebar-agenda__nav">
          <button
            type="button"
            className="icon-btn h-6 w-6"
            onClick={() => setMesVisivel(subMonths(mesVisivel, 1))}
            aria-label="Mês anterior"
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            className="icon-btn h-6 w-6"
            onClick={() => {
              setMesVisivel(startOfMonth(hoje));
              setDiaSelecionado(CHAVE(hoje));
            }}
            aria-label="Ir para hoje"
          >
            <CalendarDays className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            className="icon-btn h-6 w-6"
            onClick={() => setMesVisivel(addMonths(mesVisivel, 1))}
            aria-label="Próximo mês"
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </header>

      {atividades.estado === "falhou" ? (
        <div className="ejc-sidebar-agenda__error" role="alert">
          <p className="ejc-sidebar-agenda__error-text">{atividades.erro}</p>
          <button
            type="button"
            className="ejc-sidebar-agenda__retry"
            onClick={atividades.recarregar}
          >
            Tentar novamente
          </button>
        </div>
      ) : (
        <>
          <div className="ejc-sidebar-agenda__weekdays" aria-hidden="true">
            {DIAS_SEMANA.map((d) => (
              <span key={d}>{d}</span>
            ))}
          </div>

          <div
            ref={gradeRef}
            role="grid"
            aria-label="Calendário do mês"
            className="ejc-sidebar-agenda__grid"
          >
            {grade.map((celula, i) => {
              if (celula.vazia || !celula.dia) {
                return (
                  <span
                    key={`vazia-${i}`}
                    role="gridcell"
                    aria-hidden="true"
                    className="ejc-sidebar-agenda__day is-vazia"
                  />
                );
              }
              const { dia } = celula;
              const chave = CHAVE(dia);
              const total = totalDoDia(dia);
              const selecionadoCelula = chave === chaveSelecionada;
              return (
                <button
                  key={chave}
                  type="button"
                  role="gridcell"
                  tabIndex={i === indiceFoco ? 0 : -1}
                  aria-label={rotuloDia(dia, total)}
                  aria-selected={selecionadoCelula}
                  className={cn(
                    "ejc-sidebar-agenda__day",
                    !isSameMonth(dia, mesVisivel) && "is-outro-mes",
                    isToday(dia) && "is-hoje",
                    selecionadoCelula && "is-selecionado",
                  )}
                  onClick={() => alternarLista(dia)}
                  onKeyDown={(e) => aoTeclar(e, i, dia)}
                >
                  <span aria-hidden="true">{format(dia, "d")}</span>
                  {total > 0 && (
                    <i className="ejc-sidebar-agenda__dot" aria-hidden="true" />
                  )}
                </button>
              );
            })}
          </div>

          <div className="ejc-sidebar-agenda__upcoming">
            <div className="ejc-sidebar-agenda__upcoming-head">
              <strong>Próximos</strong>
              <Link to="/atividades">Ver agenda</Link>
            </div>
            {proximosCompromissos.length === 0 ? (
              <p className="ejc-sidebar-agenda__upcoming-empty">
                Sem próximos compromissos.
              </p>
            ) : (
              <ul>
                {proximosCompromissos.map((atividade, index) => {
                  const data = String(atividade.date).slice(0, 10);
                  const destino = atividade.case_id
                    ? `/casos/${atividade.case_id}`
                    : `/atividades/dia/${data}`;
                  return (
                    <li key={atividade.id ?? `proximo-${data}-${index}`}>
                      <Link to={destino}>
                        <time>
                          {format(new Date(`${data}T12:00:00`), "dd/MM")}
                        </time>
                        <span>
                          <strong>{atividade.titulo || "Compromisso"}</strong>
                          <small>{atividade.caso_titulo || "Agenda"}</small>
                        </span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {listaAberta && (
            <div className="ejc-sidebar-agenda__list">
              <p className="ejc-sidebar-agenda__list-head">
                {format(
                  new Date(`${chaveSelecionada}T00:00:00`),
                  "dd 'de' MMMM",
                  {
                    locale: ptBR,
                  },
                )}
              </p>
              {itensSelecionados.length === 0 ? (
                <p className="ejc-sidebar-agenda__list-empty">
                  Nenhum item nesta data.
                </p>
              ) : (
                <ul>
                  {itensSelecionados.map((a, i) => {
                    const destino = a.case_id
                      ? `/casos/${a.case_id}`
                      : `/atividades/dia/${chaveSelecionada}`;
                    return (
                      <li key={a.id ?? `${chaveSelecionada}-${i}`}>
                        <Link
                          to={destino}
                          className="ejc-sidebar-agenda__item"
                          onClick={() => setListaAberta(false)}
                        >
                          <span className="ejc-sidebar-agenda__item-title">
                            {a.titulo || "Atividade"}
                          </span>
                          <span className="ejc-sidebar-agenda__item-case">
                            {a.caso_titulo || "Sem caso vinculado"}
                          </span>
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
