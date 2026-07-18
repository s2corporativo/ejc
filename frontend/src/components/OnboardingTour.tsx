import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  X,
  Check,
  Search,
  FolderPlus,
  CalendarClock,
  FileText,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { cn } from "./UI";

// Onboarding PRÁTICO v1: em vez de um tour conceitual (slides), um checklist
// de 4 tarefas guiadas que o usuário executa de verdade no sistema.
// Retomável: o conjunto de tarefas concluídas e o estado do painel ficam no
// localStorage, então dá para fechar e voltar de onde parou.
// Sem detecção automática de conclusão (não criamos dados) — cada tarefa é
// marcada manualmente como feita. Só navegação e estado local.

// Conjunto de passos concluídos (ids das tarefas). NÃO é um booleano único.
const PROGRESS_KEY = "ejc_onboarding_tarefas";
// Gate/estado do painel (substitui o antigo ejc_tour_v3_done).
const STATE_KEY = "ejc_onboarding_v1";

type View = "aberto" | "recolhido" | "dispensado";

// Ação de cada tarefa: abrir a busca global do header ou navegar para uma
// rota já registrada no moduleRegistry (a guarda internalLinks exige isso).
type TaskAction =
  | { kind: "busca" }
  | { kind: "rota"; path: string };

type Task = {
  id: string;
  icon: LucideIcon;
  title: string;
  hint: string;
  cta: string;
  action: TaskAction;
  secondary?: { cta: string; path: string };
};

const TASKS: Task[] = [
  {
    id: "localizar",
    icon: Search,
    title: "Localize um cliente ou processo",
    hint: "Use a busca global para achar qualquer cliente, caso ou processo em segundos.",
    cta: "Abrir busca",
    action: { kind: "busca" },
    secondary: { cta: "Ver clientes", path: "/clientes" },
  },
  {
    id: "abrir-caso",
    icon: FolderPlus,
    title: "Abra um caso",
    hint: "O caso concentra prazos, documentos e peças. Comece pelo cadastro guiado.",
    cta: "Novo caso",
    action: { kind: "rota", path: "/casos/novo" },
  },
  {
    id: "prazo",
    icon: CalendarClock,
    title: "Registre ou confirme um prazo",
    hint: "Cadastre um prazo e dê ciência para não perder nenhuma data processual.",
    cta: "Ir para Agenda e Prazos",
    action: { kind: "rota", path: "/atividades?tipo=prazo" },
  },
  {
    id: "documento-minuta",
    icon: FileText,
    title: "Anexe um documento e produza uma minuta",
    hint: "Suba um arquivo em Documentos e depois gere uma minuta na área de Peças.",
    cta: "Ir para Documentos",
    action: { kind: "rota", path: "/documentos" },
    secondary: { cta: "Abrir Peças", path: "/pecas" },
  },
];

