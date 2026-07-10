import { useEffect, useState } from "react";
import { X, ChevronRight, ChevronLeft } from "lucide-react";

const TOUR_KEY = "ejc_tour_v2_done";

const SLIDES = [
  {
    emoji: "⚖️",
    title: "Bem-vindo ao EJC",
    body: "O sistema agora está organizado por workspaces. Menu, rotas, ajuda e permissões usam o mesmo manifesto de módulos.",
  },
  {
    emoji: "📁",
    title: "Casos e Processos",
    body: "Acesse Casos para acompanhar o processo completo. A Sala de Guerra fica dentro do caso, preservando contexto e confidencialidade.",
  },
  {
    emoji: "📅",
    title: "Agenda e Atividades",
    body: "Prazos, tarefas, intimações, suspensões e eventos aparecem em uma central operacional, sem transformar prazo jurídico em tarefa comum.",
  },
  {
    emoji: "✨",
    title: "Inteligência Jurídica",
    body: "Assistente, análise, validação, ferramentas especializadas, jurimetria e conhecimento foram reunidos em um único workspace com revisão humana.",
  },
  {
    emoji: "📚",
    title: "Conhecimento Jurídico",
    body: "A busca unificada consulta RAG, teses, jurisprudência e memória institucional, mantendo as fontes e entidades separadas no backend.",
  },
  {
    emoji: "⚙️",
    title: "Preferências e Administração",
    body: "Cada usuário pode ajustar tema, página inicial e menu. Administradores têm acesso separado ao mapa de módulos, usuários, auditoria e governança da IA.",
  },
  {
    emoji: "🎯",
    title: "Pronto",
    body: "Use Ctrl ou Command + K para buscar dados e abrir módulos autorizados. A Central de Ajuda continua disponível no cabeçalho.",
  },
];

export default function OnboardingTour() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!localStorage.getItem(TOUR_KEY)) {
      const timer = setTimeout(() => setVisible(true), 800);
      return () => clearTimeout(timer);
    }
  }, []);

  const fechar = () => {
    localStorage.setItem(TOUR_KEY, "1");
    setVisible(false);
  };

  const avancar = () => {
    if (step < SLIDES.length - 1) setStep((current) => current + 1);
    else fechar();
  };

  const voltar = () => setStep((current) => Math.max(0, current - 1));

  if (!visible) return null;

  const slide = SLIDES[step];
  const isLast = step === SLIDES.length - 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.35)" }}
      onClick={(event) => {
        if (event.target === event.currentTarget) fechar();
      }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
        <div className="h-0.5 bg-zinc-100">
          <div
            className="h-full bg-[#B08A50] transition-all duration-300"
            style={{ width: `${((step + 1) / SLIDES.length) * 100}%` }}
          />
        </div>

        <div className="p-7">
          <div className="flex items-start justify-between mb-5">
            <span className="text-4xl">{slide.emoji}</span>
            <button
              onClick={fechar}
              className="p-1 text-zinc-300 hover:text-zinc-500"
              aria-label="Fechar tour"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <h2 className="text-xl font-light text-zinc-800 mb-3">
            {slide.title}
          </h2>
          <p className="text-sm text-zinc-500 leading-relaxed">{slide.body}</p>

          <div className="flex items-center justify-between mt-7">
            <button
              onClick={voltar}
              className={`btn-ghost flex items-center gap-1 text-sm ${step === 0 ? "invisible" : ""}`}
            >
              <ChevronLeft className="w-4 h-4" /> Voltar
            </button>

            <span className="text-xs text-zinc-300">
              {step + 1} / {SLIDES.length}
            </span>

            <button
              onClick={avancar}
              className="btn-primary flex items-center gap-1.5"
            >
              {isLast ? "Concluir" : "Próximo"}{" "}
              {!isLast && <ChevronRight className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
