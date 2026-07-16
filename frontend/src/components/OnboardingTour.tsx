import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, ChevronRight, ChevronLeft, ArrowRight } from "lucide-react";

// v3: tour enxuto e orientado à ação — o último slide leva à criação do
// primeiro caso. Nova key para que quem já viu a v2 veja a versão nova uma vez.
const TOUR_KEY = "ejc_tour_v3_done";

// Rota do wizard guiado de abertura de caso (já registrada no moduleRegistry).
const NOVO_CASO_PATH = "/casos/novo";

const SLIDES = [
  {
    emoji: "⚖️",
    title: "Bem-vindo ao EJC",
    body: "Seu escritório em um só lugar: casos, prazos, documentos e clientes conectados. O menu começa enxuto — o que você usa todo dia fica no topo.",
  },
  {
    emoji: "📁",
    title: "Tudo gira em torno do caso",
    body: "Cada caso reúne prazos, documentos, peças e honorários. É por ele que você acompanha o andamento do início ao fim.",
  },
  {
    emoji: "📅",
    title: "Nada passa despercebido",
    body: "A Central mostra prazos, tarefas e intimações juntos. Prazos processuais têm tratamento próprio, com confirmação de ciência.",
  },
  {
    emoji: "🎯",
    title: "Vamos começar",
    body: "O jeito mais rápido de conhecer o EJC é abrindo seu primeiro caso pelo cadastro guiado. Leva menos de um minuto.",
  },
];

export default function OnboardingTour() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);
  const navigate = useNavigate();

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

  const criarPrimeiroCaso = () => {
    fechar();
    navigate(NOVO_CASO_PATH);
  };

  const voltar = () => setStep((current) => Math.max(0, current - 1));

  if (!visible) return null;

  const slide = SLIDES[step];
  const isLast = step === SLIDES.length - 1;

  return (
    <div
      className="onboarding-tour fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
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

          {isLast && (
            <button
              onClick={criarPrimeiroCaso}
              className="btn-primary mt-6 flex w-full items-center justify-center gap-2"
            >
              Criar meu primeiro caso
              <ArrowRight className="w-4 h-4" />
            </button>
          )}

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

            {isLast ? (
              <button
                onClick={fechar}
                className="btn-ghost text-sm text-zinc-400"
              >
                Explorar depois
              </button>
            ) : (
              <button
                onClick={avancar}
                className="btn-primary flex items-center gap-1.5"
              >
                Próximo <ChevronRight className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
