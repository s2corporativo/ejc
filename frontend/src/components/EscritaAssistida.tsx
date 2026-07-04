import React, { useState } from "react";

const EscritaAssistida: React.FC = () => {
  const [step, setStep] = useState(1);
  const [context, setContext] = useState("");
  const [tese, setTese] = useState("");
  const [draft, setDraft] = useState("");

  const handleGenerateTese = () => {
    // Simulação de chamada de API para o AI Brain
    setTese(
      "Com base no contexto tributário, a tese recomendada é a Exclusão do ICMS da base de cálculo do PIS/COFINS (Tema 69 STF).",
    );
    setStep(2);
  };

  const handleGenerateDraft = () => {
    setDraft(
      "EXCELENTÍSSIMO SENHOR DOUTOR JUIZ FEDERAL... \n\n Trata-se de ação visando a recuperação de créditos...",
    );
    setStep(3);
  };

  return (
    <div className="bg-stone-900 border border-warn-900/30 p-8 rounded-lg shadow-2xl max-w-4xl mx-auto">
      <h2 className="text-3xl font-serif text-warn-500 mb-6">
        Escrita Assistida (Modo Elite)
      </h2>

      <div className="flex justify-between mb-8">
        {[1, 2, 3].map((s) => (
          <div
            key={s}
            className={`flex items-center ${step >= s ? "text-warn-500" : "text-stone-600"}`}
          >
            <div
              className={`w-8 h-8 rounded-full border-2 flex items-center justify-center mr-2 ${step >= s ? "border-warn-500" : "border-stone-600"}`}
            >
              {s}
            </div>
            <span className="font-medium">
              {s === 1 ? "Contexto" : s === 2 ? "Tese" : "Peça"}
            </span>
          </div>
        ))}
      </div>

      {step === 1 && (
        <div className="space-y-4">
          <p className="text-stone-300">
            Descreva o caso ou cole a movimentação processual:
          </p>
          <textarea
            className="w-full h-40 bg-stone-800 border border-warn-900/20 text-stone-200 p-4 rounded focus:ring-1 focus:ring-warn-500 outline-none"
            value={context}
            onChange={(e) => setContext(e.target.value)}
            placeholder="Ex: Cliente recebeu autuação fiscal sobre faturamento de 2023..."
          />
          <button
            onClick={handleGenerateTese}
            className="btn-gold px-6 py-3 font-bold"
          >
            Analisar e Sugerir Tese
          </button>
        </div>
      )}

      {step === 2 && (
        <div className="space-y-4 animate-fade-in">
          <div className="bg-warn-900/10 border-l-4 border-warn-600 p-4">
            <h3 className="text-warn-500 font-bold mb-2">
              Tese Sugerida pela IA:
            </h3>
            <p className="text-stone-200">{tese}</p>
          </div>
          <p className="text-stone-300">
            Deseja prosseguir com a redação desta peça?
          </p>
          <div className="flex space-x-4">
            <button
              onClick={handleGenerateDraft}
              className="btn-gold px-6 py-3 font-bold"
            >
              Sim, Gerar Minuta Completa
            </button>
            <button
              onClick={() => setStep(1)}
              className="bg-stone-700 hover:bg-stone-600 text-white px-6 py-3 rounded font-bold transition-all"
            >
              Ajustar Contexto
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div className="space-y-4 animate-fade-in">
          <h3 className="text-warn-500 font-bold">
            Minuta Gerada (Visual Law Ready):
          </h3>
          <div className="bg-stone-800 border border-warn-900/20 p-6 rounded h-96 overflow-y-auto text-stone-200 font-serif whitespace-pre-wrap">
            {draft}
          </div>
          <div className="flex space-x-4">
            <button className="btn-gold px-6 py-3 font-bold">
              Exportar para PDF/Word
            </button>
            <button
              onClick={() => setStep(1)}
              className="bg-stone-700 hover:bg-stone-600 text-white px-6 py-3 rounded font-bold transition-all"
            >
              Nova Peça
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default EscritaAssistida;
