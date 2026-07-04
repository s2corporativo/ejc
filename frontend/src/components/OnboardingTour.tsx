import { useState, useEffect } from "react";
import { X, ChevronRight, ChevronLeft } from "lucide-react";

const TOUR_KEY = "ejc_tour_v1_done";

const SLIDES = [
  {
    emoji: "⚖️",
    title: "Bem-vindo ao EJC",
    body: "Sistema completo de gestão jurídica. Este tour rápido mostra as principais funcionalidades em menos de 1 minuto.",
  },
  {
    emoji: "📁",
    title: "Casos",
    body: "Crie e acompanhe processos em Casos no menu lateral. Cada caso tem abas de Timeline, Documentos, Checklists e Teses vinculadas.",
  },
  {
    emoji: "⚔️",
    title: "Sala de Guerra",
    body: "Dentro de qualquer caso, clique ⚔️ Sala de Guerra para uma visão consolidada: prazos críticos, horas trabalhadas, teses e análise estratégica editável.",
  },
  {
    emoji: "✨",
    title: "Inteligência Artificial",
    body: "Use Análise IA no caso para estratégia, Sugestão de Honorários pela tabela OAB/MG, e o Assistente IA no menu para consultas livres.",
  },
  {
    emoji: "📚",
    title: "Base de Conhecimento",
    body: "Em Biblioteca faça busca avançada de teses. Em Base RAG indexe PDFs e URLs. Em Memória Institucional registre precedentes do escritório.",
  },
  {
    emoji: "📈",
    title: "Analytics",
    body: "Acesse Produtividade para HH por advogado e área. Acesse Jurimetria para taxa de sucesso real por desfechos dos casos encerrados.",
  },
  {
    emoji: "🎯",
    title: "Pronto!",
    body: "Você pode revisitar este guia a qualquer momento em Central de Ajuda no menu. Bom trabalho!",
  },
];

export default function OnboardingTour() {
  const [visible, setVisible] = useState(false);
  const [step, setStep] = useState(0);

  useEffect(() => {
    if (!localStorage.getItem(TOUR_KEY)) {
      setTimeout(() => setVisible(true), 800);
    }
  }, []);

  const fechar = () => {
    localStorage.setItem(TOUR_KEY, "1");
    setVisible(false);
  };

  const avancar = () => {
    if (step < SLIDES.length - 1) setStep((s) => s + 1);
    else fechar();
  };

  const voltar = () => setStep((s) => Math.max(0, s - 1));

  if (!visible) return null;

  const slide = SLIDES[step];
  const isLast = step === SLIDES.length - 1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.35)" }}
      onClick={(e) => {
        if (e.target === e.currentTarget) fechar();
      }}
    >
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
        {/* Progress bar */}
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
