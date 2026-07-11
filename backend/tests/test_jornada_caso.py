"""Jornada do Caso — /casos/{case_id}/jornada.

Sem Postgres real (padrão test_provas.py): as regras de status são funções
PURAS em routers/jornada_caso.py — testadas com fakes leves (SimpleNamespace),
sem sessão de banco. Cobre: cada etapa nos 3 status, ordem/presença das 9
etapas (montar_etapas) e a montagem da rota em main (contrato /api).
"""
from __future__ import annotations

from types import SimpleNamespace

from app.routers.jornada_caso import (
    _etapa_cliente,
    _etapa_documentos,
    _etapa_estrategia,
    _etapa_gestao,
    _etapa_inteligencia,
    _etapa_producao,
    _etapa_protocolo,
    _etapa_revisao,
    _etapa_triagem,
    montar_etapas,
)
from app.schemas.jornada_caso import ORDEM_ETAPAS


def _client(**kw) -> SimpleNamespace:
    base = dict(id="cli1", tipo="PF", cpf="123.456.789-00", cpf_enc=None,
                cnpj=None, cnpj_enc=None, email="a@b.com", telefone=None,
                whatsapp=None, nome_exibicao="Maria")
    base.update(kw)
    return SimpleNamespace(**base)


# ── Rota montada em main (contrato /api — par do test_api_contract) ──────────

def test_rota_montada_em_main():
    from app.main import app
    paths = {getattr(r, "path", "") for r in app.routes}
    assert any(p == "/api/casos/{case_id}/jornada" for p in paths)


# ── Ordem e presença das 9 etapas ─────────────────────────────────────────────

def test_montar_etapas_9_etapas_na_ordem_canonica():
    etapas = montar_etapas(
        case_id="c1", client=None, total_analises=0, total_docs=0,
        docs_processados=0, status_dossies=[], tem_tese_principal=False,
        teses_vinculadas=0, pecas_por_status={}, numero_processo=None,
        fase="pre_processual", caso_fechado=False, prazos_abertos=0, saude=None,
    )
    assert [e.chave for e in etapas] == list(ORDEM_ETAPAS)
    assert len(etapas) == 9
    for e in etapas:
        assert e.status in ("pendente", "em_andamento", "concluida")
        assert e.titulo and e.resumo and e.link_modulo


# ── cliente ───────────────────────────────────────────────────────────────────

def test_cliente_pendente_sem_cliente():
    e = _etapa_cliente(None, "c1")
    assert e.status == "pendente"
    assert e.link_modulo == "/clientes"
    assert e.pendencias


def test_cliente_em_andamento_dados_incompletos_lista_campos():
    e = _etapa_cliente(_client(cpf=None, email=None, telefone=None,
                               whatsapp=None), "c1")
    assert e.status == "em_andamento"
    assert "CPF não cadastrado" in e.pendencias
    assert "contato (email/telefone/whatsapp) ausente" in e.pendencias
    assert e.link_modulo == "/clientes/cli1"
    # LGPD: nenhum dado sensível na resposta.
    assert "123" not in e.resumo


def test_cliente_pj_exige_cnpj():
    e = _etapa_cliente(_client(tipo="PJ", cpf=None, cnpj=None), "c1")
    assert e.status == "em_andamento"
    assert "CNPJ não cadastrado" in e.pendencias


def test_cliente_concluida_com_dados_completos():
    e = _etapa_cliente(_client(), "c1")
    assert e.status == "concluida"
    assert e.pendencias == []
    # LGPD: o CPF nunca aparece no resumo.
    assert "123.456" not in e.resumo


def test_cliente_cifrado_conta_como_documento_presente():
    # Dual-write LGPD: cpf_enc preenchido (texto puro vazio) ainda é cadastro OK.
    e = _etapa_cliente(_client(cpf=None, cpf_enc="gAAAA..."), "c1")
    assert e.status == "concluida"


# ── triagem ───────────────────────────────────────────────────────────────────

def test_triagem_pendente_sem_ailog():
    e = _etapa_triagem(0, "c1")
    assert e.status == "pendente" and e.pendencias


def test_triagem_concluida_com_ailog():
    e = _etapa_triagem(2, "c1")
    assert e.status == "concluida"
    assert e.link_modulo == "/casos/c1"


# ── documentos ────────────────────────────────────────────────────────────────

def test_documentos_pendente_sem_docs():
    e = _etapa_documentos(0, 0, "c1")
    assert e.status == "pendente"
    assert e.link_modulo == "/documentos?caso=c1"


