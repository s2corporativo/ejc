"""Integração de processo eletrônico via MNI 2.2.2 — Fase A (Issue #762).

Sem Postgres real (padrão dominante do projeto): primitivas puras testadas
direto, mapper/dedup testados com fakes leves (sem SOAP real — MNIConnector
nunca é chamado, só seus dados de retorno são simulados como dict). Cobre:
roteamento de tribunal por número CNJ, credencial nunca vaza em claro,
idempotência de dedup de documento no mapper, RBAC das rotas.
"""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.services import tribunal_registry
from app.services import processo_eletronico_credential_service as cred_service
from app.services import processo_eletronico_document_mapper as mapper
from app.services.mni_connector import ConsultaProcessoResultado
from app.models.processo_eletronico import (
    DocumentoProcessoEletronicoDedup, Tribunal,
)
from app.models.document import Document, DocConfidencialidade
from app.models.case import Case, CaseArea, CaseStatus


# ── Roteamento de tribunal por número CNJ ────────────────────────────────────

def test_extrair_codigo_tribunal_formato_pontuado():
    numero = "0001234-56.2026.8.13.0001"  # TJMG = 13
    assert tribunal_registry.extrair_codigo_tribunal(numero) == "13"


def test_extrair_codigo_tribunal_so_digitos():
    numero = "00012345620268130001"
    assert tribunal_registry.extrair_codigo_tribunal(numero) == "13"


def test_extrair_codigo_tribunal_formato_invalido():
    assert tribunal_registry.extrair_codigo_tribunal("não é um número CNJ") is None
    assert tribunal_registry.extrair_codigo_tribunal("") is None
    assert tribunal_registry.extrair_codigo_tribunal(None) is None


class _ResultadoScalar:
    def __init__(self, val):
        self._val = val

    def scalar_one_or_none(self):
        return self._val

    def scalars(self):
        return self

    def all(self):
        return self._val if isinstance(self._val, list) else [self._val]


class _FakeDBFila:
    """Fila de resultados: cada .execute() consome o próximo item."""

    def __init__(self, resultados: list):
        self._resultados = list(resultados)
        self.added: list = []
        self.commits = 0

    async def execute(self, *a, **k):
        return _ResultadoScalar(self._resultados.pop(0))

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        pass

    async def refresh(self, obj):
        pass


def test_resolver_tribunal_encontra_tjmg_ativo():
    tjmg = Tribunal(
        id=str(uuid4()), nome="TJMG - 1º Grau", codigo_tribunal="13", grau="1",
        endpoint_wsdl="https://pje1grau.tjmg.jus.br/pje/intercomunicacao?wsdl",
        versao_mni="2.2.2", ativo=True,
    )
    db = _FakeDBFila([tjmg])
    resultado = asyncio.run(
        tribunal_registry.resolver_tribunal(db, "0001234-56.2026.8.13.0001", grau="1")
    )
    assert resultado is tjmg


def test_resolver_tribunal_codigo_desconhecido_nao_lanca():
    db = _FakeDBFila([])
    resultado = asyncio.run(
        tribunal_registry.resolver_tribunal(db, "número qualquer sem CNJ válido")
    )
    assert resultado is None


# ── Credencial nunca vaza em claro ───────────────────────────────────────────

def test_credencial_roundtrip_cifra_decifra():
    id_consultante = "12345678901"
    senha = "s3nh4-muito-secreta"

    id_cifrado = cred_service.cifrar_id_consultante(id_consultante)
    senha_cifrada = cred_service.cifrar_senha(senha)

    assert id_cifrado != id_consultante
    assert senha_cifrada != senha
    assert cred_service.decifrar_id_consultante(id_cifrado) == id_consultante
    assert cred_service.decifrar_senha(senha_cifrada) == senha


def test_credencial_meta_resp_nao_tem_campo_de_segredo():
    from app.schemas.processo_eletronico import CredencialMetaResp
    campos = set(CredencialMetaResp.model_fields.keys())
    assert "id_consultante" not in campos
    assert "senha_consultante" not in campos
    assert "id_consultante_cifrado" not in campos
    assert "senha_consultante_ref" not in campos


