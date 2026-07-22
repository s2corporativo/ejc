# ── app/services/shadow_mode_eval.py ─────────────────────────────────────────
"""
SUGESTÃO 21: "Shadow Mode" para Novos Prompts

Sistema de avaliação comparativa que roda novos prompts em paralelo com os atuais
antes de deploy em produção. Se a nova versão for pior em mais de 5% dos casos,
o deploy é automaticamente bloqueado.

Componentes:
1. ShadowModeRunner - Executa prompts antigos e novos em paralelo
2. PromptComparator - Compara saídas e calcula métricas
3. DeploymentGate - Decide se novo prompt pode ir para produção
"""
from __future__ import annotations
import json
import hashlib
from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.prompt_juridico import PromptJuridico
from app.models.ai_log import AILog


@dataclass
class MetricasComparacao:
    """Métricas de comparação entre versões de prompt."""
    total_casos: int = 0
    vitorias_nova_versao: int = 0
    vitorias_versao_atual: int = 0
    empates: int = 0
    percentual_melhoria: float = 0.0
    diferenca_media_tokens: float = 0.0
    diferenca_tempo_medio_ms: float = 0.0
    blocar_deploy: bool = False
    motivo_bloqueio: Optional[str] = None
    
    # Métricas detalhadas por tipo de tarefa
    metricas_por_tarefa: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class ResultadoExecucao:
    """Resultado de uma execução de prompt."""
    prompt_id: str
    versao: str
    input_hash: str
    output: str
    tokens_usados: int
    tempo_execucao_ms: int
    confianca_ia: Optional[int]
    citacoes_geradas: List[str]
    erros: List[str]
    timestamp: datetime


