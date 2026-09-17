"""Núcleo de ajuizamento — canônico, preflight, TPU e máquina de estados.

Sem Postgres (padrão dominante do projeto): primitivas puras testadas direto,
com objetos simples no lugar das entidades ORM. Cobre:

  - construção do CanonicalJudicialCase a partir de Client/Case/CaseParte/User
    (PF e PJ, múltiplos autores/réus), mascaramento de CPF/CNPJ no snapshot e
    determinismo do hash;
  - preflight: campos obrigatórios, CPF/CNPJ inválido, endereço do polo ativo,
    OAB, MIME/tamanho/hash de documento, sigilo/gratuidade/tutela, capacidade
    do conector (REQUIRES_AUTHORIZATION vira aviso + requisito, não erro);
  - máquina de estados: transições válidas/ inválidas e histórico;
  - matriz de capacidades: escrita só com perfil homologado + credencial.

Dados 100% fictícios (CPF/CNPJ gerados com DV válido para teste).
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.models.ajuizamento import EstadoAjuizamento as E
from app.services.ajuizamento import estados
from app.services.ajuizamento.canonico import (
    CanonicalJudicialCase, DocumentoCanonico, construir_canonico,
    documento_de_document, parte_de_case_parte, representacao_de_usuario, _split_oab,
)
from app.services.ajuizamento.capacidades import (
    ContextoConector, EstadoCapacidade, montar_matriz,
)
from app.services.ajuizamento.preflight import validar_preflight

CPF_VALIDO = "529.982.247-25"
CPF_VALIDO_2 = "111.444.777-35"
CNPJ_VALIDO = "11.222.333/0001-81"


# ── Fixtures leves (sem ORM) ─────────────────────────────────────────────────

def _client(**over):
    base = dict(
        id="cli-1", tipo=SimpleNamespace(value="PF"), nome="Maria da Silva", razao_social=None,
        nome_exibicao="Maria da Silva", documento_plain=CPF_VALIDO, data_nascimento=date(1985, 3, 2),
        profissao="professora", email="maria@example.com", telefone="31999990000", whatsapp=None,
        cep="32600-000", logradouro="Rua A", numero="10", complemento=None, bairro="Centro",
        cidade="Betim", estado="MG",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _case(**over):
    base = dict(
        id="caso-1", client_id="cli-1", tribunal="TJMG", comarca="Betim", vara="2ª Vara Cível",
        valor_causa=Decimal("15000.00"), sigilo_reforcado=False,
        advogado_responsavel_id="adv-1", advogado_auxiliar_id=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


def _parte(**over):
    base = dict(id="p-1", tipo="reu", nome="Empresa XPTO LTDA", cpf_cnpj=CNPJ_VALIDO,
                email=None, telefone=None, papel_processual=None, client_id=None)
    base.update(over)
    return SimpleNamespace(**base)


def _user(**over):
    base = dict(id="adv-1", full_name="Dr. João Teixeira", oab_number="123456/MG",
                djen_oab_numero=None, djen_oab_uf=None)
    base.update(over)
    return SimpleNamespace(**base)


def _filing(**over):
    base = dict(
        id="fil-1", case_id="caso-1", client_id="cli-1", tribunal_code="TJMG", system="pje_mni",
        segment="estadual", degree="1", environment="homologacao", jurisdicao="Betim",
        codigo_localidade="3106705", competencia="Cível", competencia_codigo="1",
        classe_codigo="7", classe_nome="Procedimento Comum Cível",
        assuntos=[{"codigo": "10375", "nome": "Dano Moral", "principal": True}],
        valor_causa=Decimal("15000.00"), nivel_sigilo=0, gratuidade=False, tutela=False,
        prioridade=None, caracteristicas={}, documentos=[], advogados=[{"user_id": "adv-1", "tipo": "advogado"}],
    )
    base.update(over)
    return SimpleNamespace(**base)


_CRIADO_EM = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _doc(**over):
    base = dict(id="doc-1", filename="procuracao.pdf", mimetype="application/pdf", size_bytes=1024,
                sha256="a" * 64, created_at=_CRIADO_EM)
    base.update(over)
    return SimpleNamespace(**base)


def _peticao(sha: str = "b" * 64, signed: bool = True) -> DocumentoCanonico:
    return DocumentoCanonico(
        document_id="peca-1", origem="legal_doc", file_name="inicial.pdf",
        mime_type="application/pdf", size=2048, sha256=sha, document_type="peticao_inicial",
        signed=signed, signature_type="icp_brasil" if signed else None, ordem=0,
    )


def _canonico(**over) -> CanonicalJudicialCase:
    filing = over.pop("filing", None) or _filing()
    case = over.pop("case", None) or _case()
    client = over.pop("client", None) or _client()
    partes = over.pop("partes", None)
    if partes is None:
        partes = [_parte()]
    advogados = over.pop("advogados", None) or [(_user(), "advogado", None)]
    documentos = over.pop("documentos", None)
    if documentos is None:
        documentos = [_peticao(), documento_de_document(_doc(), "procuracao", ordem=1)]
    return construir_canonico(filing=filing, case=case, client=client, partes=partes,
                              advogados=advogados, documentos=documentos)


# ── Canônico ─────────────────────────────────────────────────────────────────

def test_canonico_monta_polos_e_inclui_cliente_no_ativo():
    c = _canonico()
    assert [p.nome for p in c.partes_por_polo("ativo")] == ["Maria da Silva"]
    assert [p.nome for p in c.partes_por_polo("passivo")] == ["Empresa XPTO LTDA"]
    assert c.partes_por_polo("passivo")[0].tipo_pessoa == "juridica"
    assert c.peticao_inicial is not None and c.peticao_inicial.document_type == "peticao_inicial"


def test_canonico_multiplos_autores_e_reus():
    partes = [
        _parte(id="p-a2", tipo="autor", nome="José Souza", cpf_cnpj=CPF_VALIDO_2),
        _parte(id="p-r1", tipo="reu", nome="Empresa XPTO LTDA", cpf_cnpj=CNPJ_VALIDO),
        _parte(id="p-r2", tipo="requerido", nome="Banco YZ S.A.", cpf_cnpj=CNPJ_VALIDO),
    ]
    c = _canonico(partes=partes)
    assert len(c.partes_por_polo("ativo")) == 2      # cliente + José
    assert len(c.partes_por_polo("passivo")) == 2


def test_canonico_snapshot_mascara_documento_e_guarda_hash():
    c = _canonico()
    d = c.to_dict()
    serializado = str(d)
    assert CPF_VALIDO not in serializado and "52998224725" not in serializado
    ativo = [p for p in d["partes"] if p["polo"] == "ativo"][0]
    assert ativo["documento_mascarado"] and ativo["documento_mascarado"].count("*") >= 2
    assert len(ativo["documento_hash"]) == 64
    assert "documento" not in ativo


def test_canonico_herda_valor_da_causa_do_caso_quando_filing_nao_tem():
    c = _canonico(filing=_filing(valor_causa=None))
    assert c.processo.valor_causa == Decimal("15000.00")


def test_canonico_hash_e_deterministico_e_sensivel_a_mudanca():
    c1, c2 = _canonico(), _canonico()
    assert c1.hash() == c2.hash()
    c3 = _canonico(filing=_filing(valor_causa=Decimal("99.00")))
    assert c3.hash() != c1.hash()


def test_parte_advogado_nao_vira_parte_processual():
    assert parte_de_case_parte(_parte(tipo="advogado", nome="Dr. X")) is None


@pytest.mark.parametrize("entrada,esperado", [
    ("123456/MG", ("123456", "MG")),
    ("MG123456", ("123456", "MG")),
    ("123456", ("123456", None)),
    (None, (None, None)),
])
def test_split_oab(entrada, esperado):
    assert _split_oab(entrada, None) == esperado


def test_representacao_usa_oab_do_usuario():
    r = representacao_de_usuario(_user(oab_number="MG98765"))
    assert (r.oab_numero, r.oab_uf) == ("98765", "MG")


# ── Preflight ────────────────────────────────────────────────────────────────

def _matriz_ok():
    perfil = SimpleNamespace(
        ativo=True, authorized=True, homologated_at=datetime.now(timezone.utc),
        production_endpoint_verified=True, credentials_valid=True, tribunal_code="TJMG",
        environment="producao",
    )
    ctx = ContextoConector(settings=SimpleNamespace(), perfil=perfil, credencial_disponivel=True)
    return montar_matriz(conector="pje_mni", sistema="pje_mni", ctx=ctx,
                         declaradas={"file_new_case": (EstadoCapacidade.SUPPORTED, "ok")})


def _matriz_sem_autorizacao():
    ctx = ContextoConector(settings=SimpleNamespace(), perfil=None, credencial_disponivel=False)
    return montar_matriz(conector="pdpj", sistema="pdpj", ctx=ctx,
                         declaradas={"file_new_case": (EstadoCapacidade.SUPPORTED, "ok")})


def test_preflight_caso_completo_fica_pronto():
    r = validar_preflight(_canonico(), _matriz_ok())
    assert r.ready is True, r.errors
    assert r.errors == []


def test_preflight_exige_classe_assunto_valor_e_partes():
    # valor_causa None no filing E no caso: a herança do caso é deliberada, então
    # só some o valor quando nenhuma das duas fontes tem número.
    filing = _filing(classe_codigo=None, assuntos=[], valor_causa=None)
    r = validar_preflight(
        _canonico(filing=filing, case=_case(valor_causa=None), partes=[]), _matriz_ok())
    assert r.ready is False
    assert any("Classe processual" in e for e in r.errors)
    assert any("assunto" in e.lower() for e in r.errors)
    assert any("Valor da causa" in e for e in r.errors)
    assert any("Polo passivo" in e for e in r.errors)
    assert "classe_codigo" in r.missing_fields and "partes" in r.missing_fields


def test_preflight_rejeita_cpf_invalido_do_polo_ativo():
    r = validar_preflight(_canonico(client=_client(documento_plain="111.111.111-11")), _matriz_ok())
    assert r.ready is False
    assert any("CPF/CNPJ inválido" in e for e in r.errors)


def test_preflight_exige_endereco_completo_do_polo_ativo():
    r = validar_preflight(_canonico(client=_client(cep=None, logradouro=None)), _matriz_ok())
    assert any("Endereço incompleto" in e for e in r.errors)


def test_preflight_exige_oab_do_advogado():
    r = validar_preflight(_canonico(advogados=[(_user(oab_number=None), "advogado", None)]), _matriz_ok())
    assert any("OAB" in e for e in r.errors)


def test_preflight_rejeita_mime_adulterado_e_documento_sem_hash():
    docs = [
        _peticao(),
        DocumentoCanonico(document_id="d2", origem="document", file_name="prova.exe",
                          mime_type="application/x-dosexec", size=10, sha256="c" * 64,
                          document_type="probatorio", ordem=1),
        DocumentoCanonico(document_id="d3", origem="document", file_name="sem_hash.pdf",
                          mime_type="application/pdf", size=10, sha256=None,
                          document_type="complementar", ordem=2),
    ]
    r = validar_preflight(_canonico(documentos=docs), _matriz_ok())
    assert any("MIME não aceito" in e for e in r.errors)
    assert any("sem hash SHA-256" in e for e in r.errors)


def test_preflight_rejeita_documento_acima_do_limite():
    docs = [_peticao(), DocumentoCanonico(
        document_id="d2", origem="document", file_name="grande.pdf", mime_type="application/pdf",
        size=50 * 1024 * 1024, sha256="d" * 64, document_type="probatorio", ordem=1)]
    r = validar_preflight(_canonico(documentos=docs), _matriz_ok())
    assert any("tamanho máximo" in e for e in r.errors)


def test_preflight_exige_peticao_inicial():
    docs = [documento_de_document(_doc(), "procuracao", ordem=1)]
    r = validar_preflight(_canonico(documentos=docs), _matriz_ok())
    assert any("Petição inicial não anexada" in e for e in r.errors)


def test_preflight_avisa_gratuidade_sem_comprovante_e_sigilo_sem_justificativa():
    filing = _filing(gratuidade=True, nivel_sigilo=3, tutela=True)
    r = validar_preflight(_canonico(filing=filing), _matriz_ok())
    assert r.ready is True   # avisos não bloqueiam
    texto = " ".join(r.warnings)
    assert "Gratuidade" in texto and "justificativa" in texto and "tutela" in texto


def test_preflight_sigilo_fora_da_faixa_bloqueia():
    r = validar_preflight(_canonico(filing=_filing(nivel_sigilo=9)), _matriz_ok())
    assert any("Nível de sigilo" in e for e in r.errors)


def test_preflight_documento_duplicado_vira_aviso():
    docs = [_peticao(), DocumentoCanonico(
        document_id="d2", origem="document", file_name="copia.pdf", mime_type="application/pdf",
        size=10, sha256=_peticao().sha256, document_type="complementar", ordem=1)]
    r = validar_preflight(_canonico(documentos=docs), _matriz_ok())
    assert r.ready is True
    assert any("duplicado" in w for w in r.warnings)


def test_preflight_sem_autorizacao_avisa_e_lista_requisitos_sem_bloquear():
    r = validar_preflight(_canonico(), _matriz_sem_autorizacao())
    assert r.ready is True
    assert r.authorization_requirements
    assert any("autorização/homologação" in w for w in r.warnings)


def test_preflight_conector_sem_protocolo_e_erro():
    ctx = ContextoConector(settings=SimpleNamespace(), perfil=None, credencial_disponivel=False)
    matriz = montar_matriz(conector="datajud", sistema="datajud", ctx=ctx, declaradas={})
    r = validar_preflight(_canonico(), matriz)
    assert r.ready is False
    assert any("não oferece protocolo" in e for e in r.errors)


def test_preflight_campos_obrigatorios_do_tribunal():
    r = validar_preflight(_canonico(), _matriz_ok(), campos_obrigatorios_destino=("codigo_orgao",))
    assert any("codigo_orgao" in e for e in r.errors)
    assert "caracteristicas.codigo_orgao" in r.missing_fields


def test_preflight_lookup_tpu_desconhecido_vira_aviso_nao_erro():
    r = validar_preflight(_canonico(), _matriz_ok(), lookup_tpu=lambda tipo, codigo: None)
    assert r.ready is True
    assert any("não encontrada no cache TPU" in w or "não encontrado no cache TPU" in w for w in r.warnings)


# ── Máquina de estados ───────────────────────────────────────────────────────

def _filing_estado(estado: E):
    return SimpleNamespace(id="fil-1", estado=estado.value)


def test_transicoes_validas_do_fluxo_feliz():
    seq = [E.PREPARING, E.VALIDATING, E.READY_FOR_REVIEW, E.APPROVED, E.SIGNING,
           E.READY_TO_SUBMIT, E.SUBMITTING, E.CONFIRMED, E.SYNCING, E.CONFIRMED]
    f = _filing_estado(E.DRAFT)
    for alvo in seq:
        linha = estados.transicionar(f, alvo, ator_id="u1")
        assert linha.para_estado == alvo.value
    assert f.estado == E.CONFIRMED.value


def test_transicao_invalida_e_recusada():
    f = _filing_estado(E.DRAFT)
    with pytest.raises(estados.TransicaoInvalida):
        estados.transicionar(f, E.CONFIRMED, ator_id="u1")


def test_nao_aprova_sem_revisao_humana_na_maquina():
    """VALIDATING nunca vai direto a APPROVED — passa por READY_FOR_REVIEW."""
    assert not estados.pode_transicionar(E.VALIDATING, E.APPROVED)
    assert estados.pode_transicionar(E.READY_FOR_REVIEW, E.APPROVED)


def test_cancelado_e_terminal():
    assert estados.TRANSICOES[E.CANCELLED] == frozenset()


def test_estados_protocolados_nao_sao_editaveis():
    assert not (estados.ESTADOS_PROTOCOLADOS & estados.ESTADOS_EDITAVEIS)


# ── Matriz de capacidades ────────────────────────────────────────────────────

def test_escrita_exige_homologacao_completa():
    for campo in ("authorized", "homologated_at", "production_endpoint_verified", "credentials_valid"):
        perfil = SimpleNamespace(ativo=True, authorized=True, homologated_at=datetime.now(timezone.utc),
                                 production_endpoint_verified=True, credentials_valid=True,
                                 tribunal_code="TJMG", environment="producao")
        setattr(perfil, campo, None if campo == "homologated_at" else False)
        ctx = ContextoConector(settings=SimpleNamespace(), perfil=perfil, credencial_disponivel=True)
        m = montar_matriz(conector="pje_mni", sistema="pje_mni", ctx=ctx,
                          declaradas={"file_new_case": (EstadoCapacidade.SUPPORTED, "ok")})
        assert m.estado("file_new_case") == EstadoCapacidade.REQUIRES_AUTHORIZATION, campo
        assert m.requisitos_autorizacao


def test_leitura_nao_e_rebaixada_por_homologacao():
    ctx = ContextoConector(settings=SimpleNamespace(), perfil=None, credencial_disponivel=False)
    m = montar_matriz(conector="datajud", sistema="datajud", ctx=ctx,
                      declaradas={"read_process": (EstadoCapacidade.SUPPORTED, "ok")})
    assert m.estado("read_process") == EstadoCapacidade.SUPPORTED


def test_operacao_nao_declarada_e_unsupported():
    ctx = ContextoConector(settings=SimpleNamespace(), perfil=None)
    m = montar_matriz(conector="datajud", sistema="datajud", ctx=ctx, declaradas={})
    assert m.estado("sign") == EstadoCapacidade.UNSUPPORTED
    assert m.to_dict()["protocolo_real_liberado"] is False