function lerConcluidas(): string[] {
  try {
    const raw = localStorage.getItem(PROGRESS_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((x): x is string => typeof x === "string");
  } catch {
    return []; // progresso corrompido: começa do zero
  }
}

export default function OnboardingTour() {
  const [view, setView] = useState<View | null>(null);
  const [feitas, setFeitas] = useState<string[]>([]);
  const navigate = useNavigate();
  const panelRef = useRef<HTMLDivElement>(null);

  // Carrega progresso + estado do painel. O painel expandido só abre
  // AUTOMATICAMENTE na primeira visita; em qualquer montagem seguinte, um
  // estado salvo "aberto" vira a pílula recolhida "Primeiros passos N/4" —
  // o usuário expande por clique. Isso impede o popover de reabrir a cada
  // navegação e de cobrir botões de ação (auditoria de usabilidade §2.4/2.5).
  useEffect(() => {
    setFeitas(lerConcluidas());
    const saved = localStorage.getItem(STATE_KEY);
    if (saved === "recolhido" || saved === "dispensado") {
      setView(saved);
      return;
    }
    if (saved === "aberto") {
      localStorage.setItem(STATE_KEY, "recolhido");
      setView("recolhido");
      return;
    }
    const timer = setTimeout(() => {
      localStorage.setItem(STATE_KEY, "aberto");
      setView("aberto");
    }, 700);
    return () => clearTimeout(timer);
  }, []);

  const setEstado = useCallback((next: View) => {
    localStorage.setItem(STATE_KEY, next);
    setView(next);
  }, []);

  const minimizar = useCallback(() => setEstado("recolhido"), [setEstado]);
  const dispensar = useCallback(() => setEstado("dispensado"), [setEstado]);
  const abrir = useCallback(() => setEstado("aberto"), [setEstado]);

  // Marca/desmarca manualmente. Sem efeitos colaterais na base.
  const toggle = useCallback((id: string) => {
    setFeitas((prev) => {
      const next = prev.includes(id)
        ? prev.filter((x) => x !== id)
        : [...prev, id];
      localStorage.setItem(PROGRESS_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  // Executa a ação da tarefa e recolhe o painel para o launcher — assim, ao
  // navegar (ou abrir a busca), o progresso continua acessível na volta.
  const executar = useCallback(
    (action: TaskAction) => {
      minimizar();
      if (action.kind === "busca") {
        window.dispatchEvent(new Event("ejc-open-search"));
      } else {
        navigate(action.path);
      }
    },
    [minimizar, navigate],
  );

  const irPara = useCallback(
    (path: string) => {
      minimizar();
      navigate(path);
    },
    [minimizar, navigate],
  );

  // Foco inicial no painel ao abrir (acessibilidade).
  useEffect(() => {
    if (view === "aberto") panelRef.current?.focus();
  }, [view]);

  // Esc recolhe o painel.
  useEffect(() => {
    if (view !== "aberto") return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") minimizar();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [view, minimizar]);

  if (view === null || view === "dispensado") return null;

  const doneIds = new Set(feitas);
  const concluidas = TASKS.filter((t) => doneIds.has(t.id)).length;
  const total = TASKS.length;
  const tudoFeito = concluidas === total;

  if (view === "recolhido") {
    return (
      <button
        type="button"
        onClick={abrir}
        aria-label={`Primeiros passos: ${concluidas} de ${total} concluídos. Reabrir.`}
        className="fixed bottom-5 right-20 z-40 flex items-center gap-2 rounded-full bg-white px-4 py-2.5 text-sm font-medium text-zinc-700 shadow-lg ring-1 ring-black/5 transition-shadow hover:shadow-xl"
      >
        <Sparkles className="h-4 w-4 text-[#B08A50]" />
        Primeiros passos
        <span className="rounded-full bg-[#B08A50]/10 px-1.5 py-0.5 text-xs font-semibold text-[#8F7117]">
          {concluidas}/{total}
        </span>
      </button>
    );
  }

  return (
    // pointer-events-none no wrapper: a faixa flex NÃO pode bloquear cliques
    // fora do card (só o painel em si recebe eventos).
    <div className="onboarding-tour pointer-events-none fixed inset-x-4 bottom-4 z-50 flex justify-center sm:inset-x-auto sm:right-4 sm:justify-end">
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="false"
        aria-labelledby="onboarding-title"
        aria-describedby="onboarding-sub"
        className="card pointer-events-auto w-full max-w-sm overflow-hidden focus:outline-none"
      >
        <div className="h-1 bg-zinc-100">
          <div
            className="h-full bg-[#B08A50] transition-all duration-300"
            style={{ width: `${(concluidas / total) * 100}%` }}
          />
        </div>

        <div className="p-5">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h2
                id="onboarding-title"
                className="text-base font-medium text-zinc-800"
              >
                Primeiros passos no EJC
              </h2>
              <p id="onboarding-sub" className="mt-0.5 text-xs text-zinc-500">
                {tudoFeito
                  ? "Tudo pronto — você concluiu o essencial."
                  : `4 tarefas rápidas · ${concluidas}/${total} concluídas`}
              </p>
            </div>
            <button
              onClick={minimizar}
              className="-mr-1 rounded-lg p-1.5 text-zinc-300 hover:bg-zinc-100 hover:text-zinc-500"
              aria-label="Recolher primeiros passos"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <ul className="mt-4 space-y-1">
            {TASKS.map((task, index) => {
              const done = doneIds.has(task.id);
              const Icon = task.icon;
              const sec = task.secondary;
              return (
                <li
                  key={task.id}
                  className="flex items-start gap-3 rounded-xl p-2 transition-colors hover:bg-zinc-50"
                >
                  <button
                    type="button"
                    onClick={() => toggle(task.id)}
                    aria-pressed={done}
                    aria-label={
                      done
                        ? `Desmarcar tarefa: ${task.title}`
                        : `Marcar como feita: ${task.title}`
                    }
                    className={cn(
                      "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border transition-colors",
                      done
                        ? "border-[#B08A50] bg-[#B08A50] text-white"
                        : "border-zinc-300 text-transparent hover:border-[#B08A50]",
                    )}
                  >
                    <Check className="h-3.5 w-3.5" />
                  </button>

                  <div className="min-w-0 flex-1">
                    <p
                      className={cn(
                        "text-sm font-medium text-zinc-800",
                        done && "text-zinc-400 line-through",
                      )}
                    >
                      {index + 1}. {task.title}
                    </p>
                    <p className="mt-0.5 text-xs leading-relaxed text-zinc-500">
                      {task.hint}
                    </p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        onClick={() => executar(task.action)}
                        className="btn-primary gap-1.5 px-3 py-1.5 text-xs"
                      >
                        <Icon className="h-3.5 w-3.5" />
                        {task.cta}
                      </button>
                      {sec && (
                        <button
                          type="button"
                          onClick={() => irPara(sec.path)}
                          className="btn-ghost px-2 py-1.5 text-xs"
                        >
                          {sec.cta}
                        </button>
                      )}
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>

          <div className="mt-4 flex items-center justify-between gap-2 border-t border-zinc-100 pt-3">
            {tudoFeito ? (
              <button
                type="button"
                onClick={dispensar}
                className="btn-primary w-full text-sm"
              >
                Concluir
              </button>
            ) : (
              <>
                <button
                  type="button"
                  onClick={dispensar}
                  className="btn-ghost text-xs text-zinc-400"
                >
                  Pular
                </button>
                <button
                  type="button"
                  onClick={minimizar}
                  className="btn-ghost text-xs"
                >
                  Continuar depois
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