class ShadowModeRunner:
    """
    Executor de testes em shadow mode.
    
    Uso:
        runner = ShadowModeRunner(db_session)
        
        # Executar comparação
        resultado = runner.executar_comparacao(
            prompt_id_atual="uuid-prompt-atual",
            prompt_id_novo="uuid-prompt-novo",
            casos_teste=[...],  # Lista de inputs de teste
            threshold_melhoria=5.0  # Precisa melhorar 5% para aprovar
        )
    """
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.resultados: List[Dict] = []
    
    def executar_comparacao(
        self,
        prompt_id_atual: str,
        prompt_id_novo: str,
        casos_teste: List[Dict],
        threshold_melhoria: float = 5.0
    ) -> MetricasComparacao:
        """
        Executa comparação shadow mode entre duas versões de prompt.
        
        Args:
            prompt_id_atual: ID do prompt em produção
            prompt_id_novo: ID do novo prompt candidato
            casos_teste: Lista de inputs de teste (gold set)
            threshold_melhoria: Percentual mínimo de melhoria para aprovar
        
        Returns:
            MetricasComparacao com decisão de deploy
        """
        metricas = MetricasComparacao(total_casos=len(casos_teste))
        
        if len(casos_teste) == 0:
            metricas.blocar_deploy = True
            metricas.motivo_bloqueio = "Nenhum caso de teste fornecido"
            return metricas
        
        # Carregar prompts
        prompt_atual = self._carregar_prompt(prompt_id_atual)
        prompt_novo = self._carregar_prompt_novo(prompt_id_novo)
        
        if not prompt_atual or not prompt_novo:
            metricas.blocar_deploy = True
            metricas.motivo_bloqueio = "Prompts não encontrados"
            return metricas
        
        # Executar cada caso de teste em ambos os prompts
        resultados_paralelos = []
        
        for caso in casos_teste:
            resultado_atual = self._executar_prompt(prompt_atual, caso)
            resultado_novo = self._executar_prompt(prompt_novo, caso)
            
            resultados_paralelos.append({
                'caso': caso,
                'atual': resultado_atual,
                'novo': resultado_novo
            })
        
        # Comparar resultados
        for resultado in resultados_paralelos:
            comparacao = self._comparar_resultados(
                resultado['atual'],
                resultado['novo'],
                resultado['caso'].get('expected_output')
            )
            
            if comparacao['vencedor'] == 'novo':
                metricas.vitorias_nova_versao += 1
            elif comparacao['vencedor'] == 'atual':
                metricas.vitorias_versao_atual += 1
            else:
                metricas.empates += 1
            
            # Acumular diferenças
            metricas.diferenca_media_tokens += (
                resultado['novo'].tokens_usados - resultado['atual'].tokens_usados
            )
            metricas.diferenca_tempo_medio_ms += (
                resultado['novo'].tempo_execucao_ms - resultado['atual'].tempo_execucao_ms
            )
        
        # Calcular médias
        if metricas.total_casos > 0:
            metricas.diferenca_media_tokens /= metricas.total_casos
            metricas.diferenca_tempo_medio_ms /= metricas.total_casos
            metricas.percentual_melhoria = (
                (metricas.vitorias_nova_versao / metricas.total_casos) * 100
            ) - ((metricas.vitorias_versao_atual / metricas.total_casos) * 100)
        
        # Decidir sobre deploy
        if metricas.percentual_melhoria < threshold_melhoria:
            metricas.blocar_deploy = True
            metricas.motivo_bloqueio = (
                f"Melhoria de {metricas.percentual_melhoria:.1f}% abaixo do threshold de {threshold_melhoria}%"
            )
        
        # Salvar resultados para auditoria
        self._salvar_resultados_shadow_mode(
            prompt_id_atual, prompt_id_novo, metricas, resultados_paralelos
        )
        
        return metricas
    
    def _carregar_prompt(self, prompt_id: str) -> Optional[PromptJuridico]:
        """Carrega prompt atual do banco."""
        return self.db.query(PromptJuridico).filter(
            PromptJuridico.id == prompt_id,
            PromptJuridico.ativo == True
        ).first()
    
    def _carregar_prompt_novo(self, prompt_id: str) -> Optional[PromptJuridico]:
        """Carrega prompt candidato (pode estar em status 'shadow')."""
        return self.db.query(PromptJuridico).filter(
            PromptJuridico.id == prompt_id
        ).first()
    
    def _executar_prompt(
        self, 
        prompt: PromptJuridico, 
        caso_teste: Dict
    ) -> ResultadoExecucao:
        """
        Executa um prompt com um caso de teste.
        Na prática, chamaria o AI Gateway.
        """
        from app.services.ai_gateway import AIGateway
        
        gateway = AIGateway(self.db)
        
        try:
            # Preparar input
            input_texto = self._preparar_input(prompt.template, caso_teste)
            input_hash = hashlib.md5(input_texto.encode()).hexdigest()[:16]
            
            # Executar (simulado - na prática chamaria gateway real)
            inicio = datetime.utcnow()
            
            # TODO: Implementar chamada real ao gateway
            output = f"[Simulação] Output para {prompt.titulo}"
            tokens = len(output.split()) * 2  # Estimativa
            tempo_ms = 1500  # Simulado
            confianca = 75
            
            fim = datetime.utcnow()
            
            return ResultadoExecucao(
                prompt_id=prompt.id,
                versao=prompt.versao,
                input_hash=input_hash,
                output=output,
                tokens_usados=tokens,
                tempo_execucao_ms=tempo_ms,
                confianca_ia=confianca,
                citacoes_geradas=[],
                erros=[],
                timestamp=fim
            )
            
        except Exception as e:
            return ResultadoExecucao(
                prompt_id=prompt.id,
                versao=prompt.versao,
                input_hash="",
                output="",
                tokens_usados=0,
                tempo_execucao_ms=0,
                confianca_ia=None,
                citacoes_geradas=[],
                erros=[str(e)],
                timestamp=datetime.utcnow()
            )
    
    def _preparar_input(self, template: str, caso_teste: Dict) -> str:
        """Prepara input substituindo variáveis no template."""
        input_texto = template
        for chave, valor in caso_teste.items():
            input_texto = input_texto.replace(f"{{{{{chave}}}}}", str(valor))
        return input_texto
    
    def _comparar_resultados(
        self,
        resultado_atual: ResultadoExecucao,
        resultado_novo: ResultadoExecucao,
        expected_output: Optional[str] = None
    ) -> Dict:
        """
        Compara dois resultados e determina vencedor.
        
        Critérios:
        1. Proximidade com expected_output (se disponível)
        2. Menos erros
        3. Mais confiança
        4. Menos tokens (eficiência)
        """
        pontuacao_atual = 0
        pontuacao_novo = 0
        
        # Critério 1: Proximidade com esperado
        if expected_output:
            similaridade_atual = self._calcular_similaridade(
                resultado_atual.output, expected_output
            )
            similaridade_novo = self._calcular_similaridade(
                resultado_novo.output, expected_output
            )
            
            pontuacao_atual += similaridade_atual * 10
            pontuacao_novo += similaridade_novo * 10
        
        # Critério 2: Menos erros
        pontuacao_atual -= len(resultado_atual.erros) * 5
        pontuacao_novo -= len(resultado_novo.erros) * 5
        
        # Critério 3: Mais confiança
        if resultado_atual.confianca_ia:
            pontuacao_atual += resultado_atual.confianca_ia / 10
        if resultado_novo.confianca_ia:
            pontuacao_novo += resultado_novo.confianca_ia / 10
        
        # Critério 4: Eficiência (menos tokens)
        if resultado_novo.tokens_usados < resultado_atual.tokens_usados:
            pontuacao_novo += 2
        
        # Determinar vencedor
        if pontuacao_novo > pontuacao_atual + 3:  # Margem de 3 pontos
            return {'vencedor': 'novo', 'pontuacao_novo': pontuacao_novo, 'pontuacao_atual': pontuacao_atual}
        elif pontuacao_atual > pontuacao_novo + 3:
            return {'vencedor': 'atual', 'pontuacao_novo': pontuacao_novo, 'pontuacao_atual': pontuacao_atual}
        else:
            return {'vencedor': 'empate', 'pontuacao_novo': pontuacao_novo, 'pontuacao_atual': pontuacao_atual}
    
    def _calcular_similaridade(self, texto1: str, texto2: str) -> float:
        """Calcula similaridade entre dois textos (0-1)."""
        # Implementação simplificada - usar fuzzy matching na prática
        palavras1 = set(texto1.lower().split())
        palavras2 = set(texto2.lower().split())
        
        interseccao = palavras1 & palavras2
        uniao = palavras1 | palavras2
        
        if len(uniao) == 0:
            return 0.0
        
        return len(interseccao) / len(uniao)
    
    def _salvar_resultados_shadow_mode(
        self,
        prompt_id_atual: str,
        prompt_id_novo: str,
        metricas: MetricasComparacao,
        resultados_paralelos: List[Dict]
    ):
        """Salva resultados no banco para auditoria."""
        registro = {
            'timestamp': datetime.utcnow().isoformat(),
            'prompt_atual': prompt_id_atual,
            'prompt_novo': prompt_id_novo,
            'metricas': {
                'total_casos': metricas.total_casos,
                'vitorias_nova': metricas.vitorias_nova_versao,
                'vitorias_atual': metricas.vitorias_versao_atual,
                'empates': metricas.empates,
                'percentual_melhoria': metricas.percentual_melhoria,
                'blocar_deploy': metricas.blocar_deploy,
                'motivo_bloqueio': metricas.motivo_bloqueio
            },
            'resultados_detalhados': [
                {
                    'input_hash': r['caso'].get('input_hash', 'unknown'),
                    'vencedor': self._comparar_resultados(r['atual'], r['novo']).get('vencedor')
                }
                for r in resultados_paralelos
            ]
        }
        
        # Salvar em tabela de auditoria (implementação futura)
        # self.db.add(ShadowModeResult(**registro))
        # self.db.commit()
        
        print(f"[Shadow Mode] Resultados salvos: {json.dumps(registro, indent=2)}")


