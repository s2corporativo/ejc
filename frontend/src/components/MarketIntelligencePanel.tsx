import React, { useState } from 'react';

const MarketIntelligencePanel: React.FC = () => {
    const [activeTab, setActiveTab] = useState('competitors');

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-stone-950 p-8">
            <div className="max-w-7xl mx-auto">
                {/* Header */}
                <div className="mb-12">
                    <h1 className="text-4xl font-serif font-bold text-amber-500 mb-2">📊 Market Intelligence</h1>
                    <p className="text-stone-400">Análise de Concorrentes e Recomendações de Nicho</p>
                </div>

                {/* Tabs */}
                <div className="flex space-x-4 mb-8 border-b border-amber-900/10 pb-4">
                    {['competitors', 'pricing', 'niches'].map((tab) => (
                        <button
                            key={tab}
                            onClick={() => setActiveTab(tab)}
                            className={`px-6 py-2 font-medium text-sm transition-all rounded-t-lg ${
                                activeTab === tab
                                    ? 'bg-amber-600/20 text-amber-400 border-b-2 border-amber-500'
                                    : 'text-stone-400 hover:text-amber-400'
                            }`}
                        >
                            {tab === 'competitors' && '🏢 Concorrentes'}
                            {tab === 'pricing' && '💰 Precificação'}
                            {tab === 'niches' && '🎯 Nichos'}
                        </button>
                    ))}
                </div>

                {/* Content */}
                {activeTab === 'competitors' && (
                    <div className="space-y-6">
                        <div className="rounded-2xl bg-gradient-to-br from-stone-800/50 to-stone-900/50 border border-amber-900/20 p-8 backdrop-blur-xl">
                            <h2 className="text-2xl font-serif font-bold text-amber-400 mb-6">Principais Concorrentes (Betim/MG)</h2>
                            <div className="space-y-4">
                                {[
                                    { name: "Advocacia Silva & Associados", wins: 12, price_factor: 0.95, specialties: ["Tributário", "Empresarial"] },
                                    { name: "Consultoria Jurídica Beta", wins: 8, price_factor: 1.05, specialties: ["Licitações", "Contratos"] },
                                    { name: "Escritório Jurídico Delta", wins: 5, price_factor: 1.10, specialties: ["Ambiental", "Regulatório"] }
                                ].map((competitor, i) => (
                                    <div key={i} className="p-6 bg-stone-700/30 rounded-lg border border-stone-700 hover:border-amber-600/40 transition-all">
                                        <div className="flex justify-between items-start mb-4">
                                            <div>
                                                <h3 className="text-lg font-bold text-white">{competitor.name}</h3>
                                                <p className="text-sm text-stone-400">Licitações Vencidas: <span className="text-amber-400 font-bold">{competitor.wins}</span></p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-xs text-stone-400">Fator de Preço</p>
                                                <p className={`text-lg font-bold ${competitor.price_factor < 1 ? 'text-green-400' : 'text-red-400'}`}>
                                                    {competitor.price_factor.toFixed(2)}x
                                                </p>
                                            </div>
                                        </div>
                                        <div className="flex flex-wrap gap-2">
                                            {competitor.specialties.map((spec, j) => (
                                                <span key={j} className="text-xs bg-amber-900/20 text-amber-300 px-3 py-1 rounded-full">
                                                    {spec}
                                                </span>
                                            ))}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'pricing' && (
                    <div className="rounded-2xl bg-gradient-to-br from-stone-800/50 to-stone-900/50 border border-amber-900/20 p-8 backdrop-blur-xl">
                        <h2 className="text-2xl font-serif font-bold text-amber-400 mb-6">Análise de Preços</h2>
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            <div className="p-6 bg-stone-700/20 rounded-lg border border-stone-700">
                                <p className="text-stone-400 text-sm uppercase tracking-widest mb-2">Preço Médio de Mercado</p>
                                <p className="text-3xl font-serif font-bold text-amber-400">R$ 10.000</p>
                            </div>
                            <div className="p-6 bg-stone-700/20 rounded-lg border border-stone-700">
                                <p className="text-stone-400 text-sm uppercase tracking-widest mb-2">Preço Recomendado (Seu)</p>
                                <p className="text-3xl font-serif font-bold text-green-400">R$ 9.500</p>
                                <p className="text-xs text-stone-400 mt-2">5% abaixo da média</p>
                            </div>
                            <div className="p-6 bg-stone-700/20 rounded-lg border border-stone-700">
                                <p className="text-stone-400 text-sm uppercase tracking-widest mb-2">Vantagem Competitiva</p>
                                <p className="text-3xl font-serif font-bold text-amber-500">+15%</p>
                                <p className="text-xs text-stone-400 mt-2">Chance de ganho</p>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'niches' && (
                    <div className="space-y-6">
                        <div className="rounded-2xl bg-gradient-to-br from-stone-800/50 to-stone-900/50 border border-amber-900/20 p-8 backdrop-blur-xl">
                            <h2 className="text-2xl font-serif font-bold text-amber-400 mb-6">Recomendações de Nicho</h2>
                            <div className="space-y-4">
                                {[
                                    { niche: "Tributário (Recuperação de Créditos)", roi: "Alto", reason: "Seu êxito em Tributário é 94%", action: "Focar em PIS/COFINS" },
                                    { niche: "Licitações (Defesa de Concorrentes)", roi: "Médio-Alto", reason: "Expertise comprovada em licitações", action: "Desenvolver material de marketing" },
                                    { niche: "Direito Ambiental", roi: "Médio", reason: "Crescente demanda de compliance", action: "Investir em certificações" }
                                ].map((rec, i) => (
                                    <div key={i} className={`p-6 rounded-lg border ${rec.roi === 'Alto' ? 'bg-green-900/10 border-green-600/30' : 'bg-amber-900/10 border-amber-600/30'}`}>
                                        <div className="flex justify-between items-start mb-3">
                                            <h3 className="text-lg font-bold text-white">{rec.niche}</h3>
                                            <span className={`px-3 py-1 rounded-full text-xs font-bold ${rec.roi === 'Alto' ? 'bg-green-900/30 text-green-300' : 'bg-amber-900/30 text-amber-300'}`}>
                                                ROI: {rec.roi}
                                            </span>
                                        </div>
                                        <p className="text-stone-300 mb-3">{rec.reason}</p>
                                        <button className="text-sm bg-amber-600 hover:bg-amber-500 text-white px-4 py-2 rounded transition-colors">
                                            {rec.action}
                                        </button>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default MarketIntelligencePanel;
