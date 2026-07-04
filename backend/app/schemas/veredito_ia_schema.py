from pydantic import BaseModel
from typing import List, Optional

class AnaliseTeseRequest(BaseModel):
    tese_juridica: str
    area_juridica: str
    tribunais_selecionados: List[str]

class TeseVitoriosaSimilar(BaseModel):
    id: str
    titulo: str
    ementa: str
    area_juridica: str
    data_vitoria: str
    link: Optional[str]

class JurisprudenciaSuporte(BaseModel):
    id: str
    ementa: str
    tribunal: str
    data: str
    link: Optional[str]

class SugestaoContextualizada(BaseModel):
    tipo: str
    descricao: str

class AnaliseTeseResponse(BaseModel):
    # None quando a amostra histórica é estatisticamente insuficiente —
    # honestidade estatística: nunca inventar número sem base.
    probabilidade_exito: Optional[float] = None
    aviso: Optional[str] = None
    amostra: Optional[dict] = None
    teses_vitoriosas_similares: List[TeseVitoriosaSimilar]
    jurisprudencia_suporte: List[JurisprudenciaSuporte]
    sugestoes_contextualizadas: List[SugestaoContextualizada]
