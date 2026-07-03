import React, { useState } from 'react';
import RadarLegislativo from './RadarLegislativo';
import RadaresEspecializados from './RadaresEspecializados';
import { VictoryVaultPanel } from './VictoryVaultPanel';
import { VeredutoIAWithVictoryVault } from './VeredutoIAWithVictoryVault';
import { AssistedWritingMode } from './AssistedWritingMode';

const DashboardModernLuxury: React.FC = () => {
    const [activeTab, setActiveTab] = useState('overview');

    return (
        <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-stone-950">
            {/* Navigation Bar - Glassmorphism */}
            <nav className="sticky top-0 z-50 backdrop-blur-xl bg-stone-950/40 border-b border-warn-900/10">
                <div className="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
                    <div className="flex items-center space-x-3">
                        <div className="w-10 h-10 bg-gradient-to-br from-warn-600 to-warn-800 rounded-lg flex items-center justify-center">
                            <span className="text-white font-serif font-bold">⚖️</span>
                        </div>
                        <div>
                            <h1 className="text-xl font-serif font-bold text-warn-500">EJC v6.0</h1>
                            <p className="text-xs text-stone-400">Sovereign Diamond</p>
                        </div>
                    </div>
                    <div className="flex items-center space-x-6">
                        <button className="text-stone-400 hover:text-warn-500 transition-colors text-sm font-medium">Notificações</button>
                        <button className="text-stone-400 hover:text-warn-500 transition-colors text-sm font-medium">Configurações</button>
                        <div className="w-10 h-10 bg-gradient-to-br from-warn-600 to-warn-800 rounded-full flex items-center justify-center text-white font-bold">DC</div>
                    </div>
                </div>
            </nav>

            {/* Main Content */}
            <main className="max-w-7xl mx-auto px-6 py-12">
                {/* Header Section */}
                <div className="mb-12">
                    <h2 className="text-4xl md:text-5xl font-serif font-bold text-white mb-2">
                        Bem-vindo, Dr. Clovis
                    </h2>
                    <p className="text-stone-400 text-lg">Seu ecossistema jurídico soberano está operacional</p>
                </div>

                {/* Tab Navigation */}
                    <div className="flex space-x-2 mb-8 border-b border-warn-900/10 pb-4">
                        {['overview', 'cases', 'intelligence', 'audit', 'radars', 'victory_vault', 'veredito_ia', 'escrita_assistida'].map((tab) => (
                            <button
                                key={tab}
                                onClick={() => setActiveTab(tab)}
                                className={`px-6 py-2 font-medium text-sm transition-all rounded-t-lg ${
                                    activeTab === tab
                                        ? 'bg-warn-600/20 text-warn-400 border-b-2 border-warn-500'
                                        : 'text-stone-400 hover:text-warn-400'
                                }`}
                            >
                                {tab === 'overview' && '📊 Visão Geral'}
                                {tab === 'cases' && '📁 Casos'}
                                {tab === 'intelligence' && '🧠 Inteligência'}
                                {tab === 'audit' && '🔍 Auditoria'}
                                {tab === 'radars' && '📡 Radares'}
                                {tab === 'victory_vault' && '🏆 Victory Vault'}
                                {tab === 'veredito_ia' && '⚖️ Veredito IA'}
                                {tab === 'escrita_assistida' && '✍️ Escrita Assistida'}
                            </button>
                        ))}
                    </div>

                {/* Content Grid */}
                {activeTab === 'overview' && (
                    <div className="space-y-8">
                        {/* KPI Cards - Modern Luxury */}
                        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
                            {[
                                { label: 'Casos Ativos', value: '24', icon: '📋', trend: '+3' },
                                { label: 'Taxa de Êxito', value: '87.4%', icon: '✅', trend: '+2.1%' },
                                { label: 'Receita (Mês)', value: 'R$ 145k', icon: '💰', trend: '+12%' },
                                { label: 'IA Soberana', value: 'Online', icon: '🧠', trend: '100%' }
                            ].map((kpi, i) => (
                                <div
                                    key={i}
                                    className="group relative overflow-hidden rounded-2xl bg-gradient-to-br from-stone-800/50 to-stone-900/50 border border-warn-900/20 p-8 hover:border-warn-600/40 transition-all duration-300 backdrop-blur-xl"
                                >
                                    <div className="absolute inset-0 bg-gradient-to-br from-warn-600/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
                                    <div className="relative">
                                        <div className="flex justify-between items-start mb-4">
                                            <span className="text-3xl">{kpi.icon}</span>
                                            <span className="text-xs font-bold text-green-400 bg-green-900/20 px-3 py-1 rounded-full">{kpi.trend}</span>
                                        </div>
                                        <p className="text-stone-400 text-sm uppercase tracking-widest mb-2">{kpi.label}</p>
                                        <p className="text-3xl font-serif font-bold text-white">{kpi.value}</p>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* Main Sections */}
                        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                            {/* Próximos Prazos */}
                            <div className="lg:col-span-2 rounded-2xl bg-gradient-to-br from-stone-800/50 to-stone-900/50 border border-warn-900/20 p-8 backdrop-blur-xl">
                                <h3 className="text-xl font-serif font-bold text-warn-400 mb-6">🔥 Foco no Hoje</h3>
                                <div className="space-y-4">
                                    {[
                                        { title: 'Réplica - Caso #1029', date: 'Hoje', priority: 'high' },
                                        { title: 'Protocolo - STJ', date: 'Amanhã', priority: 'high' },
                                        { title: 'Análise de Edital', date: 'Em 3 dias', priority: 'medium' }
                                    ].map((item, i) => (
                                        <div key={i} className="flex items-center justify-between p-4 bg-stone-700/30 rounded-lg hover:bg-stone-700/50 transition-colors">
                                            <div>
                                                <p className="font-medium text-white">{item.title}</p>
                                                <p className="text-xs text-stone-400">{item.date}</p>
                                            </div>
                                            <div className={`w-3 h-3 rounded-full ${item.priority === 'high' ? 'bg-danger-500' : 'bg-warn-500'}`} />
                                        </div>
                                    ))}
                                </div>
                            </div>

                            {/* Gatilhos de Liquidez */}
                            <div className="rounded-2xl bg-gradient-to-br from-warn-900/20 to-stone-900/50 border border-warn-600/30 p-8 backdrop-blur-xl">
                                <h3 className="text-xl font-serif font-bold text-warn-400 mb-6">💰 Liquidez</h3>
                                <div className="space-y-3">
                                    <div className="p-4 bg-warn-900/20 rounded-lg border border-warn-600/20">
                                        <p className="text-sm text-warn-200 mb-2">Alvará Expedido</p>
                                        <p className="font-bold text-warn-400">Caso #882</p>
                                        <button className="btn-primary mt-3 w-full text-xs font-bold py-2 rounded transition-colors">
                                            ACIONAR COBRANÇA
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Performance Chart */}
                        <div className="rounded-2xl bg-gradient-to-br from-stone-800/50 to-stone-900/50 border border-warn-900/20 p-8 backdrop-blur-xl">
                            <h3 className="text-xl font-serif font-bold text-warn-400 mb-6">📈 Performance (Últimos 30 Dias)</h3>
                            <div className="h-64 bg-stone-700/20 rounded-lg flex items-end justify-around px-4 py-8">
                                {[65, 78, 82, 75, 88, 92, 87].map((value, i) => (
                                    <div key={i} className="flex flex-col items-center">
                                        <div
                                            className="w-8 bg-gradient-to-t from-warn-600 to-warn-400 rounded-t transition-all hover:from-warn-500 hover:to-warn-300"
                                            style={{ height: `${value}%` }}
                                        />
                                        <p className="text-xs text-stone-500 mt-2">{['S', 'T', 'Q', 'Q', 'S', 'S', 'D'][i]}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'intelligence' && (
                    <div className="rounded-2xl bg-gradient-to-br from-stone-800/50 to-stone-900/50 border border-warn-900/20 p-8 backdrop-blur-xl">
                        <h3 className="text-2xl font-serif font-bold text-warn-400 mb-6">🧠 Cérebro EJC (Ollama Local)</h3>
                        <p className="text-stone-300 mb-6">Status: <span className="text-green-400 font-bold">✓ Operacional (100% Soberano)</span></p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div className="p-6 bg-stone-700/20 rounded-lg">
                                <p className="text-warn-400 font-bold mb-2">Modelo IA Ativo</p>
                                <p className="text-white">DeepSeek v2.5 + BGE-M3 Embeddings</p>
                            </div>
                            <div className="p-6 bg-stone-700/20 rounded-lg">
                                <p className="text-warn-400 font-bold mb-2">Base de Conhecimento</p>
                                <p className="text-white">12.500+ Teses + 4M Jurisprudências</p>
                            </div>
                        </div>
                    </div>
                )}

                {activeTab === 'audit' && (
                    <div className="rounded-2xl bg-gradient-to-br from-stone-800/50 to-stone-900/50 border border-warn-900/20 p-8 backdrop-blur-xl">
                        <h3 className="text-2xl font-serif font-bold text-warn-400 mb-6">🔍 Auditoria de Licitações</h3>
                        <p className="text-stone-300 mb-6">Carregue uma proposta de concorrente para análise automática de falhas técnicas e equivalência.</p>
                        <div className="border-2 border-dashed border-warn-600/30 rounded-lg p-12 text-center hover:border-warn-600/60 transition-colors cursor-pointer">
                            <p className="text-3xl mb-4">📄</p>
                            <p className="text-white font-medium mb-2">Arraste um PDF aqui</p>
                            <p className="text-stone-400 text-sm">ou clique para selecionar</p>
                        </div>
                    </div>
                )}

                {activeTab === 'radars' && (
                    <div className="space-y-8">
                        <RadarLegislativo />
                        <RadaresEspecializados />
                    </div>
                )}

                {activeTab === 'victory_vault' && (
                    <div className="space-y-8">
                        <VictoryVaultPanel />
                    </div>
                )}

                {activeTab === 'veredito_ia' && (
                    <div className="space-y-8">
                        <VeredutoIAWithVictoryVault />
                    </div>
                )}

                {activeTab === 'escrita_assistida' && (
                    <div className="space-y-8">
                        <AssistedWritingMode />
                    </div>
                )}
            </main>

            {/* Footer */}
            <footer className="border-t border-warn-900/10 mt-16 py-8 text-center text-stone-500 text-sm">
                <p>EJC v6.0 — Sovereign Diamond © 2026 | Soberania Tecnológica & Luxo Jurídico</p>
            </footer>
        </div>
    );
};

export default DashboardModernLuxury;
