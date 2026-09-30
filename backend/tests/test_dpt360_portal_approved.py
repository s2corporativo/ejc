from app.modules.dpt360.schemas import DptPrepareShareRequest, DptPrepareShareResponse
from app.modules.dpt360.sharing_service import render_report_markdown


def test_prepare_share_exige_aprovacao_explicita():
    payload = DptPrepareShareRequest()
    assert payload.aprovado is False
    assert payload.days == 30


def test_markdown_registra_publicacao_como_ato_separado():
    out = render_report_markdown(
        {
            "empresa": "Empresa Teste",
            "periodo_dias": 30,
            "generated_at": "2026-09-30T00:00:00Z",
            "situacao_juridica": [],
            "principais_riscos": [],
            "providencias_futuras": [],
            "pendencias": {},
            "mudancas_juridicas_relevantes": [],
            "recomendacoes": [],
            "proximos_passos": [],
            "nota": "Rascunho revisado.",
        }
    )
    assert "Empresa Teste" in out
    assert "publicação no Portal" in out
    assert "ato separado e explícito" in out


def test_response_nunca_nasce_publicado():
    out = DptPrepareShareResponse(
        document_id="doc-1",
        client_id="cli-1",
        next_step="Publicar explicitamente depois.",
    )
    assert out.publicado_portal is False
