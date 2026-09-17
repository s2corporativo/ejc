from types import SimpleNamespace

import pytest

from app.models.case_intelligence import ORIGENS_SNAPSHOT
from app.services.entrada_juridica_service import (
    _correlacionar_fato_prova_tese,
    _estimativa_sucesso,
    _perguntas_lacunas,
    _texto_base_visivel,
    identificar_conteudo,
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


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


def test_texto_base_usa_apenas_lista_pre_filtrada_e_os_cinco_ocr_mais_recentes():
    documentos_visiveis = [
        SimpleNamespace(ocr_text=f"OCR visível {indice}") for indice in range(1, 7)
    ]
    case = SimpleNamespace(descricao_fatos="fallback do caso")

    texto = _texto_base_visivel(documentos_visiveis, case)

    assert texto.startswith("OCR visível 6")
    assert "OCR visível 2" in texto
    assert "OCR visível 1" not in texto
    assert "fallback do caso" not in texto


def test_texto_base_sem_ocr_visivel_faz_fallback_nos_fatos_do_caso():
    documentos_visiveis = [SimpleNamespace(ocr_text=None), SimpleNamespace(ocr_text="  ")]
    case = SimpleNamespace(descricao_fatos="Fatos autorizados do caso")

    assert _texto_base_visivel(documentos_visiveis, case) == "Fatos autorizados do caso"


@pytest.mark.anyio
async def test_analise_estrategica_pode_bloquear_recuperacao_legada_de_ocr(monkeypatch):
    from app.services import ai_gateway
    from app.services import analise_estrategica as ae
    from app.services import document_intake_service
    from app.services import sanitizer

    async def _recuperacao_proibida(**_kwargs):
        raise AssertionError("não deve reconsultar OCR")

    async def _chat(**_kwargs):
        return SimpleNamespace(
            texto=(
                '{"alertas": [], "provas_necessarias": [], "teses_campeas": [], '
                '"riscos": [], "brechas_preliminares": {}, "estrategia": {}, '
                '"proximos_passos": []}'
            )
        )

    monkeypatch.setattr(ae, "_recuperar_ocr_completo_se_truncado", _recuperacao_proibida)
    monkeypatch.setattr(ai_gateway, "chat", _chat)
    monkeypatch.setattr(
        document_intake_service,
        "montar_dossie_documental",
        lambda texto, titulo="": texto,
    )
    monkeypatch.setattr(sanitizer, "sanitizar_pii", lambda texto, nomes=None: (texto, False))
    monkeypatch.setattr(sanitizer, "validar_sem_pii", lambda _texto: [])

    out = await ae.analisar_caso(
        titulo="Caso sintético",
        texto_documento="Contexto documental já filtrado pelo GED.",
        recuperar_ocr_completo=False,
        db=None,
    )

    assert "erro" not in out


@pytest.mark.anyio
async def test_analisar_com_case_id_reusa_rota_canonica_para_dossie(monkeypatch):
    from app.routers import entrada as router

    chamado = {}

    async def _dossie(db, cu, case_id):
        chamado.update(db=db, cu=cu, case_id=case_id)
        return {"status": "rascunho", "case_id": case_id}

    monkeypatch.setattr(
        router.entrada_juridica_service,
        "gerar_dossie_juridico",
        _dossie,
    )
    user = SimpleNamespace(id="u1", role="advogado")
    out = await router.analisar(
        files=[],
        texto=None,
        case_id="case-1",
        db="db",
        cu=user,
    )

    assert out == {"status": "rascunho", "case_id": "case-1"}
    assert chamado == {"db": "db", "cu": user, "case_id": "case-1"}