def test_documentos_em_andamento_intake_incompleto():
    e = _etapa_documentos(3, 1, "c1")
    assert e.status == "em_andamento"
    assert any("2" in p for p in e.pendencias)


def test_documentos_concluida_todos_processados():
    e = _etapa_documentos(3, 3, "c1")
    assert e.status == "concluida" and e.pendencias == []


# ── inteligencia ──────────────────────────────────────────────────────────────

def test_inteligencia_pendente_sem_dossie():
    assert _etapa_inteligencia([], "c1").status == "pendente"


def test_inteligencia_dossie_arquivado_nao_conta():
    assert _etapa_inteligencia(["arquivado"], "c1").status == "pendente"


def test_inteligencia_em_andamento_so_rascunho():
    e = _etapa_inteligencia(["rascunho"], "c1")
    assert e.status == "em_andamento"
    assert e.link_modulo == "/casos/c1/sala-de-guerra"


def test_inteligencia_concluida_com_aprovado():
    assert _etapa_inteligencia(["rascunho", "aprovado"], "c1").status == "concluida"


# ── estrategia ────────────────────────────────────────────────────────────────

def test_estrategia_pendente_sem_nada():
    assert _etapa_estrategia(False, 0, "c1").status == "pendente"


def test_estrategia_em_andamento_com_teses_vinculadas():
    e = _etapa_estrategia(False, 2, "c1")
    assert e.status == "em_andamento"
    assert e.link_modulo == "/casos/c1/sala-de-guerra"


def test_estrategia_concluida_com_tese_principal():
    assert _etapa_estrategia(True, 0, "c1").status == "concluida"


# ── producao ──────────────────────────────────────────────────────────────────

def test_producao_pendente_sem_pecas():
    e = _etapa_producao({}, "c1")
    assert e.status == "pendente"
    assert e.link_modulo == "/pecas?caso=c1"


def test_producao_em_andamento_com_rascunho_e_resumo_contagens():
    e = _etapa_producao({"rascunho": 2, "aprovada": 1}, "c1")
    assert e.status == "em_andamento"
    assert "rascunho: 2" in e.resumo and "aprovada: 1" in e.resumo


def test_producao_concluida_todas_prontas():
    e = _etapa_producao({"aprovada": 1, "protocolada": 2}, "c1")
    assert e.status == "concluida"


# ── revisao ───────────────────────────────────────────────────────────────────

def test_revisao_pendente_sem_pecas():
    assert _etapa_revisao({}, "c1").status == "pendente"


def test_revisao_em_andamento_aguardando_revisao():
    e = _etapa_revisao({"em_revisao": 1, "corrigida": 1, "aprovada": 1}, "c1")
    assert e.status == "em_andamento"
    assert any("2" in p for p in e.pendencias)


def test_revisao_concluida_todas_aprovadas():
    e = _etapa_revisao({"aprovada": 2, "final": 1}, "c1")
    assert e.status == "concluida" and e.pendencias == []


# ── protocolo ─────────────────────────────────────────────────────────────────

def test_protocolo_pendente_pre_processual_sem_numero():
    e = _etapa_protocolo(None, "pre_processual", "c1")
    assert e.status == "pendente"
    assert "protocolar e registrar nº do processo" in e.pendencias


def test_protocolo_concluida_com_numero_processo():
    e = _etapa_protocolo("0001234-56.2026.8.13.0027", None, "c1")
    assert e.status == "concluida"


def test_protocolo_concluida_por_fase_alem_da_pre_processual():
    assert _etapa_protocolo(None, "conhecimento", "c1").status == "concluida"


# ── gestao ────────────────────────────────────────────────────────────────────

def test_gestao_pendente_sem_prazos():
    e = _etapa_gestao(False, 0, None, "c1")
    assert e.status == "pendente"
    assert e.link_modulo == "/prazos?caso=c1"


def test_gestao_em_andamento_fase_ativa_com_prazos_monitorados():
    saude = {"score": 80, "fatores": [
        {"fator": "prazo_critico_sem_ciencia", "impacto": -10,
         "detalhe": "1 prazo(s) ≤7 dias sem confirmação de ciência"},
    ]}
    e = _etapa_gestao(False, 3, saude, "c1")
    assert e.status == "em_andamento"
    assert "3 prazo(s)" in e.resumo and "80/100" in e.resumo
    assert any("ciência" in p for p in e.pendencias)


def test_gestao_concluida_caso_fechado():
    e = _etapa_gestao(True, 0, {"score": 95, "fatores": []}, "c1")
    assert e.status == "concluida"
