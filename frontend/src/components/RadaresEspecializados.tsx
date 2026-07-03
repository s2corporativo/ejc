import React, { useState } from 'react';
import { Briefcase, DollarSign, Leaf, Scale, Building2, TrendingUp } from 'lucide-react';

interface RadarProps {
  titulo: string;
  icone: React.ReactNode;
  cor: string;
  alertas: Array<{
    id: string;
    titulo: string;
    descricao: string;
    data: string;
    prioridade: 'alta' | 'média' | 'baixa';
  }>;
}

const RadarCard: React.FC<RadarProps> = ({ titulo, icone, cor, alertas }) => {
  const [expandido, setExpandido] = useState(false);

  const prioridadeColor = {
    alta: 'bg-danger-500/20 text-danger-300 border-danger-500/30',
    média: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
    baixa: 'bg-green-500/20 text-green-300 border-green-500/30',
  };

  return (
    <div className={`bg-slate-800/50 border ${cor} rounded-xl p-4 hover:shadow-lg transition-all cursor-pointer`}
         onClick={() => setExpandido(!expandido)}>
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          {icone}
          <h3 className="font-bold text-white">{titulo}</h3>
        </div>
        <span className="bg-slate-700 text-slate-300 px-3 py-1 rounded-full text-sm font-medium">
          {alertas.length}
        </span>
      </div>

      {expandido && (
        <div className="space-y-2 mt-4 pt-4 border-t border-slate-700">
          {alertas.map(alerta => (
            <div key={alerta.id} className={`p-3 rounded-lg border ${prioridadeColor[alerta.prioridade]}`}>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <p className="font-medium text-sm">{alerta.titulo}</p>
                  <p className="text-xs opacity-80 mt-1">{alerta.descricao}</p>
                </div>
                <span className="text-xs opacity-60 ml-2 whitespace-nowrap">
                  {new Date(alerta.data).toLocaleDateString('pt-BR')}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const RadaresEspecializados: React.FC = () => {
  const radares = [
    {
      titulo: 'Radar Trabalhista',
      icone: <Briefcase className="w-5 h-5 text-primary-400" />,
      cor: 'border-primary-500/30 hover:border-primary-500/50',
      alertas: [
        {
          id: '1',
          titulo: 'Nova Súmula TST',
          descricao: 'Súmula sobre direitos de trabalhadoras gestantes',
          data: new Date().toISOString(),
          prioridade: 'alta' as const,
        },
        {
          id: '2',
          titulo: 'Alteração CLT',
          descricao: 'Mudança em normas de segurança e saúde no trabalho',
          data: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
          prioridade: 'média' as const,
        },
      ],
    },
    {
      titulo: 'Radar Tributário',
      icone: <DollarSign className="w-5 h-5 text-green-400" />,
      cor: 'border-green-500/30 hover:border-green-500/50',
      alertas: [
        {
          id: '1',
          titulo: 'Alteração ICMS',
          descricao: 'Nova alíquota para operações interestaduais',
          data: new Date().toISOString(),
          prioridade: 'alta' as const,
        },
        {
          id: '2',
          titulo: 'Decisão CARF',
          descricao: 'Precedente sobre dedutibilidade de despesas',
          data: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
          prioridade: 'baixa' as const,
        },
      ],
    },
    {
      titulo: 'Radar Ambiental',
      icone: <Leaf className="w-5 h-5 text-success-400" />,
      cor: 'border-success-500/30 hover:border-success-500/50',
      alertas: [
        {
          id: '1',
          titulo: 'Nova Resolução CONAMA',
          descricao: 'Normas para proteção de áreas de preservação',
          data: new Date().toISOString(),
          prioridade: 'alta' as const,
        },
      ],
    },
    {
      titulo: 'Radar Administrativo',
      icone: <Scale className="w-5 h-5 text-ai-400" />,
      cor: 'border-ai-500/30 hover:border-ai-500/50',
      alertas: [
        {
          id: '1',
          titulo: 'Decisão TCU',
          descricao: 'Precedente sobre contratações públicas',
          data: new Date().toISOString(),
          prioridade: 'alta' as const,
        },
        {
          id: '2',
          titulo: 'Portaria MJ',
          descricao: 'Novas diretrizes para processos administrativos',
          data: new Date(Date.now() - 1 * 24 * 60 * 60 * 1000).toISOString(),
          prioridade: 'média' as const,
        },
      ],
    },
    {
      titulo: 'Radar Bancário',
      icone: <Building2 className="w-5 h-5 text-cyan-400" />,
      cor: 'border-cyan-500/30 hover:border-cyan-500/50',
      alertas: [
        {
          id: '1',
          titulo: 'Circular BACEN',
          descricao: 'Novos procedimentos para operações de crédito',
          data: new Date().toISOString(),
          prioridade: 'alta' as const,
        },
      ],
    },
  ];

  return (
    <div className="w-full max-w-6xl mx-auto p-6 bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl shadow-2xl border border-slate-700">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <TrendingUp className="w-8 h-8 text-warn-500" />
          <h2 className="text-3xl font-bold text-white">Radares Especializados</h2>
        </div>
        <p className="text-slate-300">Monitoramento por área jurídica - Clique para expandir</p>
      </div>

      {/* Grid de Radares */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {radares.map((radar, idx) => (
          <RadarCard
            key={idx}
            titulo={radar.titulo}
            icone={radar.icone}
            cor={radar.cor}
            alertas={radar.alertas}
          />
        ))}
      </div>

      {/* Resumo Geral */}
      <div className="mt-8 pt-6 border-t border-slate-700">
        <h3 className="text-lg font-bold text-white mb-4">Resumo Geral</h3>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          {radares.map((radar, idx) => (
            <div key={idx} className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-center">
              <div className="text-2xl font-bold text-warn-500 mb-1">{radar.alertas.length}</div>
              <div className="text-xs text-slate-400">{radar.titulo.replace('Radar ', '')}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default RadaresEspecializados;
