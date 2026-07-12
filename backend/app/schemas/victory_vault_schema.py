from pydantic import BaseModel
from typing import Optional

class TeseVitoriosaCreate(BaseModel):
    titulo: str
    ementa: str
    area_juridica: str
    data_vitoria: str
    link: Optional[str] = None

class TeseVitoriosa(TeseVitoriosaCreate):
    id: str

class ModeloDocumentoCreate(BaseModel):
    tipo_documento: str
    area_juridica: str
    conteudo_template: str
    descricao: Optional[str] = None

class ModeloDocumento(ModeloDocumentoCreate):
    id: str