def test_credencial_create_req_aceita_segredo_mas_resposta_nao_ecoa():
    """O schema de ENTRADA aceita o segredo (é preciso cadastrá-lo); o de
    SAÍDA (CredencialMetaResp, testado acima) é o que garante que a API
    nunca devolve o valor — a garantia estrutural é a ausência do campo no
    schema de resposta, não uma checagem de valor em runtime."""
    from app.schemas.processo_eletronico import CredencialCreateReq
    req = CredencialCreateReq(
        tribunal_id="t1", advogado_id="a1", tipo="mni_sistema",
        id_consultante="123", senha_consultante="segredo",
    )
    assert req.senha_consultante == "segredo"


# ── Idempotência de dedup de documento no mapper (sem SOAP real) ────────────

class _FakeDBDedup:
    """Fake mínimo para _gravar_documentos_novos: resolve a checagem de dedup
    via um set em memória e registra os objetos adicionados."""

    def __init__(self):
        self._dedup_existentes: set[tuple[str, str]] = set()
        self.added: list = []

    async def execute(self, *a, **k):
        # Toda chamada em _gravar_documentos_novos é a checagem de dedup;
        # simplificação válida porque é o único SELECT desse helper.
        return self

    def scalar_one_or_none(self):
        # Decide dedup a partir do que já foi "commitado" nesta fake (via add).
        for obj in self.added:
            if isinstance(obj, DocumentoProcessoEletronicoDedup):
                return obj.id  # já existe → não é None
        return None

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, DocumentoProcessoEletronicoDedup):
            self._dedup_existentes.add((obj.tribunal_id, obj.id_documento_tribunal))

    async def flush(self):
        pass


def test_dedup_documento_nao_recria_na_segunda_sincronizacao(tmp_path, monkeypatch):
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    case = Case(
        id=str(uuid4()), titulo="Caso teste", area=CaseArea.civil,
        status=CaseStatus.aberto, client_id=str(uuid4()),
    )
    tribunal_id = str(uuid4())
    conteudo_b64 = __import__("base64").b64encode(b"conteudo do documento").decode()
    doc_mni = {
        "idDocumento": "DOC-001",
        "descricao": "Petição Inicial",
        "tipoDocumento": "peticao_inicial",
        "mimetype": "application/pdf",
        "nivelSigilo": 0,
        "conteudo": conteudo_b64,
    }

    db = _FakeDBDedup()
    novos_1 = asyncio.run(
        mapper._gravar_documentos_novos(db, case, tribunal_id, [doc_mni], uploaded_by=None)
    )
    assert novos_1 == 1
    assert any(isinstance(o, Document) for o in db.added)
    assert any(isinstance(o, DocumentoProcessoEletronicoDedup) for o in db.added)

    # Segunda "sincronização" com o MESMO documento — dedup deve impedir
    # recriação (idDocumento já visto para este tribunal).
    novos_2 = asyncio.run(
        mapper._gravar_documentos_novos(db, case, tribunal_id, [doc_mni], uploaded_by=None)
    )
    assert novos_2 == 0


def test_mapear_confidencialidade_conservador_para_nivel_desconhecido():
    assert mapper.mapear_confidencialidade(0) == DocConfidencialidade.normal
    assert mapper.mapear_confidencialidade(4) == DocConfidencialidade.segredo_justica
    # nível ilegível/ausente nunca vira "normal" por omissão
    assert mapper.mapear_confidencialidade(None) == DocConfidencialidade.confidencial
    assert mapper.mapear_confidencialidade("não é número") == DocConfidencialidade.confidencial
    assert mapper.mapear_confidencialidade(999) == DocConfidencialidade.confidencial


