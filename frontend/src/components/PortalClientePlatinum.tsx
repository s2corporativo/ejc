import React, { useState } from "react";

interface ClientCase {
  id: number;
  title: string;
  status: "Em Andamento" | "Concluído" | "Aguardando";
  successProbability: number;
  nextDeadline: string;
  totalFees: number;
  paidFees: number;
}

const PortalClientePlatinum: React.FC = () => {
  const [cases, setCases] = useState<ClientCase[]>([
    {
      id: 1,
      title: "Ação Tributária - ICMS",
      status: "Em Andamento",
      successProbability: 82,
      nextDeadline: "2026-07-15",
      totalFees: 15000,
      paidFees: 5000,
    },
    {
      id: 2,
      title: "Recurso Administrativo - Prefeitura",
      status: "Aguardando",
      successProbability: 65,
      nextDeadline: "2026-08-20",
      totalFees: 8000,
      paidFees: 8000,
    },
  ]);

  const getStatusColor = (status: string) => {
    switch (status) {
      case "Em Andamento":
        return "bg-primary-900/20 border-primary-600 text-primary-300";
      case "Concluído":
        return "bg-green-900/20 border-green-600 text-green-300";
      case "Aguardando":
        return "bg-warn-900/20 border-warn-600 text-warn-300";
      default:
        return "bg-stone-800";
    }
  };

  const getSuccessProbabilityColor = (prob: number) => {
    if (prob >= 80) return "text-green-400";
    if (prob >= 60) return "text-warn-400";
    return "text-danger-400";
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-stone-950 via-stone-900 to-stone-950 p-8">
      {/* Header */}
      <div className="max-w-6xl mx-auto mb-12">
        <div className="flex justify-between items-center mb-8">
          <div>
            <h1 className="text-4xl font-serif text-warn-500 mb-2">
              Portal Platinum
            </h1>
            <p className="text-stone-400">
              Transparência Total de Seus Processos
            </p>
          </div>
          <div className="text-right">
            <p className="text-stone-400 text-sm">Bem-vindo,</p>
            <p className="text-xl font-bold text-warn-500">
              Dr. Cliente Platinum
            </p>
          </div>
        </div>

        {/* KPIs Resumidos */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-12">
          <div className="bg-stone-800/50 border border-warn-900/30 p-6 rounded-lg backdrop-blur">
            <p className="text-stone-400 text-sm uppercase tracking-widest mb-2">
              Processos Ativos
            </p>
            <p className="text-3xl font-serif text-warn-500">{cases.length}</p>
          </div>
          <div className="bg-stone-800/50 border border-warn-900/30 p-6 rounded-lg backdrop-blur">
            <p className="text-stone-400 text-sm uppercase tracking-widest mb-2">
              Taxa Média de Êxito
            </p>
            <p className="text-3xl font-serif text-green-400">73.5%</p>
          </div>
          <div className="bg-stone-800/50 border border-warn-900/30 p-6 rounded-lg backdrop-blur">
            <p className="text-stone-400 text-sm uppercase tracking-widest mb-2">
              Próximo Prazo
            </p>
            <p className="text-sm font-bold text-warn-400">15 de Julho</p>
          </div>
          <div className="bg-stone-800/50 border border-warn-900/30 p-6 rounded-lg backdrop-blur">
            <p className="text-stone-400 text-sm uppercase tracking-widest mb-2">
              Investimento Total
            </p>
            <p className="text-3xl font-serif text-warn-500">R$ 23.000</p>
          </div>
        </div>
      </div>

      {/* Casos Detalhados */}
      <div className="max-w-6xl mx-auto">
        <h2 className="text-2xl font-serif text-warn-500 mb-6">
          Seus Processos
        </h2>
        <div className="space-y-6">
          {cases.map((caseItem) => (
            <div
              key={caseItem.id}
              className="bg-stone-800/30 border border-warn-900/20 rounded-lg p-8 backdrop-blur hover:bg-stone-800/50 transition-all"
            >
              <div className="flex justify-between items-start mb-6">
                <div>
                  <h3 className="text-xl font-bold text-warn-400 mb-2">
                    {caseItem.title}
                  </h3>
                  <p className="text-stone-400">
                    Processo #{caseItem.id.toString().padStart(4, "0")}
                  </p>
                </div>
                <span
                  className={`px-4 py-2 rounded-full border text-sm font-bold ${getStatusColor(caseItem.status)}`}
                >
                  {caseItem.status}
                </span>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Termômetro de Vitória */}
                <div>
                  <p className="text-stone-400 text-sm uppercase tracking-widest mb-3">
                    Probabilidade de Êxito
                  </p>
                  <div className="relative h-2 bg-stone-700 rounded-full overflow-hidden mb-2">
                    <div
                      className="h-full bg-gradient-to-r from-danger-600 via-warn-600 to-green-600"
                      style={{ width: `${caseItem.successProbability}%` }}
                    />
                  </div>
                  <p
                    className={`text-lg font-bold ${getSuccessProbabilityColor(caseItem.successProbability)}`}
                  >
                    {caseItem.successProbability}%
                  </p>
                </div>

                {/* Próximo Prazo */}
                <div>
                  <p className="text-stone-400 text-sm uppercase tracking-widest mb-3">
                    Próximo Prazo
                  </p>
                  <p className="text-lg font-bold text-warn-400">
                    {caseItem.nextDeadline}
                  </p>
                  <p className="text-stone-500 text-sm">Faltam 17 dias</p>
                </div>

                {/* Status Financeiro */}
                <div>
                  <p className="text-stone-400 text-sm uppercase tracking-widest mb-3">
                    Investimento
                  </p>
                  <p className="text-lg font-bold text-green-400">
                    R$ {caseItem.paidFees.toLocaleString()}
                  </p>
                  <p className="text-stone-500 text-sm">
                    de R$ {caseItem.totalFees.toLocaleString()}
                  </p>
                </div>
              </div>

              {/* Barra de Progresso Financeiro */}
              <div className="mt-6 pt-6 border-t border-stone-700">
                <div className="flex justify-between items-center mb-2">
                  <p className="text-stone-400 text-sm">Pagamentos</p>
                  <p className="text-warn-400 font-bold">
                    {Math.round((caseItem.paidFees / caseItem.totalFees) * 100)}
                    %
                  </p>
                </div>
                <div className="h-2 bg-stone-700 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-gradient-to-r from-warn-600 to-warn-400"
                    style={{
                      width: `${(caseItem.paidFees / caseItem.totalFees) * 100}%`,
                    }}
                  />
                </div>
              </div>

              {/* Botão de Ação */}
              <div className="mt-6 flex space-x-4">
                <button className="btn-gold flex-1 px-4 py-3 font-bold">
                  Ver Detalhes Completos
                </button>
                <button className="flex-1 bg-stone-700 hover:bg-stone-600 text-white px-4 py-3 rounded font-bold transition-all">
                  Comunicar com Advogado
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="max-w-6xl mx-auto mt-16 pt-8 border-t border-stone-800">
        <p className="text-stone-500 text-sm text-center">
          Portal Platinum © 2026 — Ecossistema Jurídico Clovis. Todos os dados
          são confidenciais e protegidos por LGPD.
        </p>
      </div>
    </div>
  );
};

export default PortalClientePlatinum;
