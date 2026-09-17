from types import SimpleNamespace

from app.models.case_intelligence import ORIGENS_SNAPSHOT
from app.services.entrada_juridica_service import (
    _correlacionar_fato_prova_tese,
    _estimativa_sucesso,
    _perguntas_lacunas,
    identificar_conteudo,
)


def test_origem_entrada_unica_snapshot_e_aditiva_sem_migration():
    assert "entrada_unica" in ORIGENS_SNAPSHOT


def test_identificar_conteudo_e_preliminar_e_exige_confirmacao():
    out = identificar_conteudo(
        "Fui intimado no processo nº 1234567-89.2026.8.13.0000 e preciso de análise.",
        [{"titulo": "intimacao.pdf", "tipo": "intimacao"}],
    )
    assert "caso_existente" in out["tipos"]
    assert "intimacao" in out["tipos"]
    assert "documento" in out["tipos"]
    assert out["requer_confirmacao_humana"] is True


def test_estimativa_nao_exibe_percentual_sem_base_verificavel():
    out = _estimativa_sucesso(
        {"jurimetria": {"chance_sucesso_percent": 82, "base_estimativa": None}}
    )
    assert out["percentual"] is None
    assert out["status"] == "sem_base_verificavel"


def test_estimativa_exibe_percentual_quando_ha_base_concreta():
    out = _estimativa_sucesso(
        {
            "jurimetria": {
                "chance_sucesso_percent": 64.25,
                "base_estimativa": "amostra interna validada do mesmo tribunal e classe",
                "tempo_estimado_meses": 18,
            }
        }
    )
    assert out["percentual"] == 64.2
    assert out["status"] == "estimativa_interna_com_base"
    assert out["tempo_estimado_meses"] == 18


def test_matriz_fato_prova_tese_nunca_confirma_automaticamente():
    provas = [
        {
            "titulo": "comprovante de pagamento",
            "tipo": "documental",
            "fato_probando": "pagamento integral da obrigação contratual",
            "ja_disponivel": True,
            "quem_produz": "cliente",
            "urgencia": "media",
        }
    ]
    teses = [
        {
            "titulo": "adimplemento contratual",
            "aplicabilidade": "pagamento integral afasta a cobrança do débito",
            "fundamento_legal": "verificar fonte",
        }
    ]
    out = _correlacionar_fato_prova_tese(provas, teses)
    assert len(out) == 1
    assert out[0]["confirmado"] is False
    assert out[0]["prova_ja_disponivel"] is True


def test_lacunas_perguntam_so_o_necessario():
    case = SimpleNamespace(
        numero_processo=None,
        case_type="judicial",
        parte_contraria=None,
    )
    analise = {"brechas_preliminares": {"prescricao": None}}
    provas = [
        {
            "titulo": "contrato assinado",
            "fato_probando": "existência da contratação",
            "ja_disponivel": False,
        }
    ]
    perguntas = _perguntas_lacunas(analise, case, provas)
    tipos = {item["tipo"] for item in perguntas}
    assert {"prova_faltante", "identificacao_processual", "parte", "prescricao"} <= tipos
