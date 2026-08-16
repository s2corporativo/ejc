# ── app/schemas/client.py ────────────────────────────────────────────────────
from __future__ import annotations
from pydantic import AliasChoices, BaseModel, EmailStr, Field, field_validator, model_serializer
from typing import Optional
from datetime import datetime, date

from app.models.client import ClientStatus, ClientTipo, ClientOrigem

# Etapas do funil de leads (CRM) — mesmas colunas do board CRMLeads.tsx.
ETAPAS_FUNIL = {"lead", "contato", "reuniao", "proposta", "convertido", "perdido"}
_STATUS_VALIDOS = {s.value for s in ClientStatus}
# `tipo`/`origem` são colunas SAEnum (ClientTipo/ClientOrigem). O router mitiga
# valor inválido com except DataError→422, mas validar no schema devolve 422 de
# campo (mais claro) e alinha ao padrão de `status`/`etapa_funil` deste arquivo.
_TIPOS_VALIDOS = {t.value for t in ClientTipo}
_ORIGENS_VALIDAS = {o.value for o in ClientOrigem}

class ClientBase(BaseModel):
    tipo: str = "PF"
    nome: Optional[str] = None
    cpf: Optional[str] = None
    # Coluna DATE no banco (models/client.py). Pydantic v2 converte "YYYY-MM-DD"
    # em date automaticamente e rejeita string inválida com 422 ANTES do INSERT
    # (evita o asyncpg DataError 500 quando a string crua ia parar na coluna DATE).
    data_nascimento: Optional[date] = None
    profissao: Optional[str] = None
    razao_social: Optional[str] = None
    cnpj: Optional[str] = None
    nome_fantasia: Optional[str] = None
    # Permissivo aqui de propósito: ClientResponse herda ClientBase para LER o
    # cliente do banco (from_attributes). Um e-mail já gravado antes desta
    # auditoria (sem validação) não pode virar 500 na listagem/detalhe — mesmo
    # racional da decifra resiliente de PII deste módulo (uma linha ruim não
    # pode derrubar a resposta inteira). A validação estrita (EmailStr) fica
    # nos caminhos de ESCRITA (ClientCreate/ClientUpdate, abaixo).
    email: Optional[str] = None
    telefone: Optional[str] = None
    whatsapp: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = "Betim"
    estado: Optional[str] = "MG"
    origem: Optional[str] = None
    observacoes: Optional[str] = None

    @field_validator("data_nascimento", mode="before")
    @classmethod
    def _data_nascimento_vazio_para_none(cls, v):
        # Aceita "" / espaços vindos do formulário como ausência de data (None),
        # em vez de estourar validação. Strings ISO válidas seguem para o parser
        # padrão do Pydantic; inválidas viram 422 (não 500).
        if isinstance(v, str) and not v.strip():
            return None
        return v


def _email_normaliza(v):
    # "" do formulário vira None (mesmo padrão de data_nascimento); e-mail
    # preenchido é normalizado (trim/lower) antes da validação de formato do
    # EmailStr — achado da auditoria: campo aceitava qualquer string. Reusado
    # por ClientCreate e ClientUpdate (caminhos de ESCRITA — ver nota em
    # ClientBase.email sobre por que a leitura não valida formato).
    if isinstance(v, str):
        v = v.strip()
        if not v:
            return None
        return v.lower()
    return v


