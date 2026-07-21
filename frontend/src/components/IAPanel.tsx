/**
 * IAPanel - Componente unificado para interações com IA
 * Substitui múltiplos componentes dispersos de IA
 * Features: Chat, Análise de Documentos, Extração, Health Check
 */
import React, { useState, useEffect, useRef } from 'react';
import { api } from '../config/api';

interface MensagemChat {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: Date;
}

interface ProviderStatus {
  ativo: boolean;
  configurado: boolean;
}

interface IAPanelProps {
  casoId?: number;
  onClose?: () => void;
}

export const IAPanel: React.FC<IAPanelProps> = ({ casoId, onClose }) => {
  const [tabAtiva, setTabAtiva] = useState<'chat' | 'analise' | 'extracao'>('chat');
  const [mensagens, setMensagens] = useState<MensagemChat[]>([]);
  const [inputUsuario, setInputUsuario] = useState('');
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [providers, setProviders] = useState<Record<string, ProviderStatus>>({});
  const [gatewayAtivo, setGatewayAtivo] = useState(false);
  const mensagensRef = useRef<HTMLDivElement>(null);

  // Verifica saúde da IA ao montar
  useEffect(() => {
    verificarHealth();
    if (casoId) {
      carregarHistoricoCaso();
    }
  }, [casoId]);

  // Scroll automático para última mensagem
  useEffect(() => {
    if (mensagensRef.current) {
      mensagensRef.current.scrollTop = mensagensRef.current.scrollHeight;
    }
  }, [mensagens]);

  const verificarHealth = async () => {
    try {
      const response = await api.get('/ia/health');
      const data = response.data;
      setProviders(data.providers || {});
      setGatewayAtivo(data.gateway_ativo);
      
      if (!data.gateway_ativo) {
        setErro('⚠️ Módulo de IA não está ativado. Contate o administrador.');
      }
    } catch (error) {
      console.error('Erro health check IA:', error);
      setErro('Não foi possível conectar ao serviço de IA');
    }
  };

  const carregarHistoricoCaso = async () => {
    if (!casoId) return;
    try {
      // Implementar quando backend tiver endpoint de histórico
      // const response = await api.get(`/casos/${casoId}/ia-historico`);
      // setMensagens(response.data.mensagens);
    } catch (error) {
      console.error('Erro carregar histórico:', error);
    }
  };

  const enviarMensagem = async () => {
    if (!inputUsuario.trim() || carregando) return;
    
    const novaMensagem: MensagemChat = {
      role: 'user',
      content: inputUsuario,
      timestamp: new Date()
    };
    
    setMensagens(prev => [...prev, novaMensagem]);
    setInputUsuario('');
    setCarregando(true);
    setErro(null);

    try {
      const response = await api.post('/ia/chat', {
        mensagem: inputUsuario,
        caso_id: casoId,
        historico: mensagens.slice(-5).map(m => ({
          role: m.role,
          content: m.content
        }))
      });

      const respostaIA: MensagemChat = {
        role: 'assistant',
        content: response.data.dados.resposta,
        timestamp: new Date()
      };
      
      setMensagens(prev => [...prev, respostaIA]);
    } catch (error: any) {
      console.error('Erro chat IA:', error);
      const msgErro = error.response?.data?.detail || 'Erro ao processar mensagem';
      
      // Traduzir erros técnicos para linguagem leiga
      let erroAmigavel = msgErro;
      if (msgErro.includes('GROQ_API_KEY')) {
        erroAmigavel = 'Configuração de IA incompleta. Contate o suporte.';
      } else if (msgErro.includes('ANTHROPIC')) {
        erroAmigavel = 'Serviço de IA temporariamente indisponível.';
      }
      
      setErro(erroAmigavel);
      
      const msgErroSistema: MensagemChat = {
        role: 'system',
        content: `⚠️ ${erroAmigavel}`,
        timestamp: new Date()
      };
      setMensagens(prev => [...prev, msgErroSistema]);
    } finally {
      setCarregando(false);
    }
  };

  const analisarDocumento = async (texto: string, tipo: string) => {
    setCarregando(true);
    setErro(null);
    
    try {
      const response = await api.post('/ia/analise/documento', {
        texto,
        tipo_analise: tipo,
        contexto: casoId ? `Caso ID: ${casoId}` : undefined
      });
      
      return response.data.dados.analise;
    } catch (error: any) {
      const msgErro = error.response?.data?.detail || 'Erro na análise';
      setErro(msgErro.includes('API_KEY') ? 'Configuração de IA incompleta' : msgErro);
      throw error;
    } finally {
      setCarregando(false);
    }
  };

  const extrairDados = async (documentoId: number, campos: string[]) => {
    setCarregando(true);
    try {
      const response = await api.post('/ia/extracao/dados', {
        documento_id: documentoId,
        campos
      });
      return response.data.dados.extracao;
    } catch (error: any) {
      const msgErro = error.response?.data?.detail || 'Erro na extração';
      setErro(msgErro.includes('API_KEY') ? 'Configuração de IA incompleta' : msgErro);
      throw error;
    } finally {
      setCarregando(false);
    }
  };

  const getStatusVisual = () => {
    if (!gatewayAtivo) {
      return { cor: 'bg-red-100 text-red-800', texto: 'IA Desativada' };
    }
    const ativos = Object.values(providers).filter(p => p.ativo).length;
    if (ativos === 0) {
      return { cor: 'bg-yellow-100 text-yellow-800', texto: 'Sem Providers Ativos' };
    }
    return { cor: 'bg-green-100 text-green-800', texto: `${ativos} Provider(s) Ativo(s)` };
  };

  const status = getStatusVisual();

  return (
    <div className="fixed inset-y-0 right-0 w-full md:w-[600px] bg-white shadow-2xl z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b bg-gray-50">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">Assistente Jurídico IA</h2>
          <span className={`inline-block mt-1 px-2 py-0.5 rounded-full text-xs font-medium ${status.cor}`}>
            {status.texto}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {onClose && (
            <button
              onClick={onClose}
              className="p-2 hover:bg-gray-200 rounded-full transition-colors"
              aria-label="Fechar painel"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Tabs de Funcionalidades */}
      <div className="flex border-b">
        <button
          onClick={() => setTabAtiva('chat')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            tabAtiva === 'chat'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          💬 Chat
        </button>
        <button
          onClick={() => setTabAtiva('analise')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            tabAtiva === 'analise'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          📄 Análise
        </button>
        <button
          onClick={() => setTabAtiva('extracao')}
          className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
            tabAtiva === 'extracao'
              ? 'border-b-2 border-blue-600 text-blue-600'
              : 'text-gray-500 hover:text-gray-700'
          }`}
        >
          🔍 Extração
        </button>
      </div>

      {/* Conteúdo das Tabs */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {tabAtiva === 'chat' && (
          <>
            {/* Área de Mensagens */}
            <div ref={mensagensRef} className="flex-1 overflow-y-auto p-4 space-y-4">
              {mensagens.length === 0 && (
                <div className="text-center text-gray-500 mt-8">
                  <p className="text-lg mb-2">👋 Olá! Sou seu assistente jurídico</p>
                  <p className="text-sm">
                    {casoId 
                      ? 'Estou contextualizado com este caso. Como posso ajudar?'
                      : 'Posso ajudar com análises, pesquisas e dúvidas jurídicas.'}
                  </p>
                </div>
              )}
              
              {mensagens.map((msg, idx) => (
                <div
                  key={idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[80%] rounded-2xl px-4 py-3 ${
                      msg.role === 'user'
                        ? 'bg-blue-600 text-white'
                        : msg.role === 'system'
                        ? 'bg-yellow-100 text-yellow-800 border border-yellow-300'
                        : 'bg-gray-100 text-gray-900'
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                    {msg.timestamp && (
                      <p className={`text-xs mt-1 ${
                        msg.role === 'user' ? 'text-blue-200' : 'text-gray-400'
                      }`}>
                        {msg.timestamp.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}
                      </p>
                    )}
                  </div>
                </div>
              ))}
              
              {carregando && (
                <div className="flex justify-start">
                  <div className="bg-gray-100 rounded-2xl px-4 py-3">
                    <div className="flex space-x-2">
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }}></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }}></div>
                      <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }}></div>
                    </div>
                  </div>
                </div>
              )}
            </div>

            {/* Input */}
            <div className="p-4 border-t bg-white">
              {erro && (
                <div className="mb-3 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                  ⚠️ {erro}
                </div>
              )}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={inputUsuario}
                  onChange={(e) => setInputUsuario(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && !e.shiftKey && enviarMensagem()}
                  placeholder={
                    !gatewayAtivo 
                      ? "IA não disponível no momento" 
                      : "Digite sua pergunta jurídica..."
                  }
                  disabled={!gatewayAtivo || carregando}
                  className="flex-1 px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
                />
                <button
                  onClick={enviarMensagem}
                  disabled={!inputUsuario.trim() || carregando || !gatewayAtivo}
                  className="px-6 py-3 bg-blue-600 text-white rounded-xl hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors font-medium"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                </button>
              </div>
            </div>
          </>
        )}

        {tabAtiva === 'analise' && (
          <div className="p-4 space-y-4 overflow-y-auto flex-1">
            <div className="bg-blue-50 p-4 rounded-lg">
              <h3 className="font-medium text-blue-900 mb-2">📋 Tipos de Análise</h3>
              <div className="grid grid-cols-2 gap-2">
                {['contratual', 'processual', 'risco', 'compliance'].map(tipo => (
                  <button
                    key={tipo}
                    disabled={carregando || !gatewayAtivo}
                    className="px-3 py-2 bg-white border border-blue-200 rounded-lg text-sm text-blue-700 hover:bg-blue-100 disabled:opacity-50 transition-colors"
                  >
                    {tipo.charAt(0).toUpperCase() + tipo.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            <p className="text-sm text-gray-500 text-center mt-8">
              Selecione um documento para iniciar a análise
            </p>
          </div>
        )}

        {tabAtiva === 'extracao' && (
          <div className="p-4 space-y-4 overflow-y-auto flex-1">
            <div className="bg-purple-50 p-4 rounded-lg">
              <h3 className="font-medium text-purple-900 mb-2">🔍 Campos para Extrair</h3>
              <div className="space-y-2">
                {['Partes envolvidas', 'Valor da causa', 'Prazos', 'Pedidos', 'Fundamentos'].map(campo => (
                  <label key={campo} className="flex items-center gap-2">
                    <input type="checkbox" className="rounded text-purple-600" />
                    <span className="text-sm text-purple-800">{campo}</span>
                  </label>
                ))}
              </div>
            </div>
            <p className="text-sm text-gray-500 text-center mt-8">
              Selecione um documento e os campos desejados
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default IAPanel;