class DeploymentGate:
    """
    Gate de aprovação para deploy de novos prompts.
    
    Uso:
        gate = DeploymentGate(db_session)
        
        pode_deploy = gate.verificar_deploy(prompt_id_novo)
        
        if pode_deploy:
            gate.aprovar_deploy(prompt_id_novo)
        else:
            gate.rejeitar_deploy(prompt_id_novo, motivo="...")
    """
    
    THRESHOLD_PADRAO = 5.0  # 5% de melhoria mínima
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.runner = ShadowModeRunner(db_session)
    
    def verificar_deploy(self, prompt_id_novo: str, threshold: float = None) -> Dict:
        """
        Verifica se um prompt pode ser deployado para produção.
        """
        if threshold is None:
            threshold = self.THRESHOLD_PADRAO
        
        # Buscar último resultado de shadow mode
        ultimo_teste = self._buscar_ultimo_teste(prompt_id_novo)
        
        if not ultimo_teste:
            return {
                'pode_deploy': False,
                'motivo': 'Nenhum teste shadow mode encontrado',
                'recomendacao': 'Executar shadow mode antes de deploy'
            }
        
        metricas = ultimo_teste.get('metricas', {})
        
        if metricas.get('blocar_deploy'):
            return {
                'pode_deploy': False,
                'motivo': metricas.get('motivo_bloqueio'),
                'metricas': metricas
            }
        
        if metricas.get('percentual_melhoria', 0) >= threshold:
            return {
                'pode_deploy': True,
                'motivo': f'Melhoria de {metricas.get("percentual_melhoria"):.1f}% acima do threshold',
                'metricas': metricas
            }
        
        return {
            'pode_deploy': False,
            'motivo': f'Melhoria insuficiente ({metricas.get("percentual_melhoria"):.1f}% < {threshold}%)',
            'metricas': metricas
        }
    
    def aprovar_deploy(self, prompt_id: str) -> bool:
        """Aprova deploy e ativa prompt em produção."""
        prompt = self.db.query(PromptJuridico).filter(
            PromptJuridico.id == prompt_id
        ).first()
        
        if not prompt:
            return False
        
        # Desativar versão anterior
        self.db.query(PromptJuridico).filter(
            PromptJuridico.titulo == prompt.titulo,
            PromptJuridico.id != prompt_id,
            PromptJuridico.ativo == True
        ).update({'ativo': False})
        
        # Ativar nova versão
        prompt.ativo = True
        prompt.status = 'producao'
        prompt.data_deploy_producao = datetime.utcnow()
        
        self.db.commit()
        return True
    
    def rejeitar_deploy(self, prompt_id: str, motivo: str) -> bool:
        """Rejeita deploy e mantém versão atual."""
        prompt = self.db.query(PromptJuridico).filter(
            PromptJuridico.id == prompt_id
        ).first()
        
        if not prompt:
            return False
        
        prompt.status = 'rejeitado'
        prompt.motivo_rejeicao = motivo
        
        self.db.commit()
        return True
    
    def _buscar_ultimo_teste(self, prompt_id: str) -> Optional[Dict]:
        """Busca último teste shadow mode para este prompt."""
        # Implementação simplificada
        # Na prática, consultaria tabela ShadowModeResult
        return None
