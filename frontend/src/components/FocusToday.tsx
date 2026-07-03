import React, { useEffect, useState } from 'react';

interface FocusData {
    critical_tasks_count: number;
    liquidity_alerts_count: number;
    next_deadlines: string[];
    revenue_opportunities: string[];
}

const FocusToday: React.FC = () => {
    const [data, setData] = useState<FocusData | null>(null);

    useEffect(() => {
        // Simulação de carregamento de dados do novo endpoint /api/v1/workflow/focus-today
        setTimeout(() => {
            setData({
                critical_tasks_count: 4,
                liquidity_alerts_count: 2,
                next_deadlines: [
                    "Réplica - Caso #1029 (ICMS)",
                    "Protocolo - Recurso STJ",
                    "Análise de Edital - Pref. Betim",
                    "Reunião de Alinhamento - Dr. Clovis"
                ],
                revenue_opportunities: [
                    "Alvará Expedido no Caso #882 - Cobrar Honorários",
                    "Trânsito em Julgado Caso #771 - Iniciar Execução"
                ]
            });
        }, 1000);
    }, []);

    if (!data) return <div className="text-warn-500 animate-pulse">Sincronizando com o Cérebro EJC...</div>;

    return (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 p-6">
            {/* Coluna 1: Crítico */}
            <div className="bg-stone-900 border-l-4 border-danger-700 p-6 rounded shadow-lg">
                <h2 className="text-xl font-bold text-danger-500 mb-4 flex items-center">
                    <span className="mr-2">🔥</span> FOCO NO HOJE (CRÍTICO)
                </h2>
                <div className="space-y-3">
                    {data.next_deadlines.map((item, i) => (
                        <div key={i} className="flex justify-between items-center bg-stone-800 p-3 rounded border border-stone-700">
                            <span className="text-stone-200">{item}</span>
                            <span className="text-xs bg-danger-900/30 text-danger-400 px-2 py-1 rounded">URGENTE</span>
                        </div>
                    ))}
                </div>
            </div>

            {/* Coluna 2: Oportunidade (Gatilhos de Liquidez) */}
            <div className="bg-stone-900 border-l-4 border-warn-600 p-6 rounded shadow-lg">
                <h2 className="text-xl font-bold text-warn-500 mb-4 flex items-center">
                    <span className="mr-2">💰</span> GATILHOS DE LIQUIDEZ
                </h2>
                <div className="space-y-3">
                    {data.revenue_opportunities.map((item, i) => (
                        <div key={i} className="bg-warn-900/10 p-3 rounded border border-warn-900/20">
                            <p className="text-warn-200 text-sm mb-2">{item}</p>
                            <button className="btn-gold text-xs px-3 py-1">
                                ACIONAR COBRANÇA
                            </button>
                        </div>
                    ))}
                    {data.revenue_opportunities.length === 0 && (
                        <p className="text-stone-500 italic">Nenhum gatilho detectado hoje.</p>
                    )}
                </div>
            </div>

            {/* Resumo de Performance (Inspirado no EasyJur) */}
            <div className="md:col-span-2 bg-stone-900 border border-stone-800 p-6 rounded flex justify-around items-center">
                <div className="text-center">
                    <p className="text-stone-500 text-xs uppercase tracking-widest">Eficiência da IA</p>
                    <p className="text-3xl font-serif text-warn-500">98.4%</p>
                </div>
                <div className="w-px h-12 bg-stone-800"></div>
                <div className="text-center">
                    <p className="text-stone-500 text-xs uppercase tracking-widest">Horas Salvas (Mês)</p>
                    <p className="text-3xl font-serif text-warn-500">124h</p>
                </div>
                <div className="w-px h-12 bg-stone-800"></div>
                <div className="text-center">
                    <p className="text-stone-500 text-xs uppercase tracking-widest">Status do Cérebro</p>
                    <p className="text-3xl font-serif text-green-500 uppercase text-sm">Soberano (Local)</p>
                </div>
            </div>
        </div>
    );
};

export default FocusToday;