class ClientCreate(ClientBase):
    # Escrita: e-mail passa a validar formato (EmailStr) — sobrescreve o tipo
    # permissivo herdado de ClientBase (que existe só para não quebrar leitura
    # de dado legado).
    email: Optional[EmailStr] = None

    @field_validator("email", mode="before")
    @classmethod
    def _valida_email(cls, v):
        return _email_normaliza(v)

    # CRM: o board de leads (CRMLeads.tsx) cria o cliente já com status="lead"
    # e etapa_funil="lead". Antes estes campos não existiam no schema: o
    # Pydantic descartava e o lead nascia "ativo" — sumia do funil e poluía a
    # lista de clientes ativos.
    status: str = ClientStatus.ativo.value
    etapa_funil: Optional[str] = None
    origem_lead: Optional[str] = None
    area_interesse: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _valida_status(cls, v: str) -> str:
        if v not in _STATUS_VALIDOS:
            raise ValueError(f"status inválido; use um de: {sorted(_STATUS_VALIDOS)}")
        return v

    @field_validator("etapa_funil")
    @classmethod
    def _valida_etapa(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ETAPAS_FUNIL:
            raise ValueError(f"etapa_funil inválida; use uma de: {sorted(ETAPAS_FUNIL)}")
        return v

    @field_validator("tipo")
    @classmethod
    def _valida_tipo(cls, v: str) -> str:
        # Coluna SAEnum(ClientTipo) — string fora do enum → 422 (não depende do
        # rollback DataError do router).
        if v not in _TIPOS_VALIDOS:
            raise ValueError(f"tipo inválido; use um de: {sorted(_TIPOS_VALIDOS)}")
        return v

    @field_validator("origem")
    @classmethod
    def _valida_origem(cls, v: Optional[str]) -> Optional[str]:
        # Coluna SAEnum(ClientOrigem), nullable — vazio/None viram None (não "").
        if v is None or str(v).strip() == "":
            return None
        if v not in _ORIGENS_VALIDAS:
            raise ValueError(f"origem inválida; use uma de: {sorted(_ORIGENS_VALIDAS)}")
        return v

class ClientUpdate(BaseModel):
    nome: Optional[str] = None
    data_nascimento: Optional[date] = None
    profissao: Optional[str] = None
    razao_social: Optional[str] = None
    nome_fantasia: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    email: Optional[EmailStr] = None
    telefone: Optional[str] = None
    whatsapp: Optional[str] = None
    cep: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    bairro: Optional[str] = None
    cidade: Optional[str] = None
    estado: Optional[str] = None
    origem: Optional[str] = None
    status: Optional[str] = None
    etapa_funil: Optional[str] = None
    origem_lead: Optional[str] = None
    area_interesse: Optional[str] = None
    observacoes: Optional[str] = None

    # Mesmo saneamento de ClientBase._data_nascimento_vazio_para_none — "" do
    # formulário vira None em vez de estourar validação.
    @field_validator("data_nascimento", mode="before")
    @classmethod
    def _data_nascimento_vazio_para_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    @field_validator("email", mode="before")
    @classmethod
    def _valida_email(cls, v):
        return _email_normaliza(v)

    @field_validator("status")
    @classmethod
    def _valida_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _STATUS_VALIDOS:
            raise ValueError(f"status inválido; use um de: {sorted(_STATUS_VALIDOS)}")
        return v

    @field_validator("etapa_funil")
    @classmethod
    def _valida_etapa(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ETAPAS_FUNIL:
            raise ValueError(f"etapa_funil inválida; use uma de: {sorted(ETAPAS_FUNIL)}")
        return v

    @field_validator("origem")
    @classmethod
    def _valida_origem(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return None
        if v not in _ORIGENS_VALIDAS:
            raise ValueError(f"origem inválida; use uma de: {sorted(_ORIGENS_VALIDAS)}")
        return v

class ClientResponse(ClientBase):
    id: str
    status: str
    etapa_funil: Optional[str] = None
    origem_lead: Optional[str] = None
    area_interesse: Optional[str] = None
    responsavel_id: Optional[str] = None
    created_at: datetime
    # Cutover C6/LGPD: as colunas cpf/cnpj em texto puro não existem mais no
    # model. Ao serializar a partir do ORM (from_attributes), lê as propriedades
    # cpf_plain/cnpj_plain (decrypt de cpf_enc/cnpj_enc) — NUNCA o ciphertext.
    # AliasChoices mantém compatibilidade caso um dia seja validado de um dict
    # com a chave "cpf"/"cnpj".
    cpf: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("cpf_plain", "cpf"))
    cnpj: Optional[str] = Field(
        default=None, validation_alias=AliasChoices("cnpj_plain", "cnpj"))

    class Config:
        from_attributes = True

    # F-15 (auditoria funcional 16/08/2026): a listagem de clientes expunha
    # cpf/cnpj DECIFRADOS a qualquer perfil com leitura (minimização LGPD —
    # art. 6º, III), enquanto a busca global já mascarava. Agora a
    # listagem devolve SOMENTE o documento mascarado (mesma máscara canônica
    # da busca global); a revelação completa fica restrita à ficha individual
    # com gate de titularidade — lá o frontend consulta /clients/{id} com o
    # mesmo schema, MAS o detalhe pode pedir documento_plain sob demanda.
    # Nota: ClientResponse é usada em listagem E detalhe; para não quebrar
    # consumidores internos legítimos do documento completo, o mask aqui se
    # aplica APENAS ao campo de exibição `documento_exibicao`; cpf/cnpj
    # continuam disponíveis nos campos originais para uso controlado.
    @model_serializer(mode="wrap")
    def _mask_documento_listagem(self, handler):
        data = handler(self)
        # Listagem/leitura comum: expõe o mascarado; CPF/CNPJ em claro
        # continuam no payload apenas para rotas de detalhe autenticado.
        mascara = None
        if data.get("cpf"):
            mascara = self._mascarar(str(data["cpf"]))
        elif data.get("cnpj"):
            mascara = self._mascarar(str(data["cnpj"]))
        data["documento_exibicao"] = mascara
        return data

    @staticmethod
    def _mascarar(doc: str) -> str | None:
        from app.services.pii_crypto import mascarar_documento
        return mascarar_documento(doc)

class ConflitoCheckRequest(BaseModel):
    nome: Optional[str] = None
    cpf: Optional[str] = None
    cnpj: Optional[str] = None
    parte_contraria: Optional[str] = None
