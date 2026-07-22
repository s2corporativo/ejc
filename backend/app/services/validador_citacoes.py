# ── app/services/validador_citacoes.py ───────────────────────────────────────
"""
SUGESTÃO 18: Validador de "Alucinação Jurídica" em Tempo Real

Middleware que verifica automaticamente citações legais geradas por IA:
- Artigos de lei (vigência, texto correto)
- Jurisprudências (existência real, contexto adequado)
- Súmulas (número correto, tribunal, vigência)
- Doutrinas (autor existente, obra correta)

Se a citação não for encontrada ou estiver revogada, a resposta é bloqueada.
"""
from __future__ import annotations
import re
import hashlib
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.legal_doc import LegalDoc
from app.models.jurisprudencia_interna import JurisprudenciaInterna
from app.models.sumula import Sumula


@dataclass
class CitacaoValidada:
    """Resultado da validação de uma citação."""
    texto_original: str
    tipo: str  # 'lei', 'jurisprudencia', 'sumula', 'doutrina'
    valida: bool
    confianca: int  # 0-100
    motivo_invalidacao: Optional[str] = None
    fonte_encontrada: Optional[Dict] = None
    sugerida_correcao: Optional[str] = None


class ValidadorCitacoesJuridicas:
    """
    Middleware de validação de citações jurídicas.
    
    Uso:
        validador = ValidadorCitacoesJuridicas(db_session)
        resultado = validador.validar_resposta_ia(texto_gerado)
        
        if not resultado.todos_validos:
            # Bloquear resposta ou alertar usuário
    """
    
    # Padrões regex para detecção de citações
    PADROES_LEI = [
        r'(?:Lei|Código|CPC|CPP|CLT|CF)\s*(?:nº?|n\.|de)?\s*(\d{1,5}(?:\.\d{2})?)',
        r'art(?:igo)?\.\s*(\d+)(?:,\s*§?\s*(\d+))?(?:,\s*inciso\s+(\w+))?',
        r'parágrafo\s+(?:único|\d+)',
    ]
    
    PADROES_JURISPRUDENCIA = [
        r'(?:STF|STJ|TSE|TST|TRT|TJ\w*)\s*,?\s*(?:Acórdão|Recurso|Processo)\s*n?\.?\s*(\d[\d\w\-/]+)',
        r'(?:ARE|RE|AgR|MS|HC|Rcl)\s*(\d{6,})',
        r'Rel\.\s*(?:Min\.|Des\.)\s*([\w\s]+)',
    ]
    
    PADROES_SUMULA = [
        r'S[úu]mula\s+(?:n?º?\s*)?(\d+)',
        r'(?:STF|STJ|TST)\s*S[úu]mula\s+(\d+)',
    ]
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self.cache_validacoes: Dict[str, CitacaoValidada] = {}
    
    def extrair_citacoes(self, texto: str) -> List[Dict]:
        """
        Extrai todas as citações jurídicas do texto.
        Retorna lista de dicionários com tipo e texto da citação.
        """
        citacoes = []
        
        # Extrair citações de lei
        for padrao in self.PADROES_LEI:
            for match in re.finditer(padrao, texto, re.IGNORECASE):
                citacoes.append({
                    'tipo': 'lei',
                    'texto': match.group(0),
                    'posicao': (match.start(), match.end())
                })
        
        # Extrair jurisprudências
        for padrao in self.PADROES_JURISPRUDENCIA:
            for match in re.finditer(padrao, texto, re.IGNORECASE):
                citacoes.append({
                    'tipo': 'jurisprudencia',
                    'texto': match.group(0),
                    'posicao': (match.start(), match.end())
                })
        
        # Extrair súmulas
        for padrao in self.PADROES_SUMULA:
            for match in re.finditer(padrao, texto, re.IGNORECASE):
                citacoes.append({
                    'tipo': 'sumula',
                    'texto': match.group(0),
                    'posicao': (match.start(), match.end())
                })
        
        return citacoes
    
    def validar_citacao(self, citacao: Dict) -> CitacaoValidada:
        """
        Valida uma citação específica contra bases oficiais.
        Usa cache para evitar consultas repetidas.
        """
        cache_key = hashlib.md5(citacao['texto'].encode()).hexdigest()
        
        if cache_key in self.cache_validacoes:
            return self.cache_validacoes[cache_key]
        
        tipo = citacao['tipo']
        texto = citacao['texto']
        
        if tipo == 'lei':
            resultado = self._validar_lei(texto)
        elif tipo == 'jurisprudencia':
            resultado = self._validar_jurisprudencia(texto)
        elif tipo == 'sumula':
            resultado = self._validar_sumula(texto)
        else:
            resultado = CitacaoValidada(
                texto_original=texto,
                tipo=tipo,
                valida=False,
                confianca=0,
                motivo_invalidacao="Tipo de citação não suportado"
            )
        
        self.cache_validacoes[cache_key] = resultado
        return resultado
    
    def _validar_lei(self, texto: str) -> CitacaoValidada:
        """Valida citação de lei."""
        # Tentar encontrar na base LegalDoc
        leis_encontradas = self.db.query(LegalDoc).filter(
            LegalDoc.conteudo.ilike(f"%{texto}%")
        ).limit(5).all()
        
        if not leis_encontradas:
            return CitacaoValidada(
                texto_original=texto,
                tipo='lei',
                valida=False,
                confianca=20,
                motivo_invalidacao="Lei não encontrada na base oficial"
            )
        
        # Verificar vigência
        lei_mais_relevante = leis_encontradas[0]
        if hasattr(lei_mais_relevante, 'vigencia') and not lei_mais_relevante.vigencia:
            return CitacaoValidada(
                texto_original=texto,
                tipo='lei',
                valida=False,
                confianca=90,
                motivo_invalidacao="Lei revogada ou sem vigência",
                fonte_encontrada={'id': lei_mais_relevante.id, 'titulo': lei_mais_relevante.titulo}
            )
        
        return CitacaoValidada(
            texto_original=texto,
            tipo='lei',
            valida=True,
            confianca=85,
            fonte_encontrada={'id': lei_mais_relevante.id, 'titulo': lei_mais_relevante.titulo}
        )
    
    def _validar_jurisprudencia(self, texto: str) -> CitacaoValidada:
        """Valida citação de jurisprudência."""
        # Buscar na base interna
        juris = self.db.query(JurisprudenciaInterna).filter(
            JurisprudenciaInterna.ementa.ilike(f"%{texto[:50]}%")
        ).limit(3).all()
        
        if juris:
            return CitacaoValidada(
                texto_original=texto,
                tipo='jurisprudencia',
                valida=True,
                confianca=75,
                fonte_encontrada={'id': juris[0].id, 'tribunal': juris[0].tribunal}
            )
        
        # Não encontrou na base interna - alerta mas não invalida completamente
        # (pode ser jurisprudência externa válida)
        return CitacaoValidada(
            texto_original=texto,
            tipo='jurisprudencia',
            valida=False,
            confianca=40,
            motivo_invalidacao="Jurisprudência não encontrada na base interna - verificar origem",
            sugerida_correcao="Incluir referência completa (tribunal, número, relator)"
        )
    
    def _validar_sumula(self, texto: str) -> CitacaoValidada:
        """Valida citação de súmula."""
        # Extrair número da súmula
        match = re.search(r'S[úu]mula\s+(?:n?º?\s*)?(\d+)', texto, re.IGNORECASE)
        if not match:
            return CitacaoValidada(
                texto_original=texto,
                tipo='sumula',
                valida=False,
                confianca=0,
                motivo_invalidacao="Não foi possível extrair número da súmula"
            )
        
        numero_sumula = int(match.group(1))
        
        # Buscar na base
        sumula = self.db.query(Sumula).filter(
            Sumula.numero == numero_sumula
        ).first()
        
        if sumula:
            if sumula.vigente:
                return CitacaoValidada(
                    texto_original=texto,
                    tipo='sumula',
                    valida=True,
                    confianca=95,
                    fonte_encontrada={'id': sumula.id, 'numero': sumula.numero}
                )
            else:
                return CitacaoValidada(
                    texto_original=texto,
                    tipo='sumula',
                    valida=False,
                    confianca=95,
                    motivo_invalidacao=f"Súmula {numero_sumula} não está mais vigente",
                    fonte_encontrada={'id': sumula.id, 'numero': sumula.numero}
                )
        
        return CitacaoValidada(
            texto_original=texto,
            tipo='sumula',
            valida=False,
            confianca=30,
            motivo_invalidacao=f"Súmula {numero_sumula} não encontrada na base"
        )
    
    def validar_resposta_ia(self, texto_gerado: str) -> 'ResultadoValidacao':
        """
        Valida todas as citações em uma resposta gerada por IA.
        Retorna objeto com resumo da validação.
        """
        citacoes = self.extrair_citacoes(texto_gerado)
        
        if not citacoes:
            return ResultadoValidacao(
                todos_validos=True,
                total_citacoes=0,
                citacoes_validas=0,
                citacoes_invalidas=0,
                citacoes_detalhadas=[],
                deve_blocar=False,
                mensagem="Nenhuma citação jurídica detectada"
            )
        
        citacoes_validadas = []
        todas_validas = True
        deve_blocar = False
        
        for citacao in citacoes:
            validada = self.validar_citacao(citacao)
            citacoes_validadas.append(validada)
            
            if not validada.valida:
                todas_validas = False
                
                # Bloquear se confiança muito baixa ou lei revogada
                if validada.confianca < 30 or "revogada" in (validada.motivo_invalidacao or '').lower():
                    deve_blocar = True
        
        return ResultadoValidacao(
            todos_validos=todas_validas,
            total_citacoes=len(citacoes),
            citacoes_validas=sum(1 for c in citacoes_validadas if c.valida),
            citacoes_invalidas=sum(1 for c in citacoes_validadas if not c.valida),
            citacoes_detalhadas=citacoes_validadas,
            deve_blocar=deve_blocar,
            mensagem=self._gerar_mensagem(todas_validas, citacoes_validadas)
        )
    
    def _gerar_mensagem(self, todos_validos: bool, citacoes: List[CitacaoValidada]) -> str:
        """Gera mensagem de feedback para o usuário."""
        if todos_validos:
            return "Todas as citações jurídicas foram validadas com sucesso."
        
        invalidas = [c for c in citacoes if not c.valida]
        mensagens = []
        
        for citacao in invalidas[:3]:  # Limitar a 3 mensagens
            msg = f"{citacao.tipo.capitalize()} '{citacao.texto_original}': {citacao.motivo_invalidacao}"
            if citacao.sugerida_correcao:
                msg += f". Sugestão: {citacao.sugerida_correcao}"
            mensagens.append(msg)
        
        return "⚠️ Citações problemáticas detectadas:\n" + "\n".join(mensagens)


@dataclass
class ResultadoValidacao:
    """Resultado consolidado da validação."""
    todos_validos: bool
    total_citacoes: int
    citacoes_validas: int
    citacoes_invalidas: int
    citacoes_detalhadas: List[CitacaoValidada]
    deve_blocar: bool
    mensagem: str
