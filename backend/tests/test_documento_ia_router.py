"""Router documento_ia — mitigações do intake híbrido (PR #55).

Invariante: quando o serviço devolve retorno DEGRADADO
(analise_llm_indisponivel=True — toda a cadeia de IA acabou de falhar),
o router NÃO chama o orchestrator (só adicionaria latência para falhar de
novo) e mantém o aviso no payload. No caminho normal, o núcleo continua
obrigatório.
"""
import io

from fastapi import UploadFile
from starlette.datastructures import Headers


class _User:
    id = "u-router"


def _upload_pdf() -> UploadFile:
    return UploadFile(
        file=io.BytesIO(b"%PDF-1.4 conteudo de teste"),
        filename="doc.pdf",
        headers=Headers({"content-type": "application/pdf"}),
    )


def _prepara(monkeypatch, resultado):
    """Mocka validação de magic bytes, o serviço e o orchestrator (contador)."""
    import app.routers.documents as documents
    monkeypatch.setattr(documents, "_validar_conteudo",
                        lambda ext, conteudo: "application/pdf")

    capturado = {}

    async def fake_extrair(*a, **kw):
        capturado["user_id"] = kw.get("user_id")
        return dict(resultado)

    from app.services import documento_service
    monkeypatch.setattr(documento_service, "extrair_e_analisar", fake_extrair)

    from app.services.ai.core.orchestrator import orchestrator
    chamadas = {"n": 0}

    async def fake_run(**kw):
        chamadas["n"] += 1
        return {"conteudo": "diag", "agente": "a", "modelo": "m",
                "provider": "ollama", "log_id": "l1"}

    monkeypatch.setattr(orchestrator, "run", fake_run)
    return chamadas, capturado


async def test_degradado_pula_orchestrator_e_mantem_aviso(monkeypatch):
    chamadas, capturado = _prepara(monkeypatch, {
        "ok": True,
        "parcial": True,
        "analise_llm_indisponivel": True,
        "aviso_llm": "A interpretação por IA está indisponível no momento.",
        "dados_estruturados": {"cpfs": []},
        "_texto_sanitizado": "texto [CPF] sanitizado",
    })

    from app.routers.documento_ia import analisar
    r = await analisar(file=_upload_pdf(), db=None, current_user=_User())

    assert chamadas["n"] == 0  # orchestrator NÃO foi chamado
    assert r["analise_llm_indisponivel"] is True
    assert "indispon" in r["aviso_llm"].lower()  # aviso preservado
    assert r["diagnostico_nucleo"] is None
    assert "_texto_sanitizado" not in r  # chave interna nunca vaza
    # Trilha art. 37: o router repassa o usuário autenticado ao serviço.
    assert capturado["user_id"] == "u-router"


async def test_caminho_normal_continua_chamando_orchestrator(monkeypatch):
    chamadas, _ = _prepara(monkeypatch, {
        "ok": True,
        "dados_estruturados": {"cpfs": []},
        "_texto_sanitizado": "texto [CPF] sanitizado",
    })

    from app.routers.documento_ia import analisar
    r = await analisar(file=_upload_pdf(), db=None, current_user=_User())

    assert chamadas["n"] == 1
    assert r["diagnostico_nucleo"] == "diag"
    assert "_texto_sanitizado" not in r