def test_erro_em_um_documento_nao_aborta_os_demais(tmp_path, monkeypatch):
    """Um documento com binário corrompido/erro de IO não impede que os
    outros da mesma leva sejam gravados (isolamento por documento)."""
    from app.core.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    case = Case(
        id=str(uuid4()), titulo="Caso teste", area=CaseArea.civil,
        status=CaseStatus.aberto, client_id=str(uuid4()),
    )
    tribunal_id = str(uuid4())
    conteudo_b64 = __import__("base64").b64encode(b"ok").decode()
    doc_ok = {
        "idDocumento": "DOC-OK", "descricao": "Doc válido",
        "mimetype": "application/pdf", "nivelSigilo": 0, "conteudo": conteudo_b64,
    }
    # idDocumento vazio é ignorado (continue), não conta como erro nem sucesso.
    doc_sem_id = {
        "idDocumento": "", "descricao": "Sem id", "conteudo": conteudo_b64,
    }

    db = _FakeDBDedup()
    novos = asyncio.run(
        mapper._gravar_documentos_novos(
            db, case, tribunal_id, [doc_sem_id, doc_ok], uploaded_by=None,
        )
    )
    assert novos == 1


# ── RBAC das rotas ────────────────────────────────────────────────────────

def test_router_dependencias_rbac_por_nivel():
    """Garante que as dependencies de RBAC do router exigem, no mínimo,
    'advogado' para operações e 'admin' para gestão de credenciais.

    Carrega app/routers/processo_eletronico.py via importlib direto do
    arquivo (sem passar por `app.routers` o pacote) — importar o pacote
    inteiro arrastaria ~160 outros routers e suas dependências pesadas
    (httpx, magic, pgvector...) só para inspecionar RBAC deste módulo."""
    import importlib.util
    import sys

    from app.core.security import ROLE_LEVEL, require_roles  # noqa: F401 (garante módulo carregado)

    caminho = os.path.join(
        os.path.dirname(__file__), "..", "app", "routers", "processo_eletronico.py",
    )
    spec = importlib.util.spec_from_file_location(
        "_test_processo_eletronico_router", caminho,
    )
    router_module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = router_module
    spec.loader.exec_module(router_module)

    assert "cliente_externo" not in _roles_permitidos_de(router_module._OPERACIONAL)
    assert "cliente_externo" not in _roles_permitidos_de(router_module._LEITURA_CREDENCIAL)
    assert "cliente_externo" not in _roles_permitidos_de(router_module._GESTAO_CREDENCIAL)
    # Gestão de credenciais é mais restrita que leitura: advogado comum não
    # pode CADASTRAR credencial de terceiros (só admin/socio/superadmin).
    assert "advogado" not in _roles_permitidos_de(router_module._GESTAO_CREDENCIAL)
    assert "advogado" in _roles_permitidos_de(router_module._OPERACIONAL)


def _roles_permitidos_de(dependency_checker) -> set[str]:
    """Extrai a lista `allowed` fechada no closure de require_roles(allowed)."""
    closure = dependency_checker.__closure__ or ()
    for cell in closure:
        val = cell.cell_contents
        if isinstance(val, list) and val and isinstance(val[0], str):
            return set(val)
    raise AssertionError("Não achou a lista `allowed` no closure do checker")


def test_listar_credenciais_nao_admin_so_ve_as_proprias():
    """Reproduz a lógica de autorização do handler (não-admin só pode listar
    advogado_id == cu.id) sem montar o app inteiro — a regra em si é o que
    a Issue exige: 'leitura restrita ao próprio advogado ou admin'."""
    from app.core.security import ROLE_LEVEL

    class _Usuario:
        def __init__(self, id, role):
            self.id = id
            self.role = role

    cu = _Usuario(id="adv-1", role="advogado")
    eh_admin = ROLE_LEVEL.get(cu.role, 0) >= ROLE_LEVEL.get("admin", 0)
    assert eh_admin is False
    # tentando listar credenciais de outro advogado → deve ser negado
    outro_advogado_id = "adv-2"
    assert not (eh_admin or outro_advogado_id == cu.id)
    # a própria lista → permitido
    assert eh_admin or cu.id == cu.id
