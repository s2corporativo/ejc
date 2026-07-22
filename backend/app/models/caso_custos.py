# ── app/models/caso_custos.py ────────────────────────────────────────────────
"""
SUGESTÃO 20: Custo Real por Caso e Cliente (Unit Economics)

Modelos para registrar custos internos (horas, tarefas, despesas) e cruzar
com valores recebidos, exibindo margens de contribuição por caso/cliente.

Benefícios:
- Identifica clientes rentáveis vs. problemáticos
- Revela casos de alto consumo de recursos
- Permite precificação baseada em dados reais
- Suporta decisões de aceitar/recusar casos similares
"""
from __future__ import annotations
from sqlalchemy import Column, String, DateTime, Enum as SAEnum, func, Text, Numeric, ForeignKey, Integer, Date
from sqlalchemy.orm import relationship
from app.core.database import Base
import enum


class TipoCusto(str, enum.Enum):
    """Tipos de custos registráveis."""
    hora_advogado = "hora_advogado"         # Tempo de advogado (custo hora * horas)
    hora_estagiario = "hora_estagiario"     # Tempo de estagiário
    custas_processuais = "custas_processuais"  # Taxas judiciais
    pericias = "pericias"                   # Custos com peritos
    deslocamento = "deslocamento"           # Viagens, combustível, Uber
    correio = "correio"                     # Postagem, AR
    fotocopia = "fotocopia"                 # Reproduções
    sistema_terceiro = "sistema_terceiro"   # Assinaturas (DataJud, infosimples, etc)
    honorarios_terceiros = "honorarios_terceiros"  # Advogados correspondentes
    outro = "outro"


class UnidadeCusto(str, enum.Enum):
    """Unidade de medida do custo."""
    hora = "hora"
    minuto = "minuto"
    unidade = "unidade"
    km = "km"
    pagina = "pagina"


class CustoCaso(Base):
    """
    Registro de custo individual associado a um caso.
    
    Cada lançamento representa um custo real incorrido.
    Pode ser automático (timesheet) ou manual (despesas).
    """
    __tablename__ = "custos_caso"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    
    # Tipo e descrição
    tipo = Column(SAEnum(TipoCusto), nullable=False)
    descricao = Column(String(255), nullable=False)
    
    # Unidade e quantidade
    unidade = Column(SAEnum(UnidadeCusto), nullable=False, default=UnidadeCusto.unidade)
    quantidade = Column(Numeric(10, 2), nullable=False)  # Ex: 2.5 horas, 100 páginas
    
    # Valor unitário e total
    valor_unitario = Column(Numeric(14, 2), nullable=False)  # Custo por unidade
    valor_total = Column(Numeric(14, 2), nullable=False)     # quantidade * valor_unitario
    
    # Profissional responsável (se aplicável)
    profissional_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    cliente_horas_id = Column(String(36), ForeignKey("time_entries.id"), nullable=True)  # Link com timesheet
    
    # Data do custo
    data_ocorrencia = Column(Date, nullable=False)
    data_lancamento = Column(DateTime(timezone=True), server_default=func.now())
    lancado_por = Column(String(36), ForeignKey("users.id"), nullable=False)
    
    # Status
    aprovado = Column(Boolean, default=True)  # Se foi aprovado pela gestão
    aprovador_id = Column(String(36), ForeignKey("users.id"), nullable=True)
    data_aprovacao = Column(DateTime(timezone=True), nullable=True)
    
    # Observações e anexos
    observacoes = Column(Text, nullable=True)
    documento_comprovante_id = Column(String(36), ForeignKey("documents.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relacionamentos
    case = relationship("Case", back_populates="custos")
    profissional = relationship("User", foreign_keys=[profissional_id])
    lancador = relationship("User", foreign_keys=[lancado_por])
    aprovador = relationship("User", foreign_keys=[aprovador_id])
    time_entry = relationship("TimeEntry", foreign_keys=[cliente_horas_id])
    documento_comprovante = relationship("Document", foreign_keys=[documento_comprovante_id])


class CentroCustoCaso(Base):
    """
    Consolidação de custos por centro de custo dentro de um caso.
    Permite análise por área de atuação, tipo de serviço, etc.
    """
    __tablename__ = "centros_custo_caso"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    centro_custo_id = Column(String(36), ForeignKey("centro_custos.id"), nullable=False, index=True)
    
    # Totais consolidados (atualizados periodicamente)
    total_horas = Column(Numeric(10, 2), default=0)
    total_custo = Column(Numeric(14, 2), default=0)
    
    # Período de consolidação
    mes_referencia = Column(Date, nullable=False)  # Primeiro dia do mês
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relacionamentos
    case = relationship("Case")
    centro_custo = relationship("CentroCusto")


class IndicadorRentabilidade(Base):
    """
    Snapshot mensal de indicadores de rentabilidade por caso.
    Calculado automaticamente ao final de cada mês.
    """
    __tablename__ = "indicadores_rentabilidade"

    id = Column(String(36), primary_key=True)
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    client_id = Column(String(36), ForeignKey("clients.id"), nullable=False, index=True)
    
    # Período
    mes_referencia = Column(Date, nullable=False)
    
    # Receitas
    receita_honorarios_fixos = Column(Numeric(14, 2), default=0)
    receita_honorarios_exito = Column(Numeric(14, 2), default=0)
    receita_sucumbencia = Column(Numeric(14, 2), default=0)
    receita_desembolso = Column(Numeric(14, 2), default=0)
    receita_total = Column(Numeric(14, 2), default=0)
    
    # Custos
    custo_mao_obra = Column(Numeric(14, 2), default=0)      # Horas dos profissionais
    custo_custas = Column(Numeric(14, 2), default=0)        # Custas processuais
    custo_despesas = Column(Numeric(14, 2), default=0)      # Despesas diversas
    custo_terceiros = Column(Numeric(14, 2), default=0)     # Correspondentes, peritos
    custo_sistemas = Column(Numeric(14, 2), default=0)      # Assinaturas rateadas
    custo_total = Column(Numeric(14, 2), default=0)
    
    # Indicadores calculados
    margem_bruta = Column(Numeric(14, 2), default=0)        # receita_total - custo_total
    margem_percentual = Column(Numeric(5, 2), default=0)    # (margem_bruta / receita_total) * 100
    
    # Horas trabalhadas
    horas_totais = Column(Numeric(10, 2), default=0)
    ticket_medio_hora = Column(Numeric(14, 2), default=0)   # receita_total / horas_totais
    
    # Status
    calculado_em = Column(DateTime(timezone=True), nullable=True)
    revisado = Column(Boolean, default=False)
    revisado_por = Column(String(36), ForeignKey("users.id"), nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relacionamentos
    case = relationship("Case")
    client = relationship("Client")
    revisor = relationship("User")


# Adicionar relacionamentos no modelo Case (back_populates)
# Isso deve ser importado após a definição completa dos modelos
def setup_relationships():
    """Configura relacionamentos bidirecionais."""
    from app.models.case import Case
    
    if not hasattr(Case, 'custos'):
        Case.custos = relationship("CustoCaso", back_populates="case", cascade="all, delete-orphan")


class Boolean(bool):
    """Placeholder para type hint."""
    pass
