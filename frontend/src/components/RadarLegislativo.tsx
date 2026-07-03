import React, { useState, useEffect } from 'react';
import { AlertCircle, TrendingUp, FileText, Calendar } from 'lucide-react';

interface Legislacao {
  id: string;
  titulo: string;
  tipo: string;
  area: string;
  data_publicacao: string;
  ementa: string;
  url_fonte: string;
}

interface AlertaRegulatorio {
  id: string;
  titulo: string;
  descricao: string;
  tipo_alerta: string;
  area_afetada: string;
  data_alerta: string;
  url_referencia: string;
  resolvido: boolean;
}

const RadarLegislativo: React.FC = () => {
  const [legislacoes, setLegislacoes] = useState<Legislacao[]>([]);
  const [alertas, setAlertas] = useState<AlertaRegulatorio[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedArea, setSelectedArea] = useState<string | null>(null);

  useEffect(() => {
    // Simular carregamento de legislações e alertas
    const mockLegislacoes: Legislacao[] = [
      {
        id: '1',
        titulo: 'Lei nº 14.133/2021 - Nova Lei de Licitações',
        tipo: 'Lei',
        area: 'Administrativa',
        data_publicacao: '2021-04-01',
        ementa: 'Institui normas gerais de licitação e contratação para a Administração Pública.',
        url_fonte: 'https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm',
      },
      {
        id: '2',
        titulo: 'Lei nº 9.784/1999 - Processo Administrativo',
        tipo: 'Lei',
        area: 'Administrativa',
        data_publicacao: '1999-01-29',
        ementa: 'Regula o processo administrativo no âmbito da Administração Federal direta e indireta.',
        url_fonte: 'https://www.planalto.gov.br/ccivil_03/leis/l9784.htm',
      },
    ];

    const mockAlertas: AlertaRegulatorio[] = [
      {
        id: '1',
        titulo: 'Alteração na Lei de Licitações',
        descricao: 'Nova resolução sobre prazos de impugnação em pregões eletrônicos.',
        tipo_alerta: 'Alteração',
        area_afetada: 'Administrativa',
        data_alerta: new Date().toISOString(),
        url_referencia: 'https://www.planalto.gov.br/ccivil_03/_ato2019-2022/2021/lei/l14133.htm',
        resolvido: false,
      },
    ];

    setLegislacoes(mockLegislacoes);
    setAlertas(mockAlertas);
    setLoading(false);
  }, []);

  const areas = ['Administrativa', 'Ambiental', 'Tributária', 'Trabalhista', 'Bancária'];

  const filteredLegislacoes = selectedArea
    ? legislacoes.filter(l => l.area === selectedArea)
    : legislacoes;

  const filteredAlertas = selectedArea
    ? alertas.filter(a => a.area_afetada === selectedArea)
    : alertas;

  return (
    <div className="w-full max-w-6xl mx-auto p-6 bg-gradient-to-br from-slate-900 to-slate-800 rounded-2xl shadow-2xl border border-warn-500/20">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <TrendingUp className="w-8 h-8 text-warn-500" />
          <h2 className="text-3xl font-bold text-white">Radar Legislativo</h2>
        </div>
        <p className="text-slate-300">Monitoramento em tempo real de alterações legislativas</p>
      </div>

      {/* Filtros por Área */}
      <div className="mb-6 flex flex-wrap gap-2">
        <button
          onClick={() => setSelectedArea(null)}
          className={`px-4 py-2 rounded-lg font-medium transition-all ${
            selectedArea === null
              ? 'bg-warn-500 text-slate-900'
              : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
          }`}
        >
          Todas as Áreas
        </button>
        {areas.map(area => (
          <button
            key={area}
            onClick={() => setSelectedArea(area)}
            className={`px-4 py-2 rounded-lg font-medium transition-all ${
              selectedArea === area
                ? 'bg-warn-500 text-slate-900'
                : 'bg-slate-700 text-slate-300 hover:bg-slate-600'
            }`}
          >
            {area}
          </button>
        ))}
      </div>

      {/* Alertas */}
      {filteredAlertas.length > 0 && (
        <div className="mb-8 bg-danger-900/20 border border-danger-500/30 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-4">
            <AlertCircle className="w-6 h-6 text-danger-500" />
            <h3 className="text-xl font-bold text-danger-400">Alertas Regulatórios</h3>
          </div>
          <div className="space-y-3">
            {filteredAlertas.map(alerta => (
              <div
                key={alerta.id}
                className="bg-slate-800/50 border border-danger-500/20 rounded-lg p-4 hover:border-danger-500/50 transition-all"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h4 className="font-bold text-white mb-1">{alerta.titulo}</h4>
                    <p className="text-slate-300 text-sm mb-2">{alerta.descricao}</p>
                    <div className="flex items-center gap-4 text-xs text-slate-400">
                      <span className="bg-danger-500/20 text-danger-300 px-2 py-1 rounded">
                        {alerta.tipo_alerta}
                      </span>
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {new Date(alerta.data_alerta).toLocaleDateString('pt-BR')}
                      </span>
                    </div>
                  </div>
                  {!alerta.resolvido && (
                    <div className="w-3 h-3 bg-danger-500 rounded-full animate-pulse ml-4 mt-1" />
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Legislações */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4 flex items-center gap-2">
          <FileText className="w-6 h-6 text-warn-500" />
          Legislação Recente
        </h3>
        <div className="space-y-3">
          {loading ? (
            <div className="text-center py-8 text-slate-400">Carregando legislações...</div>
          ) : filteredLegislacoes.length > 0 ? (
            filteredLegislacoes.map(leg => (
              <div
                key={leg.id}
                className="bg-slate-800/50 border border-warn-500/20 rounded-lg p-4 hover:border-warn-500/50 transition-all hover:shadow-lg hover:shadow-warn-500/10"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h4 className="font-bold text-white mb-1">{leg.titulo}</h4>
                    <p className="text-slate-300 text-sm mb-2">{leg.ementa}</p>
                    <div className="flex items-center gap-4 text-xs text-slate-400">
                      <span className="bg-warn-500/20 text-warn-300 px-2 py-1 rounded">
                        {leg.tipo}
                      </span>
                      <span className="bg-slate-700 text-slate-300 px-2 py-1 rounded">
                        {leg.area}
                      </span>
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {new Date(leg.data_publicacao).toLocaleDateString('pt-BR')}
                      </span>
                    </div>
                  </div>
                  <a
                    href={leg.url_fonte}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-4 px-3 py-1 bg-warn-500 text-slate-900 rounded font-medium text-sm hover:bg-warn-400 transition-all"
                  >
                    Acessar
                  </a>
                </div>
              </div>
            ))
          ) : (
            <div className="text-center py-8 text-slate-400">
              Nenhuma legislação encontrada para a área selecionada.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default RadarLegislativo;
