from pydantic import BaseModel
from typing import List, Optional


class AnaliseTeseRequest(BaseModel):
    tese_juridica: str
    area_juridica: str
    tribunais_selecionados: List[str] = []
    # Opcional: escopo de caso — habilita o isolamento de cliente no RAG
    # (conteúdo restrito só do próprio cliente) e amarra o AILog ao caso.
    case_id: Optional[str] = None


class TeseVitoriosaSimilar(BaseModel):
    id: str
    titulo: str
    ementa: str
    area_juridica: str
    data_vitoria: str
    link: Optional[str] = None


class JurisprudenciaSuporte(BaseModel):
    id: str
    ementa: str
    tribunal: str
    data: str
    link: Optional[str] = None


class SugestaoContextualizada(BaseModel):
    tipo: str
    descricao: str


class AnaliseTeseResponse(BaseModel):
    # None = amostra histórica insuficiente (honestidade estatística / OAB) —
    # NUNCA um número inventado.
    probabilidade_exito: Optional[float] = None
    fonte_probabilidade: Optional[str] = None
    n_amostra: int = 0
    teses_vitoriosas_similares: List[TeseVitoriosaSimilar] = []
    jurisprudencia_suporte: List[JurisprudenciaSuporte] = []
    sugestoes_contextualizadas: List[SugestaoContextualizada] = []
    # Verificador anti-alucinação (citation_check) sobre o material retornado.
    score_citacoes: Optional[int] = None
    avisos: List[str] = []
    # HITL: toda saída deste módulo é rascunho — revisão humana obrigatória.
    status_hitl: str = "rascunho"
